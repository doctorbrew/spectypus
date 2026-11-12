"""Plan, execute, checkpoint, and summarize current manifest evidence."""
from __future__ import annotations

import os
import signal
import subprocess
import time
import uuid
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

from .adapters import engines
from .aggregate import aggregate
from .config import load_config
from .io import atomic_text, digest, file_hash, read_json, tree_hash, write_csv, write_json
from .manifest import prepare_spectra, read_manifest, spectrum_data

SCHEMA = "spectypus-plan/1"


def make_plan(manifest: Path, config: Path | dict, targets: Path | None = None) -> dict:
    config = load_config(config)
    spectra = prepare_spectra(read_manifest(Path(manifest), targets))
    provenance = {}
    for name, cfg in config["engines"].items():
        try:
            provenance[name] = engines.fingerprint(name, cfg)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            provenance[name] = {"error": f"{type(exc).__name__}: {exc}"}
    package_hash = tree_hash(Path(__file__).parent, suffixes={".py"})
    runs = []
    for spectrum in spectra:
        z = spectrum["redshift"]
        requested = config["redshift_mode"]
        if requested == "auto":
            modes = ["fixed" if z is not None else "free"]
        elif requested == "both":
            modes = ["fixed", "free"] if z is not None else ["free"]
        else:
            modes = [requested]
        primary_mode = "fixed" if z is not None and "fixed" in modes else "free"
        for name in sorted(config["engines"]):
            for mode in modes:
                reason = spectrum["blocked_reason"]
                if not reason and spectrum["duplicate_of"]:
                    reason = f"duplicate_of:{spectrum['duplicate_of']}"
                if not reason and mode == "fixed" and z is None:
                    reason = "fixed mode requires a known redshift"
                if not reason and "error" in provenance[name]:
                    reason = provenance[name]["error"]
                if not reason and name == "snid_sage":
                    stage = spectrum["staging"]
                    overlap = max(0, min(stage["max_angstrom"], 10000) - max(stage["min_angstrom"], 2500))
                    if overlap < 2000:
                        reason = "SAGE optical grid requires >=2000 Angstrom overlap in 2500–10000 Angstrom"
                    # SAGE 1.2.3 clamps the optical profile at z=1 and applies
                    # this gate even to forced-redshift matches. Unsupported
                    # searches are not valid no-good-match evidence.
                    elif mode == "fixed" and z > 1.0:
                        reason = "SAGE optical profile does not support fixed redshift above 1.0"
                    elif mode == "free" and config["free_redshift"]["max"] > 1.0:
                        reason = "SAGE optical profile does not support free-redshift ranges above 1.0"
                identity = {"spectrum": spectrum, "mode": mode, "engine": name, "config": config,
                            "provenance": provenance[name], "package_sha256": package_hash}
                runs.append({"execution_id": digest(identity), "spectrum_id": spectrum["spectrum_id"],
                             "object_id": spectrum["object_id"], "engine": name, "mode": mode,
                             "redshift": z, "primary": mode == primary_mode or len(modes) == 1,
                             "blocked_reason": reason})
                if spectrum.get("staging", {}).get("input_mask_windows"):
                    runs[-1]["input_mask_windows"] = spectrum["staging"]["input_mask_windows"]
    plan = {"schema": SCHEMA, "tier": "exploratory", "manifest": str(Path(manifest).resolve()),
            "manifest_sha256": file_hash(Path(manifest)), "targets": str(Path(targets).resolve()) if targets else None,
            "targets_sha256": file_hash(Path(targets)) if targets else None, "config": config,
            "package_sha256": package_hash, "provenance": provenance, "spectra": spectra, "runs": runs}
    plan["plan_id"] = digest(plan)
    return plan


@contextmanager
def output_lock(output: Path):
    """OS-owned advisory lock releases on crash; never trust a stale PID file."""
    import fcntl
    output.mkdir(parents=True, exist_ok=True)
    with (output / ".writer.lock").open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError(f"another writer holds {output}") from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def save_plan(plan: dict, output: Path) -> None:
    output = Path(output).expanduser().resolve()
    write_json(output / "plans" / f"{plan['plan_id']}.json", plan)
    write_json(output / "plan.json", plan)
    write_csv(output / "plan.csv", plan["runs"], ["execution_id", "object_id", "spectrum_id",
              "engine", "mode", "redshift", "primary", "blocked_reason"])


def verify_attempt(directory: Path, execution_id: str) -> dict | None:
    """Verify record and every saved artifact before any cache reuse."""
    try:
        record_path = directory / "record.json"
        if file_hash(record_path) != (directory / "record.sha256").read_text().strip():
            return None
        record = read_json(record_path)
        if record["execution_id"] != execution_id or record["schema"] != "spectypus-attempt/1":
            return None
        for relative, checksum in record["artifacts"].items():
            path = (directory / relative).resolve()
            if not path.is_relative_to(directory.resolve()) or file_hash(path) != checksum:
                return None
        if not isinstance(record.get("candidates"), list):
            return None
        return record
    except (OSError, ValueError, KeyError, TypeError):
        return None


def current_record(output: Path, run: dict) -> dict | None:
    parent = output / "attempts" / run["execution_id"]
    try:
        pointer = read_json(parent / "current.json")
        directory = (parent / pointer["trial"]).resolve()
        if directory.parent != parent.resolve():
            return None
        return verify_attempt(directory, run["execution_id"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _run_process(command: list[str], cwd: Path, env: dict, directory: Path, timeout: float) -> tuple[int | None, bool]:
    """Stream logs to disk; kill the whole process group on timeout/interruption."""
    with (directory / "stdout.log").open("w") as stdout, (directory / "stderr.log").open("w") as stderr:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
        try:
            return process.wait(timeout=timeout), False
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            return None, True
        except BaseException:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise


def _verify_runtime(run: dict, plan: dict, record: dict, when: str) -> None:
    """Fail closed if mutable external dependencies drift during a batch."""
    observed = {"engine": engines.fingerprint(run["engine"], plan["config"]["engines"][run["engine"]]),
                "package_sha256": tree_hash(Path(__file__).parent, suffixes={".py"})}
    record.setdefault("runtime_checks", {})[when] = observed
    if observed["engine"] != plan["provenance"][run["engine"]]:
        raise ValueError(f"engine provenance changed {when} execution")
    if observed["package_sha256"] != plan["package_sha256"]:
        raise ValueError(f"Spectypus source changed {when} execution")


def execute_one(run: dict, plan: dict, output: Path) -> dict:
    parent = output / "attempts" / run["execution_id"]
    directory = parent / uuid.uuid4().hex
    directory.mkdir(parents=True)
    started = time.monotonic()
    record = {"schema": "spectypus-attempt/1", "execution_id": run["execution_id"], "run": run,
              "tier": "exploratory", "status": "failed", "reason": "", "candidates": [],
              "provenance": plan["provenance"][run["engine"]], "package_sha256": plan["package_sha256"],
              "config": plan["config"], "returncode": None, "attempt_path": str(directory)}
    try:
        _verify_runtime(run, plan, record, "before")
        spectrum = next(s for s in plan["spectra"] if s["spectrum_id"] == run["spectrum_id"])
        content, staging = spectrum_data(spectrum)
        if staging != spectrum["staging"]:
            raise ValueError("source input changed since plan creation")
        record["staging"] = staging
        atomic_text(directory / "spectrum.txt", content)
        write_json(directory / "input_staging.json", staging)
        if run["engine"] == "ngsf":
            parameters = Path(plan["config"]["engines"]["ngsf"]["parameters"])
            if file_hash(parameters) != record["provenance"]["parameters_sha256"]:
                raise ValueError("NGSF parameter template changed since plan creation")
        command, cwd, result_path = engines.build_command(run, plan["config"], directory)
        record.update(command=command, cwd=str(cwd), native_result=str(result_path.relative_to(directory)))
        env = {**os.environ, "MPLBACKEND": "Agg", "MPLCONFIGDIR": str(directory / "mpl-cache"),
               "XDG_CACHE_HOME": str(directory / "xdg-cache"), "PYTHONDONTWRITEBYTECODE": "1"}
        returncode, timed_out = _run_process(command, cwd, env, directory, plan["config"]["timeout_seconds"])
        record["returncode"] = returncode
        _verify_runtime(run, plan, record, "after")
        if timed_out:
            record["reason"] = "timeout"
        elif run["engine"] == "snid_sage" and result_path.is_file():
            candidates, status = engines.parse_result(run["engine"], result_path)
            # SAGE returns nonzero for semantic no-good-match; arbitrary engine
            # errors with a captured successful result must remain failures.
            diagnostic = (directory / "stdout.log").read_text(errors="replace") + (directory / "stderr.log").read_text(errors="replace")
            if returncode != 0 and not (status == "no_good_match" and "no good matches found" in diagnostic.lower()):
                raise ValueError(f"engine exit {returncode} despite candidate capture")
            record.update(candidates=candidates, status=status)
        elif returncode != 0:
            record["reason"] = f"engine exit {returncode}"
        else:
            candidates, status = engines.parse_result(run["engine"], result_path)
            record.update(candidates=candidates, status=status)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        record["reason"] = f"{type(exc).__name__}: {exc}"
    record["elapsed_seconds"] = time.monotonic() - started
    record["artifacts"] = {p.relative_to(directory).as_posix(): file_hash(p) for p in sorted(directory.rglob("*"))
                           if p.is_file() and not {"mpl-cache", "xdg-cache"}.intersection(p.parts)}
    write_json(directory / "record.json", record)
    atomic_text(directory / "record.sha256", file_hash(directory / "record.json") + "\n")
    write_json(parent / "current.json", {"trial": directory.name})
    return record


def _summarize(plan: dict, output: Path, *, display="report") -> dict:
    records, states, matches = {}, [], []
    for run in plan["runs"]:
        record = None if run["blocked_reason"] else current_record(output, run)
        if record:
            records[run["execution_id"]] = record
            for candidate in record["candidates"][:plan["config"]["top_n"]]:
                matches.append({**run, **candidate, "attempt_path": record["attempt_path"], "run_status": record["status"]})
        state = "blocked" if run["blocked_reason"] else record["status"] if record else "pending"
        invalid = not run["blocked_reason"] and not record and (output / "attempts" / run["execution_id"] / "current.json").exists()
        if invalid:
            state = "invalid_evidence"
        states.append({**run, "status": state, "reason": run["blocked_reason"] or (record["reason"] if record else
                      "Saved result failed verification" if invalid else "Not executed yet")})
    summary = aggregate(plan, records)
    summary["run_counts"] = dict(sorted(Counter(row["status"] for row in states).items()))
    summary["all_runs_terminal"] = all(row["status"] in engines.TERMINAL or row["blocked_reason"].startswith("duplicate_of:") for row in states)
    write_json(output / "summary.json", summary)
    write_csv(output / "run_status.csv", states, ["execution_id", "spectrum_id", "object_id", "engine", "mode", "primary", "status", "reason"])
    write_csv(output / "matches.csv", matches, ["object_id", "spectrum_id", "engine", "mode", "primary", "execution_id",
              "run_status", "rank", "template", "template_epoch_id", "native_class", "native_subtype", "class_label",
              "phase_days", "redshift", "metric", "metric_direction", "score", "qualified", "native", "attempt_path"])
    write_csv(output / "objects.csv", summary["objects"], ["object_id", "status", "proposed_class", "complete", "spectrum_count",
              "unique_spectrum_count", "duplicate_count", "contributing_spectra", "support_mass", "abstention_mass", "ranked_classes", "spectrum_ids", "frame_assumed", "frame_review_required"])
    write_csv(output / "spectra.csv", summary["spectra"], ["object_id", "spectrum_id", "status", "proposed_class", "complete",
              "duplicate_of", "expected_engines", "contributing_engines", "support_mass", "abstention_mass", "ranked_classes", "engine_evidence", "diagnostic_fits", "frame_assumed", "frame_review_required"])
    from .reporting.report import _write_report
    summary["report"] = _write_report(plan, records, states, output, display=display)
    write_json(output / "summary.json", summary)
    return summary


def summarize_output(output: Path, *, tns: bool = False, refresh_tns: bool = False, display: str = "report") -> dict:
    if display not in {"report", "atlas"}:
        raise ValueError("display must be report or atlas")
    output = Path(output).expanduser().resolve()
    with output_lock(output):
        plan = read_json(output / "plan.json")
        identity = plan.pop("plan_id")
        if plan.get("schema") != SCHEMA or digest(plan) != identity:
            raise ValueError("current plan integrity check failed")
        plan["plan_id"] = identity
        metadata = None
        if tns or refresh_tns:
            from .reporting.metadata import fetch_tns
            metadata = fetch_tns(output, plan['spectra'], refresh=refresh_tns)
        summary = _summarize(plan, output, display=display)
        if metadata is not None:
            summary['tns'] = metadata
        return summary


def run_batch(manifest: Path, config: Path | dict, output: Path, *, targets: Path | None = None,
              max_runs: int | None = None, execute: bool = True, progress=None, tns: bool = False, display: str = "report") -> dict:
    if max_runs is not None and (type(max_runs) is not int or max_runs < 1):
        raise ValueError("max_runs must be a positive integer")
    if display not in {"report", "atlas"}:
        raise ValueError("display must be report or atlas")
    output = Path(output).expanduser().resolve()
    with output_lock(output):
        plan = make_plan(manifest, config, targets)
        save_plan(plan, output)
        metadata = None
        if tns and execute:
            from .reporting.metadata import fetch_tns
            metadata = fetch_tns(output, plan['spectra'])
        # A readable pending log exists even while the first fit is running.
        _summarize(plan, output, display=display)
        launched = reused = 0
        for run in plan["runs"]:
            if run["blocked_reason"]:
                continue
            prior = current_record(output, run)
            if prior and prior["status"] in engines.TERMINAL:
                reused += 1
                continue
            if not execute or max_runs is not None and launched >= max_runs:
                continue
            record = execute_one(run, plan, output)
            launched += 1
            if progress:
                progress(f"{run['object_id']} / {run['spectrum_id']} / {run['engine']} {run['mode']}: {record['status']} ({record['elapsed_seconds']:.1f}s)")
            _summarize(plan, output, display=display)
        summary = _summarize(plan, output, display=display)
        summary["invocation"] = {"executed": launched, "reused": reused, "execution_requested": execute,
                                 "max_runs": max_runs}
        if metadata is not None:
            summary['tns'] = metadata
        write_json(output / "summary.json", summary)
        return summary

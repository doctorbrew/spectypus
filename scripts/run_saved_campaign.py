#!/usr/bin/env python3
"""Run a frozen batch with bounded processes and one authoritative controller."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import uuid

from spectypus.io import write_json, read_json, digest, file_hash
from spectypus.pipeline import make_plan, save_plan, execute_one, current_record, output_lock, _summarize
import spectypus


def checked_plan(path):
    plan = read_json(path)
    identity = plan.pop("plan_id")
    if plan.get("schema") != "spectypus-plan/1" or digest(plan) != identity:
        raise ValueError("saved plan integrity check failed")
    plan["plan_id"] = identity
    return plan


def start_worker(run, plan, output, launch_dir):
    # Each worker imports the same frozen package as this controller. It only
    # writes its unique attempt; the controller retains the campaign lock.
    env = {**os.environ, "PYTHONPATH": str(Path(spectypus.__file__).resolve().parent.parent),
           "PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[key] = "1"
    with (launch_dir / f"{run['execution_id']}.log").open("w") as log:
        return subprocess.Popen([sys.executable, str(launch_dir / "controller.py"),
            str(output.parent), "--worker-run", run["execution_id"]],
            env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)


def stop_workers(active):
    # SIGTERM raises KeyboardInterrupt in each worker's main thread, so the
    # existing execute_one cleanup kills and reaps its engine process group.
    for process, _ in active.values():
        if process.poll() is None:
            process.terminate()
    for process, _ in active.values():
        process.wait()


def execute_queue(queue, plan, output, workers, launch_dir, active_changed, disk_check):
    if workers == 1:
        for run in queue:
            disk_check()
            active_changed([run])
            yield run, execute_one(run, plan, output)
            active_changed([])
        return
    active = {}
    pending = iter(queue)
    exhausted = False
    try:
        while active or not exhausted:
            while len(active) < workers and not exhausted:
                try:
                    run = next(pending)
                except StopIteration:
                    exhausted = True
                    break
                disk_check()
                process = start_worker(run, plan, output, launch_dir)
                active[run["execution_id"]] = (process, run)
                active_changed([r for _, r in active.values()])
            done = next((key for key, (p, _) in active.items() if p.poll() is not None), None)
            if done is None:
                if active:
                    time.sleep(0.1)
                continue
            process, run = active.pop(done)
            if process.returncode != 0:
                raise RuntimeError(f"worker exited {process.returncode}: {run['execution_id']}; see {launch_dir}")
            record = current_record(output, run)
            if record is None:
                raise RuntimeError(f"worker did not save verified evidence: {run['execution_id']}")
            active_changed([r for _, r in active.values()])
            yield run, record
    finally:
        stop_workers(active)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    parser.add_argument("--prioritize-batch", default="")
    parser.add_argument("--max-runs", type=int)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--summary-interval", type=float, default=300,
                        help="Seconds between full verified summary exports; also export on exit")
    parser.add_argument("--worker-run", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.max_runs is not None and args.max_runs < 1:
        parser.error("--max-runs must be positive")
    if args.workers < 1 or not math.isfinite(args.summary_interval) or args.summary_interval < 0:
        parser.error("--workers must be positive and --summary-interval nonnegative")
    root = args.campaign.resolve()
    output = root / "run"
    report = {"schema": "spectypus-campaign/1", "pid": os.getpid(), "status": "starting",
              "started_at": datetime.now(timezone.utc).isoformat(),
              "runtime": str(Path(spectypus.__file__).resolve().parent.parent),
              "workers": args.workers, "minimum_free_gib": 20, "completed_this_invocation": 0,
              "summary_interval_seconds": args.summary_interval, "controller_sha256": file_hash(Path(__file__))}
    started = time.monotonic()
    acquired = False
    launch_dir = None

    def interrupted(signum, frame):
        raise KeyboardInterrupt(f"signal {signum}")

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)

    if args.worker_run:
        plan = checked_plan(output / "plan.json")
        run = next(r for r in plan["runs"] if r["execution_id"] == args.worker_run)
        if run["blocked_reason"]:
            raise ValueError("cannot execute a blocked run")
        execute_one(run, plan, output)
        return

    def checkpoint(**values):
        report.update(values, updated_at=datetime.now(timezone.utc).isoformat(),
                      elapsed_seconds=round(time.monotonic() - started, 2))
        write_json(root / "campaign_status.json", report)
        if launch_dir is not None:
            write_json(launch_dir / "status.json", report)

    try:
        # This controller never edits engine settings or changes the selection.
        with output_lock(output):
            acquired = True
            plan = make_plan(root / "spectra.csv", root / "config.json")
            if (output / "plan.json").exists() and checked_plan(output / "plan.json")["plan_id"] != plan["plan_id"]:
                raise ValueError("frozen plan changed; prepare a separate campaign")
            save_plan(plan, output)
            launch_dir = root / "controller_runs" / uuid.uuid4().hex
            launch_dir.mkdir(parents=True)
            shutil.copy2(__file__, launch_dir / "controller.py")
            report["controller_snapshot"] = str(launch_dir / "controller.py")
            eligible = [r for r in plan["runs"] if not r["blocked_reason"]]
            sources = {s["spectrum_id"]: s for s in plan["spectra"]}
            # Start with the shortest/longest fixed and free inputs. These are
            # real members of the full batch, and their results count once.
            representatives = []
            for mode in ("fixed", "free"):
                ids = sorted({r["spectrum_id"] for r in eligible if r["mode"] == mode},
                             key=lambda sid: sources[sid]["staging"]["samples"])
                for sid in ([ids[0], ids[-1]] if ids else []):
                    representatives.extend(r for r in eligible if r["spectrum_id"] == sid)
            seen = set()
            queue = []
            for run in representatives + eligible:
                if run["execution_id"] not in seen:
                    queue.append(run)
                    seen.add(run["execution_id"])
            if args.prioritize_batch:
                queue.sort(key=lambda r: sources[r["spectrum_id"]].get("batch") != args.prioritize_batch)
            # Date-window ZTF objects always precede the rest; within each group
            # fixed redshifts finish before the more expensive free searches.
            queue.sort(key=lambda r: (sources[r['spectrum_id']].get('priority_ztf') != 'true', r['mode'] != 'fixed'))
            checkpoint(status="running", plan_id=plan["plan_id"], eligible_runs=len(queue),
                       representative_runs=[r["execution_id"] for r in representatives])
            summary = _summarize(plan, output)
            counts = Counter(summary["run_counts"])
            previous = {}
            remaining = []
            for run in queue:
                prior = current_record(output, run)
                if prior and prior["status"] in {"completed", "no_good_match"}:
                    continue
                previous[run["execution_id"]] = prior["status"] if prior else "pending"
                remaining.append(run)
            if args.max_runs:
                remaining = remaining[:args.max_runs]
            checkpoint(runs=dict(counts), active=None, active_runs=[])
            last_summary = time.monotonic()
            failures_in_a_row = 0

            def active_changed(runs):
                active = [{k: r[k] for k in ("execution_id", "object_id", "spectrum_id", "engine", "mode")} for r in runs]
                checkpoint(active=active[0] if active else None, active_runs=active)

            def disk_check():
                if shutil.disk_usage(root).free < 20 * 1024**3:
                    raise RuntimeError("Stopped: less than 20 GiB disk space remains")

            jobs = execute_queue(remaining, plan, output, args.workers, launch_dir, active_changed, disk_check)
            try:
                for run, record in jobs:
                    failures_in_a_row = failures_in_a_row + 1 if record["status"] == "failed" else 0
                    report["completed_this_invocation"] += 1
                    counts[previous[run['execution_id']]] -= 1
                    counts[record['status']] += 1
                    print(f"{report['completed_this_invocation']}/{len(queue)} {run['object_id']} {run['engine']} {run['mode']}: {record['status']} ({record['elapsed_seconds']:.1f}s) {record['reason']}", flush=True)
                    checkpoint(runs={k: v for k, v in counts.items() if v})
                    if failures_in_a_row >= 6:
                        raise RuntimeError("Stopped after six consecutive failures; inspect the saved logs")
                    if time.monotonic() - last_summary >= args.summary_interval:
                        _summarize(plan, output)
                        last_summary = time.monotonic()
            finally:
                jobs.close()
                summary = _summarize(plan, output)
                checkpoint(active=None, active_runs=[], runs=summary['run_counts'])
            checkpoint(status="limited" if args.max_runs and len(remaining) == args.max_runs else "finished",
                       active=None, active_runs=[], runs=summary["run_counts"])
    except (Exception, KeyboardInterrupt) as exc:
        if acquired:
            checkpoint(status="stopped", reason=f"{type(exc).__name__}: {exc}", active=None)
        raise


if __name__ == "__main__":
    main()

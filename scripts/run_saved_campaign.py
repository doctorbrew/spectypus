#!/usr/bin/env python3
"""Run a finite frozen batch serially, with a disk guard and durable status."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import signal
import sys
import time

from spectypus.io import write_json
from spectypus.pipeline import make_plan, save_plan, execute_one, current_record, output_lock, _summarize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    args = parser.parse_args()
    root = args.campaign.resolve()
    output = root / "run"
    report = {"schema": "spectypus-campaign/1", "pid": os.getpid(), "status": "starting",
              "started_at": datetime.now(timezone.utc).isoformat(), "runtime": sys.path[0],
              "workers": 1, "minimum_free_gib": 20, "completed_this_invocation": 0}
    started = time.monotonic()
    acquired = False

    def interrupted(signum, frame):
        raise KeyboardInterrupt(f"signal {signum}")

    signal.signal(signal.SIGTERM, interrupted)

    def checkpoint(**values):
        report.update(values, updated_at=datetime.now(timezone.utc).isoformat(),
                      elapsed_seconds=round(time.monotonic() - started, 2))
        write_json(root / "campaign_status.json", report)

    try:
        # This controller never edits engine settings or changes the selection.
        with output_lock(output):
            acquired = True
            plan = make_plan(root / "spectra.csv", root / "config.json")
            save_plan(plan, output)
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
            checkpoint(status="running", plan_id=plan["plan_id"], eligible_runs=len(queue),
                       representative_runs=[r["execution_id"] for r in representatives])
            _summarize(plan, output)
            failures_in_a_row = 0
            for run in queue:
                prior = current_record(output, run)
                if prior and prior["status"] in {"completed", "no_good_match"}:
                    continue
                if shutil.disk_usage(root).free < 20 * 1024**3:
                    raise RuntimeError("Stopped: less than 20 GiB disk space remains")
                checkpoint(active={k: run[k] for k in ("execution_id", "object_id", "spectrum_id", "engine", "mode")})
                record = execute_one(run, plan, output)
                failures_in_a_row = failures_in_a_row + 1 if record["status"] == "failed" else 0
                report["completed_this_invocation"] += 1
                print(f"{report['completed_this_invocation']}/{len(queue)} {run['object_id']} {run['engine']} {run['mode']}: {record['status']} ({record['elapsed_seconds']:.1f}s) {record['reason']}", flush=True)
                summary = _summarize(plan, output)
                checkpoint(active=None, runs=summary["run_counts"])
                if failures_in_a_row >= 6:
                    raise RuntimeError("Stopped after six consecutive failures; inspect the saved logs")
            checkpoint(status="finished", active=None, runs=_summarize(plan, output)["run_counts"])
    except (Exception, KeyboardInterrupt) as exc:
        if acquired:
            checkpoint(status="stopped", reason=f"{type(exc).__name__}: {exc}", active=None)
        raise


if __name__ == "__main__":
    main()

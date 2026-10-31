"""Command-line interface for inspectable, resumable batches."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import __version__
from .adapters.engines import fingerprint
from .config import EXAMPLE, load_config
from .io import write_json
from .manifest import discover
from .pipeline import run_batch, summarize_output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="spectypus", description="Supernova classification across engines and epochs")
    parser.add_argument("--version", action="version", version=f"spectypus {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="write an editable engine configuration; never overwrite")
    init.add_argument("--config", type=Path, default=Path("spectypus.local.json"))
    manifest = sub.add_parser("manifest", help="scan an explicit directory layout into a CSV manifest")
    manifest.add_argument("root", type=Path)
    manifest.add_argument("--output", type=Path, required=True)
    manifest.add_argument("--layout", choices=["object", "batch-object"], required=True)
    manifest.add_argument("--frame", choices=["observer", "rest"], required=True)
    manifest.add_argument("--unit", choices=["angstrom", "nm"], required=True)
    for command in ("plan", "run"):
        child = sub.add_parser(command, help="plan without fitting" if command == "plan" else "execute missing/failed attempts")
        child.add_argument("--manifest", type=Path, required=True)
        child.add_argument("--targets", type=Path)
        child.add_argument("--config", type=Path, required=True)
        child.add_argument("--output", type=Path, required=True)
        if command == "run":
            child.add_argument("--max-runs", type=int, help="limit new engine attempts; summaries report pending work")
    summarize = sub.add_parser("summarize", help="verify saved attempts and rebuild summaries without executing engines")
    summarize.add_argument("--output", type=Path, required=True)
    doctor = sub.add_parser("doctor", help="inspect configured interpreters, engine sources, and template banks")
    doctor.add_argument("--config", type=Path, required=True)
    review = sub.add_parser("review", help="open a local read-only results website")
    review.add_argument("--output", type=Path, required=True)
    review.add_argument("--port", type=int, default=8013)
    args = parser.parse_args(argv)
    try:
        if args.command == "review":
            try:
                import uvicorn
                from .review import create_app
                app = create_app(args.output)
            except ImportError as exc:
                raise ValueError("Install the viewer with: pip install 'spectypus[web]'") from exc
            if not 1 <= args.port <= 65535:
                raise ValueError("port must be between 1 and 65535")
            if not (args.output / "plan.json").is_file():
                raise ValueError("output has no plan.json; plan or run a batch first")
            print(f"Spectypus results: http://127.0.0.1:{args.port}", flush=True)
            uvicorn.run(app, host="127.0.0.1", port=args.port)
            return 0
        if args.command == "init":
            if args.config.exists():
                raise ValueError(f"refusing to overwrite {args.config}")
            write_json(args.config, EXAMPLE)
            print(f"Edit engine paths and redshift range in {args.config.resolve()}")
            return 0
        if args.command == "manifest":
            count = discover(args.root, args.output, layout=args.layout, frame=args.frame, unit=args.unit)
            print(f"Wrote {count} spectrum records to {args.output.resolve()}; inspect object identities before running")
            return 0
        if args.command == "doctor":
            config = load_config(args.config)
            healthy = True
            for name, settings in sorted(config["engines"].items()):
                try:
                    result = fingerprint(name, settings)
                    print(json.dumps({"engine": name, "status": "ready", "fingerprint": result}, sort_keys=True))
                except (OSError, ValueError, subprocess.SubprocessError) as exc:
                    healthy = False
                    print(json.dumps({"engine": name, "status": "unavailable", "reason": str(exc)}))
            return 0 if healthy else 1
        if args.command == "summarize":
            summary = summarize_output(args.output)
        else:
            summary = run_batch(args.manifest, args.config, args.output, targets=args.targets,
                                max_runs=getattr(args, "max_runs", None), execute=args.command == "run",
                                progress=lambda line: print(line, flush=True))
        print(json.dumps({"output": str(args.output.resolve()), "objects": len(summary["objects"]),
                          "runs": summary["run_counts"], "all_runs_terminal": summary["all_runs_terminal"],
                          "invocation": summary.get("invocation")}, sort_keys=True))
        # A deliberate --max-runs subset is a valid partial invocation; failures
        # and scientific input blocks still produce a nonzero command status.
        failures = summary["run_counts"].get("failed", 0)
        nonduplicate_blocks = any(not s.get("complete", False) and s.get("status") != "duplicate"
                                  and any(e["status"] == "blocked" for e in s.get("engine_evidence", []))
                                  for s in summary["spectra"])
        return 1 if args.command != "plan" and (failures or nonduplicate_blocks) else 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"spectypus: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("spectypus: interrupted; rerun to resume. Partial attempt files are retained.", file=sys.stderr)
        return 130

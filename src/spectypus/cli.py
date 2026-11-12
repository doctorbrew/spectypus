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
from .night import prepare_night
from .pipeline import run_batch, summarize_output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="spectypus", description="Supernova classification across engines and epochs")
    parser.add_argument("--version", action="version", version=f"spectypus {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="write an editable engine configuration; never overwrite")
    init.add_argument("--config", type=Path, default=Path("spectypus.local.json"))
    night = sub.add_parser("night", help="type reduced ASCII spectra or an EFOSpec nightly output")
    night.add_argument("folder", type=Path)
    night.add_argument("--config", type=Path, help="installation settings; otherwise SPECTYPUS_CONFIG, local or user config")
    night.add_argument("--output", type=Path, help="results directory (default: FOLDER/spectypus)")
    night.add_argument("--pattern", help="optional filename glob (default: .txt/.asci/.ascii/.dat or EFOSpec science exports)")
    night.add_argument("--frame", choices=["observer", "rest"], help="flat-folder input frame (default: observer)")
    night.add_argument("--unit", choices=["angstrom", "nm"], help="flat-folder wavelength unit (default: angstrom)")
    night.add_argument("--nonfinite", choices=["mask", "reject"], default="mask", help="nonfinite flux policy (default: mask and record exclusions)")
    night.add_argument("--targets", type=Path, help="optional object_id,redshift,redshift_source CSV; EFOSpec object name or flat-folder filename stem")
    night.add_argument("--mode", choices=["auto", "both", "free", "fixed"], default="both",
                       help="redshift modes (default: both for known z, free for unknown z)")
    for key in ("min", "max", "step"):
        night.add_argument(f"--z-{key}", type=float, help=f"override configured free-redshift {key}")
    night.add_argument("--plan-only", action="store_true", help="check inputs and save the plan without fitting")
    night.add_argument("--max-runs", type=int, help="limit new engine attempts, not spectra")
    night.add_argument("--timeout", type=float, default=1800, help="seconds per engine attempt (default: 1800)")
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
    summarize = sub.add_parser("summarize", help="verify saved attempts and rebuild CSV/HTML logs without executing engines")
    summarize.add_argument("--output", type=Path, required=True)
    summarize.add_argument("--refresh-tns", action="store_true", help="refresh cached TNS discovery metadata; never refit")
    doctor = sub.add_parser("doctor", help="inspect configured interpreters, engine sources, and template banks")
    doctor.add_argument("--config", type=Path, required=True)
    review = sub.add_parser("review", help="open a local read-only results website")
    review.add_argument("--output", type=Path, required=True)
    review.add_argument("--port", type=int, default=8013)
    selected = sub.add_parser('plot-log', help='export selected matches from a saved reviewer JSON log; never refit')
    selected.add_argument('--output', type=Path, required=True)
    selected.add_argument('--log', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'plot-log':
            from .io import read_json
            from .reporting.selected import export_selected
            print(json.dumps(export_selected(args.output, read_json(args.log)), sort_keys=True))
            return 0
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
        if args.command == "night":
            if args.max_runs is not None and args.max_runs < 1:
                raise ValueError("max_runs must be a positive integer")
            manifest, config, args.output = prepare_night(
                args.folder, config=args.config, output=args.output, pattern=args.pattern,
                frame=args.frame, unit=args.unit, mode=args.mode,
                z_min=args.z_min, z_max=args.z_max, z_step=args.z_step, nonfinite=args.nonfinite,
                timeout=args.timeout)
            print(f"Nightly selection: {manifest}; nonfinite flux: {args.nonfinite}. Results: {args.output}", flush=True)
            summary = run_batch(manifest, config, args.output, targets=args.targets,
                                max_runs=args.max_runs, execute=not args.plan_only, tns=True,
                                progress=lambda line: print(line, flush=True))
        elif args.command == "summarize":
            summary = summarize_output(args.output, refresh_tns=args.refresh_tns)
        else:
            summary = run_batch(args.manifest, args.config, args.output, targets=args.targets,
                                max_runs=getattr(args, "max_runs", None), execute=args.command == "run", tns=True,
                                progress=lambda line: print(line, flush=True))
        print(json.dumps({"output": str(args.output.resolve()), "objects": len(summary["objects"]), 'tns': summary.get('tns'),
                          "runs": summary["run_counts"], "all_runs_terminal": summary["all_runs_terminal"],
                          "html": summary["report"]["path"],
                          "invocation": summary.get("invocation")}, sort_keys=True))
        # A deliberate --max-runs subset is a valid partial invocation; failures
        # and scientific input blocks still produce a nonzero command status.
        failures = summary["run_counts"].get("failed", 0) + summary["run_counts"].get("invalid_evidence", 0)
        nonduplicate_blocks = any(not s.get("complete", False) and s.get("status") != "duplicate"
                                  and any(e["status"] == "blocked" for e in s.get("engine_evidence", []))
                                  for s in summary["spectra"])
        planning = args.command == "plan" or args.command == "night" and args.plan_only
        return 1 if not planning and (failures or nonduplicate_blocks) else 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"spectypus: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("spectypus: interrupted; rerun to resume. Partial attempt files are retained.", file=sys.stderr)
        return 130

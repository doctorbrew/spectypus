#!/usr/bin/env python3
"""Create a masked follow-up batch for spectra without two successful fits."""
import argparse
from collections import defaultdict
from pathlib import Path
import shutil

from spectypus.features import TELLURIC_WINDOWS
from spectypus.io import file_hash, read_csv, read_json, write_csv, write_json
from spectypus.review import read_snapshot


def remove_identical_rows(source, destination):
    """Only repeated identical numeric rows; conflicting fluxes are not merged."""
    samples, lines, removed = {}, [], 0
    for line in source.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            lines.append(line)
            continue
        values = tuple(map(float, line.split()))
        wave = values[0]
        if wave in samples:
            if samples[wave] != values:
                raise ValueError("duplicate wavelength with differing values")
            removed += 1
        else:
            samples[wave] = values
            lines.append(line)
    if not removed:
        raise ValueError("no exact duplicate rows")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text('\n'.join(lines) + '\n')
    return {"original": str(source), "original_sha256": file_hash(source),
            "derived": str(destination), "derived_sha256": file_hash(destination),
            "removed_identical_rows": removed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    previous, output = args.previous.resolve(), args.output.resolve()
    if output.exists():
        parser.error("output already exists")
    snapshot = read_snapshot(previous / 'run')
    runs = defaultdict(list)
    for run in snapshot['runs']:
        runs[run['spectrum_id']].append(run)
    done = {sid for sid, rows in runs.items() if rows and all(r['status'] == 'completed' for r in rows)}
    # Exclude copies of a completed spectrum as well as its canonical row.
    done |= {s['spectrum_id'] for s in snapshot['plan']['spectra'] if s['duplicate_of'] in done}
    sources = {s['spectrum_id']: s for s in snapshot['plan']['spectra']}
    rows = read_csv(previous / 'spectra.csv')
    output.mkdir(parents=True)
    repairs, selected, excluded = [], [], []
    for row in rows:
        sid = row['spectrum_id']
        if sid in done:
            excluded.append({'spectrum_id': sid, 'reason': 'both classifiers completed in previous batch'})
            continue
        row['previous_states'] = [{k: r[k] for k in ('engine', 'status', 'execution_id')} for r in runs[sid]]
        if 'duplicate wavelengths' in sources[sid]['blocked_reason']:
            source = Path(row['path'])
            destination = output / 'derived_inputs' / source.name
            try:
                repair = remove_identical_rows(source, destination)
                repairs.append(repair)
                row['path'] = str(destination)
            except ValueError:
                pass  # differing data stay blocked; never average silently
        selected.append(row)
    write_csv(output / 'spectra.csv', selected, list(selected[0]))
    write_csv(output / 'previous_successes.csv', excluded, ['spectrum_id', 'reason'])
    cfg = read_json(previous / 'config.json')
    cfg['telluric_windows'] = TELLURIC_WINDOWS
    write_json(output / 'config.json', cfg)
    write_json(output / 'selection.json', {'previous_output': str(previous),
        'previous_plan_id': snapshot['plan']['plan_id'], 'selected_records': len(selected),
        'previous_successes_retained': len(excluded), 'repairs': repairs,
        'policy': 'Both engines for each spectrum with any pending, failed, blocked or no-good-match fit. Earlier successful pairs remain in previous_output.'})
    print(f"Selected {len(selected)} records; kept {len(excluded)} prior successful records; repaired {len(repairs)} inputs")


if __name__ == '__main__':
    main()

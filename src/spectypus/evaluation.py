"""Read-only, object-level evaluation of saved native matches against sourced labels.

This evaluates a declared sample, not confidence calibration. Fixed/free modes
and engines remain separate. Selection never depends on scores or fit success.
"""
from collections import Counter
import argparse
import math
import re
from pathlib import Path

from .io import digest, file_hash, read_json, tree_hash, write_json
from .phases import number
from .pipeline import SCHEMA, verify_attempt


def identity(value):
    return re.sub(r'^(?:sn|at)(?=\d{4})', '', re.sub(r'\s+', '', value.casefold()))


def validate_labels(labels):
    seen = set()
    if labels.get('schema') != 'spectypus-evaluation-labels/1' or not labels.get('objects'):
        raise ValueError('Expected nonempty spectypus-evaluation-labels/1')
    for row in labels['objects']:
        names = {identity(n) for n in [row['object_id'], *row['aliases']]}
        if not all(names) or seen.intersection(names):
            raise ValueError('Duplicate or overlapping object identities')
        seen.update(names)
        if (row.get('review_status') != 'accepted' or not row.get('class_label')
                or not row.get('references') or
                any(not r.get('url', '').startswith('https://') or not r.get('locator')
                    for r in row['references'])):
            raise ValueError('Each label needs an accepted review and located independent references')


def select_spectrum(sources):
    """Earliest finite-MJD supported, nonduplicate, nonprovisional observation."""
    eligible = [s for s in sources if not s.get('blocked_reason') and not s.get('duplicate_of')
                and not s.get('identity_conflict')
                and s.get('frame_assumed') not in (True, 'true')
                and number(s.get('mjd')) is not None]
    return min(eligible, key=lambda s: (number(s['mjd']), s['spectrum_id'])) if eligible else None


def wilson_interval(successes, total):
    if not total:
        return None
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + z * z / total
    centre = (proportion + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total)) / denominator
    return [max(0, centre - radius), min(1, centre + radius)]


def native_label(match):
    if match.get('native_class') == 'SLSN' and match.get('native_subtype') in {'SLSN-I', 'SLSN-II'}:
        return match['native_subtype']
    return match.get('class_label') or None


def summarize_rows(rows, *, prediction_key="prediction", outcome_key="outcome"):

    groups = {}
    for engine, mode in sorted({(r['engine'], r['mode']) for r in rows}):
        cohort = [r for r in rows if (r['engine'], r['mode']) == (engine, mode)]
        for stratum in ('all', 'no_known_alias_overlap'):
            sample = cohort if stratum == 'all' else [r for r in cohort if r['overlap'] == stratum]
            predicted = [r for r in sample if r[prediction_key]]
            correct = sum(r[prediction_key] == r['truth'] for r in sample)
            counts = Counter(r[outcome_key] for r in sample)
            classes = {}
            for truth in sorted({r['truth'] for r in sample}):
                positives = [r for r in sample if r['truth'] == truth]
                hits = sum(r[prediction_key] == truth for r in positives)
                top3 = sum(any((native_label(m) if prediction_key == 'native_prediction' else m.get('class_label')) == truth
                               for m in r.get('native_top_three', []))
                           for r in positives if r[outcome_key] in {'predicted', 'unsupported_taxonomy'})
                classes[truth] = {'objects': len(positives), 'recovered': hits,
                                  'recovery_fraction': hits / len(positives),
                                  'wilson95': wilson_interval(hits, len(positives)),
                                  'top3_recovered': top3, 'top3_recovery_fraction': top3 / len(positives)}
            groups[f'{engine}/{mode}/{stratum}'] = {
                'objects': len(sample), 'predictions': len(predicted), 'correct': correct,
                'coverage': len(predicted) / len(sample) if sample else None,
                'outcomes': dict(sorted(counts.items())), 'by_class': classes,
                'confusion': dict(sorted(Counter(
                    r['truth'] + ' -> ' + (r[prediction_key] or '[' + r[outcome_key] + ']')
                    for r in sample).items()))}
    return groups


def bank_inventory(engine, path):
    path = Path(path).resolve()
    if engine == 'snid_sage':
        names = list(read_json(path / 'template_index.json')['templates'])
    elif engine == 'ngsf':
        names = [p.name for p in (path / 'original_resolution' / 'sne').glob('*/*') if p.is_dir()]
    else:
        raise ValueError('Unsupported evaluation engine')
    if not names:
        raise ValueError(f'Empty template identity inventory: {path}')
    return {'path': str(path), 'sha256': tree_hash(path), 'names': sorted(names)}


def evaluate_saved(saved_output, labels, banks):
    validate_labels(labels)
    if not banks:
        raise ValueError('At least one explicit engine bank is required')
    saved_output = Path(saved_output).resolve()
    plan_path = saved_output / 'plan.json'
    plan_sha256 = file_hash(plan_path)
    plan = read_json(plan_path)
    plan_id = plan['plan_id']
    if plan.get('schema') != SCHEMA or digest({k: v for k, v in plan.items() if k != 'plan_id'}) != plan_id:
        raise ValueError('Saved plan integrity check failed')
    inventories = {engine: bank_inventory(engine, path) for engine, path in banks.items()}
    rows, inventory = [], []
    for label in labels['objects']:
        aliases = {identity(n) for n in [label['object_id'], *label['aliases']]}
        sources = [s for s in plan['spectra'] if identity(s['object_id']) in aliases]
        chosen = select_spectrum(sources)
        inventory.append({'object_id': label['object_id'], 'selected': chosen,
                          'available_spectra': [{'spectrum_id': s['spectrum_id'],
                            'blocked_reason': s.get('blocked_reason'), 'mjd': s.get('mjd'),
                            'duplicate_of': s.get('duplicate_of'), 'frame_assumed': s.get('frame_assumed')}
                            for s in sources]})
        for engine in sorted(banks):
            bank = inventories[engine]
            overlap_names = [n for n in bank['names'] if identity(n) in aliases]
            # Define the cohort from the verified plan, independently of fit
            # success or input eligibility. Failures must not shrink this cohort.
            intended_bank = plan.get('provenance', {}).get(engine, {}).get('bank_sha256')
            overlap = ('overlap' if overlap_names else 'no_known_alias_overlap') if intended_bank == bank['sha256'] else 'unverified'
            for mode in ('free', 'fixed'):
                row = {'object_id': label['object_id'], 'truth': label['class_label'],
                       'engine': engine, 'mode': mode, 'prediction': None,
                       'outcome': 'unsupported_input' if sources else 'missing_input',
                       'overlap': overlap, 'overlap_names': overlap_names}
                if chosen:
                    runs = [r for r in plan['runs'] if r['spectrum_id'] == chosen['spectrum_id']
                            and r['engine'] == engine and r['mode'] == mode]
                    if len(runs) > 1:
                        raise ValueError('Ambiguous duplicate engine/mode runs')
                    row['spectrum_id'] = chosen['spectrum_id']
                    row['outcome'] = 'not_planned'
                    if runs:
                        run = runs[0]
                        row['execution_id'] = run['execution_id']
                        pointer = saved_output / 'attempts' / run['execution_id'] / 'current.json'
                        record = None
                        if not run['blocked_reason']:
                            try:
                                trial = (pointer.parent / read_json(pointer)['trial']).resolve()
                                if trial.parent == pointer.parent.resolve():
                                    record = verify_attempt(trial, run['execution_id'])
                            except (OSError, ValueError, KeyError, TypeError):
                                pass
                        row['outcome'] = ('blocked' if run['blocked_reason'] else record['status']
                                          if record else 'invalid_evidence' if pointer.exists() else 'pending')
                        if record:
                            row['reason'] = record.get('reason')
                            row['elapsed_seconds'] = record.get('elapsed_seconds')
                            row['record_sha256'] = file_hash(trial / 'record.json')
                            row['record_path'] = str(trial / 'record.json')
                            if bank['sha256'] != record['provenance'].get('bank_sha256'):
                                row['overlap'] = 'unverified'
                            matches = sorted(record['candidates'], key=lambda m: m['rank'])
                            qualified = [m for m in matches if m.get('qualified')]
                            row['native_top_three'] = qualified[:3]
                            if record['status'] == 'completed' and qualified:
                                row['prediction'] = qualified[0].get('class_label') or None
                                row['outcome'] = 'predicted' if row['prediction'] else 'unsupported_taxonomy'
                            elif record['status'] == 'completed':
                                row['outcome'] = 'no_qualified_match'
                row['native_prediction'] = row['prediction']
                row['native_outcome'] = row['outcome']
                if row['outcome'] == 'unsupported_taxonomy' and row.get('native_top_three'):
                    best = row['native_top_three'][0]
                    # Explicit native subtype, not a type inferred from template name.
                    if best.get('native_class') == 'SLSN' and best.get('native_subtype') in {'SLSN-I', 'SLSN-II'}:
                        row['native_prediction'] = best['native_subtype']
                        row['native_outcome'] = 'predicted'
                rows.append(row)
    if file_hash(plan_path) != plan_sha256:
        raise ValueError('Saved plan changed during evaluation')
    return {'schema': 'spectypus-evaluation/1', 'plan_id': plan_id,
            'evaluator_sha256': file_hash(Path(__file__)), 'plan_sha256': plan_sha256,
            'labels_sha256': digest(labels), 'labels': labels, 'banks': inventories,
            'selection': 'earliest finite-MJD supported nonduplicate nonprovisional spectrum; independent of fit status',
            'prediction': 'first qualified native rank; engines and fixed/free modes separate',
            'limitations': ['No probability calibration', 'Alias matching does not prove absence of undocumented aliases',
                            'Selected pilot is not a representative multiclass accuracy sample',
                            'Fixed-z uses supplied redshift and is not blind classification'],
            'native_taxonomy_policy': 'Explicit SLSN-I/II subtype under native SLSN retained separately from saved normalized label; no fit or label is rewritten',
            'inventory': inventory, 'rows': rows, 'metrics': summarize_rows(rows),
            'native_metrics': summarize_rows(rows, prediction_key='native_prediction', outcome_key='native_outcome')}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--saved-output', type=Path, required=True)
    parser.add_argument('--labels', type=Path, required=True)
    parser.add_argument('--banks', type=Path, required=True, help='JSON engine-to-bank-path mapping')
    parser.add_argument('--output', type=Path, required=True, help='new audit directory')
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error('output must be a new directory; preserve previous evaluation evidence')
    result = evaluate_saved(args.saved_output, read_json(args.labels), read_json(args.banks))
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / 'evaluation.json', result)
    print(args.output / 'evaluation.json')


if __name__ == '__main__':
    main()

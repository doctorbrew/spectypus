#!/usr/bin/env python3
"""Refresh rank tables in place; archive old pages and preserve every plot/request.

Run in spectypus. Reads native banks only to verify optional local file links.
No classifier, template reconstruction, preprocessing or rendering is invoked.
"""
import argparse
from contextlib import ExitStack
import gzip
import json
from pathlib import Path
import re
import sys
import tarfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from spectypus.io import read_json, write_json, file_hash, tree_hash
from spectypus.phases import number
from build_spectral_browser import publish


def sage_group(container, name, epoch):
    """Resolve SAGE's expanded epoch position using native HDF5 key order."""
    group = f'/templates/{name}'
    if epoch is not None:
        keys = list(container[group + '/epochs'].keys())
        group += '/epochs/' + keys[int(epoch)]
    return group


def locations_for_browser(root, frozen, checks):
    import h5py
    locations, files, banks, indexes, sources = {}, {}, {}, {}, {}
    def verified_file(path, expected=None):
        path = path.resolve()
        if str(path) not in files:
            files[str(path)] = file_hash(path)
        if expected and files[str(path)] != expected:
            raise ValueError(f'Template file changed: {path}')
        return str(path)
    with ExitStack() as stack:
        containers = {}
        for snapshot in frozen['snapshots']:
            for run in snapshot['runs']:
                if not run['matches']: continue
                entries = {}; locations[run['plot_key']] = entries
                if run['engine'] == 'ngsf':
                    path = root / 'data' / (run['plot_key'] + '.json.gz')
                    if file_hash(path) != checks[str(path.relative_to(root))]:
                        raise ValueError('Changed numerical request')
                    request = json.loads(gzip.decompress(path.read_bytes()))
                    bank = Path(snapshot['config']['engines']['ngsf']['root']).resolve() / 'bank'
                    for match in request['matches']:
                        info = match['curve'].get('display_model_provenance')
                        if not info: raise ValueError('NGSF template has no verified file provenance')
                        path = Path(info['sn_template']).resolve()
                        if not path.is_relative_to(bank): raise ValueError('Template escaped its bank')
                        path = verified_file(path, info['sn_template_sha256'])
                        entries[str(match['candidate']['rank'])] = {'path': path, 'template': match['candidate']['template']}
                else:
                    record_path = Path(run['attempt_path']) / 'record.json'
                    if file_hash(record_path) != run['record_sha256']: raise ValueError('Saved record changed')
                    record = read_json(record_path)
                    source = Path(record['provenance']['runtime']['sage_source']).parent
                    if str(source) not in sources:
                        sources[str(source)] = tree_hash(source, suffixes={'.py', '.json', '.yaml', '.yml'})
                    if sources[str(source)] != record['provenance']['source_sha256']:
                        raise ValueError('SNID source changed before resolving native epoch order')
                    bank = Path(record['provenance']['templates']).resolve()
                    if str(bank) not in banks:
                        banks[str(bank)] = tree_hash(bank)
                        indexes[str(bank)] = read_json(bank / 'template_index.json')['templates']
                    if banks[str(bank)] != record['provenance']['bank_sha256']:
                        raise ValueError('SNID bank no longer matches saved fit')
                    for m in run['matches']:
                        match = re.fullmatch(r'(.+)_epoch_(\d+)', m['template'])
                        name, epoch = match.groups() if match else (m['template'], None)
                        metadata = indexes[str(bank)][name]
                        path = (bank / metadata['storage_file']).resolve()
                        if not path.is_relative_to(bank): raise ValueError('Template escaped its bank')
                        path = verified_file(path)
                        if path not in containers: containers[path] = stack.enter_context(h5py.File(path, 'r'))
                        group = sage_group(containers[path], name, epoch)
                        data = containers[path][group]
                        phase = number(m.get('phase_days'))
                        if phase is not None and abs(float(data.attrs['age']) - phase) > 1e-5:
                            raise ValueError(f'SNID epoch age disagrees with saved candidate: {m["template"]}, {group}')
                        entries[str(m['rank'])] = {'path': path, 'group': group, 'template': m['template']}
    return {'schema': 'spectypus-local-template-locations/1', 'scope': 'Optional original local bank files; not bundled atlas assets',
            'locations': locations, 'files': files, 'verified_snid_banks': banks, 'verified_snid_sources': sources}


def refresh(root, audit):
    root, audit = root.resolve(), audit.resolve()
    audit.mkdir(parents=True, exist_ok=False)
    checks = read_json(root / 'checksums.json')
    for name in ('browser-snapshot.json', 'figure-results.json', 'manifest.json', 'render-contract.json'):
        if file_hash(root / name) != checks[name]: raise ValueError(f'Changed export metadata: {name}')
    frozen = read_json(root / 'browser-snapshot.json')
    catalog = locations_for_browser(root, frozen, checks)
    write_json(audit / 'template-locations.json', catalog)
    # Retain only superseded pages/metadata, never another full export copy.
    with tarfile.open(audit / 'previous-pages-and-metadata.tar.gz', 'w:gz') as archive:
        for name in [*sorted(n for n in checks if n.endswith('.html')), 'manifest.json', 'checksums.json']:
            if name in checks and file_hash(root / name) != checks[name]: raise ValueError('Changed source page')
            archive.add(root / name, arcname=name)
    write_json(root / 'template-locations.json', catalog)
    publish(frozen, root, read_json(root / 'figure-results.json'))
    after = read_json(root / 'checksums.json')
    protected = {name: sha for name, sha in checks.items() if not name.endswith('.html') and name not in ('manifest.json', 'template-locations.json')}
    if any(after[name] != sha for name, sha in protected.items()): raise ValueError('A protected plot/evidence product changed')
    report = {'status': 'passed', 'unchanged_products': len(protected), 'linked_candidates': sum(len(v) for v in catalog['locations'].values()),
              'unique_template_files': len(catalog['files']), 'plots_rendered': 0, 'classifier_runs': 0,
              'source_export': str(root), 'previous_checksums': 'previous-pages-and-metadata.tar.gz'}
    write_json(audit / 'refresh.json', report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path); parser.add_argument('--audit-directory', type=Path, required=True)
    args = parser.parse_args(); refresh(args.directory, args.audit_directory)

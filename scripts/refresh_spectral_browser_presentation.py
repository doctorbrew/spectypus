#!/usr/bin/env python3
"""Refresh HTML only, archiving prior pages and verifying unchanged products."""
import argparse
from pathlib import Path
import tarfile

from build_spectral_browser import publish
from spectypus.io import file_hash, read_json, write_json


def refresh(root, audit):
    root, audit = root.resolve(), audit.resolve()
    if audit.is_relative_to(root):
        raise ValueError('Keep the audit outside the browser')
    audit.mkdir(parents=True, exist_ok=False)
    before = read_json(root / 'checksums.json')
    for name, expected in before.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or file_hash(path) != expected:
            raise ValueError(f'Changed source product: {name}')
    mutable = [n for n in before if n.endswith('.html') or n in ('manifest.json', 'classification_summary.csv', 'best_matches.csv', 'native_matches.csv')]
    with tarfile.open(audit / 'previous-pages-and-metadata.tar.gz', 'w:gz') as archive:
        for name in [*mutable, 'checksums.json']:
            archive.add(root / name, arcname=name)
    publish(read_json(root / 'browser-snapshot.json'), root, read_json(root / 'figure-results.json'))
    after = read_json(root / 'checksums.json')
    protected = {n: sha for n, sha in before.items() if n not in mutable}
    if any(after.get(n) != sha for n, sha in protected.items()):
        raise ValueError('A protected scientific or plot product changed')
    result = {'protected_products': len(protected), 'unchanged': True,
              'html_pages': sum(n.endswith('.html') for n in after),
              'plot_renders': 0, 'classifier_runs': 0, 'preprocessing_replays': 0}
    write_json(audit / 'refresh.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--audit', type=Path, required=True)
    args = parser.parse_args()
    print(refresh(args.directory, args.audit))

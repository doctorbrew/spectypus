"""Optional original template links; never trust names without saved provenance."""
import gzip
import json
import re
from pathlib import Path
from ..io import file_hash, read_json, tree_hash
from ..phases import number


class TemplateLocations:
    """Per-export hashes avoid rescanning a bank for every spectrum."""
    def __init__(self):
        self.hashes = {}

    def verify(self, path, expected, *, source=False):
        key = (str(path), source)
        if key not in self.hashes:
            self.hashes[key] = (tree_hash(path, suffixes={'.py', '.json', '.yaml', '.yml'})
                                if source else tree_hash(path) if path.is_dir() else file_hash(path))
        if not expected or self.hashes[key] != expected:
            raise ValueError(f'Local template provenance differs: {path}')

    def resolve(self, run, record, figure):
        try:
            entries = {}
            if run['engine'] == 'ngsf':
                if figure.get('status') != 'ready':
                    raise ValueError('Verified numerical plot request unavailable')
                request_path = Path(figure['directory']) / 'request.json.gz'
                self.verify(request_path, figure['request_sha256'])
                request = json.loads(gzip.decompress(request_path.read_bytes()))
                bank = (Path(record['config']['engines']['ngsf']['root']) / 'bank').resolve()
                candidates = {m['rank']: m for m in run['matches'][:6]}
                for match in request['matches']:
                    candidate = match['candidate']
                    if candidate['rank'] not in candidates:
                        continue
                    if candidate != candidates[candidate['rank']]:
                        raise ValueError('Template candidate disagrees with saved record')
                    info = match['curve']['display_model_provenance']
                    path = Path(info['sn_template']).resolve()
                    if not path.is_relative_to(bank):
                        raise ValueError('Template escaped its bank')
                    self.verify(path, info['sn_template_sha256'])
                    entries[str(candidate['rank'])] = {'path': str(path), 'template': candidate['template']}
            else:
                import h5py
                provenance = record['provenance']
                source = Path(provenance['runtime']['sage_source']).parent
                self.verify(source, provenance['source_sha256'], source=True)
                bank = Path(provenance['templates']).resolve()
                self.verify(bank, provenance['bank_sha256'])
                index = read_json(bank / 'template_index.json')['templates']
                for candidate in run['matches'][:6]:
                    match = re.fullmatch(r'(.+)_epoch_(\d+)', candidate['template'])
                    name, epoch = match.groups() if match else (candidate['template'], None)
                    path = (bank / index[name]['storage_file']).resolve()
                    if not path.is_relative_to(bank):
                        raise ValueError('Template escaped its bank')
                    with h5py.File(path, 'r') as container:
                        group = f'/templates/{name}'
                        if epoch is not None:
                            keys = list(container[group + '/epochs'].keys())
                            group += '/epochs/' + keys[int(epoch)]
                        phase = number(candidate.get('phase_days'))
                        age = number(container[group].attrs.get('age'))
                        if phase is not None and (age is None or abs(age - phase) > 1e-5):
                            raise ValueError('Template phase disagrees with saved candidate')
                    entries[str(candidate['rank'])] = {'path': str(path), 'group': group, 'template': candidate['template']}
            return entries, None
        except (OSError, ValueError, KeyError, TypeError, IndexError, ImportError) as exc:
            return {}, f'Optional local template links unavailable: {exc}'

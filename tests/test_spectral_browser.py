"""SN navigation and six-candidate evidence contracts, without real engines."""
from pathlib import Path
import sys

import pytest
from spectypus.io import read_json, write_json, file_hash
from spectypus.pipeline import run_batch

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from build_spectral_atlas import capture
from build_spectral_browser import prepare, saved_matches, saved_input, write_browser, target_phases
from spectypus.phases import phase_context


def test_six_native_ranks_keep_galaxy_identity_and_missing_curves():
    candidates = [{'rank': i, 'template': f'SN-template-{i}', 'score': i / 10, 'native': {'GALAXY': 'E'}, 'qualified': i < 4} for i in range(1, 8)]
    curves = [{'template': c['template'], 'score': c['score'], 'galaxy': 'E', 'available': True, 'observed': [[3000, 1], [9000, 2]], 'model': [[3000, 1], [9000, 2]]} for c in candidates]
    curves[1]['galaxy'] = 'S'; curves[2]['score'] = 10
    matches = saved_matches({'engine': 'ngsf', 'matches': candidates}, {'curves': curves}, {'redshift': .1}, {})
    assert [m['candidate']['rank'] for m in matches] == [1, 2, 3, 4, 5, 6]
    assert [m['candidate']['rank'] for m in matches if m['curve']['available']] == [1, 4, 5, 6]
    assert not matches[4]['candidate']['qualified']
    assert matches[0]['curve']['features']['host_redshift'] == .1


def test_sidebar_groups_same_sn_but_keeps_campaign_evidence(tmp_path, source_factory, manifest_factory, config_factory, fake_engine):
    run = tmp_path / 'run'
    source = source_factory(z='.1'); source['mjd'] = '59010'
    run_batch(manifest_factory([source]), config_factory(), run)
    previous = tmp_path / 'old'
    checksums = {}
    for i in (1, 2):
        dest = previous / f'campaign-{i}'
        snapshot = capture(run, dest, f'campaign {i}')
        snapshot['phase_references'] = {'SN-A': [{'kind': 'maximum', 'band': 'r', 'mjd': 59000., 'source': 'catalog.csv', 'field': 'peak_mjd'}]}
        write_json(dest / 'snapshot.json', snapshot)
        checksums[f'campaign-{i}/snapshot.json'] = file_hash(dest / 'snapshot.json')
    write_json(previous / 'checksums.json', checksums)
    root = tmp_path / 'browser'
    frozen = prepare(previous, root)
    objects = write_browser(frozen, root, {})
    assert len(objects) == 1 and objects[0]['campaigns'] == [1, 2]
    html = (root / 'index.html').read_text()
    assert html.count('data-sn=') == 1
    assert 'campaign 1' in html and 'campaign 2' in html
    assert 'MJD 59010' in html and '+9.1 d (rest)' in html
    assert html.count('class="epoch"') == 2
    assert 'Saved model curves unavailable' in html
    assert 'Scientific fieldnotes' not in html and 'Fieldnotes' not in html
    assert 'id="epoch-jump"' in html and 'aria-current="page"' in html
    # A corrupt frozen export cannot be used as authoritative evidence.
    (previous / 'campaign-1/snapshot.json').write_text('{}')
    with pytest.raises(ValueError, match='integrity'):
        prepare(previous, tmp_path / 'corrupt')


def test_changed_saved_curves_fail_closed(tmp_path, source_factory, manifest_factory, config_factory, fake_engine):
    run = tmp_path / 'run'
    run_batch(manifest_factory([source_factory(z='.1')]), config_factory(), run)
    previous = tmp_path / 'old'; dest = previous / 'campaign-1'
    snapshot = capture(run, dest, 'test')
    fit = next(r for r in snapshot['runs'] if r['matches'])
    curve = Path(fit['attempt_path']) / 'fit_curves.json'; curve.write_text('{}')
    fit['artifacts']['fit_curves.json'] = file_hash(curve)
    write_json(dest / 'snapshot.json', snapshot)
    write_json(previous / 'checksums.json', {'campaign-1/snapshot.json': file_hash(dest / 'snapshot.json')})
    curve.write_text('{"curves":[]}')
    with pytest.raises(ValueError, match='curves changed'):
        prepare(previous, tmp_path / 'browser')


def test_supplied_zero_phase_is_not_missing_or_silently_replaced():
    source = {'phase_rest_days': '0', 'mjd': '59010', 'redshift': .1}
    refs = [{'kind': 'maximum', 'band': 'r', 'mjd': 59000., 'source': 'catalog.csv', 'field': 'peak_mjd'}]
    lines = target_phases(source, phase_context(source, refs))
    assert '+0.0 d (rest' in lines[0] and 'reference unspecified' in lines[0]
    assert 'Catalogue phase:' in lines[1] and '+9.1 d (rest)' in lines[1]
    assert len(target_phases(source, phase_context(source))) == 1
    assert 'unknown' in target_phases({}, phase_context({}))[0]


def test_full_input_keeps_exact_pre_mask_bytes_and_rejects_changes(tmp_path):
    original = b'6800 1\n6900 0.3\n7000 0\n7100 1\n'
    source = tmp_path / 'spectrum.txt'; source.write_bytes(original)
    run = {'attempt_path': str(tmp_path), 'artifacts': {'spectrum.txt': file_hash(source)}}
    saved = saved_input(run)
    assert saved['contents'].encode() == original
    assert saved['wavelength_frame'] == 'observer' and saved['wavelength_unit'] == 'angstrom'
    source.write_bytes(original.replace(b'0.3', b'0.9'))
    with pytest.raises(ValueError, match='input spectrum changed'):
        saved_input(run)
    assert not saved_input({'artifacts': {}})['available']


def test_plot_preserves_telluric_samples_and_native_missing_values():
    import copy
    import numpy as np
    from spectral_atlas_top5_figures import plot_saved_curves
    class Axes:
        def __init__(self): self.lines = []
        def plot(self, x, y, **kwargs): self.lines.append((x.copy(), y.copy()))
    curve = {'observed': [[6800, 1], [6900, .3], [7000, 0], [7100, 1]],
             'model': [[6800, 1], [6900, None], [7000, .7], [7100, 1]],
             'features': {'telluric_windows': [[6850, 7050]]}}
    before = copy.deepcopy(curve); ax = Axes()
    plot_saved_curves(ax, curve)
    np.testing.assert_array_equal(ax.lines[0][1], [1, .3, 0, 1])
    np.testing.assert_array_equal(ax.lines[1][1], [1, .3, 0, 1])
    np.testing.assert_array_equal(ax.lines[2][1], [1, np.nan, .7, 1])
    assert curve == before


def test_named_legends_preserve_zero_unknown_and_conflicting_phases():
    from spectral_atlas_top5_figures import legend_labels
    candidate = {'template': 'Ic/1998bw/spectrum_epoch_1', 'phase_days': -2.5, 'native_class': 'Ic', 'native_subtype': ''}
    request = {'source': {'object_id': 'SN2018avk', 'phase_rest_days': 0}}
    assert legend_labels(request, candidate) == ('SN2018avk (+0.0 d rest)', 'SN1998bw — Ic (-2.5 d)')
    request['source'].pop('phase_rest_days')
    assert 'phase unknown' in legend_labels(request, candidate)[0]
    request['phase_context'] = {'references': [{'kind': 'maximum', 'rest_days': -3.}, {'kind': 'maximum', 'rest_days': -5.}]}
    assert 'phase ambiguous' in legend_labels(request, candidate)[0]
    request['phase_context']['references'] = [{'kind': 'discovery', 'rest_days': 6.}]
    assert 'phase unknown' in legend_labels(request, candidate)[0]
    candidate['template'] = 'Ia 02es-like/iPTF14atg/ALFOSC phase-band : -2.5B'
    assert legend_labels(request, candidate)[1] == 'iPTF14atg — Ic (-2.5 d)'
    candidate['template'] = 'LSQ14mo_epoch_2'
    assert legend_labels(request, candidate)[1] == 'LSQ14mo — Ic (-2.5 d)'


def test_ten_angstrom_sg_includes_tellurics_and_preserves_raw_layer():
    import numpy as np
    from scipy.signal import savgol_filter
    from spectral_atlas_top5_figures import smooth_observed, plot_saved_curves, smoothed_limits
    x = np.arange(6850., 6901.)
    y = 2 + .2 * np.sin(x) - np.exp(-((x - 6875) / 3) ** 2)
    points = np.column_stack((x, y))
    smooth, info = smooth_observed(points)
    np.testing.assert_allclose(smooth[:, 1], savgol_filter(y, 11, 2, mode='interp'))
    assert info['telluric_samples_included'] and info['savgol_filtered_samples'] == len(x)
    limits, _ = smoothed_limits(smooth)
    assert limits == pytest.approx([smooth[:, 1].min() / 1.1, smooth[:, 1].max() * 1.1])
    class Axes:
        def __init__(self): self.lines = []
        def plot(self, x, y, **kwargs): self.lines.append((x.copy(), y.copy(), kwargs))
    ax = Axes()
    plot_saved_curves(ax, {'observed': points, 'model': points, 'features': {'telluric_windows': [[6850, 6900]]}})
    np.testing.assert_array_equal(ax.lines[0][1], y)
    np.testing.assert_allclose(ax.lines[1][1], smooth[:, 1])
    assert ax.lines[0][2]['alpha'] == .2 and ax.lines[0][2]['color'] == '0.5'
    assert ax.lines[0][2]['zorder'] < ax.lines[1][2]['zorder']


def test_smoothing_does_not_bridge_missing_samples_or_large_gaps():
    import numpy as np
    from spectral_atlas_top5_figures import smooth_observed, smoothed_limits
    x = np.r_[np.arange(20.), np.arange(100., 120.)]
    y = np.r_[np.ones(20), np.full(20, 100.)]
    y[10] = np.nan
    smooth, info = smooth_observed(np.column_stack((x, y)))
    np.testing.assert_allclose(smooth[:, 1], y, equal_nan=True)
    assert info['native_missing_samples'] == 1
    for flux in ([-2., -1.], [-2., 3.], [0., 0.], [2., 2.]):
        limits, _ = smoothed_limits(np.column_stack(([1., 2.], flux)))
        assert limits[0] <= min(flux) and limits[1] >= max(flux)
        assert limits[0] < limits[1]
    coarse = np.array([[6800., 1.], [6900., .3], [7000., 0.]])
    smooth, info = smooth_observed(coarse)
    np.testing.assert_array_equal(smooth, coarse)
    assert info['coarse_or_short_samples_retained'] == 3


def test_match_grid_plots_full_input_including_fitter_masked_regions():
    pytest.importorskip("scienceplots")
    pytest.importorskip("pypalettes")
    import hashlib
    import numpy as np
    from spectral_atlas_top5_figures import create_figure
    import matplotlib.pyplot as plt
    raw = np.column_stack((np.arange(6800., 7201., 2.), np.full(201, 2.)))
    raw[(raw[:, 0] >= 6900) & (raw[:, 0] <= 7000), 1] = .4
    contents = ''.join(f'{x} {y}\n' for x, y in raw)
    curve = {'available': True, 'observed': [[6850, 1], [6950, None], [7100, 1]],
             'model': [[6850, 1], [6950, None], [7100, 1]],
             'display_model': [[6850, 1], [6950, 1], [7100, 1]],
             'features': {'telluric_windows': [[6900, 7000]], 'host_lines': []}}
    request = {'source': {'object_id': 'SN-test'}, 'engine': 'ngsf', 'mode': 'fixed',
               'input_spectrum': {'available': True, 'contents': contents, 'sha256': hashlib.sha256(contents.encode()).hexdigest()},
               'display_transform': {'kind': 'ngsf-scale', 'input_sha256': hashlib.sha256(contents.encode()).hexdigest(), 'scale': 2.},
               'matches': [{'candidate': {'rank': i, 'template': 'SN1998bw', 'phase_days': 0}, 'curve': curve} for i in range(1, 7)]}
    fig, diagnostics = create_figure(request)
    try:
        for ax in fig.axes:
            np.testing.assert_array_equal(ax.lines[0].get_xdata(), raw[:, 0])
            np.testing.assert_array_equal(ax.lines[0].get_ydata(), raw[:, 1])
            assert ax.get_xlim() == pytest.approx((6800, 7200))
            assert ax.lines[0].get_alpha() == .2
            assert ax.get_ylim()[0] <= .4 and ax.get_ylim()[1] >= 2.
            np.testing.assert_allclose(ax.lines[2].get_ydata(), [2., 2., 2.])
        assert all(p['observed_source'] == 'full-staged-input' for p in diagnostics)
    finally:
        plt.close(fig)
    request['display_transform']['scale'] = 100.
    fig, diagnostics = create_figure(request)
    try:
        assert all(p['model_entirely_outside_limits'] for p in diagnostics)
        assert all(any(t.get_text() == 'Saved model outside y-range' for t in ax.texts) for ax in fig.axes)
    finally:
        plt.close(fig)
    curve.pop('display_model')
    with pytest.raises(ValueError, match='internal missing'):
        create_figure(request)
    curve['model'] = [[6850, None], [6950, None], [7100, None]]
    with pytest.raises(ValueError, match='no finite'):
        create_figure(request)


def test_full_observed_replays_native_cli_flags_after_bridge_separator():
    from spectral_atlas_full_observed import sage_options
    opts = sage_options(['python', 'bridge.py', '--candidate-json', 'out', '--', 'identify', 'input', 'bank', '--profile', 'optical', '--forced-redshift', '.1', '--wavelength-masks', '6850:7000', '7500:7800'])
    assert opts['wavelength_masks'] == [[6850., 7000.], [7500., 7800.]]
    assert opts['spike_masking'] and opts['emclip_z'] == -1.
    assert 'forced_redshift' not in opts


def test_sage_model_flux_restoration_keeps_observed_data_separate():
    import numpy as np
    from spectral_atlas_full_observed import model_input_flux
    model = [[6800, -.5], [6900, 0], [7000, .5]]
    result = model_input_flux({'model': model}, {'kind': 'snid-continuum-restored', 'continuum': [[6800, 2], [7000, 4]], 'flux_offset': .1, 'fit_windows': [[6850, 6950]]})
    np.testing.assert_allclose(result[:,1], [.9, 2.9, 5.9])
    assert model == [[6800, -.5], [6900, 0], [7000, .5]]


@pytest.mark.parametrize('renderer', ['six_matches', 'portable'])
def test_renderers_write_only_300_dpi_jpg(tmp_path, renderer):
    pytest.importorskip("scienceplots")
    pytest.importorskip("pypalettes")
    import gzip
    from spectral_atlas_products import product_ready
    from spectral_atlas_top5_figures import render_matches
    from spectral_atlas_figures import render_spectrum
    curve = {'available': True, 'execution_id': 'fit', 'engine': 'ngsf', 'mode': 'fixed',
             'observed': [[4000, 1], [5000, 2], [6000, 1]],
             'model': [[4000, 1], [5000, 1.8], [6000, 1]],
             'features': {'telluric_windows': [], 'host_lines': []}}
    source = tmp_path / 'spectrum.txt'; source.write_text('4000 1\n5000 2\n6000 1\n')
    request = {'source': {'object_id': 'SN-test'}, 'engine': 'ngsf', 'mode': 'fixed',
               'curves': [curve], 'input_spectrum': saved_input({'attempt_path': str(tmp_path), 'artifacts': {'spectrum.txt': file_hash(source)}}),
               'display_transform': {'kind': 'ngsf-scale', 'input_sha256': file_hash(source), 'scale': 1.},
               'matches': [{'candidate': {'rank': 1, 'template': 'SN1998bw', 'phase_days': 0}, 'curve': curve}]}
    path = tmp_path / 'request.json'
    write_json(path, request)
    if renderer == 'six_matches':
        path.write_bytes(gzip.compress(path.read_bytes()))
        result = render_matches((path, tmp_path / 'figure'))
    else:
        result = render_spectrum((path, tmp_path / 'figure'))
    assert 'pdf' not in result and list(tmp_path.glob('*.pdf')) == []
    result['product_hashes'] = {'jpg': file_hash(tmp_path / result['jpg'])}
    assert product_ready(tmp_path, result)
    (tmp_path / result['jpg']).write_bytes(b'corrupt')
    assert not product_ready(tmp_path, result)


def test_resume_rejects_wrong_dpi_and_legacy_product_contract(tmp_path):
    from PIL import Image
    from spectral_atlas_products import product_ready
    path = tmp_path / 'image.jpg'
    result = {'status': 'ready', 'jpg': path.name}
    for dpi, expected in ((72, False), (300, True)):
        Image.new('RGB', (20, 20)).save(path, dpi=(dpi, dpi))
        result['product_hashes'] = {'jpg': file_hash(path)}
        assert product_ready(tmp_path, result) is expected
    result['pdf'] = 'image.pdf'
    assert not product_ready(tmp_path, result)


def test_jpg_only_build_and_resume_without_rendering(tmp_path, source_factory, manifest_factory, config_factory, fake_engine, monkeypatch):
    from argparse import Namespace
    import build_spectral_browser as browser
    from validate_spectral_browser import validate
    run = tmp_path / 'run'
    run_batch(manifest_factory([source_factory(z='.1')]), config_factory(), run)
    previous = tmp_path / 'old'
    capture(run, previous / 'campaign-1', 'test')
    write_json(previous / 'checksums.json', {'campaign-1/snapshot.json': file_hash(previous / 'campaign-1/snapshot.json')})
    root = tmp_path / 'browser'
    args = Namespace(output=root, from_export=previous, resume=False, workers=1)
    browser.build(args)
    assert validate(root)['jpg_only_300_dpi'] == 'passed'
    assert read_json(root / 'manifest.json')['plot_output'] == {'formats': ['jpg'], 'dpi': 300}
    def forbidden(*args, **kwargs): raise AssertionError('Resume must reuse frozen requests')
    monkeypatch.setattr(browser, 'prepare', forbidden)
    args.resume = True
    browser.build(args)
    assert validate(root)['jpg_only_300_dpi'] == 'passed'
    html = (root / 'summary.html').read_text()
    (root / 'summary.html').write_text(html + '<a href="old.pdf">PDF</a>')
    checks = read_json(root / 'checksums.json'); checks['summary.html'] = file_hash(root / 'summary.html')
    write_json(root / 'checksums.json', checks)
    with pytest.raises(AssertionError, match='PDF link'):
        validate(root)


def test_migration_preserves_jpg_and_requests_and_fails_closed(tmp_path, monkeypatch):
    from PIL import Image
    import migrate_spectral_browser_jpg as migration
    root = tmp_path / 'export'; (root / 'figures').mkdir(parents=True); (root / 'data').mkdir()
    jpg = root / 'figures/fit.jpg'; Image.new('RGB', (20, 20)).save(jpg, dpi=(300, 300))
    pdf = root / 'figures/fit.pdf'; pdf.write_bytes(b'old derived PDF fixture')
    request = root / 'data/fit.json.gz'; request.write_bytes(b'frozen numerical request fixture')
    write_json(root / 'browser-snapshot.json', {'jobs': [(str(request), str(root / 'figures/fit'))]})
    result = {'status': 'ready', 'jpg': jpg.name, 'pdf': pdf.name, 'panels': [{'rank': 1}],
              'product_hashes': {'jpg': file_hash(jpg), 'pdf': file_hash(pdf)}}
    write_json(root / 'figure-results.json', {'fit': result})
    contract = migration.render_contract(root, read_json(root / 'browser-snapshot.json')['jobs'])
    monkeypatch.setattr(migration, 'JPG_RENDERER', contract['renderer'])
    contract.pop('plot_output'); contract.pop('products'); contract['renderer'] = migration.LEGACY_RENDERER
    write_json(root / 'render-contract.json', contract)
    write_json(root / 'manifest.json', {'render_contract_sha256': file_hash(root / 'render-contract.json')})
    def checksum():
        write_json(root / 'checksums.json', {str(p.relative_to(root)): file_hash(p) for p in root.rglob('*') if p.is_file() and p.name != 'checksums.json'})
    checksum()
    before = {p.name: file_hash(p) for p in (jpg, request, root / 'browser-snapshot.json')}
    request.write_bytes(b'changed')
    with pytest.raises(ValueError, match='Changed'):
        migration.migrate(root, tmp_path / 'rejected')
    assert not (tmp_path / 'rejected').exists() and pdf.exists()
    checksum()  # Rehashing the export cannot bypass the frozen request contract.
    with pytest.raises(ValueError, match='unchanged requests'):
        migration.preflight(root)
    request.write_bytes(b'frozen numerical request fixture'); checksum()
    def publish(frozen, output, results):
        assert output == root and 'pdf' not in results['fit']
        checksum()
    monkeypatch.setattr(migration, 'publish', publish)
    migration.migrate(root, tmp_path / 'audit')
    assert not pdf.exists()
    assert before == {p.name: file_hash(p) for p in (jpg, request, root / 'browser-snapshot.json')}
    assert (tmp_path / 'audit/previous-presentation.tar.gz').is_file()
    assert read_json(root / 'jpg-migration.json')['rerendered_figures'] == 0
    assert read_json(root / 'figure-results.json')['fit']['panels'] == result['panels']


def test_robust_axis_limits_do_not_flatten_broad_spectrum_for_edge_noise():
    import numpy as np
    from spectral_atlas_limits import robust_limits
    x = np.arange(3500., 10001., 2.)
    y = 1 + .7 * np.exp(-((x - 5000) / 400) ** 2)
    y[:40] += 8 * np.sin(np.arange(40) * 2.3)
    y[1500] = 100  # isolated excursion, retained in the supplied array
    original = y.copy()
    bounds, info = robust_limits(np.column_stack((x, y)))
    assert .5 < bounds[0] < 1 and 1.7 < bounds[1] < 2.5
    assert info['limit_raw_samples_outside'] > 0
    np.testing.assert_array_equal(original, y)
    for scale in (1e-18, 1e-16, 1e8):
        scaled, diag = robust_limits(np.column_stack((x, y * scale)))
        np.testing.assert_allclose(np.array(scaled) / scale, bounds)
        assert diag['limit_raw_samples_outside'] == info['limit_raw_samples_outside']


def test_robust_limits_preserve_broad_telluric_dip_gaps_and_constant_flux():
    import numpy as np
    from spectral_atlas_limits import robust_limits
    x = np.arange(6000., 8001., 2.); y = np.full(len(x), 2.)
    y[(x > 6850) & (x < 7000)] = .4
    y[(x > 7300) & (x < 7400)] = np.nan
    bounds, info = robust_limits(np.column_stack((x, y)))
    assert bounds[0] <= .4 and bounds[1] >= 2
    assert info['limit_telluric_samples_eligible']
    for flux in (2e-17, -2e-17, 0.):
        bounds, _ = robust_limits(np.column_stack((x, np.full(len(x), flux))))
        assert bounds[0] < flux < bounds[1]
        if flux: assert bounds[1] - bounds[0] < abs(flux)
    bounds, info = robust_limits([[4000, 1e-17], [5000, 3e-17], [6000, 2e-17]])
    assert info['limit_fallback'] == 'finite-native-samples'
    assert bounds[0] < 1e-17 and bounds[1] > 3e-17


def test_native_type_legends_preserve_subtype_and_unknown():
    from spectral_atlas_top5_figures import native_type_label
    assert native_type_label({'native_class': 'Ia', 'native_subtype': 'Ia-norm'}) == 'Ia / Ia-norm'
    assert native_type_label({'native_class': 'Ia-pec', 'class_label': 'Ia'}) == 'Ia-pec'
    assert native_type_label({'class_label': 'Ia'}) == 'type unknown'


def test_browser_revision_reuses_exact_requests_without_preprocessing(tmp_path, source_factory, manifest_factory, config_factory, fake_engine, monkeypatch):
    from build_spectral_browser import prepare_browser
    import spectral_atlas_full_observed
    run = tmp_path / 'run'
    run_batch(manifest_factory([source_factory(z='.1')]), config_factory(), run)
    previous = tmp_path / 'old'; dest = previous / 'campaign-1'
    capture(run, dest, 'test')
    write_json(previous / 'checksums.json', {'campaign-1/snapshot.json': file_hash(dest / 'snapshot.json')})
    browser = tmp_path / 'browser'; original = prepare(previous, browser)
    write_json(browser / 'checksums.json', {str(p.relative_to(browser)): file_hash(p) for p in browser.rglob('*') if p.is_file()})
    def forbidden(*args, **kwargs): raise AssertionError('No native preprocessing replay allowed')
    monkeypatch.setattr(spectral_atlas_full_observed, 'make_transform', forbidden)
    revised = tmp_path / 'revised'; frozen = prepare_browser(browser, revised)
    assert frozen['snapshots'] == original['snapshots']
    for p in (browser / 'data').glob('*.json.gz'):
        assert file_hash(p) == file_hash(revised / 'data' / p.name)
    assert frozen['presentation_source']['snapshot_sha256'] == file_hash(browser / 'browser-snapshot.json')
    (browser / 'browser-snapshot.json').write_text('{}')
    with pytest.raises(ValueError, match='integrity'):
        prepare_browser(browser, tmp_path / 'corrupt-revision')


def test_robust_limits_allow_ordinary_low_snr_scatter_without_using_edge_spikes():
    import numpy as np
    from spectral_atlas_limits import robust_limits
    rng = np.random.default_rng(823)
    x = np.arange(3500., 9500., 2.)
    y = 1e-17 + rng.normal(0, 3e-17, len(x))
    y[:15] *= 100
    bounds, info = robust_limits(np.column_stack((x, y)))
    ordinary = y[15:]
    assert np.mean((ordinary < bounds[0]) | (ordinary > bounds[1])) < .01
    assert info['limit_display_noise_scale'] > 2e-17
    assert max(abs(np.array(bounds))) < 2e-16


def test_unmasked_model_recovery_preserves_native_values_and_rejects_wrong_fit():
    import numpy as np
    from prepare_unmasked_spectral_browser import restore_missing_model
    saved = [[4000, 1.], [5000, None], [6000, 2.], [7000, None]]
    evaluated = [[4000, 1. + 1e-8], [5000, 1.5], [6000, 2. - 1e-8], [7000, np.nan]]
    points, info = restore_missing_model(saved, evaluated)
    assert points == [[4000, 1.], [5000, 1.5], [6000, 2.], [7000, None]]
    assert info['restored_samples'] == 1 and info['saved_finite_samples_unchanged'] == 2
    assert saved[1][1] is None
    evaluated[0][1] = 1.1
    with pytest.raises(ValueError, match='differs from saved'):
        restore_missing_model(saved, evaluated)
    with pytest.raises(ValueError, match='internal missing'):
        restore_missing_model(saved, saved)


def test_enrichment_never_writes_through_frozen_request_hardlink(tmp_path):
    import gzip,json,os
    from prepare_unmasked_spectral_browser import atomic_gzip
    source = tmp_path / 'original.json.gz'; source.write_bytes(gzip.compress(b'{"native":1}'))
    linked = tmp_path / 'revised.json.gz'; os.link(source, linked)
    before = source.read_bytes()
    atomic_gzip(linked, {'native': 1, 'display_model': [2]})
    assert source.read_bytes() == before
    assert json.loads(gzip.decompress(linked.read_bytes()))['display_model'] == [2]


def test_saved_curve_identity_requires_exact_native_float32_coefficients():
    import numpy as np
    from prepare_unmasked_spectral_browser import recover_curve_coefficients, native_grid_value
    x = np.linspace(4000, 8000, 100)
    components = np.column_stack([1 + np.sin(x / 1000), 1 + x / 5000])
    coefficients = np.array([.56329441, .37930244], dtype=np.float32).astype(float)
    saved = np.column_stack([x, components @ coefficients])
    saved[35:40, 1] = np.nan
    np.testing.assert_array_equal(recover_curve_coefficients(saved, components), coefficients)
    saved[10, 1] += .001
    assert recover_curve_coefficients(saved, components) is None
    assert recover_curve_coefficients(saved, np.ones_like(components)) is None
    grid = np.linspace(-4, 4, 41)
    assert native_grid_value('0.8', grid) == grid[24]
    with pytest.raises(ValueError, match='one native grid'):
        native_grid_value('.8', [.8, .800000001])


def test_compact_rank_table_precision_subtype_phase_and_galaxy(tmp_path):
    from build_spectral_browser import candidate_rows
    from spectral_atlas_rank_table import compact_identity, galaxy_cell, decimal_cell
    from validate_spectral_browser import BrowserHTML
    m = {'rank': 1, 'template': 'Ia-pec/2012dn/LRIS phase-band : 5.0B',
         'native_class': 'Ia-pec', 'native_subtype': '', 'phase_days': 5.,
         'redshift': .123456, 'score': .00012345, 'qualified': False,
         'native': {'A_v': '-0.2', 'GALAXY': 'SB2', 'Frac(gal)': '.05'}}
    path = tmp_path / 'template #1.dat'; path.write_text('4000 1\n')
    run = {'engine': 'ngsf', 'matches': [m]}
    markup = candidate_rows(run, {'1': {'path': str(path)}})
    parser = BrowserHTML(); parser.feed('<section data-execution="test">' + markup + '</section>')
    rows = parser.rank_tables[0]['rows']
    assert [c['text'] for c in rows[1]] == ['1', 'SN2012dn (Ia-pec, +5d)', '0.123', '0.000Unqualified', '-0.2', 'SB2 (5%)']
    assert rows[1][1]['links'] == [path.as_uri()]
    assert 'title="0.00012345"' in markup  # native precision retained despite display rounding
    assert m['score'] == .00012345 and m['native']['Frac(gal)'] == '.05'
    assert compact_identity({**m, 'template': 'sn2012dn_epoch_3', 'native_class': 'Ia', 'native_subtype': 'Ia-pec', 'phase_days': -2.25}) == 'SN2012dn (Ia-pec, -2.25d)'
    assert compact_identity({**m, 'template': 'SLSN-I/LSQ14mo/LRIS', 'phase_days': None}) == 'LSQ14mo (Ia-pec, phase unknown)'
    assert galaxy_cell({'GALAXY': 'SB2', 'Frac(gal)': 0}).endswith('SB2 (0%)</span>')
    assert 'SB2 (unknown)' in galaxy_cell({'GALAXY': 'SB2'})
    assert decimal_cell(None) == decimal_cell(float('nan')) == '—'
    snid = candidate_rows({**run, 'engine': 'snid_sage'})
    assert 'Aᵥ' not in snid and 'Galaxy type' not in snid


def test_template_link_escapes_names_and_identifies_hdf5_container(tmp_path):
    from spectral_atlas_rank_table import template_cell
    m = {'template': '<object>_epoch_0', 'native_class': 'Ibn', 'phase_days': None}
    html = template_cell(m, {'path': str(tmp_path / 'type & name.hdf5'), 'group': '/templates/<object>/epochs/epoch_0'})
    assert '&lt;object&gt;' in html and '<object>' not in html
    assert 'HDF5 group:' in html and 'opens containing file' in html
    assert '%26' in html and 'target="_blank"' in html


def test_sage_file_location_uses_native_epoch_iteration_order(tmp_path):
    h5py = pytest.importorskip('h5py')
    from refresh_spectral_browser_tables import sage_group
    path = tmp_path / 'templates.hdf5'
    with h5py.File(path, 'w') as file:
        for i in [0, 1, 2, 10]:
            file.create_group(f'templates/sn2012dn/epochs/epoch_{i}').attrs['age'] = i
    with h5py.File(path, 'r') as file:
        group = sage_group(file, 'sn2012dn', '2')
        assert group == '/templates/sn2012dn/epochs/epoch_10'
        assert file[group].attrs['age'] == 10
        assert sage_group(file, 'sn2012dn', None) == '/templates/sn2012dn'

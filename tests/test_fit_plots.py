import copy
import pytest
from spectypus.fit_plots import display_limits, phase_lines, tex
from spectypus.phases import phase_context, references


def test_limits_smooth_50_angstrom_without_changing_curves():
    np = pytest.importorskip('numpy'); pytest.importorskip('scipy')
    x = np.arange(4000., 4201.)
    y = np.zeros(len(x)); y[100] = 100
    points = list(map(list, zip(x, y))); before = copy.deepcopy(points)
    limits, info = display_limits(points)
    assert 0 < limits[1] < 20  # one-pixel spike no longer sets the range to 125
    assert info['observed_samples_outside_limits'] > 0
    assert points == before and info['savgol_width_angstrom'] == 50


def test_limits_do_not_bridge_tellurics_or_depend_on_masked_flux():
    pytest.importorskip('numpy'); pytest.importorskip('scipy')
    points = [[float(x), -2. if x < 4060 else 4.] for x in range(4000, 4121)]
    a, _ = display_limits(points, [[4050, 4070]])
    for p in points:
        if 4050 <= p[0] <= 4070: p[1] = 1e20
    b, _ = display_limits(points, [[4050, 4070]])
    assert a == pytest.approx([-2.2, 4.4]) and b == pytest.approx(a)


def test_limits_coarse_missing_constant_and_invalid_data():
    pytest.importorskip('numpy'); pytest.importorskip('scipy')
    with pytest.raises(ValueError, match='Insufficient'):
        display_limits([[4000, 2], [4100, None], [4200, 2]])
    limits, info = display_limits([[x, 0] for x in range(4000, 4201)])
    assert info['constant_range_padded'] and limits[0] < limits[1]
    with pytest.raises(ValueError, match='Insufficient'): display_limits([[4000, None]])
    with pytest.raises(ValueError, match='increase'): display_limits([[4000, 1], [4000, 2]])


def test_spike_amplitude_cannot_set_limits_and_broad_feature_survives():
    np = pytest.importorskip('numpy'); pytest.importorskip('scipy')
    x = np.arange(4000., 4501., 5.)
    y = 1 + np.exp(-((x-4250)/60)**2)
    clean, _ = display_limits(list(zip(x,y)))
    y[20] = 1e8; y[70] = -1e8
    limits, info = display_limits(list(zip(x,y)))
    assert limits == pytest.approx(clean, rel=.01)
    assert limits[1] > 2 and info['isolated_spikes_replaced_for_limits'] >= 2
    assert limits[0] < 1  # lower bound expands downward, not into positive data


def test_short_filter_is_not_a_quadratic_identity_and_edges_do_not_set_limits():
    pytest.importorskip('numpy'); pytest.importorskip('scipy')
    points = [[float(x), 1.] for x in range(4000, 4501, 20)]
    points[0][1] = 1e9
    limits, info = display_limits(points)
    assert limits == pytest.approx([1/1.1,1.1])
    assert info['edge_or_unsupported_samples_excluded_from_limits'] > 0


def test_requested_titles_and_internal_match_label():
    from spectypus.fit_plots import figure_title, match_label
    c = {'mjd':58242.,'redshift':.132}
    assert figure_title('SN2018avk',c,'ngsf','fixed') == 'SN2018avk - MJD 58242 - NGSF (Fixed-z) (z=0.132)'
    assert figure_title('SN2018avk',c,'ngsf','free') == 'SN2018avk - MJD 58242 - NGSF (Free-z)'
    assert match_label({'template':'sn1993J_epoch_12','phase_days':-8.3}) == 'SN1993J : -8.3 d'


def test_catalogue_dates_keep_reference_band_and_frame():
    refs = references({'source_peak_time':2458256.86, 'source_peak_time_system':'jd', 'peak_band':'g',
                       'discovery_date_ut':'2018-03-17'}, 'data/chen/objects.csv')
    c = phase_context({'mjd':58242, 'redshift':.132}, refs)
    assert c['references'][0]['rest_days'] == pytest.approx(-12.6855123674)
    assert c['references'][0]['band'] == 'g'
    assert {r['kind'] for r in c['references']} == {'maximum', 'discovery'}
    assert all('chen' in line for line in phase_lines(c))
    unknown = phase_context({'mjd':58242}, refs)
    assert all(r['rest_days'] is None for r in unknown['references'])
    assert 'observer' in phase_lines(unknown)[0]


def test_conflicting_dates_are_not_averaged_and_first_detection_is_not_discovery():
    assert references({'first_jd':2458256}, 'fritz') == []
    a = references({'peak_mjd':58000, 'peak_band':'g'}, 'a')
    b = references({'peak_mjd':58001, 'peak_band':'g'}, 'b')
    c = phase_context({'mjd':58010, 'redshift':1}, a+b)
    assert [r['rest_days'] for r in c['references']] == [5,4.5]
    assert all(r['conflicting'] for r in c['references'])
    assert 'unknown' in phase_lines(phase_context({}))[0]
    assert tex('SN_a & 50%') == r'SN\_a \& 50\%'


def test_status_breakdown_does_not_call_finished_fits_blocked():
    from spectypus.review import fit_states
    runs = [dict(engine='ngsf', mode='fixed', status='completed') for _ in range(4)]
    runs += [dict(engine='ngsf', mode='fixed', status='blocked', reason='unknown frame') for _ in range(9)]
    runs += [dict(engine='ngsf', mode='fixed', status='blocked', reason='unknown units')]
    f = fit_states(runs)['ngsf']['fixed']
    assert f['done'] == 4 and f['total'] == 14
    assert f['counts'] == {'completed':4, 'blocked':10}
    assert f['blocked_reasons'] == {'unknown frame':9, 'unknown units':1}


def test_figure_layout_without_exporting_images(tmp_path, monkeypatch):
    pytest.importorskip('scienceplots'); pytest.importorskip('pypalettes')
    import matplotlib
    matplotlib.use('Agg')
    from spectypus import plot_style
    from spectypus.fit_plots import render
    from spectypus.io import write_json
    checked = []
    def inspect(fig, stem):
        for ax in fig.axes:
            if not ax.get_visible(): continue
            assert ax.get_xticklabels()[0].get_fontsize() == 27
            assert any('SN1993J : -8.3 d' == t.get_text() for t in ax.texts)
        assert all(t.get_position()[1] >= 1 for t in fig.texts)  # only collage title; no footer
        checked.append(str(stem))
    monkeypatch.setattr(plot_style, 'savefig_light', inspect)
    curve = {'observed':[[x,1.] for x in range(4000,4501)],'model':[[4000,1],[4500,1]],
             'rank':1,'features':{'telluric_windows':[],'host_lines':[]},
             'candidate':{'template':'sn1993J_epoch_12','phase_days':-8.3}}
    request=tmp_path/'request.json'
    write_json(request,{'source':{'object_id':'SN2018avk'},'curves':[curve],
                        'phase_context':{'mjd':58242.,'redshift':.132},'engine':'ngsf','mode':'fixed'})
    render(request,tmp_path/'output')
    assert len(checked)==2 and not list(tmp_path.rglob('*.jpg')) and not list(tmp_path.rglob('*.pdf'))

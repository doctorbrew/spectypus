import copy
import pytest
from spectypus.fit_plots import display_limits, phase_lines, tex
from spectypus.phases import phase_context, references


def test_limits_smooth_25_angstrom_without_changing_curves():
    np = pytest.importorskip('numpy'); pytest.importorskip('scipy')
    x = np.arange(4000., 4201.)
    y = np.zeros(len(x)); y[100] = 100
    points = list(map(list, zip(x, y))); before = copy.deepcopy(points)
    limits, info = display_limits(points)
    assert 0 < limits[1] < 20  # one-pixel spike no longer sets the range to 125
    assert info['observed_samples_outside_limits'] > 0
    assert points == before and info['savgol_width_angstrom'] == 25


def test_limits_do_not_bridge_tellurics_or_depend_on_masked_flux():
    pytest.importorskip('numpy'); pytest.importorskip('scipy')
    points = [[float(x), -2. if x < 4060 else 4.] for x in range(4000, 4121)]
    a, _ = display_limits(points, [[4050, 4070]])
    for p in points:
        if 4050 <= p[0] <= 4070: p[1] = 1e20
    b, _ = display_limits(points, [[4050, 4070]])
    assert a == pytest.approx([-2.5, 5.]) and b == pytest.approx(a)


def test_limits_coarse_missing_constant_and_invalid_data():
    pytest.importorskip('numpy'); pytest.importorskip('scipy')
    limits, info = display_limits([[4000, 2], [4100, None], [4200, 2]])
    assert info['unsmoothed_segments'] == 2 and info['constant_range_padded']
    assert limits[0] < limits[1]
    with pytest.raises(ValueError, match='No usable'): display_limits([[4000, None]])
    with pytest.raises(ValueError, match='increase'): display_limits([[4000, 1], [4000, 2]])


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

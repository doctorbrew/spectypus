import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest

from spectypus.features import features, TELLURIC_WINDOWS
from spectypus.config import load_config
from spectypus.adapters.engines import build_command
from spectypus.io import read_json


def test_host_markers_use_supplied_z_tellurics_stay_observer_frame():
    f = features(.2, 3000, 10000, TELLURIC_WINDOWS)
    assert next(x for x in f['host_lines'] if x['name']=='Hα')['observed_angstrom'] == pytest.approx(6562.801*1.2)
    assert f['telluric_windows'][0] == [6860, 6960]
    assert not features(None, 3000, 10000, TELLURIC_WINDOWS)['host_lines']
    assert not f['host_lines_masked']


@pytest.mark.parametrize('value', [[[2,1]], [[0,1]], [[1,float('nan')]], [1], 'wrong'])
def test_bad_mask_config_rejected(value, config_factory):
    with pytest.raises((ValueError, TypeError)):
        load_config(config_factory(telluric_windows=value))


def test_ngsf_excludes_mask_from_object_and_template_normal_equations(tmp_path):
    np=pytest.importorskip('numpy')
    from spectypus.adapters.ngsf_bridge import install_masks
    wave=np.arange(100,dtype=float)+6800
    original=np.ones(100)*2
    module=SimpleNamespace()
    module.sn_hg_arrays=lambda *a,**k:(np.ones((1,1,100)),np.arange(100,dtype=float).reshape(1,1,-1))
    def core(data,*args,**kwargs):
        sn,gal=module.sn_hg_arrays()
        valid=np.isfinite(data)
        assert np.array_equal(np.isfinite(sn[0,0]),valid)
        return np.linalg.lstsq(np.column_stack([sn[0,0,valid],gal[0,0,valid]]),data[valid],rcond=None)[0]
    module.core=core
    install_masks(module,[[6860,6870]],tmp_path/'mask.json')
    a=module.core(original,0,0,[],{},[],{},{},wave,10,1)
    perturbed=original.copy();perturbed[60:71]=1e20
    b=module.core(perturbed,0,0,[],{},[],{},{},wave,10,1)
    assert np.allclose(a,b) and a[0]==pytest.approx(2)
    assert np.all(original==2)
    assert read_json(tmp_path/'mask.json')['telluric_grid_samples']==11


def test_identical_input_rows_repaired_but_conflicting_values_rejected(tmp_path):
    p=Path(__file__).resolve().parents[1]/'scripts/prepare_retry_campaign.py'
    spec=importlib.util.spec_from_file_location('retry_prepare',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    source=tmp_path/'s.dat';source.write_text('4000 2\n4000 2\n5000 3\n');dest=tmp_path/'derived.dat'
    report=m.remove_identical_rows(source,dest)
    assert report['removed_identical_rows']==1 and len(source.read_text().splitlines())==3
    assert dest.read_text()=='4000 2\n5000 3\n'
    source.write_text('4000 2\n4000 4\n5000 3\n')
    with pytest.raises(ValueError,match='differing'):m.remove_identical_rows(source,tmp_path/'bad.dat')
    assert not (tmp_path/'bad.dat').exists()


def test_mask_and_curve_flags_reach_both_adapters(tmp_path,config_factory):
    params=tmp_path/'params.json';params.write_text('{}')
    cfg=load_config(config_factory(telluric_windows=TELLURIC_WINDOWS,save_fit_curves=True))
    cfg['engines']['ngsf']={'python':'python','root':str(tmp_path),'parameters':str(params)}
    run={'engine':'snid_sage','mode':'fixed','redshift':.2}
    sage=tmp_path/'sage';sage.mkdir();cmd,_,_=build_command(run,cfg,sage)
    assert '--wavelength-masks' in cmd and '--fit-curves' in cmd and '--emclip' not in cmd
    ngsf=tmp_path/'ngsf';ngsf.mkdir();cmd,_,_=build_command({**run,'engine':'ngsf'},cfg,ngsf)
    assert cmd[-1].endswith('spectral_features.json')
    assert read_json(ngsf/'parameters.json')['mask_telluric']==1
    assert read_json(ngsf/'parameters.json')['mask_galaxy_lines']==0


def test_input_masks_are_sent_to_both_engines_separately_from_tellurics(tmp_path, config_factory):
    params = tmp_path / 'params.json'; params.write_text('{}')
    cfg = load_config(config_factory(telluric_windows=[[6800, 6900]]))
    cfg['engines']['ngsf'] = {'python': 'python', 'root': str(tmp_path), 'parameters': str(params)}
    run = {'engine': 'snid_sage', 'mode': 'free', 'redshift': None, 'input_mask_windows': [[4500, 4550]]}
    sage = tmp_path / 'sage'; sage.mkdir()
    cmd, _, _ = build_command(run, cfg, sage)
    assert [list(map(float, v.split(':'))) for v in cmd[cmd.index('--wavelength-masks')+1:]] == [[4500, 4550], [6800, 6900]]
    ngsf = tmp_path / 'ngsf'; ngsf.mkdir()
    build_command({**run, 'engine': 'ngsf'}, cfg, ngsf)
    features = read_json(ngsf / 'spectral_features.json')
    assert features['input_mask_windows'] == [[4500, 4550]]
    assert features['telluric_windows'] == [[6800, 6900]]
    assert features['wavelength_masks'] == [[4500, 4550], [6800, 6900]]
    assert cfg['telluric_windows'] == [[6800, 6900]]

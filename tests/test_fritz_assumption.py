import importlib.util
from pathlib import Path
import pytest
from spectypus.aggregate import aggregate
from test_aggregate import source, plan_for, record, candidate


def inspector():
    path = Path(__file__).resolve().parents[1]/'scripts/prepare_fritz_campaign.py'
    spec = importlib.util.spec_from_file_location('prepare_fritz', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.inspect_metadata


def test_json_array_conversion_preserves_original_values_and_missingness(tmp_path):
    convert = inspector().__globals__['derive_ascii']
    target = tmp_path/'derived.dat'
    assert convert({'wavelengths':[4000,5000], 'fluxes':[1.25,-2]}, target) == ''
    assert target.read_text() == '4000 1.25\n5000 -2\n'
    missing = tmp_path/'missing.dat'
    assert convert({'wavelengths':[4000,5000], 'fluxes':[1,None]}, missing)
    assert not missing.exists()
    assert convert({'wavelengths':[4000,5000], 'fluxes':[1]}, missing)


def test_absent_frame_is_not_verified_and_flux_units_are_not_wave_units():
    inspect = inspector()
    assert inspect({'units':None,'altdata':None}) == []
    assert inspect({'units':'Jy','altdata':[]}) == []
    assert inspect({'altdata':{'CUNIT1':{'value':'pixel','comment':'old image WCS'}}}) == []
    assert inspect({'altdata':{'FRAMENO':1, 'FRAMEID':'1', 'wavelength_frame':'observer'}}) == []


@pytest.mark.parametrize('raw', [
    {'altdata':{'CUNIT1':'nm'}},
    {'altdata':{'CUNIT1':{'value':'nm'}}},
    {'wavelength_frame':'rest'},
    {'altdata':{'RESTFRAM':True}},
    {'original_file_string':'# Wavelengths are rest-frame\n4000 1\n5000 2'},
])
def test_explicit_contradictions_remain_flagged(raw):
    assert inspector()(raw)


def test_assumptions_survive_successful_classification_and_object_aggregation():
    s={**source('s'),'frame_assumed':'true','frame_review_required':'true'}
    p=plan_for([s]);r=record(candidate('Ia'));a=aggregate(p,{'s-a':r,'s-b':r})
    assert a['objects'][0]['complete'] and a['objects'][0]['proposed_class']=='Ia'
    assert a['objects'][0]['frame_assumed'] and a['objects'][0]['frame_review_required']
    assert a['spectra'][0]['frame_assumed']
    clean=aggregate(plan_for([source('t')]),{})
    assert not clean['objects'][0]['frame_review_required']


def test_completed_assumed_frame_stays_in_review_and_csv(tmp_path, source_factory, config_factory, fake_engine):
    from spectypus.io import write_csv, read_csv
    from spectypus.pipeline import run_batch
    from spectypus.review import read_snapshot
    row={**source_factory(z='.1'), 'frame_assumed':'true', 'frame_review_required':'true'}
    path=tmp_path/'inputs.csv'; write_csv(path,[row],list(row))
    output=tmp_path/'run'; run_batch(path,config_factory(),output)
    obj=read_snapshot(output)['summary']['objects'][0]
    assert obj['complete'] and obj['status']=='proposed' and obj['needs_review']
    assert read_csv(output/'objects.csv')[0]['frame_assumed']=='True'
    assert read_csv(output/'spectra.csv')[0]['frame_review_required']=='True'

import pytest
from spectypus.evaluation import select_spectrum, summarize_rows, validate_labels


def test_epoch_selection_ignores_scores_and_rejects_provisional_or_blocked():
    rows=[{'spectrum_id':'early','mjd':1,'blocked_reason':'unknown frame'},
          {'spectrum_id':'assumed','mjd':2,'frame_assumed':True},
          {'spectrum_id':'missing-date','mjd':''},
          {'spectrum_id':'late','mjd':4,'best_score':99},
          {'spectrum_id':'first','mjd':3,'best_score':0}]
    assert select_spectrum(rows)['spectrum_id']=='first'


def test_failures_and_abstentions_remain_in_object_denominator():
    rows=[dict(engine='ngsf',mode='free',truth='SLSN-I',overlap='no_known_alias_overlap',
               prediction=p,outcome=o) for p,o in [('SLSN-I','predicted'),(None,'failed'),
                                                    (None,'no_good_match'),('Ia','predicted')]]
    result=summarize_rows(rows)['ngsf/free/all']
    assert result['objects']==4 and result['correct']==1
    assert result['coverage']==.5
    assert result['by_class']['SLSN-I']['recovery_fraction']==.25
    rows[0]['overlap']='overlap'
    assert summarize_rows(rows)['ngsf/free/no_known_alias_overlap']['correct']==0


def test_labels_require_independent_provenance_and_disjoint_aliases():
    obj=dict(object_id='SN2021abc',aliases=['ZTF21abc'],class_label='SLSN-I',
             review_status='accepted',references=[{'url':'https://example.org/paper','locator':'A.1'}])
    labels={'schema':'spectypus-evaluation-labels/1','objects':[obj]}
    validate_labels(labels)
    labels['objects'].append({**obj,'object_id':'2021abc'})
    with pytest.raises(ValueError,match='identities'): validate_labels(labels)
    labels['objects']=[{**obj,'references':[]}]
    with pytest.raises(ValueError,match='references'): validate_labels(labels)


def test_verified_saved_evaluation_preserves_artifacts_and_detects_corruption(
        source_factory, manifest_factory, config_factory, fake_engine, tmp_path, monkeypatch):
    from spectypus.pipeline import run_batch
    from spectypus.io import file_hash
    from spectypus import evaluation
    source=source_factory()
    source['mjd']='60000'
    output=tmp_path/'run'
    run_batch(manifest_factory([source]),config_factory(),output)
    labels={'schema':'spectypus-evaluation-labels/1','objects':[
        dict(object_id='SN-A',aliases=[],class_label='Ia',review_status='accepted',
             references=[{'url':'https://example.org/review','locator':'Table 1'}])]}
    monkeypatch.setattr(evaluation,'bank_inventory',lambda *args:
                        {'path':'unused','sha256':'bank-v1','names':['different-object']})
    protected={p:file_hash(p) for p in output.rglob('*') if p.is_file()}
    result=evaluation.evaluate_saved(output,labels,{'snid_sage':'unused'})
    free=next(r for r in result['rows'] if r['mode']=='free')
    assert free['prediction']=='Ia'
    assert free['overlap']=='no_known_alias_overlap'
    assert protected=={p:file_hash(p) for p in protected}
    record=next((output/'attempts').rglob('record.json'))
    record.write_text('{}')
    result=evaluation.evaluate_saved(output,labels,{'snid_sage':'unused'})
    free=next(r for r in result['rows'] if r['mode']=='free')
    assert free['outcome']=='invalid_evidence' and free['prediction'] is None


def test_native_subtype_metric_does_not_replace_saved_pipeline_label():
    row=dict(engine='snid_sage',mode='free',truth='SLSN-I',overlap='no_known_alias_overlap',
             prediction=None,outcome='unsupported_taxonomy',
             native_prediction='SLSN-I',native_outcome='predicted')
    assert summarize_rows([row])['snid_sage/free/all']['correct']==0
    native=summarize_rows([row],prediction_key='native_prediction',outcome_key='native_outcome')
    assert native['snid_sage/free/all']['correct']==1
    assert row['prediction'] is None


def test_top_three_and_intervals_keep_failed_objects():
    from spectypus.evaluation import wilson_interval
    row=dict(engine='ngsf',mode='free',truth='SLSN-I',overlap='no_known_alias_overlap',
             prediction='Ia',outcome='predicted',native_top_three=[
                 {'class_label':'Ia'}, {'class_label':'SLSN-I'}])
    failed={**row,'prediction':None,'outcome':'failed','native_top_three':[]}
    result=summarize_rows([row,failed])['ngsf/free/all']['by_class']['SLSN-I']
    assert result['recovered']==0 and result['top3_recovered']==1
    assert result['top3_recovery_fraction']==.5
    assert wilson_interval(0,0) is None
    lower,upper=wilson_interval(1,2)
    assert 0<lower<.5<upper<1


def test_overlap_cohort_includes_objects_without_eligible_epoch(
        source_factory, manifest_factory, config_factory, fake_engine, tmp_path, monkeypatch):
    from spectypus.pipeline import run_batch
    from spectypus import evaluation
    output=tmp_path/'no-date'
    run_batch(manifest_factory([source_factory()]),config_factory(),output)
    labels={'schema':'spectypus-evaluation-labels/1','objects':[
        dict(object_id='SN-A',aliases=[],class_label='Ia',review_status='accepted',
             references=[{'url':'https://example.org/review','locator':'Table 1'}])]}
    monkeypatch.setattr(evaluation,'bank_inventory',lambda *args:
                        {'path':'unused','sha256':'bank-v1','names':['different-object']})
    result=evaluation.evaluate_saved(output,labels,{'snid_sage':'unused'})
    cohort=result['metrics']['snid_sage/free/no_known_alias_overlap']
    assert cohort['objects']==1
    assert cohort['outcomes']=={'unsupported_input':1}

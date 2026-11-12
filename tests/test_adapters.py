from __future__ import annotations

import json
from pathlib import Path

import pytest

from spectypus.adapters.engines import build_command, parse_ngsf, parse_sage
from spectypus.adapters.sage_bridge import _json_safe, candidate_payload
from spectypus.config import load_config
from spectypus.io import read_json, write_csv
from spectypus.taxonomy import normalize_class
from conftest import sage_payload


def test_sage_native_metric_descending_and_no_good_match(tmp_path):
    payload = sage_payload()
    payload["candidates"].extend([{**payload["candidates"][0], "score_value": 8, "template_name": "best"},
                                  {**payload["candidates"][0], "score_value": None}])
    path = tmp_path / "sage.json"
    path.write_text(json.dumps(payload))
    matches, status = parse_sage(path)
    assert status == "completed"
    assert [m["score"] for m in matches] == [8, 5]
    assert matches[0]["metric"] == "hsigma_lap_ccc"
    assert matches[0]["class_label"] == "Ia"
    payload["classification_success"] = False
    path.write_text(json.dumps(payload))
    matches, status = parse_sage(path)
    assert status == "no_good_match" and not any(m["qualified"] for m in matches)


def test_ngsf_native_lower_is_better_negative_nonfinite_unrankable(tmp_path):
    path = tmp_path / "ngsf.csv"
    rows = [{"SN": f"Ia-norm/SN{n}/instrument phase-band : 0V", "CHI2/dof2": score,
             "Z": ".1", "Phase": "0", "GALAXY": "E.dat"}
            for n, score in enumerate([4, -1, "nan", 2, 0])]
    write_csv(path, rows, list(rows[0]))
    candidates, status = parse_ngsf(path)
    assert status == "completed"
    assert [m["score"] for m in candidates] == [0, 2, 4]
    assert candidates[0]["native_class"] == "Ia-norm"
    assert candidates[0]["class_label"] == "Ia"
    assert candidates[0]["native"]["GALAXY"] == "E.dat"
    assert candidates[0]["metric"] == "CHI2/dof2"


def test_ngsf_unknown_template_identity_does_not_guess_class(tmp_path):
    path = tmp_path / "ngsf.csv"
    path.write_text("SN,CHI2/dof2,Z,Phase,GALAXY\nSN-Ia-by-name,1,.1,0,E\n")
    candidates, _ = parse_ngsf(path)
    assert candidates[0]["class_label"] == ""


def test_invalid_ngsf_result_not_empty_success(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("score,template\n1,A\n")
    with pytest.raises(ValueError, match="requires"):
        parse_ngsf(path)


@pytest.mark.parametrize("native,subtype,expected", [("Ia-norm", "", "Ia"), ("Ia", "Ia-norm", "Ia"),
    ("Ic", "Ic-BL", "Ic-BL"), ("II", "IIn", "IIn"), ("SLSN-I", "Ic-norm", "SLSN-I"),
    ("mystery", "", ""), ("TDE H+He", "", "TDE")])
def test_taxonomy_conservative(native, subtype, expected):
    assert normalize_class(native, subtype) == expected


def test_nonfinite_native_missingness_is_json_null():
    assert _json_safe({"sigma_z": float("nan"), "other": [float("inf"), 2]}) == {"sigma_z": None, "other": [None, 2]}


def test_bridge_candidates_retained_below_threshold():
    from types import SimpleNamespace
    result = SimpleNamespace(all_matches=[{"hsigma_lap_ccc": .4, "redshift": .1,
                             "template": {"name": "A", "type": "Ia", "age": 2}}], success=False)
    payload = candidate_payload(result, 1.5)
    assert payload["candidate_count"] == 1
    assert payload["classification_success"] is False
    assert payload["candidates"][0]["passes_threshold"] is False


def test_ngsf_fractional_grid_and_private_parameters(tmp_path, config_factory):
    params = tmp_path / "parameters.json"
    params.write_text(json.dumps({"object_to_fit": "original.dat", "mask_galaxy_lines": 1}))
    config = load_config(config_factory(engines={"ngsf": {"python": "/usr/bin/python3", "root": str(tmp_path), "parameters": str(params)}},
                       free_redshift={"min": 0, "max": .3, "step": .05}))
    directory = tmp_path / "attempt"
    directory.mkdir()
    command, cwd, result = build_command({"engine": "ngsf", "mode": "free", "redshift": None}, config, directory)
    effective = read_json(directory / "parameters.json")
    assert int((effective["z_range_end"] - effective["z_range_begin"]) / effective["z_int"]) + 1 == 7
    assert effective["how_many_plots"] == 0 and effective["mask_galaxy_lines"] == 0
    assert read_json(params)["object_to_fit"] == "original.dat"
    assert effective["saving_results_path"].startswith(str(directory))
    assert result == directory / "native/spectrum.csv"


def test_sage_fixed_zero_is_passed(tmp_path, config_factory):
    cfg = load_config(config_factory())
    command, _, _ = build_command({"engine": "snid_sage", "mode": "fixed", "redshift": 0.0}, cfg, tmp_path)
    assert command[command.index("--forced-redshift") + 1] == "0.0"
    assert "--zmin" not in command


@pytest.mark.parametrize("overrides", [{"top_n": 0}, {"timeout_seconds": float("nan")},
    {"free_redshift": {"min": 0, "max": .3, "step": .07}}, {"redshift_mode": "guess"},
    {"engines": {}}, {"unknown_key": 3}])
def test_invalid_configuration_rejected(config_factory, overrides):
    with pytest.raises(ValueError):
        load_config(config_factory(**overrides))


@pytest.mark.parametrize('subtype,expected', [('SLSN-I','SLSN-I'),('SLSN-II','SLSN-II'),
                                           ('',''),('Ic-norm',''),('unknown','')])
def test_sage_generic_slsn_requires_explicit_physical_subtype(subtype, expected):
    assert normalize_class('SLSN', subtype) == expected


def test_sage_slsn_normalization_keeps_native_evidence(tmp_path):
    import json
    from conftest import sage_payload
    path=tmp_path/'native.json'
    payload=sage_payload(label='SLSN',subtype='SLSN-I',score=5.25)
    path.write_text(json.dumps(payload))
    rows,status=parse_sage(path)
    assert status=='completed'
    assert rows[0]['class_label']=='SLSN-I'
    assert rows[0]['native_class']=='SLSN'
    assert rows[0]['native_subtype']=='SLSN-I'
    assert rows[0]['native']==payload['candidates'][0]
    assert rows[0]['score']==5.25 and rows[0]['qualified'] is True

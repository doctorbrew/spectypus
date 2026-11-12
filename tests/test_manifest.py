from __future__ import annotations

import pytest

from spectypus.io import write_csv
from spectypus.manifest import discover, prepare_spectra, read_manifest, spectrum_data


def test_zero_redshift_is_known_and_propagates(source_factory, manifest_factory):
    path = manifest_factory([source_factory("a", z="0"), source_factory("b", flux=2)])
    rows = read_manifest(path)
    assert [row["redshift"] for row in rows] == [0.0, 0.0]
    assert [row["redshift_source"] for row in rows] == ["manifest", "manifest"]


def test_targets_exact_identity_missing_stays_unknown(tmp_path, source_factory, manifest_factory):
    path = manifest_factory([source_factory("a"), source_factory("b", "SN-B", flux=2)])
    targets = tmp_path / "targets.csv"
    write_csv(targets, [{"object_id": "SN-A", "redshift": 0.2, "redshift_source": "host"}],
              ["object_id", "redshift", "redshift_source"])
    rows = read_manifest(path, targets)
    assert rows[0]["redshift"] == 0.2 and rows[0]["redshift_source"] == "host"
    assert rows[1]["redshift"] is None


@pytest.mark.parametrize("value", ["nan", "inf", "-0.1", "unknown"])
def test_bad_redshift_is_not_silently_free(value, source_factory, manifest_factory):
    with pytest.raises(ValueError, match="redshift"):
        read_manifest(manifest_factory([source_factory(z=value)]))


def test_redshift_conflicts_are_errors(source_factory, manifest_factory, tmp_path):
    manifest = manifest_factory([source_factory("a", z="0.1"), source_factory("b", z="0.2")])
    with pytest.raises(ValueError, match="conflicting"):
        read_manifest(manifest)
    manifest = manifest_factory([source_factory("a", z="0.1")])
    targets = tmp_path / "targets.csv"
    write_csv(targets, [{"object_id": "SN-A", "redshift": ".2"}], ["object_id", "redshift"])
    with pytest.raises(ValueError, match="conflicting"):
        read_manifest(manifest, targets)


def test_duplicate_ids_rejected(source_factory, manifest_factory, tmp_path):
    row = source_factory()
    with pytest.raises(ValueError, match="repeated"):
        read_manifest(manifest_factory([row, row]))
    targets = tmp_path / "targets.csv"
    targets.write_text("object_id,redshift\nSN-A,0.1\nSN-A,0.1\n")
    with pytest.raises(ValueError, match="repeated target"):
        read_manifest(manifest_factory([row]), targets)


def test_rest_nm_transform_once_preserves_negative_flux(tmp_path):
    path = tmp_path / "s.dat"
    path.write_text("# wave flux uncertainty\n500 -2 .2\n300 4 .4\n")
    row = {"path": str(path), "wavelength_frame": "rest", "wavelength_unit": "nm", "redshift": 0.5}
    content, report = spectrum_data(row)
    assert content == "4500 4\n7500 -2\n"
    assert report["wavelength_scale"] == 15
    assert report["staged_unit"] == "angstrom"
    assert report["sorted_wavelengths"]
    assert report["ignored_extra_column_counts"] == [1]
    assert path.read_text().startswith("# wave")


def test_masked_flux_staging_preserves_values_and_scales_gap_cells(tmp_path):
    path = tmp_path / 'masked.asci'
    original = '300 nan\n400 -2\n500 nan\n600 inf\n700 3\n800 4\n900 nan\n'
    path.write_text(original)
    row = {'path': str(path), 'wavelength_frame': 'rest', 'wavelength_unit': 'nm',
           'redshift': .5, 'nonfinite_policy': 'mask'}
    content, report = spectrum_data(row)
    assert content == '6000 -2\n10500 3\n12000 4\n'
    assert report['input_mask_windows'] == [[4500, 5250], [6750, 9750], [12750, 13500]]
    assert [s['line'] for s in report['excluded_samples']] == [1, 3, 4, 7]
    assert report['original_samples'] == 7 and report['samples'] == 3
    assert path.read_text() == original
    # Different missing support cannot be suppressed as a duplicate input.
    other = tmp_path / 'other.asci'
    other.write_text('400 -2\n700 3\n800 4\n')
    _, other_report = spectrum_data({**row, 'path': str(other)})
    assert report['numeric_sha256'] != other_report['numeric_sha256']


@pytest.mark.parametrize('bad', ['nan 2', '0 nan', '4000 broken', '4000 nan\n4000 1'])
def test_mask_policy_does_not_hide_invalid_wavelengths_or_malformed_values(tmp_path, bad):
    path = tmp_path / 'bad.txt'
    path.write_text(bad + '\n5000 2\n6000 3\n')
    with pytest.raises(ValueError):
        spectrum_data({'path': str(path), 'wavelength_frame': 'observer', 'wavelength_unit': 'angstrom',
                       'nonfinite_policy': 'mask'})


@pytest.mark.parametrize("row", ["4000,,0.1", ",4,0.1"])
def test_empty_csv_wavelength_or_flux_never_shifts_uncertainty(row, source_factory, manifest_factory):
    from pathlib import Path
    source = source_factory()
    Path(source["path"]).write_text(f"wavelength,flux,error\n{row}\n5000,2,.2\n6000,3,.3\n")
    prepared = prepare_spectra(read_manifest(manifest_factory([source])))
    assert "invalid numeric sample" in prepared[0]["blocked_reason"]


def test_csv_extra_uncertainty_column_is_not_flux(tmp_path):
    path = tmp_path / "source.csv"
    path.write_text("wavelength,flux,error\n4000,-2,0.1\n5000,3,0.2\n")
    content, report = spectrum_data({"path": str(path), "wavelength_frame": "observer",
                                     "wavelength_unit": "angstrom", "redshift": None})
    assert content == "4000 -2\n5000 3\n"
    assert report["ignored_extra_column_counts"] == [1]


@pytest.mark.parametrize("content", ["3000 nan\n4000 1\n", "3000 1\n3000 2\n",
                                     "0 2\n4000 1\n", "garbage\n3000 1\n4000 2\n"])
def test_invalid_samples_block_whole_spectrum(content, source_factory, manifest_factory):
    row = source_factory()
    from pathlib import Path
    Path(row["path"]).write_text(content)
    prepared = prepare_spectra(read_manifest(manifest_factory([row])))
    assert prepared[0]["blocked_reason"]
    assert "staging" not in prepared[0]


@pytest.mark.parametrize("frame,unit,z", [("unknown", "angstrom", ""), ("rest", "angstrom", ""),
                                        ("observer", "meters", "")])
def test_unsupported_units_and_frames_block(frame, unit, z, source_factory, manifest_factory):
    rows = prepare_spectra(read_manifest(manifest_factory([source_factory(frame=frame, unit=unit, z=z)])))
    assert rows[0]["blocked_reason"]


def test_numeric_duplicates_keep_rows_and_conflicting_identity_blocks(source_factory, manifest_factory):
    rows = prepare_spectra(read_manifest(manifest_factory([source_factory("a"), source_factory("b")])))
    assert rows[0]["duplicate_of"] == "" and rows[1]["duplicate_of"] == "a"
    conflict = prepare_spectra(read_manifest(manifest_factory([source_factory("a"), source_factory("b", "SN-B")])))
    assert all(row["identity_conflict"] for row in conflict)
    assert all(row["blocked_reason"] for row in conflict)


def test_relative_paths_resolve_from_manifest(tmp_path, source_factory, manifest_factory):
    row = source_factory()
    row["path"] = "spectrum.dat"
    manifest = manifest_factory([row])
    assert read_manifest(manifest)[0]["path"] == str(tmp_path / "spectrum.dat")


def test_explicit_batch_layout(tmp_path):
    for batch in ("night1", "night2"):
        directory = tmp_path / "raw" / batch / "SN-A"
        directory.mkdir(parents=True)
        (directory / "s.dat").write_text("3000 1\n9000 2\n")
    output = tmp_path / "manifest.csv"
    assert discover(tmp_path / "raw", output, layout="batch-object", frame="observer", unit="angstrom") == 2
    rows = read_manifest(output)
    assert {r["object_id"] for r in rows} == {"SN-A"}
    assert len({r["spectrum_id"] for r in rows}) == 2
    with pytest.raises(ValueError, match="overwrite"):
        discover(tmp_path / "raw", output, layout="batch-object", frame="observer", unit="angstrom")

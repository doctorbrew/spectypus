"""Optical telluric windows and illustrative host-line positions, in Angstrom."""

TELLURIC_WINDOWS = [[6860.0, 6960.0], [7150.0, 7350.0], [7550.0, 7750.0],
                    [8100.0, 8400.0], [8900.0, 9900.0]]
HOST_LINES = [("[O II]", 3727.0), ("Hδ", 4101.74), ("Hγ", 4340.47),
              ("Hβ", 4861.325), ("[O III]", 4958.911), ("[O III]", 5006.843),
              ("[N II]", 6548.05), ("Hα", 6562.801), ("[N II]", 6583.45),
              ("[S II]", 6716.44), ("[S II]", 6730.82)]


def features(redshift, minimum, maximum, windows):
    return {"telluric_windows": [[max(lo, minimum), min(hi, maximum)] for lo, hi in windows
                                  if hi >= minimum and lo <= maximum],
            "host_lines": [] if redshift is None else [
                {"name": name, "rest_angstrom": wave, "observed_angstrom": wave * (1 + redshift)}
                for name, wave in HOST_LINES if minimum <= wave * (1 + redshift) <= maximum],
            "host_redshift": redshift,
            "host_note": "Expected positions, not detections; approximate air-wavelength references. Input air/vacuum convention may differ.",
            "host_lines_masked": False}

# Validation and scientific limits

Spectypus is an exploratory spectral-classification pipeline. Native matches
are candidates for review. Combined support is uncalibrated, dimensionless
evidence; it is not a probability or a secure classification.

## Software verification

The automated suite exercises adapters, native result semantics, aggregation,
failure states, manifests, installed reporting, template links and offline JPG
exports using synthetic fixtures. Optional dependency checks can be skipped in
a core-only environment. CI tests Linux and installed wheels on Linux/macOS
with Python 3.10 and 3.12. See [release verification](RELEASE.md).

Tests preserve original spectra, native scores and score direction, fit redshift
provenance, qualification flags and saved attempts. Reporting reads saved evidence;
it does not refit spectra. Reviewer logs remain separate from engine results.
Fixed-redshift inputs are not independent spectral measurements. Missing support
is not silently treated as zero.

## Report acceptance

Master match grids are 300-dpi JPGs. The standalone HTML extracts selected panels
at their original pixel scale, retaining complete labels. Chrome folder saves
and Firefox downloads were exercised; Safari's individual-download fallback was
confirmed manually. Automated Safari acceptance is not established. Browser
permissions and multiple-download restrictions still apply.

Display smoothing is separate from robust y-limit calculation. Plot clipping
does not remove numerical samples. Models retain their native coverage, and
reconstructed samples require verified native inputs and agreement with saved
finite curves. Template types stay distinct from target classifications.

## Scientific limitations

Template provisioning has offline regression coverage for downloading/registering
assets, retries, single-engine configuration, checksum failures, unsafe archives
and preservation of existing assets/configs. A live SAGE 1.2.3 archive passed
checksum and structure checks; the pinned NGSF source archive was verified.
WISeREP returned HTTP 403 from the validation environment, so a full fresh NGSF
bank download is not established. ZIP fallback was exercised using fixture
archives. These checks do not run classifiers or establish template quality.

A literature-labelled, 157-object SLSN-I recovery benchmark was completed. It
is not a representative multiclass accuracy, purity or calibration measurement.
Local real-engine checks used bounded samples and external template banks; they
do not establish general throughput or accuracy. External scientific inputs,
completed attempts and detailed experiment records are retained by their owner
and are not bundled in this repository.

A representative evaluation requires independent labels, object-disjoint splits,
an explicit template-leakage policy, per-class precision/recall and confusion,
coverage/abstention, and failure denominators. No calibrated-accuracy claim is
supported by passing software tests. See [score semantics](USAGE.md).

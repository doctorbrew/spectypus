# Input templates

These are schema examples with fictional object identities, redshifts and
paths. They are not observations, reference classifications or executable
science fixtures.

- Copy `spectypus.example.json` and configure installed engine paths and the
  appropriate redshift-search interval.
- Copy `manifest.example.csv` and replace every example row with your actual
  reduced-spectrum metadata, or use `spectypus manifest` for an explicitly
  organized input directory.
- `targets.example.csv` demonstrates the optional external redshift table.
  Missing objects/blank redshifts retain the normal unknown-redshift behavior.

The main README documents commands, score semantics and scientific limits.

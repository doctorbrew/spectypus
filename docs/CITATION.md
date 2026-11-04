# Credits and citation guide

## Spectypus development

- **Avinash Singh** develops Spectypus, sets its scientific requirements and
  directs its development.
- **GPT 6 Astra (OpenAI), used through Codex**, provided substantial assistance
  with code implementation, debugging, tests, performance experiments and
  documentation.
- The human maintainer retains responsibility for scientific choices and
  release decisions. The [development log](DEVELOPMENT_LOG.md) records changes;
  [Validation](VALIDATION.md) records the checks performed and their limits.

## Using Spectypus in a publication

- Credit **Avinash Singh, Spectypus**, with the
  [repository URL](https://github.com/sPaMFouR/spectypus).
- Record the package version and exact commit used for the analysis. Use
  `spectypus --version` and, for a source checkout, `git rev-parse HEAD`.
  For an older saved run, report its recorded software version rather than
  the current checkout.
- Cite the classifiers that contributed to the reported results. For
  SNID-SAGE, include both SNID and SNID-SAGE; for NGSF, include both the NGSF
  announcement and the original Superfit paper. Use all four when both
  classifiers contribute.
- Cite the observational data and template collections you used, following
  their providers' instructions. Software citations do not replace those
  data references.
- Acknowledge the scientific libraries used in the analysis, following their
  own guidance, such as [Astropy's citation instructions](https://www.astropy.org/acknowledging.html).

Example wording for an analysis using both classifiers:

> We used Spectypus (Avinash Singh; software version and commit reported with
> this analysis) to run SNID-SAGE (Stoppa & Smartt 2026), based on SNID
> (Blondin & Tonry 2007), and NGSF (Goldwasser et al. 2022), based on Superfit
> (Howell et al. 2005), and to review their spectral matches for each supernova.

Adapt this to the tools actually used and supply your version, commit and data
references. The development acknowledgement above describes Spectypus's use of
AI; any disclosure about AI use in your own research or writing should describe
your own workflow.

## Classifier references

The four entries below are available in [references.bib](references.bib).

- **Original SNID:** Blondin, S., & Tonry, J. L. (2007).
  *Determining the Type, Redshift, and Age of a Supernova Spectrum.*
  The Astrophysical Journal, **666**, 1024–1047.
  [DOI: 10.1086/520494](https://doi.org/10.1086/520494).
  This is the reference identified on the
  [original SNID website](https://people.lam.fr/blondin.stephane/software/snid/).
- **SNID-SAGE:** Stoppa, F., & Smartt, S. J. (2026).
  *SNID–SAGE: a modern framework for interactive supernova classification and
  spectral analysis.* Monthly Notices of the Royal Astronomical Society,
  **549**(4), stag1066.
  [DOI: 10.1093/mnras/stag1066](https://doi.org/10.1093/mnras/stag1066).
  [Preprint: arXiv:2603.28741](https://arxiv.org/abs/2603.28741).
  Use the published reference rather than treating this as an unpublished preprint.
- **NGSF:** Goldwasser, S., Yaron, O., Sass, A., Irani, I., Gal-Yam, A., &
  Howell, D. A. (2022).
  *The Next Generation SuperFit (NGSF) tool is now available for online
  execution on WISeREP.* Transient Name Server AstroNote **2022-191**.
  [Announcement and citation instructions](https://www.wis-tns.org/node/138742);
  ADS bibcode `2022TNSAN.191....1G`.
  This is a software announcement, not a journal article. Its authors request
  citations to both this note and Howell et al. (2005), including for standalone use.
- **Original Superfit:** Howell, D. A., et al. (2005).
  *Gemini Spectroscopy of Supernovae from the Supernova Legacy Survey:
  Improving High-Redshift Supernova Selection and Classification.*
  The Astrophysical Journal, **634**, 1190–1201.
  [DOI: 10.1086/497119](https://doi.org/10.1086/497119).

## Examples informing the acknowledgement

These astronomy projects provide useful examples of crediting software and
describing AI contributions. They are references for the acknowledgement style.

- **TelescopeML (2024):** Gharib-Nezhad and colleagues acknowledge ChatGPT 3.5
  for helping proofread functions. Their paper separately credits the scientific
  libraries on which the package depends. See the acknowledgements on page 4 of
  the [JOSS paper](https://joss.theoj.org/papers/10.21105/joss.06346.pdf).
- **dfcosmic:** the Dragonfly team's
  [AI usage disclosure](https://github.com/DragonflyTelescope/dfcosmic/blob/master/paper.md#ai-usage-disclosure)
  names the tools, distinguishes their coding and testing contributions, and
  describes the authors' review. This motivates a specific account of tasks
  rather than a one-line model credit; Spectypus makes only the review and
  validation claims supported by its own records.
- **Astropy:** its
  [acknowledgement guide](https://www.astropy.org/acknowledging.html) provides
  suggested wording and paper citations, with a version-specific citation
  available from the package. This informs the separate publication guidance
  above for crediting the scientific software actually used.

References and examples checked on 2026-11-05 against the original project
pages, journal records and NGSF announcement.

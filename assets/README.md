# Spectypus visual assets

- `spectypus-logo.png`: website/README wordmark; 2172 × 724 RGBA PNG with
  real transparency. Generated using the built-in image generation tool.
  The brighter azure-blue lettering is visible on dark backgrounds; the website
  uses the transparent asset directly. The spectrum-shaped platypus and supernova star
  represent many spectra contributing to one object-level interpretation.
- `workflow.svg`: editable, deterministic workflow diagram. Its labels describe
  the current classification pipeline, starting with already reduced spectra.
  The two engine branches are logical alternatives, not concurrent execution.

The source-distribution manifest includes these assets. Keep implementation and
scientific contracts in `docs/USAGE.md`, not in this asset record.

- `python.svg` and `license.svg`: static badges for the package's declared
  Python floor and existing GPLv3 license.
- `ci-build.svg`, `ci-tests.svg`, `ci-coverage.svg`: automatically generated
  from trusted default-branch GitHub Actions reports, with source SHA/run URLs inside the SVG.
  Do not hand-edit metric values. These remain private with the repository;
  no external badge endpoint is used. See [CI scope](../docs/USAGE.md#continuous-verification).

## Logo generation prompt

Use case: logo-brand. Create a polished, distinctive logo for Spectypus, a scientific Python tool that takes batches of already reduced supernova spectra, compares each against multiple template-matching classifiers, and combines evidence across observing epochs for each supernova. Asset: production-ready transparent PNG logo for a website header and GitHub README. Horizontal brand lockup with a compact symbol on the left and the exact word 'Spectypus' on the right in a refined, highly legible geometric sans-serif wordmark. Symbol: a clever minimal platypus-inspired silhouette, recognizable by its broad bill, whose body is formed by three clean spectral curves with asymmetric peaks and absorption troughs; the traces converge toward a small four-point supernova star, suggesting many spectra contributing to one interpretation. Scientific, welcoming, confident and restrained; flat vector-like shapes and smooth precise edges, excellent small-scale legibility. Navy blue primary outlines and wordmark, teal and warm coral spectral accents. No gradients, no photorealism, no 3D effects, no shadows, no mascots with human features, no equations, no extra words, no arrows or flowchart boxes. Balanced compact composition, intentional negative space, no cropped content. The background must be truly transparent with clean alpha, not a checkerboard. This is a logo rather than a detailed infographic.

## 2026-11-01 colour edit

Edited with the built-in image-generation tool, preserving the original design
and transparency. Prompt: change only dark navy outlines, bill, feet and wordmark
to brighter azure blue near `#58A6E7`; preserve the exact Spectypus lettering,
platypus spectrum silhouette, coral star and teal/coral traces; no background or
new elements. The original version remains in Git history.

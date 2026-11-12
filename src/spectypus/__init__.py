"""Spectypus: traceable classification evidence across spectra and engines."""

__version__ = "0.2.1"

from .pipeline import make_plan, run_batch, summarize_output

__all__ = ["make_plan", "run_batch", "summarize_output", "__version__"]

"""Conservative versioned aliases, retaining native class and subtype verbatim."""

TAXONOMY_VERSION = "spectypus-taxonomy/2"

_ALIASES = {
    "Ia": ["Ia", "Ia-norm", "Ia norm", "Ia-pec", "Ia 91T-like", "Ia 91bg-like",
           "Ia 99aa-like", "Ia 02es-like", "Ia-02cx like", "Ia-02cx-like", "Ia-rapid",
           "Ia-91T", "Ia-91bg", "Ia-99aa", "Ia-02cx", "super_chandra"],
    "Ia-CSM": ["Ia-CSM", "Ia-CSM-(ambigious)"],
    "Ib": ["Ib", "Ib-norm", "Ib-pec"],
    "Ic": ["Ic", "Ic-norm", "Ic-pec"],
    "Ic-BL": ["Ic-BL", "Ic-broad"],
    "II": ["II", "II-norm", "IIP", "II-P", "IIL", "II-L", "II-pec", "II-flash"],
    "IIb": ["IIb", "IIb-flash"], "IIn": ["IIn"], "Ibn": ["Ibn"],
    "SLSN-I": ["SLSN-I", "SLSN I", "SLSN-Ib"],
    "SLSN-II": ["SLSN-II", "SLSN II", "SLSN-IIn", "SLSN-IIb"],
    "TDE": ["TDE", "TDE H", "TDE He", "TDE H+He"],
    "FBOT": ["FBOT"], "ILRT": ["ILRT"], "SN-impostor": ["SN - Imposter", "SN-impostor"],
    "Ca-rich": ["Ca-Ia", "Ca-Ib", "Ca-rich"],
}
LOOKUP = {alias.casefold(): label for label, aliases in _ALIASES.items() for alias in aliases}


def normalize_class(native: str, subtype: str = "") -> str:
    """Map only enumerated labels. Unknown labels abstain in combined support."""
    subtype_class = LOOKUP.get(subtype.strip().casefold(), "")
    native_class = LOOKUP.get(native.strip().casefold(), "")
    # SAGE stores the broad family and explicit hydrogen subtype separately.
    # An untyped SLSN (or an unrelated subtype) must still abstain.
    if native.strip().casefold() == "slsn" and subtype_class in {"SLSN-I", "SLSN-II"}:
        return subtype_class
    # A recognized subtype can refine a generic native class, never overwrite
    # a different physical family (e.g. SLSN-I with an Ic-looking subtype).
    refinements = {"Ia": {"Ia", "Ia-CSM", "Ca-rich"}, "Ib": {"Ib", "Ibn", "Ca-rich"},
                   "Ic": {"Ic", "Ic-BL", "Ca-rich"}, "II": {"II", "IIb", "IIn"}}
    if subtype_class in refinements.get(native_class, set()):
        return subtype_class
    return native_class

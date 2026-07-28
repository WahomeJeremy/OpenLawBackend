"""ELC litigation lookup + sheet-sync helpers.

The sheet's identifier column is a free-text, semicolon-separated list of
Title/Plot/Certificate/Allotment/Deed-Plan numbers, often prefixed with a
human-entered label ("Title LR ...", "L.R. No. ...", "Plot No. ..."). We
strip those labels before running the same normalize_parcel_id() used across
ndungu/conversions, so a plain parcel search matches regardless of how the
form respondent phrased the identifier.
"""
import re

from ndungu.models import normalize_parcel_id

from .models import ElcCase

# Public CSV export of the "INPUT FORM 1 (Responses)" Google Sheet -- no auth
# needed, sheet is shared as "anyone with the link can view". The workbook has
# two response tabs (both real, independent case logs -- not a duplicate/
# superseded pair): "Form Responses 1" (~6,640 rows, the bulk of the data)
# and "Form Responses 2" (~239 rows, a separate ongoing log). Sync merges
# both into the same ElcCase table, keyed on case_citation.
SHEET_ID = "1fRkXfaXs6vQl3BeuQHIpgEoIUGlWq5GPnyYa3iByqUE"
_GVIZ_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet="
SHEET_EXPORT_URLS = [
    _GVIZ_URL + "Form%20Responses%201",
    _GVIZ_URL + "Form%20Responses%202",
]

_LABEL_PREFIX = re.compile(
    r"^\s*(?:"
    r"title\s+deed|title\s+lr|title\s+no\.?|title|"
    r"land\s+reference\s+numbers?|land\s+reference\s+no\.?|land\s+reference|"
    r"land\s+parcel\s+numbers?|land\s+parcel\s+no\.?|land\s+parcel|"
    r"land\s+no\.?|"
    r"plot\s+numbers?|plot\s+no\.?|plot|"
    r"parcel\s+no\.?|parcel|"
    r"l\.?r\.?\s*no\.?|l\.?r\.?|"
    r"certificate\s+no\.?|allotment\s+no\.?|deed\s+plan\s+no\.?|"
    r"numbers?|no\.?"
    r")\s*",
    re.I,
)
_NONE_RE = re.compile(r"^\"?none\"?$", re.I)

DISCLAIMER = (
    "This parcel is named in an Environment and Land Court (ELC) case "
    "sourced from publicly filed judgments/rulings. This is reference "
    "information only -- it is not an encumbrance finding."
)


def split_identifiers(raw_cell):
    """Split the sheet's identifier cell into cleaned (raw, normalized)
    pairs, dropping blanks and 'NONE' placeholders."""
    out = []
    for piece in (raw_cell or "").split(";"):
        piece = piece.strip().strip('"').strip()
        if not piece or _NONE_RE.match(piece):
            continue
        # Some cells stack labels ("L.R No. Number 12337/6") -- strip
        # leading labels repeatedly until nothing more comes off.
        cleaned = piece
        while True:
            stripped = _LABEL_PREFIX.sub("", cleaned).strip()
            if stripped == cleaned:
                break
            cleaned = stripped
        if not cleaned:
            continue
        normalized = normalize_parcel_id(cleaned)
        if normalized:
            out.append((piece, normalized))
    return out


def _citation_payload(case):
    return {
        "case_citation": case.case_citation,
        "url_link": case.url_link,
        "court_station": case.court_station,
        "judgment_date": case.judgment_date,
        "action": case.action,
        "parties": case.parties,
        "outcome_status": case.outcome_status,
    }


def find_litigation(raw_query):
    """Search ELC cases citing this parcel (exact normalized match on any of
    its listed identifiers). Returns a payload dict with `matches` +
    `disclaimer`, or None if nothing matched."""
    q = normalize_parcel_id(raw_query)
    if not q:
        return None

    cases = (
        ElcCase.objects.filter(identifiers__normalized_identifier=q)
        .distinct()
        .order_by("-synced_at")
    )
    matches = [_citation_payload(c) for c in cases]
    if not matches:
        return None
    return {"disclaimer": DISCLAIMER, "matches": matches}

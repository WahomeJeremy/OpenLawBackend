"""ELC litigation lookup + sheet-sync helpers.

The sheet's identifier column is a free-text, semicolon-separated list of
Title/Plot/Certificate/Allotment/Deed-Plan numbers, often prefixed with a
human-entered label ("Title LR ...", "L.R. No. ...", "Plot No. ..."). We
strip those labels before running the same normalize_parcel_id() used across
ndungu/conversions, so a plain parcel search matches regardless of how the
form respondent phrased the identifier.
"""
import logging
import re
import uuid

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from ndungu.models import normalize_parcel_id

from .models import ElcCase, ElcCaseIdentifier, ManualReviewRequest

logger = logging.getLogger(__name__)

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
# County each tab covers, in the same order as SHEET_EXPORT_URLS.
SHEET_COUNTIES = ["Nairobi", "Kajiado"]

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


_MONTHS = ("January February March April May June July August "
           "September October November December").split()


def format_decision_date(raw):
    """Tidy the sheet's free-text judgment date to '19 February 2026'.

    Most cells already read '19 February 2026'. A few are 'M/D/YYYY'; those are
    only converted when one half is >12 (so the order is unambiguous) -- an
    ambiguous '3/4/2026' is left exactly as entered rather than guessed. A cell
    that holds a URL (the sheet has a few shifted columns) is blanked.
    """
    raw = re.sub(r"\s+", " ", (raw or "").replace("\xa0", " ")).strip()
    if raw.lower().startswith("http"):
        return ""
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw)
    if m:
        a, b, year = int(m[1]), int(m[2]), m[3]
        if b > 12 >= a:
            return f"{b} {_MONTHS[a - 1]} {year}"
        if a > 12 >= b:
            return f"{a} {_MONTHS[b - 1]} {year}"
    return raw


def _citation_payload(case, matched_identifier=""):
    return {
        "case_citation": case.case_citation,
        "matched_identifier": matched_identifier,
        "url_link": case.url_link,
        "county": case.county,
        "court_station": case.court_station,
        "location_details": case.location_details,
        "judgment_date": format_decision_date(case.judgment_date),
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
    matches = []
    for c in cases:
        ident = next((i.raw_identifier for i in c.identifiers.all()
                      if i.normalized_identifier == q), "")
        matches.append(_citation_payload(c, ident))
    if not matches:
        return None
    return {"disclaimer": DISCLAIMER, "matches": matches}


# --------------------------------------------------------------------------- #
#  Manual review workflow
# --------------------------------------------------------------------------- #
def active_review(token, parcel_query=None):
    """The completed, certificate-bearing review for this access token (None if
    unknown, still pending, parcel could not be located, or -- when given --
    it was for a different parcel than `parcel_query`)."""
    req = ManualReviewRequest.objects.filter(
        access_token=token or "", status=ManualReviewRequest.STATUS_DONE,
    ).exclude(outcome=ManualReviewRequest.OUTCOME_NOT_LOCATED).first()
    if req and parcel_query is not None and \
            normalize_parcel_id(req.parcel_id) != normalize_parcel_id(parcel_query):
        return None
    return req


def review_payload(req):
    """What the app's review-result page (and the PDF) needs about a review."""
    reviewed = timezone.localtime(req.reviewed_at) if req.reviewed_at else None
    return {
        "status": req.status,
        "outcome": req.outcome,
        "parcel_id": req.parcel_id,
        "certificate_reference": req.certificate_reference,
        "review_reference": req.review_reference,
        "reviewed_at": reviewed.isoformat() if reviewed else None,
        "reviewed_display": f"{reviewed:%d %b %Y}" if reviewed else "",
        "case_count": req.cases.count(),
    }


def complete_review(req):
    """Finalise a review once staff have recorded the outcome: link any cases
    they attached to the reviewed parcel (so ordinary searches find them too),
    then stamp the reference/date and close the request."""
    normalized = normalize_parcel_id(req.parcel_id)
    for case in req.cases.all():
        ElcCaseIdentifier.objects.get_or_create(
            case=case, normalized_identifier=normalized,
            defaults={"raw_identifier": req.parcel_id},
        )
    if not req.review_reference:
        req.review_reference = f"MR-{timezone.localtime():%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"
    if not req.reviewed_at:
        req.reviewed_at = timezone.now()
    req.status = ManualReviewRequest.STATUS_DONE
    req.save(update_fields=["review_reference", "reviewed_at", "status"])


def review_result_url(req):
    base = getattr(settings, "MANUAL_REVIEW_RESULT_URL", "https://legal.ke/review")
    return f"{base}?token={req.access_token}"


def original_search_summary(req):
    """What the user actually searched, from the audit ledger entry their
    certificate reference points to. '' when the reference is blank/unknown."""
    from ndungu.models import CertificateLog

    log = CertificateLog.objects.filter(certificate_reference=req.certificate_reference).first() \
        if req.certificate_reference else None
    if log is None:
        return ""
    when = timezone.localtime(log.created_at)
    return (
        f'Typed: "{log.searched_parcel_id}" | Dataset: {log.get_dataset_source_display()} | '
        f"Result: {log.get_status_display()} ({log.results_count} records) | "
        f"Searched: {when:%d %b %Y, %H:%M}"
    )


def notify_support_of_request(req):
    """Tell the support inbox a new manual review is waiting."""
    try:
        send_mail(
            subject=f"Manual review requested: {req.parcel_id}",
            message=(
                f"Parcel: {req.parcel_id}\n"
                f"Certificate reference: {req.certificate_reference or '-'}\n"
                f"Original search: {original_search_summary(req) or '-'}\n"
                f"Contact: {req.contact_email or '-'} / {req.contact_phone or '-'}\n"
                f"Notes: {req.notes or '-'}\n\n"
                "Record the outcome in the admin (Litigation > Manual review requests)."
            ),
            from_email=None, recipient_list=[settings.SUPPORT_EMAIL],
        )
    except Exception:  # never fail the user's request over an email problem
        logger.exception("Could not email support about manual review #%s", req.pk)


def notify_user_review_ready(req):
    """Email the requester their link back to the app. Returns True if sent.
    A phone-only requester can't be emailed; staff follow up from the admin."""
    if not req.contact_email:
        return False
    outcome_line = {
        ManualReviewRequest.OUTCOME_CLEAR: "No litigation record was found for your parcel.",
        ManualReviewRequest.OUTCOME_LITIGATION: "Litigation records were found for your parcel.",
        ManualReviewRequest.OUTCOME_NOT_LOCATED: "We could not locate your parcel in the records.",
    }.get(req.outcome, "")
    try:
        sent = send_mail(
            subject=f"Your Landledger manual review is ready ({req.parcel_id})",
            message=(
                f"Your manual review of {req.parcel_id} is complete "
                f"(ref. {req.review_reference}).\n{outcome_line}\n\n"
                f"View the result and download your certificate:\n{review_result_url(req)}\n"
            ),
            from_email=None, recipient_list=[req.contact_email],
        )
    except Exception:
        logger.exception("Could not email manual review #%s result to the requester", req.pk)
        return False
    if sent:
        req.notified_at = timezone.now()
        req.save(update_fields=["notified_at"])
    return bool(sent)

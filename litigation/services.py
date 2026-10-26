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

from ndungu.models import is_parcel_like, normalize_parcel_id

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


# An identifier column is meant to hold ONE parcel per ';'-separated item, but many
# cells list several parcels joined with commas, "and" or "&" instead. Stored whole,
# such an item can never match a search (and a long one overflows the 255-character
# column on PostgreSQL), so the individual parcel numbers are pulled out of it.
MAX_IDENTIFIER_LEN = 255
_SEPARATOR = re.compile(r",|\band\b|&", re.I)
_PARCEL_NUMBER = re.compile(
    r"(?:[A-Za-z]+\s*[/ ]\s*)?Block\s*\d+(?:\s*/\s*\d+)+"                           # Nairobi/Block 37/283, Nairobi Block 37/283
    r"|[A-Za-z]{3,}(?:\s*/\s*[A-Za-z]{3,})+\s*/\s*\d+[A-Za-z]?"                         # Ngong/Ngong/1445
    r"|\d+[A-Za-z]?(?:\s*/\s*(?:\d+[A-Za-z]?|[IVX]{1,5}))+"                            # 97/5262, 209/6002/7, 36/VII/637
    r"|\b\d{4,}\b"                                                                      # a plain LR number: 12826
)


def _expand_multi(piece):
    """Individual parcel numbers found in a multi-parcel (or oversized) cell item."""
    seen, out = set(), []
    for m in _PARCEL_NUMBER.finditer(piece):
        token = re.sub(r"\s*/\s*", "/", re.sub(r"\s+", " ", m.group(0))).strip()  # "97/ 5264" -> "97/5264"
        token = re.sub(r"^([A-Za-z]+)\s+(Block)", r"\1/\2", token)             # "Nairobi Block" -> "Nairobi/Block"
        token = re.sub(r"Block(?=\d)", "Block ", token)                          # "Block126/749" -> "Block 126/749"
        if token not in seen and len(token) <= MAX_IDENTIFIER_LEN:
            seen.add(token)
            out.append(token)
    return out


def split_identifiers(raw_cell):
    """Split the sheet's identifier cell into cleaned (raw, normalized)
    pairs, dropping blanks and 'NONE' placeholders."""
    out = []
    for piece in (raw_cell or "").split(";"):
        piece = piece.strip().strip('"').strip()
        if not piece or _NONE_RE.match(piece):
            continue
        if len(piece) > MAX_IDENTIFIER_LEN or _SEPARATOR.search(piece):
            tokens = _expand_multi(piece)
            if tokens or len(piece) > MAX_IDENTIFIER_LEN:
                for token in tokens:
                    normalized = normalize_parcel_id(token)
                    if normalized:
                        out.append((token, normalized))
                continue
            # a separator but no recognisable parcel number: keep the item as written
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


# Name search: how many cases one name search will list, and which words don't count.
MAX_NAME_MATCHES = 25
_NAME_STOPWORDS = {"the", "of", "and", "for", "in", "on", "at", "to", "ltd", "limited", "co", "company", "inc"}


def _name_tokens(term):
    tokens = [t for t in re.split(r"[^a-z0-9']+", (term or "").lower()) if len(t) >= 2 and t not in _NAME_STOPWORDS]
    # a lone word must be a real word: 'nssf' or 'karura' yes, 'ab' no
    return tokens if tokens and (len(tokens) > 1 or len(tokens[0]) >= 4) else []


def _case_names_party(case, tokens):
    """True when ONE party of the case contains every word (so 'Mary' in one party
    and 'Kaittany' in another does not count)."""
    parties = [p.lower() for p in re.split(r";", case.parties or "") if p.strip()]
    if not parties:  # no parties recorded: use the two sides of the case title
        title = re.split(r"\[\d{4}\]", case.case_citation)[0]
        parties = [p.lower() for p in re.split(r"\s+v\s+|;|&", title) if p.strip()]
    return any(all(t in p for t in tokens) for p in parties)


def _find_by_party(raw_query):
    """Cases in which one party's name contains EVERY word of a typed name.

    Matching is by name only, so it can pick up a different person who shares it;
    the payload says so (`match_basis`) and the certificate repeats the caution."""
    tokens = _name_tokens(raw_query)
    if not tokens:
        return None
    from django.db.models import Q

    qs = ElcCase.objects.all()
    for t in tokens:
        qs = qs.filter(Q(parties__icontains=t) | Q(case_citation__icontains=t))
    hits = [c for c in qs.order_by("-synced_at")[:3000] if _case_names_party(c, tokens)]
    if not hits:
        return None
    return {
        "disclaimer": DISCLAIMER,
        "matches": [_citation_payload(c) for c in hits[:MAX_NAME_MATCHES]],
        "match_basis": "parties",
        "total": len(hits),
        "truncated": len(hits) > MAX_NAME_MATCHES,
    }


def find_litigation(raw_query):
    """Search ELC cases for this search term.

    A parcel number is matched exactly against each case's listed identifiers. A
    name or entity that matches no identifier is matched against the cases'
    parties. Returns a payload dict (`matches`, `disclaimer`, `match_basis`,
    `total`, `truncated`), or None if nothing matched."""
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
    if matches:
        return {"disclaimer": DISCLAIMER, "matches": matches, "match_basis": "identifier",
                "total": len(matches), "truncated": False}
    if not is_parcel_like(raw_query):
        return _find_by_party(raw_query)
    return None


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

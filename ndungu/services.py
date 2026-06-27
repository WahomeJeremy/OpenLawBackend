"""Search + certificate engine for the Ndung'u Report (PRD section 2-3).

Pure functions that build the structured certificate payloads. Endpoints in
views.py call these and persist the audit ledger entry.
"""
import uuid
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.db.models import Q

from .models import CertificateLog, Finding, Parcel, normalize_parcel_id

EAT = timezone(timedelta(hours=3))  # East Africa Time (UTC+3)


def scope_statement():
    """Live scope line for the NIL certificate (real record count)."""
    count = Finding.objects.count()
    return (
        f"Searched {count:,} records across the Ndung'u Report "
        "(2004 Commission of Inquiry) — flagged parcels, schools, "
        "corporations and other entities."
    )
DISCLAIMER = (
    "Based on the 2004 Ndung'u Report (Commission of Inquiry into the "
    "Illegal/Irregular Allocation of Public Land). For historical due-diligence "
    "only — not a legal title or a substitute for an official Ministry of Lands "
    "Registry search."
)
_ROMAN = {"1": "I", "2": "II", "3": "III"}


def now_eat():
    return datetime.now(EAT)


def generate_reference():
    """Unique alphanumeric verification string, e.g. NDR-20260625-1A2B3C4D."""
    return f"NDR-{now_eat():%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"


def _roman_volumes(volumes):
    return [_ROMAN.get(v, v) for v in volumes]


def _citation(f):
    vol = _ROMAN.get(f.source_volume, f.source_volume or "?")
    page = f.source_page or "?"
    cite = f"Ndungu Report Vol {vol} Page {page}"
    if f.flag_source_csv:
        cite += f" ({f.flag_source_csv.replace('.csv', '').replace('_', ' ')})"
    return cite


def _aggregate_recommendation(findings):
    """Categorical action (e.g. REVOKE) from the findings' recommendations."""
    seen = []
    for f in findings:
        rec = (f.commission_recommendation or "").strip()
        if rec and rec not in seen:
            seen.append(rec)
    if not seen:
        return ""
    # Leading verb of the first recommendation, capitalised as the action.
    return seen[0].split(",")[0].split(";")[0].strip().upper()


# --------------------------------------------------------------------------- #
#  Search
# --------------------------------------------------------------------------- #
def run_search(raw_query):
    """Exact (normalized) -> disambiguation -> suggestion -> none.

    Returns {"match_type": ..., "parcel"/"parcels": ...}.
    """
    raw = (raw_query or "").strip()
    nq = normalize_parcel_id(raw)

    exact = Parcel.objects.filter(
        Q(normalized_lr=nq) | Q(parcel_id_clean__iexact=raw)
    )
    n = exact.count()
    if n == 1:
        return {"match_type": "exact", "parcel": exact.first()}
    if n > 1:
        return {"match_type": "multiple", "parcels": list(exact[:25])}

    # Fuzzy: same numeric stem with broader naming context (PRD 2.1).
    suggestions = []
    if nq:
        suggestions = list(
            Parcel.objects.filter(normalized_lr__startswith=nq)
            .exclude(normalized_lr=nq)[:10]
        )
    # Name / location fallback when no id-style match.
    if not suggestions and len(raw) >= 3:
        suggestions = list(
            Parcel.objects.filter(
                Q(parcel_display__icontains=raw)
                | Q(findings__current_holder__icontains=raw)
                | Q(findings__location__icontains=raw)
            ).distinct()[:10]
        )
    if suggestions:
        return {"match_type": "suggestions", "parcels": suggestions}
    return {"match_type": "none"}


def _clean_label(s):
    """Strip whitespace and stray leading/trailing commas from a display value."""
    return (s or "").strip().strip(",").strip()


def friendly_label(parcel, findings=None):
    """A human-readable label for a parcel — never the internal synthetic key
    (e.g. 'narrative::forest_018'). Falls back through display -> holder ->
    location -> category so users always see something meaningful."""
    label = _clean_label(parcel.parcel_display)
    if label:
        return label
    if "::" in parcel.parcel_id_clean:  # narrative / entity synthetic key
        fs = findings if findings is not None else list(parcel.findings.all())
        f = fs[0] if fs else None
        if f:
            return (_clean_label(f.current_holder) or _clean_label(f.location)
                    or f.flag_category.replace("_", " ").title())
        return "Unidentified record"
    return parcel.parcel_id_clean


def suggestion_payload(parcel):
    findings = list(parcel.findings.all())
    # A short context line so name-based (entity) suggestions are meaningful.
    first = findings[0] if findings else None
    context = ""
    if first:
        context = first.current_holder or first.location or first.flag_category
    return {
        "parcel_id": parcel.parcel_id_clean,
        "display": friendly_label(parcel, findings),
        "type": parcel.parcel_id_type.replace("_", " "),
        "context": _clean_label(context),
        "records": len(findings),
        "volumes": _roman_volumes(
            sorted({f.source_volume for f in findings if f.source_volume})
        ),
    }


# --------------------------------------------------------------------------- #
#  Certificate builders
# --------------------------------------------------------------------------- #
def _dedupe_quotes(findings):
    """One quote per distinct recommendation text."""
    seen, quotes = set(), []
    for f in findings:
        text = f.commission_recommendation or f.flag_reason
        if not text or text in seen:
            continue
        seen.add(text)
        quotes.append({"citation": _citation(f), "quote": text})
    return quotes


def _dedupe(findings):
    """Collapse exact-duplicate findings (same content) to a single entry."""
    seen, unique = set(), []
    for f in findings:
        sig = (f.flag_category, f.flag_reason, f.current_holder, f.prior_party,
               f.source_volume, f.source_page, f.price_kshs, f.transaction_date)
        if sig in seen:
            continue
        seen.add(sig)
        unique.append(f)
    return unique


def build_certificate(parcel, searched_id):
    """Progressive-disclosure encumbrance certificate (PRD 2.2 / 3.2)."""
    findings = _dedupe(sorted(
        parcel.findings.all(),
        key=lambda f: (f.source_volume or "", f.source_page or ""),
    ))
    volumes = sorted({f.source_volume for f in findings if f.source_volume})
    roman = _roman_volumes(volumes)

    # Synthetic keys (narrative::… / school::…) are not human ids — show a
    # friendly label instead of the raw key.
    shown_id = (friendly_label(parcel, findings)
                if "::" in parcel.parcel_id_clean else searched_id)

    reserved = next((f.reserved_use for f in findings if f.reserved_use), "")
    area = next((f.area for f in findings if f.area), "")
    location = next((f.location for f in findings if f.location), "")
    owner = ""
    for f in reversed(findings):  # owner at latest volume
        if f.current_holder:
            owner = f.current_holder
            break

    timeline = []
    for f in findings:
        entry = {
            "volume": f.source_volume,
            "page": f.source_page,
            "citation": _citation(f),
            "flag_category": f.flag_category,
            "reserved_use": f.reserved_use,
            "current_use": f.current_use,
            "allocating_authority": f.allocating_authority,
            "prior_party": f.prior_party,
            "current_holder": f.current_holder,
            "flag_reason": f.flag_reason,
        }
        if f.price_kshs or f.transaction_date:
            entry["onward_sale"] = {
                "vendor": f.prior_party,
                "buyer": f.current_holder,
                "price_kshs": f.price_kshs,
                "date": f.transaction_date,
            }
        timeline.append(entry)

    summary = (
        f"{len(findings)} "
        f"{'entry' if len(findings) == 1 else 'entries'} found across "
        f"Volume {' and '.join(roman) if roman else 'I-III'}"
    )

    return {
        "status": "encumbrance_found",
        "overview": {
            "banner": "Encumbrance Found",
            "parcel": shown_id,
            "records_matched": len(findings),
            "volumes": roman,
            "summary": summary,
        },
        "tier_a_summary": {
            "searched_id": shown_id,
            "matched_parcel_id": parcel.parcel_id_clean,
            "location": location,
            "reserved_purpose": reserved,
            "area_hectares": area,
            "current_owner": owner,
            "commission_recommendation": _aggregate_recommendation(findings),
        },
        "tier_b_timeline": timeline,
        "tier_c_recommendation": {
            "action": _aggregate_recommendation(findings),
            "raw_quotes": _dedupe_quotes(findings),
        },
        "disclaimer": DISCLAIMER,
    }


def build_nil_certificate(searched_id):
    """NIL certificate with the PRD 3.1 mandatory legal phrasing."""
    date_str = f"{now_eat():%d/%m/%Y}"
    return {
        "status": "no_encumbrance",
        "overview": {
            "banner": "No Encumbrance Recorded",
            "parcel": searched_id,
            "records_matched": 0,
        },
        "legal_statement": (
            f"No encumbrance recorded in the NDUNGU REPORT (Volume I-III) "
            f"as at {date_str} against parcel {searched_id}"
        ),
        "search_scope": scope_statement(),
        "disclaimer": DISCLAIMER,
    }


# --------------------------------------------------------------------------- #
#  Audit ledger
# --------------------------------------------------------------------------- #
def log_search(searched_id, normalized, results_count, status, parcel=None):
    """Write the immutable ledger entry and return its certificate reference."""
    ref = generate_reference()
    CertificateLog.objects.create(
        certificate_reference=ref,
        searched_parcel_id=searched_id,
        normalized_query=normalized,
        results_count=results_count,
        status=status,
        matched_parcel=parcel,
    )
    return ref


# --------------------------------------------------------------------------- #
#  PDF rendering (WeasyPrint)
# --------------------------------------------------------------------------- #
def _content_bottom_px(page):
    """Bottom Y (CSS px) of the real content on a page, ignoring the fixed
    watermark and the page margin boxes (e.g. the footer)."""
    root = None
    for child in page._page_box.children:
        if getattr(child, "element_tag", None) == "html":
            root = child
            break
    if root is None:
        return page._page_box.height

    def deepest(box):
        try:
            if box.style["position"] == "fixed":   # skip the watermark
                return 0.0
        except (KeyError, TypeError, AttributeError):
            pass
        bottom = (getattr(box, "position_y", 0) or 0) + (getattr(box, "height", 0) or 0)
        for child in getattr(box, "children", ()) or ():
            bottom = max(bottom, deepest(child))
        return bottom

    return deepest(root)


def verify_url(reference):
    """Public verify-page URL the certificate QR resolves to."""
    base = getattr(settings, "NDUNGU_VERIFY_URL", "https://legal.ke/verify")
    return f"{base}?ref={reference}"


def qr_data_uri(data):
    """Return a base64 PNG data URI of a QR code for the given data."""
    import base64
    import io

    import segno

    buff = io.BytesIO()
    segno.make(data, error="m").save(buff, kind="png", scale=3, border=1)
    return "data:image/png;base64," + base64.b64encode(buff.getvalue()).decode()


def render_certificate_pdf(cert, meta):
    """Render a certificate to a content-height PDF (no trailing whitespace).

    Lays the certificate out on one very tall page, measures where the content
    actually ends, then re-renders on a page sized exactly to that content.
    """
    from django.template.loader import render_to_string
    from weasyprint import CSS, HTML  # lazy import: native libs only needed here

    html = render_to_string("ndungu/certificate.html", {"cert": cert, "meta": meta})

    measure = CSS(string="@page { size: 210mm 6000mm; }")
    page = HTML(string=html).render(stylesheets=[measure]).pages[0]
    content_mm = _content_bottom_px(page) / 96 * 25.4
    height_mm = max(content_mm + 12 + 4, 90)  # + bottom margin + slack

    fit = CSS(string=f"@page {{ size: 210mm {height_mm:.0f}mm; }}")
    return HTML(string=html).write_pdf(stylesheets=[fit])

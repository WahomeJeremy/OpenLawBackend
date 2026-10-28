"""Search + certificate engine for the Ndung'u Report (PRD section 2-3).

Pure functions that build the structured certificate payloads. Endpoints in
views.py call these and persist the audit ledger entry.
"""
import os
import re
import uuid
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.db.models import Q

from .models import CertificateLog, Finding, Parcel, is_parcel_like, normalize_parcel_id

EAT = timezone(timedelta(hours=3))  # East Africa Time (UTC+3)


def scope_statement():
    """Scope line for the NIL certificate. No record count: the index grows."""
    return (
        "Searched records across the Ndung'u Report "
        "(2004 Commission of Inquiry), covering flagged parcels, schools, "
        "corporations and other entities indexed by Landledger."
    )


DISCLAIMER = (
    "Based on the 2004 Ndung'u Report (Commission of Inquiry into the "
    "Illegal/Irregular Allocation of Public Land). For historical due diligence "
    "only. Not a legal title or a substitute for an official Ministry of Lands "
    "Registry search. It does not constitute legal advice."
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
# A single Ndung'u finding is indexed under ONE canonical key, but the source
# routinely lists several registrable references for the same plot, e.g.
# "L.R. 19095 Original 12661 Cf 157469". Only the primary LR (19095) becomes a
# Parcel key; the cross-reference (Cf) and "Original" numbers live only in
# Finding.parcel_id_raw. A search on any of those must still resolve to the plot,
# so we scan parcel_id_raw for the query's identifier tokens.
#
# A token is a slash-style ref (209/11642, 12661/82) or a standalone 4-6 digit
# number. Short/bare numbers are intentionally excluded — they are handled by the
# normalized_lr path and would produce noisy substring hits here.
_ID_TOKEN = re.compile(r"\b\d{1,5}/\d{2,6}[A-Za-z]?(?:/\d+[A-Za-z]?)*\b|\b\d{4,6}\b")


def _identifier_tokens(raw):
    return {m.group(0) for m in _ID_TOKEN.finditer(raw or "")}


def _parcels_by_alternate_id(raw):
    """Distinct parcels reachable via an alternate identifier (Cf / Original /
    secondary LR) embedded in a finding's parcel_id_raw. Every identifier token in
    the query must appear (word-bounded) in the SAME finding, so a multi-part query
    like "LR 19095 original 12661" resolves precisely rather than fanning out."""
    tokens = _identifier_tokens(raw)
    if not tokens:
        return []
    # Boundary via explicit character classes, not \b: PostgreSQL's regex engine
    # (production) reads \b as a backspace, so \b-boundaries silently match nothing.
    # (^|[^0-9/]) ... ([^0-9/]|$) works identically on SQLite and PostgreSQL and
    # keeps a token from matching inside a longer number or slash reference.
    findings = Finding.objects.all()
    for tok in tokens:
        findings = findings.filter(
            parcel_id_raw__iregex=r"(^|[^0-9/])" + re.escape(tok) + r"([^0-9/]|$)")
    return list(Parcel.objects.filter(findings__in=findings).distinct()[:25])
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

    # Alternate identifiers (Cf cross-reference / Original / secondary LR) that the
    # source lists alongside the primary key. A precise id match, so a single hit is
    # treated as exact rather than a mere suggestion.
    alt = _parcels_by_alternate_id(raw)
    if len(alt) == 1:
        return {"match_type": "exact", "parcel": alt[0]}
    if len(alt) > 1:
        return {"match_type": "multiple", "parcels": alt}

    # Fuzzy: same numeric stem with broader naming context (PRD 2.1).
    suggestions = []
    if nq:
        suggestions = list(
            Parcel.objects.filter(normalized_lr__startswith=nq)
            .exclude(normalized_lr=nq)[:10]
        )
    # Name / location fallback when no id-style match: try the whole phrase
    # as one substring first (fast path for well-formed queries).
    if not suggestions and len(raw) >= 3:
        suggestions = list(
            Parcel.objects.filter(
                Q(parcel_display__icontains=raw)
                | Q(findings__current_holder__icontains=raw)
                | Q(findings__location__icontains=raw)
            ).distinct()[:10]
        )
    # A multi-word query that isn't a literal substring (skipped a middle
    # name, words out of order, etc.) shouldn't be brushed off as "not
    # found" -- require every word present somewhere instead, so an
    # incomplete-but-recognizable name still surfaces its match.
    if not suggestions:
        words = [w for w in raw.split() if len(w) >= 2]
        if len(words) >= 2:
            word_q = Q()
            for w in words:
                word_q &= (
                    Q(parcel_display__icontains=w)
                    | Q(findings__current_holder__icontains=w)
                    | Q(findings__location__icontains=w)
                )
            suggestions = list(Parcel.objects.filter(word_q).distinct()[:10])
    if suggestions:
        return {"match_type": "suggestions", "parcels": suggestions}
    return {"match_type": "none"}


def conversion_numbers(conversion_info):
    """Every other LR number this parcel is known by (old <-> new), from the gazetted
    conversion. The Ndung'u report and the ELC log record whichever number was current
    then, so a search by one number must also look under the other."""
    seen, out = set(), []
    for m in (conversion_info or {}).get("matches", []):
        for num in (m["old_lr_no"], m["new_lr_number"]):
            key = normalize_parcel_id(num)
            if key and key not in seen:
                seen.add(key)
                out.append(num)
    return out


def resolve_via_conversion(result, conversion_info):
    """If a search found no exact Ndung'u parcel but the term is one side of a gazetted
    LR conversion, and exactly one parcel carries the other number, use that parcel
    (otherwise 'no encumbrance' would be certified for a parcel that has one)."""
    if result["match_type"] == "exact":
        return result
    parcels = {}
    for num in conversion_numbers(conversion_info):
        r = run_search(num)
        if r["match_type"] == "exact":
            parcels[r["parcel"].pk] = r["parcel"]
    if len(parcels) == 1:
        return {"match_type": "exact", "parcel": next(iter(parcels.values())), "via_conversion": True}
    return result


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


# A labelled registrable reference inside parcel_id_raw: an optional Cf / Original /
# L.R. / I.R. prefix followed by the number (slash ref or 4-6 digit).
_LABELLED_REF = re.compile(
    r"(Cf|Original|Orig|L\.?\s*R\.?|I\.?\s*R\.?)?\.?\s*"
    r"(\d{1,5}/\d{2,6}[A-Za-z]?(?:/\d+[A-Za-z]?)*|\d{4,6})",
    re.I,
)
_REF_LABELS = {"cf": "Cf", "original": "Original", "orig": "Original",
               "lr": "L.R.", "ir": "I.R."}


def _associated_references(findings, shown_id):
    """Other registrable references the Ndung'u source records for the SAME plot —
    the Cf cross-reference, Original, and secondary LR numbers in parcel_id_raw —
    excluding the one already shown. Lets a user who searched by one reference (e.g.
    the Cf number) see the plot's other identifiers."""
    shown = normalize_parcel_id(shown_id)
    seen, refs = set(), []
    for f in findings:
        for label, num in _LABELLED_REF.findall(f.parcel_id_raw or ""):
            norm = normalize_parcel_id(num)
            if not norm or norm == shown or norm in seen:
                continue
            seen.add(norm)
            pretty = _REF_LABELS.get(re.sub(r"[.\s]", "", label).lower(), "")
            refs.append(f"{pretty} {num}".strip())
    return refs


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
    also_recorded_as = _associated_references(findings, shown_id)

    overview = {
        "banner": "Adverse Record Found",
        "parcel": shown_id,
        "records_matched": len(findings),
        "volumes": roman,
        "summary": summary,
    }
    if also_recorded_as:
        overview["also_recorded_as"] = also_recorded_as

    return {
        "status": "encumbrance_found",
        "overview": overview,
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


def elc_nil_statement(searched_id):
    # 'parcel 209/11642' for a parcel number; the name itself for a person,
    # company or place ("Mary Kaittany" is not a parcel).
    subject = search_subject(display_term(searched_id))
    target = f"parcel {searched_id}" if subject["kind"] == "property" else subject["ref"]
    return f"No ELC litigation case recorded against {target}."


def _combined_summary(ndungu_found, elc_found, ndungu_cert, litigation_info):
    parts = []
    if ndungu_found:
        parts.append(ndungu_cert["overview"]["summary"])
    if elc_found:
        n = len(litigation_info["matches"])
        parts.append(f"{n} ELC litigation {'case' if n == 1 else 'cases'} found")
    if not parts:
        return ""
    return " · ".join(parts)


def build_combined_certificate(parcel, litigation_info, shown_id, ndungu_suggestions=0):
    """Combine a (possibly absent) Ndung'u match with (possibly absent) ELC
    litigation into ONE certificate payload -- our encumbrance verdict is now
    Ndung'u OR ELC (LR conversion stays separate, pure reference data).

    ALWAYS returns both a `ndungu` and an `elc` section (each `found` or not,
    with an explicit statement when not), regardless of overall status --
    the frontend uses this to offer a source picker even on a fully NIL
    result. The Ndung'u "not found" text reuses build_nil_certificate's
    mandatory legal phrasing (PRD 3.1), just nested under `ndungu` instead of
    being the whole document.
    """
    ndungu_cert = build_certificate(parcel, shown_id) if parcel is not None else None
    ndungu_found = ndungu_cert is not None
    elc_found = bool(litigation_info)

    overview_parcel = ndungu_cert["overview"]["parcel"] if ndungu_found else shown_id
    overall_status = "encumbrance_found" if (ndungu_found or elc_found) else "no_encumbrance"

    if ndungu_found:
        ndungu_section = {
            "found": True,
            "tier_a_summary": ndungu_cert["tier_a_summary"],
            "tier_b_timeline": ndungu_cert["tier_b_timeline"],
            "tier_c_recommendation": ndungu_cert["tier_c_recommendation"],
            **({"also_recorded_as": ndungu_cert["overview"]["also_recorded_as"]}
               if "also_recorded_as" in ndungu_cert["overview"] else {}),
        }
    else:
        nil = build_nil_certificate(overview_parcel)
        ndungu_section = {
            "found": False,
            "legal_statement": nil["legal_statement"],
            "search_scope": nil["search_scope"],
        }
        if ndungu_suggestions:
            # The term matches several Ndung'u records (e.g. a name). They are not
            # shown on this journey -- only counted, so the ELC result can point
            # the user to them.
            ndungu_section["suggestions"] = ndungu_suggestions

    elc_section = (
        {"found": True, "matches": litigation_info["matches"],
         "disclaimer": litigation_info["disclaimer"],
         "match_basis": litigation_info.get("match_basis", "identifier"),
         "total": litigation_info.get("total", len(litigation_info["matches"])),
         "truncated": litigation_info.get("truncated", False)} if elc_found else
        {"found": False, "nil_statement": elc_nil_statement(overview_parcel)}
    )
    # When the ELC index was last refreshed (the modal's disclaimer dates it, not the search).
    elc_section["index_as_of"] = elc_index_stats()["as_of"]

    return {
        "status": overall_status,
        "overview": {
            "banner": "Adverse Record Found" if overall_status == "encumbrance_found" else "No Adverse Record Found",
            "parcel": overview_parcel,
            "summary": _combined_summary(ndungu_found, elc_found, ndungu_cert, litigation_info),
        },
        "ndungu": ndungu_section,
        "elc": elc_section,
        "disclaimer": DISCLAIMER,
    }


def _statement_target(searched_id):
    """'parcel 2/267' for a parcel number (the PRD's fixed wording is unchanged for
    those); a name, entity or place is quoted instead of being called a parcel."""
    if is_parcel_like(searched_id):
        return f"parcel {searched_id}"
    return search_subject(display_term(searched_id))["ref"]


def build_nil_certificate(searched_id):
    """NIL certificate with the PRD 3.1 mandatory legal phrasing."""
    date_str = f"{now_eat():%d/%m/%Y}"
    return {
        "status": "no_encumbrance",
        "overview": {
            "banner": "No Adverse Record Found",
            "parcel": searched_id,
            "records_matched": 0,
        },
        "legal_statement": (
            f"No encumbrance recorded in the NDUNGU REPORT (Volume I-III) "
            f"as at {date_str} against {_statement_target(searched_id)}"
        ),
        "search_scope": scope_statement(),
        "disclaimer": DISCLAIMER,
    }


# --------------------------------------------------------------------------- #
#  Audit ledger
# --------------------------------------------------------------------------- #
DATASET_SOURCES = ("ndungu", "elc")


def clean_source(raw):
    """Normalise the client's dataset pick; anything unknown means Ndung'u."""
    raw = (raw or "").strip().lower()
    return raw if raw in DATASET_SOURCES else "ndungu"


def source_status(combined, source):
    """Verdict for ONE dataset. The combined payload's `status` is Ndung'u OR
    ELC; a certificate that is exclusively about one dataset must not be
    reported 'found' because of the other."""
    found = combined["elc" if source == "elc" else "ndungu"]["found"]
    return "encumbrance_found" if found else "no_encumbrance"


def log_search(searched_id, normalized, results_count, status, parcel=None,
               dataset_source="ndungu"):
    """Write the immutable ledger entry and return its certificate reference."""
    ref = generate_reference()
    CertificateLog.objects.create(
        certificate_reference=ref,
        searched_parcel_id=searched_id,
        normalized_query=normalized,
        results_count=results_count,
        status=status,
        dataset_source=dataset_source,
        matched_parcel=parcel,
    )
    return ref


# --------------------------------------------------------------------------- #
#  PDF rendering (WeasyPrint)
# --------------------------------------------------------------------------- #
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


def _logo_data_uri():
    """Landledger lockup + tagline for the certificate header ('' if the asset is missing)."""
    import base64

    path = settings.BASE_DIR / "ndungu" / "assets" / "landledger-logo-tagline.png"
    try:
        return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()
    except OSError:
        return ""


def report_pages(timeline):
    """'Vol I, Page 60; Vol II, Page 12' -- the report pages a finding cites."""
    seen = []
    for e in timeline:
        if e.get("volume") and e.get("page"):
            ref = f"Vol {_ROMAN.get(str(e['volume']), e['volume'])}, Page {e['page']}"
            if ref not in seen:
                seen.append(ref)
    return "; ".join(seen)


_NEUTRAL_CITATION = re.compile(r"^(.*?)\s*(\[\d{4}\].*)$", re.S)


def elc_rows(matches):
    """ELC matches prepared for the schedule table: the case title and its
    neutral citation ('[2015] KEELC 728 (KLR)') on separate lines."""
    rows = []
    for m in matches:
        cit = (m.get("case_citation") or "").replace("\xa0", " ").strip()
        mo = _NEUTRAL_CITATION.match(cit)
        title, neutral = (mo.group(1), mo.group(2)) if mo and mo.group(1) else (cit, "")
        rows.append({
            **m,
            "title": title,
            "neutral": neutral,
            "county": m.get("county") or (m.get("court_station") or "").title(),
            "decision_date": m.get("judgment_date", ""),  # already tidied by litigation.services
            "outcome_long": len((m.get("outcome_status") or "").strip()) > LONG_OUTCOME,
            "outcome_lead": _outcome_lead(m.get("outcome_status")),
            "source_display": re.sub(r"^https?://", "", m.get("url_link") or ""),
        })
    return rows


# A long outcome would wrap into a very tall sliver in the narrow table column, so
# the column shows a short lead and the full text is printed across the row below.
LONG_OUTCOME = 140


def _outcome_lead(text, width=70):
    text = " ".join((text or "").split())
    if len(text) <= width:
        return text
    return text[:width].rsplit(" ", 1)[0].rstrip(",;:.") + "\u2026"


def contact_links(reference, topic):
    """Email / WhatsApp / form targets for the 'quote this reference' lines."""
    from urllib.parse import quote

    msg = quote(f"Hello, I'd like to {topic} for certificate {reference}.")
    wa = getattr(settings, "CERTIFICATE_WHATSAPP_URL", "https://wa.me/254180049253")
    return {
        "email": f"mailto:{getattr(settings, 'SUPPORT_EMAIL', '')}?subject={quote('Certificate ' + reference)}",
        "whatsapp": f"{wa}{'&' if '?' in wa else '?'}text={msg}",
        "site": getattr(settings, "CERTIFICATE_SITE_URL", "https://legal.ke"),
    }


def pdf_filename(cert, searched, source):
    """e.g. Ndungu_Report_Search_Certificate_2-267_No_Adverse_Record.pdf"""
    if source == "elc":
        term, kind = searched, ("Litigation_Found" if cert["elc"]["found"] else "No_Record")
        prefix = "Litigation_Search_Certificate"
    else:
        term = cert["overview"]["parcel"]
        kind = "Adverse_Record_Found" if cert["ndungu"]["found"] else "No_Adverse_Record"
        prefix = "Ndungu_Report_Search_Certificate"
    safe = re.sub(r"[^A-Za-z0-9\-]", "", (term or "").strip().replace("/", "-").replace(" ", "")) or "Search"
    return f"{prefix}_{safe}_{kind}.pdf"


def _ensure_fontconfig():
    """macOS only: point fontconfig at the bundled fonts before WeasyPrint loads.

    The stock Homebrew fontconfig on a Mac fails to match many families by name
    (and ignores @font-face), so the certificate would silently fall back to a
    system font. A tiny config that lists the bundled font folder fixes that.
    Linux/Heroku resolve @font-face through fontconfig natively, so this is a
    no-op there, and it never overrides a FONTCONFIG_FILE the user already set.
    """
    import sys

    if sys.platform != "darwin" or os.environ.get("FONTCONFIG_FILE"):
        return
    import tempfile

    fonts = settings.BASE_DIR / "ndungu" / "assets" / "fonts"
    cfg_dir = os.path.join(tempfile.gettempdir(), "landledger-fontconfig")
    os.makedirs(cfg_dir, exist_ok=True)
    conf = os.path.join(cfg_dir, "fonts.conf")
    with open(conf, "w") as fh:
        fh.write(
            '<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd">'
            f"<fontconfig><dir>{fonts}</dir><dir>/System/Library/Fonts</dir>"
            f"<dir>/System/Library/Fonts/Supplemental</dir>"
            f"<cachedir>{os.path.join(cfg_dir, 'cache')}</cachedir></fontconfig>"
        )
    os.environ["FONTCONFIG_FILE"] = conf


_parcel_like = is_parcel_like


_SMALL_WORDS = {"of", "and", "the", "for", "in", "on", "at", "to"}


def display_term(term):
    """What the certificate prints as 'Searched'.

    A name typed all-lowercase or all-UPPERCASE ('mary kaittany') reads in proper
    case ('Mary Kaittany'); short all-caps tokens (NSSF, KPA) stay as acronyms.
    Anything typed in mixed case, and every parcel / LR number, is left as typed."""
    t = re.sub(r"\s+", " ", (term or "").strip())
    if not t or _parcel_like(t) or not (t.islower() or t.isupper()):
        return t
    upper_input = t.isupper()

    def word(w, first):
        if upper_input and w.isalpha() and len(w) <= 4 and len(t.split()) == 1:
            return w  # a lone short acronym such as NSSF
        if not first and w.lower() in _SMALL_WORDS:
            return w.lower()
        out = w[:1].upper() + w[1:].lower()
        return re.sub(r"(?<=\b\w')(\w)", lambda m: m.group(1).upper(), out)  # O'Brien, D'Souza

    return " ".join("-".join(word(p, i == 0 and j == 0) for j, p in enumerate(tok.split("-")))
                    for i, tok in enumerate(t.split(" ")))


def search_subject(term):
    """How a certificate refers to what was searched.

    A parcel / LR number reads as 'this property'; a name, entity or location
    can't be called a property, so it is quoted back instead ("Gospel Revival
    Centre"). 'lead' is the sentence-initial form."""
    t = re.sub(r"\s+", " ", (term or "").strip())
    if _parcel_like(t):
        return {"ref": "this property", "lead": "This property", "kind": "property"}
    shown = t if len(t) <= 60 else t[:57].rstrip() + "\u2026"
    quoted = f"\u201c{shown}\u201d"
    return {"ref": quoted, "lead": quoted, "kind": "name"}


def conversion_blocks(info):
    """LR-conversion matches as label/value fields in rows of two, mirroring the
    Parcel Summary layout. Missing optional fields are skipped, not shown as dashes."""
    blocks = []
    for m in (info or {}).get("matches", []):
        cells = [("Old LR number", m.get("old_lr_no")), ("New LR number", m.get("new_lr_number"))]
        for label, key in (("Scheme", "scheme_name"), ("Area (Ha)", "area_ha"),
                           ("Registration unit", "registration_unit")):
            if m.get(key):
                cells.append((label, m[key]))
        cites = "; ".join(f"{c.get('gazette_vol_no', '')} ({c.get('gazette_date', '')})"
                          for c in m.get("citations") or [])
        if cites:  # sits beside the registration unit rather than on a row of its own
            cells.append(("Gazetted", cites))
        rows = [[{"label": l, "value": v} for l, v in cells[i:i + 2]] for i in range(0, len(cells), 2)]
        blocks.append({"rows": rows})
    return blocks


def elc_index_stats():
    """What the ELC certificate's 'indexed decisions' refers to: how many
    decisions Landledger holds and when that index was last updated."""
    from django.db.models import Count, Max

    from litigation.models import ElcCase

    agg = ElcCase.objects.aggregate(n=Count("id"), last=Max("synced_at"))
    last = agg["last"]
    return {
        "count": agg["n"],
        "count_display": f"{agg['n']:,}",
        "as_of": f"{last.astimezone(EAT):%d %b %Y}" if last else "",
    }


def build_pdf_context(cert, meta):
    """Everything certificate.html needs beyond `cert` and `meta`."""
    from pathlib import Path

    source = cert.get("source", "ndungu")
    ref = meta.get("certificate_reference", "")
    ctx = {
        "cert": cert, "meta": meta, "logo": _logo_data_uri(),
        "qr": qr_data_uri(meta.get("verify_url", "")),
        "font_dir": (Path(settings.BASE_DIR) / "ndungu" / "assets" / "fonts").as_uri(),
        "conv_blocks": conversion_blocks(cert.get("conversion_info")),
        "subject": search_subject(meta.get("searched_parcel_id")),
    }
    if source == "elc":
        ctx["elc_rows"] = elc_rows(cert["elc"].get("matches", []))
        ctx["elc_total"] = cert["elc"].get("total", len(cert["elc"].get("matches", [])))
        ctx["index"] = elc_index_stats()
        ctx["links"] = contact_links(ref, "request a manual review")
    elif cert["ndungu"]["found"]:
        ctx["pages_ref"] = report_pages(cert["ndungu"]["tier_b_timeline"])
        ctx["links"] = contact_links(ref, "request a copy of the relevant report page")
    else:
        ctx["links"] = contact_links(ref, "ask about this certificate")
    return ctx


def render_certificate_pdf(cert, meta):
    """Render a certificate to a standard, naturally-paginated A4 PDF.

    Content flows across as many normal A4 pages as it needs; the template's
    own @page rule carries the repeating frame and "Page X of Y" footer.
    """
    from django.template.loader import render_to_string

    _ensure_fontconfig()  # must run before WeasyPrint/Pango first initialise
    from weasyprint import HTML  # lazy import: native libs only needed here

    html = render_to_string("ndungu/certificate.html", build_pdf_context(cert, meta))
    return HTML(string=html).write_pdf()

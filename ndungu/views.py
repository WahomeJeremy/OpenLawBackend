"""Ndung'u Report API (PRD section 4).

GET  /api/ndungu/search/?q=...      -> structured certificate JSON + ledger token
GET  /api/ndungu/verify/<ref>/      -> resolve a reference against the audit ledger
"""
from django.db.models import Q
from django.http import HttpResponse
from django.urls import reverse
from rest_framework import status as http_status
from rest_framework.response import Response
from rest_framework.views import APIView

from conversions.services import find_conversions
from litigation.services import (
    active_review,
    case_list_item,
    find_litigation,
    is_case_key,
    review_payload,
)

from .models import CertificateLog, Parcel, normalize_parcel_id
from .services import (
    _parcels_by_alternate_id,
    build_combined_certificate,
    clean_source,
    display_term,
    log_search,
    now_eat,
    pdf_filename,
    render_certificate_pdf,
    run_search,
    source_status,
    suggestion_payload,
    verify_url,
)


def _metadata(request, searched_id, reference):
    dt = now_eat()
    return {
        "searched_parcel_id": searched_id,
        "timestamp": dt.isoformat(),                  # machine-readable (JSON/API)
        "generated_display": f"{dt:%d %b %Y, %H:%M} EAT",  # human-readable (PDF)
        "certificate_reference": reference,
        "verify_url": verify_url(reference),          # public verify page (QR target)
        "verification_link": request.build_absolute_uri(
            reverse("ndungu:verify", args=[reference])
        ),
    }


class SearchView(APIView):
    """Primary search -> certificate generation. Logs every execution."""

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        if len(q) < 2:
            return Response(
                {"detail": "Provide a Parcel ID, LR number, name or location (min 2 chars)."},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        normalized = normalize_parcel_id(q)
        source = clean_source(request.query_params.get("source"))
        case_key = is_case_key(q)
        result = {"match_type": "none"} if case_key else run_search(q)
        # LR-conversion stays pure reference data, independent of the verdict.
        # ELC litigation now DOES factor into the verdict, alongside Ndung'u --
        # our "encumbrance" is Ndung'u OR ELC; conversion never decides it.
        conversion_info = find_conversions(q)
        litigation_info = find_litigation(q)

        if source == "elc" and not case_key and litigation_info \
                and len(litigation_info["matches"]) > 1:
            # Several cases: list them (citation only) and let the user open one,
            # exactly as Ndung'u lists parcels. The certificate is per case.
            total = litigation_info["total"]
            ref = log_search(q, normalized, total, "suggestions", dataset_source=source)
            note = (f" Showing the first {len(litigation_info['matches'])}; add a word to narrow it."
                    if litigation_info["truncated"] else "")
            payload = {
                "status": "suggestions",
                "list_kind": "elc",
                "metadata": _metadata(request, q, ref),
                "message": f"{total} ELC cases match this search. Select the one you want to open.{note}",
                "suggestions": [case_list_item(m) for m in litigation_info["matches"]],
            }
            if conversion_info:
                payload["conversion_info"] = conversion_info
            return Response(payload)

        shown_id = (litigation_info["matches"][0]["case_citation"]
                    if case_key and litigation_info else q)

        if result["match_type"] in ("suggestions", "multiple") and source == "elc":
            # One journey, one dataset: an ELC search never opens Ndung'u suggestions.
            # The term is looked up in the ELC index only; the Ndung'u matches are
            # reported as a count so the result can offer to switch.
            combined = build_combined_certificate(
                None, litigation_info, q, ndungu_suggestions=len(result["parcels"]))
            shown = combined["overview"]["parcel"]
            ref = log_search(shown, normalized, 0, source_status(combined, source),
                             None, dataset_source=source)
            combined["metadata"] = _metadata(request, shown, ref)
            if conversion_info:
                combined["conversion_info"] = conversion_info
            return Response(combined)

        if result["match_type"] in ("suggestions", "multiple"):
            ref = log_search(q, normalized, len(result["parcels"]), "suggestions",
                             dataset_source=source)
            payload = {
                "status": "suggestions",
                "metadata": _metadata(request, q, ref),
                "message": (
                    "No exact match. Did you mean one of these? "
                    "Select a parcel or refine with a location."
                ),
                "suggestions": [suggestion_payload(p) for p in result["parcels"]],
            }
            if conversion_info:
                payload["conversion_info"] = conversion_info
            if litigation_info:
                payload["litigation_info"] = litigation_info
            return Response(payload)

        parcel = result["parcel"] if result["match_type"] == "exact" else None
        combined = build_combined_certificate(parcel, litigation_info, shown_id)

        shown = combined["overview"]["parcel"]
        count = parcel.findings.count() if parcel else 0
        ref = log_search(shown, normalized, count, source_status(combined, source),
                         parcel, dataset_source=source)
        combined["metadata"] = _metadata(request, shown, ref)
        if conversion_info:
            combined["conversion_info"] = conversion_info
        return Response(combined)


class CertificatePDFView(APIView):
    """POST a verified parcel id (or query) -> print-ready PDF binary."""

    def post(self, request):
        data = request.data or {}
        q = (data.get("parcel_id") or data.get("q") or "").strip()
        searched_term = (data.get("searched_term") or "").strip()
        if len(q) < 2:
            return Response(
                {"detail": "Provide 'parcel_id' (or 'q') of at least 2 characters."},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        normalized = normalize_parcel_id(q)
        case_key = is_case_key(q)
        parcel = None if case_key else Parcel.objects.filter(
            Q(normalized_lr=normalized) | Q(parcel_id_clean__iexact=q)
        ).first()
        if parcel is None and not case_key:
            # Resolve Cf / Original / secondary-LR references the same way search does.
            alt = _parcels_by_alternate_id(q)
            if len(alt) == 1:
                parcel = alt[0]

        source = clean_source(data.get("source"))
        litigation_info = find_litigation(q)
        shown_id = (litigation_info["matches"][0]["case_citation"]
                    if case_key and litigation_info else q)
        cert = build_combined_certificate(parcel, litigation_info, shown_id)
        cert["source"] = source  # the PDF is about this one dataset only
        # A completed manual review (token from the emailed link) upgrades the
        # litigation certificate's wording; ignored if it was for another parcel.
        review = active_review(data.get("review_token"), q) if source == "elc" else None
        if review:
            cert["review"] = review_payload(review)
        shown = cert["overview"]["parcel"]
        count = parcel.findings.count() if parcel else 0
        ref = log_search(shown, normalized, count, source_status(cert, source),
                         parcel, dataset_source=source)

        # "Searched" is what the user typed; "Matched" is the record we resolved
        # to. Only carry Matched when it isn't a 1-to-1 match (e.g. name search).
        searched_display = display_term(searched_term) or shown
        meta = _metadata(request, searched_display, ref)
        if shown and shown.strip().lower() != searched_display.strip().lower():
            meta["matched_parcel_id"] = shown
        cert["metadata"] = meta

        conversion_info = find_conversions(q)
        if conversion_info:
            cert["conversion_info"] = conversion_info

        try:
            pdf = render_certificate_pdf(cert, meta)
        except OSError as exc:  # WeasyPrint native libs missing
            return Response(
                {"detail": f"PDF rendering unavailable: {exc}"},
                status=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        filename = pdf_filename(cert, searched_display, source)
        resp = HttpResponse(pdf, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp


class VerifyView(APIView):
    """Zero-auth public gateway resolving a reference against the ledger."""

    def get(self, request, reference):
        log = CertificateLog.objects.filter(
            certificate_reference=reference
        ).first()
        if not log:
            return Response(
                {"valid": False,
                 "detail": "No certificate found for this reference number."},
                status=http_status.HTTP_404_NOT_FOUND,
            )
        return Response({
            "valid": True,
            "certificate_reference": log.certificate_reference,
            "searched_parcel_id": log.searched_parcel_id,
            "results_count": log.results_count,
            "status": log.status,
            "dataset_source": log.dataset_source,
            "timestamp": log.created_at.isoformat(),
        })

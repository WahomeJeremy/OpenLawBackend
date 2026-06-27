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

from .models import CertificateLog, Parcel, normalize_parcel_id
from .services import (
    build_certificate,
    build_nil_certificate,
    log_search,
    now_eat,
    render_certificate_pdf,
    run_search,
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
        result = run_search(q)

        if result["match_type"] == "exact":
            parcel = result["parcel"]
            count = parcel.findings.count()
            cert = build_certificate(parcel, q)
            shown = cert["overview"]["parcel"]  # friendly id (never a synthetic key)
            ref = log_search(shown, normalized, count, "encumbrance_found", parcel)
            cert["metadata"] = _metadata(request, shown, ref)
            return Response(cert)

        if result["match_type"] in ("suggestions", "multiple"):
            ref = log_search(q, normalized, len(result["parcels"]), "suggestions")
            return Response({
                "status": "suggestions",
                "metadata": _metadata(request, q, ref),
                "message": (
                    "No exact match. Did you mean one of these? "
                    "Select a parcel or refine with a location."
                ),
                "suggestions": [suggestion_payload(p) for p in result["parcels"]],
            })

        # No match -> NIL certificate.
        ref = log_search(q, normalized, 0, "no_encumbrance")
        nil = build_nil_certificate(q)
        nil["metadata"] = _metadata(request, q, ref)
        return Response(nil)


class CertificatePDFView(APIView):
    """POST a verified parcel id (or query) -> print-ready PDF binary."""

    def post(self, request):
        data = request.data or {}
        q = (data.get("parcel_id") or data.get("q") or "").strip()
        if len(q) < 2:
            return Response(
                {"detail": "Provide 'parcel_id' (or 'q') of at least 2 characters."},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        normalized = normalize_parcel_id(q)
        parcel = Parcel.objects.filter(
            Q(normalized_lr=normalized) | Q(parcel_id_clean__iexact=q)
        ).first()

        if parcel is not None:
            count = parcel.findings.count()
            cert = build_certificate(parcel, q)
            shown = cert["overview"]["parcel"]  # friendly id (never a synthetic key)
            ref = log_search(shown, normalized, count, "encumbrance_found", parcel)
        else:
            cert = build_nil_certificate(q)
            shown = q
            ref = log_search(q, normalized, 0, "no_encumbrance")

        meta = _metadata(request, shown, ref)
        cert["metadata"] = meta

        try:
            pdf = render_certificate_pdf(cert, meta)
        except OSError as exc:  # WeasyPrint native libs missing
            return Response(
                {"detail": f"PDF rendering unavailable: {exc}"},
                status=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        filename = f"OpenLaw_Certificate_{ref}.pdf"
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
            "timestamp": log.created_at.isoformat(),
        })

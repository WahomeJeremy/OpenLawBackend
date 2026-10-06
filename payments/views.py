"""M-Pesa payment API.

POST /api/payments/initiate/           -> kicks off an STK Push, returns a checkout_request_id
GET  /api/payments/<checkout_id>/status/ -> polled by the frontend until completed/failed
POST /api/payments/callback/           -> Safaricom's async result (zero-auth, called by Daraja itself)
"""
from rest_framework import status as http_status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PaymentTransaction
from .services import initiate_stk_push, process_callback


class InitiatePaymentView(APIView):
    """Starts an STK Push for a certificate. The certificate itself is not
    generated here -- this only initiates payment; the caller polls status
    and requests the certificate separately once it's "completed"."""

    def post(self, request):
        data = request.data or {}
        phone_number = (data.get("phone_number") or "").strip()
        account_reference = (data.get("account_reference") or "").strip()

        if not phone_number or not account_reference:
            return Response(
                {"detail": "'phone_number' and 'account_reference' are required."},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        txn = initiate_stk_push(
            phone_number=phone_number,
            account_reference=account_reference,
            transaction_desc=data.get("transaction_desc", "Certificate payment"),
        )

        if txn.status == "failed":
            return Response(
                {"detail": txn.result_desc or "Payment could not be initiated.",
                 "checkout_request_id": txn.checkout_request_id},
                status=http_status.HTTP_502_BAD_GATEWAY,
            )

        return Response({
            "checkout_request_id": txn.checkout_request_id,
            "status": txn.status,
            "amount": str(txn.amount),
        })


class PaymentStatusView(APIView):
    """Polled by the frontend every few seconds after initiating payment."""

    def get(self, request, checkout_request_id):
        txn = PaymentTransaction.objects.filter(
            checkout_request_id=checkout_request_id
        ).first()
        if not txn:
            return Response(
                {"detail": "No payment found for that reference."},
                status=http_status.HTTP_404_NOT_FOUND,
            )
        return Response({
            "checkout_request_id": txn.checkout_request_id,
            "status": txn.status,
            "amount": str(txn.amount),
            "account_reference": txn.account_reference,
            "mpesa_receipt_number": txn.mpesa_receipt_number,
            "result_desc": txn.result_desc,
        })


class MpesaCallbackView(APIView):
    """Safaricom calls this directly -- no auth, not called by our own
    frontend. Always returns 200 with a simple acknowledgement regardless of
    what we found, since a non-200 makes Daraja retry the callback."""

    permission_classes = [AllowAny]

    def post(self, request):
        process_callback(request.data or {})
        return Response({"ResultCode": 0, "ResultDesc": "Accepted"})

"""Daraja (M-Pesa) STK Push integration.

Two things are fixed by Safaricom and must not be improvised: the request
body shape for /stkpush/v1/processrequest, and the callback payload shape
under Body.stkCallback. Everything else here (the AccountReference content,
our own PaymentTransaction bookkeeping) is ours.

Uses urllib.request rather than the requests library, matching the existing
pattern in litigation/services.py -- no new dependency for a couple of
JSON calls.
"""
import base64
import json
import urllib.error
import urllib.request
from datetime import datetime

from django.conf import settings

from .models import PaymentTransaction

_SANDBOX_BASE = "https://sandbox.safaricom.co.ke"
_PRODUCTION_BASE = "https://api.safaricom.co.ke"


def _base_url():
    return _PRODUCTION_BASE if settings.MPESA_ENV == "production" else _SANDBOX_BASE


def _post_json(url, payload, headers):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_access_token():
    """OAuth token for the Consumer Key/Secret pair. Short-lived (~1hr on
    Safaricom's side) -- callers should fetch a fresh one per request rather
    than cache it; this is a single fast call, not worth the staleness risk."""
    credentials = f"{settings.MPESA_CONSUMER_KEY}:{settings.MPESA_CONSUMER_SECRET}"
    auth = base64.b64encode(credentials.encode()).decode()
    req = urllib.request.Request(
        f"{_base_url()}/oauth/v1/generate?grant_type=client_credentials",
        headers={"Authorization": f"Basic {auth}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["access_token"]


def _password_and_timestamp():
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    raw = f"{settings.MPESA_SHORTCODE}{settings.MPESA_PASSKEY}{timestamp}"
    password = base64.b64encode(raw.encode()).decode()
    return password, timestamp


def initiate_stk_push(phone_number, account_reference, transaction_desc, amount=None):
    """Kick off an STK Push and log it as a PaymentTransaction (status
    "initiated" if Safaricom accepts the request, "failed" immediately if
    it doesn't -- e.g. a malformed phone number). Returns the
    PaymentTransaction row either way, so callers always have something to
    show the user or inspect on failure."""
    amount = amount or settings.MPESA_CERTIFICATE_PRICE
    password, timestamp = _password_and_timestamp()

    payload = {
        "BusinessShortCode": settings.MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(amount),
        "PartyA": phone_number,
        "PartyB": settings.MPESA_SHORTCODE,
        "PhoneNumber": phone_number,
        "CallBackURL": settings.MPESA_CALLBACK_URL,
        "AccountReference": account_reference[:20],  # Daraja truncates around here anyway
        "TransactionDesc": transaction_desc[:20] or "Certificate payment",
    }

    try:
        token = get_access_token()
        data = _post_json(
            f"{_base_url()}/mpesa/stkpush/v1/processrequest",
            payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, TimeoutError) as exc:
        # No CheckoutRequestID to key on -- log under a synthetic one so the
        # attempt is still visible in the ledger, just clearly not a real
        # Daraja reference.
        return PaymentTransaction.objects.create(
            checkout_request_id=f"failed-{timestamp}-{phone_number}",
            phone_number=phone_number,
            amount=amount,
            account_reference=account_reference,
            transaction_desc=transaction_desc,
            status="failed",
            result_desc=str(exc),
        )

    if data.get("ResponseCode") != "0":
        return PaymentTransaction.objects.create(
            checkout_request_id=data.get("CheckoutRequestID") or f"rejected-{timestamp}",
            merchant_request_id=data.get("MerchantRequestID", ""),
            phone_number=phone_number,
            amount=amount,
            account_reference=account_reference,
            transaction_desc=transaction_desc,
            status="failed",
            result_desc=data.get("ResponseDescription", ""),
        )

    return PaymentTransaction.objects.create(
        checkout_request_id=data["CheckoutRequestID"],
        merchant_request_id=data.get("MerchantRequestID", ""),
        phone_number=phone_number,
        amount=amount,
        account_reference=account_reference,
        transaction_desc=transaction_desc,
        status="pending",
    )


def process_callback(payload):
    """Parse a Daraja STK callback and update the matching PaymentTransaction.

    Shape (fixed by Safaricom):
      {"Body": {"stkCallback": {
          "MerchantRequestID": "...", "CheckoutRequestID": "...",
          "ResultCode": 0, "ResultDesc": "...",
          "CallbackMetadata": {"Item": [{"Name": "Amount", "Value": ...}, ...]}
      }}}
    ResultCode 0 = success; any other value = declined, cancelled, or timed out
    on the customer's phone -- Safaricom doesn't distinguish those in the code,
    only in ResultDesc text, so we bucket them all as "failed".
    """
    stk = payload.get("Body", {}).get("stkCallback", {})
    checkout_request_id = stk.get("CheckoutRequestID")
    if not checkout_request_id:
        return None

    try:
        txn = PaymentTransaction.objects.get(checkout_request_id=checkout_request_id)
    except PaymentTransaction.DoesNotExist:
        return None

    result_code = stk.get("ResultCode")
    txn.result_code = result_code
    txn.result_desc = stk.get("ResultDesc", "")
    txn.raw_callback = payload

    if result_code == 0:
        items = {
            i["Name"]: i.get("Value")
            for i in stk.get("CallbackMetadata", {}).get("Item", [])
        }
        txn.mpesa_receipt_number = items.get("MpesaReceiptNumber", "")
        txn.status = "completed"
    else:
        txn.status = "failed"

    txn.save()
    return txn

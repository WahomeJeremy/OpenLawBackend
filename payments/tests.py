import json
from io import BytesIO
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import PaymentTransaction
from .services import process_callback


def _mock_response(payload):
    """A fake urlopen() context manager returning the given JSON payload."""
    mock = MagicMock()
    mock.__enter__.return_value.read.return_value = json.dumps(payload).encode()
    return mock


@override_settings(
    MPESA_SHORTCODE="174379",
    MPESA_PASSKEY="testpasskey",
    MPESA_CONSUMER_KEY="testkey",
    MPESA_CONSUMER_SECRET="testsecret",
    MPESA_CALLBACK_URL="https://example.com/api/payments/callback/",
    MPESA_CERTIFICATE_PRICE=650,
    MPESA_ENV="sandbox",
)
class InitiatePaymentTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch("payments.services.urllib.request.urlopen")
    def test_initiate_success_creates_pending_transaction(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _mock_response({"access_token": "tok123"}),
            _mock_response({
                "MerchantRequestID": "mr-1",
                "CheckoutRequestID": "ws_CO_1",
                "ResponseCode": "0",
                "ResponseDescription": "Success. Request accepted for processing",
                "CustomerMessage": "Success. Request accepted for processing",
            }),
        ]
        resp = self.client.post("/api/payments/initiate/", {
            "phone_number": "254708374149",
            "account_reference": "NDR-20260728-TEST",
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["checkout_request_id"], "ws_CO_1")
        self.assertEqual(resp.data["status"], "pending")

        txn = PaymentTransaction.objects.get(checkout_request_id="ws_CO_1")
        self.assertEqual(txn.amount, 650)
        self.assertEqual(txn.account_reference, "NDR-20260728-TEST")
        self.assertEqual(txn.status, "pending")

    @patch("payments.services.urllib.request.urlopen")
    def test_initiate_rejected_by_daraja_marks_failed(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _mock_response({"access_token": "tok123"}),
            _mock_response({
                "ResponseCode": "1",
                "ResponseDescription": "Invalid PhoneNumber",
            }),
        ]
        resp = self.client.post("/api/payments/initiate/", {
            "phone_number": "not-a-number",
            "account_reference": "NDR-20260728-TEST",
        }, format="json")
        self.assertEqual(resp.status_code, 502)
        self.assertEqual(PaymentTransaction.objects.first().status, "failed")

    def test_initiate_requires_phone_and_reference(self):
        resp = self.client.post("/api/payments/initiate/", {}, format="json")
        self.assertEqual(resp.status_code, 400)


class CallbackTests(TestCase):
    def setUp(self):
        self.txn = PaymentTransaction.objects.create(
            checkout_request_id="ws_CO_2",
            phone_number="254708374149",
            amount=650,
            account_reference="NDR-20260728-TEST",
            status="pending",
        )

    def test_successful_callback_marks_completed(self):
        payload = {
            "Body": {"stkCallback": {
                "MerchantRequestID": "mr-2",
                "CheckoutRequestID": "ws_CO_2",
                "ResultCode": 0,
                "ResultDesc": "The service request is processed successfully.",
                "CallbackMetadata": {"Item": [
                    {"Name": "Amount", "Value": 650},
                    {"Name": "MpesaReceiptNumber", "Value": "NLJ7RT61SV"},
                    {"Name": "PhoneNumber", "Value": 254708374149},
                ]},
            }}
        }
        txn = process_callback(payload)
        self.assertEqual(txn.status, "completed")
        self.assertEqual(txn.mpesa_receipt_number, "NLJ7RT61SV")

    def test_cancelled_callback_marks_failed(self):
        payload = {
            "Body": {"stkCallback": {
                "MerchantRequestID": "mr-2",
                "CheckoutRequestID": "ws_CO_2",
                "ResultCode": 1032,
                "ResultDesc": "Request cancelled by user.",
            }}
        }
        txn = process_callback(payload)
        self.assertEqual(txn.status, "failed")
        self.assertEqual(txn.mpesa_receipt_number, "")

    def test_callback_for_unknown_checkout_id_is_a_noop(self):
        result = process_callback({
            "Body": {"stkCallback": {"CheckoutRequestID": "does-not-exist", "ResultCode": 0}}
        })
        self.assertIsNone(result)


class PaymentStatusViewTests(TestCase):
    def test_status_for_unknown_reference_404s(self):
        client = APIClient()
        resp = client.get("/api/payments/does-not-exist/status/")
        self.assertEqual(resp.status_code, 404)

    def test_status_reflects_current_state(self):
        PaymentTransaction.objects.create(
            checkout_request_id="ws_CO_3",
            phone_number="254708374149",
            amount=650,
            account_reference="NDR-20260728-TEST",
            status="completed",
            mpesa_receipt_number="NLJ7RT61SV",
        )
        client = APIClient()
        resp = client.get("/api/payments/ws_CO_3/status/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "completed")
        self.assertEqual(resp.data["mpesa_receipt_number"], "NLJ7RT61SV")

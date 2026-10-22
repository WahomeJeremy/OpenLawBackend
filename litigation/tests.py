from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from .models import ManualReviewRequest


class ReviewRequestTests(TestCase):
    def setUp(self):
        cache.clear()  # throttle counters live in the cache
        self.url = reverse("litigation:review_request")

    def test_creates_a_pending_request(self):
        res = self.client.post(
            self.url,
            {"parcel_id": "209/11642", "certificate_reference": "OL-1",
             "contact_email": "a@b.co", "notes": "please check"},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 201)
        req = ManualReviewRequest.objects.get()
        self.assertEqual(req.parcel_id, "209/11642")
        self.assertEqual(req.status, ManualReviewRequest.STATUS_PENDING)

    def test_optional_fields_may_be_blank(self):
        res = self.client.post(self.url, {"parcel_id": "LR 1/2"}, content_type="application/json")
        self.assertEqual(res.status_code, 201)

    def test_parcel_id_is_required(self):
        res = self.client.post(self.url, {"notes": "x"}, content_type="application/json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(ManualReviewRequest.objects.count(), 0)

    def test_rejects_a_malformed_email(self):
        res = self.client.post(
            self.url, {"parcel_id": "1/2", "contact_email": "nope"}, content_type="application/json"
        )
        self.assertEqual(res.status_code, 400)

    def test_is_throttled_after_ten_requests_an_hour(self):
        for _ in range(10):
            self.client.post(self.url, {"parcel_id": "1/2"}, content_type="application/json")
        res = self.client.post(self.url, {"parcel_id": "1/2"}, content_type="application/json")
        self.assertEqual(res.status_code, 429)

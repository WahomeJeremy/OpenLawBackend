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

    def test_needs_an_email_or_a_phone_number(self):
        res = self.client.post(self.url, {"parcel_id": "LR 1/2"}, content_type="application/json")
        self.assertEqual(res.status_code, 400)
        res = self.client.post(
            self.url, {"parcel_id": "LR 1/2", "contact_phone": "0712345678"}, content_type="application/json"
        )
        self.assertEqual(res.status_code, 201)

    def test_support_inbox_is_told(self):
        from django.core import mail
        self.client.post(self.url, {"parcel_id": "LR 1/2", "contact_email": "a@b.co"},
                         content_type="application/json")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("LR 1/2", mail.outbox[0].subject)

    def test_parcel_id_is_required(self):
        res = self.client.post(self.url, {"notes": "x", "contact_email": "a@b.co"}, content_type="application/json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(ManualReviewRequest.objects.count(), 0)

    def test_rejects_a_malformed_email(self):
        res = self.client.post(
            self.url, {"parcel_id": "1/2", "contact_email": "nope"}, content_type="application/json"
        )
        self.assertEqual(res.status_code, 400)

    def test_is_throttled_after_ten_requests_an_hour(self):
        for _ in range(10):
            self.client.post(self.url, {"parcel_id": "1/2", "contact_email": "a@b.co"}, content_type="application/json")
        res = self.client.post(self.url, {"parcel_id": "1/2", "contact_email": "a@b.co"}, content_type="application/json")
        self.assertEqual(res.status_code, 429)


class FindLitigationPayloadTests(TestCase):
    def test_payload_carries_county_and_the_matched_identifier(self):
        from .models import ElcCase, ElcCaseIdentifier
        from .services import find_litigation
        from ndungu.services import normalize_parcel_id

        case = ElcCase.objects.create(
            case_citation="X v Y [2020] KEELC 1 (KLR)", county="Kajiado",
            location_details="Kitengela",
        )
        ElcCaseIdentifier.objects.create(
            case=case, raw_identifier="Plot No. 55/1",
            normalized_identifier=normalize_parcel_id("55/1"),
        )
        ElcCaseIdentifier.objects.create(
            case=case, raw_identifier="209/11642",
            normalized_identifier=normalize_parcel_id("209/11642"),
        )
        m = find_litigation("55/1")["matches"][0]
        self.assertEqual(m["county"], "Kajiado")
        self.assertEqual(m["matched_identifier"], "Plot No. 55/1")
        self.assertEqual(m["location_details"], "Kitengela")

    def test_each_sheet_tab_has_a_county(self):
        from .services import SHEET_COUNTIES, SHEET_EXPORT_URLS

        self.assertEqual(len(SHEET_COUNTIES), len(SHEET_EXPORT_URLS))


class ManualReviewWorkflowTests(TestCase):
    def setUp(self):
        from .models import ElcCase
        self.req = ManualReviewRequest.objects.create(
            parcel_id="209/11642", certificate_reference="NDR-1", contact_email="u@x.co",
        )
        self.case = ElcCase.objects.create(case_citation="A v B [2021] KEELC 9 (KLR)", source="manual")

    def test_completing_links_cases_stamps_and_emails(self):
        from django.core import mail
        from .services import complete_review, find_litigation, notify_user_review_ready

        self.req.outcome = ManualReviewRequest.OUTCOME_LITIGATION
        self.req.save()
        self.req.cases.add(self.case)
        complete_review(self.req)
        self.assertTrue(notify_user_review_ready(self.req))

        self.req.refresh_from_db()
        self.assertEqual(self.req.status, "done")
        self.assertTrue(self.req.review_reference.startswith("MR-"))
        self.assertIsNotNone(self.req.notified_at)
        self.assertIn(self.req.access_token, mail.outbox[0].body)
        # ordinary searches now find the hand-added case too
        self.assertEqual(len(find_litigation("209/11642")["matches"]), 1)

    def test_staff_can_see_what_the_user_searched(self):
        from ndungu.models import CertificateLog
        from .services import original_search_summary

        self.assertEqual(original_search_summary(self.req), "")  # no ledger row yet
        CertificateLog.objects.create(
            certificate_reference="NDR-1", searched_parcel_id="Plot 209 / 11642",
            results_count=0, status="no_encumbrance", dataset_source="elc",
        )
        summary = original_search_summary(self.req)
        self.assertIn('"Plot 209 / 11642"', summary)
        self.assertIn("ELC Litigation", summary)

    def test_status_endpoint_is_token_gated(self):
        ok = self.client.get(reverse("litigation:review_status", args=[self.req.access_token]))
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["status"], "pending")
        bad = self.client.get(reverse("litigation:review_status", args=["nope"]))
        self.assertEqual(bad.status_code, 404)

    def test_sync_cleanup_spares_manual_cases(self):
        from .models import ElcCase
        ElcCase.objects.filter(source="sheet").delete()
        self.assertTrue(ElcCase.objects.filter(pk=self.case.pk).exists())

    def test_review_only_applies_to_its_own_parcel_and_when_done(self):
        from .services import active_review, complete_review
        self.req.outcome = ManualReviewRequest.OUTCOME_CLEAR
        self.req.save()
        self.assertIsNone(active_review(self.req.access_token, "209/11642"))  # not completed yet
        complete_review(self.req)
        self.assertIsNotNone(active_review(self.req.access_token, "209/11642"))
        self.assertIsNone(active_review(self.req.access_token, "1/2"))

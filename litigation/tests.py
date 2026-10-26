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


class OversizedIdentifierTests(TestCase):
    """A cell that lists many parcels with commas must not become one giant identifier."""

    LONG = ("L.R No. 97/5262 police post, L.R No. 97/5265, D.O’s office, L.R No. 97/ 5264 chief’s office, "
            "L.R No. 97/5263 post office, Nairobi/Block 37/283 (former 209/22334), 209/6002/7, 12826, "
            + ", ".join(f"15400/{n}" for n in range(1, 120)))

    def test_an_oversized_cell_is_split_into_individual_parcel_numbers(self):
        from .services import MAX_IDENTIFIER_LEN, split_identifiers

        self.assertGreater(len(self.LONG), MAX_IDENTIFIER_LEN)
        pairs = split_identifiers(self.LONG)
        raws = [r for r, _ in pairs]
        for expected in ("97/5262", "97/5265", "97/5264", "209/6002/7", "12826", "15400/57",
                         "Nairobi/Block 37/283", "209/22334"):
            self.assertIn(expected, raws)
        self.assertNotIn("D.O’s office", " ".join(raws))      # words are not identifiers
        self.assertTrue(all(len(r) <= MAX_IDENTIFIER_LEN and len(n) <= MAX_IDENTIFIER_LEN for r, n in pairs))
        self.assertEqual(len(raws), len(set(raws)))             # no duplicates

    def test_ordinary_cells_are_untouched(self):
        from .services import split_identifiers

        self.assertEqual([r for r, _ in split_identifiers("L.R No. 209/11642; Title LR Ngong/Ngong/10915")],
                         ["L.R No. 209/11642", "Title LR Ngong/Ngong/10915"])
        self.assertEqual(split_identifiers("NONE"), [])

    def test_the_parcels_inside_a_long_list_are_now_findable(self):
        from .models import ElcCase, ElcCaseIdentifier
        from .services import find_litigation, split_identifiers

        case = ElcCase.objects.create(case_citation="Mua & 4 others v Dandora [2020] KEELC 1 (KLR)", county="Nairobi")
        for raw, norm in split_identifiers(self.LONG):
            ElcCaseIdentifier.objects.get_or_create(case=case, normalized_identifier=norm,
                                                    defaults={"raw_identifier": raw})
        self.assertEqual(len(find_litigation("15400/57")["matches"]), 1)
        self.assertEqual(len(find_litigation("97/5264")["matches"]), 1)


class SyncSurvivesBadRowsTests(TestCase):
    """PostgreSQL rejects over-long values (SQLite doesn't): one bad sheet row must not abort the sync."""

    def _run(self, rows):
        from django.core.management import call_command
        from unittest.mock import patch

        from .management.commands.sync_elc_litigation import Command

        with patch.object(Command, "_fetch_rows", return_value=rows):
            call_command("sync_elc_litigation", verbosity=0)

    def _row(self, **kw):
        row = {"Case Citation": "A v B [2025] KEELC 1 (KLR)", "URL Link": "https://x.org/a", "Court Station": "NAIROBI",
               "Judgement/Ruling Date": "19 February 2026", "Action": "Ruling", "Parties": "A; B",
               "Location Details": "Nairobi", "Case Outcome": "Dismissed", "Timestamp": "1/1/2026",
               "Title/Plot/Certificate/Allotment/Deed Plan Number": "209/11642"}
        row.update(kw)
        return row

    def test_overlong_values_are_clipped_and_oversized_identifier_cells_are_expanded(self):
        from django.db.models import CharField

        from .models import ElcCase, ElcCaseIdentifier

        ids_col = "Title/Plot/Certificate/Allotment/Deed Plan Number"
        rows = [
            self._row(**{"Court Station": "N" * 400, "Judgement/Ruling Date": "D" * 300, "Action": "R" * 120}),
            self._row(**{"Case Citation": "C v D [2025] KEELC 2 (KLR)",
                         ids_col: ", ".join(f"15400/{n}" for n in range(1, 150))}),
        ]
        self._run(rows)

        self.assertEqual(ElcCase.objects.count(), 2)  # nothing was dropped or aborted
        for model in (ElcCase, ElcCaseIdentifier):
            for f in model._meta.fields:
                if isinstance(f, CharField) and f.max_length:
                    longest = max((len(getattr(o, f.name) or "") for o in model.objects.all()), default=0)
                    self.assertLessEqual(longest, f.max_length, f"{model.__name__}.{f.name}")
        self.assertTrue(ElcCaseIdentifier.objects.filter(normalized_identifier="15400/77").exists())

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


class MultiParcelCellTests(TestCase):
    """Cells that join several parcels with 'and', '&' or commas become separate identifiers."""

    def _raws(self, cell):
        from .services import split_identifiers

        return [r for r, _ in split_identifiers(cell)]

    def test_and_ampersand_and_comma_joined_parcels_are_separated(self):
        self.assertEqual(self._raws("land reference numbers 14902/32 and 14902/41"), ["14902/32", "14902/41"])
        self.assertEqual(self._raws("Ngong/Ngong/1445 & Ngong/Ngong/94240"), ["Ngong/Ngong/1445", "Ngong/Ngong/94240"])
        self.assertEqual(self._raws("LR. No. 13658/4 & LR. No. 13658/13"), ["13658/4", "13658/13"])
        self.assertEqual(self._raws("209/11307, 209/11308 and 209/11309"), ["209/11307", "209/11308", "209/11309"])

    def test_old_roman_numeral_plots_and_block_references_survive(self):
        self.assertEqual(
            self._raws("Plot No. 36/VII/637 (Now Nairobi /Block 50/186), Plot No. 36/VII/638"),
            ["36/VII/637", "Nairobi/Block 50/186", "36/VII/638"],
        )
        self.assertEqual(self._raws("Nairobi Block 91/130/333 and 386"), ["Nairobi/Block 91/130/333"])
        self.assertEqual(self._raws("Nairobi/Block126/749,"), ["Nairobi/Block 126/749"])

    def test_single_parcels_and_unrecognised_items_are_left_as_written(self):
        self.assertEqual(self._raws("L.R No. 209/11642"), ["L.R No. 209/11642"])
        self.assertEqual(self._raws("Title LR Ngong/Ngong/10915"), ["Title LR Ngong/Ngong/10915"])
        self.assertEqual(self._raws("Plot No. 34, Karen"), ["Plot No. 34, Karen"])   # a comma, but no parcel number
        self.assertEqual(self._raws("209/1; 209/2"), ["209/1", "209/2"])             # semicolons still split

    def test_each_parcel_in_a_joined_cell_is_findable(self):
        from .models import ElcCase, ElcCaseIdentifier
        from .services import find_litigation, split_identifiers

        case = ElcCase.objects.create(case_citation="X v Y [2024] KEELC 5 (KLR)", county="Nairobi")
        for raw, norm in split_identifiers("land reference numbers 14902/32 and 14902/41"):
            ElcCaseIdentifier.objects.get_or_create(case=case, normalized_identifier=norm, defaults={"raw_identifier": raw})
        for q in ("14902/32", "14902/41"):
            self.assertEqual(len(find_litigation(q)["matches"]), 1, q)


class PartyNameSearchTests(TestCase):
    """A name or entity that matches no identifier is matched against case parties."""

    def _case(self, citation, parties, **kw):
        from .models import ElcCase

        return ElcCase.objects.create(case_citation=citation, parties=parties, **kw)

    def setUp(self):
        self._case("Mary Wamaitha Kaittany v Njeri Kariuki [2019] KEELC 1 (KLR)", "MARY WAMAITHA KAITTANY; NJERI KARIUKI")
        self._case("Mary Wanjiku v Peter Kaittany [2020] KEELC 2 (KLR)", "MARY WANJIKU; PETER KAITTANY")  # words in DIFFERENT parties
        self._case("Gachichio v Twin Properties Limited [2026] KEELC 3 (KLR)", "MWANGI GACHICHIO; TWIN PROPERTIES LIMITED;")

    def test_all_words_must_be_in_one_party(self):
        from .services import find_litigation

        r = find_litigation("Mary Kaittany")
        self.assertEqual(r["match_basis"], "parties")
        self.assertEqual([m["case_citation"][:22] for m in r["matches"]], ["Mary Wamaitha Kaittany"])

    def test_company_suffixes_do_not_have_to_match(self):
        from .services import find_litigation

        self.assertEqual(find_litigation("Twin Properties Ltd")["total"], 1)

    def test_short_or_generic_terms_do_not_search_names(self):
        from .services import find_litigation

        for term in ("ab", "the", "ltd", "x y"):
            self.assertIsNone(find_litigation(term), term)

    def test_a_parcel_number_is_never_name_searched(self):
        from .services import find_litigation

        self.assertIsNone(find_litigation("209/11642"))

    def test_an_identifier_match_wins_over_a_name_match(self):
        from .models import ElcCaseIdentifier
        from .services import find_litigation
        from ndungu.models import normalize_parcel_id

        case = self._case("Taxation Matter [2021] KEELC 9 (KLR)", "A; B")
        ElcCaseIdentifier.objects.create(case=case, raw_identifier="Taxation",
                                         normalized_identifier=normalize_parcel_id("Taxation"))
        r = find_litigation("Taxation")
        self.assertEqual(r["match_basis"], "identifier")

    def test_a_long_result_is_capped_but_reports_the_true_total(self):
        from .services import MAX_NAME_MATCHES, find_litigation

        for n in range(40):
            self._case(f"Kamau v Party{n} [2022] KEELC {n} (KLR)", f"JOHN KAMAU; PARTY{n}")
        r = find_litigation("John Kamau")
        self.assertEqual((len(r["matches"]), r["total"], r["truncated"]), (MAX_NAME_MATCHES, 40, True))

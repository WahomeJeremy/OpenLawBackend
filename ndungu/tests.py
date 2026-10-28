"""Unit tests for the Ndung'u encumbrance engine (models, services, API)."""
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from ndungu import services
from ndungu.models import CertificateLog, Finding, Parcel
from ndungu.services import (
    build_certificate,
    build_nil_certificate,
    friendly_label,
    normalize_parcel_id,
    run_search,
)


def make_parcel(pid, display="", ptype="lr", scope="global"):
    return Parcel.objects.create(
        parcel_id_clean=pid,
        normalized_lr=normalize_parcel_id(pid),
        parcel_display=display or pid,
        parcel_id_type=ptype,
        key_scope=scope,
    )


def make_finding(parcel, record_id, **kw):
    defaults = dict(
        record_id=record_id, flag_category="irregular_municipal_allocation",
        flag_reason="Irregular allocation of public land",
        current_holder="Holder Co", prior_party="Prior Co",
        location="Nairobi", area="0.21", commission_recommendation="Revoke",
        source_volume="1", source_page="25",
    )
    defaults.update(kw)
    return Finding.objects.create(parcel=parcel, **defaults)


# --------------------------------------------------------------------------- #
class NormalizeTests(TestCase):
    def test_strips_lr_prefixes_and_tightens_slashes(self):
        for variant in ("209/11642", "L.R. No. 209 / 11642", "LR 209/11642",
                        "209 / 11642"):
            self.assertEqual(normalize_parcel_id(variant), "209/11642")

    def test_blank(self):
        self.assertEqual(normalize_parcel_id(""), "")
        self.assertEqual(normalize_parcel_id(None), "")


class FriendlyLabelTests(TestCase):
    def test_real_parcel_returns_display(self):
        p = make_parcel("209/11642")
        self.assertEqual(friendly_label(p), "209/11642")

    def test_synthetic_key_uses_display_and_strips_commas(self):
        p = make_parcel("narrative::forest_018", display=", Karura",
                        ptype="narrative", scope="narrative")
        self.assertEqual(friendly_label(p), "Karura")

    def test_synthetic_key_falls_back_to_holder(self):
        p = make_parcel("narrative::x", display="", ptype="narrative")
        make_finding(p, "x", current_holder="Gospel Centre")
        # parcel_display defaults to pid in make_parcel; clear it to test fallback
        p.parcel_display = ""
        p.save()
        self.assertEqual(friendly_label(p), "Gospel Centre")

    def test_never_returns_synthetic_key(self):
        p = make_parcel("narrative::y", display="", ptype="narrative")
        p.parcel_display = ""
        p.save()
        self.assertNotIn("::", friendly_label(p))


class CertificateBuilderTests(TestCase):
    def setUp(self):
        self.p = make_parcel("209/11642", display="209/11642")
        make_finding(self.p, "r1", flag_category="institutional_land_allocation",
                     reserved_use="Customs & Excise Extension",
                     current_holder="NSSF Board", source_volume="1", source_page="532",
                     commission_recommendation="Revoke")
        make_finding(self.p, "r2", flag_category="state_corp_purchase",
                     current_holder="NSSF (buyer)", prior_party="Lekuna Ltd",
                     price_kshs="20307750", transaction_date="23/03/95",
                     source_volume="3", source_page="96",
                     commission_recommendation="Revoke; refer to NSSF")

    def test_encumbrance_overview_and_tiers(self):
        cert = build_certificate(self.p, "209/11642")
        self.assertEqual(cert["status"], "encumbrance_found")
        self.assertEqual(cert["overview"]["records_matched"], 2)
        self.assertEqual(cert["overview"]["volumes"], ["I", "III"])
        self.assertEqual(cert["tier_a_summary"]["current_owner"], "NSSF (buyer)")
        self.assertEqual(cert["tier_a_summary"]["location"], "Nairobi")
        # onward sale present on the vol III finding
        sales = [e for e in cert["tier_b_timeline"] if "onward_sale" in e]
        self.assertEqual(len(sales), 1)
        self.assertEqual(sales[0]["onward_sale"]["price_kshs"], "20307750")

    def test_exact_duplicate_findings_collapse(self):
        # add an exact duplicate of r1
        make_finding(self.p, "r1-dup",
                     flag_category="institutional_land_allocation",
                     reserved_use="Customs & Excise Extension",
                     current_holder="NSSF Board", source_volume="1",
                     source_page="532", commission_recommendation="Revoke",
                     flag_reason="Irregular allocation of public land")
        # make r1 identical signature
        Finding.objects.filter(record_id="r1").update(
            flag_reason="Irregular allocation of public land")
        cert = build_certificate(self.p, "209/11642")
        # still 2 distinct entries (the dup collapses)
        self.assertEqual(cert["overview"]["records_matched"], 2)

    def test_synthetic_parcel_shows_friendly_id(self):
        p = make_parcel("narrative::z", display="Karura Forest", ptype="narrative")
        make_finding(p, "z")
        cert = build_certificate(p, "narrative::z")
        self.assertEqual(cert["overview"]["parcel"], "Karura Forest")
        self.assertNotIn("::", cert["tier_a_summary"]["searched_id"])

    def test_also_recorded_as_lists_other_references(self):
        """A plot with several registrable refs surfaces the others (Cf / Original
        / secondary LR) on the certificate, excluding the one searched."""
        p = make_parcel("19095", display="19095")
        make_finding(p, "r_cf",
                     parcel_id_raw="L.R. 19095 Original 12661 Cf 157469 Park View")
        # searched by the primary LR -> shows the Cf and Original numbers
        ov = build_certificate(p, "19095")["overview"]
        self.assertEqual(ov["also_recorded_as"], ["Original 12661", "Cf 157469"])
        # searched by the Cf number -> shows the LR and Original numbers instead
        ov = build_certificate(p, "157469")["overview"]
        self.assertEqual(ov["also_recorded_as"], ["L.R. 19095", "Original 12661"])

    def test_no_also_recorded_as_when_single_reference(self):
        p = make_parcel("209/5001", display="209/5001")
        make_finding(p, "r_single", parcel_id_raw="L.R. 209/5001")
        self.assertNotIn("also_recorded_as", build_certificate(p, "209/5001")["overview"])

    def test_nil_certificate_legal_phrasing(self):
        nil = build_nil_certificate("999/99999")
        self.assertEqual(nil["status"], "no_encumbrance")
        self.assertIn("No encumbrance recorded in the NDUNGU REPORT",
                      nil["legal_statement"])
        self.assertIn("999/99999", nil["legal_statement"])


class SearchTests(TestCase):
    def setUp(self):
        self.p = make_parcel("209/11642", display="209/11642")
        make_finding(self.p, "r1")

    def test_exact_match(self):
        r = run_search("L.R. 209/11642")  # variant normalises to the parcel
        self.assertEqual(r["match_type"], "exact")
        self.assertEqual(r["parcel"], self.p)

    def test_no_match(self):
        self.assertEqual(run_search("999/99999")["match_type"], "none")

    def test_name_fallback(self):
        make_parcel("narrative::n", display="Kariobangi", ptype="narrative")
        Finding.objects.create(
            parcel=Parcel.objects.get(parcel_id_clean="narrative::n"),
            record_id="n", current_holder="Joseph Mwangi", location="Nairobi",
            flag_category="x", source_volume="1", source_page="1")
        r = run_search("Joseph Mwangi")
        self.assertEqual(r["match_type"], "suggestions")

    def test_cross_reference_number_resolves(self):
        """A Cf / Original number embedded in parcel_id_raw (not itself a Parcel
        key) resolves to the parcel it belongs to — we can't rely on the LR alone."""
        p = make_parcel("19095", display="19095")
        make_finding(p, "r_cf",
                     parcel_id_raw="L.R. 19095 Original 12661 Cf 157469 Park View")
        # bare cross-reference number -> the parcel, treated as an exact hit
        r = run_search("157469")
        self.assertEqual(r["match_type"], "exact")
        self.assertEqual(r["parcel"], p)
        # the "Original" number likewise resolves to the same parcel
        self.assertEqual(run_search("12661")["parcel"], p)

    def test_multipart_reference_string_resolves(self):
        """A full multi-part reference the user copies verbatim still finds the
        parcel even though it doesn't normalise to the single LR key."""
        p = make_parcel("19095", display="19095")
        make_finding(p, "r_multi",
                     parcel_id_raw="L.R. 19095 Original 12661 Cf 157469 Park View")
        r = run_search("LR 19095 original 12661")
        self.assertIn(p, r.get("parcels", [r.get("parcel")]))

    def test_alternate_id_does_not_break_nil(self):
        r = run_search("157470")  # a near-miss number absent from every finding
        self.assertEqual(r["match_type"], "none")


# --------------------------------------------------------------------------- #
class SearchAPITests(TestCase):
    def setUp(self):
        self.p = make_parcel("209/11642", display="209/11642")
        make_finding(self.p, "r1")

    def test_search_encumbrance(self):
        res = self.client.get("/api/ndungu/search/", {"q": "209/11642"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "encumbrance_found")
        self.assertIn("certificate_reference", data["metadata"])

    def test_search_nil(self):
        res = self.client.get("/api/ndungu/search/", {"q": "999/99999"})
        data = res.json()
        self.assertEqual(data["status"], "no_encumbrance")

    def test_search_too_short(self):
        res = self.client.get("/api/ndungu/search/", {"q": "2"})
        self.assertEqual(res.status_code, 400)

    def test_every_search_writes_audit_log(self):
        before = CertificateLog.objects.count()
        self.client.get("/api/ndungu/search/", {"q": "209/11642"})
        self.assertEqual(CertificateLog.objects.count(), before + 1)

    def test_verify_resolves_reference(self):
        res = self.client.get("/api/ndungu/search/", {"q": "209/11642"})
        ref = res.json()["metadata"]["certificate_reference"]
        v = self.client.get(f"/api/ndungu/verify/{ref}/")
        self.assertEqual(v.status_code, 200)
        self.assertTrue(v.json()["valid"])

    def test_verify_bogus_reference_404(self):
        v = self.client.get("/api/ndungu/verify/NDR-FAKE-000/")
        self.assertEqual(v.status_code, 404)

    @patch("ndungu.views.render_certificate_pdf", return_value=b"%PDF-1.7 test")
    def test_certificate_pdf_endpoint(self, _mock):
        res = self.client.post(
            "/api/ndungu/certificate/",
            data={"parcel_id": "209/11642"}, content_type="application/json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "application/pdf")


class SourceAwareTests(TestCase):
    """The certificate is exclusively about the dataset the user picked."""

    def setUp(self):
        from litigation.models import ElcCase, ElcCaseIdentifier

        self.p = make_parcel("209/11642", display="209/11642")
        make_finding(self.p, "r1")
        case = ElcCase.objects.create(
            case_citation="ELC Case 7 of 2019", court_station="Nairobi",
            judgment_date="2020-01-02", action="Judgement", parties="A v B",
            outcome_status="Allowed",
        )
        ElcCaseIdentifier.objects.create(
            case=case, raw_identifier="209/11642",
            normalized_identifier=services.normalize_parcel_id("209/11642"),
        )
        # A parcel with ELC litigation only (no Ndung'u record).
        ElcCaseIdentifier.objects.create(
            case=case, raw_identifier="55/1", normalized_identifier=services.normalize_parcel_id("55/1"),
        )

    def _search(self, q, **extra):
        return self.client.get("/api/ndungu/search/", {"q": q, **extra})

    def test_source_defaults_to_ndungu_and_unknown_falls_back(self):
        for extra in ({}, {"source": "bogus"}):
            ref = self._search("209/11642", **extra).json()["metadata"]["certificate_reference"]
            self.assertEqual(CertificateLog.objects.get(certificate_reference=ref).dataset_source, "ndungu")

    def test_elc_pick_is_logged_with_elc_status(self):
        # ELC-only parcel: found in ELC, not in Ndung'u.
        ref = self._search("55/1", source="elc").json()["metadata"]["certificate_reference"]
        log = CertificateLog.objects.get(certificate_reference=ref)
        self.assertEqual((log.dataset_source, log.status), ("elc", "encumbrance_found"))

    def test_status_is_per_dataset_not_combined(self):
        # Same ELC-only parcel viewed as Ndung'u: the combined verdict is still
        # "found" (via ELC) but the Ndung'u certificate itself records none.
        data = self._search("55/1", source="ndungu").json()
        self.assertEqual(data["status"], "encumbrance_found")
        log = CertificateLog.objects.get(certificate_reference=data["metadata"]["certificate_reference"])
        self.assertEqual(log.status, "no_encumbrance")

    def test_verify_reports_dataset_source(self):
        ref = self._search("55/1", source="elc").json()["metadata"]["certificate_reference"]
        v = self.client.get(f"/api/ndungu/verify/{ref}/").json()
        self.assertEqual((v["dataset_source"], v["status"]), ("elc", "encumbrance_found"))

    def test_elc_section_carries_the_disclaimer(self):
        elc = self._search("209/11642").json()["elc"]
        self.assertTrue(elc["found"])
        self.assertIn("reference", elc["disclaimer"])

    @patch("ndungu.views.render_certificate_pdf", return_value=b"%PDF-1.7 test")
    def test_pdf_endpoint_passes_the_source_through(self, mock_render):
        self.client.post("/api/ndungu/certificate/",
                         data={"parcel_id": "55/1", "source": "elc"}, content_type="application/json")
        cert = mock_render.call_args[0][0]
        self.assertEqual(cert["source"], "elc")
        self.client.post("/api/ndungu/certificate/",
                         data={"parcel_id": "55/1"}, content_type="application/json")
        self.assertEqual(mock_render.call_args[0][0]["source"], "ndungu")

    @patch("ndungu.views.render_certificate_pdf", return_value=b"%PDF-1.7 test")
    def test_pdf_endpoint_applies_a_completed_review_to_its_own_parcel_only(self, mock_render):
        from litigation.models import ManualReviewRequest
        from litigation.services import complete_review

        req = ManualReviewRequest.objects.create(
            parcel_id="77/7", contact_email="u@x.co", outcome=ManualReviewRequest.OUTCOME_CLEAR)
        post = lambda q, tok: self.client.post(
            "/api/ndungu/certificate/", data={"parcel_id": q, "source": "elc", "review_token": tok},
            content_type="application/json")
        post("77/7", req.access_token)
        self.assertNotIn("review", mock_render.call_args[0][0])      # still pending
        complete_review(req)
        post("77/7", req.access_token)
        self.assertEqual(mock_render.call_args[0][0]["review"]["review_reference"], req.review_reference)
        post("88/8", req.access_token)
        self.assertNotIn("review", mock_render.call_args[0][0])      # different parcel
        post("77/7", "forged-token")
        self.assertNotIn("review", mock_render.call_args[0][0])

    def _html(self, q, source):
        from django.template.loader import render_to_string
        from ndungu.services import build_combined_certificate, build_pdf_context
        from litigation.services import find_litigation

        parcel = Parcel.objects.filter(parcel_id_clean=q).first()
        cert = build_combined_certificate(parcel, find_litigation(q), q)
        cert["source"] = source
        meta = {"searched_parcel_id": q, "certificate_reference": "REF-1",
                "generated_display": "22 Oct 2026, 10:00 EAT"}
        return render_to_string("ndungu/certificate.html", build_pdf_context(cert, meta))

    def test_elc_pdf_template_shows_cases_not_ndungu_sections(self):
        html = self._html("209/11642", "elc")
        self.assertIn("Property Litigation Search Certificate", html)
        self.assertIn("ELC Case 7 of 2019", html)
        self.assertIn("Litigation found", html)
        self.assertNotIn("Parcel summary", html)

    def test_ndungu_pdf_template_is_ndungu_only(self):
        html = self._html("209/11642", "ndungu")
        self.assertIn("Certificate of Search on the Ndung", html)
        self.assertIn("Parcel summary", html)
        self.assertNotIn("ELC Case 7 of 2019", html)

    def test_elc_pdf_nil(self):
        html = self._html("77/7", "elc")
        self.assertIn("No litigation record found", html)
        self.assertIn("no case recorded against this property", html)

    def test_elc_nil_without_review_says_so_and_does_not_tell_the_reader_to_act(self):
        html = self._html("77/7", "elc")
        # Definitive and tied to the index, with no repeated timestamp, no count
        # and no hedge about a review that hasn't happened.
        self.assertIn("No Environment and Land Court case in the decisions indexed by Landledger Ltd names this property", html)
        self.assertNotRegex(html, r"among the [0-9,]+ decisions")
        self.assertNotIn("Not confirmed by manual review", html)
        self.assertNotIn("Basis of this result", html)
        self.assertNotIn("as at ", html)
        self.assertNotIn("request a manual review", html)

    def test_elc_nil_with_review_is_marked_confirmed(self):
        from django.template.loader import render_to_string
        from ndungu.services import build_combined_certificate, build_pdf_context

        cert = build_combined_certificate(None, None, "77/7")
        cert["source"] = "elc"
        cert["review"] = {"review_reference": "MR-20261023-ABC123", "reviewed_display": "23 Oct 2026"}
        meta = {"searched_parcel_id": "77/7", "certificate_reference": "REF-1",
                "generated_display": "23 Oct 2026, 10:00 EAT"}
        html = render_to_string("ndungu/certificate.html", build_pdf_context(cert, meta))
        self.assertIn("Confirmed by Landledger manual review (ref. MR-20261023-ABC123, 23 Oct 2026)", html)
        self.assertIn("located and indexed", html)
        self.assertNotIn("Not confirmed by manual review", html)
        self.assertNotIn("decisions indexed by Landledger Ltd names this property", html)

    def test_ndungu_nil_points_to_the_litigation_search(self):
        html = self._html("77/7", "ndungu")
        self.assertIn("No encumbrance recorded", html)
        self.assertIn("Property Litigation Search", html)

    def test_pdf_download_filenames_follow_the_convention(self):
        # Ndung'u: matched parcel + outcome. ELC: the search term + outcome.
        for q, src, want in [
            ("209/11642", "ndungu", "Ndungu_Report_Search_Certificate_209-11642_Adverse_Record_Found.pdf"),
            ("77/7", "ndungu", "Ndungu_Report_Search_Certificate_77-7_No_Adverse_Record.pdf"),
            ("209/11642", "elc", "Litigation_Search_Certificate_209-11642_Litigation_Found.pdf"),
            ("77/7", "elc", "Litigation_Search_Certificate_77-7_No_Record.pdf"),
        ]:
            with patch("ndungu.views.render_certificate_pdf", return_value=b"%PDF"):
                res = self.client.post("/api/ndungu/certificate/",
                                       data={"parcel_id": q, "searched_term": q, "source": src},
                                       content_type="application/json")
            self.assertIn(f'filename="{want}"', res["Content-Disposition"])


class CertificateHelperTests(TestCase):
    def test_decision_dates_are_tidied_without_guessing(self):
        from litigation.services import format_decision_date as f

        self.assertEqual(f("19 February 2026"), "19 February 2026")
        self.assertEqual(f("6   October 2020"), "6 October 2020")
        self.assertEqual(f("2/19/2026"), "19 February 2026")   # M/D, unambiguous
        self.assertEqual(f("19/2/2026"), "19 February 2026")   # D/M, unambiguous
        self.assertEqual(f("3/4/2026"), "3/4/2026")            # ambiguous: left as entered
        self.assertEqual(f("https://new.kenyalaw.org/x"), "")  # shifted sheet column
        self.assertEqual(f(None), "")

    def test_elc_rows_split_title_from_neutral_citation(self):
        from ndungu.services import elc_rows

        row = elc_rows([{"case_citation": "A v B & 2 others [2015]\xa0KEELC\xa0728\xa0(KLR)",
                         "court_station": "NAIROBI", "url_link": "https://x.org/a"}])[0]
        self.assertEqual(row["title"], "A v B & 2 others")
        self.assertEqual(row["neutral"], "[2015] KEELC 728 (KLR)")
        self.assertEqual((row["county"], row["source_display"]), ("Nairobi", "x.org/a"))
        plain = elc_rows([{"case_citation": "Just a title"}])[0]
        self.assertEqual((plain["title"], plain["neutral"]), ("Just a title", ""))

    def test_report_pages_dedupes_and_uses_roman_volumes(self):
        from ndungu.services import report_pages

        tl = [{"volume": "1", "page": "60"}, {"volume": "1", "page": "60"},
              {"volume": "3", "page": "95"}, {"volume": "", "page": "9"}]
        self.assertEqual(report_pages(tl), "Vol I, Page 60; Vol III, Page 95")


class ImportNdunguTests(TestCase):
    """import_ndungu must load each finding exactly once."""

    def test_finding_count_matches_the_searchable_csvs(self):
        import csv
        import os
        from django.conf import settings
        from django.core.management import call_command

        def rows(name):
            path = os.path.join(settings.BASE_DIR, "data", "ndungu", name)
            with open(path, newline="", encoding="utf-8") as fh:
                return sum(1 for _ in csv.DictReader(fh))

        call_command("import_ndungu", "--flush", verbosity=0)
        expected = rows("master_findings.csv") + rows("aux_findings.csv")
        self.assertEqual(Finding.objects.count(), expected)

        # master_findings legitimately repeats a record_id (one source record can
        # name several parcels), but aux records are one row each -- seeing any
        # of them twice means a second loader re-imported the flagged_* files.
        path = os.path.join(settings.BASE_DIR, "data", "ndungu", "aux_findings.csv")
        with open(path, newline="", encoding="utf-8") as fh:
            aux_ids = [r["record_id"] for r in csv.DictReader(fh)]
        loaded = Finding.objects.filter(record_id__in=aux_ids).count()
        self.assertEqual(loaded, len(aux_ids))


class ElcCertificateDisclaimerTests(TestCase):
    """The ELC certificate closes with disclaimer points 1 and 3 (not the
    manual-review pointer); the Ndung'u certificates carry none."""

    def setUp(self):
        from litigation.models import ElcCase, ElcCaseIdentifier

        self.p = make_parcel("209/11642", display="209/11642")
        make_finding(self.p, "r1")
        case = ElcCase.objects.create(case_citation="ELC Case 7 of 2019", county="Nairobi")
        ElcCaseIdentifier.objects.create(
            case=case, raw_identifier="209/11642",
            normalized_identifier=services.normalize_parcel_id("209/11642"),
        )

    def _html(self, q, source):
        from django.template.loader import render_to_string
        from litigation.services import find_litigation
        from ndungu.services import build_combined_certificate, build_pdf_context

        parcel = Parcel.objects.filter(parcel_id_clean=q).first()
        cert = build_combined_certificate(parcel, find_litigation(q), q)
        cert["source"] = source
        meta = {"searched_parcel_id": q, "certificate_reference": "REF-1",
                "generated_display": "26 Oct 2026, 10:17 EAT"}
        return render_to_string("ndungu/certificate.html", build_pdf_context(cert, meta))

    def test_both_elc_states_carry_disclaimers_one_and_three(self):
        for q in ("209/11642", "77/7"):  # found, then nil
            html = self._html(q, "elc")
            self.assertIn("currently indexed by Landledger Ltd", html)
            self.assertIn("does not replace, an official Lands Registry search", html)
            self.assertNotIn("manual review by quoting", html)  # point 2 stays out

    def test_disclaimer_dates_the_index_not_the_search(self):
        html = self._html("77/7", "elc")
        self.assertNotIn("as of 26 Oct 2026, 10:17 EAT", html)
        self.assertIn("as of ", html)  # the index's last-updated date

    def test_ndungu_certificates_close_with_the_ndungu_report_disclaimer(self):
        import html as htmllib

        for q in ("209/11642", "77/7"):  # found, then nil
            html = htmllib.unescape(self._html(q, "ndungu"))
            self.assertIn("Disclaimer", html)
            self.assertIn("Based on the 2004 Ndung'u Report", html)
            self.assertIn("Not a legal title or a substitute for an official Ministry of Lands Registry search", html)
            # ...and none of the litigation certificate's wording
            self.assertNotIn("currently indexed by Landledger Ltd", html)

    def test_index_stats_report_count_and_freshness(self):
        stats = services.elc_index_stats()
        self.assertEqual(stats["count"], 1)
        self.assertEqual(stats["count_display"], "1")
        self.assertRegex(stats["as_of"], r"^\d{2} [A-Z][a-z]{2} \d{4}$")


class ConversionBlockTests(TestCase):
    """LR conversion data is a label/value grid like the parcel summary."""

    INFO = {"matches": [{
        "old_lr_no": "209/11642", "new_lr_number": "NAIROBI/BLOCK 30/32", "scheme_name": "LOWER HILL",
        "area_ha": "0.2100", "registration_unit": "Nairobi",
        "citations": [{"gazette_vol_no": "Vol. CXXIV—No. 94", "gazette_date": "20th May 2022"}],
    }]}

    def test_fields_come_in_rows_of_two_with_gazetted_beside_the_registration_unit(self):
        (block,) = services.conversion_blocks(self.INFO)
        labels = [[c["label"] for c in row] for row in block["rows"]]
        self.assertEqual(labels, [["Old LR number", "New LR number"], ["Scheme", "Area (Ha)"],
                                  ["Registration unit", "Gazetted"]])
        self.assertEqual(block["rows"][-1][1]["value"], "Vol. CXXIV—No. 94 (20th May 2022)")

    def test_missing_optional_fields_are_skipped_not_dashed(self):
        (block,) = services.conversion_blocks({"matches": [{"old_lr_no": "1/2", "new_lr_number": "N/1"}]})
        self.assertEqual([[c["label"] for c in r] for r in block["rows"]], [["Old LR number", "New LR number"]])

    def test_no_conversion_means_no_blocks(self):
        self.assertEqual(services.conversion_blocks(None), [])

    def test_section_renders_on_every_certificate_kind(self):
        from django.template.loader import render_to_string

        for source in ("ndungu", "elc"):
            cert = services.build_combined_certificate(None, None, "209/11642")
            cert["source"] = source
            cert["conversion_info"] = self.INFO
            meta = {"searched_parcel_id": "209/11642", "certificate_reference": "R1", "generated_display": "x"}
            html = render_to_string("ndungu/certificate.html", services.build_pdf_context(cert, meta))
            for text in ("LR number conversion", "Old LR number", "NAIROBI/BLOCK 30/32", "LOWER HILL", "Gazetted"):
                self.assertIn(text, html, f"{text!r} missing on the {source} certificate")


class SearchSubjectTests(TestCase):
    """Certificates must not call a person, company or place a 'property'."""

    def test_parcel_numbers_read_as_this_property(self):
        for term in ("209/11642", "LR No. 3589/6", "Title LR Ngong/Ngong/10915", "Ondiri 24", "Ondiri24", "", None):
            self.assertEqual(services.search_subject(term)["ref"], "this property", term)

    def test_names_entities_and_places_are_quoted_back(self):
        for term in ("Gospel Revival Centre", "Mary Wamatha Kaittany", "Karura", "NSSF"):
            subj = services.search_subject(term)
            self.assertEqual(subj["ref"], f"\u201c{term}\u201d")
            self.assertEqual(subj["kind"], "name")

    def test_long_terms_are_shortened(self):
        subj = services.search_subject("A" * 90)
        self.assertLessEqual(len(subj["ref"]), 64)
        self.assertIn("\u2026", subj["ref"])

    def _html(self, term, source, found=False):
        from django.template.loader import render_to_string

        cert = services.build_combined_certificate(None, {"disclaimer": "d", "matches": [
            {"case_citation": "A v B [2020] KEELC 1 (KLR)"}]} if found else None, term)
        cert["source"] = source
        meta = {"searched_parcel_id": term, "certificate_reference": "R1", "generated_display": "x"}
        return render_to_string("ndungu/certificate.html", services.build_pdf_context(cert, meta))

    def test_no_record_statements_follow_what_was_searched(self):
        name = self._html("Gospel Revival Centre", "elc")
        self.assertIn("names \u201cGospel Revival Centre\u201d.", name)
        self.assertIn("no case recorded against \u201cGospel Revival Centre\u201d", name)
        self.assertNotIn("this property", name)
        parcel = self._html("77/7", "elc")
        self.assertIn("names this property.", parcel)
        self.assertIn("no case recorded against this property", parcel)

    def test_found_banner_and_ndungu_callout_follow_what_was_searched(self):
        self.assertIn("\u201cGospel Revival Centre\u201d is named in Environment and Land Court proceedings",
                      self._html("Gospel Revival Centre", "elc", found=True))
        self.assertIn("This property is named in", self._html("77/7", "elc", found=True))
        self.assertIn("in respect of \u201cKaittany\u201d by running a", self._html("Kaittany", "ndungu"))
        self.assertIn("in respect of this property by running a", self._html("77/7", "ndungu"))


class DisplayTermTests(TestCase):
    def test_names_typed_in_one_case_read_in_proper_case(self):
        for typed, shown in [
            ("mary kaittany", "Mary Kaittany"),
            ("MARY KAITTANY", "Mary Kaittany"),
            ("gospel revival centre", "Gospel Revival Centre"),
            ("ministry of lands and settlement", "Ministry of Lands and Settlement"),
            ("jean-paul wamatha", "Jean-Paul Wamatha"),
            ("o'brien holdings", "O'Brien Holdings"),
            ("  mary   kaittany ", "Mary Kaittany"),
        ]:
            self.assertEqual(services.display_term(typed), shown, typed)

    def test_acronyms_mixed_case_and_parcel_numbers_are_left_alone(self):
        for typed in ("NSSF", "KPA", "McDonald Holdings", "Mary Wamatha Kaittany", "209/11642",
                      "LR No. 3589/6", "Ondiri24", "Ngong/Ngong/10915"):
            self.assertEqual(services.display_term(typed), typed, typed)

    def test_empty_is_empty(self):
        self.assertEqual(services.display_term(""), "")
        self.assertEqual(services.display_term(None), "")


class CertificateMetadataTests(TestCase):
    """'Searched' reads in proper case; 'Matched' names the record we resolved to."""

    def setUp(self):
        self.p = make_parcel("11927/8", display="11927/8")
        make_finding(self.p, "r1")

    def _meta(self, **data):
        with patch("ndungu.views.render_certificate_pdf", return_value=b"%PDF") as mock_render:
            self.client.post("/api/ndungu/certificate/", data={"source": "ndungu", **data},
                             content_type="application/json")
        return mock_render.call_args[0][1]

    def test_name_search_shows_proper_case_searched_and_the_matched_parcel(self):
        meta = self._meta(parcel_id="11927/8", searched_term="mary kaittany")
        self.assertEqual(meta["searched_parcel_id"], "Mary Kaittany")
        self.assertEqual(meta["matched_parcel_id"], "11927/8")

    def test_direct_parcel_search_has_no_matched(self):
        meta = self._meta(parcel_id="11927/8", searched_term="11927/8")
        self.assertEqual(meta["searched_parcel_id"], "11927/8")
        self.assertNotIn("matched_parcel_id", meta)

    def test_matched_is_not_repeated_when_only_the_case_differs(self):
        # a name that resolves to a record carrying that same name
        parcel = make_parcel("narrative::x", display="Kenya Ports Authority")
        make_finding(parcel, "r2")
        meta = self._meta(parcel_id="narrative::x", searched_term="kenya ports authority")
        self.assertEqual(meta["searched_parcel_id"], "Kenya Ports Authority")
        self.assertNotIn("matched_parcel_id", meta)


class JourneysDoNotMixTests(TestCase):
    """An ELC search stays in the ELC journey; a Ndung'u search stays in Ndung'u."""

    def setUp(self):
        self.p = make_parcel("11927/8", display="11927/8")
        make_finding(self.p, "r1", current_holder="Mary Wamatha Kaittany", prior_party="Mary Wamatha Kaittany")

    def _get(self, source, q="Mary Kaittany"):
        return self.client.get("/api/ndungu/search/", {"q": q, "source": source}).json()

    def test_ndungu_search_by_name_opens_ndungu_suggestions(self):
        data = self._get("ndungu")
        self.assertEqual(data["status"], "suggestions")
        self.assertTrue(data["suggestions"])

    def test_elc_search_by_name_never_returns_ndungu_suggestions(self):
        data = self._get("elc")
        self.assertNotEqual(data["status"], "suggestions")
        self.assertNotIn("suggestions", data)
        self.assertFalse(data["elc"]["found"])          # an ELC result...
        self.assertEqual(data["ndungu"]["suggestions"], 1)  # ...that only counts the Ndung'u matches
        self.assertNotIn("tier_b_timeline", data["ndungu"])  # and carries none of their data

    def test_elc_name_search_is_logged_as_an_elc_certificate(self):
        data = self._get("elc")
        log = CertificateLog.objects.get(certificate_reference=data["metadata"]["certificate_reference"])
        self.assertEqual((log.dataset_source, log.status), ("elc", "no_encumbrance"))

    def test_elc_name_search_with_no_ndungu_match_has_no_hint(self):
        data = self._get("elc", q="Zzyzx Nobody")
        self.assertNotIn("suggestions", data["ndungu"])

    def test_exact_parcel_search_is_unchanged_in_both_modes(self):
        for source in ("ndungu", "elc"):
            data = self._get(source, q="11927/8")
            self.assertTrue(data["ndungu"]["found"], source)


class ElcCaseListTests(TestCase):
    """A search matching several ELC cases lists them; one case opens its own certificate."""

    def setUp(self):
        from litigation.models import ElcCase

        self.a = ElcCase.objects.create(case_citation="Karura Residents v Kenya Forest Service [2021] KEELC 1 (KLR)",
                                        parties="KARURA RESIDENTS; KENYA FOREST SERVICE", county="Nairobi",
                                        court_station="Milimani", url_link="http://x/1", outcome_status="Dismissed")
        self.b = ElcCase.objects.create(case_citation="Karura Estate v Njoroge [2022] KEELC 2 (KLR)",
                                        parties="KARURA ESTATE; NJOROGE", county="Nairobi")

    def _get(self, q, source="elc"):
        return self.client.get("/api/ndungu/search/", {"q": q, "source": source}).json()

    def test_several_cases_are_listed_without_their_detail(self):
        data = self._get("Karura")
        self.assertEqual(data["status"], "suggestions")
        self.assertEqual(data["list_kind"], "elc")
        self.assertEqual(len(data["suggestions"]), 2)
        first = data["suggestions"][0]
        self.assertEqual(set(first), {"parcel_id", "display", "context"})
        self.assertNotIn("litigation_info", data)
        self.assertNotIn("Dismissed", str(data))

    def test_the_list_is_logged_as_suggestions_for_the_elc_dataset(self):
        data = self._get("Karura")
        log = CertificateLog.objects.get(certificate_reference=data["metadata"]["certificate_reference"])
        self.assertEqual((log.dataset_source, log.status), ("elc", "suggestions"))

    def test_picking_one_opens_a_certificate_for_that_case_only(self):
        key = self._get("Karura")["suggestions"][0]["parcel_id"]
        data = self._get(key)
        self.assertEqual(data["status"], "encumbrance_found")
        self.assertEqual(len(data["elc"]["matches"]), 1)
        self.assertEqual(data["elc"]["match_basis"], "parties")   # keeps the name caution
        self.assertEqual(data["overview"]["parcel"], data["elc"]["matches"][0]["case_citation"])

    def test_the_pdf_for_a_picked_case_covers_that_case_only(self):
        key = self._get("Karura")["suggestions"][0]["parcel_id"]
        resp = self.client.post("/api/ndungu/certificate/", data={"parcel_id": key, "searched_term": "karura", "source": "elc"},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_the_ledger_counts_the_elc_cases_matched(self):
        key = self._get("Karura")["suggestions"][0]["parcel_id"]
        data = self._get(key)
        ref = data["metadata"]["certificate_reference"]
        self.assertEqual(self.client.get(f"/api/ndungu/verify/{ref}/").json()["results_count"], 1)

    def test_a_single_case_is_not_listed(self):
        self.assertEqual(self._get("Karura Estate")["status"], "encumbrance_found")

    def test_ndungu_searches_are_not_affected(self):
        self.assertNotEqual(self._get("Karura", source="ndungu").get("list_kind"), "elc")

    def test_an_unknown_case_key_is_a_nil_result_not_an_error(self):
        data = self._get("elc-case:999999")
        self.assertFalse(data["elc"]["found"])


class ConversionBridgesNumbersTests(TestCase):
    """The Ndung'u report records the OLD LR number; searching the NEW one must still find it."""

    def setUp(self):
        from conversions.models import LrConversion

        self.p = make_parcel("209/11642", display="209/11642")
        make_finding(self.p, "r1", current_holder="National Social Security Fund")
        LrConversion.objects.create(old_lr_no="209/11642", new_lr_number="NAIROBI/BLOCK 30/32")

    def test_searching_the_new_number_finds_the_old_numbers_encumbrance(self):
        for q in ("NAIROBI/BLOCK 30/32", "209/11642"):
            data = self.client.get("/api/ndungu/search/", {"q": q}).json()
            self.assertEqual(data["status"], "encumbrance_found", q)
            self.assertTrue(data["ndungu"]["found"], q)
            self.assertEqual(data["overview"]["parcel"], "209/11642")   # the number it is filed under

    def test_the_pdf_by_the_new_number_covers_the_encumbrance(self):
        resp = self.client.post("/api/ndungu/certificate/", data={"parcel_id": "NAIROBI/BLOCK 30/32", "searched_term": "NAIROBI/BLOCK 30/32"},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("_Adverse_Record_Found.pdf", resp["Content-Disposition"])

    def test_an_unrelated_new_number_stays_nil(self):
        from conversions.models import LrConversion

        LrConversion.objects.create(old_lr_no="1/1", new_lr_number="NAIROBI/BLOCK 1/1")
        data = self.client.get("/api/ndungu/search/", {"q": "NAIROBI/BLOCK 1/1"}).json()
        self.assertFalse(data["ndungu"]["found"])


class ElcNilStatementTests(TestCase):
    def test_parcels_stay_parcels_and_names_are_quoted(self):
        self.assertEqual(services.elc_nil_statement("209/11642"),
                         "No ELC litigation case recorded against parcel 209/11642.")
        self.assertEqual(services.elc_nil_statement("mary kaittany"),
                         "No ELC litigation case recorded against \u201cMary Kaittany\u201d.")


class DisclaimerNeverCrossesJourneysTests(TestCase):
    """Each certificate carries only its own dataset's disclaimer."""

    def test_litigation_certificate_has_no_ndungu_disclaimer(self):
        from django.template.loader import render_to_string

        cert = services.build_combined_certificate(None, None, "77/7")
        cert["source"] = "elc"
        meta = {"searched_parcel_id": "77/7", "certificate_reference": "R1", "generated_display": "x"}
        html = render_to_string("ndungu/certificate.html", services.build_pdf_context(cert, meta))
        import html as htmllib

        html = htmllib.unescape(html)
        self.assertIn("currently indexed by Landledger Ltd", html)
        self.assertNotIn("Based on the 2004 Ndung'u Report", html)


class RequestAPageCalloutTests(TestCase):
    """Asking for the report's pages is offered in the results modal, not on the certificate."""

    def test_the_certificate_no_longer_carries_the_request_a_page_line(self):
        from django.template.loader import render_to_string

        p = make_parcel("209/11642", display="209/11642")
        make_finding(p, "r1")
        cert = services.build_combined_certificate(p, None, "209/11642")
        cert["source"] = "ndungu"
        meta = {"searched_parcel_id": "209/11642", "certificate_reference": "NDR-1", "generated_display": "x"}
        html = render_to_string("ndungu/certificate.html", services.build_pdf_context(cert, meta))
        self.assertNotIn("Request a copy of the relevant page", html)


class PageRequestTests(TestCase):
    """The user leaves an email/phone; support gets the reference, what was searched and matched."""

    def setUp(self):
        from django.core import mail  # noqa: F401

        self.ref = services.log_search("209/11642", "209/11642", 2, "encumbrance_found")

    def _post(self, **kw):
        body = {"certificate_reference": self.ref, "contact": "a@b.co", "searched": "Mary Kaittany",
                "matched": "11927/8", "pages": "Vol I, Page 60"}
        body.update(kw)
        return self.client.post("/api/ndungu/request-pages/", data=body, content_type="application/json")

    def test_emails_support_with_reference_searched_matched_and_contact(self):
        from django.core import mail

        self.assertEqual(self._post().status_code, 201)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, [settings.SUPPORT_EMAIL])
        for want in (self.ref, "Searched: Mary Kaittany", "Matched: 11927/8", "Vol I, Page 60", "Contact: a@b.co"):
            self.assertIn(want, msg.body)

    def test_needs_a_contact_and_a_real_reference(self):
        self.assertEqual(self._post(contact="").status_code, 400)
        self.assertEqual(self._post(contact="not@valid").status_code, 400)
        self.assertEqual(self._post(certificate_reference="NDR-NOPE").status_code, 404)

    def test_a_phone_number_is_accepted(self):
        self.assertEqual(self._post(contact="0712345678").status_code, 201)


class ContactNumberTests(TestCase):
    def test_certificate_whatsapp_link_uses_the_current_number(self):
        from django.test import override_settings

        links = services.contact_links("NDR-1", "request a copy")
        self.assertTrue(links["whatsapp"].startswith("https://wa.me/254180049253?text="), links["whatsapp"])
        self.assertIn("NDR-1", links["whatsapp"])
        # a deployment override still wins over the default
        with override_settings(CERTIFICATE_WHATSAPP_URL="https://wa.me/254700000001"):
            self.assertTrue(services.contact_links("NDR-1", "x")["whatsapp"].startswith("https://wa.me/254700000001?text="))


class NameSearchCertificateTests(TestCase):
    """What the certificate says when the cases were found by a party name."""

    def _html(self, term, source, litigation=None, outcome="Dismissed", total=None, truncated=False):
        from django.template.loader import render_to_string

        info = None
        if litigation:
            info = {"disclaimer": "d", "match_basis": litigation, "total": total or 1, "truncated": truncated,
                    "matches": [{"case_citation": "A v B [2020] KEELC 1 (KLR)", "county": "Nairobi",
                                 "outcome_status": outcome, "parties": "A; B"}]}
        cert = services.build_combined_certificate(None, info, term)
        cert["source"] = source
        meta = {"searched_parcel_id": term, "certificate_reference": "R1", "generated_display": "x"}
        return render_to_string("ndungu/certificate.html", services.build_pdf_context(cert, meta))

    def test_party_matches_say_so_and_carry_the_name_caution(self):
        html = self._html("Mary Kaittany", "elc", litigation="parties")
        self.assertIn("is named as a party in Environment and Land Court proceedings", html)
        self.assertIn("matches party names only", html)
        # an identifier match carries neither
        html = self._html("209/11642", "elc", litigation="identifier")
        self.assertIn("This property is named in Environment and Land Court proceedings", html)
        self.assertNotIn("matches party names only", html)

    def test_the_banner_shows_the_true_total_and_a_truncation_note(self):
        html = self._html("John Kamau", "elc", litigation="parties", total=88, truncated=True)
        self.assertIn('<div class="n">88</div>', html)
        self.assertIn("most recent of 88 cases that name", html)

    def test_a_long_outcome_is_printed_across_the_row_not_in_the_narrow_column(self):
        long_text = "a declaration is hereby issued that the Plaintiff is the lawful proprietor " * 6
        html = self._html("209/11642", "elc", litigation="identifier", outcome=long_text)
        self.assertEqual(html.count(long_text.strip()), 1)          # printed once, in full
        self.assertIn("Outcome: " + long_text.strip()[:30], html)  # in the full-width detail row
        short = self._html("209/11642", "elc", litigation="identifier", outcome="Dismissed")
        self.assertNotIn("Outcome: Dismissed", short)             # a short outcome stays in its cell

    def test_ndungu_statement_keeps_the_prd_wording_for_parcels_and_quotes_names(self):
        self.assertIn("against parcel 2/267", services.build_nil_certificate("2/267")["legal_statement"])
        self.assertIn("against “Mary Kaittany”",
                      services.build_nil_certificate("mary kaittany")["legal_statement"])

    def test_elc_section_exposes_basis_total_and_the_index_date(self):
        info = {"disclaimer": "d", "match_basis": "parties", "total": 4, "truncated": False,
                "matches": [{"case_citation": "x"}]}
        elc = services.build_combined_certificate(None, info, "Mary Kaittany")["elc"]
        self.assertEqual((elc["match_basis"], elc["total"]), ("parties", 4))
        self.assertIn("index_as_of", elc)

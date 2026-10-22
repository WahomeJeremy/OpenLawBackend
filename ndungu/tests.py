"""Unit tests for the Ndung'u encumbrance engine (models, services, API)."""
from unittest.mock import patch

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

    def test_ndungu_nil_points_to_the_litigation_search(self):
        html = self._html("77/7", "ndungu")
        self.assertIn("No encumbrance recorded", html)
        self.assertIn("Property Litigation Search", html)

    def test_pdf_download_filenames_follow_the_convention(self):
        # Ndung'u: matched parcel + outcome. ELC: the search term + outcome.
        for q, src, want in [
            ("209/11642", "ndungu", "Ndungu_Report_Search_Certificate_209-11642_Encumbrance_Found.pdf"),
            ("77/7", "ndungu", "Ndungu_Report_Search_Certificate_77-7_No_Encumbrance.pdf"),
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
        from ndungu.services import format_decision_date as f

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

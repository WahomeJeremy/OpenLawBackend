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

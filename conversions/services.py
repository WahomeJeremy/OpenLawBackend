"""LR-conversion lookup: given a query, find any gazetted old-LR <-> new-LR
reissue under the 2017 Land Registration (Registration Units) Order.

This is reference data only -- it proves a parcel-number change, never an
encumbrance -- so callers must surface DISCLAIMER alongside any match.
"""
from ndungu.models import normalize_parcel_id

from .models import LrConversion

DISCLAIMER = (
    "This parcel's LR number was reissued under the 2017 Land Registration "
    "(Registration Units) conversion. This is reference information only "
    "-- it is not an encumbrance finding."
)


def _citation_payload(c):
    return {
        "gazette_notice_no": c.gazette_notice_no,
        "gazette_vol_no": c.gazette_vol_no,
        "gazette_date": c.gazette_date,
        "source_pdf": c.source_pdf,
        "source_page": c.source_page,
    }


def _conversion_payload(conv, matched_on):
    return {
        "old_lr_no": conv.old_lr_no,
        "new_lr_number": conv.new_lr_number,
        "new_parcel_no": conv.new_parcel_no,
        "block": conv.block,
        "scheme_name": conv.scheme_name,
        "area_ha": conv.area_ha,
        "registration_unit": conv.registration_unit,
        "matched_on": matched_on,  # "old" | "new" -- which side the query hit
        "citations": [_citation_payload(c) for c in conv.citations.all()],
    }


def find_conversions(raw_query):
    """Search both directions (old LR -> new LR and new LR/block/parcel ->
    old LR) for an exact normalized match. Returns a payload dict with
    `matches` + `disclaimer`, or None if nothing matched."""
    q = normalize_parcel_id(raw_query)
    if not q:
        return None

    matches = []
    seen_ids = set()

    for conv in LrConversion.objects.filter(normalized_old_lr=q).prefetch_related("citations"):
        matches.append(_conversion_payload(conv, "old"))
        seen_ids.add(conv.id)

    for conv in LrConversion.objects.filter(normalized_new_lr=q).prefetch_related("citations"):
        if conv.id in seen_ids:
            continue
        matches.append(_conversion_payload(conv, "new"))
        seen_ids.add(conv.id)

    if not matches:
        return None
    return {"disclaimer": DISCLAIMER, "matches": matches}

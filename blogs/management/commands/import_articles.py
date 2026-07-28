"""Seed the 4 legal-resource categories + the 17 articles into Category/Article.

Categories carry the journey title / bold tagline / descriptive line that the
frontend renders. Articles (HTML body) are loaded from blogs/data/articles.json
and linked to their category. Idempotent — keyed on Category.title / Article.slug.

Usage:  python manage.py import_articles
"""
import json
import os

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from blogs.models import Category, Article

DATA = os.path.join(settings.BASE_DIR, "blogs", "data", "articles.json")

# key -> Category fields. title = journey stage, tagline = bold line, description = explainer.
# Ordered as a land-transaction lifecycle: search -> acquire -> consents ->
# conveyancing -> transfer/succession -> use/develop -> protect.
CATEGORIES = [
    {
        "key": "search", "order": 1, "title": "Search & Due Diligence",
        "tagline": "Before You Pay: Search, Verify, Investigate",
        "description": "Run the searches and read the register like a lawyer — confirm who really owns the land and uncover hidden claims before a single shilling changes hands.",
    },
    {
        "key": "acquire", "order": 2, "title": "Ways to Acquire",
        "tagline": "Routes to Ownership: How Land Is Acquired",
        "description": "The lawful ways to come to own land in Kenya — the recognised methods of acquiring title, buying through a co-operative, and how public land is allocated.",
    },
    {
        "key": "consents", "order": 3, "title": "Consents & Clearances",
        "tagline": "Clearing the Way: Consents Before You Register",
        "description": "The approvals a dealing needs before it can be registered — Land Control Board and mandatory spousal consent, plus the rates and rent clearances that unlock a transfer.",
    },
    {
        "key": "conveyancing", "order": 4, "title": "Conveyancing & Costs",
        "tagline": "Closing the Deal: Conveyancing, Duty & Authority",
        "description": "The paperwork and money that complete a transaction — stamp duty, capital gains tax and land rates, and using a power of attorney to execute a dealing on your behalf.",
    },
    {
        "key": "transfer", "order": 5, "title": "Transfer & Succession",
        "tagline": "Passing It On: Transfers, Death & Court Orders",
        "description": "How title moves after you own it — passing land by operation of law on death through transmission, and transferring property by a court vesting order.",
    },
    {
        "key": "use", "order": 6, "title": "Use & Develop",
        "tagline": "Working the Land: Leases, Licences & Subdivision",
        "description": "Dealings short of outright sale — granting, extending and ending leases and licences, and subdividing or surveying land into new titles.",
    },
    {
        "key": "protect", "order": 7, "title": "Protect Your Title",
        "tagline": "Locking It Down: Cautions, Claims & Recovery",
        "description": "Defend your investment against fraud, adverse possession and lost records — with cautions, inhibitions and restrictions, and by reconstructing a lost register or title.",
    },
]


class Command(BaseCommand):
    help = "Seed legal-resource categories + articles into Category/Article."

    def handle(self, *args, **options):
        key_to_cat = {}
        for c in CATEGORIES:
            cat, _ = Category.objects.update_or_create(
                title=c["title"],
                defaults={
                    "tagline": c["tagline"],
                    "description": c["description"],
                    "order": c["order"],
                    "is_active": True,
                },
            )
            key_to_cat[c["key"]] = cat

        if not os.path.exists(DATA):
            self.stderr.write(f"Missing {DATA}")
            return
        with open(DATA, encoding="utf-8") as fh:
            articles = json.load(fh)

        created = updated = 0
        for a in articles:
            cat = key_to_cat.get(a["category"])
            if cat is None:
                self.stderr.write(f"Unknown category '{a['category']}' for {a['title']}")
                continue
            slug = a.get("slug") or slugify(a["title"])
            _, was_created = Article.objects.update_or_create(
                slug=slug,
                defaults={
                    "category": cat,
                    "title": a["title"],
                    "content": a["content"],
                    "excerpt": (a.get("excerpt") or "")[:500],
                    "order": a.get("order", 0),
                    "is_published": a.get("is_published", True),
                },
            )
            created += was_created
            updated += not was_created

        self.stdout.write(self.style.SUCCESS(
            f"Categories: {Category.objects.count()} | "
            f"Articles: {created} created, {updated} updated, {Article.objects.count()} total"
        ))
        for c in Category.objects.all().order_by("order"):
            self.stdout.write(f"  {c.title}: {c.articles.count()} articles")

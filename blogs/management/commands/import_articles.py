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
CATEGORIES = [
    {
        "key": "due_diligence", "order": 1, "title": "Due Diligence",
        "tagline": "The Buyer’s Checklist: Verify Before You Pay",
        "description": "Don’t buy a lawsuit. Verify ownership, investigate the Green Card, and spot hidden legal claims before you sign a contract.",
    },
    {
        "key": "purchase", "order": 2, "title": "Purchase",
        "tagline": "Path to Ownership: Navigating Your Purchase",
        "description": "From sale agreements to stamp duty — the legal mechanics of acquiring land, whether through a co-operative, shares, or sectional title.",
    },
    {
        "key": "transfer", "order": 3, "title": "Transfer",
        "tagline": "Moving Title Deeds: Transfers, Leases & Inheritance",
        "description": "Ownership changes, and so do the rules. Navigate transferring land through inheritance, managing leases, and handling lost title deeds.",
    },
    {
        "key": "caution", "order": 4, "title": "Caution",
        "tagline": "Protecting Your Title: Managing Cautions & Risks",
        "description": "Secure your investment against fraud or third-party interference using cautions, inhibitions, and restrictions to lock your title.",
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

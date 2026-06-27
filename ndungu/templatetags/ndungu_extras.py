from django import template

register = template.Library()


@register.filter
def underscore_to_title(value):
    """forest_excision_allotment -> Forest Excision Allotment."""
    if not value:
        return ""
    return str(value).replace("_", " ").title()

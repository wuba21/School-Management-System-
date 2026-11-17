"""
Django Template Tags and Filters for Ethiopian Calendar Support.
Enables seamless Ethiopian date rendering across all SSMS templates.
"""

from django import template
from django.utils import timezone
from core.utils.ethiopian_calendar import (
    EthiopianDate,
    gregorian_to_ethiopian,
    format_ethiopian,
    get_ethiopian_academic_year,
    ETH_MONTH_EN,
    ETH_MONTH_AM,
)

register = template.Library()


@register.filter(name='to_ethiopian')
def to_ethiopian_filter(date_val):
    """
    Formats a Gregorian date/datetime as full Ethiopian date.
    Example: {{ student.admission_date|to_ethiopian }} -> 'Meskerem 1, 2016 E.C.'
    """
    if not date_val:
        return ""
    return format_ethiopian(date_val, style='full_en')


@register.filter(name='to_ethiopian_short')
def to_ethiopian_short_filter(date_val):
    """
    Formats a Gregorian date/datetime as short Ethiopian date.
    Example: {{ session.date|to_ethiopian_short }} -> '01/01/2016 E.C.'
    """
    if not date_val:
        return ""
    return format_ethiopian(date_val, style='short')


@register.filter(name='to_ethiopian_am')
def to_ethiopian_am_filter(date_val):
    """
    Formats a Gregorian date/datetime using Ge'ez / Amharic script.
    Example: {{ exam.start_date|to_ethiopian_am }} -> 'መስከረም 1 ቀን 2016 ዓ.ም.'
    """
    if not date_val:
        return ""
    return format_ethiopian(date_val, style='full_am')


@register.filter(name='to_ethiopian_dual')
def to_ethiopian_dual_filter(date_val):
    """
    Formats both Ethiopian and Gregorian dates side-by-side.
    Example: {{ student.date_of_birth|to_ethiopian_dual }}
    Output: 'Meskerem 1, 2016 E.C. (Sep 12, 2023)'
    """
    if not date_val:
        return ""
    return format_ethiopian(date_val, style='dual')


@register.filter(name='to_ethiopian_dual_short')
def to_ethiopian_dual_short_filter(date_val):
    """
    Compact dual format for tabular views.
    Example: {{ session.date|to_ethiopian_dual_short }}
    Output: '01/01/2016 E.C. [12/09/2023]'
    """
    if not date_val:
        return ""
    return format_ethiopian(date_val, style='dual_short')


@register.filter(name='to_ethiopian_academic_year')
def to_ethiopian_academic_year_filter(date_val):
    """
    Returns the Ethiopian academic year.
    Example: {{ year.start_date|to_ethiopian_academic_year }} -> '2016 E.C.'
    """
    if not date_val:
        return ""
    return get_ethiopian_academic_year(date_val)


@register.simple_tag(name='current_ethiopian_date')
def current_ethiopian_date_tag(style='full_en'):
    """
    Outputs current Ethiopian date in active timezone.
    Usage: {% current_ethiopian_date 'full_en' %} or {% current_ethiopian_date 'full_am' %}
    """
    eth_now = EthiopianDate.today()
    return eth_now.format(style)


@register.simple_tag(name='current_ethiopian_year')
def current_ethiopian_year_tag():
    """
    Outputs current Ethiopian year (e.g. '2019 E.C.').
    Usage: {% current_ethiopian_year %}
    """
    return f"{EthiopianDate.today().year} E.C."


@register.filter(name='ethiopian_month_name')
def ethiopian_month_name_filter(month_num):
    """Returns English name for month number (1-13)."""
    try:
        return ETH_MONTH_EN.get(int(month_num), "")
    except (ValueError, TypeError):
        return ""


@register.filter(name='ethiopian_month_name_am')
def ethiopian_month_name_am_filter(month_num):
    """Returns Amharic name for month number (1-13)."""
    try:
        return ETH_MONTH_AM.get(int(month_num), "")
    except (ValueError, TypeError):
        return ""

"""
Core utilities package for Smart School Management System.
"""
from core.utils.ethiopian_calendar import (
    EthiopianDate,
    gregorian_to_ethiopian,
    ethiopian_to_gregorian,
    is_ethiopian_leap_year,
    get_ethiopian_month_days,
    format_ethiopian,
    get_ethiopian_academic_year,
    ETH_MONTH_EN,
    ETH_MONTH_AM,
)

__all__ = [
    'EthiopianDate',
    'gregorian_to_ethiopian',
    'ethiopian_to_gregorian',
    'is_ethiopian_leap_year',
    'get_ethiopian_month_days',
    'format_ethiopian',
    'get_ethiopian_academic_year',
    'ETH_MONTH_EN',
    'ETH_MONTH_AM',
]

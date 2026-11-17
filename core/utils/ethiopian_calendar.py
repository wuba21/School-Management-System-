"""
Ethiopian Calendar (Ge'ez Calendar / ዓውደ አውራኅ) Conversion and Display Engine.
Designed for Smart School Management System (SSMS) in Majang Zone, Gambella Region, Ethiopia.

100% Offline, Pure Python, Mathematically Exact via Julian Day Number (JDN) algorithms.
"""

from __future__ import annotations
import datetime
from typing import Tuple, Union, Optional
from django.utils import timezone


# -----------------------------------------------------------------------------
# 1. CONSTANTS & METADATA
# -----------------------------------------------------------------------------

ETH_MONTH_EN = {
    1: 'Meskerem',
    2: 'Tikimt',
    3: 'Hidar',
    4: 'Tahsas',
    5: 'Tir',
    6: 'Yekatit',
    7: 'Megabit',
    8: 'Miazia',
    9: 'Ginbot',
    10: 'Sene',
    11: 'Hamle',
    12: 'Nehase',
    13: 'Pagume',
}

ETH_MONTH_AM = {
    1: 'መስከረም',
    2: 'ጥቅምት',
    3: 'ኅዳር',
    4: 'ታኅሣሥ',
    5: 'ጥር',
    6: 'የካቲት',
    7: 'መጋቢት',
    8: 'ሚያዝያ',
    9: 'ግንቦት',
    10: 'ሰኔ',
    11: 'ሐምሌ',
    12: 'ነሐሴ',
    13: 'ጳጉሜ',
}

# Reverse lookup for month parsing (case-insensitive)
ETH_MONTH_LOOKUP = {}
for num, name in ETH_MONTH_EN.items():
    ETH_MONTH_LOOKUP[name.lower()] = num
for num, name in ETH_MONTH_AM.items():
    ETH_MONTH_LOOKUP[name] = num
# Common alternate spellings
ETH_MONTH_LOOKUP.update({
    'meskerem': 1, 'maskaram': 1,
    'tikimt': 2, 'teqemt': 2, 'tekemt': 2,
    'hidar': 3, 'hedar': 3,
    'tahsas': 4, 'tahasas': 4,
    'tir': 5, 'ter': 5,
    'yekatit': 6, 'yakatit': 6,
    'megabit': 7, 'maggabit': 7,
    'miazia': 8, 'miyazya': 8, 'myazya': 8,
    'ginbot': 9, 'genbot': 9,
    'sene': 10, 'sane': 10,
    'hamle': 11, 'hamile': 11,
    'nehase': 12, 'nahase': 12,
    'pagume': 13, 'pagumen': 13, 'pagumie': 13, 'puagme': 13,
})


# -----------------------------------------------------------------------------
# 2. CORE MATHEMATICAL ALGORITHMS (JDN)
# -----------------------------------------------------------------------------

def gregorian_to_jdn(year: int, month: int, day: int) -> int:
    """
    Computes Julian Day Number (JDN) for a given proleptic Gregorian date.
    Fliegel and van Flandern algorithm.
    """
    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12 * a - 3
    return day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045


def jdn_to_gregorian(jdn: int) -> Tuple[int, int, int]:
    """
    Converts a Julian Day Number (JDN) to proleptic Gregorian (year, month, day).
    """
    a = jdn + 32044
    b = (4 * a + 3) // 146097
    c = a - (146097 * b) // 4
    d = (4 * c + 3) // 1461
    e = c - (1461 * d) // 4
    m = (5 * e + 2) // 153
    day = e - (153 * m + 2) // 5 + 1
    month = m + 3 - 12 * (m // 10)
    year = 100 * b + d - 4800 + m // 10
    return (year, month, day)


def jdn_to_ethiopian(jdn: int) -> Tuple[int, int, int]:
    """
    Converts a Julian Day Number (JDN) to Ethiopian calendar (year, month, day).
    Ethiopian calendar epoch: Meskerem 1, 1 E.C. = JDN 1724221 (August 29, 8 AD Julian).
    """
    r = (jdn - 1723856) % 1461
    n = (r % 365) + 365 * (r // 1460)
    year = 4 * ((jdn - 1723856) // 1461) + (r // 365) - (r // 1460)
    month = (n // 30) + 1
    day = (n % 30) + 1
    return (year, month, day)


def ethiopian_to_jdn(year: int, month: int, day: int) -> int:
    """
    Converts Ethiopian (year, month, day) to Julian Day Number (JDN).
    """
    return (1723856 + 365) + 365 * (year - 1) + (year // 4) + 30 * (month - 1) + day - 1


# -----------------------------------------------------------------------------
# 3. CALENDAR RULES & VALIDATION
# -----------------------------------------------------------------------------

def is_ethiopian_leap_year(year: int) -> bool:
    """
    Determines if an Ethiopian year is a leap year (Pagume has 6 days).
    Rule: (year % 4 == 3) or ((year + 1) % 4 == 0).
    Examples: 2011, 2015, 2019, 2023 E.C. are leap years.
    """
    return (year % 4) == 3


def get_ethiopian_month_days(year: int, month: int) -> int:
    """
    Returns the number of days in a given Ethiopian month.
    Months 1 to 12 always have 30 days.
    Month 13 (Pagume) has 6 days in a leap year, otherwise 5 days.
    """
    if not (1 <= month <= 13):
        raise ValueError(f"Invalid Ethiopian month: {month}. Must be between 1 and 13.")
    if month < 13:
        return 30
    return 6 if is_ethiopian_leap_year(year) else 5


def validate_ethiopian_date(year: int, month: int, day: int) -> None:
    """
    Validates that (year, month, day) forms a valid Ethiopian calendar date.
    Raises ValueError with descriptive guidance if invalid.
    """
    if year < 1:
        raise ValueError(f"Invalid Ethiopian year: {year}. Year must be a positive integer.")
    if not (1 <= month <= 13):
        raise ValueError(f"Invalid Ethiopian month: {month}. Ethiopian calendar has months 1 to 13 (Pagume).")
    max_days = get_ethiopian_month_days(year, month)
    if not (1 <= day <= max_days):
        month_name = ETH_MONTH_EN.get(month, f"Month {month}")
        leap_note = " (Leap Year - 6 days)" if month == 13 and max_days == 6 else ""
        raise ValueError(
            f"Invalid day {day} for Ethiopian month {month_name} ({year} E.C.){leap_note}. "
            f"Expected 1 to {max_days}."
        )


# -----------------------------------------------------------------------------
# 4. ETHIOPIAN DATE OBJECT
# -----------------------------------------------------------------------------

class EthiopianDate:
    """
    Immutable representation of an Ethiopian Calendar date (ዓውደ አውራኅ).
    Provides rich conversion, formatting, arithmetic, and validation.
    """

    __slots__ = ('_year', '_month', '_day')

    def __init__(self, year: int, month: int, day: int):
        validate_ethiopian_date(year, month, day)
        self._year = int(year)
        self._month = int(month)
        self._day = int(day)

    @property
    def year(self) -> int:
        return self._year

    @property
    def month(self) -> int:
        return self._month

    @property
    def day(self) -> int:
        return self._day

    @property
    def month_name(self) -> str:
        """English transliteration of month name."""
        return ETH_MONTH_EN[self._month]

    @property
    def month_name_am(self) -> str:
        """Amharic Ge'ez script month name."""
        return ETH_MONTH_AM[self._month]

    @property
    def is_leap_year(self) -> bool:
        """True if this Ethiopian year is a leap year (Pagume has 6 days)."""
        return is_ethiopian_leap_year(self._year)

    @property
    def days_in_month(self) -> int:
        return get_ethiopian_month_days(self._year, self._month)

    @property
    def academic_year(self) -> str:
        """Formatted Ethiopian academic year (e.g. '2016 E.C.')."""
        return f"{self._year} E.C."

    # -------------------------------------------------------------------------
    # Conversions
    # -------------------------------------------------------------------------
    def to_gregorian(self) -> datetime.date:
        """Converts this Ethiopian date to an exact Python datetime.date."""
        jdn = ethiopian_to_jdn(self._year, self._month, self._day)
        gy, gm, gd = jdn_to_gregorian(jdn)
        return datetime.date(gy, gm, gd)

    @classmethod
    def from_gregorian(cls, date_val: Union[datetime.date, datetime.datetime]) -> EthiopianDate:
        """
        Creates an EthiopianDate from a Python datetime.date or datetime.datetime.
        Preserves timezone-awareness by extracting the local date.
        """
        if date_val is None:
            raise ValueError("Cannot convert None to EthiopianDate.")
        if isinstance(date_val, datetime.datetime):
            # If timezone-aware, ensure converted in active timezone
            if timezone.is_aware(date_val):
                date_val = timezone.localtime(date_val).date()
            else:
                date_val = date_val.date()
        elif not isinstance(date_val, datetime.date):
            raise TypeError(f"Expected datetime.date or datetime.datetime, got {type(date_val).__name__}")

        jdn = gregorian_to_jdn(date_val.year, date_val.month, date_val.day)
        ey, em, ed = jdn_to_ethiopian(jdn)
        return cls(ey, em, ed)

    @classmethod
    def today(cls) -> EthiopianDate:
        """Returns the current Ethiopian date in the active school timezone."""
        return cls.from_gregorian(timezone.localdate())

    # -------------------------------------------------------------------------
    # Formatting
    # -------------------------------------------------------------------------
    def format(self, style: str = 'full_en') -> str:
        """
        Formats the Ethiopian date according to standard styles:
        - 'full_en': 'Meskerem 1, 2016 E.C.'
        - 'full_am': 'መስከረም 1 ቀን 2016 ዓ.ም.'
        - 'short':   '01/01/2016 E.C.' (DD/MM/YYYY)
        - 'iso':     '2016-01-01'
        - 'dual':    'Meskerem 1, 2016 E.C. (Sep 12, 2023)'
        - 'dual_short': '01/01/2016 E.C. [12/09/2023]'
        - 'academic': '2016 E.C.'
        """
        if style == 'full_en':
            return f"{self.month_name} {self._day}, {self._year} E.C."
        elif style == 'full_am':
            return f"{self.month_name_am} {self._day} ቀን {self._year} ዓ.ም."
        elif style == 'short':
            return f"{self._day:02d}/{self._month:02d}/{self._year} E.C."
        elif style == 'iso':
            return f"{self._year:04d}-{self._month:02d}-{self._day:02d}"
        elif style == 'dual':
            g = self.to_gregorian()
            return f"{self.month_name} {self._day}, {self._year} E.C. ({g.strftime('%b %d, %Y')})"
        elif style == 'dual_short':
            g = self.to_gregorian()
            return f"{self._day:02d}/{self._month:02d}/{self._year} E.C. [{g.strftime('%d/%m/%Y')}]"
        elif style == 'academic':
            return f"{self._year} E.C."
        else:
            return f"{self.month_name} {self._day}, {self._year} E.C."

    def __str__(self) -> str:
        return self.format('full_en')

    def __repr__(self) -> str:
        return f"EthiopianDate({self._year}, {self._month}, {self._day})"

    # -------------------------------------------------------------------------
    # Comparisons & Hashing
    # -------------------------------------------------------------------------
    def __eq__(self, other: object) -> bool:
        if isinstance(other, EthiopianDate):
            return (self._year, self._month, self._day) == (other._year, other._month, other._day)
        if isinstance(other, datetime.date):
            return self.to_gregorian() == other
        return False

    def __lt__(self, other: object) -> bool:
        if isinstance(other, EthiopianDate):
            return (self._year, self._month, self._day) < (other._year, other._month, other._day)
        if isinstance(other, datetime.date):
            return self.to_gregorian() < other
        return NotImplemented

    def __le__(self, other: object) -> bool:
        return self == other or self < other

    def __gt__(self, other: object) -> bool:
        if isinstance(other, EthiopianDate):
            return (self._year, self._month, self._day) > (other._year, other._month, other._day)
        if isinstance(other, datetime.date):
            return self.to_gregorian() > other
        return NotImplemented

    def __ge__(self, other: object) -> bool:
        return self == other or self > other

    def __hash__(self) -> int:
        return hash((self._year, self._month, self._day))


# -----------------------------------------------------------------------------
# 5. PUBLIC CONVENIENCE HELPERS
# -----------------------------------------------------------------------------

def gregorian_to_ethiopian(date_val: Union[datetime.date, datetime.datetime, None]) -> Optional[EthiopianDate]:
    """
    Public conversion helper. Converts a Python date or datetime to an EthiopianDate.
    Returns None if date_val is None.
    """
    if date_val is None:
        return None
    return EthiopianDate.from_gregorian(date_val)


def ethiopian_to_gregorian(year: int, month: int, day: int) -> datetime.date:
    """
    Public conversion helper. Converts Ethiopian (year, month, day) to a Gregorian datetime.date.
    """
    eth_date = EthiopianDate(year, month, day)
    return eth_date.to_gregorian()


def format_ethiopian(date_val: Union[datetime.date, datetime.datetime, EthiopianDate, None],
                     style: str = 'full_en') -> str:
    """
    Convenience formatter. Accepts datetime.date, datetime.datetime, or EthiopianDate.
    Returns empty string if date_val is None.
    """
    if date_val is None:
        return ""
    if isinstance(date_val, EthiopianDate):
        return date_val.format(style)
    try:
        eth_date = gregorian_to_ethiopian(date_val)
        return eth_date.format(style)
    except Exception:
        return ""


def get_ethiopian_academic_year(date_val: Union[datetime.date, datetime.datetime, None] = None) -> str:
    """
    Returns the Ethiopian academic year for a given date (or current date if None).
    Format: '2016 E.C.'
    """
    if date_val is None:
        date_val = timezone.localdate()
    eth_date = gregorian_to_ethiopian(date_val)
    return f"{eth_date.year} E.C."

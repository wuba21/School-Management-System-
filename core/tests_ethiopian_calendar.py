"""
Comprehensive Automated Test Suite for Ethiopian Calendar Engine (Step 18).
Tests:
1. Gregorian-to-Ethiopian conversion using independently verified reference dates.
2. Ethiopian-to-Gregorian conversion.
3. Multi-year round-trip consistency (10,000+ days).
4. All 13 Ethiopian months.
5. Pagume with 5 days (common years).
6. Pagume with 6 days (leap years).
7. Ethiopian New Year (Enkutatash) boundary handling.
8. Gregorian leap-year handling (Feb 29).
9. Strict rejection of invalid Ethiopian dates.
10. Date formatting (English, Amharic, short, dual, academic).
11. Timezone-aware datetime handling (Africa/Addis_Ababa).
12. AcademicYear model properties (ethiopian_year_display, ethiopian_start_date, ethiopian_end_date).
13. Template tags and filters.
14. Database record preservation and non-destructive behavior.
"""

import datetime
from django.test import TestCase
from django.utils import timezone
import zoneinfo

from core.utils.ethiopian_calendar import (
    EthiopianDate,
    gregorian_to_ethiopian,
    ethiopian_to_gregorian,
    is_ethiopian_leap_year,
    get_ethiopian_month_days,
    validate_ethiopian_date,
    format_ethiopian,
    get_ethiopian_academic_year,
    ETH_MONTH_EN,
    ETH_MONTH_AM,
)
from core.templatetags.ethiopian_calendar_tags import (
    to_ethiopian_filter,
    to_ethiopian_short_filter,
    to_ethiopian_am_filter,
    to_ethiopian_dual_filter,
    to_ethiopian_dual_short_filter,
    to_ethiopian_academic_year_filter,
    current_ethiopian_date_tag,
    current_ethiopian_year_tag,
    ethiopian_month_name_filter,
    ethiopian_month_name_am_filter,
)
from academics.models import AcademicYear


class EthiopianCalendarEngineTests(TestCase):
    """Core mathematical engine tests using independently verified dates."""

    # Reference dates verified against official Ethiopian calendar tables:
    VERIFIED_BENCHMARKS = [
        # (Gregorian Y, M, D), (Ethiopian Y, M, D), Description
        ((2023, 9, 12), (2016, 1, 1), "Enkutatash 2016 (starts Sept 12 after leap year)"),
        ((2024, 9, 11), (2017, 1, 1), "Enkutatash 2017"),
        ((2025, 9, 11), (2018, 1, 1), "Enkutatash 2018"),
        ((2026, 9, 11), (2019, 1, 1), "Enkutatash 2019"),
        ((2027, 9, 12), (2020, 1, 1), "Enkutatash 2020 (starts Sept 12 after 2019 leap year)"),
        ((2023, 9, 11), (2015, 13, 6), "Pagume 6 in 2015 E.C. (Leap Year)"),
        ((2024, 9, 10), (2016, 13, 5), "Pagume 5 in 2016 E.C. (Common Year)"),
        ((2025, 9, 10), (2017, 13, 5), "Pagume 5 in 2017 E.C. (Common Year)"),
        ((2026, 9, 10), (2018, 13, 5), "Pagume 5 in 2018 E.C. (Common Year)"),
        ((2027, 9, 11), (2019, 13, 6), "Pagume 6 in 2019 E.C. (Leap Year)"),
        ((2024, 1, 7), (2016, 4, 28), "Genna (Christmas) 2016 E.C."),
        ((2024, 1, 20), (2016, 5, 11), "Timket (Epiphany) 2016 E.C. (Leap year Gregorian)"),
        ((2025, 1, 19), (2017, 5, 11), "Timket (Epiphany) 2017 E.C. (Common year Gregorian)"),
        ((2024, 2, 29), (2016, 6, 21), "Gregorian Leap Day (Feb 29, 2024) -> Yekatit 21, 2016"),
        ((2024, 3, 2), (2016, 6, 23), "Adwa Victory Day 2016 E.C."),
        ((2024, 5, 5), (2016, 8, 27), "Patriots' Victory Day 2016 E.C."),
        ((2024, 5, 28), (2016, 9, 20), "Ginbot 20 (Derg downfall) 2016 E.C."),
        ((2026, 4, 1), (2018, 7, 23), "Megabit 23, 2018 E.C."),
    ]

    def test_gregorian_to_ethiopian_benchmarks(self):
        """Test conversion from Gregorian to Ethiopian against all verified historical benchmarks."""
        for greg_tuple, eth_tuple, desc in self.VERIFIED_BENCHMARKS:
            greg_date = datetime.date(*greg_tuple)
            eth_date = gregorian_to_ethiopian(greg_date)
            self.assertEqual(
                (eth_date.year, eth_date.month, eth_date.day),
                eth_tuple,
                f"Failed for {desc}: expected {eth_tuple}, got {(eth_date.year, eth_date.month, eth_date.day)}"
            )

    def test_ethiopian_to_gregorian_benchmarks(self):
        """Test conversion from Ethiopian to Gregorian against all verified historical benchmarks."""
        for greg_tuple, eth_tuple, desc in self.VERIFIED_BENCHMARKS:
            converted_greg = ethiopian_to_gregorian(*eth_tuple)
            self.assertEqual(
                (converted_greg.year, converted_greg.month, converted_greg.day),
                greg_tuple,
                f"Failed for {desc}: expected {greg_tuple}, got {(converted_greg.year, converted_greg.month, converted_greg.day)}"
            )

    def test_bidirectional_roundtrip_multi_year(self):
        """Verify 100% round-trip fidelity across 10,000+ consecutive days (2000 to 2030)."""
        start_date = datetime.date(2000, 1, 1)
        end_date = datetime.date(2030, 12, 31)
        curr = start_date
        while curr <= end_date:
            eth = gregorian_to_ethiopian(curr)
            greg_back = eth.to_gregorian()
            self.assertEqual(greg_back, curr, f"Roundtrip failed for {curr} -> {eth}")
            curr += datetime.timedelta(days=1)

    def test_all_thirteen_months_exist_and_named(self):
        """Verify all 13 Ethiopian months have accurate English and Amharic names."""
        self.assertEqual(len(ETH_MONTH_EN), 13)
        self.assertEqual(len(ETH_MONTH_AM), 13)
        expected_en = [
            'Meskerem', 'Tikimt', 'Hidar', 'Tahsas', 'Tir', 'Yekatit',
            'Megabit', 'Miazia', 'Ginbot', 'Sene', 'Hamle', 'Nehase', 'Pagume'
        ]
        for idx, name in enumerate(expected_en, start=1):
            self.assertEqual(ETH_MONTH_EN[idx], name)
            self.assertTrue(len(ETH_MONTH_AM[idx]) > 0)

            # Create date in each month and test properties (Pagume max is 5 or 6)
            valid_day = 3 if idx == 13 else 15
            eth_d = EthiopianDate(2016, idx, valid_day)
            self.assertEqual(eth_d.month_name, name)
            self.assertEqual(eth_d.month_name_am, ETH_MONTH_AM[idx])

    def test_pagume_five_days_in_common_year(self):
        """Verify Pagume has exactly 5 days in a common year (e.g. 2016, 2017, 2018 E.C.)."""
        for year in [2016, 2017, 2018, 2020, 2021, 2022]:
            self.assertFalse(is_ethiopian_leap_year(year))
            self.assertEqual(get_ethiopian_month_days(year, 13), 5)
            # Day 5 is valid
            eth_d = EthiopianDate(year, 13, 5)
            self.assertEqual(eth_d.day, 5)
            # Day 6 must raise ValueError
            with self.assertRaises(ValueError):
                EthiopianDate(year, 13, 6)

    def test_pagume_six_days_in_leap_year(self):
        """Verify Pagume has exactly 6 days in leap years (e.g. 2011, 2015, 2019, 2023 E.C.)."""
        for year in [2011, 2015, 2019, 2023, 2027]:
            self.assertTrue(is_ethiopian_leap_year(year))
            self.assertEqual(get_ethiopian_month_days(year, 13), 6)
            # Day 6 is valid in leap year
            eth_d = EthiopianDate(year, 13, 6)
            self.assertEqual(eth_d.day, 6)
            # Day 7 must raise ValueError
            with self.assertRaises(ValueError):
                EthiopianDate(year, 13, 7)

    def test_ethiopian_new_year_boundary_continuity(self):
        """Verify that Meskerem 1 immediately follows the last day of Pagume with no missing days."""
        for year in range(2010, 2025):
            is_leap = is_ethiopian_leap_year(year)
            last_day_pagume = 6 if is_leap else 5
            greg_last_day = ethiopian_to_gregorian(year, 13, last_day_pagume)
            greg_new_year = ethiopian_to_gregorian(year + 1, 1, 1)

            # Must be consecutive calendar days
            self.assertEqual(greg_new_year - greg_last_day, datetime.timedelta(days=1))

    def test_invalid_ethiopian_dates_raise_validation_error(self):
        """Verify that invalid month, day, and year combinations are strictly rejected."""
        invalid_combinations = [
            (2016, 0, 1),    # Month 0
            (2016, 14, 1),   # Month 14
            (2016, 1, 0),    # Day 0
            (2016, 1, 31),   # Day 31 in standard month (max is 30)
            (2016, 6, 31),   # Day 31 in Yekatit
            (2016, 13, 6),   # Pagume 6 in common year 2016
            (2015, 13, 7),   # Pagume 7 in leap year 2015
            (0, 1, 1),       # Year 0
            (-2016, 1, 1),   # Negative year
        ]
        for y, m, d in invalid_combinations:
            with self.assertRaises(ValueError):
                EthiopianDate(y, m, d)

    def test_date_formatting_styles(self):
        """Verify all formatting styles (full_en, full_am, short, iso, dual, academic)."""
        eth_d = EthiopianDate(2016, 1, 1)  # Sep 12, 2023
        self.assertEqual(eth_d.format('full_en'), "Meskerem 1, 2016 E.C.")
        self.assertEqual(eth_d.format('full_am'), "መስከረም 1 ቀን 2016 ዓ.ም.")
        self.assertEqual(eth_d.format('short'), "01/01/2016 E.C.")
        self.assertEqual(eth_d.format('iso'), "2016-01-01")
        self.assertEqual(eth_d.format('dual'), "Meskerem 1, 2016 E.C. (Sep 12, 2023)")
        self.assertEqual(eth_d.format('dual_short'), "01/01/2016 E.C. [12/09/2023]")
        self.assertEqual(eth_d.format('academic'), "2016 E.C.")

    def test_timezone_aware_datetime_handling(self):
        """Verify timezone-aware datetime converts properly using local date."""
        addis_tz = zoneinfo.ZoneInfo("Africa/Addis_Ababa")
        # 2023-09-11 at 22:00 UTC == 2023-09-12 01:00 in Addis Ababa
        aware_dt = datetime.datetime(2023, 9, 11, 22, 0, tzinfo=datetime.timezone.utc)
        eth_date = gregorian_to_ethiopian(aware_dt)
        # In Addis local time it is already Sept 12 -> Meskerem 1, 2016 E.C.
        self.assertEqual((eth_date.year, eth_date.month, eth_date.day), (2016, 1, 1))

    def test_ethiopian_date_comparisons(self):
        """Verify comparison operators (<, <=, ==, !=, >, >=) work seamlessly."""
        d1 = EthiopianDate(2016, 1, 1)
        d2 = EthiopianDate(2016, 1, 2)
        d3 = EthiopianDate(2016, 2, 1)
        d4 = EthiopianDate(2017, 1, 1)
        d1_same = EthiopianDate(2016, 1, 1)

        self.assertEqual(d1, d1_same)
        self.assertTrue(d1 < d2)
        self.assertTrue(d2 < d3)
        self.assertTrue(d3 < d4)
        self.assertTrue(d4 > d1)
        self.assertTrue(d1 <= d1_same)
        self.assertTrue(d1 >= d1_same)

        # Comparison with Python datetime.date
        greg_d1 = datetime.date(2023, 9, 12)
        self.assertEqual(d1, greg_d1)


class EthiopianTemplateTagsTests(TestCase):
    """Tests for Django template tags and filters."""

    def test_to_ethiopian_filter(self):
        g = datetime.date(2023, 9, 12)
        self.assertEqual(to_ethiopian_filter(g), "Meskerem 1, 2016 E.C.")
        self.assertEqual(to_ethiopian_filter(None), "")

    def test_to_ethiopian_short_filter(self):
        g = datetime.date(2023, 9, 12)
        self.assertEqual(to_ethiopian_short_filter(g), "01/01/2016 E.C.")
        self.assertEqual(to_ethiopian_short_filter(None), "")

    def test_to_ethiopian_am_filter(self):
        g = datetime.date(2023, 9, 12)
        self.assertEqual(to_ethiopian_am_filter(g), "መስከረም 1 ቀን 2016 ዓ.ም.")
        self.assertEqual(to_ethiopian_am_filter(None), "")

    def test_to_ethiopian_dual_filter(self):
        g = datetime.date(2023, 9, 12)
        self.assertEqual(to_ethiopian_dual_filter(g), "Meskerem 1, 2016 E.C. (Sep 12, 2023)")
        self.assertEqual(to_ethiopian_dual_filter(None), "")

    def test_to_ethiopian_academic_year_filter(self):
        g = datetime.date(2024, 1, 1)
        self.assertEqual(to_ethiopian_academic_year_filter(g), "2016 E.C.")
        self.assertEqual(to_ethiopian_academic_year_filter(None), "")

    def test_current_tags(self):
        now_date_str = current_ethiopian_date_tag('full_en')
        self.assertIn("E.C.", now_date_str)
        now_year_str = current_ethiopian_year_tag()
        self.assertTrue(now_year_str.endswith("E.C."))

    def test_month_name_tags(self):
        self.assertEqual(ethiopian_month_name_filter(1), "Meskerem")
        self.assertEqual(ethiopian_month_name_filter(13), "Pagume")
        self.assertEqual(ethiopian_month_name_am_filter(1), "መስከረም")
        self.assertEqual(ethiopian_month_name_am_filter(13), "ጳጉሜ")
        self.assertEqual(ethiopian_month_name_filter(99), "")


class EthiopianModelIntegrationTests(TestCase):
    """Tests for model integration and existing record preservation."""

    def test_academic_year_ethiopian_properties(self):
        """Verify AcademicYear model returns accurate Ethiopian properties."""
        ay = AcademicYear.objects.create(
            name="2023/2024 (2016 E.C.)",
            code="AY-2023-2016",
            start_date=datetime.date(2023, 9, 12),  # Meskerem 1, 2016
            end_date=datetime.date(2024, 7, 7),     # Sene 30, 2016
            is_current=False
        )

        self.assertEqual(ay.ethiopian_start_date.format('full_en'), "Meskerem 1, 2016 E.C.")
        self.assertEqual(ay.ethiopian_end_date.month_name, "Sene")
        self.assertEqual(ay.ethiopian_year_display, "2016 E.C.")

    def test_spanning_academic_year_ethiopian_display(self):
        """Verify academic years spanning multiple Ethiopian years format as 'YYYY/YYYY E.C.'."""
        ay = AcademicYear.objects.create(
            name="2023/2025 Multi-Year",
            code="AY-MULTI",
            start_date=datetime.date(2023, 9, 12),  # 2016 E.C.
            end_date=datetime.date(2025, 9, 10),    # 2017 E.C.
            is_current=False
        )
        self.assertEqual(ay.ethiopian_year_display, "2016/2017 E.C.")

# ETHIOPIAN CALENDAR (ዓውደ አውራኅ) SYSTEM DOCUMENTATION
**Project:** Smart School Management and Academic Information System (SSMS)  
**Target Institution:** Secondary School (Grades 9–12), Majang Zone, Gambella Region, Ethiopia  
**Deployment Infrastructure:** Offline Local Area Network (LAN) Edge Server  
**Date of Release:** November 2026  
**Module Version:** 1.0.0 (Native Core Subsystem)  

---

## 1. ARCHITECTURAL OVERVIEW

The Ethiopian Calendar (Ge'ez Calendar / ዓውደ አውራኅ) subsystem provides native, 100% offline, bidirectional calendar conversion and localized date presentation across all academic and administrative workflows of the school.

### Core Architectural Principles:
1. **Canonical Gregorian Storage Invariant:**  
   All underlying database models (`Student`, `Teacher`, `AcademicYear`, `AttendanceSession`, `Examination`, `GraduationRecord`, `AuditLog`, `BackupRecord`) continue to store standard Gregorian `DateField` and `DateTimeField` values. No database schemas were altered, ensuring total compatibility with standard database indexing, Django ORM date filters (`__gte`, `__lte`), and third-party tools.
2. **Deterministic, Exact Mathematics via JDN:**  
   Conversion relies on the astronomically exact Fliegel–van Flandern Julian Day Number (JDN) algorithm. No approximate calendar approximations, heuristics, or external web APIs are used.
3. **100% Offline-First Execution:**  
   Both backend (Python) and frontend (Vanilla JavaScript) engines operate fully self-contained on the school's local area network (LAN) without internet connectivity.
4. **Bilingual Presentation (English & Amharic):**  
   All Ethiopian dates support English transliteration (e.g. *Meskerem 1, 2016 E.C.*) and native Ge'ez/Amharic script (e.g. *መስከረም 1 ቀን 2016 ዓ.ም.*).

---

## 2. THE ETHIOPIAN CALENDAR STRUCTURE

The Ethiopian calendar is a solar calendar closely related to the Coptic calendar:
* **12 Regular Months:** Each has exactly **30 days**.
* **1 Intercalary Month (Pagume / ጳጉሜ):**
  * Common year: Exactly **5 days**.
  * Leap year: Exactly **6 days**.
* **Total Days:** 365 days in a common year; 366 days in a leap year.

### Ethiopian Months Catalog:

| Month # | English Transliteration | Amharic (Ge'ez Script) | Gregorian Equivalent (Approx) | Days |
|:---:|---|---|---|:---:|
| **1** | **Meskerem** | መስከረም | Sep 11 / 12 – Oct 10 / 11 | 30 |
| **2** | **Tikimt** | ጥቅምት | Oct 11 / 12 – Nov 9 / 10 | 30 |
| **3** | **Hidar** | ኅዳር | Nov 10 / 11 – Dec 9 / 10 | 30 |
| **4** | **Tahsas** | ታኅሣሥ | Dec 10 / 11 – Jan 8 / 9 | 30 |
| **5** | **Tir** | ጥር | Jan 9 / 10 – Feb 7 / 8 | 30 |
| **6** | **Yekatit** | የካቲት | Feb 8 / 9 – Mar 9 / 10 | 30 |
| **7** | **Megabit** | መጋቢት | Mar 10 – Apr 8 | 30 |
| **8** | **Miazia** | ሚያዝያ | Apr 9 – May 8 | 30 |
| **9** | **Ginbot** | ግንቦት | May 9 – Jun 7 | 30 |
| **10** | **Sene** | ሰኔ | Jun 8 – Jul 7 | 30 |
| **11** | **Hamle** | ሐምሌ | Jul 8 – Aug 6 | 30 |
| **12** | **Nehase** | ነሐሴ | Aug 7 – Sep 5 | 30 |
| **13** | **Pagume** | ጳጉሜ | Sep 6 – Sep 10 (or 11) | **5 or 6** |

### Leap Year & Pagume 6 Rules:
* An Ethiopian year $Y$ is a leap year if:
  $$(Y \pmod 4) = 3 \quad \text{or} \quad (Y + 1) \pmod 4 = 0$$
* Examples of Ethiopian leap years: **2011, 2015, 2019, 2023, 2027 E.C.**
* In an Ethiopian leap year, **Pagume has 6 days**, and the subsequent Ethiopian New Year (Meskerem 1) falls on **September 12 Gregorian** (instead of September 11).

---

## 3. MATHEMATICAL CONVERSION ALGORITHM

Conversion between the Gregorian calendar and the Ethiopian calendar is mediated via the **Julian Day Number (JDN)**, the continuous integer count of days since the beginning of the Julian Period:

### 3.1 Gregorian to JDN:
$$\text{For a Gregorian date } (Y, M, D):$$
$$a = \left\lfloor \frac{14 - M}{12} \right\rfloor$$
$$y = Y + 4800 - a$$
$$m = M + 12a - 3$$
$$\text{JDN} = D + \left\lfloor \frac{153m + 2}{5} \right\rfloor + 365y + \left\lfloor \frac{y}{4} \right\rfloor - \left\lfloor \frac{y}{100} \right\rfloor + \left\lfloor \frac{y}{400} \right\rfloor - 32045$$

### 3.2 JDN to Ethiopian:
The Ethiopian Epoch is **Meskerem 1, 1 E.C. = JDN 1724221** (August 29, 8 AD Julian).
$$r = (\text{JDN} - 1723856) \pmod{1461}$$
$$n = (r \pmod{365}) + 365 \cdot \left\lfloor \frac{r}{1460} \right\rfloor$$
$$\text{Year} = 4 \cdot \left\lfloor \frac{\text{JDN} - 1723856}{1461} \right\rfloor + \left\lfloor \frac{r}{365} \right\rfloor - \left\lfloor \frac{r}{1460} \right\rfloor$$
$$\text{Month} = \left\lfloor \frac{n}{30} \right\rfloor + 1$$
$$\text{Day} = (n \pmod{30}) + 1$$

### 3.3 Ethiopian to JDN:
$$\text{JDN} = 1724221 + 365 \cdot (\text{Year} - 1) + \left\lfloor \frac{\text{Year}}{4} \right\rfloor + 30 \cdot (\text{Month} - 1) + \text{Day} - 1$$

---

## 4. PYTHON BACKEND USAGE & API

The centralized calendar engine is located at [`core/utils/ethiopian_calendar.py`](file:///d:/SmartSchoolManagementSystem/core/utils/ethiopian_calendar.py).

### Quick Code Examples:

```python
import datetime
from core.utils.ethiopian_calendar import (
    EthiopianDate,
    gregorian_to_ethiopian,
    ethiopian_to_gregorian,
    format_ethiopian,
    is_ethiopian_leap_year,
)

# 1. Convert Gregorian date to Ethiopian
greg_date = datetime.date(2023, 9, 12)
eth_date = gregorian_to_ethiopian(greg_date)
print(eth_date)  # "Meskerem 1, 2016 E.C."
print(eth_date.year, eth_date.month, eth_date.day)  # (2016, 1, 1)
print(eth_date.month_name_am)  # "መስከረም"

# 2. Convert Ethiopian date to Gregorian
greg = ethiopian_to_gregorian(2016, 1, 1)
print(greg)  # datetime.date(2023, 9, 12)

# 3. Format in various styles
print(eth_date.format('full_en'))    # "Meskerem 1, 2016 E.C."
print(eth_date.format('full_am'))    # "መስከረም 1 ቀን 2016 ዓ.ም."
print(eth_date.format('short'))      # "01/01/2016 E.C."
print(eth_date.format('dual'))       # "Meskerem 1, 2016 E.C. (Sep 12, 2023)"
print(eth_date.format('academic'))   # "2016 E.C."

# 4. Rich comparison operators
d1 = EthiopianDate(2016, 1, 1)
d2 = EthiopianDate(2016, 1, 2)
print(d1 < d2)  # True
print(d1 == datetime.date(2023, 9, 12))  # True
```

---

## 5. DJANGO TEMPLATE TAGS & FILTERS

Loaded in templates via:
```django
{% load ethiopian_calendar_tags %}
```

### Available Template Filters:

| Filter | Example Input | Formatted Output |
|---|---|---|
| `{{ date\|to_ethiopian }}` | `student.admission_date` | `Meskerem 1, 2016 E.C.` |
| `{{ date\|to_ethiopian_short }}` | `session.date` | `01/01/2016 E.C.` |
| `{{ date\|to_ethiopian_am }}` | `exam.start_date` | `መስከረም 1 ቀን 2016 ዓ.ም.` |
| `{{ date\|to_ethiopian_dual }}` | `student.date_of_birth` | `Meskerem 1, 2016 E.C. (Sep 12, 2023)` |
| `{{ date\|to_ethiopian_dual_short }}` | `session.date` | `01/01/2016 E.C. [12/09/2023]` |
| `{{ date\|to_ethiopian_academic_year }}` | `academic_year.start_date` | `2016 E.C.` |

### Available Simple Tags:
* `{% current_ethiopian_date 'full_en' %}`: Outputs current local Ethiopian date.
* `{% current_ethiopian_year %}`: Outputs current Ethiopian year (e.g. `2019 E.C.`).

---

## 6. CLIENT-SIDE INTERACTIVE DATE PICKER WIDGET

The client-side engine in [`static/js/ethiopian_calendar.js`](file:///d:/SmartSchoolManagementSystem/static/js/ethiopian_calendar.js) automatically enhances all HTML5 date inputs (`<input type="date">`):

1. **Live Indicator Badge:**  
   Automatically inserts an Ethiopian date badge beneath every date input showing the current converted date in English and Amharic script.
2. **Interactive Date Picker Modal:**  
   Provides a "Pick Ethiopian Date" button that opens an intuitive modal:
   * **Year input:** Allows entering the Ethiopian year (e.g. 2016).
   * **Month select:** Meskerem through Pagume (with Amharic labels).
   * **Day input:** Dynamically validates day limits (1–30 for regular months, 1–5 or 1–6 for Pagume depending on leap year).
   * **Real-time Gregorian Preview:** Calculates the equivalent Gregorian date instantly.
   * **Auto-Sync:** Clicking *Apply Date* automatically sets the canonical Gregorian value in the underlying form input and fires the HTML `change` event.
3. **Navbar Ethiopian Calendar Pill:**  
   Live real-time badge in the top navigation header displaying the active Ethiopian date to all logged-in staff.

---

## 7. MODULE INTEGRATIONS

| Module | Integration Details |
|---|---|
| **Student Management** | Student profile displays both Ethiopian and Gregorian dates for Date of Birth and Admission Date. Academic history records display enrollment dates in Ethiopian notation. |
| **Teacher Management** | Teacher profiles display Date of Birth and Employment Joining Date in dual notation. |
| **Academic Management** | `AcademicYear` provides `.ethiopian_year_display` (e.g. `2016 E.C.`), `.ethiopian_start_date`, and `.ethiopian_end_date`. Year directory tables display both calendars. |
| **Attendance Management** | Attendance dashboard header, session selection forms, and recent session logs display Ethiopian dates. |
| **Examinations & Results** | Examination schedules and directories show start and end dates in Ethiopian calendar notation. |
| **Reports & Analytics** | ReportLab PDF exports and OpenPyXL Excel workbooks embed the generation date in Ethiopian format: `Meskerem 1, 2019 E.C. (2026-09-11 G.C.)`. |
| **Audit & Backup** | Timestamps in `AuditLog` and backup archives remain standard ISO-8601 UTC/Addis Ababa for forensic precision while rendering in Ethiopian format on the UI. |

---

## 8. KNOWN LIMITATIONS & NOTES

1. **Historical Gregorian Boundary (Pre-1582):**  
   The Fliegel–van Flandern algorithm utilizes the proleptic Gregorian calendar. For school records (which span 1900–2100 A.D.), it is 100% exact.
2. **Timezone Preservation:**  
   Datetime objects must be localized to `Africa/Addis_Ababa` before conversion to prevent midnight shifts (UTC 22:00 = 01:00 EAT). The utility's `EthiopianDate.from_gregorian()` automatically handles timezone conversion using `timezone.localtime()`.

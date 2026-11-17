# Amharic Language Support (Bilingual System) Documentation
**Smart School Management and Academic Information System (SSMS)**  
*Target: Secondary School in Majang Zone, Gambella Region, Ethiopia (Grades 9–12)*  
*Deployment: Offline-First Local Area Network (LAN)*

---

## 1. Executive Summary & Purpose

The Smart School Management and Academic Information System (SSMS) implements an offline-ready, bilingual architecture supporting **English (`en`)** as the primary default administrative language and **Amharic (`am` - አማርኛ)** as the co-equal national/regional language.

In the Gambella Region and Majang Zone, administrative and academic staff, teachers, department heads, and school leaders require an interface that respects local linguistic standards while operating in a low-resource, air-gapped Local Area Network (LAN) without internet connectivity.

### Core Principles
1. **Zero External Dependencies:** No cloud translation APIs (Google Translate, Azure Cognitive Services) or external font CDNs (Google Fonts). All translation catalogs and TrueType fonts are bundled locally.
2. **Seamless On-Page Language Switching:** Users can toggle between English and Amharic from anywhere in the application without losing active URL location or form state.
3. **Database & Data Preservation:** Stored database records (student names, roll numbers, marks, teacher IDs) remain unaltered and schema-neutral. Only the user interface, labels, instructions, navigation, and generated reports adapt dynamically.
4. **Offline Typography:** Bundled Ethiopic TrueType font (`Nyala.ttf`) powers both web browser rendering (`@font-face`) and publication-grade PDF generation (`ReportLab`).
5. **Bilingual AI Assistant:** The offline conversational engine natively detects Amharic queries, extracts Ethiopian grade and section references, and delivers formatted Amharic responses.

---

## 2. System Architecture & Internationalization (I18N)

### 2.1 Django Internationalization Stack
- **Framework:** Django native `gettext` internationalization (`django.utils.translation`).
- **Middleware:** `django.middleware.locale.LocaleMiddleware` placed between `SessionMiddleware` and `CommonMiddleware` in `config/settings.py`.
- **Context Processor:** `django.template.context_processors.i18n` added to template context processors.
- **Language Definitions:**
  ```python
  LANGUAGE_CODE = 'en'
  LANGUAGES = [
      ('en', 'English'),
      ('am', 'አማርኛ'),
  ]
  LOCALE_PATHS = [
      BASE_DIR / 'locale',
  ]
  ```
- **Language Cookie:** `django_language` cookie (path `/`, default expiration).

### 2.2 URL Routing
In `config/urls.py`, Django's standard i18n URL handlers are registered:
```python
path('i18n/', include('django.conf.urls.i18n')),
```
This enables the `/i18n/set_language/` endpoint to handle language switching requests.

---

## 3. Typography & Offline Font Assets

### 3.1 Bundled Ethiopic Font (`Nyala.ttf`)
Ethiopic script requires proper Unicode glyph support spanning the Unicode block `U+1200` to `U+137F`.
- The `Nyala` TrueType font is bundled directly into the project repository:
  `static/fonts/nyala.ttf` (912 KB).
- It provides full character coverage for Ge'ez/Ethiopic syllables, numerals, and punctuation marks (`፡`, `።`, `፣`, `፤`, `፥`, `፦`).

### 3.2 CSS Typography Stack
In `static/css/styles.css`:
```css
@font-face {
    font-family: 'Nyala';
    src: url('../fonts/nyala.ttf') format('truetype');
    font-weight: normal;
    font-style: normal;
    font-display: swap;
}

body {
    background-color: var(--ssms-bg);
    color: var(--ssms-text-main);
    font-family: "Nyala", "Noto Sans Ethiopic", "Abyssinica SIL", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    font-size: 0.95rem;
    line-height: 1.55;
}
```
This ensures seamless fallback across Windows, Linux, and macOS client browsers connecting over the school LAN.

### 3.3 ReportLab PDF Engine Integration
ReportLab by default relies on 14 standard Type 1 fonts (such as Helvetica), which lack Ethiopic glyphs. To render Amharic PDFs without crashes or garbled characters, SSMS provides a font registration helper in `core/utils/font_helper.py`:
```python
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

def register_nyala_font():
    font_path = settings.BASE_DIR / 'static' / 'fonts' / 'nyala.ttf'
    if font_path.exists():
        pdfmetrics.registerFont(TTFont('Nyala', str(font_path)))
        return True
    return False
```
Both `reports/services.py` and `ai_assistant/services.py` utilize this helper to dynamically activate `Nyala` for table headers, cell values, and official document signatures.

---

## 4. UI Components & Language Switching

### 4.1 Navigation Bar Language Switcher
The language switcher is integrated into the top sticky navbar in `templates/base.html`, positioned alongside the Ethiopian Calendar status pill and Local LAN indicator:

```html
<form action="{% url 'set_language' %}" method="post" class="d-inline-flex align-items-center me-2">
    {% csrf_token %}
    <input name="next" type="hidden" value="{{ request.get_full_path }}">
    <div class="input-group input-group-sm">
        <span class="input-group-text bg-white border-end-0 py-1 px-2 text-primary" title="{% trans 'Switch Language' %}">
            <i class="bi bi-translate"></i>
        </span>
        <select name="language" onchange="this.form.submit()" class="form-select form-select-sm border-start-0 py-1 ps-1 pe-4 fw-semibold text-secondary" style="font-size: 0.8rem; cursor: pointer;">
            {% get_available_languages as AVAILABLE_LANGUAGES %}
            {% for lang_code, lang_name in AVAILABLE_LANGUAGES %}
                <option value="{{ lang_code }}" {% if lang_code == CURRENT_LANGUAGE %}selected{% endif %}>
                    {{ lang_name }}
                </option>
            {% endfor %}
        </select>
    </div>
</form>
```

### 4.2 Switching Dynamics
1. The user selects **English** or **አማርኛ** from the dropdown.
2. The form submits a `POST` request to `/i18n/set_language/`.
3. The hidden `next` input transmits the exact current URL path (`request.get_full_path`).
4. Django sets the `django_language` cookie and issues a `302 Redirect` back to the exact same page.
5. The view re-renders immediately in the newly chosen language with all form parameters, filter queries, and paginations intact.

---

## 5. Translation Catalog Management (`polib`)

### 5.1 Structure
Translations reside in the project root:
```
locale/
└── am/
    └── LC_MESSAGES/
        ├── django.po  (Human-readable Gettext source catalog)
        └── django.mo  (Binary compiled machine object)
```

### 5.2 Standalone Python Compiler
To eliminate reliance on GNU `gettext` or `msgfmt` binaries (which are typically missing on air-gapped Windows school servers), SSMS includes `scripts/compile_translations.py`. It uses the Python library `polib` to compile `.po` directly into `.mo`.

To compile or refresh translations:
```bash
python scripts/compile_translations.py
```
**Output:**
```
[PASS] Saved PO file: D:\SmartSchoolManagementSystem\locale\am\LC_MESSAGES\django.po with 220 entries.
[PASS] Compiled MO file: D:\SmartSchoolManagementSystem\locale\am\LC_MESSAGES\django.mo successfully.
```

### 5.3 Catalog Coverage
Over 220 localized strings span:
- **Global Navigation & Menus:** Dashboard (ዳሽቦርድ), Students (ተማሪዎች), Teachers (መምህራን), Academic Years (የትምህርት ዘመናት), Grades & Sections (ክፍሎች እና ሴክሽኖች), Subjects (የትምህርት ዓይነቶች), Attendance (የተማሪዎች መገኘት), Examinations (ፈተናዎች), Results (ውጤቶች), Promotion (የተማሪዎች ዝውውር እና ማለፍ), Timetable (የክፍል የጊዜ ሰሌዳ), Reports (ሪፖርቶች እና ትንታኔዎች), AI Assistant (ሰው ሰራሽ አስተውሎት), Settings (ቅንብሮች), Backup & Recovery (የመረጃ ቅጂ እና መልሶ ማግኛ), Audit Logs (የክትትል ምዝግብ ማስታወሻዎች).
- **Core Entities & Actions:** Save (አስቀምጥ), Cancel (ሰርዝ), Edit (አስተካክል), Delete (አስወግድ), View (ተመልከት), Export PDF (PDF ላክ), Export Excel (Excel ላክ), Search (ፈልግ), Filter (አጣራ).
- **Attendance Statuses:** Present (ተገኝቷል), Absent (ቀርቷል), Late (አርፍዷል), Excused (በፈቃድ).
- **Academic Scales & Outcomes:** Promoted (አልፏል), Retained (ተደግሟል), Excellent (እጅግ በጣም ጥሩ), Very Good (በጣም ጥሩ), Good (ጥሩ), Satisfactory (አጥጋቢ), Poor (ዝቅተኛ).
- **Institution Identifiers:** Smart School Management System (ስማርት የትምህርት ቤት አስተዳደር ስርዓት), Majang Zone (ማጃንግ ዞን), Metti Secondary School (ሜቲ 2ኛ ደረጃ ትምህርት ቤት).

---

## 6. Bilingual Reporting (PDF & Excel)

In `reports/services.py`, `ReportExportService` dynamically checks the active request language via `translation.get_language()`:

### 6.1 PDF Reports (`ReportExportService.export_pdf`)
- When language is `am`:
  - Activates `fontName='Nyala'` for all Paragraph and Table styles.
  - Generates institutional header:  
    `ስማርት የትምህርት ቤት አስተዳደር ስርዓት (SSMS)`  
    `ማጃንግ ዞን 2ኛ ደረጃ ትምህርት ቤት • ጋምቤላ ክልላዊ መንግሥት፣ ኢትዮጵያ`
  - Formats date string in Amharic Ethiopian Calendar (`full_am`): e.g. `ጥቅምት 30 ቀን 2019 ዓ.ም`.
  - Translates table column headers:
    - Students: `የመግቢያ ቁጥር`, `የተማሪ ሙሉ ስም`, `ጾታ`, `ክፍል እና ሴክሽን`, `የትምህርት ዘርፍ`, `የትምህርት ዘመን`, `ሁኔታ`
    - Teachers: `የመታወቂያ ቁጥር`, `የመምህር ሙሉ ስም`, `ጾታ`, `ሙያዊ ዘርፍ`, `የክፍሎች ብዛት`, `የሚያስተምሯቸው ትምህርቶች`, `የሳምንት ክፍለ ጊዜ`, `ሁኔታ`
    - Attendance: `ቀን`, `ጠቅላላ ተማሪዎች`, `የተገኙ`, `ያረፈዱ`, `የቀሩ`, `በፈቃድ`, `የመገኘት ምጣኔ (%)`
    - Exams: `ፈተና`, `የትምህርት ዓይነት`, `ክፍል`, `ከፍተኛ / ማለፊያ`, `የተፈተኑ`, `አማካይ`, `ከፍተኛ`, `ዝቅተኛ`, `የማለፍ ምጣኔ (%)`
    - Promotion: `የቡድን ስም`, `የትምህርት ዘመን`, `ቀጣይ ዓመት`, `ክፍል`, `እጩዎች`, `ያለፉ`, `የደገሙ`, `የተመረቁ`, `የማለፍ ምጣኔ (%)`
  - Translates signature block:  
    `ያዘጋጀው: ___________________________`  
    `ያረጋገጠው (ርዕሰ መምህር): ___________________________`  
    `ኦፊሴላዊ ማህተም: [                ]`

### 6.2 Excel Reports (`ReportExportService.export_excel`)
- UTF-8 openpyxl spreadsheet generation natively supports Ethiopic strings.
- Automatically selects Amharic or English sheet headers and column labels based on `translation.get_language()`.

---

## 7. Bilingual AI Assistant Integration

The offline AI assistant in `ai_assistant/services.py` (`ConversationalAssistantService`) provides native dual-language intelligence.

### 7.1 Language Detection
Queries containing Ethiopic characters (range `\u1200` to `\u137f`) or submitted during an active Amharic session are automatically processed through the Amharic conversational path.

### 7.2 Intent Recognition Matrix
| Intent | English Query Samples | Amharic Query Samples |
|---|---|---|
| `STUDENT_COUNT` | "How many students are registered?", "Total student count" | "በትምህርት ቤቱ ስንት ተማሪዎች አሉ?", "የተማሪዎች ብዛት ስንት ነው?" |
| `TEACHER_COUNT` | "How many teachers are registered?", "Total teachers" | "በአጠቃላይ ስንት መምህራን አሉ?", "ጠቅላላ መምህራን" |
| `LOW_SCORING_SUBJECTS` | "Which subjects have the lowest average scores?", "Subjects needing attention" | "ዝቅተኛ ውጤት የተመዘገበባቸው የትምህርት ዓይነቶች የትኞቹ ናቸው?", "ትኩረት የሚሹ ትምህርቶች" |
| `GRADE_ATTENDANCE` | "What is the attendance of Grade 10?", "Attendance percentage" | "የ10ኛ ክፍል የተማሪዎች መገኘት ሁኔታ እንዴት ነው?", "የመገኘት ምጣኔ" |
| `GRADE_ACADEMIC_SUMMARY`| "Summarize Grade 11 academic performance" | "የ11ኛ ክፍል ውጤት ማጠቃለያ አሳየኝ" |
| `CHRONIC_ABSENTEES` | "Who are the frequent absentees?", "Chronic absentees" | "በተደጋጋሚ የቀሩ ተማሪዎች እነማን ናቸው?" |
| `TIMETABLE_INFO` | "What are the school periods and working days?" | "የትምህርት ሰዓት እና የጊዜ ሰሌዳ እንዴት ነው?" |
| `PROMOTION_CRITERIA` | "What are the promotion criteria from Grade 10 to 11?" | "የተማሪዎች ማለፊያ መስፈርት ምንድን ነው?" |
| `HELP` | "What can you do?", "Help" | "እርዳታ እፈልጋለሁ ምን መስራት ትችላለህ?" |

### 7.3 Entity Extraction
Regex entity extraction recognizes both Latin and Amharic formats:
- Grade numbers: `Grade 9`, `G10`, `11th grade`, `9ኛ ክፍል`, `ክፍል 10`.
- Section letters: `Section A`, `Sec B`, `ሴክሽን A`.

---

## 8. Verification & Test Suite

The internationalization features are covered by dedicated automated test suites in `core/tests_i18n.py`:
- `InternationalizationConfigTests`: Verifies settings, middleware, and `.mo` file loading.
- `TranslationCatalogTests`: Tests string resolution in `en` and `am` overrides.
- `LanguageSwitcherTests`: Tests `set_language` redirection, cookie preservation, and UI translation.
- `TypographyAndFontHelperTests`: Tests ReportLab font registration of `Nyala`.
- `BilingualReportingTests`: Validates PDF and Excel generation in both languages.
- `BilingualAIAssistantTests`: Tests natural-language intent recognition and Amharic markdown responses.

**Full Test Suite Status:**
- Total Tests: **244 passing**
- System Check: **0 issues**
- Migrations Check: **Clean (no schema changes)**

---

## 9. Administrator Maintenance Runbook

### Updating or Adding New Translations
1. Open `scripts/compile_translations.py`.
2. Add the new English term and its Amharic translation to the `TRANSLATIONS` dictionary:
   ```python
   "New English String": "አዲስ የአማርኛ ጽሑፍ",
   ```
3. Run the compiler script:
   ```bash
   python scripts/compile_translations.py
   ```
4. Restart or reload the Django application server.

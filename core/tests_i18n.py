"""
Automated tests for Step 19: Bilingual (English & Amharic) internationalization,
language switching, Amharic typography, ReportLab Nyala font registration,
bilingual PDF/Excel reporting, and AI Assistant bilingual handling.
"""

import io
from django.test import TestCase, Client
from django.conf import settings
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext as _
from django.contrib.auth import get_user_model

from accounts.models import Role
from core.utils.font_helper import register_nyala_font
from reports.services import ReportExportService
from ai_assistant.services import ConversationalAssistantService


class InternationalizationConfigTests(TestCase):
    """Verifies settings and i18n infrastructure configuration."""

    def test_default_language_is_english(self):
        self.assertEqual(settings.LANGUAGE_CODE, 'en')

    def test_supported_languages_include_english_and_amharic(self):
        lang_codes = [code for code, name in settings.LANGUAGES]
        self.assertIn('en', lang_codes)
        self.assertIn('am', lang_codes)

    def test_locale_middleware_configured(self):
        self.assertIn('django.middleware.locale.LocaleMiddleware', settings.MIDDLEWARE)

    def test_mo_file_exists_and_loads(self):
        mo_path = settings.BASE_DIR / 'locale' / 'am' / 'LC_MESSAGES' / 'django.mo'
        self.assertTrue(mo_path.exists(), f"MO file missing at {mo_path}")
        self.assertGreater(mo_path.stat().st_size, 1000)


class TranslationCatalogTests(TestCase):
    """Verifies translation resolution between English and Amharic."""

    def test_english_translation(self):
        with translation.override('en'):
            self.assertEqual(_('Dashboard'), 'Dashboard')
            self.assertEqual(_('Students'), 'Students')
            self.assertEqual(_('Teachers'), 'Teachers')
            self.assertEqual(_('Attendance'), 'Attendance')
            self.assertEqual(_('Examinations'), 'Examinations')

    def test_amharic_translation(self):
        with translation.override('am'):
            self.assertEqual(_('Dashboard'), 'ዳሽቦርድ')
            self.assertEqual(_('Students'), 'ተማሪዎች')
            self.assertEqual(_('Teachers'), 'መምህራን')
            self.assertEqual(_('Attendance'), 'የተማሪዎች መገኘት')
            self.assertEqual(_('Examinations'), 'ፈተናዎች')
            self.assertEqual(_('Results'), 'ውጤቶች')
            self.assertEqual(_('Promotion'), 'የተማሪዎች ዝውውር እና ማለፍ')
            self.assertEqual(_('Timetable'), 'የክፍል የጊዜ ሰሌዳ')
            self.assertEqual(_('Present'), 'ተገኝቷል')
            self.assertEqual(_('Absent'), 'ቀርቷል')
            self.assertEqual(_('Late'), 'አርፍዷል')
            self.assertEqual(_('Excused'), 'በፈቃድ')


class LanguageSwitcherTests(TestCase):
    """Verifies client-side language switching via set_language view."""

    def setUp(self):
        self.client = Client()
        self.admin_role = Role.objects.create(code='ADMIN', name='System Administrator')
        User = get_user_model()
        self.user = User.objects.create_user(
            username='i18n_admin',
            password='Password123!',
            role=self.admin_role
        )

    def test_set_language_to_amharic(self):
        response = self.client.post(
            reverse('set_language'),
            {'language': 'am', 'next': reverse('dashboard')},
            follow=False
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('dashboard'), response.url)
        # Check cookie was set
        self.assertIn(settings.LANGUAGE_COOKIE_NAME, response.cookies)
        self.assertEqual(response.cookies[settings.LANGUAGE_COOKIE_NAME].value, 'am')

    def test_set_language_to_english(self):
        response = self.client.post(
            reverse('set_language'),
            {'language': 'en', 'next': reverse('dashboard')},
            follow=False
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(settings.LANGUAGE_COOKIE_NAME, response.cookies)
        self.assertEqual(response.cookies[settings.LANGUAGE_COOKIE_NAME].value, 'en')

    def test_rendered_page_reflects_active_language(self):
        self.client.force_login(self.user)
        # Request with Amharic cookie
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = 'am'
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        # Check Amharic translation in navbar / sidebar
        self.assertIn('ዳሽቦርድ', content)
        self.assertIn('ተማሪዎች', content)
        self.assertIn('መምህራን', content)


class TypographyAndFontHelperTests(TestCase):
    """Verifies that Nyala font is detected and registered with ReportLab."""

    def test_nyala_font_registration(self):
        registered = register_nyala_font()
        self.assertTrue(registered)

        # Confirm fontmetrics has Nyala registered
        from reportlab.pdfbase import pdfmetrics
        registered_fonts = pdfmetrics.getRegisteredFontNames()
        self.assertIn('Nyala', registered_fonts)


class BilingualReportingTests(TestCase):
    """Verifies that PDF and Excel exports compile cleanly in both English and Amharic."""

    def test_pdf_export_english(self):
        with translation.override('en'):
            buf = ReportExportService.export_pdf(
                report_type='attendance',
                context={'records': []},
                title="Weekly Attendance Roster"
            )
            self.assertIsInstance(buf, io.BytesIO)
            pdf_bytes = buf.getvalue()
            self.assertTrue(pdf_bytes.startswith(b'%PDF'))
            self.assertGreater(len(pdf_bytes), 1000)

    def test_pdf_export_amharic(self):
        with translation.override('am'):
            buf = ReportExportService.export_pdf(
                report_type='attendance',
                context={'records': []},
                title="የተማሪዎች ሳምንታዊ መገኘት"
            )
            self.assertIsInstance(buf, io.BytesIO)
            pdf_bytes = buf.getvalue()
            self.assertTrue(pdf_bytes.startswith(b'%PDF'))
            self.assertGreater(len(pdf_bytes), 1000)

    def test_excel_export_english(self):
        with translation.override('en'):
            buf = ReportExportService.export_excel(
                report_type='attendance',
                context={'records': []},
                title="Weekly Attendance Roster"
            )
            self.assertIsInstance(buf, io.BytesIO)
            self.assertGreater(len(buf.getvalue()), 500)

    def test_excel_export_amharic(self):
        with translation.override('am'):
            buf = ReportExportService.export_excel(
                report_type='attendance',
                context={'records': []},
                title="የተማሪዎች ሳምንታዊ መገኘት"
            )
            self.assertIsInstance(buf, io.BytesIO)
            self.assertGreater(len(buf.getvalue()), 500)


class BilingualAIAssistantTests(TestCase):
    """Verifies AI Assistant handling of both English and Amharic queries."""

    def setUp(self):
        self.admin_role = Role.objects.create(code='ADMIN', name='System Administrator')
        User = get_user_model()
        self.user = User.objects.create_user(
            username='ai_bilingual_admin',
            password='Password123!',
            role=self.admin_role
        )

    def test_english_student_count_query(self):
        result = ConversationalAssistantService.handle_query(
            "How many students are registered in the school?",
            user=self.user
        )
        self.assertEqual(result['intent'], 'STUDENT_COUNT')
        self.assertIn("Student Population Statistics", result['content'])

    def test_amharic_student_count_query(self):
        result = ConversationalAssistantService.handle_query(
            "በትምህርት ቤቱ ውስጥ ስንት ተማሪዎች አሉ?",
            user=self.user
        )
        self.assertEqual(result['intent'], 'STUDENT_COUNT')
        self.assertIn("የተማሪዎች ብዛት ስታቲስቲክስ", result['content'])

    def test_amharic_teacher_count_query(self):
        result = ConversationalAssistantService.handle_query(
            "በአጠቃላይ ስንት መምህራን አሉ?",
            user=self.user
        )
        self.assertEqual(result['intent'], 'TEACHER_COUNT')
        self.assertIn("የመምህራን ስታቲስቲክስ", result['content'])

    def test_amharic_low_scoring_query(self):
        result = ConversationalAssistantService.handle_query(
            "ዝቅተኛ ውጤት የተመዘገበባቸው የትምህርት ዓይነቶች የትኞቹ ናቸው?",
            user=self.user
        )
        self.assertEqual(result['intent'], 'LOW_SCORING_SUBJECTS')
        self.assertTrue(
            "የአካዳሚክ ውጤት ምርመራ" in result['content'] or
            "ትኩረት የሚሹ የትምህርት ዓይነቶች" in result['content']
        )

    def test_amharic_grade_attendance_query(self):
        result = ConversationalAssistantService.handle_query(
            "የ10ኛ ክፍል የተማሪዎች መገኘት ሁኔታ እንዴት ነው?",
            user=self.user
        )
        self.assertEqual(result['intent'], 'GRADE_ATTENDANCE')
        self.assertIn("የተማሪዎች መገኘት ትንተና", result['content'])

    def test_amharic_promotion_criteria_query(self):
        result = ConversationalAssistantService.handle_query(
            "የተማሪዎች ማለፊያ መስፈርት ምንድን ነው?",
            user=self.user
        )
        self.assertEqual(result['intent'], 'PROMOTION_CRITERIA')
        self.assertIn("የተማሪዎች ማለፊያ መስፈርት", result['content'])

    def test_amharic_help_query(self):
        result = ConversationalAssistantService.handle_query(
            "እርዳታ እፈልጋለሁ ምን መስራት ትችላለህ?",
            user=self.user
        )
        self.assertEqual(result['intent'], 'HELP')
        self.assertIn("የትምህርት ቤት ረዳት AI አገልግሎቶች", result['content'])

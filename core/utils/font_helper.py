"""
Font helper for ReportLab PDF generation in SSMS.
Registers the bundled Nyala TrueType font for rendering Ethiopic (Amharic) glyphs.
"""

from pathlib import Path
from django.conf import settings

_font_registered = False


def register_nyala_font():
    """
    Registers Nyala TrueType font with ReportLab if available.
    Returns True if font was registered or already available, False otherwise.
    """
    global _font_registered
    if _font_registered:
        return True

    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        font_path = settings.BASE_DIR / 'static' / 'fonts' / 'nyala.ttf'
        if font_path.exists():
            pdfmetrics.registerFont(TTFont('Nyala', str(font_path)))
            _font_registered = True
            return True
    except Exception:
        pass
    return False

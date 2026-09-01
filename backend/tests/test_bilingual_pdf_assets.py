"""WP-A bilingual PDF assets (addendum §7). Filesystem only; no DB."""

from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"
FONT_PATH = FRONTEND_SRC / "assets" / "fonts" / "NotoNaskhArabic-Regular.ttf"
OFL_PATH = FRONTEND_SRC / "assets" / "fonts" / "OFL.txt"
TITLES_PATH = FRONTEND_SRC / "components" / "pdf" / "pdfTitles.ts"
FONTS_PATH = FRONTEND_SRC / "components" / "pdf" / "pdfFonts.ts"
MODELS_DIR = REPO_ROOT / "backend" / "app" / "models"
ALEMBIC_VERSIONS = REPO_ROOT / "backend" / "alembic" / "versions"

TTF_MAGIC = b"\x00\x01\x00\x00"
OTF_MAGIC = b"OTTO"
MIN_FONT_BYTES = 50_000
MAX_FONT_BYTES = 2_000_000

TITLES_EN = (
    "Tax Invoice",
    "Tax Credit Note",
    "Quotation",
    "LPO",
    "Delivery Note",
    "Account Statement",
)
TITLES_AR = (
    "فاتورة ضريبية",
    "إشعار دائن ضريبي",
    "عرض سعر",
    "أمر شراء محلي",
    "إذن تسليم",
    "كشف حساب",
)


def test_font_file_exists_size_and_magic() -> None:
    assert FONT_PATH.is_file()
    size = FONT_PATH.stat().st_size
    assert MIN_FONT_BYTES <= size <= MAX_FONT_BYTES
    magic = FONT_PATH.read_bytes()[:4]
    assert magic in (TTF_MAGIC, OTF_MAGIC)


def test_ofl_license_present() -> None:
    assert OFL_PATH.is_file()
    text = OFL_PATH.read_text(encoding="utf-8")
    assert "SIL OPEN FONT LICENSE" in text.upper()


def test_pdf_titles_contain_six_en_and_ar() -> None:
    text = TITLES_PATH.read_text(encoding="utf-8")
    for title in TITLES_EN:
        assert title in text
    for title in TITLES_AR:
        assert title in text


def test_pdf_fonts_register_local_ttf_not_cdn() -> None:
    text = FONTS_PATH.read_text(encoding="utf-8")
    assert "Font.register" in text
    assert "NotoNaskhArabic" in text
    assert "NotoNaskhArabic-Regular.ttf" in text
    lowered = text.lower()
    assert "fonts.googleapis" not in lowered
    assert "fonts.gstatic" not in lowered
    assert "http://" not in lowered


def test_models_have_no_arabic_name_columns() -> None:
    for name in ("workspace.py", "client.py", "product.py"):
        text = (MODELS_DIR / name).read_text(encoding="utf-8")
        assert "name_ar" not in text
        assert "address_ar" not in text


def test_alembic_head_unchanged_no_bilingual_revision() -> None:
    names = [p.name for p in ALEMBIC_VERSIONS.iterdir() if p.suffix == ".py"]
    assert "b8d5f0c3a216_add_credit_notes.py" in names
    for name in names:
        assert "_bilingual" not in name
        assert "_name_ar" not in name

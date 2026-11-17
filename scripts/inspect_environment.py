"""Print what this machine can do for ProcureAI (dependencies, OCR, database, LLM mode). No secrets are printed."""

import importlib
import shutil
import sys

MODULES = [
    "fastapi",
    "sqlalchemy",
    "pydantic",
    "langgraph",
    "chromadb",
    "pymupdf",
    "pdfplumber",
    "pytesseract",
    "sklearn",
    "pandas",
    "reportlab",
    "openpyxl",
    "streamlit",
    "plotly",
    "alembic",
]

print(f"python {sys.version.split()[0]}")
for m in MODULES:
    try:
        mod = importlib.import_module(m)
        print(f"  ok       {m} {getattr(mod, '__version__', '')}")
    except ImportError:
        print(f"  MISSING  {m}")
print("tesseract binary:", shutil.which("tesseract") or "NOT FOUND (scanned PDFs/images cannot be read)")
try:
    from procureai.config.settings import get_settings

    s = get_settings()
    print(
        f"env={s.app_env} database={s.database_url.split('://')[0]} llm_provider={s.llm_provider} "
        f"llm_configured={bool(s.llm_api_key and s.llm_model)}"
    )
except Exception as exc:
    print("settings invalid:", exc)

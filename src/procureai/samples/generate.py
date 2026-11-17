"""Generates SYNTHETIC procurement documents for demos, tests and retrieval evaluation.

Nothing here is real vendor, pricing or policy data. Every document says so on its first page.
"""

from __future__ import annotations

import io
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

BANNER = "SYNTHETIC SAMPLE DOCUMENT - fictional data for demonstration and testing only."

TENDER_LINES = [
    "Tender Notice",
    "Tender No: SYN-2026-014",
    "Item: Business laptops",
    "Quantity: 50 units",
    "Closing date: 30 November 2026",
    "Technical Requirements",
    "Minimum RAM: 16 GB (mandatory)",
    "Storage capacity: at least 512 GB (mandatory)",
    "Processor cores: minimum 8 (mandatory)",
    "Display size: 14 to 15.6 inches (mandatory)",
    "Weight: maximum 1.8 kg (desirable)",
    "Operating system: Windows 11 Pro (mandatory)",
    "Commercial Requirements",
    "Warranty: at least 3 years (mandatory)",
    "Delivery: within 30 days (mandatory)",
    "Instructions to Bidders",
    "Bidders must submit prices in a single currency and state taxes separately.",
]

VENDORS = {
    "northwind": {
        "Vendor": "Northwind Computers",
        "Quotation Reference": "NW-Q-2201",
        "Currency": "USD",
        "Unit price": "USD 1,150",
        "Quantity": "50",
        "Tax": "10%",
        "Delivery charges": "USD 500",
        "specs": [
            ("RAM", "16 GB DDR5"),
            ("Storage", "512 GB NVMe SSD"),
            ("Processor cores", "8 cores"),
            ("Display size", "15.6 inch"),
            ("Weight", "1.7 kg"),
            ("Operating system", "Windows 11 Pro"),
            ("Warranty", "3 years on-site"),
            ("Delivery time", "21 days"),
        ],
    },
    "contoso": {
        "Vendor": "Contoso Systems",
        "Quotation Reference": "CS-7781",
        "Currency": "USD",
        "Unit price": "USD 980",
        "Quantity": "50",
        "Tax": "10%",
        "Delivery charges": "USD 650",
        "specs": [
            ("RAM", "8 GB"),
            ("Storage", "1 TB SSD"),
            ("Processor cores", "6 cores"),
            ("Display size", "14 inch"),
            ("Weight", "1.5 kg"),
            ("Operating system", "Windows 11 Home"),
            ("Warranty", "24 months"),
            ("Delivery time", "6 weeks"),
        ],
    },
    "fabrikam": {
        "Vendor": "Fabrikam Tech",
        "Quotation Reference": "FT-0099",
        "Currency": "EUR",
        "Unit price": "EUR 1,900",
        "Quantity": "50",
        "Tax": "10%",
        "Delivery charges": "EUR 400",
        "specs": [
            ("RAM", "32 GB"),
            ("Storage", "512 GB SSD"),
            ("Display size", "13.3 inch"),
            ("Weight", "2.1 kg"),
            ("Operating system", "Windows 11 Pro"),
            ("Warranty", "5 years"),
            ("Delivery time", "15 days"),
        ],  # processor cores intentionally omitted -> Missing Information
    },
}

TABLE_VENDOR = {
    "name": "Globex Trading",
    "reference": "GX-4410",
    "commercial": [
        ("Vendor", "Globex Trading"),
        ("Quotation Reference", "GX-4410"),
        ("Currency", "USD"),
        ("Unit price", "USD 1,120"),
        ("Quantity", "50"),
        ("Tax", "10%"),
        ("Delivery charges", "USD 300"),
    ],
    "specs": [
        ("RAM", "16 GB"),
        ("Storage", "1 TB"),
        ("Processor cores", "8"),
        ("Display size", "15.6 inch"),
        ("Weight", "1.8 kg"),
        ("Operating system", "Windows 11 Pro"),
        ("Warranty", "3 years"),
        ("Delivery time", "30 days"),
    ],
}

POLICY_SECTIONS = [
    ("Procurement Policy", ["This synthetic policy describes how the fictional organisation buys goods and services."]),
    (
        "Competitive Bidding",
        [
            "Purchases above USD 10,000 shall be competitively bid and require at least three written quotations.",
            "Quotations must be evaluated against the published technical requirements before price is considered.",
        ],
    ),
    (
        "Warranty Standards",
        [
            "All IT hardware purchases must carry a minimum warranty of three years covering parts and labour.",
            "Extended warranty cost shall be stated separately from the unit price.",
        ],
    ),
    (
        "Delivery and Acceptance",
        [
            "Delivery lead time must not exceed 30 days from purchase order unless the Procurement Committee approves.",
            "Goods are accepted only after inspection against the purchase order specification.",
        ],
    ),
    (
        "Approval Authority",
        [
            "Purchases up to USD 50,000 may be approved by the Head of Procurement.",
            "Purchases above USD 50,000 require approval of the Procurement Committee.",
        ],
    ),
    (
        "Price Evaluation",
        [
            "Quotations that deviate by more than 25 percent from the median of comparable quotations shall be reviewed "
            "by a second officer before award.",
            "A price deviation alone is not evidence of wrongdoing and must not be described as such.",
        ],
    ),
    (
        "Conflict of Interest",
        ["Evaluators must declare any financial interest in a bidder and withdraw from that evaluation."],
    ),
    ("Sustainability", ["Preference shall be given to equipment carrying recognised energy efficiency certification."]),
]

HISTORY_ROWS = [
    ("Business laptops", 1090, "USD", "2025-03-12", "Northwind Computers"),
    ("Business laptops", 1135, "USD", "2025-06-20", "Contoso Systems"),
    ("Business laptops", 1210, "USD", "2025-09-02", "Northwind Computers"),
    ("Business laptops", 1180, "USD", "2025-11-18", "Globex Trading"),
    ("Business laptops", 1250, "USD", "2026-02-09", "Northwind Computers"),
    ("Business laptops", 1195, "USD", "2026-04-27", "Globex Trading"),
    ("Office chairs", 140, "USD", "2025-05-05", "Chairs Inc"),
]


def _pdf(lines_by_page: list[list[tuple[str, str]]]) -> bytes:
    """lines: (style, text) where style is 'h' (heading) or 'p'."""
    styles = getSampleStyleSheet()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    story: list = []
    for i, page in enumerate(lines_by_page):
        if i:
            story.append(PageBreak())
        for style, text in page:
            story.append(Paragraph(text, styles["Heading2"] if style == "h" else styles["BodyText"]))
            story.append(Spacer(1, 3))
    doc.build(story)
    return buf.getvalue()


def tender_pdf() -> bytes:
    page = [("p", f"<i>{BANNER}</i>")]
    for line in TENDER_LINES:
        heading = ":" not in line and len(line.split()) <= 4
        page.append(("h" if heading else "p", line))
    return _pdf([page])


def vendor_pdf(key: str) -> bytes:
    v = VENDORS[key]
    page1 = [("p", f"<i>{BANNER}</i>"), ("h", "Quotation")]
    page1 += [
        ("p", f"{k}: {v[k]}")
        for k in ("Vendor", "Quotation Reference", "Currency", "Unit price", "Quantity", "Tax", "Delivery charges")
    ]
    page2 = [("h", "Offered Specifications")] + [("p", f"{k}: {val}") for k, val in v["specs"]]
    return _pdf([page1, page2])


def table_vendor_pdf() -> bytes:
    styles = getSampleStyleSheet()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)

    def table(rows):
        t = Table([["Field", "Value"]] + [list(r) for r in rows], colWidths=[180, 260])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey)]))
        return t

    story = [
        Paragraph(f"<i>{BANNER}</i>", styles["BodyText"]),
        Paragraph("Quotation", styles["Heading2"]),
        table(TABLE_VENDOR["commercial"]),
        Spacer(1, 12),
        Paragraph("Offered Specifications", styles["Heading2"]),
        table(TABLE_VENDOR["specs"]),
    ]
    doc.build(story)
    return buf.getvalue()


def policy_pdf() -> bytes:
    pages: list[list[tuple[str, str]]] = [[("p", f"<i>{BANNER}</i>")]]
    for i, (title, paras) in enumerate(POLICY_SECTIONS):
        page = pages[0] if i < 4 else (pages[1] if len(pages) > 1 else None)
        if page is None:
            pages.append([])
            page = pages[1]
        page.append(("h", title))
        page += [("p", p) for p in paras]
    return _pdf(pages)


def history_csv() -> bytes:
    lines = ["item,unit_price,currency,date,supplier"]
    lines += [f"{i},{p},{c},{d},{s}" for i, p, c, d, s in HISTORY_ROWS]
    return ("\n".join(lines) + "\n").encode()


def scanned_page_pdf(text: str = "Scanned requirement: Minimum RAM: 16 GB") -> bytes:
    """A PDF whose only content is a raster image of text, to exercise the OCR path."""
    import pymupdf as fitz
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (1400, 300), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 56)
    except OSError:
        font = ImageFont.load_default()
    draw.text((40, 100), text, fill="black", font=font)
    png = io.BytesIO()
    img.save(png, "PNG")
    doc = fitz.open()
    page = doc.new_page(width=595, height=200)
    page.insert_image(page.rect, stream=png.getvalue())
    out = doc.tobytes()
    doc.close()
    return out


def all_samples() -> dict[str, bytes]:
    files = {
        "tender_laptops.pdf": tender_pdf(),
        "policy_procurement.pdf": policy_pdf(),
        "historical_purchases.csv": history_csv(),
        "quotation_globex_table.pdf": table_vendor_pdf(),
    }
    for key in VENDORS:
        files[f"quotation_{key}.pdf"] = vendor_pdf(key)
    return files


def write_samples(directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, blob in all_samples().items():
        p = directory / name
        p.write_bytes(blob)
        paths.append(p)
    (directory / "README.txt").write_text(
        "All files in this folder are SYNTHETIC. They contain fictional vendors, prices and policies.\n"
        "Regenerate with: python scripts/generate_sample_data.py\n"
    )
    return paths

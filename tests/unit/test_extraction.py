from procureai.document_processing.classification.classifier import classify_text
from procureai.document_processing.extraction.historical import parse_historical_csv
from procureai.document_processing.extraction.quotation import extract_quotation
from procureai.document_processing.extraction.requirements import extract_requirements
from procureai.rag.chunking.chunker import chunk_pages
from procureai.rag.evaluation import reciprocal_rank, summarize
from procureai.shared.enums import DocumentType, Operator


def test_requirements_from_text():
    text = (
        "Tender Notice\nTender No: X1\nTechnical Requirements\nMinimum RAM: 16 GB (mandatory)\n"
        "Delivery: within 30 days\nWarranty: at least 3 years\nWeight: maximum 1.8 kg (desirable)\n"
        "Display size: 14 to 15.6 inches\n"
    )
    reqs = {r.field: r for r in extract_requirements([(1, text)])}
    assert "tender_no" not in reqs
    assert reqs["ram"].operator == Operator.GTE and reqs["ram"].value == "16"
    assert reqs["delivery_time"].operator == Operator.LTE
    assert reqs["weight"].criticality.value == "desirable"
    assert reqs["display_size"].operator == Operator.BETWEEN and reqs["display_size"].value_max == "15.6"
    assert all(r.page == 1 and r.source_text for r in reqs.values())


def test_requirements_ignore_outside_section():
    text = "Terms\nPayment: 30 days after delivery\nTechnical Requirements\nMinimum RAM: 8 GB\nInstructions\nNote: x\n"
    assert [r.field for r in extract_requirements([(1, text)])] == ["ram"]


def test_pipe_row_requirement():
    reqs = extract_requirements([(2, "REQ-01 | RAM | >= | 16 | GB | Mandatory")])
    assert reqs[0].field == "ram" and reqs[0].page == 2


def test_quotation_conflict_noted():
    q = extract_quotation([(1, "Vendor: A\nUnit price: USD 10\nRAM: 8 GB\nRAM: 16 GB\n")], "a.pdf")
    assert q.unit_price == 10 and q.currency == "USD"
    assert len(q.specs) == 1 and any("Conflicting" in n for n in q.notes)


def test_quotation_vendor_fallback_from_filename():
    q = extract_quotation([(1, "RAM: 16 GB\n")], "acme_corp.pdf")
    assert q.vendor_name == "Acme Corp" and q.notes


def test_historical_csv_skips_bad_rows():
    rows, skipped = parse_historical_csv("item,unit_price,currency\nLaptop,1000,USD\nLaptop,abc,USD\n,5,USD\n")
    assert len(rows) == 1 and skipped == 2


def test_classifier():
    assert classify_text("Technical requirements for bidders. Tender notice.")[0] == DocumentType.TENDER
    assert classify_text("Quotation. Unit price USD 5. Vendor offered specifications")[0] == DocumentType.QUOTATION
    assert classify_text("Procurement policy. Approval authority limits.")[0] == DocumentType.POLICY
    assert classify_text("hello")[0] == DocumentType.OTHER


def test_chunking_keeps_pages_and_sections():
    pages = [(1, "Warranty Standards\nHardware needs three years.\n"), (2, "Delivery\nWithin 30 days.\n")]
    chunks = chunk_pages(pages)
    assert [c.page for c in chunks] == [1, 2] and chunks[0].section == "Warranty Standards"


def test_chunk_overlap_for_long_sections():
    text = "Heading One\n" + " ".join(f"w{i}" for i in range(600))
    chunks = chunk_pages([(1, text)], target_tokens=130, overlap_tokens=20)
    assert len(chunks) > 3 and all(c.page == 1 for c in chunks)


def test_metrics():
    assert reciprocal_rank(["a", "b", "c"], frozenset({"c"})) == 1 / 3
    m = summarize([(["a", "b"], frozenset({"a"})), (["x", "a"], frozenset({"a"}))], 2)
    assert m["mrr"] == 0.75 and m["recall@2"] == 1.0 and m["precision@2"] == 0.5

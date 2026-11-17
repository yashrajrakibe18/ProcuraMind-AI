import pytest

from procureai.analytics.pricing.baselines import evaluate_price
from procureai.domain.compliance.rules import OfferedValue, RequirementSpec, evaluate_requirement
from procureai.domain.pricing.calc import MissingPricingData, calculate_quote_cost, convert_currency
from procureai.domain.requirements.units import convert, parse_quantity
from procureai.shared.enums import ComplianceStatus as S
from procureai.shared.enums import Operator as Op


def req(op, value, unit=None, vmax=None):
    return RequirementSpec("f", op, value, unit, vmax, "F")


def off(text, num=None, unit=None, conf=0.9):
    return OfferedValue(text, num, unit, conf)


@pytest.mark.parametrize(
    "op,val,unit,offered,expected",
    [
        (Op.GTE, "16", "GB", off("16 GB", 16, "gb"), S.MEETS),
        (Op.GTE, "16", "GB", off("8 GB", 8, "gb"), S.FAILS),
        (Op.GTE, "16", "GB", off("1 TB", 1000, "gb"), S.MEETS),
        (Op.GTE, "3", "years", off("36 months", 36, "months"), S.MEETS),
        (Op.GTE, "3", "years", off("24 months", 24, "months"), S.FAILS),
        (Op.LTE, "30", "days", off("6 weeks", 42, "days"), S.FAILS),
        (Op.LTE, "30", "days", off("30 days", 30, "days"), S.MEETS),
        (Op.GT, "8", None, off("8", 8), S.FAILS),
        (Op.LT, "8", None, off("7", 7), S.MEETS),
        (Op.EQ, "8", None, off("8", 8), S.MEETS),
    ],
)
def test_numeric_rules(op, val, unit, offered, expected):
    assert evaluate_requirement(req(op, val, unit), offered).status == expected


def test_between_inclusive():
    r = req(Op.BETWEEN, "14", "inches", "15.6")
    assert evaluate_requirement(r, off("15.6 inch", 15.6, "inch")).status == S.MEETS
    assert evaluate_requirement(r, off("13.3 inch", 13.3, "inch")).status == S.FAILS


def test_missing_is_flagged():
    out = evaluate_requirement(req(Op.GTE, "16", "GB"), None)
    assert out.status == S.MISSING and out.review_required


def test_incompatible_units_go_to_review():
    out = evaluate_requirement(req(Op.GTE, "16", "GB"), off("16 kg", 16, "kg"))
    assert out.status == S.REVIEW


def test_missing_unit_goes_to_review():
    assert evaluate_requirement(req(Op.GTE, "16", "GB"), off("16", 16, None)).status == S.REVIEW


def test_non_numeric_for_numeric_rule_goes_to_review():
    assert evaluate_requirement(req(Op.GTE, "16", "GB"), off("as per standard")).status == S.REVIEW


def test_low_confidence_goes_to_review():
    assert evaluate_requirement(req(Op.GTE, "16", "GB"), off("16 GB", 16, "gb", 0.3)).status == S.REVIEW


def test_categorical_match_and_ambiguity():
    r = req(Op.EQ, "Windows 11 Pro")
    assert evaluate_requirement(r, off("Windows 11 Pro")).status == S.MEETS
    # never asserts failure on text alone: wording may differ
    assert evaluate_requirement(r, off("Windows 11 Home")).status == S.REVIEW


def test_unit_parsing():
    assert parse_quantity("16 GB DDR5").value == 16
    assert parse_quantity("3 years").value == 36
    assert parse_quantity("8th gen CPU") is None
    assert parse_quantity("Windows 11") is None
    assert convert(1, "tb", "gb") == 1000
    assert convert(1, "kg", "gb") is None


def test_cost_and_fx():
    c = calculate_quote_cost(1000, 10, "usd", 10, 100)
    assert (c.subtotal, c.tax_amount, c.total, c.unit_price_all_in) == (10000, 1000, 11100, 1110)
    assert convert_currency(100, "EUR", "USD", {"EUR": 1.1, "USD": 1.0}) == pytest.approx(110)
    with pytest.raises(MissingPricingData):
        convert_currency(1, "XXX", "USD", {"USD": 1.0})
    with pytest.raises(MissingPricingData):
        calculate_quote_cost(None, 10, "USD", 0, 0)


def test_baselines():
    assert evaluate_price(100, [100], "x").method == "insufficient_data"
    small = evaluate_price(200, [100, 105, 110], "x")
    assert small.anomaly_flag and "not a finding" in small.explanation
    assert not evaluate_price(105, [100, 105, 110], "x").anomaly_flag
    big = evaluate_price(300, [100, 102, 98, 101, 99, 103], "x")
    assert big.method == "modified_zscore" and big.anomaly_flag

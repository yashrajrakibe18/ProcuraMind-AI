"""Transparent statistical baselines. Flags are 'review' signals, never fraud/overpricing verdicts."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

MIN_POINTS_FOR_ROBUST = 5
MIN_POINTS_FOR_BASELINE = 2


@dataclass(frozen=True)
class BaselineResult:
    baseline: float | None
    deviation_pct: float | None
    method: str
    anomaly_flag: bool
    explanation: str


def evaluate_price(
    value: float, reference_prices: list[float], source_label: str, threshold_pct: float = 25.0
) -> BaselineResult:
    """Compare ``value`` with reference prices (peer quotes and/or historical purchases).

    * >= 5 points: modified z-score (median/MAD) with |z| > 3.5 flag, or IQR fences as a fallback when MAD == 0.
    * 2-4 points: median baseline with a fixed percentage-deviation threshold.
    * < 2 points: no baseline; nothing is flagged.
    """
    refs = np.asarray([p for p in reference_prices if p is not None and p > 0], dtype=float)
    n = len(refs)
    if n < MIN_POINTS_FOR_BASELINE:
        return BaselineResult(
            None,
            None,
            "insufficient_data",
            False,
            f"Only {n} comparable price point(s) from {source_label}; no baseline computed.",
        )
    median = float(np.median(refs))
    dev = (value - median) / median * 100.0 if median else None

    if n >= MIN_POINTS_FOR_ROBUST:
        mad = float(np.median(np.abs(refs - median)))
        if mad > 0:
            z = 0.6745 * (value - median) / mad
            flag = abs(z) > 3.5
            expl = (
                f"Modified z-score {z:+.2f} vs median {median:,.2f} across {n} points from {source_label} "
                f"(flag when |z| > 3.5)."
            )
            return BaselineResult(median, dev, "modified_zscore", flag, expl + _review_note(flag))
        q1, q3 = np.percentile(refs, [25, 75])
        iqr = q3 - q1
        low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        flag = bool(value < low or value > high)
        expl = f"IQR fences [{low:,.2f}, {high:,.2f}] from {n} points ({source_label}); median {median:,.2f}."
        return BaselineResult(median, dev, "iqr", flag, expl + _review_note(flag))

    flag = dev is not None and abs(dev) > threshold_pct
    expl = (
        f"Median baseline {median:,.2f} from {n} points ({source_label}); "
        f"deviation {dev:+.1f}% (flag when beyond ±{threshold_pct:.0f}%). Small sample, interpret with care."
    )
    return BaselineResult(median, dev, "median_deviation", flag, expl + _review_note(flag))


def _review_note(flag: bool) -> str:
    return (
        " Flagged for review: this is a statistical deviation, not a finding of overpricing or fraud." if flag else ""
    )

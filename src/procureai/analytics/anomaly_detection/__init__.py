"""Anomaly detection lives in analytics.pricing.baselines (transparent statistics first).

ML-based detectors are intentionally not enabled: they need sufficient comparable historical data
and an evaluation set (precision/recall/F1). See docs/decisions/0003-no-ml-price-model.md.
"""

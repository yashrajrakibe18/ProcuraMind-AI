"""Optional ML outlier signal, used only when there is enough comparable history.

The result is ADVISORY text; it never sets a flag by itself. With no labelled outcomes in the data there is
nothing to compute precision/recall against, so it must not be presented as validated detection.
"""

from __future__ import annotations

import numpy as np
from sklearn.ensemble import IsolationForest


def isolation_advisory(history: list[float], candidate: float, min_rows: int) -> str | None:
    if len(history) < min_rows:
        return None
    x = np.asarray(history, dtype=float).reshape(-1, 1)
    model = IsolationForest(n_estimators=100, contamination="auto", random_state=0).fit(x)
    outlier = model.predict(np.asarray([[candidate]]))[0] == -1
    return (
        f"ML advisory (IsolationForest, n={len(history)}, unvalidated): candidate looks like "
        f"{'an outlier' if outlier else 'an inlier'} relative to history."
    )

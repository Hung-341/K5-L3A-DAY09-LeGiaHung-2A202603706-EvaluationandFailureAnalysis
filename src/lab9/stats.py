"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

from collections.abc import Sequence
from math import comb

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    if len(human) != len(judge):
        raise ValueError("human and judge must have the same length")
    cm = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for h, j in zip(human, judge):
        cm[("t" if h == j else "f") + ("p" if j == POS else "n")] += 1
    return cm


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    cm = confusion(human, judge)
    flagged, actual = cm["tp"] + cm["fp"], cm["tp"] + cm["fn"]
    return (cm["tp"] / flagged if flagged else 0.0, cm["tp"] / actual if actual else 0.0)


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    cm = confusion(human, judge)
    n = sum(cm.values())
    if n == 0:
        raise ValueError("kappa is undefined for an empty sample")
    p_o = (cm["tp"] + cm["tn"]) / n
    p_e = ((cm["tp"] + cm["fn"]) * (cm["tp"] + cm["fp"]) + (cm["tn"] + cm["fp"]) * (cm["tn"] + cm["fn"])) / n**2
    if p_e == 1:
        raise ValueError("kappa is undefined: human and judge are the same constant")
    return (p_o - p_e) / (1 - p_e)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1]."""
    informativeness = sensitivity + specificity - 1
    if informativeness <= 0:
        # A judge no better than chance cannot be corrected; keep the observed rate so that
        # lab9.judge still reports FAIL floors instead of crashing.
        return min(1.0, max(0.0, observed_rate))
    return min(1.0, max(0.0, (observed_rate + specificity - 1) / informativeness))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    import numpy as np
    from scipy.stats import bootstrap

    x, y = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if x.shape != y.shape or x.size == 0:
        raise ValueError("a and b must be non-empty and the same length")
    if np.array_equal(x, y):
        return 0.0, 0.0, 0.0      # zero spread: scipy would return a degenerate interval
    if x.size == 1:
        d = float(x[0] - y[0])    # one item (a one-item slice): no spread to resample, report the point
        return d, d, d
    res = bootstrap((x, y), lambda u, v, axis=-1: np.mean(u, axis=axis) - np.mean(v, axis=axis),
                    paired=True, vectorized=True, n_resamples=n_resamples, confidence_level=confidence,
                    method="percentile", rng=np.random.default_rng(rng))
    return float(x.mean() - y.mean()), float(res.confidence_interval.low), float(res.confidence_interval.high)


def _check_nck(n: int, c: int, k: int) -> None:
    if not (0 <= c <= n) or not (1 <= k <= n):
        raise ValueError(f"need 0 <= c <= n and 1 <= k <= n, got n={n} c={c} k={k}")


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n."""
    _check_nck(n, c, k)
    return 1 - comb(n - c, k) / comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    _check_nck(n, c, k)
    return comb(c, k) / comb(n, k)

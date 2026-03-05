# src/qae/postprocess.py
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

import numpy as np


@dataclass(frozen=True)
class MLEAmplitudeResult:
    a_hat: float
    theta_hat: float
    nll: float


def _p_k(a: float, k: int) -> float:
    a = min(max(a, 0.0), 1.0)
    theta = math.asin(math.sqrt(a))
    return math.sin((2 * k + 1) * theta) ** 2


def _nll(a: float, ks: Sequence[int], m: Sequence[int], N: Sequence[int], eps: float = 1e-12) -> float:
    val = 0.0
    for k, mk, Nk in zip(ks, m, N):
        pk = _p_k(a, int(k))
        pk = min(max(pk, eps), 1.0 - eps)
        val -= mk * math.log(pk) + (Nk - mk) * math.log(1.0 - pk)
    return val


def mle_amplitude(
    ks: Sequence[int],
    successes: Sequence[int],
    shots: Sequence[int],
    grid_size: int = 20001,
) -> MLEAmplitudeResult:
    """
    Conservative, dependency-free MLE for amplitude 'a' in [0,1].

    Strategy:
      1) dense grid search on a in [0,1]
      2) local refinement with a few steps of golden-section on [a0-d, a0+d]

    This is robust for small K (e.g., ks=[0,1,2]) typical on Triangulum.
    """
    ks = [int(x) for x in ks]
    m = [int(x) for x in successes]
    N = [int(x) for x in shots]

    # 1) grid search
    A = np.linspace(0.0, 1.0, grid_size)
    nlls = np.array([_nll(float(a), ks, m, N) for a in A])
    idx = int(np.argmin(nlls))
    a0 = float(A[idx])

    # 2) golden-section refinement
    # bracket
    d = 5.0 / grid_size
    lo = max(0.0, a0 - d)
    hi = min(1.0, a0 + d)

    phi = (1 + 5**0.5) / 2
    invphi = 1 / phi

    x1 = hi - (hi - lo) * invphi
    x2 = lo + (hi - lo) * invphi
    f1 = _nll(x1, ks, m, N)
    f2 = _nll(x2, ks, m, N)

    for _ in range(60):
        if f1 > f2:
            lo = x1
            x1 = x2
            f1 = f2
            x2 = lo + (hi - lo) * invphi
            f2 = _nll(x2, ks, m, N)
        else:
            hi = x2
            x2 = x1
            f2 = f1
            x1 = hi - (hi - lo) * invphi
            f1 = _nll(x1, ks, m, N)

        if abs(hi - lo) < 1e-12:
            break

    a_hat = float((lo + hi) / 2.0)
    theta_hat = float(math.asin(math.sqrt(min(max(a_hat, 0.0), 1.0))))
    nll_hat = float(_nll(a_hat, ks, m, N))
    return MLEAmplitudeResult(a_hat=a_hat, theta_hat=theta_hat, nll=nll_hat)


@dataclass(frozen=True)
class IntegralReport:
    y: float
    a_hat: float
    I_hat: float


def amplitude_to_integral_report(y: float, a_hat: float) -> IntegralReport:
    """
    For a uniform grid discretization of [0,y], the integral estimator is:
      I_hat = y * a_hat
    """
    return IntegralReport(y=float(y), a_hat=float(a_hat), I_hat=float(y) * float(a_hat))

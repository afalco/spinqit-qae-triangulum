# src/qae/integrands.py

from __future__ import annotations

import math
import re
from typing import Final, Literal

OfficialGFunc = Literal[
    "1/4",
    "sin^2(pi*x/2)",
    "sin^2(pi*x)",
    "x",
    "x^2",
]

OFFICIAL_GFUNCS: Final[tuple[str, ...]] = (
    "1/4",
    "sin^2(pi*x/2)",
    "sin^2(pi*x)",
    "x",
    "x^2",
)


def ensure_one_integrand(
    gfunc: str | None = None,
    expr: str | None = None,
) -> None:
    if (gfunc is None) == (expr is None):
        raise ValueError("Provide exactly one of gfunc or expr.")


def _clip01(v: float) -> float:
    return min(max(v, 0.0), 1.0)


def official_gfunc_value(x: float, gfunc: OfficialGFunc) -> float:
    if gfunc == "1/4":
        return 0.25
    if gfunc == "sin^2(pi*x/2)":
        return math.sin(math.pi * x / 2.0) ** 2
    if gfunc == "sin^2(pi*x)":
        return math.sin(math.pi * x) ** 2
    if gfunc == "x":
        return x
    if gfunc == "x^2":
        return x**2
    raise ValueError(f"Unknown official gfunc: {gfunc}")


def eval_expr(x: float, expr: str) -> float:
    """
    Safe(ish) expression evaluator for custom integrands.

    Supported names:
      x, pi, e,
      sin, cos, tan,
      asin, acos, atan,
      sqrt, exp, log, log10,
      fabs, abs
    """
    allowed = {
        "x": x,
        "pi": math.pi,
        "e": math.e,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "asin": math.asin,
        "acos": math.acos,
        "atan": math.atan,
        "sqrt": math.sqrt,
        "exp": math.exp,
        "log": math.log,
        "log10": math.log10,
        "fabs": math.fabs,
        "abs": abs,
    }
    return float(eval(expr, {"__builtins__": {}}, allowed))


def g_value(
    x: float,
    gfunc: OfficialGFunc | None = None,
    expr: str | None = None,
) -> float:
    ensure_one_integrand(gfunc, expr)
    if gfunc is not None:
        return official_gfunc_value(x, gfunc)
    assert expr is not None
    return eval_expr(x, expr)


def theta_from_value(v: float) -> float:
    """
    Given v in [0,1], return theta such that sin^2(theta/2) = v.
    """
    vv = _clip01(v)
    return 2.0 * math.asin(math.sqrt(vv))


def exact_integral(
    y: float,
    gfunc: OfficialGFunc | None = None,
    expr: str | None = None,
) -> float | None:
    """
    Return the exact integral over [0,y] when available.

    For custom expressions we return None by default.
    """
    ensure_one_integrand(gfunc, expr)

    if gfunc == "1/4":
        return 0.25 * y

    if gfunc == "sin^2(pi*x/2)":
        return 0.5 * y - math.sin(math.pi * y) / (2.0 * math.pi)

    if gfunc == "sin^2(pi*x)":
        return 0.5 * y - math.sin(2.0 * math.pi * y) / (4.0 * math.pi)

    if gfunc == "x":
        return 0.5 * y**2

    if gfunc == "x^2":
        return y**3 / 3.0

    return None


def integrand_label(
    gfunc: OfficialGFunc | None = None,
    expr: str | None = None,
) -> str:
    ensure_one_integrand(gfunc, expr)
    if gfunc is not None:
        return gfunc
    assert expr is not None
    return expr


def integrand_slug(
    gfunc: OfficialGFunc | None = None,
    expr: str | None = None,
) -> str:
    label = integrand_label(gfunc=gfunc, expr=expr)
    slug = label.lower().strip()

    replacements = {
        "sin^2(pi*x/2)": "sin2_pi_x_over_2",
        "sin^2(pi*x)": "sin2_pi_x",
        "1/4": "const_quarter",
        "x^2": "x2",
    }
    if slug in replacements:
        return replacements[slug]

    slug = slug.replace("^", "pow")
    slug = slug.replace("/", "_over_")
    slug = slug.replace("*", "_")
    slug = slug.replace("(", "_")
    slug = slug.replace(")", "_")
    slug = slug.replace("+", "_plus_")
    slug = slug.replace("-", "_minus_")
    slug = slug.replace(" ", "_")
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "integrand"


def official_closed_form_theta(
    x: float,
    gfunc: OfficialGFunc | None = None,
) -> float | None:
    """
    Closed forms used to preserve exact affine-friendly constructions when possible.
    """
    if gfunc == "1/4":
        return math.pi / 3.0
    if gfunc == "sin^2(pi*x/2)":
        return math.pi * x
    if gfunc == "sin^2(pi*x)":
        return 2.0 * math.pi * x
    return None
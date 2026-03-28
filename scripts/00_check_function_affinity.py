# scripts/00_check_function_affinity.py

from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime, timezone

from src.qae.integrands import (
    OFFICIAL_GFUNCS,
    exact_integral,
    g_value,
    integrand_label,
    integrand_slug,
    official_closed_form_theta,
    theta_from_value,
)
from src.qae.quadrature import grid_points


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Check whether the 4-point angle table induced by an integrand is exactly affine "
            "for the current 2-index-qubit Triangulum-friendly discretization.\n\n"
            "Important: this diagnostic evaluates the GENERIC amplitude-to-angle mapping\n"
            "    theta = 2*asin(sqrt(g(x)))\n"
            "and does not classify a function as affine merely because the implementation\n"
            "provides a special closed-form angle parametrization for compilation."
        )
    )

    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--gfunc",
        type=str,
        choices=OFFICIAL_GFUNCS,
        help=(
            "Official reproducible integrand. "
            "Choices: '1/4', 'sin^2(pi*x/2)', 'sin^2(pi*x)', 'x', 'x^2'."
        ),
    )
    group.add_argument(
        "--expr",
        type=str,
        help=(
            "Custom expression in x, e.g. "
            "'4*x*(1-x)', 'cos(pi*x)**2', 'sin(pi*x/2)**2'."
        ),
    )

    p.add_argument("--y", type=float, default=1.0, help="Upper limit y in [0,1].")
    p.add_argument(
        "--rule",
        type=str,
        default="midpoint",
        choices=["left", "right", "midpoint"],
        help="Quadrature grid rule.",
    )
    p.add_argument("--tol", type=float, default=1e-9, help="Tolerance for exact affine check.")
    p.add_argument(
        "--outdir",
        type=str,
        default="data/processed",
        help="Output directory for optional JSON/CSV diagnostic artifacts.",
    )
    p.add_argument(
        "--save",
        action="store_true",
        help="If set, save the diagnostic summary as JSON and CSV.",
    )
    return p.parse_args()


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def write_csv(rows: list[dict], out_csv: str) -> None:
    if not rows:
        with open(out_csv, "w", encoding="utf-8", newline=""):
            pass
        return

    fieldnames = list(rows[0].keys())
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def current_utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def affine_fit_from_angles(t00: float, t01: float, t10: float, t11: float):
    c0 = t00
    c1 = t10 - t00
    c2 = t01 - t00
    t11_fit = c0 + c1 + c2
    residual = abs(t11_fit - t11)
    return c0, c1, c2, t11_fit, residual


def classify_affinity(residual: float, tol: float) -> str:
    if residual <= tol:
        return "hardware-friendly"
    if residual <= 1e-2:
        return "candidate (very close to affine)"
    if residual <= 5e-2:
        return "candidate (approximate affine compression may be possible)"
    return "simulation-ready / likely too deep for current Triangulum path"


def recommendation_from_classification(
    label: str,
    gfunc: str | None,
    expr: str | None,
    y: float,
    rule: str,
) -> str:
    if gfunc is not None:
        quoted = repr(gfunc)
        if label == "hardware-friendly":
            return (
                "Proceed to Triangulum test: "
                f"python -m scripts.02_run_mlae_triangulum --gfunc {quoted} "
                f"--y {y} --rule {rule} --ks 0,1 --shots 1024 ..."
            )
        return (
            "Validate in simulation first: "
            f"python -m scripts.01_run_mlae_sim --gfunc {quoted} "
            f"--y {y} --rule {rule} --ks 0,1 --shots 4096"
        )

    assert expr is not None
    quoted = repr(expr)
    if label == "hardware-friendly":
        return (
            "Exploratory result: the custom expression looks hardware-friendly "
            "on the current 4-point grid. "
            f"Try directly: python -m scripts.02_run_mlae_triangulum --expr {quoted} "
            f"--y {y} --rule {rule} --ks 0,1 --shots 1024 ..."
        )
    return (
        "Custom expression is not exactly affine on the current grid. "
        f"Try first: python -m scripts.01_run_mlae_sim --expr {quoted} "
        f"--y {y} --rule {rule} --ks 0,1 --shots 4096"
    )


def build_generic_angle_table(
    y: float,
    rule: str,
    gfunc: str | None = None,
    expr: str | None = None,
):
    """
    Build the 4-point angle table using the GENERIC mapping

        theta(x) = 2 * asin(sqrt(g(x)))

    This is the mathematical affinity diagnostic we want here.

    It intentionally does NOT substitute any special closed-form theta
    parametrization that may be available for selected official functions.
    """
    grid = grid_points(y=y, n=2, rule=rule)
    patterns = []

    for i, x_i in enumerate(grid.points):
        bits = tuple((i >> (1 - b)) & 1 for b in range(2))
        gx = g_value(x_i, gfunc=gfunc, expr=expr)
        theta = theta_from_value(gx)
        patterns.append((bits, theta, x_i, gx))

    return patterns


def build_closed_form_angle_table_if_available(
    y: float,
    rule: str,
    gfunc: str | None = None,
):
    """
    Optional informational table using the implementation's special closed-form
    parametrization when available for an official gfunc.
    """
    if gfunc is None:
        return None

    grid = grid_points(y=y, n=2, rule=rule)
    patterns = []

    any_closed_form = False
    for i, x_i in enumerate(grid.points):
        bits = tuple((i >> (1 - b)) & 1 for b in range(2))
        theta_cf = official_closed_form_theta(x_i, gfunc=gfunc)
        if theta_cf is not None:
            any_closed_form = True
        patterns.append((bits, theta_cf, x_i))

    return patterns if any_closed_form else None


def main() -> None:
    args = parse_args()

    patterns = build_generic_angle_table(
        y=args.y,
        rule=args.rule,
        gfunc=args.gfunc,
        expr=args.expr,
    )

    angle_map = {bits: theta for bits, theta, _, _ in patterns}
    required = [(0, 0), (0, 1), (1, 0), (1, 1)]
    if any(bits not in angle_map for bits in required):
        raise SystemExit("Unexpected angle table: missing one of the four basis patterns.")

    t00 = angle_map[(0, 0)]
    t01 = angle_map[(0, 1)]
    t10 = angle_map[(1, 0)]
    t11 = angle_map[(1, 1)]

    c0, c1, c2, t11_fit, residual = affine_fit_from_angles(t00, t01, t10, t11)
    label = classify_affinity(residual, args.tol)
    exact_affine = residual <= args.tol

    closed_form_patterns = build_closed_form_angle_table_if_available(
        y=args.y,
        rule=args.rule,
        gfunc=args.gfunc,
    )

    print("=== Function affinity diagnostic ===")
    print(f"integrand        : {integrand_label(gfunc=args.gfunc, expr=args.expr)}")
    print(f"mode             : {'gfunc' if args.gfunc is not None else 'expr'}")
    print(f"y                : {args.y}")
    print(f"rule             : {args.rule}")
    print("theta model      : generic theta = 2*asin(sqrt(g(x)))")
    print()

    print("Grid points and generic angles:")
    for bits, theta, x_i, gx in patterns:
        print(
            f"  bits={bits}  x={x_i:.12f}  g(x)={gx:.12f}  theta={theta:.12f}"
        )
    print()

    print("Angles:")
    print(f"  theta_00 = {t00:.12f}")
    print(f"  theta_01 = {t01:.12f}")
    print(f"  theta_10 = {t10:.12f}")
    print(f"  theta_11 = {t11:.12f}")
    print()

    print("Affine fit:")
    print(f"  c0      = {c0:.12f}")
    print(f"  c1      = {c1:.12f}")
    print(f"  c2      = {c2:.12f}")
    print(f"  t11_fit = {t11_fit:.12f}")
    print(f"  residual= {residual:.12e}")
    print()

    print(f"classification   : {label}")
    print(f"exact_affine     : {exact_affine}")

    if closed_form_patterns is not None:
        print()
        print("Closed-form theta table available for this official gfunc:")
        for bits, theta_cf, x_i in closed_form_patterns:
            if theta_cf is None:
                continue
            print(f"  bits={bits}  x={x_i:.12f}  theta_closed_form={theta_cf:.12f}")
        print("note             : closed-form parametrization is shown for information only")
        print("                   and is NOT used for the affinity classification above.")

    print(
        "recommendation   : "
        + recommendation_from_classification(
            label=label,
            gfunc=args.gfunc,
            expr=args.expr,
            y=args.y,
            rule=args.rule,
        )
    )

    if not args.save:
        return

    ensure_dir(args.outdir)
    stamp = current_utc_stamp()
    slug = integrand_slug(gfunc=args.gfunc, expr=args.expr)
    base = f"affinity_{slug}_y{args.y:g}_{args.rule}_{stamp}"

    out_json = os.path.join(args.outdir, f"{base}.json")
    out_csv = os.path.join(args.outdir, f"{base}.csv")

    payload = {
        "integrand_label": integrand_label(gfunc=args.gfunc, expr=args.expr),
        "gfunc": args.gfunc,
        "expr": args.expr,
        "y": args.y,
        "rule": args.rule,
        "tol": args.tol,
        "theta_model": "generic_2asin_sqrt_g",
        "theta_00": t00,
        "theta_01": t01,
        "theta_10": t10,
        "theta_11": t11,
        "c0": c0,
        "c1": c1,
        "c2": c2,
        "t11_fit": t11_fit,
        "residual": residual,
        "classification": label,
        "exact_affine": exact_affine,
        "exact_integral": exact_integral(args.y, gfunc=args.gfunc, expr=args.expr),
        "grid_points": [
            {
                "bits": "".join(str(b) for b in bits),
                "x": x_i,
                "g_value": gx,
                "theta_generic": theta,
            }
            for bits, theta, x_i, gx in patterns
        ],
        "closed_form_theta_table_available": closed_form_patterns is not None,
        "closed_form_theta_table": (
            [
                {
                    "bits": "".join(str(b) for b in bits),
                    "x": x_i,
                    "theta_closed_form": theta_cf,
                }
                for bits, theta_cf, x_i in closed_form_patterns
                if theta_cf is not None
            ]
            if closed_form_patterns is not None
            else []
        ),
        "timestamp_utc": stamp,
    }
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    write_csv(
        [
            {
                "integrand_label": payload["integrand_label"],
                "gfunc": payload["gfunc"],
                "expr": payload["expr"],
                "y": payload["y"],
                "rule": payload["rule"],
                "tol": payload["tol"],
                "theta_model": payload["theta_model"],
                "theta_00": payload["theta_00"],
                "theta_01": payload["theta_01"],
                "theta_10": payload["theta_10"],
                "theta_11": payload["theta_11"],
                "c0": payload["c0"],
                "c1": payload["c1"],
                "c2": payload["c2"],
                "t11_fit": payload["t11_fit"],
                "residual": payload["residual"],
                "classification": payload["classification"],
                "exact_affine": payload["exact_affine"],
                "exact_integral": payload["exact_integral"],
                "closed_form_theta_table_available": payload["closed_form_theta_table_available"],
                "timestamp_utc": payload["timestamp_utc"],
            }
        ],
        out_csv,
    )
    print(f"[OK] Wrote:\n  {out_json}\n  {out_csv}")


if __name__ == "__main__":
    main()

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
    integrand_label,
    integrand_slug,
)
from src.qae.state_prep import build_A_spec, is_affine_hardware_friendly


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Check whether the 4-point angle table induced by an integrand is exactly affine "
            "for the current 2-index-qubit Triangulum-friendly state preparation."
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
            f"--y {y} --rule {rule} --ks 0,1,2 --shots 4096"
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
        f"--y {y} --rule {rule} --ks 0,1,2 --shots 4096"
    )


def main() -> None:
    args = parse_args()

    spec = build_A_spec(
        y=args.y,
        rule=args.rule,
        gfunc=args.gfunc,
        expr=args.expr,
    )

    angle_map = {bits: theta for bits, theta in spec.patterns}
    required = [(0, 0), (0, 1), (1, 0), (1, 1)]
    if any(bits not in angle_map for bits in required):
        raise SystemExit("Unexpected angle table: missing one of the four basis patterns.")

    t00 = angle_map[(0, 0)]
    t01 = angle_map[(0, 1)]
    t10 = angle_map[(1, 0)]
    t11 = angle_map[(1, 1)]

    c0, c1, c2, t11_fit, residual = affine_fit_from_angles(t00, t01, t10, t11)
    label = classify_affinity(residual, args.tol)
    exact_affine = is_affine_hardware_friendly(spec, tol=args.tol)

    print("=== Function affinity diagnostic ===")
    print(f"integrand        : {integrand_label(gfunc=args.gfunc, expr=args.expr)}")
    print(f"mode             : {'gfunc' if args.gfunc is not None else 'expr'}")
    print(f"y                : {args.y}")
    print(f"rule             : {args.rule}")
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
        "timestamp_utc": stamp,
    }
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    write_csv([payload], out_csv)
    print(f"[OK] Wrote:\n  {out_json}\n  {out_csv}")


if __name__ == "__main__":
    main()

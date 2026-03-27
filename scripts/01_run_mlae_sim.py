# scripts/01_run_mlae_sim.py

from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime, timezone

from src.backends.simulator import SimulatorBackend, SimulatorConfig
from src.qae.integrands import OFFICIAL_GFUNCS, exact_integral, integrand_label, integrand_slug
from src.qae.mlae import run_mlae
from src.qae.postprocess import amplitude_to_integral_report, mle_amplitude
from src.qae.state_prep import build_A_spec, is_affine_hardware_friendly


GFUNC_CHOICES = list(OFFICIAL_GFUNCS)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run MLAE-style QAE numerical-integration demo on the SpinQit simulator."
    )

    p.add_argument("--y", type=float, default=1.0, help="Upper limit y in [0,1] for I(y)=∫_0^y g(x) dx.")

    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--gfunc",
        type=str,
        choices=GFUNC_CHOICES,
        help="Official target function g(x).",
    )
    group.add_argument(
        "--expr",
        type=str,
        help="Custom expression in x for exploratory runs.",
    )

    p.add_argument("--rule", type=str, default="midpoint", choices=["left", "right", "midpoint"])
    p.add_argument("--ks", type=str, default="0,1,2", help="Comma-separated k values, e.g. '0,1,2'.")
    p.add_argument("--shots", type=int, default=4096, help="Shots per k circuit.")
    p.add_argument(
        "--ancilla-bit-index-from-right",
        type=int,
        default=0,
        help=(
            "Which bit (from the right) corresponds to the ancilla in returned bitstrings. "
            "Adjust if your simulator bit ordering differs."
        ),
    )
    p.add_argument("--outdir", type=str, default="data/raw", help="Output directory for raw JSON/CSV results.")
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


def classify_function_for_current_hardware(hardware_friendly: bool) -> str:
    return "hardware-friendly" if hardware_friendly else "simulation-ready"


def main() -> None:
    args = parse_args()
    ks = tuple(int(x.strip()) for x in args.ks.split(",") if x.strip() != "")

    backend = SimulatorBackend(SimulatorConfig())

    rr = run_mlae(
        backend=backend,
        y=args.y,
        ks=ks,
        rule=args.rule,
        shots=args.shots,
        ancilla_bit_index_from_right=args.ancilla_bit_index_from_right,
        gfunc=args.gfunc,
        expr=args.expr,
    )

    spec = build_A_spec(y=args.y, rule=args.rule, gfunc=args.gfunc, expr=args.expr)
    i_exact = exact_integral(args.y, gfunc=args.gfunc, expr=args.expr)
    hardware_friendly = is_affine_hardware_friendly(spec)
    function_class = classify_function_for_current_hardware(hardware_friendly)

    successes = []
    for counts in rr.counts_per_k:
        succ = 0
        for bitstr, c in counts.items():
            s = bitstr.replace("0b", "").strip()
            if len(s) < args.ancilla_bit_index_from_right + 1:
                s = s.zfill(args.ancilla_bit_index_from_right + 1)
            anc_bit = s[-1 - args.ancilla_bit_index_from_right]
            if anc_bit == "1":
                succ += c
        successes.append(succ)

    shots_vec = [rr.shots] * len(rr.ks)
    mle = mle_amplitude(rr.ks, successes, shots_vec)
    report = amplitude_to_integral_report(rr.y, mle.a_hat)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    slug = integrand_slug(gfunc=args.gfunc, expr=args.expr)
    run_id = f"sim_{slug}_y{args.y:g}_{args.rule}_ks{'-'.join(map(str, ks))}_shots{args.shots}_{stamp}"

    ensure_dir(args.outdir)
    out_json = os.path.join(args.outdir, f"{run_id}.json")
    out_csv = os.path.join(args.outdir, f"{run_id}.csv")

    payload = {
        "run_id": run_id,
        "backend": "simulator",
        "integrand_label": integrand_label(gfunc=args.gfunc, expr=args.expr),
        "gfunc": rr.gfunc,
        "expr": rr.expr,
        "y": rr.y,
        "rule": rr.rule,
        "ks": list(rr.ks),
        "shots_per_k": rr.shots,
        "p_hat": list(rr.p_hat),
        "successes": successes,
        "mle": {
            "a_hat": mle.a_hat,
            "theta_hat": mle.theta_hat,
            "nll": mle.nll,
        },
        "integral": {
            "I_hat": report.I_hat,
        },
        "exact_integral": i_exact,
        "abs_error_global": (abs(report.I_hat - i_exact) if i_exact is not None else None),
        "hardware_friendly_affine": hardware_friendly,
        "function_class": function_class,
        "counts_per_k": list(rr.counts_per_k),
        "timestamp_utc": stamp,
    }

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    rows = []
    for k, p, succ in zip(rr.ks, rr.p_hat, successes):
        rows.append(
            {
                "run_id": run_id,
                "backend": "simulator",
                "integrand_label": integrand_label(gfunc=args.gfunc, expr=args.expr),
                "gfunc": rr.gfunc,
                "expr": rr.expr,
                "y": rr.y,
                "function_class": function_class,
                "hardware_friendly_affine": hardware_friendly,
                "rule": rr.rule,
                "k": k,
                "shots": rr.shots,
                "successes": succ,
                "p_hat": p,
                "a_hat_global": mle.a_hat,
                "I_hat_global": report.I_hat,
                "exact_integral": i_exact,
                "abs_error_global": (abs(report.I_hat - i_exact) if i_exact is not None else None),
                "timestamp_utc": stamp,
            }
        )

    write_csv(rows, out_csv)

    label = integrand_label(gfunc=args.gfunc, expr=args.expr)
    print(f"[OK] Wrote:\n  {out_json}\n  {out_csv}")
    print(
        f"[MLE] integrand={label!r} a_hat={mle.a_hat:.6f} I_hat={report.I_hat:.6f}"
        + (f" I_exact={i_exact:.6f}" if i_exact is not None else "")
    )


if __name__ == "__main__":
    main()
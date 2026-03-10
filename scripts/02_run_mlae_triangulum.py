# scripts/02_run_mlae_triangulum.py
from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime, timezone

from src.backends.nmr_triangulum import TriangulumBackend, TriangulumConfig
from src.qae.mlae import run_mlae
from src.qae.postprocess import mle_amplitude, amplitude_to_integral_report
from src.qae.state_prep import (
    build_A_spec,
    exact_integral,
    is_affine_hardware_friendly,
)

GFUNC_CHOICES = ["sin2_pi", "x", "x2", "sqrt_x", "exp_minus_x", "parabola"]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run MLAE-style QAE numerical-integration demo on SpinQ Triangulum (NMR) via SpinQit."
    )
    # NMR connection
    p.add_argument("--ip", type=str, required=True, help="Triangulum IP address.")
    p.add_argument("--port", type=int, default=55444, help="Triangulum port (default 55444).")
    p.add_argument("--account", type=str, required=True, help="Triangulum account/username.")
    p.add_argument("--password", type=str, required=True, help="Triangulum password.")
    p.add_argument("--task-name", type=str, default="qae_mlae", help="Task name in NMR backend.")
    p.add_argument("--task-desc", type=str, default="MLAE-style QAE experiment", help="Task description in NMR backend.")

    # Experiment parameters
    p.add_argument("--y", type=float, default=1.0, help="Upper limit y in [0,1] for I(y)=∫_0^y g(x) dx.")
    p.add_argument(
        "--gfunc",
        type=str,
        default="sin2_pi",
        choices=GFUNC_CHOICES,
        help="Target function g(x).",
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
            "For 3 qubits with ancilla qubit index=0, a common default is 0. "
            "Adjust if your NMR backend bit ordering differs."
        ),
    )
    p.add_argument("--outdir", type=str, default="data/raw", help="Output directory for raw JSON/CSV results.")
    return p.parse_args()


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def write_csv(rows: list[dict], out_csv: str) -> None:
    if not rows:
        with open(out_csv, "w", encoding="utf-8", newline="") as f:
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

    backend = TriangulumBackend(
        TriangulumConfig(
            ip=args.ip,
            port=args.port,
            account=args.account,
            password=args.password,
            task_name=args.task_name,
            task_desc=args.task_desc,
        )
    )

    rr = run_mlae(
        backend=backend,
        y=args.y,
        ks=ks,
        rule=args.rule,
        shots=args.shots,
        ancilla_bit_index_from_right=args.ancilla_bit_index_from_right,
        gfunc=args.gfunc,
    )

    spec = build_A_spec(y=args.y, rule=args.rule, gfunc=args.gfunc)
    i_exact = exact_integral(args.y, args.gfunc)
    hardware_friendly = is_affine_hardware_friendly(spec)
    function_class = classify_function_for_current_hardware(hardware_friendly)

    # Convert counts -> successes
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
    run_id = (
        f"triangulum_{args.gfunc}_y{args.y:g}_{args.rule}_"
        f"ks{'-'.join(map(str, ks))}_shots{args.shots}_{stamp}"
    )

    ensure_dir(args.outdir)
    out_json = os.path.join(args.outdir, f"{run_id}.json")
    out_csv = os.path.join(args.outdir, f"{run_id}.csv")

    payload = {
        "run_id": run_id,
        "backend": "triangulum_nmr",
        "nmr": {
            "ip": args.ip,
            "port": args.port,
            "task_name": args.task_name,
            "task_desc": args.task_desc,
        },
        "y": rr.y,
        "gfunc": rr.gfunc,
        "rule": rr.rule,
        "ks": list(rr.ks),
        "shots_per_k": rr.shots,
        "p_hat": list(rr.p_hat),
        "successes": successes,
        "mle": {"a_hat": mle.a_hat, "theta_hat": mle.theta_hat, "nll": mle.nll},
        "integral": {"I_hat": report.I_hat},
        "exact_integral": i_exact,
        "abs_error_global": (abs(report.I_hat - i_exact) if i_exact is not None else None),
        "hardware_friendly_affine": hardware_friendly,
        "function_class": function_class,
        "counts_per_k": list(rr.counts_per_k),
        "timestamp_utc": stamp,
    }

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    # Flat CSV summary (one row per k)
    rows = []
    for k, p, succ in zip(rr.ks, rr.p_hat, successes):
        rows.append(
            {
                "run_id": run_id,
                "backend": "triangulum_nmr",
                "y": rr.y,
                "gfunc": rr.gfunc,
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

    print(f"[OK] Wrote:\n  {out_json}\n  {out_csv}")
    print(
        f"[MLE] gfunc={args.gfunc}  a_hat={mle.a_hat:.6f}  I_hat={report.I_hat:.6f}"
        + (f"  I_exact={i_exact:.6f}" if i_exact is not None else "")
    )


if __name__ == "__main__":
    main()
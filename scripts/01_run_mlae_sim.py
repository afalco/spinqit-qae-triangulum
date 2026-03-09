from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime, timezone

from src.backends.simulator import SimulatorBackend, SimulatorConfig
from src.qae.mlae import run_mlae
from src.qae.postprocess import mle_amplitude, amplitude_to_integral_report


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run MLAE-style QAE numerical-integration demo on the SpinQit simulator."
    )
    p.add_argument("--y", type=float, default=1.0, help="Upper limit y in [0,1] for I(y)=∫_0^y g(x) dx.")
    p.add_argument("--rule", type=str, default="midpoint", choices=["left", "right", "midpoint"])
    p.add_argument("--ks", type=str, default="0,1,2", help="Comma-separated k values, e.g. '0,1,2'.")
    p.add_argument("--shots", type=int, default=4096, help="Shots per k circuit.")
    p.add_argument(
        "--ancilla-bit-index-from-right",
        type=int,
        default=2,
        help=(
            "Which bit (from the right) corresponds to the ancilla in returned bitstrings. "
            "For 3 qubits with ancilla qubit index=2, a common default is 2. "
            "Adjust if your simulator bit ordering differs."
        ),
    )
    p.add_argument("--outdir", type=str, default="data/raw", help="Output directory for raw JSON/CSV results.")
    return p.parse_args()


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def write_csv(rows: list[dict], out_csv: str) -> None:
    if not rows:
        # Still create an empty file with no content if desired
        with open(out_csv, "w", encoding="utf-8", newline="") as f:
            pass
        return

    fieldnames = list(rows[0].keys())
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


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
    )

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
    run_id = f"sim_y{args.y:g}_{args.rule}_ks{'-'.join(map(str, ks))}_shots{args.shots}_{stamp}"

    ensure_dir(args.outdir)
    out_json = os.path.join(args.outdir, f"{run_id}.json")
    out_csv = os.path.join(args.outdir, f"{run_id}.csv")

    payload = {
        "run_id": run_id,
        "backend": "simulator",
        "y": rr.y,
        "rule": rr.rule,
        "ks": list(rr.ks),
        "shots_per_k": rr.shots,
        "p_hat": list(rr.p_hat),
        "successes": successes,
        "mle": {"a_hat": mle.a_hat, "theta_hat": mle.theta_hat, "nll": mle.nll},
        "integral": {"I_hat": report.I_hat},
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
                "backend": "simulator",
                "y": rr.y,
                "rule": rr.rule,
                "k": k,
                "shots": rr.shots,
                "successes": succ,
                "p_hat": p,
                "a_hat_global": mle.a_hat,
                "I_hat_global": report.I_hat,
                "timestamp_utc": stamp,
            }
        )

    write_csv(rows, out_csv)

    print(f"[OK] Wrote:\n  {out_json}\n  {out_csv}")
    print(f"[MLE] a_hat={mle.a_hat:.6f}  I_hat={report.I_hat:.6f}")


if __name__ == "__main__":
    main()
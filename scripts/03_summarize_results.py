# scripts/03_summarize_results.py
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
from typing import Any, Dict, List


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Summarize multiple MLAE run JSON files into a single CSV (processed)."
    )
    p.add_argument("--indir", type=str, default="data/raw", help="Input directory containing run JSON files.")
    p.add_argument("--outdir", type=str, default="data/processed", help="Output directory for processed summary.")
    p.add_argument("--pattern", type=str, default="*.json", help="Glob pattern for JSON files.")
    return p.parse_args()


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_csv(rows: List[Dict[str, Any]], out_csv: str) -> None:
    if not rows:
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
    ensure_dir(args.outdir)

    files = sorted(glob.glob(os.path.join(args.indir, args.pattern)))
    if not files:
        raise SystemExit(f"No JSON files found in {args.indir} with pattern {args.pattern}")

    rows: List[Dict[str, Any]] = []
    rows_k: List[Dict[str, Any]] = []

    for fp in files:
        obj = load_json(fp)

        run_id = obj.get("run_id", os.path.basename(fp).replace(".json", ""))
        backend = obj.get("backend", "unknown")
        y = obj.get("y", None)
        rule = obj.get("rule", None)
        ks = obj.get("ks", [])
        shots = obj.get("shots_per_k", None)
        p_hat = obj.get("p_hat", [])
        successes = obj.get("successes", [])
        mle = obj.get("mle", {})
        integral = obj.get("integral", {})
        stamp = obj.get("timestamp_utc", None)

        rows.append(
            {
                "run_id": run_id,
                "backend": backend,
                "y": y,
                "rule": rule,
                "ks": ",".join(str(k) for k in ks),
                "shots_per_k": shots,
                "a_hat": mle.get("a_hat", None),
                "theta_hat": mle.get("theta_hat", None),
                "nll": mle.get("nll", None),
                "I_hat": integral.get("I_hat", None),
                "timestamp_utc": stamp,
                "source_json": os.path.basename(fp),
            }
        )

        for k, ph, succ in zip(ks, p_hat, successes):
            rows_k.append(
                {
                    "run_id": run_id,
                    "backend": backend,
                    "y": y,
                    "rule": rule,
                    "k": k,
                    "shots": shots,
                    "successes": succ,
                    "p_hat": ph,
                    "timestamp_utc": stamp,
                    "source_json": os.path.basename(fp),
                }
            )

    out_summary = os.path.join(args.outdir, "summary_runs.csv")
    out_by_k = os.path.join(args.outdir, "summary_by_k.csv")

    write_csv(rows, out_summary)
    write_csv(rows_k, out_by_k)

    print(f"[OK] Wrote:\n  {out_summary}\n  {out_by_k}")
    print(f"[INFO] Runs: {len(rows)}  (k-rows: {len(rows_k)})")


if __name__ == "__main__":
    main()
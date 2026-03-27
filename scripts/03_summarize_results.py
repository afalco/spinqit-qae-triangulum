# scripts/03_summarize_results.py

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Summarize raw MLAE JSON artifacts into compact CSV tables."
    )
    p.add_argument("--rawdir", type=str, default="data/raw", help="Directory containing per-run JSON files.")
    p.add_argument("--outdir", type=str, default="data/processed", help="Directory for summary CSV/JSON outputs.")
    return p.parse_args()


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def load_json(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_csv(rows: list[dict[str, Any]], out_csv: Path) -> None:
    if not rows:
        with open(out_csv, "w", encoding="utf-8", newline=""):
            pass
        return

    fieldnames = list(rows[0].keys())
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    rawdir = Path(args.rawdir)
    outdir = Path(args.outdir)
    ensure_dir(str(outdir))

    json_files = sorted(rawdir.glob("*.json"))
    if not json_files:
        raise SystemExit(f"No JSON files found in {rawdir}")

    runs_rows: list[dict[str, Any]] = []
    by_k_rows: list[dict[str, Any]] = []

    grouped: dict[tuple[str, str | None, str | None, str], list[dict[str, Any]]] = defaultdict(list)

    for path in json_files:
        obj = load_json(path)

        run_row = {
            "run_id": obj.get("run_id"),
            "backend": obj.get("backend"),
            "integrand_label": obj.get("integrand_label"),
            "gfunc": obj.get("gfunc"),
            "expr": obj.get("expr"),
            "y": obj.get("y"),
            "rule": obj.get("rule"),
            "ks": ",".join(str(k) for k in obj.get("ks", [])),
            "shots_per_k": obj.get("shots_per_k"),
            "a_hat": (obj.get("mle") or {}).get("a_hat"),
            "theta_hat": (obj.get("mle") or {}).get("theta_hat"),
            "nll": (obj.get("mle") or {}).get("nll"),
            "I_hat": (obj.get("integral") or {}).get("I_hat"),
            "exact_integral": obj.get("exact_integral"),
            "abs_error_global": obj.get("abs_error_global"),
            "hardware_friendly_affine": obj.get("hardware_friendly_affine"),
            "function_class": obj.get("function_class"),
            "timestamp_utc": obj.get("timestamp_utc"),
        }
        runs_rows.append(run_row)

        ks = obj.get("ks", [])
        p_hat = obj.get("p_hat", [])
        successes = obj.get("successes", [])
        for i, k in enumerate(ks):
            by_k_rows.append(
                {
                    "run_id": obj.get("run_id"),
                    "backend": obj.get("backend"),
                    "integrand_label": obj.get("integrand_label"),
                    "gfunc": obj.get("gfunc"),
                    "expr": obj.get("expr"),
                    "y": obj.get("y"),
                    "rule": obj.get("rule"),
                    "k": k,
                    "shots_per_k": obj.get("shots_per_k"),
                    "successes": successes[i] if i < len(successes) else None,
                    "p_hat": p_hat[i] if i < len(p_hat) else None,
                    "a_hat_global": (obj.get("mle") or {}).get("a_hat"),
                    "I_hat_global": (obj.get("integral") or {}).get("I_hat"),
                    "exact_integral": obj.get("exact_integral"),
                    "abs_error_global": obj.get("abs_error_global"),
                    "timestamp_utc": obj.get("timestamp_utc"),
                }
            )

        key = (
            str(obj.get("backend")),
            obj.get("gfunc"),
            obj.get("expr"),
            str(obj.get("rule")),
        )
        grouped[key].append(obj)

    summary_by_group: list[dict[str, Any]] = []
    for (backend, gfunc, expr, rule), objs in grouped.items():
        i_hats = [
            float((o.get("integral") or {}).get("I_hat"))
            for o in objs
            if (o.get("integral") or {}).get("I_hat") is not None
        ]
        a_hats = [
            float((o.get("mle") or {}).get("a_hat"))
            for o in objs
            if (o.get("mle") or {}).get("a_hat") is not None
        ]
        exact_vals = [o.get("exact_integral") for o in objs if o.get("exact_integral") is not None]
        exact_val = exact_vals[0] if exact_vals else None

        summary_by_group.append(
            {
                "backend": backend,
                "gfunc": gfunc,
                "expr": expr,
                "rule": rule,
                "num_runs": len(objs),
                "mean_a_hat": (sum(a_hats) / len(a_hats) if a_hats else None),
                "mean_I_hat": (sum(i_hats) / len(i_hats) if i_hats else None),
                "exact_integral": exact_val,
                "mean_abs_error": (
                    abs((sum(i_hats) / len(i_hats)) - exact_val)
                    if i_hats and exact_val is not None
                    else None
                ),
            }
        )

    write_csv(runs_rows, outdir / "summary_runs.csv")
    write_csv(by_k_rows, outdir / "summary_by_k.csv")
    write_csv(summary_by_group, outdir / "summary_grouped.csv")

    with open(outdir / "summary_manifest.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "num_json_files": len(json_files),
                "runs_csv": "summary_runs.csv",
                "by_k_csv": "summary_by_k.csv",
                "grouped_csv": "summary_grouped.csv",
            },
            f,
            indent=2,
        )

    print("[OK] Wrote:")
    print(f"  {outdir / 'summary_runs.csv'}")
    print(f"  {outdir / 'summary_by_k.csv'}")
    print(f"  {outdir / 'summary_grouped.csv'}")
    print(f"  {outdir / 'summary_manifest.json'}")


if __name__ == "__main__":
    main()
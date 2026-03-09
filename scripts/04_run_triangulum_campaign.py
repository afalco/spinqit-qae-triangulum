#04_run_triangulum_campaign.py
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_RULES = ("left", "midpoint", "right")
DEFAULT_KS = "0,1"
DEFAULT_SHOTS = 1024


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Run a depth-constrained Triangulum MLAE campaign for the three quadrature rules "
            "(left, midpoint, right), then aggregate the results and compute the Simpson-style combination."
        )
    )
    p.add_argument("--ip", type=str, required=True, help="Triangulum IP address.")
    p.add_argument("--port", type=int, default=55444, help="Triangulum port.")
    p.add_argument("--account", type=str, required=True, help="Triangulum account/username.")
    p.add_argument("--password", type=str, required=True, help="Triangulum password.")
    p.add_argument("--task-prefix", type=str, default="qae_mlae", help="Prefix for backend task names.")
    p.add_argument(
        "--task-desc",
        type=str,
        default="Depth-constrained MLAE campaign on Triangulum",
        help="Task description.",
    )
    p.add_argument("--y", type=float, default=1.0, help="Upper limit y in [0,1].")
    p.add_argument("--ks", type=str, default=DEFAULT_KS, help="Comma-separated k values, typically '0,1'.")
    p.add_argument("--shots", type=int, default=DEFAULT_SHOTS, help="Shots per rule.")
    p.add_argument(
        "--rules",
        type=str,
        default=",".join(DEFAULT_RULES),
        help="Comma-separated rules to run, e.g. 'left,midpoint,right'.",
    )
    p.add_argument(
        "--ancilla-bit-index-from-right",
        type=int,
        default=2,
        help="Ancilla bit index from the right in returned bitstrings.",
    )
    p.add_argument(
        "--raw-outdir",
        type=str,
        default="data/raw",
        help="Directory where per-run JSON/CSV files are written.",
    )
    p.add_argument(
        "--processed-outdir",
        type=str,
        default="data/processed",
        help="Directory where the campaign summary JSON/CSV files are written.",
    )
    p.add_argument(
        "--runner-module",
        type=str,
        default="scripts.02_run_mlae_triangulum",
        help="Module used to launch individual Triangulum runs.",
    )
    p.add_argument(
        "--python-executable",
        type=str,
        default=sys.executable,
        help="Python executable used to launch the per-rule runner.",
    )
    p.add_argument(
        "--pause-seconds",
        type=float,
        default=0.0,
        help="Optional pause between consecutive rule executions.",
    )
    p.add_argument(
        "--reuse-existing",
        action="store_true",
        help=(
            "Reuse the newest matching raw JSON for each requested rule if it already exists, "
            "instead of relaunching the hardware job."
        ),
    )
    return p.parse_args()


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def load_json(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_csv(rows: list[dict[str, Any]], out_csv: Path) -> None:
    if not rows:
        with open(out_csv, "w", encoding="utf-8", newline="") as f:
            pass
        return

    fieldnames = list(rows[0].keys())
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def current_utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def find_newest_matching_json(raw_outdir: Path, prefix: str) -> Path:
    matches = sorted(raw_outdir.glob(f"{prefix}*.json"), key=lambda p: p.stat().st_mtime)
    if not matches:
        raise FileNotFoundError(f"No JSON files found in {raw_outdir} matching prefix '{prefix}'.")
    return matches[-1]


def run_single_rule(args: argparse.Namespace, rule: str) -> Path:
    raw_outdir = Path(args.raw_outdir)
    ensure_dir(str(raw_outdir))

    prefix = f"triangulum_y{args.y:g}_{rule}_ks{args.ks.replace(',', '-')}_shots{args.shots}_"

    if args.reuse_existing:
        try:
            newest = find_newest_matching_json(raw_outdir, prefix)
            print(f"[REUSE] Using existing JSON for rule='{rule}': {newest}")
            return newest
        except FileNotFoundError:
            print(f"[REUSE] No existing JSON found for rule='{rule}'. Launching hardware run.")

    task_name = f"{args.task_prefix}_{rule}"
    cmd = [
        args.python_executable,
        "-m",
        args.runner_module,
        "--ip",
        args.ip,
        "--port",
        str(args.port),
        "--account",
        args.account,
        "--password",
        args.password,
        "--task-name",
        task_name,
        "--task-desc",
        args.task_desc,
        "--y",
        str(args.y),
        "--rule",
        rule,
        "--ks",
        args.ks,
        "--shots",
        str(args.shots),
        "--ancilla-bit-index-from-right",
        str(args.ancilla_bit_index_from_right),
        "--outdir",
        str(raw_outdir),
    ]

    print(f"[RUN] Launching rule='{rule}'")
    masked_cmd = ["***" if x == args.password else x for x in cmd]
    print("[CMD]", " ".join(masked_cmd))
    subprocess.run(cmd, check=True)

    newest = find_newest_matching_json(raw_outdir, prefix)
    print(f"[OK] Collected JSON for rule='{rule}': {newest}")
    return newest


def exact_integral_sin2_pi(y: float) -> float:
    return 0.5 * y - math.sin(2.0 * math.pi * y) / (4.0 * math.pi)


def summarize_campaign(json_paths: dict[str, Path], y: float) -> dict[str, Any]:
    records: dict[str, dict[str, Any]] = {}
    for rule, path in json_paths.items():
        records[rule] = load_json(path)

    missing = [r for r in DEFAULT_RULES if r not in records]
    if missing:
        raise ValueError(f"Cannot compute full campaign summary. Missing rules: {missing}")

    i_left = float(records["left"]["integral"]["I_hat"])
    i_mid = float(records["midpoint"]["integral"]["I_hat"])
    i_right = float(records["right"]["integral"]["I_hat"])
    i_exact = exact_integral_sin2_pi(y)
    i_simpson = (i_left + 4.0 * i_mid + i_right) / 6.0

    return {
        "campaign_id": f"triangulum_campaign_y{y:g}_{current_utc_stamp()}",
        "y": y,
        "ks": records["left"].get("ks"),
        "shots_per_k": records["left"].get("shots_per_k"),
        "I_exact": i_exact,
        "rules": {
            "left": {
                "run_id": records["left"].get("run_id"),
                "I_hat": i_left,
                "a_hat": records["left"].get("mle", {}).get("a_hat"),
                "abs_error": abs(i_left - i_exact),
                "source_json": os.path.basename(json_paths["left"]),
            },
            "midpoint": {
                "run_id": records["midpoint"].get("run_id"),
                "I_hat": i_mid,
                "a_hat": records["midpoint"].get("mle", {}).get("a_hat"),
                "abs_error": abs(i_mid - i_exact),
                "source_json": os.path.basename(json_paths["midpoint"]),
            },
            "right": {
                "run_id": records["right"].get("run_id"),
                "I_hat": i_right,
                "a_hat": records["right"].get("mle", {}).get("a_hat"),
                "abs_error": abs(i_right - i_exact),
                "source_json": os.path.basename(json_paths["right"]),
            },
        },
        "simpson": {
            "I_hat": i_simpson,
            "abs_error": abs(i_simpson - i_exact),
            "formula": "(I_left + 4*I_midpoint + I_right)/6",
        },
    }


def flatten_campaign_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    i_exact = summary["I_exact"]

    for rule in DEFAULT_RULES:
        rec = summary["rules"][rule]
        rows.append(
            {
                "campaign_id": summary["campaign_id"],
                "kind": "rule",
                "rule": rule,
                "I_exact": i_exact,
                "I_hat": rec["I_hat"],
                "abs_error": rec["abs_error"],
                "a_hat": rec["a_hat"],
                "run_id": rec["run_id"],
                "source_json": rec["source_json"],
            }
        )

    rows.append(
        {
            "campaign_id": summary["campaign_id"],
            "kind": "combined",
            "rule": "simpson",
            "I_exact": i_exact,
            "I_hat": summary["simpson"]["I_hat"],
            "abs_error": summary["simpson"]["abs_error"],
            "a_hat": "",
            "run_id": "",
            "source_json": "",
        }
    )
    return rows


def main() -> None:
    args = parse_args()
    rules = tuple(x.strip() for x in args.rules.split(",") if x.strip())
    if set(rules) != set(DEFAULT_RULES):
        raise SystemExit("This campaign script currently expects exactly the three rules: left, midpoint, right.")

    ensure_dir(args.raw_outdir)
    ensure_dir(args.processed_outdir)

    json_paths: dict[str, Path] = {}
    for idx, rule in enumerate(rules):
        json_paths[rule] = run_single_rule(args, rule)
        if args.pause_seconds > 0 and idx < len(rules) - 1:
            time.sleep(args.pause_seconds)

    summary = summarize_campaign(json_paths, y=args.y)
    rows = flatten_campaign_rows(summary)

    stamp = current_utc_stamp()
    out_json = (
        Path(args.processed_outdir)
        / f"campaign_summary_y{args.y:g}_ks{args.ks.replace(',', '-')}_shots{args.shots}_{stamp}.json"
    )
    out_csv = (
        Path(args.processed_outdir)
        / f"campaign_summary_y{args.y:g}_ks{args.ks.replace(',', '-')}_shots{args.shots}_{stamp}.csv"
    )

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    write_csv(rows, out_csv)

    print(f"[OK] Wrote:\n  {out_json}\n  {out_csv}")
    print(
        "[SUMMARY] "
        f"I_left={summary['rules']['left']['I_hat']:.9f}  "
        f"I_midpoint={summary['rules']['midpoint']['I_hat']:.9f}  "
        f"I_right={summary['rules']['right']['I_hat']:.9f}  "
        f"I_simpson={summary['simpson']['I_hat']:.9f}"
    )


if __name__ == "__main__":
    main()
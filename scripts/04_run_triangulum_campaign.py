# scripts/04_run_triangulum_campaign.py

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.qae.integrands import OFFICIAL_GFUNCS, exact_integral, integrand_label, integrand_slug
from src.qae.state_prep import build_A_spec, is_affine_hardware_friendly


DEFAULT_RULES = ("left", "midpoint", "right")
DEFAULT_KS = "0,1"
DEFAULT_SHOTS = 1024
DEFAULT_GFUNC = "sin^2(pi*x)"
GFUNC_CHOICES = list(OFFICIAL_GFUNCS)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Run a depth-constrained Triangulum MLAE campaign for multiple quadrature rules, "
            "then aggregate the results and compute the Simpson-style combination when available."
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

    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--gfunc",
        type=str,
        default=None,
        choices=GFUNC_CHOICES,
        help="Official target function g(x).",
    )
    group.add_argument(
        "--expr",
        type=str,
        default=None,
        help="Custom expression in x for exploratory campaigns.",
    )

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
        default=0,
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


def _timestamp_from_stem(stem: str) -> str:
    """Extract the trailing YYYYMMDDTHHMMSSz segment for deterministic sorting."""
    parts = stem.rsplit("_", 1)
    return parts[-1] if len(parts) == 2 else ""


def find_newest_matching_json(raw_outdir: Path, prefix: str) -> Path:
    matches = sorted(
        raw_outdir.glob(f"{prefix}*.json"),
        key=lambda p: _timestamp_from_stem(p.stem),
    )
    if not matches:
        raise FileNotFoundError(f"No JSON files found in {raw_outdir} matching prefix '{prefix}'.")
    return matches[-1]


def check_affinity_per_rule(
    y: float,
    rules: tuple[str, ...],
    gfunc: str | None = None,
    expr: str | None = None,
) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for rule in rules:
        spec = build_A_spec(y=y, rule=rule, gfunc=gfunc, expr=expr)
        result[rule] = is_affine_hardware_friendly(spec)
    return result


def abort_if_not_affine_friendly(
    y: float,
    rules: tuple[str, ...],
    gfunc: str | None = None,
    expr: str | None = None,
) -> None:
    affinity = check_affinity_per_rule(y=y, rules=rules, gfunc=gfunc, expr=expr)
    bad_rules = [rule for rule, ok in affinity.items() if not ok]
    if bad_rules:
        details = ", ".join(f"{rule}=non-affine" for rule in bad_rules)
        all_details = ", ".join(f"{rule}={'affine' if ok else 'non-affine'}" for rule, ok in affinity.items())
        label = integrand_label(gfunc=gfunc, expr=expr)
        raise SystemExit(
            "[ABORT] The requested campaign was not launched because the integrand is not "
            f"affine-friendly for all requested rules. integrand={label!r}, y={y}. "
            f"Failing rules: {details}. Full check: {all_details}. "
            "Under the current Triangulum implementation, the three-rule campaign should only be run "
            "when all requested rules are affine-friendly."
        )


def run_single_rule(args: argparse.Namespace, rule: str) -> Path:
    raw_outdir = Path(args.raw_outdir)
    ensure_dir(str(raw_outdir))

    slug = integrand_slug(gfunc=args.gfunc, expr=args.expr)
    ks_slug = "-".join(str(int(k.strip())) for k in args.ks.split(",") if k.strip())
    prefix = f"triangulum_{slug}_y{args.y:g}_{rule}_ks{ks_slug}_shots{args.shots}_"

    if args.reuse_existing:
        try:
            newest = find_newest_matching_json(raw_outdir, prefix)
            print(f"[REUSE] Using existing JSON for rule='{rule}': {newest}")
            return newest
        except FileNotFoundError:
            print(f"[REUSE] No existing JSON found for rule='{rule}'. Launching hardware run.")

    task_name = f"{args.task_prefix}_{slug}_{rule}"
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

    if args.gfunc is not None:
        cmd.extend(["--gfunc", args.gfunc])
    else:
        cmd.extend(["--expr", args.expr])

    print(f"[RUN] Launching rule='{rule}'")
    masked_cmd = ["***" if x == args.password else x for x in cmd]
    print("[CMD]", " ".join(masked_cmd))
    subprocess.run(cmd, check=True)

    newest = find_newest_matching_json(raw_outdir, prefix)
    print(f"[OK] Collected JSON for rule='{rule}': {newest}")
    return newest


def classify_function_for_current_hardware(hardware_friendly: bool | None) -> str:
    return "hardware-friendly" if hardware_friendly else "simulation-ready"


def summarize_campaign(
    json_paths: dict[str, Path],
    y: float,
    gfunc: str | None = None,
    expr: str | None = None,
) -> dict[str, Any]:
    records: dict[str, dict[str, Any]] = {}
    for rule, path in json_paths.items():
        records[rule] = load_json(path)

    per_rule = {}
    for rule, obj in records.items():
        per_rule[rule] = {
            "run_id": obj.get("run_id"),
            "I_hat": (obj.get("integral") or {}).get("I_hat"),
            "a_hat": (obj.get("mle") or {}).get("a_hat"),
            "exact_integral": obj.get("exact_integral"),
            "abs_error_global": obj.get("abs_error_global"),
            "hardware_friendly_affine": obj.get("hardware_friendly_affine"),
        }

    simpson_hat = None
    if all(r in per_rule for r in ("left", "midpoint", "right")):
        il = per_rule["left"]["I_hat"]
        im = per_rule["midpoint"]["I_hat"]
        ir = per_rule["right"]["I_hat"]
        if il is not None and im is not None and ir is not None:
            simpson_hat = (float(il) + 4.0 * float(im) + float(ir)) / 6.0

    exact_val = exact_integral(y, gfunc=gfunc, expr=expr)

    return {
        "integrand_label": integrand_label(gfunc=gfunc, expr=expr),
        "gfunc": gfunc,
        "expr": expr,
        "y": y,
        "rules": list(json_paths.keys()),
        "per_rule": per_rule,
        "simpson_style_combination": simpson_hat,
        "exact_integral": exact_val,
        "abs_error_simpson": (abs(simpson_hat - exact_val) if simpson_hat is not None and exact_val is not None else None),
        "all_rules_hardware_friendly": all(
            bool((obj.get("hardware_friendly_affine")))
            for obj in records.values()
        ),
    }


def main() -> None:
    args = parse_args()
    rules = tuple(r.strip() for r in args.rules.split(",") if r.strip())
    if not rules:
        raise SystemExit("No rules requested.")

    abort_if_not_affine_friendly(
        y=args.y,
        rules=rules,
        gfunc=args.gfunc,
        expr=args.expr,
    )

    raw_paths: dict[str, Path] = {}
    for idx, rule in enumerate(rules):
        raw_paths[rule] = run_single_rule(args, rule)
        if idx + 1 < len(rules) and args.pause_seconds > 0:
            time.sleep(args.pause_seconds)

    summary = summarize_campaign(
        json_paths=raw_paths,
        y=args.y,
        gfunc=args.gfunc,
        expr=args.expr,
    )

    ensure_dir(args.processed_outdir)
    stamp = current_utc_stamp()
    slug = integrand_slug(gfunc=args.gfunc, expr=args.expr)
    ks_slug = "-".join(str(int(k.strip())) for k in args.ks.split(",") if k.strip())
    base = f"triangulum_campaign_{slug}_y{args.y:g}_rules_{'-'.join(rules)}_ks{ks_slug}_shots{args.shots}_{stamp}"

    out_json = Path(args.processed_outdir) / f"{base}.json"
    out_csv = Path(args.processed_outdir) / f"{base}.csv"

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    rows: list[dict[str, Any]] = []
    for rule in rules:
        pr = summary["per_rule"][rule]
        rows.append(
            {
                "integrand_label": summary["integrand_label"],
                "gfunc": summary["gfunc"],
                "expr": summary["expr"],
                "y": summary["y"],
                "rule": rule,
                "run_id": pr["run_id"],
                "I_hat": pr["I_hat"],
                "a_hat": pr["a_hat"],
                "exact_integral": pr["exact_integral"],
                "abs_error_global": pr["abs_error_global"],
                "hardware_friendly_affine": pr["hardware_friendly_affine"],
                "simpson_style_combination": summary["simpson_style_combination"],
                "abs_error_simpson": summary["abs_error_simpson"],
                "timestamp_utc": stamp,
            }
        )

    write_csv(rows, out_csv)

    print("[OK] Campaign summary written:")
    print(f"  {out_json}")
    print(f"  {out_csv}")


if __name__ == "__main__":
    main()
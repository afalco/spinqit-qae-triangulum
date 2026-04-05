# scripts/04_export_qasm2.py
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

from src.qae.integrands import OFFICIAL_GFUNCS, integrand_label, integrand_slug
from src.qae.state_prep import (
    _extract_affine_angles_for_two_controls,
    _extract_quadratic_angles_for_two_controls,
    build_A_spec,
    is_affine_hardware_friendly,
)
from src.qasm2.emitter import export_qasm2_for_k

GFUNC_CHOICES = list(OFFICIAL_GFUNCS)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Export IBM Composer-compatible OpenQASM 2.0 circuits."
    )
    p.add_argument("--y", type=float, default=1.0, help="Upper limit y in [0,1].")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--gfunc", type=str, choices=GFUNC_CHOICES, help="Official g(x).")
    group.add_argument("--expr", type=str, help="Custom exploratory expression in x.")
    p.add_argument(
        "--rule",
        type=str,
        default="midpoint",
        choices=["left", "right", "midpoint"],
        help="Quadrature rule used to define the grid.",
    )
    p.add_argument(
        "--ks",
        type=str,
        default="0,1,2",
        help="Comma-separated amplification indices, e.g. 0,1,2",
    )
    p.add_argument(
        "--outdir",
        type=str,
        default="artifacts/qasm2",
        help="Output directory for .qasm and metadata.json",
    )
    return p.parse_args()


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def main() -> None:
    args = parse_args()
    ks = tuple(int(x.strip()) for x in args.ks.split(",") if x.strip())

    spec = build_A_spec(
        y=args.y,
        rule=args.rule,
        gfunc=args.gfunc,
        expr=args.expr,
        index_qubits=(0, 1),
        ancilla=2,
    )

    affine = _extract_affine_angles_for_two_controls(spec)
    quad = _extract_quadratic_angles_for_two_controls(spec)
    hardware_friendly = is_affine_hardware_friendly(spec)

    slug = integrand_slug(gfunc=args.gfunc, expr=args.expr)
    label = integrand_label(gfunc=args.gfunc, expr=args.expr)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"qasm2_ibmcomposer_{slug}_y{args.y:g}_{args.rule}_ks{'-'.join(map(str, ks))}_{stamp}"

    outdir = os.path.join(args.outdir, run_id)
    ensure_dir(outdir)

    written = []
    for k in ks:
        qasm = export_qasm2_for_k(spec, k)
        fname = f"{run_id}_k{k}.qasm"
        path = os.path.join(outdir, fname)
        with open(path, "w", encoding="utf-8") as f:
            f.write(qasm)
        written.append(path)

    metadata = {
        "run_id": run_id,
        "format": "OpenQASM 2.0",
        "target_environment": "IBM Quantum Composer",
        "integrand_label": label,
        "gfunc": args.gfunc,
        "expr": args.expr,
        "y": args.y,
        "rule": args.rule,
        "ks": list(ks),
        "index_qubits": list(spec.index_qubits),
        "ancilla": spec.ancilla,
        "patterns": [
            {"bits": list(bits), "theta": theta}
            for bits, theta in spec.patterns
        ],
        "hardware_friendly_affine": hardware_friendly,
        "affine_angles": (
            None if affine is None else {"c0": affine[0], "c1": affine[1], "c2": affine[2]}
        ),
        "quadratic_angles": (
            None
            if quad is None
            else {"c0": quad[0], "c1": quad[1], "c2": quad[2], "c12": quad[3]}
        ),
        "export_policy": {
            "custom_gates": False,
            "expanded_cry": True,
            "expanded_ccry": True,
            "allowed_ops": ["h", "x", "z", "ry", "cx", "ccx", "measure"],
        },
        "state_order": "q0q1q2",
        "measurement_map": {"q[0]": "c[0]", "q[1]": "c[1]", "q[2]": "c[2]"},
        "timestamp_utc": stamp,
        "files": [os.path.basename(p) for p in written],
    }

    meta_path = os.path.join(outdir, f"{run_id}_metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print("[OK] IBM Composer-compatible OpenQASM 2.0 export completed.")
    for p in written:
        print(" ", p)
    print(" ", meta_path)


if __name__ == "__main__":
    main()
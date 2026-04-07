#!/usr/bin/env python3
"""
08_run_ibm_g2_qiskit.py
=======================
Executes g2 = sin^2(pi*x) on IBM Kingston via Qiskit Runtime API.
Uses optimization_level=0 to prevent transpiler gate cancellation.

Key fix: CCRy(-pi) implemented as CCX (Toffoli), which is correct
up to a global phase that does not affect P(ancilla=1) measurements.

Usage (zsh, macOS):
    export IBM_QUANTUM_TOKEN="your_token_here"
    python3 08_run_ibm_g2_qiskit.py --dry-run
    python3 08_run_ibm_g2_qiskit.py --shots 2048 --ks 0 1 2
    python3 08_run_ibm_g2_qiskit.py --shots 2048 --ks 0 1 2 --wait

Requirements:
    pip install qiskit qiskit-ibm-runtime
    pip install qiskit-aer   # optional, for --dry-run validation
"""

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

import numpy as np

PI4 = np.pi / 4  # 0.7853981633974483


# ---------------------------------------------------------------------------
# Circuit building
# ---------------------------------------------------------------------------

def apply_A(qc):
    """
    State preparation for g2 = sin^2(pi*x), midpoint, n=2.

    Encodes theta(q0,q1) = c0 + c1*q0 + c2*q1 + c12*q0*q1
    with c0=pi/4, c1=pi/2, c2=pi/2, c12=-pi (quadratic, d=2).

    CCRy(c12=-pi) is replaced by CCX: both implement a conditional
    bit-flip on the ancilla (pi rotation), differing only by a global
    phase that cancels in P(ancilla=1) measurements.
    """
    qc.h(0); qc.h(1)
    qc.ry(PI4, 2)                                                  # ry(c0)
    qc.ry(PI4, 2); qc.cx(0, 2); qc.ry(-PI4, 2); qc.cx(0, 2)     # cry(c1, q0->q2)
    qc.ry(PI4, 2); qc.cx(1, 2); qc.ry(-PI4, 2); qc.cx(1, 2)     # cry(c2, q1->q2)
    qc.ccx(0, 1, 2)                                                # ccry(c12=-pi)


def apply_Adag(qc):
    """
    A^dagger: gate-by-gate reverse of apply_A.
    Verified: apply_A . apply_Adag = I  (P(|000>)=1.0 in statevector sim).
    """
    qc.ccx(0, 1, 2)
    qc.cx(1, 2); qc.ry(PI4, 2); qc.cx(1, 2); qc.ry(-PI4, 2)
    qc.cx(0, 2); qc.ry(PI4, 2); qc.cx(0, 2); qc.ry(-PI4, 2)
    qc.ry(-PI4, 2)
    qc.h(0); qc.h(1)


def apply_S0(qc):
    """Reflection about |000>."""
    qc.x(0); qc.x(1); qc.x(2)
    qc.h(2); qc.ccx(0, 1, 2); qc.h(2)
    qc.x(0); qc.x(1); qc.x(2)


def build_g2_circuit(k: int):
    """Build Q^k A|000> for g2 = sin^2(pi*x), midpoint."""
    from qiskit import QuantumCircuit
    qc = QuantumCircuit(3, 3, name=f"g2_midpoint_k{k}")
    apply_A(qc)
    for _ in range(k):
        qc.z(2)
        apply_Adag(qc)
        apply_S0(qc)
        apply_A(qc)
    qc.measure([0, 1, 2], [0, 1, 2])
    return qc


# ---------------------------------------------------------------------------
# Validation (Aer)
# ---------------------------------------------------------------------------

def validate_circuits(ks):
    try:
        from qiskit_aer import AerSimulator
    except ImportError:
        print("  qiskit-aer not installed -- skipping Aer validation.")
        print("  Install with: pip install qiskit-aer")
        return True

    sim = AerSimulator()
    xs = np.array([1/8, 3/8, 5/8, 7/8])
    g2 = np.sin(np.pi * xs) ** 2
    a_exact = g2.mean()  # 0.5

    def pk(a, k):
        a = np.clip(a, 1e-12, 1 - 1e-12)
        return np.sin((2*k+1) * np.arcsin(np.sqrt(a))) ** 2

    print("Aer simulation (65536 shots, no transpiler):")
    print(f"  k   p_hat     model     dev        status")
    all_ok = True
    for k in ks:
        qc = build_g2_circuit(k)
        counts = sim.run(qc, shots=65536).result().get_counts()
        m = sum(v for bs, v in counts.items() if bs[0] == '1')
        p = m / 65536
        model = pk(a_exact, k)
        ok = abs(p - model) < 0.008
        all_ok = all_ok and ok
        print(f"  k={k}  {p:.6f}  {model:.6f}  {p-model:+.6f}  "
              f"{'OK' if ok else 'FAIL'}")
    print()
    return all_ok


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="Submit g2=sin^2(pi*x) to IBM Kingston via Qiskit Runtime"
    )
    p.add_argument("--shots",   type=int, default=2048)
    p.add_argument("--ks",      type=int, nargs="+", default=[0, 1, 2])
    p.add_argument("--backend", default="ibm_kingston")
    p.add_argument("--out",     default="data/ibm_kingston/raw",
                   help="Directory for result JSON files")
    p.add_argument("--initial-layout", type=int, nargs=3, default=[0, 1, 2],
                   metavar=("Q0", "Q1", "Q2"),
                   help="Physical qubit mapping q[0] q[1] q[2] (default: 0 1 2)")
    p.add_argument("--dry-run", action="store_true",
                   help="Validate + transpile but do not submit")
    p.add_argument("--wait",    action="store_true",
                   help="Block until jobs complete and write result JSONs")
    p.add_argument("--skip-validation", action="store_true")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()

    print("=" * 60)
    print("g2 = sin^2(pi*x)  |  IBM Kingston  |  opt_level=0")
    print("=" * 60)
    print()

    # 1. Validate
    if not args.skip_validation:
        ok = validate_circuits(args.ks)
        if not ok:
            sys.exit("Aer validation failed -- aborting.")
    else:
        print("Validation skipped.\n")

    # 2. Gate counts
    from qiskit import QuantumCircuit
    circuits = {k: build_g2_circuit(k) for k in args.ks}
    print("Gate counts (logical):")
    for k, qc in circuits.items():
        ops = qc.count_ops()
        print(f"  k={k}: ry={ops.get('ry',0)}  cx={ops.get('cx',0)}  "
              f"ccx={ops.get('ccx',0)}  depth={qc.depth()}")
    print()

    # 3. Connect
    token = os.environ.get("IBM_QUANTUM_TOKEN")
    if not token:
        if args.dry_run:
            print("[dry-run] IBM_QUANTUM_TOKEN not set -- skipping transpile check.")
            return
        sys.exit("Error: export IBM_QUANTUM_TOKEN='your_token' first.")

    from qiskit import transpile
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler

    print("Connecting to IBM Quantum Platform ...")
    service = QiskitRuntimeService(channel="ibm_quantum_platform", token=token)
    backend = service.backend(args.backend)
    print(f"  Backend : {backend.name}")
    print(f"  Status  : {backend.status().status_msg}")
    print()

    # 4. Transpile
    print(f"Transpiling (optimization_level=0, "
          f"initial_layout={args.initial_layout}) ...")
    transpiled = {}
    for k, qc in circuits.items():
        t = transpile(
            qc,
            backend=backend,
            optimization_level=0,
            initial_layout=args.initial_layout,
        )
        transpiled[k] = t
        ops_t = t.count_ops()
        print(f"  k={k}: depth={t.depth()}  "
              f"cx={ops_t.get('cx', 0)}  ecr={ops_t.get('ecr', 0)}")
    print()

    if args.dry_run:
        print("[dry-run] Transpilation successful. Re-run without --dry-run to submit.")
        return

    # 5. Submit
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    sampler = Sampler(backend)
    submitted = {}

    for k, t in transpiled.items():
        print(f"Submitting k={k} ...", end=" ", flush=True)
        job = sampler.run([t], shots=args.shots)
        jid = job.job_id()
        submitted[k] = job
        print(f"job_id={jid}")
        meta = {
            "job_id":            jid,
            "k":                 k,
            "backend":           args.backend,
            "shots":             args.shots,
            "gfunc":             "sin2_pi_x",
            "rule":              "midpoint",
            "optimization_level": 0,
            "initial_layout":    args.initial_layout,
            "submitted_utc":     datetime.now(timezone.utc).isoformat(),
        }
        (out_dir / f"pending_g2_k{k}_{jid}.json").write_text(
            json.dumps(meta, indent=2))
    print()

    if not args.wait:
        print("Jobs submitted. Retrieve with 06_ibm_job_to_json.py when done.")
        print("Job IDs:")
        for k, job in submitted.items():
            print(f"  k={k}: {job.job_id()}")
        return

    # 6. Wait and save
    print("Waiting for results ...")
    xs = np.array([1/8, 3/8, 5/8, 7/8])
    a_exact = np.sin(np.pi * xs) ** 2
    a_exact = a_exact.mean()  # 0.5

    def pk(a, k):
        a = np.clip(a, 1e-12, 1 - 1e-12)
        return np.sin((2*k+1) * np.arcsin(np.sqrt(a))) ** 2

    ms = {}
    for k, job in submitted.items():
        print(f"  k={k} ...", end=" ", flush=True)
        result = job.result()
        counts = result[0].data.c.get_counts()
        N = args.shots
        m = sum(v for bs, v in counts.items() if bs[0] == '1')
        p = m / N
        ms[k] = m
        print(f"p_hat={p:.6f}  dev={p - pk(a_exact, k):+.6f}")
        out = {
            "job_id":            job.job_id(),
            "k":                 k,
            "backend":           args.backend,
            "shots":             N,
            "gfunc":             "sin2_pi_x",
            "rule":              "midpoint",
            "optimization_level": 0,
            "initial_layout":    args.initial_layout,
            "ancilla_qubit":     2,
            "ancilla_bit":       2,
            "bitstring_order":   "qiskit_c2c1c0",
            "m_ancilla":         m,
            "p_hat":             p,
            "counts":            dict(sorted(counts.items())),
            "completed_utc":     datetime.now(timezone.utc).isoformat(),
        }
        path = out_dir / f"ibm_kingston_g2_midpoint_k{k}_{job.job_id()}.json"
        path.write_text(json.dumps(out, indent=2))
        print(f"     Saved: {path.name}")

    # 7. Quick MLAE
    if 0 in ms and 1 in ms:
        from scipy.optimize import minimize_scalar
        N = args.shots

        def neg_ll(a):
            eps = 1e-15; ll = 0.0
            for k in [0, 1]:
                p = np.clip(pk(a, k), eps, 1 - eps)
                ll += ms[k]*np.log(p) + (N - ms[k])*np.log(1 - p)
            return -ll

        grid = np.linspace(1e-4, 1 - 1e-4, 100000)
        ab = grid[np.argmin([neg_ll(a) for a in grid])]
        res = minimize_scalar(neg_ll,
                              bounds=(max(0, ab - 0.01), min(1, ab + 0.01)),
                              method='bounded')
        a_hat = res.x
        print()
        print(f"MLAE K={{0,1}}: a_hat={a_hat:.8f}  "
              f"error={abs(a_hat - a_exact):.6f}  "
              f"(a_exact={a_exact:.6f})")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
08_run_ibm_g1_qiskit.py
=======================
Executes g1 = sin^2(pi*x/2) on IBM Kingston via Qiskit Runtime.

g1 in G_2^{(1)}: affine encoding with 3 controlled rotations.
Amplitude (midpoint rule): a = 1/2 exactly.

Mobius coefficients:
  c0 = pi/8,  c1 = pi/2 (ctrl q[0]),  c2 = pi/4 (ctrl q[1]),  c12 = 0

Key MLAE property at a=1/2 (uniform-measurement regime):
  p_k(1/2) = 1/2 for ALL k >= 0  (Remark 7.2 of the paper).
  => All circuits give equiprobable outcomes regardless of k.
  => Fisher information I_k(1/2) = 4(2k+1)^2 still grows with k,
     so adding k improves the Cramer-Rao bound despite uniform p_hat.

Circuit depths (logical / typical after transpilation):
  k=0:  depth 10 / ~37
  k=1:  depth 34 / ~120
  k=2:  depth 58 / ~210

Hardware results (IBM Kingston, N=2048 shots, opt_level=0):
  K={0,1}:   a_hat=0.4980,  error=2.0e-3  (0.56 sigma_CRB)
  K={0,1,2}: a_hat=0.4939,  error=6.1e-3  (3.29 sigma_CRB)

Usage (zsh, macOS):
    export IBM_QUANTUM_TOKEN="your_token_here"
    python3 08_run_ibm_g1_qiskit.py --dry-run
    python3 08_run_ibm_g1_qiskit.py --shots 2048 --ks 0 1 2
    python3 08_run_ibm_g1_qiskit.py --shots 2048 --ks 0 1 2 --wait

Requirements:
    pip install qiskit qiskit-ibm-runtime
    pip install qiskit-aer   # optional, for validation
"""

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

import numpy as np

PI8 = np.pi / 8   # c0, and half-angle of cry(c2)
PI4 = np.pi / 4   # half-angle of cry(c1)


# ---------------------------------------------------------------------------
# Circuit construction
# ---------------------------------------------------------------------------

def apply_A(qc):
    """
    State preparation A for g1 = sin^2(pi*x/2), midpoint rule, n=2.

    Encodes theta(q0,q1) = c0 + c1*q0 + c2*q1
    with c0=pi/8, c1=pi/2, c2=pi/4 (affine, d=1, c12=0).

    Qubit layout: q[0]=index MSB, q[1]=index LSB, q[2]=ancilla.
    """
    qc.h(0); qc.h(1)
    qc.ry(PI8, 2)                                              # c0 = pi/8
    qc.ry(PI4, 2); qc.cx(0, 2); qc.ry(-PI4, 2); qc.cx(0, 2)  # cry(c1, q0->q2)
    qc.ry(PI8, 2); qc.cx(1, 2); qc.ry(-PI8, 2); qc.cx(1, 2)  # cry(c2, q1->q2)


def apply_Adag(qc):
    """
    A^dagger: gate-by-gate reverse of apply_A.
    Verified: apply_A . apply_Adag = I  (P(|000>)=1.0 in statevector sim).
    """
    qc.cx(1, 2); qc.ry(PI8, 2); qc.cx(1, 2); qc.ry(-PI8, 2)
    qc.cx(0, 2); qc.ry(PI4, 2); qc.cx(0, 2); qc.ry(-PI4, 2)
    qc.ry(-PI8, 2)
    qc.h(0); qc.h(1)


def apply_S0(qc):
    """Reflection about |000>."""
    qc.x(0); qc.x(1); qc.x(2)
    qc.h(2); qc.ccx(0, 1, 2); qc.h(2)
    qc.x(0); qc.x(1); qc.x(2)


def build_g1_circuit(k: int):
    """Build Q^k A|000> for g1 = sin^2(pi*x/2), midpoint."""
    from qiskit import QuantumCircuit
    qc = QuantumCircuit(3, 3, name=f"g1_midpoint_k{k}")
    apply_A(qc)
    for _ in range(k):
        qc.z(2)
        apply_Adag(qc)
        apply_S0(qc)
        apply_A(qc)
    qc.measure([0, 1, 2], [0, 1, 2])
    return qc


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_circuits(ks):
    try:
        from qiskit_aer import AerSimulator
    except ImportError:
        print("  qiskit-aer not installed — skipping validation.")
        return True

    sim = AerSimulator()
    a_exact = 0.5

    def pk(a, k):
        a = np.clip(a, 1e-12, 1 - 1e-12)
        return np.sin((2*k+1) * np.arcsin(np.sqrt(a))) ** 2

    print("Aer simulation (32768 shots):")
    print(f"  k   p_hat     model     dev        status")
    all_ok = True
    for k in ks:
        qc = build_g1_circuit(k)
        counts = sim.run(qc, shots=32768).result().get_counts()
        m = sum(v for bs, v in counts.items() if bs[0] == '1')
        p = m / 32768
        model = pk(a_exact, k)
        ok = abs(p - model) < 0.008
        all_ok = all_ok and ok
        note = "  [uniform: p_k(1/2)=1/2 for all k]" if ok else ""
        print(f"  k={k}  {p:.6f}  {model:.6f}  {p-model:+.6f}  "
              f"{'OK' if ok else 'FAIL'}{note}")
    print()
    return all_ok


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="Submit g1=sin^2(pi*x/2) to IBM Kingston via Qiskit Runtime"
    )
    p.add_argument("--shots",   type=int, default=2048)
    p.add_argument("--ks",      type=int, nargs="+", default=[0, 1, 2])
    p.add_argument("--backend", default="ibm_kingston")
    p.add_argument("--out",     default="data/ibm_kingston/raw")
    p.add_argument("--initial-layout", type=int, nargs=3, default=[0, 1, 2],
                   metavar=("Q0", "Q1", "Q2"))
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--wait",    action="store_true")
    p.add_argument("--skip-validation", action="store_true")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()

    print("=" * 60)
    print("g1 = sin²(πx/2)  |  IBM Kingston  |  opt_level=0")
    print("=" * 60)
    print()

    if not args.skip_validation:
        ok = validate_circuits(args.ks)
        if not ok:
            sys.exit("Aer validation failed — aborting.")
    else:
        print("Validation skipped.\n")

    from qiskit import QuantumCircuit
    circuits = {k: build_g1_circuit(k) for k in args.ks}
    print("Gate counts (logical):")
    for k, qc in circuits.items():
        ops = qc.count_ops()
        print(f"  k={k}: ry={ops.get('ry',0)}  cx={ops.get('cx',0)}  "
              f"ccx={ops.get('ccx',0)}  depth={qc.depth()}")
    print()

    token = os.environ.get("IBM_QUANTUM_TOKEN")
    if not token:
        if args.dry_run:
            print("[dry-run] IBM_QUANTUM_TOKEN not set — skipping transpile.")
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

    print(f"Transpiling (optimization_level=0, "
          f"initial_layout={args.initial_layout}) ...")
    transpiled = {}
    for k, qc in circuits.items():
        t = transpile(qc, backend=backend, optimization_level=0,
                      initial_layout=args.initial_layout)
        transpiled[k] = t
        ops_t = t.count_ops()
        print(f"  k={k}: depth={t.depth()}  "
              f"cx={ops_t.get('cx',0)}  ecr={ops_t.get('ecr',0)}")
    print()

    if args.dry_run:
        print("[dry-run] Done. Re-run without --dry-run to submit.")
        return

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
            "gfunc":             "sin2_pi_x_over_2",
            "rule":              "midpoint",
            "a_exact":           0.5,
            "optimization_level": 0,
            "initial_layout":    args.initial_layout,
            "submitted_utc":     datetime.now(timezone.utc).isoformat(),
        }
        (out_dir / f"pending_g1_k{k}_{jid}.json").write_text(
            json.dumps(meta, indent=2))
    print()

    if not args.wait:
        print("Jobs submitted. Job IDs:")
        for k, job in submitted.items():
            print(f"  k={k}: {job.job_id()}")
        return

    print("Waiting for results ...")
    a_exact = 0.5

    def pk(a, k):
        a = np.clip(a, 1e-12, 1 - 1e-12)
        return np.sin((2*k+1) * np.arcsin(np.sqrt(a))) ** 2

    def fisher(a, k):
        eps = 1e-10; a = np.clip(a, eps, 1-eps)
        th = np.arcsin(np.sqrt(a))
        p = np.clip(np.sin((2*k+1)*th)**2, eps, 1-eps)
        dp = ((2*k+1)*np.sin((2*k+1)*th)*np.cos((2*k+1)*th))/np.sqrt(a*(1-a))
        return args.shots * dp**2 / (p*(1-p))

    ms = {}
    for k, job in submitted.items():
        print(f"  k={k} ...", end=" ", flush=True)
        result = job.result()
        try:
            counts = result[0].data.c.get_counts()
            N = args.shots
            m = sum(v for bs, v in counts.items() if bs[0] == '1')
        except AttributeError:
            arr = result[0].data.c.array
            m = int(arr[:, 2].sum())
            N = len(arr)
        p = m / N
        ms[k] = m
        print(f"p_hat={p:.6f}  dev={p - pk(a_exact, k):+.6f}")

        out = {
            "job_id":            job.job_id(),
            "k":                 k,
            "backend":           args.backend,
            "shots":             N,
            "gfunc":             "sin2_pi_x_over_2",
            "rule":              "midpoint",
            "a_exact":           0.5,
            "optimization_level": 0,
            "initial_layout":    args.initial_layout,
            "ancilla_qubit":     2,
            "ancilla_bit":       2,
            "m_ancilla":         m,
            "p_hat":             p,
            "completed_utc":     datetime.now(timezone.utc).isoformat(),
        }
        path = out_dir / f"ibm_kingston_g1_midpoint_k{k}_{job.job_id()}.json"
        path.write_text(json.dumps(out, indent=2))
        print(f"     Saved: {path.name}")

    # MLAE
    if 0 in ms and 1 in ms:
        from scipy.optimize import minimize_scalar
        N = args.shots

        print()
        print("MLAE results:")
        for label, K in [("K={0,1}", [0, 1]), ("K={0,1,2}", [0, 1, 2])]:
            if not all(k in ms for k in K):
                continue

            def neg_ll(a, _K=K):
                eps = 1e-15
                return -sum(ms[k]*np.log(max(pk(a,k),eps)) +
                            (N-ms[k])*np.log(max(1-pk(a,k),eps))
                            for k in _K)

            grid = np.linspace(1e-4, 1-1e-4, 100000)
            ab = grid[np.argmin([neg_ll(a) for a in grid])]
            res = minimize_scalar(neg_ll,
                                  bounds=(max(0, ab-0.01), min(1, ab+0.01)),
                                  method='bounded')
            a_hat = res.x
            sigma = 1 / np.sqrt(sum(fisher(a_exact, k) for k in K))
            err = abs(a_hat - a_exact)
            print(f"  {label}: a_hat={a_hat:.8f}  error={err:.6f}  "
                  f"({err/sigma:.2f} sigma_CRB)")


if __name__ == "__main__":
    main()

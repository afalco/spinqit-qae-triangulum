#!/usr/bin/env python3
"""
08_run_ibm_g0_qiskit.py
=======================
Executes g0 = 1/4 (constant function) on IBM Kingston via Qiskit Runtime.

g0 in G_2^{(0)}: encoded by a single unconditional RY(pi/3) on the ancilla.
Amplitude: a = sin^2(pi/3 / 2) = sin^2(pi/6) = 1/4 exactly.

Key MLAE property at a=1/4:
  p_1(1/4) = sin^2(3*arcsin(1/2)) = sin^2(pi/2) = 1
  => I_1(1/4) = 0: the k=1 circuit is saturated, Fisher info vanishes.
  => K={0,1} likelihood is bimodal under noise (diagnosed on Triangulum).
  => K={0,1,2} resolves the degeneracy (p_2(1/4) = 1/4 ≠ 1).

Circuit depths (logical / typical after transpilation):
  k=0:  depth  2 / ~10
  k=1:  depth 10 / ~40
  k=2:  depth 18 / ~70

Usage (zsh, macOS):
    export IBM_QUANTUM_TOKEN="your_token_here"
    python3 08_run_ibm_g0_qiskit.py --dry-run
    python3 08_run_ibm_g0_qiskit.py --shots 2048 --ks 0 1 2
    python3 08_run_ibm_g0_qiskit.py --shots 2048 --ks 0 1 2 --wait

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

THETA0 = np.pi / 3   # = 2*arcsin(sqrt(1/4)) = 2*arcsin(1/2)


# ---------------------------------------------------------------------------
# Circuit construction
# ---------------------------------------------------------------------------

def apply_A(qc):
    """
    State preparation A for g0 = 1/4 (constant, d=0).

    Encodes theta = pi/3 unconditionally on the ancilla.
    Index qubits q[0], q[1] are placed in uniform superposition
    to ensure the Grover iterate S0 = 2|000><000| - I acts correctly.

    P(ancilla=1 | any node) = sin^2(pi/6) = 1/4 exactly.
    """
    qc.h(0); qc.h(1)
    qc.ry(THETA0, 2)


def apply_Adag(qc):
    """A^dagger: exact reverse of apply_A. Verified: A.A† = I."""
    qc.ry(-THETA0, 2)
    qc.h(0); qc.h(1)


def apply_S0(qc):
    """Reflection about |000>."""
    qc.x(0); qc.x(1); qc.x(2)
    qc.h(2); qc.ccx(0, 1, 2); qc.h(2)
    qc.x(0); qc.x(1); qc.x(2)


def build_g0_circuit(k: int):
    """
    Build Q^k A |000> for g0 = 1/4.

    Note: at k=1, p_1(1/4) = 1 exactly (Fisher info = 0).
    The k=1 circuit acts as a perfect amplifier at the true amplitude,
    saturating the ancilla. This is the MLAE degeneracy regime
    described in Remark 7.2 of the paper.
    """
    from qiskit import QuantumCircuit
    qc = QuantumCircuit(3, 3, name=f"g0_k{k}")
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
    a_exact = 0.25

    def pk(a, k):
        a = np.clip(a, 1e-12, 1 - 1e-12)
        return np.sin((2*k+1) * np.arcsin(np.sqrt(a))) ** 2

    print("Aer simulation (32768 shots):")
    print(f"  k   p_hat     model     dev        status")
    all_ok = True
    for k in ks:
        qc = build_g0_circuit(k)
        counts = sim.run(qc, shots=32768).result().get_counts()
        m = sum(v for bs, v in counts.items() if bs[0] == '1')
        p = m / 32768
        model = pk(a_exact, k)
        ok = abs(p - model) < 0.01
        all_ok = all_ok and ok
        note = "  [k=1: p=1 is correct — MLAE degeneracy]" if k == 1 else ""
        print(f"  k={k}  {p:.6f}  {model:.6f}  {p-model:+.6f}  "
              f"{'OK' if ok else 'FAIL'}{note}")
    print()
    return all_ok


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="Submit g0=1/4 to IBM Kingston via Qiskit Runtime"
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
    print("g0 = 1/4  |  IBM Kingston  |  opt_level=0")
    print("=" * 60)
    print()

    if not args.skip_validation:
        ok = validate_circuits(args.ks)
        if not ok:
            sys.exit("Aer validation failed — aborting.")
    else:
        print("Validation skipped.\n")

    from qiskit import QuantumCircuit
    circuits = {k: build_g0_circuit(k) for k in args.ks}
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
            "gfunc":             "g0_constant_quarter",
            "rule":              "midpoint",
            "a_exact":           0.25,
            "optimization_level": 0,
            "initial_layout":    args.initial_layout,
            "submitted_utc":     datetime.now(timezone.utc).isoformat(),
        }
        (out_dir / f"pending_g0_k{k}_{jid}.json").write_text(
            json.dumps(meta, indent=2))
    print()

    if not args.wait:
        print("Jobs submitted. Job IDs:")
        for k, job in submitted.items():
            print(f"  k={k}: {job.job_id()}")
        return

    print("Waiting for results ...")
    a_exact = 0.25

    def pk(a, k):
        a = np.clip(a, 1e-12, 1 - 1e-12)
        return np.sin((2*k+1) * np.arcsin(np.sqrt(a))) ** 2

    import zlib, io
    ms = {}
    for k, job in submitted.items():
        print(f"  k={k} ...", end=" ", flush=True)
        result = job.result()

        # SamplerV2 result: BitArray compressed with zlib+numpy
        import base64
        ba = result[0].data.c
        try:
            # New SamplerV2 format: BitArray has get_counts()
            counts = ba.get_counts()
            N = args.shots
            m = sum(v for bs, v in counts.items() if bs[0] == '1')
        except AttributeError:
            # Fallback: raw bit matrix
            arr = ba.array
            m = int(arr[:, 2].sum())
            N = len(arr)

        p = m / N
        ms[k] = m
        note = " [degeneracy: expected p~1]" if k == 1 else ""
        print(f"p_hat={p:.6f}  dev={p - pk(a_exact, k):+.6f}{note}")

        out = {
            "job_id":            job.job_id(),
            "k":                 k,
            "backend":           args.backend,
            "shots":             N,
            "gfunc":             "g0_constant_quarter",
            "rule":              "midpoint",
            "a_exact":           0.25,
            "optimization_level": 0,
            "initial_layout":    args.initial_layout,
            "ancilla_qubit":     2,
            "ancilla_bit":       2,
            "m_ancilla":         m,
            "p_hat":             p,
            "completed_utc":     datetime.now(timezone.utc).isoformat(),
        }
        path = out_dir / f"ibm_kingston_g0_midpoint_k{k}_{job.job_id()}.json"
        path.write_text(json.dumps(out, indent=2))
        print(f"     Saved: {path.name}")

    # Quick MLAE for K={0,2} (skip k=1 — Fisher info = 0 at a=1/4)
    if 0 in ms and 2 in ms:
        from scipy.optimize import minimize_scalar
        N = args.shots

        def neg_ll(a):
            eps = 1e-15
            ll = sum(ms[k] * np.log(max(pk(a,k), eps)) +
                     (N - ms[k]) * np.log(max(1 - pk(a,k), eps))
                     for k in [0, 2])
            return -ll

        grid = np.linspace(1e-4, 1 - 1e-4, 100000)
        ab = grid[np.argmin([neg_ll(a) for a in grid])]
        res = minimize_scalar(neg_ll,
                              bounds=(max(0, ab - 0.02), min(1, ab + 0.02)),
                              method='bounded')
        a_hat = res.x
        print()
        print(f"MLAE K={{0,2}}: a_hat={a_hat:.8f}  "
              f"error={abs(a_hat - a_exact):.6f}  "
              f"(a_exact={a_exact:.6f})")
        print("  (K={0,1} unreliable: I_1(1/4)=0, Fisher info vanishes at k=1)")


if __name__ == "__main__":
    main()

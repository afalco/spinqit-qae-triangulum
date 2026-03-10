#calibrate_bit_order.py
from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter
from datetime import datetime, timezone
from typing import Any


TEST_CASES = [
    {"name": "none", "flips": []},
    {"name": "x_q0", "flips": [0]},
    {"name": "x_q1", "flips": [1]},
    {"name": "x_q2", "flips": [2]},
    {"name": "x_q0_q1", "flips": [0, 1]},
    {"name": "x_q0_q2", "flips": [0, 2]},
    {"name": "x_q1_q2", "flips": [1, 2]},
    {"name": "x_q0_q1_q2", "flips": [0, 1, 2]},
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Standalone 3-qubit bit-order calibration for SpinQit simulator or Triangulum."
    )
    p.add_argument(
        "--backend",
        type=str,
        choices=["sim", "triangulum"],
        required=True,
        help="Backend to use: sim or triangulum.",
    )
    p.add_argument("--shots", type=int, default=256, help="Shots per test circuit.")
    p.add_argument("--outdir", type=str, default="bit_order_calibration", help="Output directory.")

    # Triangulum-only params
    p.add_argument("--ip", type=str, default=None, help="Triangulum IP.")
    p.add_argument("--port", type=int, default=55444, help="Triangulum port.")
    p.add_argument("--account", type=str, default=None, help="Triangulum account.")
    p.add_argument("--password", type=str, default=None, help="Triangulum password.")
    p.add_argument("--task-prefix", type=str, default="bit_order_calib", help="Triangulum task prefix.")
    return p.parse_args()


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def normalize_counts(result: Any) -> dict[str, int]:
    if isinstance(result, dict):
        return {str(k): int(v) for k, v in result.items()}
    if hasattr(result, "counts"):
        return {str(k): int(v) for k, v in result.counts.items()}
    if hasattr(result, "get_counts"):
        c = result.get_counts()
        return {str(k): int(v) for k, v in c.items()}
    raise RuntimeError("Unsupported backend result type for counts extraction.")


def clean_bitstring(s: str) -> str:
    return s.replace("0b", "").strip()


def dominant_bitstring(counts: dict[str, int]) -> str:
    if not counts:
        return ""
    return max(counts.items(), key=lambda kv: kv[1])[0]


def expected_bitstring_q0q1q2(flips: list[int]) -> str:
    bits = ["0", "0", "0"]
    for q in flips:
        bits[q] = "1"
    return "".join(bits)


def expected_bitstring_q2q1q0(flips: list[int]) -> str:
    q0q1q2 = expected_bitstring_q0q1q2(flips)
    return q0q1q2[::-1]


def build_circuit(flips: list[int]):
    from spinqit import Circuit, X  # type: ignore

    circ = Circuit()
    try:
        circ.allocateQubits(3)
    except Exception:
        pass

    for q in flips:
        circ << (X, q)

    try:
        circ.measure_all()
    except Exception:
        try:
            circ.measure(range(3))
        except Exception:
            pass

    return circ


def make_backend(args: argparse.Namespace):
    if args.backend == "sim":
        from spinqit import get_basic_simulator  # type: ignore
        return get_basic_simulator(), None

    from spinqit import get_nmr, NMRConfig  # type: ignore

    if not args.ip or not args.account or not args.password:
        raise SystemExit("For --backend triangulum you must provide --ip, --account, and --password.")

    engine = get_nmr()
    conf = NMRConfig()
    conf.configure_ip(args.ip)
    conf.configure_port(int(args.port))
    conf.configure_account(args.account, args.password)
    conf.configure_task(args.task_prefix, "3-qubit bit-order calibration")
    return engine, conf


def run_circuit(engine, conf, circ, shots: int):
    if conf is None:
        # simulator

        # 1) direct execute(circ, shots=...)
        try:
            return engine.execute(circ, shots=shots)
        except Exception:
            pass

        # 2) direct execute(circ) without shots
        try:
            return engine.execute(circ)
        except Exception:
            pass

        # 3) compile + execute(compiled, config/shots) depending on local SpinQit API
        try:
            from spinqit import get_compiler  # type: ignore

            compiler = get_compiler()
            compiled = compiler.compile(circ, 0)

            # common patterns seen across versions
            try:
                return engine.execute(compiled, shots)
            except Exception:
                pass

            try:
                return engine.execute(compiled, shots=shots)
            except Exception:
                pass

            try:
                return engine.execute(compiled)
            except Exception:
                pass

        except Exception:
            pass

        raise RuntimeError(
            "Could not execute circuit on simulator backend. "
            "Your local SpinQit version likely requires a different simulator invocation."
        )

    else:
        # Triangulum
        try:
            return engine.execute(circ, conf, shots=shots)
        except Exception:
            try:
                return engine.run(circ, conf, shots=shots)
            except Exception as e:
                raise RuntimeError("Could not execute circuit on Triangulum backend.") from e

def infer_order(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Use single-flip tests to infer whether the backend reports q0q1q2 or q2q1q0.
    """
    by_name = {r["test_name"]: r for r in rows}

    needed = ["x_q0", "x_q1", "x_q2"]
    if not all(name in by_name for name in needed):
        return {
            "reported_order": "undetermined",
            "reason": "Missing single-flip tests.",
        }

    dom_q0 = clean_bitstring(by_name["x_q0"]["dominant_bitstring"]).zfill(3)
    dom_q1 = clean_bitstring(by_name["x_q1"]["dominant_bitstring"]).zfill(3)
    dom_q2 = clean_bitstring(by_name["x_q2"]["dominant_bitstring"]).zfill(3)

    if dom_q0 == "100" and dom_q1 == "010" and dom_q2 == "001":
        return {
            "reported_order": "q0q1q2",
            "reason": "Single-flip tests match q0q1q2 ordering.",
        }

    if dom_q0 == "001" and dom_q1 == "010" and dom_q2 == "100":
        return {
            "reported_order": "q2q1q0",
            "reason": "Single-flip tests match q2q1q0 ordering.",
        }

    return {
        "reported_order": "undetermined",
        "reason": (
            f"Observed single-flip dominant strings: "
            f"x_q0={dom_q0}, x_q1={dom_q1}, x_q2={dom_q2}. "
            "This does not match a pure q0q1q2 or q2q1q0 convention."
        ),
    }


def write_csv(path: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        with open(path, "w", encoding="utf-8", newline="") as f:
            pass
        return
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    ensure_dir(args.outdir)

    engine, conf = make_backend(args)

    rows: list[dict[str, Any]] = []
    full_payload: dict[str, Any] = {
        "backend": args.backend,
        "shots": args.shots,
        "timestamp_utc": utc_stamp(),
        "tests": [],
    }

    for case in TEST_CASES:
        circ = build_circuit(case["flips"])
        result = run_circuit(engine, conf, circ, shots=args.shots)
        counts = normalize_counts(result)
        dom = dominant_bitstring(counts)

        expected_a = expected_bitstring_q0q1q2(case["flips"])
        expected_b = expected_bitstring_q2q1q0(case["flips"])

        row = {
            "test_name": case["name"],
            "flips": ",".join(str(q) for q in case["flips"]),
            "expected_if_q0q1q2": expected_a,
            "expected_if_q2q1q0": expected_b,
            "dominant_bitstring": clean_bitstring(dom),
            "shots": args.shots,
            "match_q0q1q2": clean_bitstring(dom).zfill(3) == expected_a,
            "match_q2q1q0": clean_bitstring(dom).zfill(3) == expected_b,
        }
        rows.append(row)

        full_payload["tests"].append(
            {
                "test_name": case["name"],
                "flips": case["flips"],
                "expected_if_q0q1q2": expected_a,
                "expected_if_q2q1q0": expected_b,
                "dominant_bitstring": clean_bitstring(dom),
                "counts": counts,
            }
        )

    inference = infer_order(rows)
    full_payload["inference"] = inference

    stamp = utc_stamp()
    base = f"bit_order_{args.backend}_{stamp}"
    out_json = os.path.join(args.outdir, f"{base}.json")
    out_csv = os.path.join(args.outdir, f"{base}.csv")

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(full_payload, f, indent=2)

    write_csv(out_csv, rows)

    print("[OK] Wrote:")
    print(f"  {out_json}")
    print(f"  {out_csv}")
    print(f"[INFERENCE] reported_order={inference['reported_order']}")
    print(f"[DETAIL] {inference['reason']}")


if __name__ == "__main__":
    main()
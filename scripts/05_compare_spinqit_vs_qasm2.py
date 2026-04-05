from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src.qae.state_prep import (
    ASpec,
    _extract_affine_angles_for_two_controls,
    _extract_quadratic_angles_for_two_controls,
    build_A_spec,
)
from src.qae.integrands import OFFICIAL_GFUNCS


GFUNC_CHOICES = list(OFFICIAL_GFUNCS)


@dataclass(frozen=True)
class Op:
    name: str
    qubits: tuple[int, ...]
    angle: float | None = None
    block: str | None = None

    def pretty(self) -> str:
        q = ",".join(f"q[{i}]" for i in self.qubits)
        if self.angle is None:
            return f"{self.name} {q}" + (f"  [{self.block}]" if self.block else "")
        return (
            f"{self.name}({self.angle:.16f}) {q}"
            + (f"  [{self.block}]" if self.block else "")
        )


def ry_op(theta: float, q: int, block: str) -> list[Op]:
    if abs(theta) < 1e-12:
        return []
    return [Op("ry", (q,), theta, block)]


def cx_op(c: int, t: int, block: str) -> list[Op]:
    return [Op("cx", (c, t), None, block)]


def h_op(q: int, block: str) -> list[Op]:
    return [Op("h", (q,), None, block)]


def x_op(q: int, block: str) -> list[Op]:
    return [Op("x", (q,), None, block)]


def z_op(q: int, block: str) -> list[Op]:
    return [Op("z", (q,), None, block)]


def ccx_op(c0: int, c1: int, t: int, block: str) -> list[Op]:
    return [Op("ccx", (c0, c1, t), None, block)]


def measure_op(q: int, c: int, block: str) -> list[Op]:
    return [Op("measure", (q, c), None, block)]


def emit_cry_expanded(theta: float, c: int, t: int, block: str) -> list[Op]:
    if abs(theta) < 1e-12:
        return []
    ops: list[Op] = []
    ops += ry_op(theta / 2.0, t, block)
    ops += cx_op(c, t, block)
    ops += ry_op(-theta / 2.0, t, block)
    ops += cx_op(c, t, block)
    return ops


def emit_ccry_expanded(theta: float, c0: int, c1: int, t: int, block: str) -> list[Op]:
    if abs(theta) < 1e-12:
        return []
    ops: list[Op] = []
    ops += emit_cry_expanded(theta / 2.0, c1, t, block)
    ops += cx_op(c0, c1, block)
    ops += emit_cry_expanded(-theta / 2.0, c1, t, block)
    ops += cx_op(c0, c1, block)
    return ops


def expected_A_ops(spec: ASpec, block: str = "A") -> list[Op]:
    q0, q1 = spec.index_qubits
    a = spec.ancilla
    ops: list[Op] = []
    ops += h_op(q0, block)
    ops += h_op(q1, block)

    affine = _extract_affine_angles_for_two_controls(spec)
    if affine is not None:
        c0, c1, c2 = affine
        ops += ry_op(c0, a, block)
        ops += emit_cry_expanded(c1, q0, a, block)
        ops += emit_cry_expanded(c2, q1, a, block)
        return ops

    quad = _extract_quadratic_angles_for_two_controls(spec)
    if quad is not None:
        c0, c1, c2, c12 = quad
        ops += ry_op(c0, a, block)
        ops += emit_cry_expanded(c1, q0, a, block)
        ops += emit_cry_expanded(c2, q1, a, block)
        ops += emit_ccry_expanded(c12, q0, q1, a, block)
        return ops

    raise NotImplementedError(
        "Comparator currently supports the 2-index-qubit affine/quadratic paths only."
    )


def expected_Adag_ops(spec: ASpec, block: str = "A^dagger") -> list[Op]:
    q0, q1 = spec.index_qubits
    a = spec.ancilla
    ops: list[Op] = []

    affine = _extract_affine_angles_for_two_controls(spec)
    if affine is not None:
        c0, c1, c2 = affine
        ops += emit_cry_expanded(-c2, q1, a, block)
        ops += emit_cry_expanded(-c1, q0, a, block)
        ops += ry_op(-c0, a, block)
        ops += h_op(q0, block)
        ops += h_op(q1, block)
        return ops

    quad = _extract_quadratic_angles_for_two_controls(spec)
    if quad is not None:
        c0, c1, c2, c12 = quad
        ops += emit_ccry_expanded(-c12, q0, q1, a, block)
        ops += emit_cry_expanded(-c2, q1, a, block)
        ops += emit_cry_expanded(-c1, q0, a, block)
        ops += ry_op(-c0, a, block)
        ops += h_op(q0, block)
        ops += h_op(q1, block)
        return ops

    raise NotImplementedError(
        "Comparator currently supports the 2-index-qubit affine/quadratic paths only."
    )


def expected_Spsi0_ops(spec: ASpec, block: str = "S_psi0") -> list[Op]:
    return z_op(spec.ancilla, block)


def expected_S0_ops(spec: ASpec, block: str = "S0") -> list[Op]:
    q0, q1 = spec.index_qubits
    q2 = spec.ancilla
    ops: list[Op] = []
    ops += x_op(q0, block)
    ops += x_op(q1, block)
    ops += x_op(q2, block)
    ops += h_op(q2, block)
    ops += ccx_op(q0, q1, q2, block)
    ops += h_op(q2, block)
    ops += x_op(q0, block)
    ops += x_op(q1, block)
    ops += x_op(q2, block)
    return ops


def expected_Q_ops(spec: ASpec, q_index: int) -> list[Op]:
    ops: list[Op] = []
    ops += expected_Spsi0_ops(spec, block=f"Q{q_index}:S_psi0")
    ops += expected_Adag_ops(spec, block=f"Q{q_index}:A^dagger")
    ops += expected_S0_ops(spec, block=f"Q{q_index}:S0")
    ops += expected_A_ops(spec, block=f"Q{q_index}:A")
    return ops


def expected_full_ops(spec: ASpec, k: int, add_measurements: bool = True) -> list[Op]:
    ops: list[Op] = []
    ops += expected_A_ops(spec, block="A_init")
    for i in range(k):
        ops += expected_Q_ops(spec, q_index=i + 1)
    if add_measurements:
        for q in range(3):
            ops += measure_op(q, q, "measure")
    return ops


RY_RE = re.compile(r"^ry\(([-+0-9.eE]+)\)\s+q\[(\d+)\];$")
CX_RE = re.compile(r"^cx\s+q\[(\d+)\],q\[(\d+)\];$")
CCX_RE = re.compile(r"^ccx\s+q\[(\d+)\],q\[(\d+)\],q\[(\d+)\];$")
H_RE = re.compile(r"^h\s+q\[(\d+)\];$")
X_RE = re.compile(r"^x\s+q\[(\d+)\];$")
Z_RE = re.compile(r"^z\s+q\[(\d+)\];$")
MEASURE_RE = re.compile(r"^measure\s+q\[(\d+)\]\s*->\s*c\[(\d+)\];$")


def parse_qasm_ops(qasm_text: str) -> list[Op]:
    ops: list[Op] = []
    for raw in qasm_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("//"):
            continue
        if line.startswith("OPENQASM"):
            continue
        if line.startswith("include "):
            continue
        if line.startswith("qreg "):
            continue
        if line.startswith("creg "):
            continue

        m = RY_RE.match(line)
        if m:
            ops.append(Op("ry", (int(m.group(2)),), float(m.group(1)), "parsed"))
            continue
        m = CX_RE.match(line)
        if m:
            ops.append(Op("cx", (int(m.group(1)), int(m.group(2))), None, "parsed"))
            continue
        m = CCX_RE.match(line)
        if m:
            ops.append(
                Op("ccx", (int(m.group(1)), int(m.group(2)), int(m.group(3))), None, "parsed")
            )
            continue
        m = H_RE.match(line)
        if m:
            ops.append(Op("h", (int(m.group(1)),), None, "parsed"))
            continue
        m = X_RE.match(line)
        if m:
            ops.append(Op("x", (int(m.group(1)),), None, "parsed"))
            continue
        m = Z_RE.match(line)
        if m:
            ops.append(Op("z", (int(m.group(1)),), None, "parsed"))
            continue
        m = MEASURE_RE.match(line)
        if m:
            ops.append(Op("measure", (int(m.group(1)), int(m.group(2))), None, "parsed"))
            continue

        raise ValueError(f"Unsupported or unparsed QASM line: {line}")

    return ops


def infer_k_from_filename(path: Path) -> int | None:
    m = re.search(r"_k(\d+)\.qasm$", path.name)
    if m:
        return int(m.group(1))
    return None


def compare_ops(expected: list[Op], parsed: list[Op], angle_tol: float = 1e-9) -> tuple[bool, str]:
    if len(expected) != len(parsed):
        return (
            False,
            f"Operation-count mismatch: expected {len(expected)} ops, parsed {len(parsed)} ops."
        )

    for i, (e, p) in enumerate(zip(expected, parsed)):
        if e.name != p.name:
            return False, (
                f"Mismatch at op {i}: expected gate {e.name!r}, parsed {p.name!r}\n"
                f"  expected: {e.pretty()}\n"
                f"  parsed  : {p.pretty()}"
            )
        if e.qubits != p.qubits:
            return False, (
                f"Mismatch at op {i}: qubits differ\n"
                f"  expected: {e.pretty()}\n"
                f"  parsed  : {p.pretty()}"
            )
        if e.angle is None and p.angle is None:
            continue
        if (e.angle is None) != (p.angle is None):
            return False, (
                f"Mismatch at op {i}: one op has angle and the other does not\n"
                f"  expected: {e.pretty()}\n"
                f"  parsed  : {p.pretty()}"
            )
        assert e.angle is not None and p.angle is not None
        if abs(e.angle - p.angle) > angle_tol:
            return False, (
                f"Mismatch at op {i}: angle differs by {abs(e.angle - p.angle):.3e}\n"
                f"  expected: {e.pretty()}\n"
                f"  parsed  : {p.pretty()}"
            )

    return True, "Exact logical-structure match."


def summarize_ops(ops: list[Op]) -> dict[str, int]:
    out: dict[str, int] = {}
    for op in ops:
        out[op.name] = out.get(op.name, 0) + 1
    return out


def default_report_path(qasm: str | None, qasm_dir: str | None) -> Path:
    if qasm_dir is not None:
        return Path(qasm_dir) / "comparison_report.json"
    assert qasm is not None
    qasm_path = Path(qasm)
    return qasm_path.parent / f"{qasm_path.stem}_comparison_report.json"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Compare IBM Composer QASM2 export against the logical SpinQit structure from the repo."
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--qasm", type=str, help="Path to one exported .qasm file.")
    src.add_argument("--qasm-dir", type=str, help="Directory containing exported .qasm files.")
    p.add_argument("--k", type=int, default=None, help="Amplification index k. If omitted, try to infer from filename.")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--gfunc", type=str, choices=GFUNC_CHOICES, help="Official g(x).")
    g.add_argument("--expr", type=str, help="Custom exploratory expression in x.")
    p.add_argument("--y", type=float, default=1.0, help="Upper limit y in [0,1].")
    p.add_argument(
        "--rule",
        type=str,
        default="midpoint",
        choices=["left", "right", "midpoint"],
        help="Quadrature rule used to define the grid.",
    )
    p.add_argument(
        "--angle-tol",
        type=float,
        default=1e-9,
        help="Absolute tolerance for angle comparisons.",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON summary to stdout.",
    )
    p.add_argument(
        "--write-report",
        action="store_true",
        help="Write comparison_report.json automatically.",
    )
    p.add_argument(
        "--report-out",
        type=str,
        default=None,
        help="Explicit output path for the JSON report.",
    )
    return p.parse_args()


def compare_one_file(
    qasm_path: Path,
    *,
    y: float,
    rule: str,
    gfunc: str | None,
    expr: str | None,
    k: int | None,
    angle_tol: float,
) -> dict:
    actual_k = k if k is not None else infer_k_from_filename(qasm_path)
    if actual_k is None:
        raise ValueError(f"Could not infer k from filename and --k was not provided: {qasm_path}")

    spec = build_A_spec(
        y=y,
        n_index_qubits=2,
        rule=rule,
        gfunc=gfunc,
        expr=expr,
        index_qubits=(0, 1),
        ancilla=2,
    )

    expected = expected_full_ops(spec, actual_k, add_measurements=True)
    parsed = parse_qasm_ops(qasm_path.read_text(encoding="utf-8"))
    ok, message = compare_ops(expected, parsed, angle_tol=angle_tol)

    affine = _extract_affine_angles_for_two_controls(spec)
    quad = _extract_quadratic_angles_for_two_controls(spec)

    return {
        "file": str(qasm_path),
        "k": actual_k,
        "ok": ok,
        "message": message,
        "expected_op_count": len(expected),
        "parsed_op_count": len(parsed),
        "expected_gate_histogram": summarize_ops(expected),
        "parsed_gate_histogram": summarize_ops(parsed),
        "path_type": "affine" if affine is not None else ("quadratic" if quad is not None else "unsupported"),
    }


def maybe_write_report(payload: dict, args: argparse.Namespace) -> Path | None:
    if not args.write_report and args.report_out is None:
        return None

    report_path = Path(args.report_out) if args.report_out else default_report_path(args.qasm, args.qasm_dir)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return report_path


def main() -> None:
    args = parse_args()

    if args.qasm is not None:
        files = [Path(args.qasm)]
    else:
        qdir = Path(args.qasm_dir)
        files = sorted(qdir.glob("*.qasm"))
        if not files:
            raise FileNotFoundError(f"No .qasm files found in {qdir}")

    results = []
    all_ok = True
    for f in files:
        res = compare_one_file(
            f,
            y=args.y,
            rule=args.rule,
            gfunc=args.gfunc,
            expr=args.expr,
            k=args.k,
            angle_tol=args.angle_tol,
        )
        results.append(res)
        all_ok = all_ok and bool(res["ok"])

    payload = {
        "all_ok": all_ok,
        "integrand": args.gfunc if args.gfunc is not None else args.expr,
        "y": args.y,
        "rule": args.rule,
        "angle_tol": args.angle_tol,
        "results": results,
    }

    report_path = maybe_write_report(payload, args)

    if args.json:
        print(json.dumps(payload, indent=2))
        if report_path is not None:
            print(f"\n[report written to] {report_path}")
        if not all_ok:
            raise SystemExit(1)
        return

    print("=== SpinQit logical structure vs QASM2 export ===")
    print(f"integrand : {args.gfunc if args.gfunc is not None else args.expr}")
    print(f"y         : {args.y}")
    print(f"rule      : {args.rule}")
    print()

    for res in results:
        status = "PASS" if res["ok"] else "FAIL"
        print(f"[{status}] {res['file']}")
        print(f"  k                : {res['k']}")
        print(f"  path_type        : {res['path_type']}")
        print(f"  expected_ops     : {res['expected_op_count']}")
        print(f"  parsed_ops       : {res['parsed_op_count']}")
        print(f"  expected_hist    : {res['expected_gate_histogram']}")
        print(f"  parsed_hist      : {res['parsed_gate_histogram']}")
        print(f"  result           : {res['message']}")
        print()

    if report_path is not None:
        print(f"[OK] JSON report written to: {report_path}")

    if not all_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
# src/qasm2/emitter.py
from __future__ import annotations

import math
from dataclasses import asdict
from typing import Iterable, Sequence

from src.qae.grover_op import apply_Q_iteration
from src.qae.state_prep import (
    ASpec,
    _extract_affine_angles_for_two_controls,
    _extract_quadratic_angles_for_two_controls,
    build_A_spec,
)


class Qasm2Builder:
    """
    Minimal OpenQASM 2.0 text builder for the 3-qubit QAE/Triangulum setup.

    Qubit convention:
      - q[0], q[1] = index qubits
      - q[2]       = ancilla

    Classical convention:
      - measure q[i] -> c[i]
      - downstream interpretation should remain consistent with the repo's
        canonical q0q1q2 convention.
    """

    def __init__(self, n_qubits: int = 3, n_clbits: int = 3) -> None:
        self.n_qubits = n_qubits
        self.n_clbits = n_clbits
        self.lines: list[str] = []
        self._write_header()

    def _write_header(self) -> None:
        self.lines.extend(
            [
                "OPENQASM 2.0;",
                'include "qelib1.inc";',
                "",
                self._custom_gate_defs().rstrip(),
                "",
                f"qreg q[{self.n_qubits}];",
                f"creg c[{self.n_clbits}];",
                "",
            ]
        )

    @staticmethod
    def _fmt_angle(theta: float) -> str:
        # Numeric literals are safest across OpenQASM 2.0 parsers.
        if abs(theta) < 1e-15:
            return "0.0"
        return f"{theta:.16f}"

    @staticmethod
    def _custom_gate_defs() -> str:
        # qelib1.inc has cx, ccx, h, x, z, ry, etc.
        # We define cry and ccry explicitly to avoid backend-dependent assumptions.
        return """gate cry(theta) c,t {
  ry(theta/2) t;
  cx c,t;
  ry(-theta/2) t;
  cx c,t;
}

gate ccry(theta) c0,c1,t {
  cry(theta/2) c1,t;
  cx c0,c1;
  cry(-theta/2) c1,t;
  cx c0,c1;
}"""

    def comment(self, text: str) -> None:
        for line in text.splitlines():
            self.lines.append(f"// {line}")

    def blank(self) -> None:
        self.lines.append("")

    def h(self, q: int) -> None:
        self.lines.append(f"h q[{q}];")

    def x(self, q: int) -> None:
        self.lines.append(f"x q[{q}];")

    def z(self, q: int) -> None:
        self.lines.append(f"z q[{q}];")

    def ry(self, theta: float, q: int) -> None:
        self.lines.append(f"ry({self._fmt_angle(theta)}) q[{q}];")

    def cx(self, c: int, t: int) -> None:
        self.lines.append(f"cx q[{c}],q[{t}];")

    def ccx(self, c0: int, c1: int, t: int) -> None:
        self.lines.append(f"ccx q[{c0}],q[{c1}],q[{t}];")

    def cry(self, theta: float, c: int, t: int) -> None:
        if abs(theta) < 1e-12:
            return
        self.lines.append(f"cry({self._fmt_angle(theta)}) q[{c}],q[{t}];")

    def ccry(self, theta: float, c0: int, c1: int, t: int) -> None:
        if abs(theta) < 1e-12:
            return
        self.lines.append(f"ccry({self._fmt_angle(theta)}) q[{c0}],q[{c1}],q[{t}];")

    def measure_all(self) -> None:
        for i in range(min(self.n_qubits, self.n_clbits)):
            self.lines.append(f"measure q[{i}] -> c[{i}];")

    def build(self) -> str:
        return "\n".join(self.lines).rstrip() + "\n"


def _emit_A_from_spec(builder: Qasm2Builder, spec: ASpec) -> None:
    q0, q1 = spec.index_qubits
    a = spec.ancilla

    builder.comment("A: state preparation")
    builder.h(q0)
    builder.h(q1)

    affine = _extract_affine_angles_for_two_controls(spec)
    if affine is not None:
        c0, c1, c2 = affine
        if abs(c0) > 1e-12:
            builder.ry(c0, a)
        builder.cry(c1, q0, a)
        builder.cry(c2, q1, a)
        return

    quad = _extract_quadratic_angles_for_two_controls(spec)
    if quad is not None:
        c0, c1, c2, c12 = quad
        if abs(c0) > 1e-12:
            builder.ry(c0, a)
        builder.cry(c1, q0, a)
        builder.cry(c2, q1, a)
        builder.ccry(c12, q0, q1, a)
        return

    raise NotImplementedError(
        "OpenQASM 2.0 exporter currently supports the 2-index-qubit affine/quadratic paths only."
    )


def _emit_Adag_from_spec(builder: Qasm2Builder, spec: ASpec) -> None:
    q0, q1 = spec.index_qubits
    a = spec.ancilla

    builder.comment("A^dagger")
    affine = _extract_affine_angles_for_two_controls(spec)
    if affine is not None:
        c0, c1, c2 = affine
        builder.cry(-c2, q1, a)
        builder.cry(-c1, q0, a)
        if abs(c0) > 1e-12:
            builder.ry(-c0, a)
        builder.h(q0)
        builder.h(q1)
        return

    quad = _extract_quadratic_angles_for_two_controls(spec)
    if quad is not None:
        c0, c1, c2, c12 = quad
        builder.ccry(-c12, q0, q1, a)
        builder.cry(-c2, q1, a)
        builder.cry(-c1, q0, a)
        if abs(c0) > 1e-12:
            builder.ry(-c0, a)
        builder.h(q0)
        builder.h(q1)
        return

    raise NotImplementedError(
        "OpenQASM 2.0 exporter currently supports the 2-index-qubit affine/quadratic paths only."
    )


def _emit_S_psi0(builder: Qasm2Builder, ancilla: int) -> None:
    builder.comment("S_psi0")
    builder.z(ancilla)


def _emit_S0_3q(builder: Qasm2Builder, qubits: Sequence[int]) -> None:
    if len(qubits) != 3:
        raise NotImplementedError("This exporter currently assumes exactly 3 qubits.")

    q0, q1, q2 = qubits
    builder.comment("S0 on |000>")
    builder.x(q0)
    builder.x(q1)
    builder.x(q2)
    builder.h(q2)
    builder.ccx(q0, q1, q2)
    builder.h(q2)
    builder.x(q0)
    builder.x(q1)
    builder.x(q2)


def _emit_Q_iteration(builder: Qasm2Builder, spec: ASpec) -> None:
    builder.comment("Q = A S0 A^dagger S_psi0")
    _emit_S_psi0(builder, spec.ancilla)
    _emit_Adag_from_spec(builder, spec)
    _emit_S0_3q(builder, [*spec.index_qubits, spec.ancilla])
    _emit_A_from_spec(builder, spec)


def export_qasm2_for_k(spec: ASpec, k: int, add_measurements: bool = True) -> str:
    if tuple(spec.index_qubits) != (0, 1) or spec.ancilla != 2:
        raise ValueError(
            "This initial exporter assumes index_qubits=(0,1) and ancilla=2."
        )

    builder = Qasm2Builder(n_qubits=3, n_clbits=3)
    builder.comment(f"Circuit for k={k}: Q^k A |000>")
    builder.blank()

    _emit_A_from_spec(builder, spec)
    for _ in range(int(k)):
        builder.blank()
        _emit_Q_iteration(builder, spec)

    if add_measurements:
        builder.blank()
        builder.comment("Measurement")
        builder.measure_all()

    return builder.build()


def export_qasm2_bundle(
    *,
    y: float,
    ks: Sequence[int],
    rule: str = "midpoint",
    gfunc: str | None = "sin^2(pi*x)",
    expr: str | None = None,
    index_qubits: Sequence[int] = (0, 1),
    ancilla: int = 2,
) -> dict[int, str]:
    spec = build_A_spec(
        y=y,
        n_index_qubits=len(index_qubits),
        rule=rule,  # type: ignore[arg-type]
        gfunc=gfunc,
        expr=expr,
        index_qubits=index_qubits,
        ancilla=ancilla,
    )
    return {int(k): export_qasm2_for_k(spec, int(k)) for k in ks}
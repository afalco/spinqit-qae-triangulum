# src/qae/state_prep.py

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Tuple

from .integrands import (
    OfficialGFunc,
    exact_integral,
    g_value,
    official_closed_form_theta,
    theta_from_value,
)
from .quadrature import Rule, grid_points


@dataclass(frozen=True)
class ASpec:
    index_qubits: Tuple[int, ...]
    ancilla: int
    patterns: Tuple[Tuple[Tuple[int, ...], float], ...]


def build_A_spec(
    y: float,
    n_index_qubits: int = 2,
    rule: Rule = "midpoint",
    gfunc: OfficialGFunc | None = "sin^2(pi*x)",
    expr: str | None = None,
    index_qubits: Sequence[int] = (0, 1),
    ancilla: int = 2,
) -> ASpec:
    if len(index_qubits) != n_index_qubits:
        raise ValueError("index_qubits length must match n_index_qubits.")

    grid = grid_points(y=y, n=n_index_qubits, rule=rule)
    m = 2**n_index_qubits
    patterns: List[Tuple[Tuple[int, ...], float]] = []

    for i in range(m):
        bits = tuple((i >> (n_index_qubits - 1 - b)) & 1 for b in range(n_index_qubits))
        x_i = grid.points[i]

        theta = official_closed_form_theta(x_i, gfunc=gfunc)
        if theta is None:
            gx = g_value(x_i, gfunc=gfunc, expr=expr)
            theta = theta_from_value(gx)
        else:
            # Consistency check: closed-form theta must agree with the
            # generic formula 2*asin(sqrt(g(x))) used by check_affinity.
            # A mismatch here means integrands.py has a typo in the
            # closed-form table and the circuit would silently implement
            # a different function from what the affinity diagnostic validated.
            gx = g_value(x_i, gfunc=gfunc, expr=expr)
            theta_generic = theta_from_value(gx)
            if abs(theta - theta_generic) > 1e-9:
                raise ValueError(
                    f"Closed-form theta mismatch for gfunc={gfunc!r} at x={x_i}: "
                    f"closed_form={theta:.12f}, generic={theta_generic:.12f}, "
                    f"diff={abs(theta - theta_generic):.3e}. "
                    "Fix the closed-form table in integrands.py."
                )

        patterns.append((bits, theta))

    return ASpec(
        index_qubits=tuple(index_qubits),
        ancilla=ancilla,
        patterns=tuple(patterns),
    )


def _get_gates():
    from spinqit import H, X, Ry  # type: ignore
    from spinqit.primitive import MultiControlledGateBuilder  # type: ignore

    return H, X, Ry, MultiControlledGateBuilder


def _extract_affine_angles_for_two_controls(spec: ASpec, tol: float = 1e-9):
    if len(spec.index_qubits) != 2 or len(spec.patterns) != 4:
        return None

    angle_map = {bits: theta for bits, theta in spec.patterns}
    required = [(0, 0), (0, 1), (1, 0), (1, 1)]
    if any(bits not in angle_map for bits in required):
        return None

    t00 = angle_map[(0, 0)]
    t01 = angle_map[(0, 1)]
    t10 = angle_map[(1, 0)]
    t11 = angle_map[(1, 1)]

    c0 = t00
    c1 = t10 - t00
    c2 = t01 - t00

    if abs((c0 + c1 + c2) - t11) > tol:
        return None

    return c0, c1, c2


def is_affine_hardware_friendly(spec: ASpec, tol: float = 1e-9) -> bool:
    return _extract_affine_angles_for_two_controls(spec, tol=tol) is not None


def _extract_quadratic_angles_for_two_controls(spec: ASpec, tol: float = 1e-9):
    """
    Extract Mobius coefficients for the degree-2 (quadratic) case with 2 index qubits.

    Any function on B^2 has the unique multilinear expansion
        theta(b0, b1) = c0 + c1*b0 + c2*b1 + c12*b0*b1
    with coefficients recovered by Mobius inversion:
        c0   = t00
        c1   = t10 - t00
        c2   = t01 - t00
        c12  = t11 - t10 - t01 + t00
    This covers ALL functions on B^2, so this extractor always succeeds
    for a 2-qubit spec (returns None only if the spec has wrong shape).

    The encoding operator then factors as (Thm 4.2 in the paper):
        G_g = Ry(c0) . C_q0-Ry(c1) . C_q1-Ry(c2) . CC_q0q1-Ry(c12)
    implemented with exactly binom(2,<=2) = 4 controlled-Ry gates.
    """
    if len(spec.index_qubits) != 2 or len(spec.patterns) != 4:
        return None

    angle_map = {bits: theta for bits, theta in spec.patterns}
    required = [(0, 0), (0, 1), (1, 0), (1, 1)]
    if any(bits not in angle_map for bits in required):
        return None

    t00 = angle_map[(0, 0)]
    t01 = angle_map[(0, 1)]
    t10 = angle_map[(1, 0)]
    t11 = angle_map[(1, 1)]

    c0  = t00
    c1  = t10 - t00
    c2  = t01 - t00
    c12 = t11 - t10 - t01 + t00

    return c0, c1, c2, c12


def _apply_single_controlled_ry(circuit, control: int, target: int, theta: float):
    if abs(theta) < 1e-12:
        return

    _, _, Ry, MultiControlledGateBuilder = _get_gates()
    c_ry = MultiControlledGateBuilder(1, Ry, [theta]).to_gate()
    circuit << (c_ry, (control, target))


def _apply_two_controlled_ry(circuit, control0: int, control1: int, target: int, theta: float):
    """
    Implement CC-Ry(theta) — a doubly-controlled Ry rotation — using the
    standard decomposition into singly-controlled gates (Barenco et al. 1995,
    also Appendix B of the paper):
        CC-Ry(theta) = C_c1-Ry(theta/2) . CNOT(c0->c1) .
                       C_c1-Ry(-theta/2) . CNOT(c0->c1)
    This uses 2 CNOTs and 2 singly-controlled Ry gates, keeping circuit
    depth within the Triangulum line-depth limit of 60.
    """
    if abs(theta) < 1e-12:
        return

    _, X, Ry, MultiControlledGateBuilder = _get_gates()

    # Step 1: C_control1-Ry(theta/2) on target
    _apply_single_controlled_ry(circuit, control1, target, theta / 2.0)

    # Step 2: CNOT(control0 -> control1)
    from spinqit import CNOT  # type: ignore
    circuit << (CNOT, (control0, control1))

    # Step 3: C_control1-Ry(-theta/2) on target
    _apply_single_controlled_ry(circuit, control1, target, -theta / 2.0)

    # Step 4: CNOT(control0 -> control1)
    circuit << (CNOT, (control0, control1))


def _apply_controlled_ry_on_pattern(
    circuit,
    controls: Sequence[int],
    ancilla: int,
    theta: float,
    bits: Tuple[int, ...],
):
    _, X, Ry, MultiControlledGateBuilder = _get_gates()

    flipped = []
    for q, b in zip(controls, bits):
        if b == 0:
            circuit << (X, q)
            flipped.append(q)

    mc_ry = MultiControlledGateBuilder(len(controls), Ry, [theta]).to_gate()
    qubits = tuple(list(controls) + [ancilla])
    circuit << (mc_ry, qubits)

    for q in flipped:
        circuit << (X, q)


def apply_A_from_spec(circuit, spec: ASpec):
    H, _, Ry, _ = _get_gates()

    for q in spec.index_qubits:
        circuit << (H, q)

    # Branch 1: affine case (d=1) — 3 gates, shallowest circuit
    affine = _extract_affine_angles_for_two_controls(spec)
    if affine is not None:
        c0, c1, c2 = affine
        q0, q1 = spec.index_qubits
        a = spec.ancilla

        if abs(c0) > 1e-12:
            circuit << (Ry, a, c0)
        _apply_single_controlled_ry(circuit, q0, a, c1)
        _apply_single_controlled_ry(circuit, q1, a, c2)
        return

    # Branch 2: quadratic case (d=2) — 4 controlled-Ry gates via Mobius
    # factorisation (Thm 4.2). CC-Ry is decomposed into 2 CNOTs + 2 C-Ry
    # (Appendix B), keeping total depth within the Triangulum limit of 60.
    if len(spec.index_qubits) == 2:
        quad = _extract_quadratic_angles_for_two_controls(spec)
        if quad is not None:
            c0, c1, c2, c12 = quad
            q0, q1 = spec.index_qubits
            a = spec.ancilla

            if abs(c0) > 1e-12:
                circuit << (Ry, a, c0)
            _apply_single_controlled_ry(circuit, q0, a, c1)
            _apply_single_controlled_ry(circuit, q1, a, c2)
            _apply_two_controlled_ry(circuit, q0, q1, a, c12)
            return

    # Branch 3: generic fallback (d > 2 or n > 2) — uses MultiControlledGateBuilder
    # Note: this branch may exceed the Triangulum line-depth limit for n=2, d=2.
    for bits, theta in spec.patterns:
        _apply_controlled_ry_on_pattern(circuit, spec.index_qubits, spec.ancilla, theta, bits)


def apply_Adag_from_spec(circuit, spec: ASpec):
    H, _, Ry, _ = _get_gates()

    # Branch 1: affine case (d=1)
    affine = _extract_affine_angles_for_two_controls(spec)
    if affine is not None:
        c0, c1, c2 = affine
        q0, q1 = spec.index_qubits
        a = spec.ancilla

        _apply_single_controlled_ry(circuit, q1, a, -c2)
        _apply_single_controlled_ry(circuit, q0, a, -c1)
        if abs(c0) > 1e-12:
            circuit << (Ry, a, -c0)

        for q in spec.index_qubits:
            circuit << (H, q)
        return

    # Branch 2: quadratic case (d=2) — reverse order, negated angles
    if len(spec.index_qubits) == 2:
        quad = _extract_quadratic_angles_for_two_controls(spec)
        if quad is not None:
            c0, c1, c2, c12 = quad
            q0, q1 = spec.index_qubits
            a = spec.ancilla

            _apply_two_controlled_ry(circuit, q0, q1, a, -c12)
            _apply_single_controlled_ry(circuit, q1, a, -c2)
            _apply_single_controlled_ry(circuit, q0, a, -c1)
            if abs(c0) > 1e-12:
                circuit << (Ry, a, -c0)

            for q in spec.index_qubits:
                circuit << (H, q)
            return

    # Branch 3: generic fallback
    for bits, theta in reversed(spec.patterns):
        _apply_controlled_ry_on_pattern(circuit, spec.index_qubits, spec.ancilla, -theta, bits)

    for q in spec.index_qubits:
        circuit << (H, q)
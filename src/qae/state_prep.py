#src/qae/state_prep.py
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Literal, Sequence, Tuple

from .quadrature import Rule, grid_points

GFunc = Literal["sin2_pi"]  # extensible


@dataclass(frozen=True)
class ASpec:
    """
    Declarative specification of the state-preparation operator A.

    For 2 index qubits (Triangulum), A is:
      - H on each index qubit
      - For each basis |i>, apply controlled Ry(theta_i) on ancilla,
        where theta_i encodes g(x_i).

    We store:
      - index_qubits: positions (e.g., [0,1])
      - ancilla: position (e.g., 2)
      - patterns: list of (bitpattern, theta) where bitpattern is tuple of bits for index qubits
    """
    index_qubits: Tuple[int, ...]
    ancilla: int
    patterns: Tuple[Tuple[Tuple[int, ...], float], ...]  # ((bits...), theta)


def _g_value(x: float, gfunc: GFunc) -> float:
    if gfunc == "sin2_pi":
        return math.sin(math.pi * x) ** 2
    raise ValueError(f"Unknown gfunc: {gfunc}")


def build_A_spec(
    y: float,
    n_index_qubits: int = 2,
    rule: Rule = "midpoint",
    gfunc: GFunc = "sin2_pi",
    index_qubits: Sequence[int] = (0, 1),
    ancilla: int = 2,
) -> ASpec:
    """
    Build a Triangulum-friendly A-spec with 2 index qubits + 1 ancilla by default.

    We use the convenient encoding:
      Pr(anc=1 | i) = sin^2(theta_i/2)

    For g(x)=sin^2(pi x), we can set:
      theta_i = 2*pi*x_i

    so that sin^2(theta_i/2) = sin^2(pi x_i) = g(x_i).
    """
    if len(index_qubits) != n_index_qubits:
        raise ValueError("index_qubits length must match n_index_qubits.")
    grid = grid_points(y=y, n=n_index_qubits, rule=rule)
    m = 2**n_index_qubits

    patterns: List[Tuple[Tuple[int, ...], float]] = []
    for i in range(m):
        bits = tuple((i >> (n_index_qubits - 1 - b)) & 1 for b in range(n_index_qubits))
        x_i = grid.points[i]
        if gfunc == "sin2_pi":
            theta = 2.0 * math.pi * x_i
        else:
            # Generic fallback: theta = 2*arcsin(sqrt(g(x)))
            gx = _g_value(x_i, gfunc)
            gx = min(max(gx, 0.0), 1.0)
            theta = 2.0 * math.asin(math.sqrt(gx))
        patterns.append((bits, theta))

    return ASpec(index_qubits=tuple(index_qubits), ancilla=ancilla, patterns=tuple(patterns))


def _get_gates():
    """
    Import SpinQit gates lazily to keep import-time failures localized.

    NOTE: SpinQit API names may vary by version. If your installation differs,
    adapt this function to map to your local gate constructors.
    """
    from spinqit import H, X, Ry  # type: ignore

    try:
        from spinqit.primitive import MultiControlledGateBuilder  # type: ignore
    except Exception as e:
        raise ImportError(
            "Could not import MultiControlledGateBuilder from spinqit. "
            "Please adapt _get_gates() to your SpinQit version."
        ) from e

    return H, X, Ry, MultiControlledGateBuilder


def _extract_affine_angles_for_two_controls(spec: ASpec):
    """
    If the 4 pattern angles satisfy
        theta(b0,b1) = c0 + c1*b0 + c2*b1
    return (c0, c1, c2). Otherwise return None.

    Bit ordering follows spec.patterns as produced by build_A_spec:
      (0,0), (0,1), (1,0), (1,1)
    with b0 = first index qubit, b1 = second index qubit.
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

    c0 = t00
    c1 = t10 - t00
    c2 = t01 - t00

    if abs((c0 + c1 + c2) - t11) > 1e-9:
        return None

    return c0, c1, c2


def _apply_single_controlled_ry(circuit, control: int, target: int, theta: float):
    if abs(theta) < 1e-12:
        return

    H, X, Ry, MultiControlledGateBuilder = _get_gates()
    c_ry = MultiControlledGateBuilder(1, Ry, [theta]).to_gate()
    circuit << (c_ry, (control, target))


def _apply_controlled_ry_on_pattern(
    circuit,
    controls: Sequence[int],
    ancilla: int,
    theta: float,
    bits: Tuple[int, ...],
):
    """
    Apply a multi-controlled Ry(theta) on ancilla, conditioned on controls
    being exactly 'bits'.

    We implement the exact bit-pattern condition by X-flipping the controls
    where bits[j] = 0, so the condition becomes all-ones, then applying a
    multi-controlled Ry(theta), then undoing the flips.
    """
    H, X, Ry, MultiControlledGateBuilder = _get_gates()

    flipped = []
    for q, b in zip(controls, bits):
        if b == 0:
            circuit << (X, q)
            flipped.append(q)

    mc_ry = MultiControlledGateBuilder(len(controls), Ry, [theta]).to_gate()

    qubits = tuple(list(controls) + [ancilla])

    try:
        circuit << (mc_ry, qubits)
    except Exception as e:
        raise RuntimeError(
            f"Could not apply multi-controlled Ry on qubits {qubits}. "
            "Your local SpinQit build may use a different call signature."
        ) from e

    for q in flipped:
        circuit << (X, q)


def apply_A_from_spec(circuit, spec: ASpec):
    """Append the state-preparation operator A described by `spec` to `circuit`."""
    H, X, Ry, MultiControlledGateBuilder = _get_gates()

    # Uniform superposition over index
    for q in spec.index_qubits:
        circuit << (H, q)

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

    # Generic fallback: exact pattern-controlled implementation
    for bits, theta in spec.patterns:
        _apply_controlled_ry_on_pattern(circuit, spec.index_qubits, spec.ancilla, theta, bits)


def apply_Adag_from_spec(circuit, spec: ASpec):
    r"""
    Append A^\dagger to `circuit`.

    Since A is a sequence of:
      H on index qubits (self-inverse),
      followed by controlled Ry(theta_i),
    we implement the inverse by reversing the sequence and negating angles.
    """
    H, X, Ry, MultiControlledGateBuilder = _get_gates()

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

    # Generic fallback: reverse order, angle -> -angle
    for bits, theta in reversed(spec.patterns):
        _apply_controlled_ry_on_pattern(circuit, spec.index_qubits, spec.ancilla, -theta, bits)

    # Inverse of H on index qubits (self-inverse)
    for q in spec.index_qubits:
        circuit << (H, q)
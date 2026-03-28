from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Literal

ReportedOrder = Literal["q0q1q2", "q2q1q0"]


CANONICAL_ORDER: ReportedOrder = "q0q1q2"
CANONICAL_STATES_3Q = ("000", "001", "010", "011", "100", "101", "110", "111")


def normalize_bitstring(bitstr: str, nbits: int = 3) -> str:
    s = str(bitstr).replace("0b", "").strip()
    if len(s) < nbits:
        s = s.zfill(nbits)
    return s[-nbits:]


def canonicalize_bitstring(bitstr: str, reported_order: ReportedOrder, nbits: int = 3) -> str:
    s = normalize_bitstring(bitstr, nbits=nbits)
    if reported_order == "q0q1q2":
        return s
    if reported_order == "q2q1q0":
        return s[::-1]
    raise ValueError(f"Unsupported reported_order: {reported_order}")


def canonicalize_counts(
    counts: Dict[str, int],
    reported_order: ReportedOrder,
    nbits: int = 3,
) -> Dict[str, int]:
    out = {state: 0 for state in CANONICAL_STATES_3Q[: 2**nbits]}
    for bitstr, c in counts.items():
        key = canonicalize_bitstring(bitstr, reported_order=reported_order, nbits=nbits)
        out[key] = out.get(key, 0) + int(c)
    return out


def ancilla_index_from_right_for_canonical_q0q1q2(ancilla_qubit: int, nbits: int = 3) -> int:
    """
    In canonical order q0q1q2, the rightmost character is q_{nbits-1}.
    So the position from the right is:
        ancilla_bit_index_from_right = (nbits - 1 - ancilla_qubit)
    For 3 qubits and ancilla_qubit=2, this returns 0.
    """
    if not (0 <= ancilla_qubit < nbits):
        raise ValueError(f"ancilla_qubit must lie in [0, {nbits - 1}]")
    return nbits - 1 - ancilla_qubit

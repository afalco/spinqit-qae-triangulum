# src/qae/reflections.py
from __future__ import annotations

from typing import Sequence


def _get_gates():
    from spinqit import X, Z, H, CCX  # type: ignore
    return X, Z, H, CCX


def apply_S_psi0(circuit, ancilla: int):
    """
    Reflection marking 'good' states. Here good <=> ancilla == |1>.
    Implement as a Z on the ancilla.
    """
    X, Z, H, CCX = _get_gates()
    circuit << (Z, ancilla)


def apply_S0(circuit, qubits: Sequence[int]):
    """
    Reflection about |0...0>. For Triangulum we assume exactly 3 qubits.

    Implementation:
      X on all qubits
      CCZ on all qubits (via H on target + CCX + H)
      X on all qubits
    """
    X, Z, H, CCX = _get_gates()

    if len(qubits) != 3:
        raise ValueError("apply_S0 currently supports exactly 3 qubits (Triangulum).")

    q0, q1, q2 = qubits  # use q2 as target for CCZ via CCX
    circuit << (X, q0)
    circuit << (X, q1)
    circuit << (X, q2)

    # CCZ(q0,q1,q2) = H(q2) CCX(q0,q1->q2) H(q2)
    circuit << (H, q2)
    circuit << (CCX, q0, q1, q2)
    circuit << (H, q2)

    circuit << (X, q0)
    circuit << (X, q1)
    circuit << (X, q2)

# src/qae/reflections.py
from __future__ import annotations

from typing import Sequence


def _get_gates():
    from spinqit import X, Z, H, CX, CCX  # type: ignore
    return X, Z, H, CX, CCX


def apply_S_psi0(circuit, ancilla: int):
    """
    Reflection S_{psi0}: phase flip on the ancilla |1> component.
    Implemented as Z on ancilla.
    """
    X, Z, H, CX, CCX = _get_gates()
    circuit << (Z, ancilla)


def apply_S0(circuit, qubits: Sequence[int]):
    """
    Reflection about |0...0>:
        S0 = I - 2|0...0><0...0|

    Up to a global phase, this is implemented by:
      X on all qubits
      multi-controlled Z on the all-ones state
      X on all qubits

    For 3 qubits (Triangulum), CCZ is implemented as H on target, CCX, H on target.
    """
    X, Z, H, CX, CCX = _get_gates()

    qs = list(qubits)
    n = len(qs)

    if n == 0:
        return

    for q in qs:
        circuit << (X, q)

    if n == 1:
        circuit << (Z, qs[0])

    elif n == 2:
        # CZ = H(target) CX(control,target) H(target)
        q0, q1 = qs
        circuit << (H, q1)
        circuit << (CX, (q0, q1))
        circuit << (H, q1)

    elif n == 3:
        # CCZ = H(target) CCX(control1,control2,target) H(target)
        q0, q1, q2 = qs
        circuit << (H, q2)
        circuit << (CCX, (q0, q1, q2))
        circuit << (H, q2)

    else:
        raise NotImplementedError(
            "apply_S0 currently supports up to 3 qubits. "
            "For more qubits, build a general multi-controlled Z."
        )

    for q in qs:
        circuit << (X, q)
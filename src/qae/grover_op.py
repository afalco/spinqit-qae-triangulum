# src/qae/grover_op.py
from __future__ import annotations

from .reflections import apply_S0, apply_S_psi0
from .state_prep import ASpec, apply_A_from_spec, apply_Adag_from_spec


def apply_Q_iteration(circuit, spec: ASpec) -> None:
    """
    Apply one amplitude-amplification (Grover/QAE) iteration:

        Q = A S0 A^\dagger S_{psi0}

    where:
      - S_{psi0} marks "good" states (ancilla == |1>) and is implemented as Z on the ancilla,
      - S0 is the reflection about |000> on the full 3-qubit register (X..CCZ..X),
      - A is the state-preparation operator for the numerical integration instance.

    Convention:
      This ordering is consistent with constructing states |psi_k> = Q^k A |000>.
    """
    # Q = A S0 A† S_psi0
    apply_S_psi0(circuit, spec.ancilla)
    apply_Adag_from_spec(circuit, spec)
    apply_S0(circuit, list(spec.index_qubits) + [spec.ancilla])
    apply_A_from_spec(circuit, spec)

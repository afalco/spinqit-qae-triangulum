# src/qae/mlae.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from .grover_op import apply_Q_iteration
from .integrands import OfficialGFunc
from .state_prep import ASpec, build_A_spec, apply_A_from_spec


@dataclass(frozen=True)
class RunResult:
    """
    Container for a single MLAE run over a list of k values.
    """
    y: float
    rule: str
    gfunc: str | None
    expr: str | None
    ks: Tuple[int, ...]
    shots: int
    counts_per_k: Tuple[Dict[str, int], ...]
    p_hat: Tuple[float, ...]


def _extract_ancilla_1_prob(counts: Dict[str, int], ancilla_bit_index_from_right: int) -> float:
    """
    Extract Pr(ancilla=1) from canonicalized counts.

    The repository-wide canonical convention is:
        q0q1q2  ->  ['000', '001', ..., '111']

    Hence, for 3 qubits and ancilla_qubit=2, the canonical position from the right is 0.
    """
    total = sum(counts.values())
    if total <= 0:
        return 0.0

    ones = 0
    for bitstr, c in counts.items():
        s = bitstr.replace("0b", "").strip()
        if len(s) < ancilla_bit_index_from_right + 1:
            s = s.zfill(ancilla_bit_index_from_right + 1)
        anc_bit = s[-1 - ancilla_bit_index_from_right]
        if anc_bit == "1":
            ones += c
    return ones / total


def build_circuit_for_k(spec: ASpec, k: int):
    """
    Construct a SpinQit circuit for a given amplification index k:
        circuit = Q^k A |000>
    Then append measurement.
    """
    from spinqit import Circuit  # type: ignore

    circ = Circuit()
    try:
        circ.allocateQubits(3)
    except Exception:
        pass

    apply_A_from_spec(circ, spec)

    for _ in range(int(k)):
        apply_Q_iteration(circ, spec)

    try:
        circ.measure_all()
    except Exception:
        try:
            circ.measure(range(3))
        except Exception:
            pass

    return circ


def run_mlae(
    backend,
    y: float,
    ks: Sequence[int] = (0, 1, 2),
    rule: str = "midpoint",
    shots: int = 4096,
    ancilla_qubit: int = 2,
    index_qubits: Sequence[int] = (0, 1),
    ancilla_bit_index_from_right: int = 0,
    gfunc: OfficialGFunc | None = "sin^2(pi*x)",
    expr: str | None = None,
) -> RunResult:
    """
    Execute MLAE-style runs for each k in `ks` on the provided backend wrapper.

    The backend is expected to return counts already canonicalized to q0q1q2.
    """
    spec = build_A_spec(
        y=y,
        n_index_qubits=len(index_qubits),
        rule=rule,  # type: ignore[arg-type]
        gfunc=gfunc,
        expr=expr,
        index_qubits=index_qubits,
        ancilla=ancilla_qubit,
    )

    counts_list: List[Dict[str, int]] = []
    p_list: List[float] = []

    for k in ks:
        circ = build_circuit_for_k(spec, int(k))
        result = backend.run(circ, shots=shots)

        if isinstance(result, dict):
            counts = result
        elif hasattr(result, "counts"):
            counts = result.counts
        elif hasattr(result, "get_counts"):
            counts = result.get_counts()
        else:
            raise RuntimeError(
                "Backend returned an unsupported result type. "
                "Please adapt backend.run() to return dict counts or a compatible object."
            )

        counts_list.append(counts)
        p_list.append(_extract_ancilla_1_prob(counts, ancilla_bit_index_from_right))

    return RunResult(
        y=float(y),
        rule=str(rule),
        gfunc=None if gfunc is None else str(gfunc),
        expr=None if expr is None else str(expr),
        ks=tuple(int(k) for k in ks),
        shots=int(shots),
        counts_per_k=tuple(counts_list),
        p_hat=tuple(p_list),
    )

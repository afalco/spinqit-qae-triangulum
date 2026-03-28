## Canonical bit-order policy

The repository now adopts a single canonical state-order convention for all
stored and compared 3-qubit distributions:

- canonical state order: `q0q1q2`
- canonical state list: `['000', '001', '010', '011', '100', '101', '110', '111']`

This convention applies to:

- simulator runs,
- Triangulum NMR runs,
- JSON and CSV artifacts,
- affinity diagnostics,
- postprocessing and summaries.

### Backend-reported order vs canonical order

A backend may report raw bitstrings in one of two common orders:

- `q0q1q2`
- `q2q1q0`

The wrappers in `src/backends/` are responsible for converting raw backend
counts into the canonical repository order before those counts are used
downstream.

This means that the main execution scripts no longer rely on ad hoc bit-order
reasoning when extracting the ancilla probability.

### Role of `calibrate_bit_order.py`

Use `calibrate_bit_order.py` to determine how a backend reports raw bitstrings.
Then set the backend wrapper accordingly through the `reported_order` setting.

The calibration utility remains the reference diagnostic for distinguishing:

- `reported_order = "q0q1q2"`
- `reported_order = "q2q1q0"`

### Ancilla indexing after canonicalization

After canonicalization to `q0q1q2`, the ancilla bit index from the right is
fixed by the ancilla qubit number.

For the current 3-qubit layout used in this repository:

- index qubits: `q0`, `q1`
- ancilla qubit: `q2`

so the canonical ancilla position from the right is:

- `ancilla_bit_index_from_right = 0`

This is now the canonical default in the main execution scripts.

# IBM Quantum Composer workflow for `spinqit-qae-triangulum`

This document explains how to export **IBM Quantum Composer-compatible OpenQASM 2.0** circuits from this repository and how to use them in the Composer environment at `quantum.cloud.ibm.com/composer`.

The goal is **not** to move the whole MLAE workflow into Composer. Instead, the goal is to export the **quantum circuits**

$$
Q^k A\lvert 000\rangle,
$$

one circuit for each amplification index `k`, run those circuits in IBM Quantum Composer, and then perform the **maximum-likelihood estimation (MLE)** classically outside Composer.

IBM Quantum Composer provides an editable **OpenQASM 2.0** code view synchronized with the circuit view, so it is a natural target for this export path. 

---

## 1. Scope of this exporter

The IBM Composer exporter is designed for the **3-qubit QAE setup** used in this repository:

- `q[0]`, `q[1]`: index qubits,
- `q[2]`: ancilla qubit.

It currently targets the structured two-index-qubit state-preparation path already implemented in the repository:

- **affine angle structure**, and
- **quadratic angle structure**.

The exporter intentionally emits a conservative OpenQASM 2.0 subset using only:

- `h`
- `x`
- `z`
- `ry`
- `cx`
- `ccx`
- `measure`

This conservative policy is recommended because IBM backends have backend-specific transpilation constraints and instruction sets, and Composer-based workflows are generally smoother when circuits are expressed in standard operations rather than in higher-level custom macros. Backend instruction support and calibration data are exposed on IBM Quantum Platform through backend details and transpilation targets. citeturn115054search1turn115054search5

---

## 2. Why OpenQASM 2.0 is sufficient here

OpenQASM is appropriate for the **circuit layer** of the MLAE workflow because it describes ordered sequences of gates, measurements, and classical registers. IBM documents OpenQASM as a machine-independent circuit description language, and Composer directly supports editing OpenQASM 2.0. 

However, OpenQASM 2.0 is **not** the right place to encode the full MLAE workflow, because MLAE also contains a classical postprocessing stage. IBM explicitly notes that OpenQASM 2.0 is a simple language and is not suitable as a general serialization format for arbitrary higher-level program objects. 

Therefore, the correct split is:

- **inside Composer / OpenQASM 2.0**: each circuit `Q^k A |000>`
- **outside Composer**: aggregation of counts and MLE estimation

---

## 3. Files to add to the repository

Add the following files:

- `src/qasm2/__init__.py`
- `src/qasm2/emitter.py`
- `scripts/04_export_qasm2.py`

The emitter should generate **IBM Composer-compatible OpenQASM 2.0** and should avoid custom gate declarations. In particular:

- `CRy(theta)` is emitted through its explicit expansion in `ry` and `cx`,
- `CCRy(theta)` is emitted through an explicit decomposition using only expanded `CRy` and `cx`,
- `S_0` is emitted as `X... CCZ ...X`, with `CCZ` implemented as `H-CCX-H` on the ancilla.

This matches the structure already used in the current repository for the 3-qubit case.

---

## 4. Export script usage

Once the exporter has been added, generate the OpenQASM files with, for example:

```bash
python scripts/04_export_qasm2.py --gfunc "sin^2(pi*x)" --y 1.0 --rule midpoint --ks 0,1,2
```

or

```bash
python scripts/04_export_qasm2.py --gfunc "x" --y 1.0 --rule midpoint --ks 0,1,2
```

This creates an output directory such as:

```text
artifacts/qasm2/qasm2_ibmcomposer_x_y1_midpoint_ks0-1-2_<timestamp>/
```

containing:

- one `.qasm` file for each value of `k`, and
- one `metadata.json` file.

A typical output set is:

```text
qasm2_ibmcomposer_x_y1_midpoint_ks0-1-2_<timestamp>_k0.qasm
qasm2_ibmcomposer_x_y1_midpoint_ks0-1-2_<timestamp>_k1.qasm
qasm2_ibmcomposer_x_y1_midpoint_ks0-1-2_<timestamp>_k2.qasm
qasm2_ibmcomposer_x_y1_midpoint_ks0-1-2_<timestamp>_metadata.json
```

---

## 5. What each exported circuit represents

Each exported file corresponds to a **single** amplification index `k`.

The logical content is:

1. prepare the state with `A`,
2. apply the Grover-style QAE iterate `Q` exactly `k` times,
3. measure all qubits.

That is,

$$
\text{circuit}(k) = Q^k A \lvert 000 \rangle.
$$

This is the correct object to run in Composer because Composer works at the circuit level, while MLAE as an estimator combines the outcome statistics from several such circuits.

---

## 6. Importing the files into IBM Quantum Composer

IBM Quantum Composer supports a code editor in which **OpenQASM 2.0 is editable**, and the code view is synchronized with the visual circuit representation. Composer also supports exporting code for use in different applications.

Recommended workflow:

1. Open IBM Quantum Composer.
2. Create a new circuit or open the code editor.
3. Paste the contents of one exported `.qasm` file into the OpenQASM editor, or upload the `.qasm` file if that option is available in your Composer session.
4. Verify that the circuit diagram renders correctly.
5. Select a backend or simulator.
6. Run the circuit.
7. Repeat for each value of `k`.

Because the code editor and circuit view are synchronized, Composer is useful both for execution and for checking that the decomposition looks structurally correct. 

---

## 7. Reading the results correctly

The exported circuits measure all three qubits:

- `q[0] -> c[0]`
- `q[1] -> c[1]`
- `q[2] -> c[2]`

The repository should continue to treat the state label convention consistently with its own canonical ordering. The `metadata.json` file therefore records:

- the qubit roles,
- the measurement map,
- the value of `k`,
- the chosen integrand,
- the quadrature rule,
- and the extracted affine or quadratic angle data.

For MLAE, the key quantity is the success probability associated with the ancilla measurement, but the full 3-qubit readout is useful for diagnostics, debugging, and consistency checks.

---

## 8. Practical advice for IBM hardware

Even when Composer accepts the OpenQASM file, actual execution quality depends on the chosen IBM backend. IBM exposes per-backend calibration data, instruction properties, and transpilation target information, which are relevant when analyzing depth, two-qubit error accumulation, and measurement quality. 

For that reason, the recommended initial campaign is conservative:

- start with `k = 0, 1, 2`,
- start with an affine or near-affine integrand when possible,
- inspect circuit depth after import/transpilation,
- and only then test larger values of `k`.

This matters because the circuits become deeper as `k` increases, and deeper decompositions generally amplify hardware noise.

---

## 9. Suggested first experiments

A good first pass is:

### Example A: `g(x) = x`

```bash
python scripts/04_export_qasm2.py --gfunc "x" --y 1.0 --rule midpoint --ks 0,1,2
```

This is a good sanity check because the angle structure is especially transparent.

### Example B: `g(x) = sin^2(pi*x)`

```bash
python scripts/04_export_qasm2.py --gfunc "sin^2(pi*x)" --y 1.0 --rule midpoint --ks 0,1,2
```

This is closer to the integrands already used in the repository’s QAE experiments.

---

## 10. Limitations of the current IBM Composer path

The current exporter is intentionally limited to the structured **two-index-qubit** workflow.

It does **not** aim, at this stage, to:

- serialize the full hybrid MLAE pipeline into OpenQASM,
- support arbitrary generic multi-controlled constructions beyond the present structured case,
- or optimize directly for a particular IBM backend’s native instruction set.

Those are reasonable future extensions, but they should be treated as a second phase.

---

## 11. Recommended next step after basic import succeeds

Once the exported `.qasm` circuits load correctly in Composer, the next useful step is to add a validation script, for example:

```text
scripts/05_compare_spinqit_vs_qasm2.py
```

The purpose of that script would be to verify that the exported IBM Composer version preserves the logical ordering of:

- `A`,
- `A^\dagger`,
- `S_{\psi_0}`,
- `S_0`,
- and therefore `Q`.

This is especially useful before running a full experiment campaign on IBM hardware.

---

## 12. Summary

The IBM Composer path is feasible and technically natural for this repository because:

- Composer supports editable **OpenQASM 2.0** and keeps code and circuit views synchronized, 
- OpenQASM 2.0 is appropriate for the circuit layer of MLAE, 
- backend-dependent instruction constraints and calibration data can then be inspected directly on IBM Quantum Platform, 
- and the repository’s current 3-qubit structured QAE construction is simple enough to be exported in a conservative gate set compatible with Composer.

The right conceptual model is:

- **export circuits to Composer**,
- **run one circuit per `k`**,
- **collect counts**,
- **perform MLAE classically outside Composer**.

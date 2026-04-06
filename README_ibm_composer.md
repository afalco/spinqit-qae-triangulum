# IBM Quantum Composer and Runtime workflow for `spinqit-qae-triangulum`

This document describes the practical IBM workflow that has now been validated for the repository:

1. export IBM Composer-compatible OpenQASM 2.0 circuits,
2. run one circuit per amplification index `k` on IBM Quantum,
3. recover the IBM Runtime job results,
4. convert those results into repository-friendly JSON artifacts,
5. combine the data from `k=0,1,2,...` for classical MLAE postprocessing.

The purpose of this path is **not** to move the whole MLAE workflow into Composer.  
The purpose is to export the **quantum circuits**
\[
Q^k A\lvert 000\rangle,
\]
run them on IBM Quantum, and then perform the estimator and data analysis classically outside IBM Composer.

---

## 1. Scope of the IBM exporter

The exporter targets the **3-qubit QAE setup** used in this repository:

- `q[0]`, `q[1]`: index qubits,
- `q[2]`: ancilla qubit.

It is designed for the structured two-index-qubit state-preparation path already present in the repository:

- affine angle structure,
- quadratic angle structure.

The emitted OpenQASM 2.0 is deliberately conservative and uses only:

- `h`
- `x`
- `z`
- `ry`
- `cx`
- `ccx`
- `measure`

No custom gates are required in the IBM Composer-oriented export.

---

## 2. Files involved in the IBM workflow

The practical IBM path uses the following scripts and modules:

- `src/qasm2/__init__.py`
- `src/qasm2/emitter.py`
- `scripts/04_export_qasm2.py`
- `scripts/05_compare_spinqit_vs_qasm2.py`
- `scripts/06_ibm_job_to_json.py`

Their roles are:

- `04_export_qasm2.py`: export one `.qasm` file per `k`,
- `05_compare_spinqit_vs_qasm2.py`: verify that the export preserves the logical circuit structure,
- `06_ibm_job_to_json.py`: convert IBM Runtime job outputs into JSON artifacts ready for postprocessing.

---

## 3. Exporting IBM Composer-compatible OpenQASM 2.0

Typical usage:

```bash
python scripts/04_export_qasm2.py --gfunc "sin^2(pi*x/2)" --y 1.0 --rule midpoint --ks 0,1,2
```

or, for another integrand,

```bash
python scripts/04_export_qasm2.py --gfunc "x" --y 1.0 --rule midpoint --ks 0,1,2
```

This generates a directory such as:

```text
artifacts/qasm2/qasm2_ibmcomposer_sin2_pi_x_over_2_y1_midpoint_ks0-1-2_<timestamp>/
```

containing:

- one `.qasm` file for each value of `k`,
- one `metadata.json` file recording the export parameters.

Typical output files:

```text
..._k0.qasm
..._k1.qasm
..._k2.qasm
..._metadata.json
```

---

## 4. What each exported circuit represents

Each exported `.qasm` file corresponds to a **single** amplification index `k`.

Its logical content is:

1. prepare the state with `A`,
2. apply the QAE iterate `Q` exactly `k` times,
3. measure all qubits.

Thus,

\[
\text{circuit}(k)=Q^k A\lvert 000\rangle.
\]

This is the correct object to run in Composer or IBM Runtime, because MLAE combines the outcome statistics of several such circuits classically.

---

## 5. Structural validation of the exported QASM

Before running a campaign, validate that the export preserves the logical SpinQit structure.

Example:

```bash
python scripts/05_compare_spinqit_vs_qasm2.py \
  --qasm-dir artifacts/qasm2/qasm2_ibmcomposer_sin2_pi_x_over_2_y1_midpoint_ks0-1-2_<timestamp> \
  --gfunc "sin^2(pi*x/2)" \
  --y 1.0 \
  --rule midpoint \
  --write-report
```

This checks that the exported circuit matches the expected ordering of:

- initial `A`,
- `S_{\psi_0}`,
- `A^\dagger`,
- `S_0`,
- repeated `Q` blocks,
- final measurements.

It also writes a JSON report, typically:

```text
artifacts/qasm2/.../comparison_report.json
```

---

## 6. Importing into IBM Quantum Composer

Each exported `.qasm` file can be opened in IBM Quantum Composer.

Recommended workflow:

1. open Composer,
2. load or paste the content of one `.qasm` file,
3. verify that the circuit diagram renders correctly,
4. run the circuit in simulator first,
5. then execute on hardware if desired,
6. repeat for each value of `k`.

For MLAE, remember that **each `k` is a separate circuit**.  
Composer executes circuits individually; the estimator is assembled later outside Composer.

---

## 7. Recovering IBM Runtime jobs

If the circuit is run through IBM Runtime and you know the job ID, the following pattern retrieves the job:

```python
from qiskit_ibm_runtime import QiskitRuntimeService

service = QiskitRuntimeService(
    channel="ibm_quantum_platform",
    token="YOUR_IBM_QUANTUM_TOKEN",
    instance="YOUR_INSTANCE_CRN",
)

job = service.job("YOUR_JOB_ID")
result = job.result()
print(result)
```

If no account has been saved locally for `ibm_quantum_platform`, then `token=...` must be provided explicitly or the account must first be saved with `QiskitRuntimeService.save_account(...)`.

---

## 8. Important difference from some backend wrappers

IBM Runtime results may not come back as a simple pre-aggregated dictionary of counts.

In the validated workflow here, the downloaded IBM result contained:

- a classified measurement payload,
- encoded as compressed/base64 data,
- representing a boolean matrix of shape `(shots, nbits)`.

For the present 3-qubit circuits, that means a matrix of shape:

```text
(shots, 3)
```

So the IBM path explicitly requires:

1. decode the boolean matrix,
2. reconstruct counts,
3. fix the bitstring convention,
4. extract the ancilla marginal,
5. write a normalized JSON artifact for postprocessing.

This is one of the main practical differences relative to some repository wrappers, where counts or normalized probability dictionaries may already be returned directly.

---

## 9. Converting IBM job outputs to repository JSON

Use `scripts/06_ibm_job_to_json.py` to convert a downloaded IBM job into a repository-friendly JSON artifact.

### 9.1 Generic usage

```bash
python scripts/06_ibm_job_to_json.py \
  --info artifacts/qasm2/job-<JOBID>-info.json \
  --result artifacts/qasm2/job-<JOBID>-result.json \
  --out artifacts/qasm2/qae_k0_ibm_backend.json \
  --ancilla-bit 2 \
  --bitstring-order qiskit
```

If desired, `k` can be passed explicitly:

```bash
python scripts/06_ibm_job_to_json.py \
  --info artifacts/qasm2/job-<JOBID>-info.json \
  --result artifacts/qasm2/job-<JOBID>-result.json \
  --out artifacts/qasm2/qae_k1_ibm_backend.json \
  --k 1 \
  --ancilla-bit 2 \
  --bitstring-order qiskit
```

### 9.2 Validated example for `k=0`

The following command was used in the validated IBM workflow for the `k=0` circuit:

```bash
python scripts/06_ibm_job_to_json.py \
  --info job-d79b8v0eecps73d82ltg-info.json \
  --result job-d79b8v0eecps73d82ltg-result.json \
  --out artifacts/ibm_jobs/qae_k0_ibm_kingston.json \
  --k 0 \
  --ancilla-bit 2 \
  --bitstring-order qiskit
```

This produces a postprocessing JSON artifact containing:

- job metadata,
- reconstructed counts,
- reconstructed probabilities,
- counts in both `c012` and Qiskit-style bitstring orderings,
- one-bit marginals,
- ancilla marginal,
- index-register marginal excluding the ancilla.

### 9.3 Interpreting the ancilla bit

In this repository's IBM workflow, the qubit-to-classical mapping is:

- `q[0] -> c[0]`
- `q[1] -> c[1]`
- `q[2] -> c[2]`

and the ancilla is `q[2]`, so the correct choice is:

```text
--ancilla-bit 2
```

The exported JSON then records the ancilla marginal explicitly as:

```text
derived.ancilla_marginal
```

which is the quantity used to estimate the amplitude and, for `k=0`, the discretized integral.

---

## 10. Recommended directory layout for IBM jobs

A practical repository layout is:

```text
artifacts/
  qasm2/
    qasm2_ibmcomposer_<...>/
      ..._k0.qasm
      ..._k1.qasm
      ..._k2.qasm
      ..._metadata.json
      comparison_report.json
  ibm_jobs/
    job-<JOBID>-info.json
    job-<JOBID>-result.json
    qae_k0_ibm_kingston.json
    qae_k1_ibm_kingston.json
    qae_k2_ibm_kingston.json
```

This separation keeps the exported circuits apart from the recovered IBM job artifacts and the normalized postprocessing JSON files.

---

## 11. Reading `k=0`, `k=1`, `k=2` for MLAE

After conversion with `06_ibm_job_to_json.py`, the key quantity for each job is:

```text
derived.ancilla_marginal.p1
```

That is the empirical estimate of the success probability:

\[
\hat p_k = P(\text{ancilla}=1 \mid k).
\]

For standard amplitude estimation notation,

\[
a = \sin^2\theta,
\qquad
p_k = \sin^2((2k+1)\theta).
\]

Thus:

- `k=0` gives the direct success probability `a`,
- `k=1` gives the transformed probability `p_1`,
- `k=2` gives the transformed probability `p_2`.

These are the data that must later be merged and passed to a classical MLAE estimator.

---

## 12. Important special case: integrands with value `a = 1/2`

For the validated example

\[
g(x)=\sin^2\!\left(\frac{\pi x}{2}\right),
\]

with `y=1.0`, 2 index qubits, and midpoint discretization, the encoded amplitude is exactly

\[
a = \frac12.
\]

In that case,

\[
\theta = \frac{\pi}{4},
\qquad
p_k = \sin^2((2k+1)\theta)=\frac12
\quad\text{for all }k.
\]

So, for this specific integrand, the ideal values of `k=0`, `k=1`, and `k=2` are all the same.

This means that the example is excellent for validating the export and execution pipeline, but it is **not** ideal for demonstrating visible amplitude amplification across `k` values.

---

## 13. Relation to Triangulum workflows

The mathematical target is the same as in the Triangulum experiments: estimate the ancilla success probability corresponding to the encoded discretized integral.

The main practical differences are:

- IBM Runtime may return raw classified measurement payloads rather than already aggregated counts,
- bitstring conventions must be made explicit during postprocessing,
- ancilla extraction is handled through the JSON conversion step rather than repository-specific wrappers.

So the estimator is conceptually the same, but the IBM path requires a slightly more explicit data-decoding layer.

---

## 14. Recommended next step after collecting `k=0,1,2`

Once the three JSON artifacts exist, the next step is to merge them into a single MLAE-ready artifact and then run the classical estimator using the ancilla probabilities:

\[
\hat p_0,\hat p_1,\hat p_2.
\]

That postprocessing stage remains outside IBM Composer and outside IBM Runtime; it belongs in the repository's classical analysis pipeline.

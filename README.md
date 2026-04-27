# Efficient State Preparation for Quantum Amplitude Estimation on SpinQ Triangulum (SpinQit)

## Abstract

This repository provides an academic-grade, reproducible implementation of a hardware-oriented Quantum Amplitude Estimation (QAE) workflow using **SpinQit**, targeting execution on **SpinQ Triangulum** (3-qubit NMR QPU) and **IBM Kingston** (superconducting QPU via Qiskit Runtime). The implementation follows the core strategy of efficient state preparation for QAE applied to a **numerical integration** task: a function is encoded into the amplitude of an ancilla qubit via a shallow state-preparation operator $A$, and the target probability is estimated using a **maximum-likelihood, QAE-without-QPE** approach (MLAE-style).

The codebase includes a simulator path, a Triangulum backend path, and an IBM Kingston backend path, together with structured experimental outputs for quantitative analysis. This version of the repository adopts a **dual integrand interface**:

- `--gfunc` for **official, reproducible benchmark functions**;
- `--expr` for **direct exploratory experiments** with custom expressions.

To guarantee consistency across scripts and outputs, all integrand logic is centralized in:

- `src/qae/integrands.py`

and all JSON/CSV outputs record both:

- `gfunc`
- `expr`

for complete traceability.

---

## Scope and Contributions

The repository focuses on a minimal, experimentally viable instantiation of QAE under tight hardware constraints (3 qubits, limited circuit depth), with the following contributions:

1. **Triangulum-compatible state preparation** $A$ for numerical quadrature, using a small grid (2 index qubits) and one ancilla qubit whose measurement probability encodes the integrand value.
2. **Shallow QAE estimation** via repeated execution of circuits $Q^k A\lvert 0\rangle$ for a small set of amplification indices $k$, followed by **classical maximum likelihood estimation** of the amplitude parameter.
3. A **reproducible experimental pipeline** with simulator runs, Triangulum runs, structured outputs (JSON/CSV), and a dedicated affine-diagnostic script for screening functions before hardware execution.
4. A **depth-constrained hardware implementation** for Triangulum, where the original pattern-controlled version of $A$ is replaced by a compressed affine-angle construction whenever the induced angle table admits such compression.
5. A **pandas-free execution and summarization workflow**, including simulator runs, Triangulum runs, postprocessing utilities, and a reusable three-rule campaign driver.
6. A **centralized integrand layer** supporting both official named functions and arbitrary custom expressions.
7. **IBM Kingston superconducting hardware experiments** for the three benchmark functions $g_0$, $g_1$, $g_2$, validating the angle-structure hierarchy $\mathcal{G}_n^{(d)}$ on a second hardware platform.

---

## Methodological Overview

### Numerical integration as amplitude estimation

We consider integrals of the form

$$I(y)=\int_0^y g(x)\,dx,\qquad y\in[0,1].$$

We discretize $[0,y]$ with $2^n$ points (here $n=2$, i.e. 4 midpoints to fit in Triangulum). Using a uniform superposition over grid indices and controlled single-qubit rotations on an ancilla, the state-preparation operator $A$ is constructed so that

$$a:=\Pr(\text{ancilla}=1\ \text{after }A\lvert 0\rangle)\approx \frac{1}{2^n}\sum_{i=0}^{2^n-1} g(x_i),$$

yielding the estimator $I(y)\approx y\,a$ for uniform grids.

### Angle-structure hierarchy

The key theoretical object is the **angle-structure hierarchy** $\mathcal{G}_n^{(d)}$, which classifies state-preparation operators by the multilinear degree $d$ of the angle map $g \mapsto \Theta_g = 2\arcsin(\sqrt{g})$ evaluated on the $n$-qubit grid. The three benchmark functions used in hardware experiments correspond to degrees $d=0,1,2$:

| Label | Function | Degree $d$ | Exact $a$ | MLAE schedule |
|-------|----------|-----------|-----------|---------------|
| $g_0$ | $g(x) = \tfrac{1}{4}$ | 0 | $\tfrac{1}{4}$ | $K=\{0,2\}$ (k=1 degenerate) |
| $g_1$ | $g(x) = \sin^2(\pi x/2)$ | 1 | $\tfrac{1}{2}$ | $K=\{0,1\}$ |
| $g_2$ | $g(x) = \sin^2(\pi x)$ | 2 | $\tfrac{1}{2}$ | $K=\{0,1\}$ |

The MLAE model is $p_k(a) = \sin^2\!\big((2k+1)\arcsin(\sqrt{a})\big)$ and the Fisher information is $I_k(a) = 4(2k+1)^2$ at $a=1/2$.

**Key structural property**: $g_0$ exhibits a Fisher degeneracy at $k=1$ ($I_1(1/4)=0$, $p_1(1/4)=1$ exactly), making $K=\{0,1\}$ unreliable; $K=\{0,2\}$ resolves this.

### QAE without quantum phase estimation (MLAE-style)

$$\hat a=\arg\max_{a\in[0,1]}\sum_{k\in\mathcal{K}} \Big[m_k\log p_k(a)+(N_k-m_k)\log(1-p_k(a))\Big].$$

---

## Repository Structure

```
spinqit-qae-triangulum/
├── src/
│   ├── qae/           state prep, integrands, reflections, Grover op, MLAE
│   └── backends/      simulator and Triangulum NMR backend wrappers
├── scripts/
│   ├── 00_check_function_affinity.py
│   ├── 01_run_mlae_sim.py
│   ├── 02_run_mlae_triangulum.py
│   ├── 03_summarize_results.py
│   ├── 04_export_qasm2.py
│   ├── 04_run_triangulum_campaign.py
│   ├── 05_compare_spinqit_vs_qasm2.py
│   ├── 06_ibm_job_to_json.py
│   ├── 08_run_ibm_g0_qiskit.py    IBM Kingston – g0 = 1/4
│   ├── 08_run_ibm_g1_qiskit.py    IBM Kingston – g1 = sin²(πx/2)
│   ├── 08_run_ibm_g2_qiskit.py    IBM Kingston – g2 = sin²(πx)
│   └── 09_analyze_ibm_results.py  MLAE analysis of IBM raw job files
├── data/
│   └── ibm_kingston/
│       ├── g0/        3 JSON result files (k=0,1,2)
│       ├── g1/        3 JSON result files (k=0,1,2)
│       └── g2/        3 JSON result files (k=0,1,2)
├── docs/
├── calibrate_bit_order.py
├── requirements.txt
└── README.md
```

---

## IBM Kingston Hardware Campaign

### Overview

In addition to the SpinQ Triangulum NMR experiments, the repository contains a complete IBM Kingston superconducting hardware campaign for the three benchmark functions $g_0$, $g_1$, $g_2$ with amplification schedule $\mathcal{K}=\{0,1,2\}$ and $N=2048$ shots per circuit. All jobs were submitted via **Qiskit Runtime API** with `optimization_level=0` to prevent transpiler gate cancellation.

### Key circuit fix: CCRy → CCX (Toffoli)

The $d=2$ circuit for $g_2$ requires a doubly-controlled $R_y(-\pi)$ gate. This is implemented as a **Toffoli gate (CCX)**, which differs from $CCR_y(-\pi)$ only by a global phase that cancels in $P(\text{ancilla}=1)$ measurements. IBM Composer's gate-fusion optimizer incorrectly cancelled CX gates in the original CCRy decomposition; the CCX replacement and `optimization_level=0` resolve this entirely.

### Bit decoding (SamplerV2 format)

IBM Kingston returns results as `BitArray` with shape `(N_shots, 1)` uint8 — each shot is an integer whose **bit index 2** (value `& 4`) is the ancilla qubit q[2]. This is distinct from the MSB of the printed bitstring.

### Results

All raw IBM job files (`*-info.json` + `*-result.json`) are archived in `data/ibm_kingston/g{0,1,2}/`. The decoded summary:

| Function | $a_\text{exact}$ | $K$ | $\hat{a}_\text{MLAE}$ | error |
|----------|-----------------|-----|-----------------------|-------|
| $g_0 = 1/4$ | 0.25 | $\{0,2\}$ | 0.2518 | $1.8\times10^{-3}$ |
| $g_1 = \sin^2(\pi x/2)$ | 0.50 | $\{0,1\}$ | 0.5009 | $9.3\times10^{-4}$ |
| $g_2 = \sin^2(\pi x)$ | 0.50 | $\{0,1\}$ | 0.5013 | $1.3\times10^{-3}$ |

**Note on $g_0$**: the $k=1$ circuit gives $p_1(1/4)=1$ exactly (Fisher degeneracy, $I_1(1/4)=0$). The IBM hardware measurement is $\hat{p}_1 = 0.909$, consistent with decoherence. MLAE $K=\{0,1\}$ is unreliable for $g_0$; $K=\{0,2\}$ gives correct results.

**Note on $g_2$ (Triangulum)**: $g_2$ circuits exceed the Triangulum line-depth limit of 60 and are not executable on the NMR hardware. IBM Kingston successfully executes all three $k$ values, confirming the angle-structure hierarchy.

### Running the IBM scripts

```bash
# Prerequisites
pip install qiskit qiskit-ibm-runtime
pip install qiskit-aer   # optional, for --dry-run validation

# Set token
export IBM_QUANTUM_TOKEN="your_token_here"

# Dry-run (validates circuits, transpiles, does not submit)
python3 scripts/08_run_ibm_g1_qiskit.py --dry-run

# Submit and wait for results
python3 scripts/08_run_ibm_g0_qiskit.py --shots 2048 --ks 0 1 2 --wait
python3 scripts/08_run_ibm_g1_qiskit.py --shots 2048 --ks 0 1 2 --wait
python3 scripts/08_run_ibm_g2_qiskit.py --shots 2048 --ks 0 1 2 --wait
```

Results are saved to `data/ibm_kingston/raw/` by default. To retrieve results from completed jobs (without `--wait`):

```bash
python3 scripts/06_ibm_job_to_json.py <job_id> --out data/ibm_kingston/raw
```

### Analysing IBM results

`scripts/09_analyze_ibm_results.py` processes pairs of `*-info.json` / `*-result.json` files in the current working directory and writes CSV/LaTeX summaries:

```bash
cd data/ibm_kingston/g1          # or g0, g2
python3 ../../../scripts/09_analyze_ibm_results.py
# outputs: ibm_results_per_job_v9.csv
#          ibm_results_summary_v9.csv
#          ibm_results_summary_v9.tex
```

The script infers circuit identity (g0/g1/g2, k value) automatically from the QPY circuit name embedded in the info file; no manual labelling is required.

---

## Triangulum NMR Campaign

### Hardware constraints

- **Line-depth limit**: 60 gates. $g_2$ ($d=2$) circuits exceed this limit and are documented as non-executable on Triangulum.
- **Hardware angle offset**: $\Delta\theta \approx -0.036$ rad (NMR pulse calibration); requires hardware-level intervention to fully resolve.
- **$g_0$ bimodal MLAE**: structural degeneracy at $a=1/4$ for $k=1$ produces bimodal likelihood; observed on Triangulum and confirmed on IBM Kingston.

### Running Triangulum scripts

```bash
# Affinity check (run before hardware submission)
python -m scripts.00_check_function_affinity --gfunc "sin^2(pi*x/2)" --y 1.0 --rule midpoint

# Simulator reference
python -m scripts.01_run_mlae_sim --gfunc "sin^2(pi*x/2)" --y 1.0 --rule midpoint \
    --ks 0,1,2 --shots 4096 --ancilla-bit-index-from-right 0

# Triangulum hardware (use 02_ for d≤1 functions; 04_ bypasses affine pre-check)
python -m scripts.02_run_mlae_triangulum \
    --ip 10.30.227.5 --port 55444 --account USER --password PASSWORD \
    --gfunc "sin^2(pi*x/2)" --y 1.0 --rule midpoint --ks 0,1 --shots 1024
```

---

## Integrand Interface

### Official reproducible functions: `--gfunc`

| Label | Function |
|-------|----------|
| `"1/4"` | $g_0 = \tfrac{1}{4}$ |
| `"sin^2(pi*x/2)"` | $g_1 = \sin^2(\pi x/2)$ |
| `"sin^2(pi*x)"` | $g_2 = \sin^2(\pi x)$ |
| `"x"` | $g(x) = x$ |
| `"x^2"` | $g(x) = x^2$ |

### Exploratory custom expressions: `--expr`

```bash
python -m scripts.00_check_function_affinity --expr "cos(pi*x)**2" --y 1.0 --rule midpoint
python -m scripts.01_run_mlae_sim --expr "4*x*(1-x)" --y 1.0 --rule midpoint --ks 0,1,2 --shots 4096
```

Provide exactly one of `--gfunc` or `--expr`.

---

## Canonical Bit-Order Policy

| Item | Value |
|------|-------|
| Canonical qubit order | `q0q1q2` |
| Default index qubits | `q0`, `q1` |
| Default ancilla qubit | `q2` |
| `ancilla_bit_index_from_right` | `0` (Triangulum/simulator) |
| IBM Kingston ancilla | bit index 2 of shot integer (`value & 4`) |

Use `calibrate_bit_order.py` to verify backend-reported qubit ordering before any hardware run.

---

## Environment Setup

```bash
pip install spinqit                    # Triangulum backend
pip install qiskit qiskit-ibm-runtime  # IBM Kingston backend
pip install qiskit-aer                 # optional, for validation
pip install scipy numpy pandas         # analysis
```

A `requirements.txt` is provided. The Triangulum execution scripts are written in a `pandas`-free style.

---

## Recommended Workflow

### Triangulum path

1. Run `scripts/00_check_function_affinity.py` for the intended quadrature rule.
2. Run the simulator path (`scripts/01_run_mlae_sim.py`).
3. Submit to Triangulum only if the affinity diagnostic passes (`scripts/02_run_mlae_triangulum.py`).
4. Aggregate with `scripts/03_summarize_results.py`.

### IBM Kingston path

1. Run an `08_run_ibm_gX_qiskit.py` script with `--dry-run` to validate circuits.
2. Submit with `--shots 2048 --ks 0 1 2 --wait` (or retrieve later with `06_ibm_job_to_json.py`).
3. Analyse with `09_analyze_ibm_results.py` from the relevant `data/ibm_kingston/gX/` directory.

---

## Related Publications

This repository accompanies the paper:

> A. Falcó, F. Chinesta, D. Falcó-Pomares, *On the complexity of quantum numerical integration: an angle-structure characterization*, submitted to *Journal of Complexity*.

Circuit implementations are also related to:

- arXiv:2601.17930 — Grover–Rudolph state preparation (submitted to *AIMS Mathematics*)
- arXiv:2601.17936 — Elementary quantum gates from Lie group embeddings (submitted to *Quantum*)

---

## Migration Note

This repository replaces an earlier naming scheme (`sin2_pi`, `x2`, `parabola`, `exp_minus_x`, `sqrt_x`) with the current dual interface (`--gfunc` / `--expr`). All scripts and outputs are fully traceable via the `gfunc`/`expr` fields in JSON/CSV artifacts.

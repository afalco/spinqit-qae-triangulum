# Efficient State Preparation for Quantum Amplitude Estimation on SpinQ Triangulum (SpinQit)

## Abstract

This repository provides an academic-grade, reproducible implementation of a hardware-oriented Quantum Amplitude Estimation (QAE) workflow using **SpinQit**, targeting execution on **SpinQ Triangulum** (3-qubit NMR QPU).

The implementation follows the core strategy of efficient state preparation for QAE applied to a **numerical integration** task: a function is encoded into the amplitude of an ancilla qubit via a shallow state-preparation operator $A$, and the target probability is estimated using a **maximum-likelihood, QAE-without-QPE** approach (MLAE-style). The codebase includes both a simulator path and a Triangulum backend path, together with structured experimental outputs for quantitative analysis.

This version of the repository adopts a **dual integrand interface**:

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

---

## Methodological Overview

### Numerical integration as amplitude estimation

We consider integrals of the form

$$
I(y)=\int_0^y g(x)\,dx,\qquad y\in[0,1].
$$

We discretize $[0,y]$ with $2^n$ points (here typically $n=2$, i.e. 4 points to fit in Triangulum). Using a uniform superposition over grid indices,

$$
i\in\{0,\dots,2^n-1\},
$$

and controlled single-qubit rotations on an ancilla, the state-preparation operator $A$ is constructed so that

$$
a:=\Pr(\text{ancilla}=1\ \text{after }A\lvert 0\rangle)\approx \frac{1}{2^n}\sum_{i=0}^{2^n-1} g(x_i),
$$

yielding the estimator

$$
I(y)\approx y\,a
$$

for uniform grids.

The official benchmark family currently includes:

- $g(x)=\tfrac14$
- $g(x)=\sin^2(\pi x/2)$
- $g(x)=\sin^2(\pi x)$
- $g(x)=x$
- $g(x)=x^2$

These are accessible through `--gfunc` and are intended for reproducible studies.

### QAE without quantum phase estimation (MLAE-style)

To mitigate depth and noise sensitivity, we employ a practical QAE approach based on amplitude amplification:

$$
\lvert \psi_k\rangle = Q^k A\lvert 0\rangle,\qquad k\in\mathcal{K},
$$

with the canonical model

$$
p_k(a)=\Pr(\text{ancilla}=1\mid k)=\sin^2\big((2k+1)\theta\big),
\qquad
\theta=\arcsin(\sqrt{a}).
$$

From experimental counts $\{(m_k,N_k)\}_{k\in\mathcal{K}}$ we compute the maximum-likelihood estimate

$$
\hat a=\arg\max_{a\in[0,1]}\sum_{k\in\mathcal{K}}
\Big[m_k\log p_k(a)+(N_k-m_k)\log(1-p_k(a))\Big].
$$

For the current Triangulum implementation, the recommended hardware schedule remains

$$
\mathcal{K}=\{0,1\},
$$

because larger amplification schedules may exceed the hardware depth budget.

### Operators and reflections

- **Good-state marking**: the ancilla being in state $\lvert 1\rangle$, implemented as a single $Z$ on the ancilla qubit.
- **Reflection about $\lvert 0\cdots 0\rangle$**: implemented via an $X$-conjugated CCZ on 3 qubits.

---

## Integrand Interface

### 1. Official reproducible functions: `--gfunc`

The supported official labels are exactly:

- `"1/4"`
- `"sin^2(pi*x/2)"`
- `"sin^2(pi*x)"`
- `"x"`
- `"x^2"`

These are the functions that should be used in reproducible experiments, comparisons, reports, and papers.

### 2. Exploratory custom expressions: `--expr`

For direct experimentation, the scripts also accept:

- `--expr "..."`

where the expression is evaluated as a function of `x` using a restricted mathematical environment. Typical examples are:

```bash
python -m scripts.00_check_function_affinity --expr "cos(pi*x)**2" --y 1.0 --rule midpoint
python -m scripts.01_run_mlae_sim --expr "4*x*(1-x)" --y 1.0 --rule midpoint --ks 0,1,2 --shots 4096
```

### 3. Mutual exclusivity

All execution scripts use the same rule:

- provide **exactly one** of `--gfunc` or `--expr`.

This is enforced to avoid ambiguity in provenance and in downstream summaries.

### 4. Traceability in outputs

All JSON/CSV outputs record both fields:

- `gfunc`
- `expr`

with one of them equal to `null` depending on the selected mode. This makes all runs fully auditable and easy to summarize.

---

## Hardware Design Assumptions

The repository is not intended as a generic black-box integration engine for arbitrary functions on Triangulum.

Its current hardware-oriented design assumes the following practical conditions.

### 1. Bounded range

The ancilla encoding is based on amplitudes, so the target function should satisfy

$$
0\le g(x)\le 1
\qquad \text{for }x\in[0,1].
$$

This allows us to define rotation angles through

$$
\theta(x)=2\arcsin\big(\sqrt{g(x)}\big),
$$

so that the ancilla measurement probability reproduces the desired value.

### 2. Small-grid compatibility

The present Triangulum implementation uses only two index qubits, hence four quadrature nodes. Therefore, the relevant object for hardware execution is not just the continuous function itself, but the induced four-angle table

$$
\{\theta_i\}_{i=0}^{3}.
$$

### 3. Hardware-friendly angle structure

Because of the Triangulum line-depth limit, the most suitable functions are those for which the induced angle table can be implemented with a very shallow circuit.

In particular, the hardware path is designed for functions whose discretized angles on the 2-qubit grid are exactly, or very nearly, of the affine form

$$
\theta(b_0,b_1)=c_0+c_1 b_0+c_2 b_1,
$$

where $b_0,b_1\in\{0,1\}$ are the index bits.

For this class, the state-preparation operator $A$ can be compressed into:

- Hadamards on the index register,
- one single-qubit $R_y$ on the ancilla,
- and a small number of singly controlled $R_y$ gates.

This is the key reason why the current implementation is experimentally viable on Triangulum.

---

## Function Classification Under Current Constraints

The repository is best suited to:

- benchmark functions with values in $[0,1]$;
- functions whose discretized angle table is affine or nearly affine on the 4-point grid;
- shallow numerical-integration demonstrations under strict hardware depth constraints;
- comparative studies of quadrature rule, shot budget, and reduced MLAE schedules.

A practical classification for the current official functions is the following.

| Function | `--gfunc` label | Exact integral on $[0,1]$ | Values in $[0,1]$ | Simulator | Triangulum hardware |
|---|---|---:|:---:|:---:|:---:|
| $\tfrac14$ | `"1/4"` | $\tfrac14$ | Yes | Yes | Yes |
| $\sin^2(\pi x/2)$ | `"sin^2(pi*x/2)"` | $\tfrac12$ | Yes | Yes | Yes |
| $\sin^2(\pi x)$ | `"sin^2(pi*x)"` | $\tfrac12$ | Yes | Yes | Yes |
| $x$ | `"x"` | $\tfrac12$ | Yes | Yes | rule-dependent |
| $x^2$ | `"x^2"` | $\tfrac13$ | Yes | Yes | generally simulation-first |

This classification should always be interpreted **rule by rule**. In particular, a function may be affine-friendly for one quadrature rule and not for another, so the dedicated diagnostic script should be used before attempting hardware execution.

---

## Centralized Integrand Logic

All integrand-related functionality is centralized in:

- `src/qae/integrands.py`

This module is responsible for:

- official function labels;
- expression evaluation for `--expr`;
- integrand value evaluation;
- conversion from values to rotation angles;
- exact integrals when available;
- integrand labels and output-safe slugs.

The state-preparation layer in:

- `src/qae/state_prep.py`

uses this integrand module rather than embedding function-specific logic directly inside the circuit-building code.

This separation is intentional:

- `integrands.py` handles the **mathematical definition of the integrand**;
- `state_prep.py` handles the **quantum encoding of the induced angle table**.

---

## Affinity Diagnostic Script

The repository includes a dedicated screening utility:

- `scripts/00_check_function_affinity.py`

This script evaluates a candidate integrand on the 4-point quadrature grid, computes the induced angle table, fits the affine model

$$
\theta(b_0,b_1)=c_0+c_1 b_0+c_2 b_1,
$$

and reports:

- the quadrature nodes;
- the values $g(x_i)$;
- the angles $\theta_i$;
- the affine-fit coefficients;
- the residual;
- and a practical recommendation for simulation or hardware.

Typical usage with official functions:

```bash
python -m scripts.00_check_function_affinity --gfunc "1/4" --y 1.0 --rule midpoint
python -m scripts.00_check_function_affinity --gfunc "sin^2(pi*x/2)" --y 1.0 --rule left
python -m scripts.00_check_function_affinity --gfunc "sin^2(pi*x)" --y 1.0 --rule midpoint
python -m scripts.00_check_function_affinity --gfunc "x" --y 1.0 --rule midpoint
python -m scripts.00_check_function_affinity --gfunc "x^2" --y 1.0 --rule midpoint
```

Typical usage with custom expressions:

```bash
python -m scripts.00_check_function_affinity --expr "cos(pi*x)**2" --y 1.0 --rule midpoint
python -m scripts.00_check_function_affinity --expr "4*x*(1-x)" --y 1.0 --rule midpoint
```

The intended workflow is:

1. run the affinity diagnostic first;
2. check whether the angle table is affine-friendly for the intended rule;
3. only then attempt Triangulum hardware execution.

---

## Repository Structure

- `src/qae/`: state preparation, integrands, reflections, Grover operator, MLAE circuits, and post-processing.
- `src/backends/`: simulator and Triangulum (NMR) backend wrappers.
- `scripts/`: end-to-end runnable experiments and summarization utilities.
- `data/`: raw and processed experimental outputs.
- `docs/`: experimental notes and methodological context.

The main runnable scripts are:

- `scripts/00_check_function_affinity.py`
- `scripts/01_run_mlae_sim.py`
- `scripts/02_run_mlae_triangulum.py`
- `scripts/03_summarize_results.py`
- `scripts/04_run_triangulum_campaign.py`

---

## Main Experimental Scripts

### 1. Affinity diagnostic

Check whether a function is a plausible Triangulum candidate.

```bash
python -m scripts.00_check_function_affinity --gfunc "sin^2(pi*x)" --y 1.0 --rule midpoint
```

or

```bash
python -m scripts.00_check_function_affinity --expr "cos(pi*x)**2" --y 1.0 --rule midpoint
```

### 2. Simulator

Run a reference simulation.

```bash
python -m scripts.01_run_mlae_sim --gfunc "x^2" --y 1.0 --rule midpoint --ks 0,1,2 --shots 4096 --ancilla-bit-index-from-right 0
```

or

```bash
python -m scripts.01_run_mlae_sim --expr "4*x*(1-x)" --y 1.0 --rule midpoint --ks 0,1,2 --shots 4096 --ancilla-bit-index-from-right 0
```

### 3. Triangulum hardware

Run a reduced hardware experiment.

```bash
python -m scripts.02_run_mlae_triangulum --ip 10.30.227.5 --port 55444 --account USER --password PASSWORD --gfunc "sin^2(pi*x)" --y 1.0 --rule midpoint --ks 0,1 --shots 1024
```

or, for exploratory hardware tests,

```bash
python -m scripts.02_run_mlae_triangulum --ip 10.30.227.5 --port 55444 --account USER --password PASSWORD --expr "cos(pi*x)**2" --y 1.0 --rule midpoint --ks 0,1 --shots 1024
```

### 4. Summarization

Aggregate raw JSON files into processed CSV summaries.

```bash
python -m scripts.03_summarize_results --rawdir data/raw --outdir data/processed
```

### 5. Full three-rule campaign

Run or reuse the complete `left` / `midpoint` / `right` campaign.

```bash
python -m scripts.04_run_triangulum_campaign --ip 10.30.227.5 --port 55444 --account USER --password PASSWORD --gfunc "sin^2(pi*x)" --y 1.0 --ks 0,1 --shots 1024
```

To recompute the campaign summary without relaunching hardware:

```bash
python -m scripts.04_run_triangulum_campaign --ip 10.30.227.5 --port 55444 --account USER --password PASSWORD --gfunc "sin^2(pi*x)" --y 1.0 --ks 0,1 --shots 1024 --reuse-existing
```

The campaign script performs a **rule-by-rule affine pre-check** before launching hardware. This means that if a function is not affine-friendly for one of the requested rules, the campaign aborts early with a specific warning.

---

## JSON/CSV Output Policy

Each execution run records enough metadata to reconstruct exactly what was launched.

In particular, the raw outputs include:

- backend information;
- quadrature rule;
- amplification schedule `ks`;
- shot count;
- `integrand_label`;
- `gfunc`;
- `expr`;
- estimated amplitudes and integrals;
- exact integral when available;
- affine-friendliness information;
- timestamps.

This makes downstream summarization fully reproducible and simplifies comparative analyses across official benchmarks and exploratory runs.

---

## Environment Setup

A standard Python environment is enough. The execution and summarization scripts are written in a `pandas`-free style.

The code is designed around:

- SpinQit circuit construction;
- simulator execution through backend wrappers;
- Triangulum execution through the NMR backend wrapper;
- backend-specific adaptation isolated in `src/backends/`.

---

## Recommended Workflow

For reliable studies, the recommended workflow is:

1. choose either an official `--gfunc` or an exploratory `--expr`;
2. run `scripts/00_check_function_affinity.py` for the intended quadrature rule;
3. run the simulator path;
4. run the Triangulum path only if the affinity diagnostic indicates that the induced angle table is hardware-friendly;
5. aggregate results with `scripts/03_summarize_results.py` or `scripts/04_run_triangulum_campaign.py`.

This preserves a clear distinction between:

- **reproducible benchmark studies**, based on `--gfunc`;
- **exploratory mathematical experiments**, based on `--expr`.

---

## Migration Note

This repository version replaces the earlier benchmark naming scheme based on labels such as:

- `sin2_pi`
- `x2`
- `parabola`
- `exp_minus_x`
- `sqrt_x`

with the current dual interface:

- official labels via `--gfunc`:
  - `"1/4"`
  - `"sin^2(pi*x/2)"`
  - `"sin^2(pi*x)"`
  - `"x"`
  - `"x^2"`
- arbitrary custom expressions via `--expr`

This change makes the repository both more reproducible and more flexible, while keeping the hardware workflow conservative and explicit.

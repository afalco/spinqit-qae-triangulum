# Efficient State Preparation for Quantum Amplitude Estimation on SpinQ Triangulum (SpinQit)

## Abstract
This repository provides an academic-grade, reproducible implementation of a hardware-oriented Quantum Amplitude Estimation (QAE) workflow using **SpinQit**, targeting execution on **SpinQ Triangulum** (3-qubit NMR QPU). The implementation follows the core strategy of *efficient state preparation for QAE* applied to a **numerical integration** task: a function is encoded into the amplitude of an ancilla qubit via a shallow state-preparation operator $A$, and the target probability is estimated using a **maximum-likelihood, QAE-without-QPE** approach (MLAE-style). The codebase includes both a simulator path and a Triangulum backend path, together with structured experimental outputs for quantitative analysis.

## Scope and Contributions
The repository focuses on a minimal, experimentally viable instantiation of QAE under tight hardware constraints (3 qubits, limited circuit depth), with the following contributions:

1. **Triangulum-compatible state preparation** $A$ for numerical quadrature, using a small grid (2 “index” qubits) and one ancilla qubit whose measurement probability encodes the integrand value.
2. **Shallow QAE estimation** via repeated execution of circuits $Q^k A |0\rangle$ for a small set of amplification indices $k$, followed by **classical maximum likelihood estimation** of the amplitude parameter.
3. A **reproducible experimental pipeline**: consistent scripts, logging, structured outputs (CSV/JSON), and a diagnostic script for screening functions before attempting hardware execution.
4. A **depth-constrained hardware implementation** for Triangulum, where the original pattern-controlled version of $A$ exceeded the device line-depth limit and was replaced by a compressed affine-angle construction enabling practical execution with $k \in \{0,1\}$.
5. A **pandas-free execution and summarization workflow**, including simulator runs, Triangulum runs, postprocessing utilities, and a reusable three-rule campaign driver.

## Methodological Overview

### Numerical integration as amplitude estimation
We consider integrals of the form

$$
I(y) = \int_0^y g(x)\,dx,\qquad y\in[0,1],
$$

and approximate them by discretizing $[0,y]$ with $2^n$ points (here typically $n=2$, i.e., 4 points to fit in Triangulum). Using a uniform superposition over grid indices

$$
i\in\{0,\dots,2^n-1\},
$$

and controlled single-qubit rotations on an ancilla, the state-preparation operator $A$ is constructed so that

$$
a := \Pr(\text{ancilla}=1\ \text{after }A|0\rangle)\approx \frac{1}{2^n}\sum_{i=0}^{2^n-1} g(x_i),
$$

yielding the estimator $I(y)\approx y\cdot a$ for uniform grids.

In the main benchmark we use

$$
g(x)=\sin^2(\pi x),
$$

so that

$$
I(1)=\int_0^1 \sin^2(\pi x)\,dx=\frac12.
$$

### QAE without quantum phase estimation (MLAE-style)
To mitigate depth and noise sensitivity, we employ a practical QAE approach based on amplitude amplification:

$$
|\psi_k\rangle = Q^k A|0\rangle,\qquad k\in\mathcal{K},
$$

with the canonical model

$$
p_k(a)=\Pr(\text{ancilla}=1\mid k)=\sin^2\!\big((2k+1)\theta\big),\qquad \theta=\arcsin(\sqrt{a}).
$$

From experimental counts $\{(m_k,N_k)\}_{k\in\mathcal{K}}$ we compute the maximum-likelihood estimate

$$
\hat a=\arg\max_{a\in[0,1]}\sum_{k\in\mathcal{K}}
\Big[m_k\log p_k(a)+(N_k-m_k)\log(1-p_k(a))\Big].
$$

For the current Triangulum implementation, the recommended hardware schedule is

$$
\mathcal{K}=\{0,1\},
$$

since the original deeper pattern-controlled implementation exceeded the hardware line-depth constraint.

### Operators and reflections
- “Good state” marking: the ancilla being $|1\rangle$, implemented as a **single $Z$** on the ancilla qubit.
- Reflection about $|0\cdots 0\rangle$: implemented via an $X$-conjugated CCZ (on 3 qubits, realized using standard decompositions with `CCX` and `H`).

## Function Class and Hardware Design Assumptions

The repository is not intended as a generic black-box integration engine for arbitrary functions on Triangulum. Its current hardware-oriented design assumes that the target integrand $g$ satisfies the following practical conditions.

### 1. Bounded range
The ancilla encoding is based on amplitudes, so the target function should satisfy

$$
0 \le g(x) \le 1 \qquad \text{for } x\in[0,1].
$$

This allows one to define rotation angles through

$$
\theta(x)=2\arcsin\!\big(\sqrt{g(x)}\big),
$$

so that the ancilla measurement probability reproduces the desired value.

### 2. Small-grid compatibility
The present Triangulum implementation uses only two index qubits, hence four quadrature nodes. Therefore, the relevant object for hardware execution is not the continuous function alone, but the four-angle table

$$
\{\theta_i\}_{i=0}^{3}
$$

obtained from the chosen quadrature rule.

### 3. Hardware-friendly angle structure
Because of the Triangulum line-depth limit, the most suitable functions are those for which the angle table can be implemented with a very shallow circuit. In particular, the hardware path is designed for functions whose discretized angles on the 2-qubit grid are exactly, or very nearly, of the affine form

$$
\theta(b_0,b_1)=c_0+c_1 b_0+c_2 b_1,
$$

where $b_0,b_1\in\{0,1\}$ are the index bits.

For this class, the state-preparation operator $A$ can be compressed into:

- Hadamards on the index register,
- one single-qubit $R_y$ on the ancilla,
- and a small number of singly controlled $R_y$ gates.

This is the key reason why the current implementation is experimentally viable on Triangulum.

### 4. Functions that are best suited to the current repository
The repository is therefore best suited to:

- benchmark functions with values in $[0,1]$,
- functions whose discretized angle table is affine or nearly affine on the 4-point grid,
- shallow numerical-integration demonstrations under strict hardware depth constraints,
- comparative studies of quadrature rule, shot budget, and reduced MLAE schedules.

The current benchmark

$$
g(x)=\sin^2(\pi x)
$$

is particularly suitable because, on the 2-qubit grid used here, its induced angles admit a compressed implementation compatible with Triangulum.

### 5. Function candidates under the current Triangulum constraints

| Function | Exact integral on $[0,1]$ | Values in $[0,1]$ | Affine-angle friendly on 4-point grid | Simulator | Triangulum hardware | Suggested label |
|---|---:|:---:|:---:|:---:|:---:|---|
| $\sin^2(\pi x)$ | $\tfrac12$ | Yes | Yes | Yes | Yes | hardware-friendly |
| $x$ | $\tfrac12$ | Yes | Yes | Yes | Yes | hardware-friendly |
| $x^2$ | $\tfrac13$ | Yes | No | Yes | No (current path) | simulation-ready |
| $4x(1-x)$ | $\tfrac23$ | Yes | No | Yes | No (current path) | simulation-ready |
| $e^{-x}$ | $1-e^{-1}$ | Yes | No | Yes | Not recommended initially | simulation-ready |
| General normalized smooth $g$ | depends on $g$ | If normalized | Not guaranteed | Yes | Case by case | simulation-ready |
| Arbitrary high-complexity $g$ | depends on $g$ | not guaranteed | No | Sometimes | No, in general | simulation-only |

This table reflects the current empirical status of the repository under the present state-preparation strategy. In particular, direct tests on Triangulum already support the classification:

- hardware-friendly: `sin2_pi`, `x`
- simulation-ready: `x2`, `parabola`
- simulation-first: `exp_minus_x`

### 6. What is currently not the main target
The present hardware workflow is not primarily designed for:

- arbitrary high-complexity functions,
- functions requiring exact multi-pattern controlled rotations with large circuit depth,
- larger quadrature grids beyond the 3-qubit Triangulum setting,
- fully generic function loading without hardware-aware compression.

Such functions can still be explored in simulation, but they may exceed the depth budget of the NMR hardware path.

## Hardware-Constrained Implementation
A key practical point of this repository is that the original exact pattern-controlled implementation of the state-preparation operator $A$ was too deep for the Triangulum hardware limit. In particular, even the $k=0$ hardware run exceeded the maximum allowed line depth when using the generic construction.

To address this, `src/qae/state_prep.py` includes a compressed affine-angle implementation for the two-index-qubit case. For the benchmark function and small quadrature grids used here, the rotation angles satisfy an affine relation in the index bits, allowing $A$ to be implemented with a much shallower sequence of:

- Hadamards on the index register,
- one single-qubit $R_y$ on the ancilla,
- and a small number of singly controlled $R_y$ gates.

This compressed construction makes the reduced MLAE hardware protocol feasible on Triangulum.

## Repository Modification Strategy for Additional Functions
The repository can be extended to additional integrands, but the recommended development strategy is to distinguish clearly between the **simulation path** and the **Triangulum hardware path**.

### Simulation path
For simulation, the natural extension is broad. Any function satisfying

$$
0 \le g(x) \le 1
$$

can be incorporated by defining its pointwise values and the corresponding angles

$$
\theta_i = 2\arcsin\!\big(\sqrt{g(x_i)}\big).
$$

This is the right setting for adding benchmark functions such as:

- $g(x)=x$,
- $g(x)=x^2$,
- $g(x)=4x(1-x)$,
- $g(x)=e^{-x}$,
- other smooth functions normalized to $[0,1]$.

### Triangulum hardware path
For hardware, new functions should be added only after checking whether their four-node angle table is compatible with a shallow compressed implementation.

A practical criterion is:

1. compute the four angles induced by the chosen quadrature rule,
2. test whether they satisfy an affine relation in the index bits,
3. if yes, use the compressed hardware implementation,
4. if not, keep the function for simulator-only studies or introduce an explicit approximation strategy.

### Recommended implementation roadmap
A clean extension of the repository would proceed as follows:

1. Add a `--gfunc` option to the simulator and Triangulum scripts.
2. Generalize `src/qae/state_prep.py` so that `_g_value` supports several named benchmark functions.
3. Record `gfunc` in all JSON/CSV outputs.
4. Mark each function in the documentation as either:
   - `hardware-friendly`,
   - `simulation-ready`,
   - or `simulation-only` under the current Triangulum constraints.
5. Add and use a small diagnostic utility that tests whether the discretized angle table is affine on the 2-qubit grid and reports a fit residual.
6. Keep the simulator path broad, but document the hardware path conservatively.

This preserves the scientific clarity of the repository: the code supports broader function classes in simulation while being explicit about what remains feasible on the actual hardware.

## Affinity Diagnostic Script
The repository includes a dedicated screening utility:

- `scripts/00_check_function_affinity.py`

This script evaluates a candidate function on the 4-point quadrature grid, computes the induced angle table, fits the affine model

$$
\theta(b_0,b_1)=c_0+c_1 b_0+c_2 b_1,
$$

and reports:

- the quadrature nodes,
- the values $g(x_i)$,
- the angles $\theta_i$,
- the affine-fit coefficients,
- the residual,
- and a practical recommendation for simulation or hardware.

Typical usage:

```powershell
python -m scripts.00_check_function_affinity --gfunc x --y 1.0 --rule midpoint
python -m scripts.00_check_function_affinity --gfunc x2 --y 1.0 --rule midpoint
python -m scripts.00_check_function_affinity --gfunc exp_minus_x --y 1.0 --rule midpoint
```

The intended workflow is to run this diagnostic first, and only attempt Triangulum hardware for functions that appear hardware-friendly under the current compression strategy.

## Implementation Notes (SpinQit)
The repository is written against SpinQit’s circuit model and backend abstractions. The current implementation uses:

- circuit construction from elementary gates,
- multi-controlled rotation handling compatible with the local SpinQit version,
- simulator execution through compile-and-execute wrappers,
- Triangulum execution through `get_nmr()` and `NMRConfig`,
- backend wrappers in `src/backends/` that isolate version-specific API differences.

The experiment is designed specifically so that all core building blocks reduce to:

- single-qubit rotations (`Ry`) and Hadamards,
- a small number of two- and three-qubit controlled operations compatible with a 3-qubit device.

## Repository Structure
- `src/qae/`: state preparation, reflections, Grover operator, MLAE circuits, and post-processing.
- `src/backends/`: simulator and Triangulum (NMR) backend wrappers.
- `scripts/`: end-to-end runnable experiments and summarization utilities.
- `data/`: raw and processed experimental outputs.
- `docs/`: experimental notes and methodological context.

In particular, the main runnable scripts are:

- `scripts/00_check_function_affinity.py`
- `scripts/01_run_mlae_sim.py`
- `scripts/02_run_mlae_triangulum.py`
- `scripts/03_summarize_results.py`
- `scripts/04_run_triangulum_campaign.py`

## Main Experimental Scripts

### Affinity diagnostic
Check whether a function is a plausible Triangulum candidate:

```powershell
python -m scripts.00_check_function_affinity --gfunc sin2_pi --y 1.0 --rule midpoint
```

### Simulator
Run a reference simulation:

```powershell
python -m scripts.01_run_mlae_sim --gfunc x2 --y 1.0 --rule midpoint --ks 0,1,2 --shots 4096 --ancilla-bit-index-from-right 0
```

### Triangulum hardware
Run a reduced hardware experiment:

```powershell
python -m scripts.02_run_mlae_triangulum --ip 10.30.227.5 --port 55444 --account USER --password PASSWORD --gfunc x --y 1.0 --rule midpoint --ks 0,1 --shots 1024
```

### Summarization
Aggregate raw JSON files into processed CSV summaries:

```powershell
python -m scripts.03_summarize_results --pattern "*.json"
```

### Full three-rule campaign
Run or reuse the complete `left` / `midpoint` / `right` campaign:

```powershell
python -m scripts.04_run_triangulum_campaign --ip 10.30.227.5 --port 55444 --account USER --password PASSWORD --gfunc sin2_pi --y 1.0 --ks 0,1 --shots 1024
```

To recompute the campaign summary without relaunching hardware:

```powershell
python -m scripts.04_run_triangulum_campaign --ip 10.30.227.5 --port 55444 --account USER --password PASSWORD --gfunc sin2_pi --y 1.0 --ks 0,1 --shots 1024 --reuse-existing
```

## Environment Setup
A standard Python environment is enough. The execution and summarization scripts are written in a `pandas`-free style.

Typical setup:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Windows PowerShell Notes
When running multiline commands in PowerShell, use the backtick character:

```powershell
python -m scripts.02_run_mlae_triangulum `
  --ip $env:SPINQ_IP `
  --port $env:SPINQ_PORT `
  --account $env:SPINQ_USER `
  --password $env:SPINQ_PASS `
  --gfunc x `
  --y 1.0 `
  --rule midpoint `
  --ks 0,1 `
  --shots 1024
```

A convenient session setup is:

```powershell
$env:SPINQ_IP="10.30.227.5"
$env:SPINQ_PORT="55444"
$env:SPINQ_USER="user1"
$env:SPINQ_PASS="YOUR_PASSWORD"
```

Important bit-ordering note:

- in the **simulator**, the current default is `--ancilla-bit-index-from-right 0`
- in the **Triangulum NMR backend**, the current working default remains `--ancilla-bit-index-from-right 2`

If results look inconsistent, calibrate the ancilla bit ordering explicitly.

## Reproducibility and Outputs
Each run produces structured outputs capturing:

- hardware/backend configuration (simulator vs NMR),
- chosen target function `gfunc`,
- chosen discretization rule (`left`, `right`, `midpoint`),
- amplification indices $\mathcal{K}$,
- shot counts and ancilla statistics per $k$,
- fitted amplitude $\hat a$ and derived integral estimate $\widehat{I}(y)$,
- exact integral when available,
- hardware-affinity metadata for the current Triangulum path.

These outputs are intended to support:

- cross-backend comparisons,
- stability analysis under varying $k$ and shot budgets,
- controlled evaluation of discretization vs estimation error,
- and explicit separation between simulation-ready and hardware-friendly function classes.

## Example Hardware Campaign Result
For the Triangulum campaign with

$$
g(x)=\sin^2(\pi x),\qquad y=1,\qquad \mathcal{K}=\{0,1\},\qquad \text{shots}=1024,
$$

the repository produced the following representative estimates:

- $I_{\text{left}} = 0.506837249$
- $I_{\text{midpoint}} = 0.500683590$
- $I_{\text{right}} = 0.499707016$

and the Simpson-style combination

$$
\widehat I_S = \frac{\widehat I_L + 4\widehat I_M + \widehat I_R}{6}
= 0.501546438.
$$

With exact value

$$
I(1)=0.5,
$$

these results show that the reduced depth-constrained protocol is experimentally viable on the 3-qubit Triangulum device.

A second direct hardware test with

$$
g(x)=x
$$

also succeeded under the same reduced schedule, whereas tests with

$$
g(x)=x^2
\qquad\text{and}\qquad
g(x)=4x(1-x)
$$

exceeded the current line-depth limit.

## Recommended Workflow

### 1. Check function affinity
```powershell
python -m scripts.00_check_function_affinity --gfunc x --y 1.0 --rule midpoint
```

### 2. Validate in simulation
```powershell
python -m scripts.01_run_mlae_sim --gfunc x --y 1.0 --rule midpoint --ks 0,1,2 --shots 4096 --ancilla-bit-index-from-right 0
```

### 3. Run a reduced Triangulum test only for hardware-friendly functions
```powershell
python -m scripts.02_run_mlae_triangulum --ip $env:SPINQ_IP --port $env:SPINQ_PORT --account $env:SPINQ_USER --password $env:SPINQ_PASS --gfunc x --y 1.0 --rule midpoint --ks 0,1 --shots 1024
```

### 4. Launch the full three-rule hardware campaign when appropriate
```powershell
python -m scripts.04_run_triangulum_campaign --ip $env:SPINQ_IP --port $env:SPINQ_PORT --account $env:SPINQ_USER --password $env:SPINQ_PASS --gfunc sin2_pi --y 1.0 --ks 0,1 --shots 1024
```

### 5. Recompute the campaign summary without relaunching hardware
```powershell
python -m scripts.04_run_triangulum_campaign --ip $env:SPINQ_IP --port $env:SPINQ_PORT --account $env:SPINQ_USER --password $env:SPINQ_PASS --gfunc sin2_pi --y 1.0 --ks 0,1 --shots 1024 --reuse-existing
```

## Troubleshooting

### `Line depth exceeds limit:60`
The original exact pattern-controlled version of $A$ may exceed the Triangulum hardware limit. Use the compressed implementation currently included in `src/qae/state_prep.py`, run `scripts.00_check_function_affinity.py` first, and restrict hardware tests to functions that are hardware-friendly under the current criterion.

### `ModuleNotFoundError: No module named 'src'`
Run the scripts from the repository root using module mode:

```powershell
python -m scripts.01_run_mlae_sim ...
```

### Inconsistent simulator estimates for new functions
Check the ancilla bit ordering. The simulator currently uses `--ancilla-bit-index-from-right 0` as working default. Using a mismatched bit index can produce apparently reasonable but incorrect estimates.

### SpinQit API differences
SpinQit versions may differ in simulator and NMR execution signatures. The wrappers in `src/backends/` are intended to isolate these differences. If needed, adapt:

- `src/backends/simulator.py`
- `src/backends/nmr_triangulum.py`

to your local SpinQit installation.

## How to Cite
If you use this repository in academic work, please cite:

- The underlying methodological reference (see `CITATION.bib`):  
  *A. Carrera Vazquez and S. Woerner, “Efficient State Preparation for Quantum Amplitude Estimation,” arXiv:2005.07711 (quant-ph), 2020.*

You may also cite this software repository (add a Zenodo DOI if you plan to archive a release).

## License
See `LICENSE` for usage terms.

## Contact / Maintainers
Maintained within the context of experimental QAE workflows for SpinQit/Triangulum execution.

For issues, please open a GitHub issue with:

- SpinQit version,
- backend (simulator or NMR),
- full configuration used,
- raw output files from `data/raw/`.

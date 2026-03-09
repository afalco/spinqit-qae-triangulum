# Efficient State Preparation for Quantum Amplitude Estimation on SpinQ Triangulum (SpinQit)

## Abstract
This repository provides an academic-grade, reproducible implementation of a hardware-oriented Quantum Amplitude Estimation (QAE) workflow using **SpinQit**, targeting execution on **SpinQ Triangulum** (3-qubit NMR QPU). The implementation follows the core strategy of *efficient state preparation for QAE* applied to a **numerical integration** task: a function is encoded into the amplitude of an ancilla qubit via a shallow state-preparation operator $A$, and the target probability is estimated using a **maximum-likelihood, QAE-without-QPE** approach (MLAE-style). The codebase includes both a simulator path and a Triangulum backend path, together with structured experimental outputs for quantitative analysis.

## Scope and Contributions
The repository focuses on a minimal, experimentally viable instantiation of QAE under tight hardware constraints (3 qubits, limited circuit depth), with the following contributions:

1. **Triangulum-compatible state preparation** $A$ for numerical quadrature, using a small grid (2 “index” qubits) and one ancilla qubit whose measurement probability encodes the integrand value.
2. **Shallow QAE estimation** via repeated execution of circuits $Q^k A |0\rangle$ for a small set of amplification indices $k$, followed by **classical maximum likelihood estimation** of the amplitude parameter.
3. A **reproducible experimental pipeline**: consistent scripts, logging, and structured outputs (CSV/JSON) for benchmarking across simulator and NMR hardware runs.
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

## Hardware-Constrained Implementation
A key practical point of this repository is that the original exact pattern-controlled implementation of the state-preparation operator $A$ was too deep for the Triangulum hardware limit. In particular, even the $k=0$ hardware run exceeded the maximum allowed line depth when using the generic construction.

To address this, `src/qae/state_prep.py` includes a compressed affine-angle implementation for the two-index-qubit case. For the benchmark function and small quadrature grids used here, the rotation angles satisfy an affine relation in the index bits, allowing $A$ to be implemented with a much shallower sequence of:

- Hadamards on the index register,
- one single-qubit $R_y$ on the ancilla,
- and a small number of singly controlled $R_y$ gates.

This compressed construction makes the reduced MLAE hardware protocol feasible on Triangulum.

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

- `scripts/01_run_mlae_sim.py`
- `scripts/02_run_mlae_triangulum.py`
- `scripts/03_summarize_results.py`
- `scripts/04_run_triangulum_campaign.py`

## Main Experimental Scripts

### Simulator
Run a reference simulation:

```powershell
python -m scripts.01_run_mlae_sim --y 1.0 --rule midpoint --ks 0,1,2 --shots 4096
```

### Triangulum hardware
Run a reduced hardware experiment:

```powershell
python -m scripts.02_run_mlae_triangulum --ip 10.30.227.5 --port 55444 --account USER --password PASSWORD --y 1.0 --rule midpoint --ks 0,1 --shots 1024
```

### Summarization
Aggregate raw JSON files into processed CSV summaries:

```powershell
python -m scripts.03_summarize_results --pattern "triangulum_*.json"
```

### Full three-rule campaign
Run or reuse the complete `left` / `midpoint` / `right` campaign:

```powershell
python -m scripts.04_run_triangulum_campaign --ip 10.30.227.5 --port 55444 --account USER --password PASSWORD --y 1.0 --ks 0,1 --shots 1024
```

To recompute the campaign summary without relaunching hardware:

```powershell
python -m scripts.04_run_triangulum_campaign --ip 10.30.227.5 --port 55444 --account USER --password PASSWORD --y 1.0 --ks 0,1 --shots 1024 --reuse-existing
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

## Reproducibility and Outputs
Each run produces structured outputs capturing:

- hardware/backend configuration (simulator vs NMR),
- chosen discretization rule (`left`, `right`, `midpoint`),
- amplification indices $\mathcal{K}$,
- shot counts and ancilla statistics per $k$,
- fitted amplitude $\hat a$ and derived integral estimate $\widehat{I}(y)$.

These outputs are intended to support:

- cross-backend comparisons,
- stability analysis under varying $k$ and shot budgets,
- controlled evaluation of discretization vs estimation error.

## Example Hardware Campaign Result
For the Triangulum campaign with

$$
y=1,\qquad \mathcal{K}=\{0,1\},\qquad \text{shots}=1024,
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

## Recommended Workflow

### 1. Validate in simulation
```powershell
python -m scripts.01_run_mlae_sim --y 1.0 --rule midpoint --ks 0,1,2 --shots 4096
```

### 2. Run a reduced Triangulum test
```powershell
python -m scripts.02_run_mlae_triangulum --ip $env:SPINQ_IP --port $env:SPINQ_PORT --account $env:SPINQ_USER --password $env:SPINQ_PASS --y 1.0 --rule midpoint --ks 0,1 --shots 1024
```

### 3. Launch the full three-rule hardware campaign
```powershell
python -m scripts.04_run_triangulum_campaign --ip $env:SPINQ_IP --port $env:SPINQ_PORT --account $env:SPINQ_USER --password $env:SPINQ_PASS --y 1.0 --ks 0,1 --shots 1024
```

### 4. Recompute the campaign summary without relaunching hardware
```powershell
python -m scripts.04_run_triangulum_campaign --ip $env:SPINQ_IP --port $env:SPINQ_PORT --account $env:SPINQ_USER --password $env:SPINQ_PASS --y 1.0 --ks 0,1 --shots 1024 --reuse-existing
```

## Troubleshooting

### `Line depth exceeds limit:60`
The original exact pattern-controlled version of $A$ may exceed the Triangulum hardware limit. Use the compressed implementation currently included in `src/qae/state_prep.py` and the reduced schedule $k \in \{0,1\}$.

### `ModuleNotFoundError: No module named 'src'`
Run the scripts from the repository root using module mode:

```powershell
python -m scripts.01_run_mlae_sim ...
```

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

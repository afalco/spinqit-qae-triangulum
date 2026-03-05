# Efficient State Preparation for Quantum Amplitude Estimation on SpinQ Triangulum (SpinQit)

## Abstract
This repository provides an academic-grade, reproducible implementation of a hardware-oriented Quantum Amplitude Estimation (QAE) workflow using **SpinQit**, targeting execution on **SpinQ Triangulum** (3-qubit NMR QPU). The implementation follows the core strategy of *efficient state preparation for QAE* applied to a **numerical integration** task: a function is encoded into the amplitude of an ancilla qubit via a shallow state-preparation operator $$A$$, and the target probability is estimated using a **maximum-likelihood, QAE-without-QPE** approach (MLAE-style). The codebase includes both a simulator path and a Triangulum backend path, together with structured experimental outputs for quantitative analysis.

## Scope and Contributions
The repository focuses on a minimal, experimentally viable instantiation of QAE under tight hardware constraints (3 qubits, limited circuit depth), with the following contributions:

1. **Triangulum-compatible state preparation** $$A$$ for numerical quadrature, using a small grid (2 “index” qubits) and one ancilla qubit whose measurement probability encodes the integrand value.
2. **Shallow QAE estimation** via repeated execution of circuits $$Q^k A |0\rangle$$ for a small set of amplification indices $$k$$, followed by **classical maximum likelihood estimation** of the amplitude parameter.
3. A **reproducible experimental pipeline**: consistent scripts, logging, and structured outputs (CSV/JSON) for benchmarking across simulator and NMR hardware runs.

## Methodological Overview

### Numerical integration as amplitude estimation
We consider integrals of the form

$$I(y) = \int_0^y g(x)\,dx,\qquad y\in[0,1],$$

and approximate them by discretizing $$[0,y]$$ with $$2^n$$ points (here typically $$n=2$$, i.e., 4 points to fit in Triangulum). Using a uniform superposition over grid indices 

$$i\in\{0,\dots,2^n-1\}$$ 

and controlled single-qubit rotations on an ancilla, the state-preparation operator $$A$$ is constructed so that

$$a := \Pr(\text{ancilla}=1\ \text{after }A|0\rangle)\approx \frac{1}{2^n}\sum_{i=0}^{2^n-1} g(x_i),$$

yielding the estimator $$I(y)\approx y\cdot a$$ for uniform grids.

### QAE without quantum phase estimation (MLAE-style)
To mitigate depth and noise sensitivity, we employ a practical QAE approach based on amplitude amplification:

$$|\psi_k\rangle = Q^k A|0\rangle,\qquad k\in\mathcal{K},$$

with the canonical model

$$p_k(a)=\Pr(\text{ancilla}=1\mid k)=\sin^2\!\big((2k+1)\theta\big),\qquad \theta=\arcsin(\sqrt{a}).$$

From experimental counts $$\{(m_k,N_k)\}_{k\in\mathcal{K}}$$ we compute the maximum-likelihood estimate

$$\hat a=\arg\max_{a\in[0,1]}\sum_{k\in\mathcal{K}}
\Big[m_k\log p_k(a)+(N_k-m_k)\log(1-p_k(a))\Big].$$

For Triangulum we recommend small sets such as $$\mathcal{K}=\{0,1,2\}$$ to keep circuits shallow.

### Operators and reflections
- “Good state” marking: the ancilla being $$|1\rangle$$, implemented as a **single $$Z$$** on the ancilla qubit.
- Reflection about $$|0\cdots 0\rangle$$: implemented via an $X$-conjugated CCZ (on 3 qubits, realized using standard decompositions with `CCX` and `H`).

## Implementation Notes (SpinQit)
The repository is written against SpinQit’s circuit model and gate abstractions:
- construction of circuits from elementary gates,
- creation of controlled gates via `ControlledGate`,
- definition/inversion of composite gates via `GateBuilder` and `InverseBuilder`,
- execution on Triangulum via `get_nmr()` and `NMRConfig`.

The experiment is designed specifically so that all core building blocks reduce to:
- single-qubit rotations (`Ry`) and Hadamards,
- a small number of two- and three-qubit controlled operations compatible with a 3-qubit device.

## Repository Structure
- `src/qae/`: state preparation, reflections, Grover operator, MLAE circuits, and post-processing.
- `src/backends/`: simulator and Triangulum (NMR) backend wrappers.
- `scripts/`: end-to-end runnable experiments and summarization utilities.
- `data/`: raw and processed experimental outputs.
- `docs/`: experimental notes and methodological context.

## Reproducibility and Outputs
Each run produces structured outputs capturing:
- hardware/backend configuration (simulator vs NMR),
- chosen discretization rule (left/right/midpoint),
- amplification indices $$\mathcal{K}$$,
- shot counts and ancilla statistics per $$k$$,
- fitted amplitude $$\hat a$$ and derived integral estimate

$$\widehat{I}(y)$$.

These outputs are intended to support:
- cross-backend comparisons,
- stability analysis under varying $$k$$ and shot budgets,
- controlled evaluation of discretization vs estimation error.

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

# Experiment Notes: MLAE-Style QAE Numerical Integration on SpinQ Triangulum (SpinQit)

## Purpose
These notes document the experimental design implemented in this repository: a Triangulum-compatible (3-qubit) realization of a hardware-oriented Quantum Amplitude Estimation (QAE) workflow for numerical integration, based on the efficient state-preparation strategy of Carrera Vazquez & Woerner (arXiv:2005.07711).

The goal is to estimate an integral
$$
I(y)=\int_0^y g(x)\,dx,\qquad y\in[0,1],
$$
by encoding function values into an ancilla amplitude via a shallow operator $$A$$ and estimating the ancilla probability using a maximum-likelihood (MLAE-style) procedure.

---

## Hardware Mapping (Triangulum: 3 qubits)
We assume a 3-qubit register:
- **Index qubits**: $$q_0,q_1$$ represent $$i\in\{0,1,2,3\}$$ (uniform discretization grid).
- **Ancilla qubit**: $$q_2$$ is measured; the event $$q_2=1$$ defines the “good” outcome.

The state-preparation operator $$A$$ is constructed so that
$$
a := \Pr(q_2=1 \text{ after } A|000\rangle)\approx \frac{1}{2^n}\sum_{i=0}^{2^n-1} g(x_i),
$$
and for a uniform grid on $$[0,y]$$ we use
$$
\widehat{I}(y) \approx y\cdot \hat a.
$$

---

## Discretization / Quadrature Rules
We discretize $$[0,y]$$ with $$2^n$$ points (Triangulum: typically $$n=2$$, i.e., 4 points). Sampling points $$x_i$$ are defined as:

- **Left rule**:
  $$
  x_i = y \cdot \frac{i}{2^n}
  $$
- **Right rule**:
  $$
  x_i = y \cdot \frac{i+1}{2^n}
  $$
- **Midpoint rule**:
  $$
  x_i = y \cdot \frac{i+\frac12}{2^n}
  $$

### Simpson-type postprocessing (optional)
To reduce quadrature bias without increasing qubit count, one may combine three independent estimates:
$$
\widehat{I}_S \;=\; \frac{\widehat{I}_{\text{left}} + 4\,\widehat{I}_{\text{mid}} + \widehat{I}_{\text{right}}}{6}.
$$

This requires three separate runs (left/mid/right), each with the same MLAE estimation pipeline.

---

## Integrand and Rotation Encoding
Default integrand:
$$
g(x)=\sin^2(\pi x).
$$

For each grid point $$x_i$$ we apply a controlled single-qubit rotation on the ancilla such that
$$
\Pr(q_2=1\mid i)=g(x_i).
$$

We use the identity
$$
\sin^2\!\Big(\frac{\theta_i}{2}\Big)=\sin^2(\pi x_i),
$$
which is satisfied by choosing
$$
\theta_i = 2\pi x_i.
$$

Thus, conditioned on the index state $$|i\rangle$$, we apply $$\mathrm{Ry}(\theta_i)$$ to the ancilla.

---

## State Preparation Operator $$A$$
For $$n=2$$ index qubits, $$A$$ has the form:
1. Apply Hadamards on index qubits:
   $$H^{\otimes 2} \text{ on } (q_0,q_1).$$
2. Apply a 2-controlled rotation $$\mathrm{Ry}(\theta_i)$$ on the ancilla for each basis pattern $$|i\rangle$$.

### Implementation pattern in SpinQit
To condition on a specific bitstring $$b\in\{0,1\}^2$$, we implement:
- apply $$X$$ on those control qubits where $$b_j=0$$ (turning the condition into “all ones”),
- apply a doubly-controlled rotation (nested `ControlledGate` wrapping),
- undo the $$X$$ flips.

This avoids requiring an explicit multiplexor and is viable for 2 controls.

---

## Amplitude Amplification and the $$Q$$ Operator
We define “good” states as those with ancilla $$|1\rangle$$. The standard amplitude amplification operator is
$$
Q = A\,S_0\,A^\dagger\,S_{\psi_0},
$$
where:

- $$S_{\psi_0}$$ marks good states:
  - implemented as $$Z$$ on the ancilla $$q_2$$.
- $$S_0$$ is the reflection about $$|000\rangle$$:
  $$
  S_0 = I - 2|000\rangle\langle 000|.
  $$

### Practical construction of $$S_0$$ on 3 qubits
A common construction is:
1. Apply $$X$$ on all qubits.
2. Apply $$\mathrm{CCZ}$$ on $$(q_0,q_1,q_2)$$.
3. Apply $$X$$ on all qubits.

With 3 qubits, $$\mathrm{CCZ}$$ can be realized using a Toffoli (`CCX`) and Hadamards on the target:
$$
\mathrm{CCZ}(q_0,q_1,q_2) = H(q_2)\,\mathrm{CCX}(q_0,q_1\to q_2)\,H(q_2).
$$

---

## MLAE-Style Estimation (No QPE)
To reduce depth and improve robustness on NMR hardware, we avoid QPE-based QAE and instead use an MLAE-style likelihood fit:

For amplification indices $$k\in\mathcal{K}$$ we prepare
$$
|\psi_k\rangle = Q^k A|000\rangle,
$$
measure the ancilla, and estimate
$$
p_k = \Pr(q_2=1\mid k).
$$

Under the ideal model,
$$
p_k(a)=\sin^2\!\big((2k+1)\theta\big),\qquad \theta=\arcsin(\sqrt{a}).
$$

Given observed successes $$m_k$$ out of $$N_k$$ shots, we compute
$$
\hat a=\arg\max_{a\in[0,1]}\sum_{k\in\mathcal{K}}
\Big[m_k\log p_k(a)+(N_k-m_k)\log(1-p_k(a))\Big].
$$

### Recommended settings for Triangulum
- $$n=2$$ (4 grid points, 2 index qubits).
- $$\mathcal{K}=\{0,1,2\}$$ (keeps circuits shallow).
- Start with $$y=1$$ (exact integral for $$\sin^2(\pi x)$$ is $$1/2$$) or $$y=1/2$$ (exact integral $$1/4$$).

Note: With 4 points, discretization error dominates, so comparisons should be made against the *corresponding quadrature reference* as well as the exact continuous value.

---

## Bitstring Ordering (Important Practical Note)
SpinQit backends may return measurement outcomes with differing endianness conventions. This affects which bit corresponds to the ancilla in the returned bitstring counts.

The scripts expose an option:
- `--ancilla-bit-index-from-right`

where `0` means “rightmost bit”, `1` means “second from right”, etc.

### Suggested calibration
Run a simple circuit that flips only the ancilla and confirm which bit toggles in the returned counts. Then set `--ancilla-bit-index-from-right` accordingly.

---

## Output Files and Interpretation
Each run produces:
- a JSON record in `data/raw/` storing:
  - backend config (simulator / NMR),
  - parameters $$y$$, rule, $$\mathcal{K}$$, shots,
  - raw counts per $$k$$,
  - estimated $$\hat a$$ and $$\widehat{I}(y)$$.
- a CSV summary (one row per $$k$$) for quick plotting/aggregation.

The summarization script consolidates all JSON runs into:
- `data/processed/summary_runs.csv` (one row per run),
- `data/processed/summary_by_k.csv` (one row per run and per $$k$$).

---

## Reference
Carrera Vazquez, A., and Woerner, S.
*Efficient State Preparation for Quantum Amplitude Estimation*.
arXiv:2005.07711 (quant-ph), 2020.

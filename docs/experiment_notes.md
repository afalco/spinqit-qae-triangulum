# Experiment Notes

## Purpose

This repository implements a compact MLAE-style quantum amplitude estimation workflow for numerical integration on the SpinQ Triangulum 3-qubit NMR device and on the SpinQit simulator.

The current version supports two complementary ways of specifying the integrand:

- `--gfunc` for official, reproducible benchmark functions
- `--expr` for direct exploratory experimentation with user-defined expressions

Exactly one of these options must be provided in the main scripts.

---

## Integrand model

All integrand logic is centralized in:

```text
src/qae/integrands.py
```

This module is responsible for:

- the official list of reproducible benchmark functions
- evaluation of custom expressions
- conversion from function values to rotation angles
- exact integrals when closed forms are available
- human-readable labels and filename-friendly slugs

### Official benchmark functions

The current official `--gfunc` choices are:

- `"1/4"`
- `"sin^2(pi*x/2)"`
- `"sin^2(pi*x)"`
- `"x"`
- `"x^2"`

These are the supported reproducible cases for simulation, hardware runs, and campaign execution.

### Custom expressions

For exploratory tests, the repository also accepts:

```bash
--expr "..."
```

Examples:

```bash
--expr "cos(pi*x)**2"
--expr "4*x*(1-x)"
--expr "sin(pi*x/3)**2"
```

These expressions are evaluated in a restricted mathematical environment.

---

## Traceability

For reproducibility and auditability, raw outputs store both:

- `gfunc`
- `expr`

in JSON and CSV artifacts.

This means:

- official runs keep track of which named benchmark was used
- exploratory runs preserve the exact expression string used to generate the data

---

## State-preparation logic

State-preparation is built from quadrature samples on the chosen grid and encoded through controlled `Ry` rotations on the ancilla.

The relevant module is:

```text
src/qae/state_prep.py
```

For a sample value `v = g(x_i)` in `[0,1]`, the rotation angle is chosen so that

```math
\sin^2(\theta_i/2) = v.
```

Hence the generic rule is

```math
\theta_i = 2\arcsin(\sqrt{v}).
```

For some official functions, exact closed-form affine angle formulas are used when available:

- `1/4`
- `sin^2(pi*x/2)`
- `sin^2(pi*x)`

This preserves the hardware-friendly affine structure whenever possible.

---

## Affinity diagnostic

Before launching hardware experiments, the recommended first step is:

```bash
python -m scripts.00_check_function_affinity --gfunc "sin^2(pi*x)" --y 1.0 --rule midpoint
```

or for an exploratory case:

```bash
python -m scripts.00_check_function_affinity --expr "cos(pi*x)**2" --y 1.0 --rule midpoint
```

This diagnostic checks whether the induced 4-point angle table is exactly affine for the current 2-index-qubit encoding.

Typical classifications include:

- `hardware-friendly`
- `candidate (very close to affine)`
- `simulation-ready / likely too deep for current Triangulum path`

---

## Simulator workflow

Main simulator entry point:

```bash
python -m scripts.01_run_mlae_sim --gfunc "x^2" --y 1.0 --rule midpoint --ks 0,1,2 --shots 4096
```

Exploratory example:

```bash
python -m scripts.01_run_mlae_sim --expr "4*x*(1-x)" --y 1.0 --rule midpoint --ks 0,1,2 --shots 4096
```

This writes per-run JSON and CSV artifacts in `data/raw/`.

---

## Triangulum workflow

Main hardware entry point:

```bash
python -m scripts.02_run_mlae_triangulum \
  --ip <IP> \
  --account <ACCOUNT> \
  --password <PASSWORD> \
  --gfunc "sin^2(pi*x/2)" \
  --y 1.0 \
  --rule midpoint \
  --ks 0,1 \
  --shots 1024
```

Exploratory example:

```bash
python -m scripts.02_run_mlae_triangulum \
  --ip <IP> \
  --account <ACCOUNT> \
  --password <PASSWORD> \
  --expr "cos(pi*x)**2" \
  --y 1.0 \
  --rule midpoint \
  --ks 0,1 \
  --shots 1024
```

Because the current Triangulum path is depth-constrained, the affinity diagnostic is strongly recommended before running exploratory expressions on hardware.

---

## Campaign execution

Campaign script:

```bash
python -m scripts.04_run_triangulum_campaign \
  --ip <IP> \
  --account <ACCOUNT> \
  --password <PASSWORD> \
  --gfunc "sin^2(pi*x)" \
  --y 1.0 \
  --rules left,midpoint,right \
  --ks 0,1 \
  --shots 1024
```

This script is intended for affine-friendly cases across all requested rules. It aggregates the per-rule outputs and computes a Simpson-style combination when `left`, `midpoint`, and `right` are all present.

---

## Output structure

### Raw artifacts

Produced in `data/raw/`:

- one JSON file per run
- one CSV file per run

These include fields such as:

- `run_id`
- `backend`
- `integrand_label`
- `gfunc`
- `expr`
- `y`
- `rule`
- `ks`
- `shots_per_k`
- `p_hat`
- `successes`
- `a_hat`
- `I_hat`
- `exact_integral`
- `abs_error_global`
- `hardware_friendly_affine`
- `function_class`

### Processed artifacts

Produced in `data/processed/`:

- `summary_runs.csv`
- `summary_by_k.csv`
- `summary_grouped.csv`
- campaign summaries when applicable

---

## Recommended workflow

For a new integrand, the most robust workflow is:

1. Run `00_check_function_affinity`
2. If the case is affine-friendly, test it on the simulator
3. Then move to Triangulum hardware execution
4. Aggregate and summarize raw outputs with `03_summarize_results`
5. Use campaign mode only when the requested rules remain hardware-friendly

---

## Migration note

Older versions of the repository used benchmark identifiers such as:

- `sin2_pi`
- `x2`
- `sqrt_x`
- `exp_minus_x`
- `parabola`

The current version replaces that scheme with:

- official reproducible functions through `--gfunc`
- direct exploratory functions through `--expr`

This makes the repo cleaner, more extensible, and easier to track experimentally.

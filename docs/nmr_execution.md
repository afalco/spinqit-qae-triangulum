# NMR Execution Manual (Triangulum / SpinQit)

This manual describes how to execute the MLAE-style QAE workflow in this repository on the **SpinQ Triangulum (3-qubit NMR QPU)** and on the **SpinQit simulator**, using the current integrand model based on `--gfunc` and `--expr`.

The present version assumes:

- a scripts-first workflow;
- explicit backend configuration;
- raw artifacts in `data/raw/`;
- processed summaries in `data/processed/`;
- centralized integrand logic in `src/qae/integrands.py`.

---

## 1. Prerequisites

### 1.1 System requirements

- Python 3.10+ recommended
- Network access (LAN/VPN) to the Triangulum device
- SpinQit installed and functional

### 1.2 Relevant repository layout

- `scripts/00_check_function_affinity.py`: affine-friendliness diagnostic for a selected integrand
- `scripts/01_run_mlae_sim.py`: simulator execution entry point
- `scripts/02_run_mlae_triangulum.py`: main Triangulum execution entry point
- `scripts/03_summarize_results.py`: summary builder for raw JSON artifacts
- `scripts/04_run_triangulum_campaign.py`: multi-rule campaign runner with affine pre-check
- `src/qae/integrands.py`: official integrands, custom expression evaluation, exact integrals, labels/slugs
- `src/qae/state_prep.py`: quadrature-to-angle encoding and state preparation
- `src/backends/nmr_triangulum.py`: NMR backend wrapper
- `data/raw/`: raw JSON and per-run CSV files
- `data/processed/`: aggregated summaries and campaign outputs

---

## 2. Integrands

Exactly one of the following must be provided in the main scripts.

### 2.1 Official reproducible cases: `--gfunc`

The current official benchmark choices are:

- `"1/4"`
- `"sin^2(pi*x/2)"`
- `"sin^2(pi*x)"`
- `"x"`
- `"x^2"`

These are the intended reproducible cases for simulation, hardware runs, and campaign execution.

### 2.2 Exploratory cases: `--expr`

For direct experimentation, you may instead pass:

```bash
--expr "..."
```

Examples:

```bash
--expr "cos(pi*x)**2"
--expr "4*x*(1-x)"
--expr "sin(pi*x/3)**2"
```

Custom expressions are evaluated in a restricted mathematical environment.

---

## 3. Environment setup

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
# On Windows PowerShell:
# .venv\Scripts\activate

pip install -U pip
pip install -r requirements.txt
```

Sanity check:

```bash
python -c "import spinqit; print('spinqit ok')"
```

---

## 4. Connectivity check

Before running any hardware experiment, verify that the device is reachable:

```bash
nc -vz -w 2 <TRIANGULUM_IP> 55444
```

Expected outcome: a successful connection report.

If this fails:

- verify LAN/VPN access,
- verify routing,
- confirm the port,
- check local firewall rules.

---

## 5. Recommended pre-screening workflow

Under the current implementation, not every function that works in simulation is suitable for direct NMR execution. The key issue is whether the induced 4-point angle table is affine-friendly on the 2-index-qubit grid.

### 5.1 Affinity diagnostic

For an official benchmark:

```bash
python -m scripts.00_check_function_affinity --gfunc "sin^2(pi*x)" --y 1.0 --rule midpoint
```

For an exploratory function:

```bash
python -m scripts.00_check_function_affinity --expr "cos(pi*x)**2" --y 1.0 --rule midpoint
```

This script classifies the current case as, for example:

- `hardware-friendly`
- `candidate (very close to affine)`
- `simulation-ready / likely too deep for current Triangulum path`

### 5.2 Simulator validation

Before sending a new configuration to hardware, validate it in the simulator:

```bash
python -m scripts.01_run_mlae_sim \
  --gfunc "x^2" \
  --y 1.0 \
  --rule midpoint \
  --ks 0,1,2 \
  --shots 4096 \
  --ancilla-bit-index-from-right 0 \
  --outdir data/raw
```

Exploratory example:

```bash
python -m scripts.01_run_mlae_sim \
  --expr "4*x*(1-x)" \
  --y 1.0 \
  --rule midpoint \
  --ks 0,1,2 \
  --shots 4096 \
  --ancilla-bit-index-from-right 0 \
  --outdir data/raw
```

---

## 6. Running on Triangulum

### 6.1 Minimal recommended hardware run

A conservative baseline configuration is:

- 2 index qubits (4-point grid)
- 1 ancilla qubit
- amplification indices `k = {0,1}`
- `rule = midpoint`
- moderate shot count

Example with an official benchmark:

```bash
python -m scripts.02_run_mlae_triangulum \
  --ip <TRIANGULUM_IP> \
  --port 55444 \
  --account <ACCOUNT> \
  --password <PASSWORD> \
  --task-name qae_mlae_demo \
  --task-desc "MLAE-style QAE numerical integration (Triangulum)" \
  --gfunc "sin^2(pi*x)" \
  --y 1.0 \
  --rule midpoint \
  --ks 0,1 \
  --shots 1024 \
  --ancilla-bit-index-from-right 2 \
  --outdir data/raw
```

Exploratory example:

```bash
python -m scripts.02_run_mlae_triangulum \
  --ip <TRIANGULUM_IP> \
  --port 55444 \
  --account <ACCOUNT> \
  --password <PASSWORD> \
  --task-name qae_mlae_expr \
  --task-desc "Exploratory MLAE-style QAE numerical integration (Triangulum)" \
  --expr "cos(pi*x)**2" \
  --y 1.0 \
  --rule midpoint \
  --ks 0,1 \
  --shots 1024 \
  --ancilla-bit-index-from-right 2 \
  --outdir data/raw
```

On success the script writes JSON and CSV artifacts and prints the estimated amplitude and integral.

---

## 7. Output artifacts

Each raw run generates two files under `data/raw/`:

1. `triangulum_*.json`
2. `triangulum_*.csv`

These artifacts retain both:

- `gfunc`
- `expr`

for traceability.

Typical JSON fields include:

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
- `mle`
- `integral`
- `exact_integral`
- `abs_error_global`
- `hardware_friendly_affine`
- `function_class`

---

## 8. Bitstring ordering

SpinQit backends may return measurement strings with different endianness conventions. This affects which bit corresponds to the ancilla.

The scripts expose:

```text
--ancilla-bit-index-from-right
```

Interpretation:

- `0` = rightmost bit
- `1` = second from right
- `2` = third from right

A common working default for Triangulum with the ancilla on qubit 2 is:

```text
--ancilla-bit-index-from-right 2
```

### 8.1 Quick calibration procedure

If the extracted probabilities appear degenerate, repeat the same command with:

- `--ancilla-bit-index-from-right 0`
- `--ancilla-bit-index-from-right 1`
- `--ancilla-bit-index-from-right 2`

and keep the setting that yields coherent `p_hat` values.

---

## 9. Campaign execution

For multi-rule experiments, use:

```bash
python -m scripts.04_run_triangulum_campaign \
  --ip <TRIANGULUM_IP> \
  --port 55444 \
  --account <ACCOUNT> \
  --password <PASSWORD> \
  --gfunc "sin^2(pi*x)" \
  --y 1.0 \
  --rules left,midpoint,right \
  --ks 0,1 \
  --shots 1024
```

This script checks affine compatibility rule by rule before sending anything to hardware. If any requested rule is not affine-friendly for the current compressed Triangulum path, the campaign aborts before launch.

To recompute a campaign summary without relaunching hardware:

```bash
python -m scripts.04_run_triangulum_campaign \
  --ip <TRIANGULUM_IP> \
  --port 55444 \
  --account <ACCOUNT> \
  --password <PASSWORD> \
  --gfunc "sin^2(pi*x)" \
  --y 1.0 \
  --rules left,midpoint,right \
  --ks 0,1 \
  --shots 1024 \
  --reuse-existing
```

When `left`, `midpoint`, and `right` are all present, the campaign summary computes the Simpson-style combination

```math
I_S = \frac{I_{\mathrm{left}} + 4I_{\mathrm{mid}} + I_{\mathrm{right}}}{6}.
```

---

## 10. Aggregating results

To summarize raw JSON artifacts into compact CSV tables:

```bash
python -m scripts.03_summarize_results --rawdir data/raw --outdir data/processed
```

This produces:

- `data/processed/summary_runs.csv`
- `data/processed/summary_by_k.csv`
- `data/processed/summary_grouped.csv`
- `data/processed/summary_manifest.json`

---

## 11. Practical recommendations

A robust workflow for a new integrand is:

1. Run `00_check_function_affinity`
2. Validate in the simulator with `01_run_mlae_sim`
3. Start shallow on hardware with `02_run_mlae_triangulum`
4. Aggregate results with `03_summarize_results`
5. Use campaign mode only when all requested rules pass the affine pre-check

For current hardware constraints, `ks = 0,1` is usually the conservative starting point.

---

## 12. Troubleshooting

### 12.1 Connection errors

Symptoms may include:

- timeouts,
- refused connection,
- transient messages such as `invalid state`.

Actions:

- re-check `nc -vz -w 2 <TRIANGULUM_IP> 55444`,
- verify LAN/VPN access,
- verify credentials,
- confirm the port.

### 12.2 `Line depth exceeds limit:60`

This indicates that the circuit exceeds the Triangulum line-depth budget.

Actions:

- run `scripts.00_check_function_affinity.py` first,
- validate in the simulator,
- keep hardware runs shallow,
- start with `--ks 0,1`,
- do not assume simulator compatibility implies hardware compatibility.

### 12.3 Degenerate counts

If counts appear nearly all-zero or all-one:

- re-check `--ancilla-bit-index-from-right`,
- reduce depth,
- reduce shots initially,
- verify device calibration status.

### 12.4 Backend API mismatch

If your local SpinQit version differs, you may need to adapt:

- `src/backends/nmr_triangulum.py::TriangulumBackend.run()`
- `src/backends/simulator.py::SimulatorBackend.run()`

The backend wrappers are intentionally isolated so that version-specific changes remain localized.

---

## 13. Reproducibility checklist

Before reporting results, record:

- SpinQit version
- backend type and task name
- full command line
- produced `data/raw/*.json`
- affinity diagnostics for new integrands
- simulator validation outputs
- processed summaries in `data/processed/`

For repeated assessments, keep multiple runs of the same configuration to quantify variability.

# NMR Execution Manual (Triangulum / SpinQit)

This manual describes how to execute the MLAE-style QAE experiment in this repository on the **SpinQ Triangulum (3-qubit NMR QPU)**, following the same operational philosophy as the Grover–Rudolph practical repository: **scripts-first execution**, explicit backend configuration, and structured outputs in `data/`.

---

## 1. Prerequisites

### 1.1 System requirements
- Python 3.10+ recommended
- Network access (LAN/VPN) to the Triangulum device
- SpinQit installed and functional

### 1.2 Repository layout (relevant parts)
- `scripts/02_run_mlae_triangulum.py`: main Triangulum execution entrypoint  
- `scripts/03_summarize_results.py`: merges raw JSON runs into CSV summaries  
- `data/raw/`: raw results (JSON + per-run CSV)  
- `data/processed/`: aggregated summaries  
- `src/backends/nmr_triangulum.py`: backend wrapper (NMRConfig + engine call)

---

## 2. Environment Setup

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate         # Windows PowerShell
```
pip install -U pip
pip install -r requirements.txt

Sanity check:

python -c "import spinqit; print('spinqit ok')"


⸻

3. Connectivity Check (Triangulum Port 55444)

Before running any experiment, verify that the device is reachable:

nc -vz -w 2 <TRIANGULUM_IP> 55444

Expected output: succeeded.

If this fails:
	•	verify you are on the correct LAN/VPN,
	•	verify routing (e.g., netstat -nr),
	•	confirm the port is correct (default is 55444),
	•	check local firewall rules.

⸻

4. Running on Triangulum (Main Command)

4.1 Minimal recommended run (baseline)

This is the reference configuration intended to work under typical hardware constraints:
	•	discretization: 2 index qubits (4 points)
	•	ancilla: 1 qubit
	•	amplification indices: k = {0,1,2}
	•	rule: midpoint
	•	y: 1.0

python scripts/02_run_mlae_triangulum.py \
  --ip <TRIANGULUM_IP> \
  --port 55444 \
  --account <USER> \
  --password <PASSWORD> \
  --task-name qae_mlae_demo \
  --task-desc "MLAE-style QAE numerical integration (Triangulum)" \
  --y 1.0 \
  --rule midpoint \
  --ks 0,1,2 \
  --shots 4096 \
  --ancilla-bit-index-from-right 2 \
  --outdir data/raw

On success the script prints:
	•	the locations of the written files,
	•	the estimated amplitude a_hat,
	•	the estimated integral I_hat.

4.2 Output artifacts

Each run generates two files under data/raw/:
	1.	triangulum_....json
Contains:
	•	backend metadata (ip/port/task),
	•	experiment parameters (y, rule, ks, shots),
	•	raw bitstring counts for each k,
	•	MLE estimate a_hat and derived I_hat.
	2.	triangulum_....csv
Flat per-k summary (one row per k) to facilitate quick plots.

⸻

5. Important Practical Issue: Bitstring Ordering

SpinQit backends may return measurement strings with different endianness conventions.
This affects which bit corresponds to the ancilla.

The scripts expose:
	•	--ancilla-bit-index-from-right

Interpretation:
	•	0 = rightmost bit
	•	1 = second from right
	•	2 = third from right (common default for 3 qubits if ancilla is qubit 2)

5.1 Quick calibration procedure

If you suspect the extracted probabilities are incorrect (e.g., p_hat always ~0 or ~1), run the same command with three settings:

python scripts/02_run_mlae_triangulum.py ... --ancilla-bit-index-from-right 0
python scripts/02_run_mlae_triangulum.py ... --ancilla-bit-index-from-right 1
python scripts/02_run_mlae_triangulum.py ... --ancilla-bit-index-from-right 2

Choose the setting that yields sensible p_hat values and coherent variation across k.

⸻

6. Recommended Experimental Workflow (Triangulum)

6.1 Step 1 — Baseline functionality

Start shallow and conservative:
	•	--ks 0,1
	•	--shots 1024

python scripts/02_run_mlae_triangulum.py \
  --ip <TRIANGULUM_IP> --port 55444 --account <USER> --password <PASSWORD> \
  --y 1.0 --rule midpoint --ks 0,1 --shots 1024 \
  --ancilla-bit-index-from-right 2 --outdir data/raw

If this works reliably, increase to:
	•	--ks 0,1,2
	•	--shots 4096

6.2 Step 2 — Validation points

Use values where the exact integral for sin^2(pi x) is known:
	•	y=1.0 gives exact I(1)=1/2
	•	y=0.5 gives exact I(1/2)=1/4

Note: with only 4 grid points, quadrature bias may be visible; compare both against:
	•	exact integral, and
	•	the corresponding quadrature reference (left/right/midpoint).

6.3 Step 3 — Optional Simpson improvement (3 runs)

Run three variants:
	•	--rule left
	•	--rule midpoint
	•	--rule right

Then combine classically:
I_S = (I_left + 4 I_mid + I_right)/6

⸻

7. Aggregating Results

To merge all raw JSON runs into two CSV summary files:

python scripts/03_summarize_results.py --indir data/raw --outdir data/processed

Outputs:
	•	data/processed/summary_runs.csv (one row per run)
	•	data/processed/summary_by_k.csv (one row per run × per k)

⸻

8. Troubleshooting

8.1 Connection errors

Symptoms:
	•	timeouts
	•	refused connection
	•	backend exceptions

Actions:
	•	re-check nc -vz <IP> 55444
	•	ensure VPN/LAN is active
	•	verify correct IP and credentials

8.2 Counts look degenerate (all 0 or all 1)

Actions:
	•	re-check --ancilla-bit-index-from-right (Section 5)
	•	reduce depth: use --ks 0,1
	•	reduce shots initially (some backends have hidden limits)
	•	confirm Triangulum calibration status (T1/T2, temperature stability)

8.3 Backend API mismatch

If SpinQit version differs, you may need to adapt:
	•	src/backends/nmr_triangulum.py::TriangulumBackend.run()
	•	src/backends/simulator.py::SimulatorBackend.run()

The wrappers are intentionally isolated so you only modify backend invocation/return parsing in one place.

⸻

9. Reproducibility Checklist (Before Reporting Results)
	•	record:
	•	SpinQit version
	•	backend type and NMR task name
	•	full command line used
	•	data/raw/*.json produced
	•	run:
	•	at least 3 repeated trials for the same configuration to assess variability
	•	keep:
	•	summary_runs.csv and summary_by_k.csv for plotting and archiving


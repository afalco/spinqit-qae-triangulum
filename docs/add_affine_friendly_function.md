# How to Add a New Affine-Friendly Function

This note explains how to extend the repository with a new function that is compatible with the current **compressed Triangulum state-preparation path**.

The key point is that, under the present 3-qubit implementation, hardware execution is feasible only when the angle table induced by the chosen quadrature rule is **affine on the 2-qubit index grid**.

---

## 1. What “affine-friendly” means

For a given rule (`left`, `midpoint`, or `right`) and a function $g(x)$ with values in $[0,1]$, the repository builds four angles

$$
\theta_i = 2\arcsin\!\big(\sqrt{g(x_i)}\big),
$$

where $x_i$ are the four quadrature nodes associated with the 2-qubit index register.

Writing the index state as

$$
(b_0,b_1)\in\{(0,0),(0,1),(1,0),(1,1)\},
$$

we say that the function is **affine-friendly for that rule** if the corresponding angle table satisfies

$$
\theta(b_0,b_1)=c_0+c_1 b_0+c_2 b_1
$$

for some coefficients $c_0,c_1,c_2$.

Equivalently, if the four angles are denoted by

$$
\theta_{00},\theta_{01},\theta_{10},\theta_{11},
$$

the affine condition is

$$
\theta_{00}+\theta_{11}=\theta_{01}+\theta_{10}.
$$

The repository measures the affine residual

$$
r = \left|\theta_{11}-(\theta_{10}+\theta_{01}-\theta_{00})\right|.
$$

A function is treated as affine-friendly when this residual is zero up to numerical tolerance.

---

## 2. Why this matters

If the angles are affine, the state-preparation operator $A$ can be implemented in compressed form using only:

- Hadamards on the two index qubits,
- one single-qubit $R_y$ on the ancilla,
- one singly controlled $R_y$ from $q_0$,
- one singly controlled $R_y$ from $q_1$.

This is shallow enough for the current Triangulum path.

If the angles are not affine, the generic pattern-controlled implementation is needed, which usually exceeds the hardware depth limit.

---

## 3. Step 1 — Check whether the new function is affine-friendly

Before modifying the codebase, test the candidate function with the diagnostic script.

### If the function is already available as `--expr`
Use:

```bash
python -m scripts.00_check_function_affinity --expr "YOUR_EXPRESSION_IN_X" --y 1.0 --rule midpoint
```

Example:

```bash
python -m scripts.00_check_function_affinity --expr "cos(pi*x)**2" --y 1.0 --rule midpoint
```

### If you want to test all rules
Run:

```bash
python -m scripts.00_check_function_affinity --expr "YOUR_EXPRESSION_IN_X" --y 1.0 --rule left
python -m scripts.00_check_function_affinity --expr "YOUR_EXPRESSION_IN_X" --y 1.0 --rule midpoint
python -m scripts.00_check_function_affinity --expr "YOUR_EXPRESSION_IN_X" --y 1.0 --rule right
```

### Interpretation
- if the function is affine-friendly only for `midpoint`, it can be used for direct midpoint hardware runs but **not** for the full three-rule campaign;
- if the function is affine-friendly for `left`, `midpoint`, and `right`, it is a candidate for the full campaign script;
- if it is not affine-friendly for the rule you want, keep it simulator-only under the current implementation.

---

## 4. Step 2 — Add the function to `src/qae/state_prep.py`

The central place to add a new named function is `src/qae/state_prep.py`.

### 4.1 Extend the `GFunc` literal
Find something like:

```python
GFunc = Literal["sin2_pi", "x", "x2", "sqrt_x", "exp_minus_x", "parabola"]
```

and add your new name, for example:

```python
GFunc = Literal["sin2_pi", "x", "x2", "sqrt_x", "exp_minus_x", "parabola", "cos2_pi"]
```

### 4.2 Implement the function in `_g_value`
Add a new branch:

```python
if gfunc == "cos2_pi":
    return math.cos(math.pi * x) ** 2
```

### 4.3 Add the exact integral if available
If `exact_integral(...)` is implemented in the same file, add the exact formula there too.

For example:

```python
if gfunc == "cos2_pi":
    return 0.5 * y + math.sin(2.0 * math.pi * y) / (4.0 * math.pi)
```

If no simple closed form is available, it is acceptable to return `None`.

---

## 5. Step 3 — Add the function to the CLI scripts

The new named function must be exposed in the scripts that accept `--gfunc`.

### Update the `GFUNC_CHOICES` list in:
- `scripts/00_check_function_affinity.py`
- `scripts/01_run_mlae_sim.py`
- `scripts/02_run_mlae_triangulum.py`
- `scripts/04_run_triangulum_campaign.py`

For example:

```python
GFUNC_CHOICES = ["sin2_pi", "x", "x2", "sqrt_x", "exp_minus_x", "parabola", "cos2_pi"]
```

---

## 6. Step 4 — Validate in simulation

Before sending the new function to hardware, validate it in the simulator.

Example:

```bash
python -m scripts.01_run_mlae_sim --gfunc cos2_pi --y 1.0 --rule midpoint --ks 0,1,2 --shots 4096 --ancilla-bit-index-from-right 0
```

Check that:

- the script runs correctly,
- the estimate is consistent with the exact integral if available,
- the stored metadata marks the function as hardware-friendly when appropriate.

---

## 7. Step 5 — Validate on Triangulum

### Midpoint-only hardware test
If the function is affine-friendly only for `midpoint`, run:

```bash
python -m scripts.02_run_mlae_triangulum --ip <TRIANGULUM_IP> --port 55444 --account <USER> --password <PASSWORD> --gfunc cos2_pi --y 1.0 --rule midpoint --ks 0,1 --shots 1024
```

### Full campaign
Only if the function is affine-friendly for all requested rules, run:

```bash
python -m scripts.04_run_triangulum_campaign --ip <TRIANGULUM_IP> --port 55444 --account <USER> --password <PASSWORD> --gfunc cos2_pi --y 1.0 --ks 0,1 --shots 1024
```

Remember that the campaign script now performs a pre-check by rule and aborts early if any requested rule is non-affine.

---

## 8. Step 6 — Update the documentation

After adding the function, update:

- `README.md`
- `docs/experimental_notes.md`
- `docs/nmr_execution_manual.md`

You should document:

1. the function definition;
2. whether it is affine-friendly for `midpoint` only or for all rules;
3. whether it is simulator-only, midpoint-hardware-friendly, or full-campaign hardware-friendly;
4. the exact integral if known.

---

## 9. Recommended classification labels

For consistency, use one of the following labels:

- `full-campaign hardware-friendly`
- `midpoint-only hardware-friendly`
- `simulation-ready`
- `simulation-first`
- `simulation-only`

Suggested interpretation:

- **full-campaign hardware-friendly**: affine-friendly for `left`, `midpoint`, and `right`
- **midpoint-only hardware-friendly**: affine-friendly for `midpoint` but not for all campaign rules
- **simulation-ready**: works well in simulation but not on the current Triangulum path
- **simulation-first**: interesting but not yet recommended for hardware
- **simulation-only**: no realistic hardware path under the current constraints

---

## 10. Minimal checklist for adding a new affine-friendly function

1. Test with `scripts/00_check_function_affinity.py`
2. Add the name to `GFunc` in `src/qae/state_prep.py`
3. Implement the function in `_g_value(...)`
4. Add `exact_integral(...)` if available
5. Add the name to all `GFUNC_CHOICES`
6. Validate with `scripts/01_run_mlae_sim.py`
7. Validate with `scripts/02_run_mlae_triangulum.py`
8. Use `scripts/04_run_triangulum_campaign.py` only if the function is affine-friendly for all requested rules
9. Update the documentation

---

## 11. Practical warning

A function being “friendly” is **rule-dependent**.

For example, under the current implementation:

- `x` is compatible with `midpoint`,
- but not with the full `left` / `midpoint` / `right` campaign.

Therefore, always evaluate affine-friendliness **for the exact rule you plan to run**.

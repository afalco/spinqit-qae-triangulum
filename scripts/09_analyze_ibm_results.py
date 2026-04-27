#!/usr/bin/env python3
"""
09_analyze_ibm_results.py
=========================
Analyse IBM Kingston MLAE campaign results.

USAGE
-----
Run this script from the directory that contains the raw IBM job files::

    cd data/ibm_kingston/g1          # or g0, g2
    python3 ../../../scripts/09_analyze_ibm_results.py

INPUT FILES (expected in the current working directory)
-------------------------------------------------------
The script scans for pairs of files matching::

    <prefix>-info.json      job metadata  (backend, shots, circuit QPY blob)
    <prefix>-result.json    job result    (SamplerV2 BitArray payload)

Both files must share the same ``<prefix>`` (e.g. the IBM job ID
``job-d7b90be5nvhs73a31jk0``).  Any number of pairs can be present;
each pair is processed as one MLAE sample.

OUTPUT FILES (written to the current working directory)
-------------------------------------------------------
ibm_results_per_job_v9.csv    one row per job: k, shots, p_hat, p_exact, ...
ibm_results_summary_v9.csv   one row per (backend, gfunc, rule): a_hat, error
ibm_results_summary_v9.tex   LaTeX table of the summary

NOTES
-----
* Circuit identity (g0/g1/g2, k value) is inferred from the QPY circuit
  name embedded in the info file; no manual labelling is required.
* The ancilla qubit is q[2] (bit index 2 of the integer-encoded shot).
* MLAE uses K = {0,1,2} by default; for g0 the k=1 term has
  I_1(1/4) = 0 (Fisher degeneracy) and should be interpreted with care.
"""
import json, base64, zlib, io, re
from pathlib import Path
from collections import Counter
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

def load_json(path):
    with open(path, 'r') as f:
        return json.load(f)

def decode_base64_zlib_npy(payload):
    raw = base64.b64decode(payload)
    try:
        raw = zlib.decompress(raw)
    except Exception:
        pass
    bio = io.BytesIO(raw)
    try:
        return np.load(bio, allow_pickle=True)
    except Exception:
        return None

def decode_packed_bool_matrix(payload, shape, bitorder="big"):
    raw = base64.b64decode(payload)
    nbits = int(np.prod(shape))
    bits = np.unpackbits(np.frombuffer(raw, dtype=np.uint8), bitorder=bitorder)
    if bits.size < nbits:
        raise ValueError(f"Packed bool payload too short: got {bits.size} bits, need {nbits}")
    bits = bits[:nbits]
    return bits.reshape(shape).astype(bool)

def ndarray_to_counts(arr, num_bits):
    arr = np.asarray(arr)
    if arr.ndim == 2 and arr.shape[1] == 1:
        vals = arr[:, 0].astype(int)
        return dict(Counter(format(v, f'0{num_bits}b') for v in vals))
    if arr.ndim == 2 and arr.shape[1] == num_bits:
        return dict(Counter(''.join(str(int(b)) for b in row) for row in arr))
    if arr.ndim == 1:
        vals = arr.astype(int)
        return dict(Counter(format(v, f'0{num_bits}b') for v in vals))
    raise ValueError(f"Unsupported ndarray shape {arr.shape}")

def recursive_find_candidates(obj, path="root"):
    out = []
    if isinstance(obj, dict):
        keys = set(obj.keys())
        if {"array","num_bits"} <= keys or {"data","num_bits"} <= keys or \
           {"data","shape","dtype"} <= keys or "__type__" in keys or \
           "counts" in keys or "memory" in keys:
            out.append((path, obj))
        for k, v in obj.items():
            out.extend(recursive_find_candidates(v, path + "." + str(k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.extend(recursive_find_candidates(v, path + f"[{i}]"))
    return out

def parse_counts_from_cnode(cnode):
    if isinstance(cnode, dict) and "__value__" in cnode and isinstance(cnode["__value__"], dict):
        cnode = cnode["__value__"]

    if isinstance(cnode, dict) and "counts" in cnode and isinstance(cnode["counts"], dict):
        return {str(k): int(v) for k, v in cnode["counts"].items()}

    if isinstance(cnode, dict) and "memory" in cnode and isinstance(cnode["memory"], list):
        return dict(Counter(str(x) for x in cnode["memory"]))

    if isinstance(cnode, dict):
        num_bits = cnode.get("num_bits")
        shape = cnode.get("shape")
        dtype = str(cnode.get("dtype", "")).lower()

        for payload_key in ("array", "data"):
            payload = cnode.get(payload_key)
            if isinstance(payload, dict) and "__value__" in payload:
                payload = payload["__value__"]

            if not isinstance(payload, str):
                continue

            # Packed boolean matrix case: base64-encoded packed bits with explicit shape/dtype.
            if shape is not None and dtype in {"bool", "bool_", "np.bool_", "boolean"}:
                arr = decode_packed_bool_matrix(payload, tuple(shape), bitorder="big")
                return ndarray_to_counts(arr, int(shape[1]))

            # .npy or zlib+.npy case.
            arr = decode_base64_zlib_npy(payload)
            if arr is not None:
                if num_bits is None:
                    a = np.asarray(arr)
                    if a.ndim == 2 and a.shape[1] > 1:
                        num_bits = int(a.shape[1])
                    elif a.size:
                        vmax = int(np.max(a))
                        num_bits = max(1, int(np.ceil(np.log2(max(vmax, 1) + 1))))
                if num_bits is None:
                    raise ValueError("Decoded ndarray but num_bits missing")
                return ndarray_to_counts(arr, int(num_bits))

    if isinstance(cnode, str):
        arr = decode_base64_zlib_npy(cnode)
        if arr is not None:
            vmax = int(np.max(arr))
            num_bits = max(1, int(np.ceil(np.log2(max(vmax,1)+1))))
            return ndarray_to_counts(arr, num_bits)

    raise ValueError("No supported payload found in field 'c'")

def extract_counts(result):
    try:
        pub_results = result.get("__value__", {}).get("pub_results", [])
        if pub_results:
            pr0 = pub_results[0].get("__value__", {})
            cnode = pr0.get("data", {}).get("__value__", {}).get("fields", {}).get("c")
            if cnode is not None:
                return parse_counts_from_cnode(cnode)
    except Exception:
        pass

    try:
        cnode = result["data"][0]["results"]["c"]
        return parse_counts_from_cnode(cnode)
    except Exception:
        pass

    for _, node in recursive_find_candidates(result):
        try:
            return parse_counts_from_cnode(node)
        except Exception:
            continue

    raise ValueError("Could not decode counts from any known result format")

def parse_tag_metadata(tags):
    for tag in tags or []:
        m = re.fullmatch(r'(sin2_pix_over2|sin2_pix|g0|g1_midpoint|g2_midpoint|g1|g2)_k(\d+)', tag)
        if m:
            stem, k = m.group(1), int(m.group(2))
            if stem == "sin2_pix_over2":
                return "g1_midpoint", "midpoint", k, tag
            if stem == "sin2_pix":
                return "g2_midpoint", "midpoint", k, tag
            if stem == "g1":
                return "g1_midpoint", "midpoint", k, tag
            if stem == "g2":
                return "g2_midpoint", "midpoint", k, tag
            if stem == "g0":
                return "g0", "midpoint", k, tag
            return stem, "midpoint", k, tag
    return "", "", np.nan, ""

def infer_info(info):
    backend = info.get("backend", "")
    shots = np.nan
    circuit_label = ""
    gfunc = ""
    rule = ""
    k = np.nan

    params = info.get("params", {})

    # Runtime "pubs" format
    pubs = params.get("pubs", [])
    if pubs and isinstance(pubs[0], list) and len(pubs[0]) >= 3:
        try:
            shots = int(pubs[0][2])
        except Exception:
            pass
        qpy_blob = pubs[0][0].get("__value__") if isinstance(pubs[0][0], dict) else None
        if isinstance(qpy_blob, str):
            raw = base64.b64decode(qpy_blob)
            try:
                raw = zlib.decompress(raw)
            except Exception:
                pass
            text = raw.decode("latin1", errors="ignore")
            m = re.search(r'(g[0-9](?:_[A-Za-z0-9]+)?_k[0-9]+)', text)
            if m:
                circuit_label = m.group(1)

    # Executor/Composer format
    qp = params.get("quantum_program", {})
    if shots != shots:
        try:
            shots = int(qp.get("shots"))
        except Exception:
            pass

    if not circuit_label:
        tg_gfunc, tg_rule, tg_k, tg_label = parse_tag_metadata(info.get("tags", []))
        if tg_label:
            gfunc, rule, k, circuit_label = tg_gfunc, tg_rule, tg_k, tg_label

    if circuit_label and (not gfunc or k != k):
        m = re.match(r'(g[0-9](?:_[A-Za-z0-9]+)?)_k([0-9]+)$', circuit_label)
        if m:
            gfunc = gfunc or m.group(1)
            k = int(m.group(2))
            rule = rule or ("midpoint" if ("midpoint" in gfunc or gfunc in {"g0", "g1", "g2"}) else "")

    return backend, gfunc, rule, k, circuit_label, shots

def infer_a_exact(gfunc, circuit_label=""):
    s = ((gfunc or "") + " " + (circuit_label or "")).lower()
    if "g0" in s or "quarter" in s:
        return 0.25
    if "g1" in s or "over2" in s or "sin2_pix_over2" in s:
        return 0.5
    if "g2" in s or "sin2_pix" in s:
        return 0.5
    return np.nan

def pk(a, k):
    a = np.clip(float(a), 1e-12, 1 - 1e-12)
    return float(np.sin((2 * int(k) + 1) * np.arcsin(np.sqrt(a))) ** 2)

def mlae_from_rows(rows):
    ks = [int(r["k"]) for r in rows]
    ms = [int(r["m_ancilla"]) for r in rows]
    Ns = [int(r["shots"]) for r in rows]

    def negll(a):
        eps = 1e-15
        s = 0.0
        for k, m, N in zip(ks, ms, Ns):
            p = pk(a, k)
            s += m * np.log(max(p, eps)) + (N - m) * np.log(max(1 - p, eps))
        return -s

    grid = np.linspace(1e-4, 1 - 1e-4, 5000)
    vals = np.array([negll(a) for a in grid])
    ab = float(grid[np.argmin(vals)])
    lo, hi = max(1e-9, ab - 0.05), min(1 - 1e-9, ab + 0.05)
    res = minimize_scalar(negll, bounds=(lo, hi), method='bounded')
    return float(res.x)

def analyze():
    result_files = sorted(Path(".").glob("*-result.json"))
    rows = []
    for rf in result_files:
        prefix = rf.name.replace("-result.json", "")
        inf = Path(prefix + "-info.json")
        row = {"prefix": prefix}
        try:
            result = load_json(rf)
            info = load_json(inf) if inf.exists() else {}
            backend, gfunc, rule, k, circuit_label, shots_info = infer_info(info)
            counts = extract_counts(result)
            if not counts:
                raise ValueError("Empty counts")
            total = int(sum(int(v) for v in counts.values()))
            shots = int(shots_info) if shots_info == shots_info else total
            m_ancilla = sum(v for bs, v in counts.items() if str(bs)[0] == '1')
            p_hat = m_ancilla / shots if shots else np.nan
            a_exact = infer_a_exact(gfunc, circuit_label)
            p_exact_job = pk(a_exact, int(k)) if (a_exact == a_exact and k == k) else np.nan
            prob_abs_error_job = abs(p_hat - p_exact_job) if (p_exact_job == p_exact_job and p_hat == p_hat) else np.nan
            row.update({
                "backend": backend, "gfunc": gfunc, "rule": rule, "k": k,
                "circuit_label": circuit_label, "shots": shots, "m_ancilla": m_ancilla,
                "p_hat": p_hat, "a_exact": a_exact, "p_exact_job": p_exact_job,
                "prob_abs_error_job": prob_abs_error_job, "status": "ok", "error_message": ""
            })
        except Exception as e:
            row.update({
                "backend": "", "gfunc": "", "rule": "", "k": np.nan, "circuit_label": "",
                "shots": np.nan, "m_ancilla": np.nan, "p_hat": np.nan, "a_exact": np.nan,
                "p_exact_job": np.nan, "prob_abs_error_job": np.nan,
                "status": "error", "error_message": str(e)
            })
        rows.append(row)

    per = pd.DataFrame(rows)
    summary_rows = []
    ok = per[per["status"] == "ok"].copy()
    for (backend, gfunc, rule), grp in ok.groupby(["backend", "gfunc", "rule"], dropna=False):
        grp2 = grp.sort_values("k")
        a_exact = infer_a_exact(gfunc, " ".join(grp2["circuit_label"].astype(str).tolist()))
        a_hat = mlae_from_rows(grp2.to_dict("records")) if len(grp2) else np.nan
        abs_error = abs(a_hat - a_exact) if (a_hat == a_hat and a_exact == a_exact) else np.nan
        summary_rows.append({
            "backend": backend, "gfunc": gfunc, "rule": rule,
            "schedule": ",".join(str(int(x)) for x in grp2["k"].tolist()),
            "a_hat": a_hat, "a_exact": a_exact, "abs_error": abs_error,
            "num_jobs": len(grp2), "status": "ok"
        })
    summ = pd.DataFrame(summary_rows)

    per.to_csv("ibm_results_per_job_v9.csv", index=False)
    summ.to_csv("ibm_results_summary_v9.csv", index=False)
    with open("ibm_results_summary_v9.tex", "w") as f:
        if len(summ):
            f.write(summ.to_latex(index=False))
        else:
            f.write("% No valid summary rows\n")

    print("=== Per-job results ===")
    if len(per):
        print(per.to_string(index=False))
    else:
        print("No per-job rows.")
    print("\n=== Summary ===")
    if len(summ):
        print(summ.to_string(index=False))
    else:
        print("No valid summary rows.")

if __name__ == "__main__":
    analyze()

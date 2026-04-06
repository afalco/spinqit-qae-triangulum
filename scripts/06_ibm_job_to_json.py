from __future__ import annotations

import argparse
import base64
import json
import os
import re
from collections import Counter
from pathlib import Path

import numpy as np


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Convert an IBM Runtime job info/result JSON pair into a post-processing JSON artifact."
    )
    p.add_argument("--info", required=True, help="Path to job-...-info.json")
    p.add_argument("--result", required=True, help="Path to job-...-result.json")
    p.add_argument("--out", required=True, help="Output JSON path")
    p.add_argument(
        "--k",
        type=int,
        default=None,
        help="Amplification index k. If omitted, infer from tags or filename.",
    )
    p.add_argument(
        "--ancilla-bit",
        type=int,
        default=2,
        help="Classical bit index corresponding to the ancilla measurement. Default: 2",
    )
    p.add_argument(
        "--bitstring-order",
        choices=["c012", "qiskit"],
        default="qiskit",
        help=(
            "Preferred exported bitstring convention for counts/probabilities. "
            "'c012' means c[0]c[1]c[2]; "
            "'qiskit' means reversed display order c[2]c[1]c[0]."
        ),
    )
    return p.parse_args()


def load_json(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def infer_k(info: dict, info_path: str | Path, explicit_k: int | None) -> int | None:
    if explicit_k is not None:
        return explicit_k

    tags = info.get("tags", [])
    for t in tags:
        m = re.fullmatch(r"qae_k_(\d+)", t)
        if m:
            return int(m.group(1))

    name = Path(info_path).name
    m = re.search(r"_k(\d+)", name)
    if m:
        return int(m.group(1))

    return None


def decode_bool_matrix_from_result(result: dict) -> np.ndarray:
    payload = result["data"][0]["results"]["c"]
    b64 = payload["data"]
    shape = payload["shape"]
    dtype = payload["dtype"]

    if dtype != "bool":
        raise ValueError(f"Unsupported dtype {dtype!r}; expected 'bool'.")

    if len(shape) != 2:
        raise ValueError(f"Unsupported shape {shape!r}; expected [shots, nbits].")

    nshots, nbits = shape

    raw = base64.b64decode(b64)
    bits = np.unpackbits(np.frombuffer(raw, dtype=np.uint8), bitorder="little")
    bits = bits[: nshots * nbits]
    mat = bits.reshape(nshots, nbits).astype(np.uint8)

    return mat


def counts_from_matrix(mat: np.ndarray, order: str) -> Counter:
    if order == "c012":
        return Counter("".join(str(int(b)) for b in row) for row in mat)
    if order == "qiskit":
        return Counter("".join(str(int(b)) for b in row[::-1]) for row in mat)
    raise ValueError(f"Unknown order: {order}")


def probabilities_from_counts(counts: Counter, nshots: int) -> dict[str, float]:
    return {k: v / nshots for k, v in sorted(counts.items())}


def marginals_by_bit(mat: np.ndarray) -> dict[str, dict[str, float]]:
    nshots, nbits = mat.shape
    out: dict[str, dict[str, float]] = {}
    for j in range(nbits):
        p1 = float(mat[:, j].mean())
        out[f"c{j}"] = {
            "p0": 1.0 - p1,
            "p1": p1,
        }
    return out


def joint_index_distribution_excluding_bit(
    mat: np.ndarray,
    excluded_bit: int,
    order: str = "ascending",
) -> dict[str, float]:
    """
    Return the marginal distribution over all measured bits except excluded_bit.
    For 3 bits and excluded_bit=2, this gives the distribution over c0,c1.
    """
    nshots, nbits = mat.shape
    keep = [j for j in range(nbits) if j != excluded_bit]
    sub = mat[:, keep]

    if order == "ascending":
        counts = Counter("".join(str(int(b)) for b in row) for row in sub)
    else:
        counts = Counter("".join(str(int(b)) for b in row[::-1]) for row in sub)

    return {k: v / nshots for k, v in sorted(counts.items())}


def extract_metadata(info: dict, result: dict) -> dict:
    payload = result["data"][0]["results"]["c"]
    return {
        "job_id": info.get("id"),
        "backend": info.get("backend"),
        "status": info.get("status"),
        "created": info.get("created"),
        "shots": info.get("params", {})
                    .get("quantum_program", {})
                    .get("shots", payload["shape"][0]),
        "nbits": payload["shape"][1],
        "tags": info.get("tags", []),
        "program_id": info.get("program", {}).get("id"),
        "cost": info.get("cost"),
        "meas_level": info.get("params", {})
                         .get("quantum_program", {})
                         .get("meas_level"),
        "chunk_timing": result.get("metadata", {}).get("chunk_timing"),
    }


def main() -> None:
    args = parse_args()

    info = load_json(args.info)
    result = load_json(args.result)

    mat = decode_bool_matrix_from_result(result)
    nshots, nbits = mat.shape

    if not (0 <= args.ancilla_bit < nbits):
        raise ValueError(
            f"--ancilla-bit={args.ancilla_bit} is out of range for nbits={nbits}"
        )

    k = infer_k(info, args.info, args.k)

    counts_c012 = counts_from_matrix(mat, "c012")
    counts_qiskit = counts_from_matrix(mat, "qiskit")

    probs_c012 = probabilities_from_counts(counts_c012, nshots)
    probs_qiskit = probabilities_from_counts(counts_qiskit, nshots)

    ancilla_p1 = float(mat[:, args.ancilla_bit].mean())
    ancilla_summary = {
        "classical_bit": f"c[{args.ancilla_bit}]",
        "p0": 1.0 - ancilla_p1,
        "p1": ancilla_p1,
    }

    payload = {
        "schema_version": "qae_ibm_job_v1",
        "source_files": {
            "info_json": str(Path(args.info)),
            "result_json": str(Path(args.result)),
        },
        "job_metadata": extract_metadata(info, result),
        "derived": {
            "k": k,
            "ancilla_bit": args.ancilla_bit,
            "bitstring_convention_primary": args.bitstring_order,
            "counts": dict(sorted(
                (counts_qiskit if args.bitstring_order == "qiskit" else counts_c012).items()
            )),
            "probabilities": probs_qiskit if args.bitstring_order == "qiskit" else probs_c012,
            "counts_c012": dict(sorted(counts_c012.items())),
            "probabilities_c012": probs_c012,
            "counts_qiskit": dict(sorted(counts_qiskit.items())),
            "probabilities_qiskit": probs_qiskit,
            "marginals_by_classical_bit": marginals_by_bit(mat),
            "ancilla_marginal": ancilla_summary,
            "index_distribution_excluding_ancilla_c_order": joint_index_distribution_excluding_bit(
                mat, excluded_bit=args.ancilla_bit, order="ascending"
            ),
        },
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"[OK] Wrote {out_path}")
    print(f"  shots             : {nshots}")
    print(f"  nbits             : {nbits}")
    print(f"  inferred k        : {k}")
    print(f"  backend           : {payload['job_metadata']['backend']}")
    print(f"  ancilla bit       : c[{args.ancilla_bit}]")
    print(f"  P(ancilla=1)      : {ancilla_summary['p1']:.6f}")
    print(f"  P(ancilla=0)      : {ancilla_summary['p0']:.6f}")


if __name__ == "__main__":
    main()
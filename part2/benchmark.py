from __future__ import annotations

import argparse
import csv
import importlib
import os
import sys
from pathlib import Path

import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
GRADER = HERE / "grader"
PART1 = ROOT / "part1"

for path in (str(HERE), str(GRADER), str(PART1)):
    if path not in sys.path:
        sys.path.insert(0, path)

from routing_common import (
    capture, line_edges, grid_edges, heavy_hex_edges,
    circuit_depth, fidelity, gate_counts, is_legal,
)
from route_harness import qiskit_baseline
import circuits as C
import numpy as np


def build_full_suite():
    rng = np.random.default_rng(1234)
    circuit_cases = [
        ("ghz_n5", capture(C.ghz, 5), 5),
        ("qft_n5", capture(C.qft, 5), 5),
        ("bv_n4", capture(C.bv_circuit, 4, 0b1011), 5),
        ("qaoa_n6", capture(C.qaoa_1d, 6, 1, [0.7], [0.4]), 6),
        ("rand_n5", capture(C.random_universal, 5, rng, 3), 5),
        ("nearclif_n5", capture(C.near_clifford, 5, rng, 3), 5),
    ]
    grid, _ = grid_edges(2, 3)
    heavy_hex, _ = heavy_hex_edges()
    graphs = [
        ("line6", line_edges(6)),
        ("grid2x3", grid),
        ("heavyhex27", heavy_hex),
    ]
    return [
        (f"{circuit_name}_{graph_name}", ops, n, edges, graph_name)
        for circuit_name, ops, n in circuit_cases
        for graph_name, edges in graphs
    ]


def load_router(module_name):
    module = importlib.import_module(module_name)
    importlib.reload(module)
    return module.Router


def evaluate(router_class, suite, label):
    rows = []
    passed = True

    for circuit, ops, n, edges, graph in suite:
        result = router_class(edges).route(ops, n)
        legal, message = is_legal(result.ops, edges)
        fid = fidelity(ops, result.ops, n, result.final)
        ok = legal and fid >= 0.999
        passed = passed and ok

        original = gate_counts(ops)
        routed = gate_counts(result.ops)
        original_depth = circuit_depth(ops)
        routed_depth = circuit_depth(result.ops)
        qiskit = qiskit_baseline(ops, n, edges)

        rows.append({
            "router": label,
            "circuit": circuit,
            "graph": graph,
            "n": n,
            "legal": legal,
            "legality_message": message,
            "fidelity": fid,
            "pass": ok,
            "original_2q": original["2q"],
            "routed_2q": routed["2q"],
            "inserted_swaps": routed["swap"] - original["swap"],
            "original_depth": original_depth,
            "routed_depth": routed_depth,
            "twoq_overhead_ratio": routed["2q"] / max(original["2q"], 1),
            "depth_overhead_ratio": routed_depth / max(original_depth, 1),
            "inserted_swaps_per_original_2q": (
                (routed["swap"] - original["swap"]) / max(original["2q"], 1)
            ),
            "qiskit_swaps_opt0": qiskit["swap"] if qiskit else "",
            "qiskit_2q_opt3": qiskit["2q3"] if qiskit else "",
            "qiskit_depth_opt3": qiskit["depth3"] if qiskit else "",
        })

    return rows, passed


def write_csv(rows, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError("no benchmark rows to write")
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def plot_metric(rows, metric, ylabel, output):
    labels = sorted({row["circuit"] for row in rows})
    routers = sorted({row["router"] for row in rows})
    graphs = sorted({row["graph"] for row in rows})

    for graph in graphs:
        selected = [r for r in rows if r["graph"] == graph]
        if not selected:
            continue

        x = list(range(len(labels)))
        width = 0.8 / max(len(routers), 1)
        plt.figure(figsize=(max(8, len(labels) * 1.2), 5))

        for index, router in enumerate(routers):
            values = []
            for label in labels:
                match = next(
                    (r for r in selected if r["router"] == router and r["circuit"] == label),
                    None,
                )
                values.append(float(match[metric]) if match else 0.0)
            offsets = [v + (index - (len(routers) - 1) / 2) * width for v in x]
            plt.bar(offsets, values, width=width, label=router)

        plt.xticks(x, labels, rotation=25, ha="right")
        plt.ylabel(ylabel)
        plt.title(f"{ylabel} — {graph}")
        plt.legend()
        plt.tight_layout()
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        graph_name = graph.replace("/", "_")
        plt.savefig(output_path.with_name(f"{output_path.stem}_{graph_name}{output_path.suffix}"), dpi=180)
        plt.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", default="router")
    parser.add_argument("--improved", default="router_improved")
    parser.add_argument("--output", default=str(HERE / "results" / "benchmark.csv"))
    parser.add_argument("--plots", default=str(HERE / "results" / "plots" / "comparison.png"))
    parser.add_argument("--ablation", action="store_true")
    args = parser.parse_args()

    if args.ablation:
        os.environ["SABRE_IMPROVED_ABLATION"] = "1"

    suite = build_full_suite()
    baseline_class = load_router(args.baseline)
    improved_class = load_router(args.improved)

    baseline_rows, baseline_ok = evaluate(baseline_class, suite, args.baseline)
    improved_rows, improved_ok = evaluate(improved_class, suite, args.improved)
    rows = baseline_rows + improved_rows

    write_csv(rows, args.output)
    plot_metric(rows, "inserted_swaps", "Inserted SWAP gates", args.plots)
    plot_metric(rows, "depth_overhead_ratio", "Depth overhead ratio", args.plots)

    print(f"Baseline correctness: {'PASS' if baseline_ok else 'FAIL'}")
    print(f"Improved correctness: {'PASS' if improved_ok else 'FAIL'}")
    print(f"CSV: {args.output}")
    print(f"Plots: {Path(args.plots).parent}")
    if not baseline_ok or not improved_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

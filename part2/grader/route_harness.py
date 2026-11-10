#!/usr/bin/env python3
# COL8422 Part 2 -- routing auto-grader.
#
# Per group, one run:
#   * LEGALITY   -- every 2q gate of the routed circuit lies on a coupling edge
#   * EQUIVALENCE-- routed circuit == original (fidelity >= 0.999), undoing the
#                   output qubit placement; checked with a trusted numpy oracle
#                   (needs NEITHER Qiskit NOR the student's C++ backend)
#   * METRICS    -- inserted SWAPs / 2q-count / depth, vs Qiskit's SABRE
#                   transpiler computed on THIS machine
#   * IMPROVEMENT-- if a second router module is given, the delta vs the first
#
# Usage (self-test with the reference router):
#   python route_harness.py
# Grade a group:
#   python route_harness.py --router-dir ../../group7/part2 --router router \
#                           --improved router_improved --csv results/group7.csv
#
# Qiskit is optional: without it, legality + equivalence + the student's own
# metrics still run; only the Qiskit baseline column shows "n/a".

from __future__ import annotations

import argparse
import csv
import importlib
import os
import sys

# --- make routing_common (part2/) and circuits.py (part1/) importable --------
_HERE = os.path.dirname(os.path.abspath(__file__))
_PART2 = os.path.abspath(os.path.join(_HERE, ".."))
_PART1 = os.path.abspath(os.path.join(_HERE, "..", "..", "part1"))
for p in (_PART2, _PART1):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np  # noqa: E402

import circuits as C  # noqa: E402  (Part-1 provided generators)
from routing_common import (  # noqa: E402
    capture, line_edges, grid_edges, heavy_hex_edges,
    is_legal, fidelity, gate_counts, circuit_depth,
)

FID_THRESHOLD = 0.999

try:
    from qiskit import QuantumCircuit, transpile
    from qiskit.transpiler import CouplingMap
    _HAVE_QISKIT = True
except Exception:  # noqa: BLE001
    _HAVE_QISKIT = False


# ---------------------------------------------------------------------------
# Benchmark suite: (label, ops, n_logical, edges, graph_name)
# n is kept small so the exact numpy oracle (2**n) is cheap.
# ---------------------------------------------------------------------------

def build_suite():
    rng = np.random.default_rng(1234)
    suite = []

    l5, _ = line_edges(5), None
    g6, n6 = grid_edges(2, 3)
    hh, _ = heavy_hex_edges()

    suite.append(("ghz_n5",       capture(C.ghz, 5),                 5, line_edges(5), "line5"))
    suite.append(("qft_n5_line",  capture(C.qft, 5),                 5, line_edges(5), "line5"))
    suite.append(("qft_n5_hhex",  capture(C.qft, 5),                 5, hh,            "heavyhex27"))
    suite.append(("bv_n4",        capture(C.bv_circuit, 4, 0b1011),  5, line_edges(5), "line5"))  # 4 data +1 anc (ancilla=idx4)
    suite.append(("qaoa_n6_grid", capture(C.qaoa_1d, 6, 1, [0.7], [0.4]), 6, g6,       "grid2x3"))
    suite.append(("rand_n5",      capture(C.random_universal, 5, rng, 3), 5, line_edges(5), "line5"))
    suite.append(("nearclif_n5",  capture(C.near_clifford, 5, rng, 3),    5, line_edges(5), "line5"))
    return suite


# ---------------------------------------------------------------------------
# Qiskit baseline (SABRE) -- SWAPs at opt-level 0, depth at opt-level 3
# ---------------------------------------------------------------------------

def _to_qiskit(ops, n):
    qc = QuantumCircuit(n)
    g1 = {"H": "h", "X": "x", "Y": "y", "Z": "z", "S": "s", "T": "t"}
    for op in ops:
        if not op.is_2q:
            if op.gate == "U":
                qc.u(op.params["theta"], op.params["phi"], op.params["lam"], op.qubits[0])
            else:
                getattr(qc, g1[op.gate])(op.qubits[0])
        else:
            a, b = op.qubits
            if op.gate == "CNOT":
                qc.cx(a, b)
            elif op.gate == "CZ":
                qc.cz(a, b)
            elif op.gate == "SWAP":
                qc.swap(a, b)
            elif op.gate == "CU":
                qc.cu(op.params["theta"], op.params["phi"], op.params["lam"], 0.0, a, b)
    return qc


def qiskit_baseline(ops, n, edges):
    if not _HAVE_QISKIT:
        return None
    qc = _to_qiskit(ops, n)
    cm = CouplingMap([[u, v] for u, v in edges] + [[v, u] for u, v in edges])
    t0 = transpile(qc, coupling_map=cm, layout_method="sabre", routing_method="sabre",
                   optimization_level=0, seed_transpiler=7)
    swaps = t0.count_ops().get("swap", 0)
    t3 = transpile(qc, coupling_map=cm, layout_method="sabre", routing_method="sabre",
                   optimization_level=3, seed_transpiler=7)
    return {"swap": swaps, "depth3": t3.depth(),
            "2q3": sum(1 for inst in t3.data if inst.operation.num_qubits == 2)}


# ---------------------------------------------------------------------------
# Run one router over the suite
# ---------------------------------------------------------------------------

def run_router(RouterCls, suite, verbose=True):
    rows = []
    all_pass = True
    for label, ops, n, edges, gname in suite:
        router = RouterCls(edges)
        res = router.route(ops, n)
        legal, msg = is_legal(res.ops, edges)
        fid = fidelity(ops, res.ops, n, res.final)
        ok = legal and fid >= FID_THRESHOLD
        all_pass = all_pass and ok
        gc = gate_counts(res.ops)
        base = qiskit_baseline(ops, n, edges)
        row = {
            "circuit": label, "graph": gname, "n": n,
            "legal": legal, "fidelity": round(fid, 6), "pass": ok,
            "swaps": gc["swap"], "2q": gc["2q"], "depth": circuit_depth(res.ops),
            "qiskit_swaps": (base["swap"] if base else "n/a"),
            "qiskit_depth3": (base["depth3"] if base else "n/a"),
        }
        rows.append(row)
        if verbose:
            status = "PASS" if ok else ("FAIL:" + ("illegal " + msg if not legal else f"fid={fid:.4f}"))
            qk = f"  qiskit_swaps={base['swap']}" if base else ""
            print(f"  [{status:>5}] {label:<14} {gname:<11} "
                  f"swaps={gc['swap']:<3} 2q={gc['2q']:<4} depth={row['depth']:<4}{qk}")
    return rows, all_pass


def load_router(router_dir, module_name):
    rd = os.path.abspath(router_dir)
    if rd not in sys.path:
        sys.path.insert(0, rd)
    mod = importlib.import_module(module_name)
    importlib.reload(mod)
    return getattr(mod, "Router")


def main():
    ap = argparse.ArgumentParser(description="COL8422 Part-2 routing grader")
    ap.add_argument("--router-dir", default=_PART2,
                    help="directory containing the student's router module")
    ap.add_argument("--router", default="reference_router",
                    help="router module name (defines class Router)")
    ap.add_argument("--improved", default=None,
                    help="optional improved router module for the delta")
    ap.add_argument("--csv", default=None, help="write per-circuit metrics here")
    args = ap.parse_args()

    print(f"Qiskit baseline: {'ON' if _HAVE_QISKIT else 'OFF (install qiskit for the comparison)'}")
    suite = build_suite()

    print(f"\n== Router: {args.router} ==")
    RouterCls = load_router(args.router_dir, args.router)
    rows, all_pass = run_router(RouterCls, suite)
    total_swaps = sum(r["swaps"] for r in rows)
    print(f"  correctness gate: {'ALL PASS' if all_pass else 'FAILURES PRESENT'}"
          f"   |   total SWAPs = {total_swaps}")

    if args.improved:
        print(f"\n== Improved router: {args.improved} ==")
        ImpCls = load_router(args.router_dir, args.improved)
        rows2, all_pass2 = run_router(ImpCls, suite)
        total2 = sum(r["swaps"] for r in rows2)
        delta = total_swaps - total2
        pct = (100.0 * delta / total_swaps) if total_swaps else 0.0
        print(f"  correctness gate: {'ALL PASS' if all_pass2 else 'FAILURES PRESENT'}")
        print(f"\n== Improvement: {total_swaps} -> {total2} SWAPs "
              f"({delta:+d}, {pct:+.1f}%) over the baseline router ==")

    if args.csv:
        os.makedirs(os.path.dirname(os.path.abspath(args.csv)), exist_ok=True)
        with open(args.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"\nwrote {args.csv}")

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()

import os
import sys
import csv
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PART1 = ROOT / "part1"
PART2 = ROOT / "part2"

sys.path.insert(0, str(PART1))
sys.path.insert(0, str(PART2))

os.environ["STATEVECTOR_IMPL"] = "cpu"

from backends.statevector import StatevectorSimulator
from routing_common import replay
from benchmark import build_full_suite
import router
import router_improved


class PhysicalQubitMapper:
    def __init__(self, simulator, mapping):
        self.simulator = simulator
        self.mapping = mapping

    def apply_1q_gate(self, gate, q, *args, **kwargs):
        return self.simulator.apply_1q_gate(
            gate, self.mapping[q], *args, **kwargs
        )

    def apply_2q_gate(self, gate, q1, q2, *args, **kwargs):
        return self.simulator.apply_2q_gate(
            gate,
            self.mapping[q1],
            self.mapping[q2],
            *args,
            **kwargs
        )


def execute_original(ops, n):
    sim = StatevectorSimulator()
    sim.initialize(n)
    replay(ops, sim)
    return np.asarray(sim.statevector).copy()


def execute_routed(ops, result):
    physical = set(result.final)
    for op in ops:
        physical.update(op.qubits)

    physical = sorted(physical)
    mapping = {q: i for i, q in enumerate(physical)}

    sim = StatevectorSimulator()
    sim.initialize(len(physical))

    mapped_sim = PhysicalQubitMapper(sim, mapping)
    replay(ops, mapped_sim)

    physical_state = np.asarray(sim.statevector)
    logical_state = np.zeros(2 ** len(result.final), dtype=np.complex128)

    # Part 1 CPU backend uses qubit 0 as the least significant bit.
    # final[logical] gives the physical position of each logical qubit.
    final_dense = [mapping[q] for q in result.final]

    for logical_index in range(len(logical_state)):
        physical_index = 0
        for logical_q, physical_q in enumerate(final_dense):
            bit = (logical_index >> logical_q) & 1
            physical_index |= bit << physical_q

        logical_state[logical_index] = physical_state[physical_index]

    return logical_state


def state_fidelity(a, b):
    denominator = np.vdot(a, a).real * np.vdot(b, b).real
    if denominator == 0:
        return 0.0
    return float(abs(np.vdot(a, b)) ** 2 / denominator)


def main():
    rows = []
    suite = build_full_suite()

    for module in (router, router_improved):
        label = module.__name__
        print(f"\nTesting {label}", flush=True)

        for name, ops, n, edges, graph in suite:
            result = module.Router(edges).route(ops, n)

            original_state = execute_original(ops, n)
            routed_state = execute_routed(result.ops, result)

            fid = state_fidelity(original_state, routed_state)
            passed = fid >= 0.999

            rows.append({
                "router": label,
                "circuit": name,
                "graph": graph,
                "qubits": n,
                "backend_fidelity": fid,
                "pass": passed,
            })

            print(
                f"{name:25s} fidelity={fid:.12f} "
                f"{'PASS' if passed else 'FAIL'}",
                flush=True,
            )

            if not passed:
                raise RuntimeError(
                    f"Part 1 backend equivalence failed: {label}, {name}, "
                    f"fidelity={fid}"
                )

    output = PART2 / "results" / "backend_equivalence.csv"
    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nAll {len(rows)} backend checks passed.")
    print(f"Results: {output}")


if __name__ == "__main__":
    main()

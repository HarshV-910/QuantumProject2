import os
import sys
import csv
import time
import statistics
import inspect
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
PART1 = ROOT / "part1"
PART2 = ROOT / "part2"

sys.path.insert(0, str(PART1))
sys.path.insert(0, str(PART2))

# Select the CPU implementation before importing the backend.
os.environ["STATEVECTOR_IMPL"] = "cpu"

import circuits as C
from backends.statevector import StatevectorSimulator
from routing_common import capture, replay, fidelity
import router
import router_improved


def get_router(module, edges):
    """Find and instantiate the Router class defined in a router module."""
    candidates = [
        cls for _, cls in inspect.getmembers(module, inspect.isclass)
        if cls.__module__ == module.__name__
        and callable(getattr(cls, "route", None))
    ]
    if not candidates:
        raise RuntimeError(f"No Router class found in {module.__name__}")
    return candidates[0](edges)


def timed_execution(ops, n, repeats=100, batches=5):
    """Measure median circuit execution time using batched repetitions."""
    batch_times = []

    for _ in range(batches):
        sim = StatevectorSimulator()
        sim.initialize(n)

        # Warm-up execution (not included in timing).
        replay(ops, sim)

        # Reset state before measuring.
        sim.initialize(n)

        start = time.perf_counter()

        for _ in range(repeats):
            replay(ops, sim)

        elapsed = time.perf_counter() - start
        batch_times.append(elapsed / repeats)

    return statistics.median(batch_times)


def main():
    output_dir = PART2 / "results"
    plot_dir = output_dir / "plots"
    output_dir.mkdir(parents=True, exist_ok=True)
    plot_dir.mkdir(parents=True, exist_ok=True)

    # Increase these sizes only after confirming the first run completes.
    qubit_sizes = [4, 6, 8, 10, 12]
    rows = []

    for n in qubit_sizes:
        print(f"\nTesting QFT with {n} qubits...", flush=True)

        # Capture the original logical circuit.
        original_ops = capture(C.qft, n)

        # Use a line coupling graph with n physical qubits.
        edges = [(i, i + 1) for i in range(n - 1)]

        baseline = get_router(router, edges)
        improved = get_router(router_improved, edges)

        baseline_result = baseline.route(original_ops, n)
        improved_result = improved.route(original_ops, n)

        # Check routing equivalence using the Part 2 oracle.
        base_fidelity = fidelity(
            original_ops, baseline_result.ops, n, baseline_result.final
        )
        improved_fidelity = fidelity(
            original_ops, improved_result.ops, n, improved_result.final
        )

        if base_fidelity < 0.999 or improved_fidelity < 0.999:
            raise RuntimeError(
                f"Routing correctness failed at n={n}: "
                f"baseline={base_fidelity}, improved={improved_fidelity}"
            )

        # Measure Part 1 backend execution time.
        original_time = timed_execution(original_ops, n)
        baseline_time = timed_execution(baseline_result.ops, n)
        improved_time = timed_execution(improved_result.ops, n)

        row = {
            "qubits": n,
            "original_time_sec": original_time,
            "baseline_routed_time_sec": baseline_time,
            "improved_routed_time_sec": improved_time,
            "baseline_fidelity": base_fidelity,
            "improved_fidelity": improved_fidelity,
            "original_gates": len(original_ops),
            "baseline_routed_gates": len(baseline_result.ops),
            "improved_routed_gates": len(improved_result.ops),
        }
        rows.append(row)

        print(
            f"Original: {original_time:.6f}s | "
            f"Baseline: {baseline_time:.6f}s | "
            f"Improved: {improved_time:.6f}s",
            flush=True,
        )

    csv_path = output_dir / "simulator_stress.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    # Runtime comparison plot.
    x = [r["qubits"] for r in rows]

    plt.figure(figsize=(9, 5))
    plt.plot(x, [r["original_time_sec"] for r in rows],
             marker="o", label="Original circuit")
    plt.plot(x, [r["baseline_routed_time_sec"] for r in rows],
             marker="s", label="Baseline SABRE")
    plt.plot(x, [r["improved_routed_time_sec"] for r in rows],
             marker="^", label="Improved router")

    plt.xlabel("Number of qubits")
    plt.ylabel("Execution time (seconds)")
    plt.title("Part 1 CPU Statevector: QFT Simulation Runtime")
    plt.xticks(x)
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()

    plot_path = plot_dir / "simulator_stress_runtime.png"
    plt.savefig(plot_path, dpi=300)
    plt.close()

    print("\nBenchmark completed.")
    print(f"CSV:  {csv_path}")
    print(f"Plot: {plot_path}")


if __name__ == "__main__":
    main()

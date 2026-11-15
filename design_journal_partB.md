# Design Journal

## 1. Overview of Contribution

our responsibility in Part 2 of the project was to work on the optimization and evaluation layer built around the SABRE routing algorithm.

The project was divided between two groups. Group 1 was responsible for implementing the baseline SABRE router and its underlying routing engine. our contribution as part of Group 2 focused on improving the initial qubit mapping, integrating layout optimization with the routing engine, and evaluating the resulting router against the baseline and Qiskit's SABRE implementation.

The main objectives of our work were:

- Implement a layout optimization procedure using forward and reverse traversal.
- Develop an improved router that explores multiple initial qubit layouts.
- Select a suitable layout based on routing quality.
- Build an evaluation pipeline covering different circuit families and hardware coupling graphs.

## 2. Initial Design and Understanding

The first step was understanding the qubit allocation and routing problem and the role of SABRE in solving it.

A quantum circuit may contain two-qubit gates between logical qubits that are not physically adjacent on the target hardware. Since the hardware coupling graph restricts which physical qubits can directly interact, additional SWAP gates must sometimes be inserted to make the circuit executable.

The initial mapping of logical qubits to physical qubits can significantly affect the number of SWAP gates required during routing. Therefore, improving the initial mapping provides an opportunity to reduce routing overhead without changing the logical computation.

We studied the role of reverse traversal in SABRE and how information from routing in the reverse direction can help improve the initial layout used for forward execution.

Based on this, we decided to keep the baseline routing engine separate from the layout optimization procedure. This allows the layout optimizer to work with a common routing interface rather than duplicating the routing algorithm implemented by Group 1.

## 3. Layout Optimization – `layout_optimizer.py`

I implemented the layout optimization layer in `part2/layout_optimizer.py`.

The central idea is to use repeated forward and reverse routing passes to improve the initial mapping.

The procedure is:

1. Start with an initial logical-to-physical qubit mapping.
2. Route the original circuit in the forward direction.
3. Use the final layout produced by this pass as the starting layout for a reverse traversal.
4. Route the reversed operation sequence.
5. Use the resulting layout as the starting point for another forward pass.
6. Repeat the process for a configurable number of iterations.
7. Retain the best forward-routing result based on the number of inserted SWAP gates, using circuit depth as a tie-breaker.

The reverse operation sequence is constructed by reversing the order of operations while preserving gate names, operand ordering and parameters. This is important because reversing the operation sequence should not accidentally change the meaning of controlled gates or their operand relationships.


## 4. Improved Router – `router_improved.py`

After implementing the layout optimizer, I developed `part2/router_improved.py`.

The improvement selected for this project is **multi-input initial-layout search**.

Rather than relying on only one initial mapping, the improved router evaluates multiple candidate mappings and selects the best resulting routing.

The candidate layouts include:

- **Identity layout:** Maps logical qubits to physical qubits in their natural order.
- **Degree-ranked layout:** Assigns logical qubits to physical locations using the connectivity information of the hardware graph.
- **Random layouts:** Generates additional candidate mappings using a fixed random seed for reproducibility.

The motivation for including degree-ranked layouts is that physical qubits with higher connectivity may provide more routing flexibility. However, a high-degree physical qubit does not necessarily correspond to the best placement for every logical qubit. The actual routing result must therefore be evaluated.

Each candidate is passed through the layout optimization procedure. The improved router then compares the resulting forward-routing solutions and selects the one with:

1. The lowest SWAP count.
2. The lowest circuit depth when SWAP counts are equal.


## 5. Benchmarking and Evaluation – `benchmark.py`

I developed `part2/benchmark.py` to evaluate the baseline and improved routers under a consistent set of circuit and hardware configurations.

The benchmark suite covers six circuit families:

1. GHZ circuits.
2. Quantum Fourier Transform (QFT).
3. Bernstein–Vazirani circuits.
4. One-dimensional QAOA circuits.
5. Random universal circuits.
6. Near-Clifford circuits.

These circuits are evaluated against three coupling graph configurations:

- Linear coupling graph.
- 2 × 3 grid coupling graph.
- Heavy-hex coupling graph.

This produces a matrix of 18 circuit-and-graph combinations.

For each configuration, the benchmark records relevant routing and circuit metrics, including:

- Routing legality.
- Equivalence fidelity.
- Inserted SWAP count.
- Total two-qubit gate count.
- Circuit depth.
- Routing overhead relative to the original circuit.
- Qiskit SABRE metrics, when the required Qiskit installation is available.

## 6. Ablation Study Design

To evaluate whether multi-start initial-layout search contributes to the routing improvement, I prepared an ablation mode.

In the normal improved-router configuration, multiple initial layouts are considered. In the ablation configuration, the additional candidate layouts are disabled, leaving the identity-layout configuration as the starting point while retaining the same reverse-layout optimization procedure.

The two configurations can then be compared using the same circuit suite, random seed and execution environment.

The main comparison metrics are:

- Total inserted SWAP gates.
- Two-qubit gate count.
- Circuit depth.
- Routing overhead.

This experiment is intended to isolate the contribution of multi-start layout selection from the rest of the layout optimization procedure.

## 7. Conclusion

Our contribution to Part 2 focuses on improving the initial-layout search and building the experimental framework required to evaluate that improvement.

We implemented the forward/reverse layout optimization procedure, developed a multi-start improved-router layer, and prepared a benchmark pipeline covering six circuit families and three hardware coupling graphs. We also prepared an ablation configuration to isolate the effect of multi-start layout selection.
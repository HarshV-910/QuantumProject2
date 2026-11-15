## 1. Project Scope

Group 1 is responsible for implementing the core SABRE routing engine and exposing it through the required public `Router` interface.

The objective is to take a logical quantum circuit and a hardware coupling graph, then produce a physically executable gate sequence by inserting SWAP operations whenever two-qubit gates cannot execute directly under the current qubit mapping.

The implementation focuses on:
- Preserving the dependency order of logical operations.
- Maintaining a valid logical-to-physical qubit mapping.
- Reducing routing overhead using a SABRE-style distance heuristic.
- Providing a clean interface compatible with the supplied grading harness.

Reverse traversal, layout optimization, improved-router orchestration, and benchmarking are assigned to Group 2 and are outside the scope of this implementation.

---

## 2. Core SABRE Routing Engine

**File:** `part2/sabre_engine.py`

### Work completed

Implemented the core SABRE-style routing pass.

The routing algorithm maintains a dependency-aware front layer and evaluates candidate SWAP operations using shortest-path distances on the hardware coupling graph.

The implemented pass performs the following steps:

1. Builds a dependency DAG to preserve the ordering constraints between operations acting on the same logical qubits.
2. Identifies the current executable front layer.
3. Executes ready two-qubit operations directly whenever their mapped physical qubits are adjacent.
4. Generates candidate SWAP operations using physical neighbors of the qubits involved in front-layer operations.
5. Builds an extended look-ahead set using upcoming dependency successors rather than simply selecting the next unprocessed operations in list order.
6. Evaluates candidate SWAPs using front-layer and look-ahead distance costs.
7. Applies a configurable decay penalty to discourage repeatedly moving the same physical qubits.
8. Updates the logical-to-physical mapping after each selected SWAP.
9. Raises a clear `ValueError` when a required interaction cannot be connected through the hardware coupling graph.

### Scoring heuristic

The candidate SWAP score is based on the following expression:

`score = (front_weight * ΔF) + (lookahead_weight * ΔE) + decay_penalty`

Where:

- `ΔF` represents the total shortest-path distance of the active front layer.
- `ΔE` represents the total shortest-path distance of the dependency-based extended set.
- `front_weight` controls the importance of the current front layer.
- `lookahead_weight` controls the importance of upcoming operations.
- `decay_penalty` discourages repeatedly using recently active physical qubits.

### Configuration

The implemented default configuration is:

| Parameter | Default value |
|---|---:|
| Look-ahead size | 10 |
| Front-layer weight | 1.0 |
| Look-ahead weight | 0.5 |
| Decay base | 0.1 |
| Decay step | 1 |

The decay mechanism tracks recently active physical qubits and gradually reduces their influence. This discourages repeated use without permanently accumulating a penalty.

### Design decision

The implementation uses a simplified SABRE-style heuristic rather than attempting to reproduce every internal detail of Qiskit's SABRE implementation.

The focus is on maintaining the required routing behavior, dependency correctness, configurable scoring, and compatibility with the project interface.

---

## 3. Public Router Interface

**File:** `part2/router.py`

### Work completed

Implemented the public `Router` interface required by the project and grading harness.

The interface provides:

- `Router(edges)` to initialize the router using the hardware coupling graph.
- `route(ops, n)` to route the supplied logical operations for a circuit containing `n` qubits.

The public router delegates the actual routing work to the core SABRE pass implemented in `part2/sabre_engine.py`.

This separation keeps the implementation modular:

- `router.py` handles the public interface and integration.
- `sabre_engine.py` contains the core routing algorithm.

The router preserves the expected `RoutingResult` output contract, including the routed operations and initial and final logical-to-physical layouts.

### Design decision

The public interface was kept separate from the routing algorithm so that the core implementation can be tested and maintained independently.

It also allows the final project to integrate Group 2's improved routing workflow without changing the required external interface unnecessarily.

---

## 4. Testing and Validation

After completing the Group 1 implementation, the supplied grading harness was executed using:

```bash
cd /home/harsh/Downloads/Quantum/project/QuantumProject2/part2/grader
python3 route_harness.py --router-dir .. --router router
```

### Official grading harness results

The reported result was:

- All seven supplied circuits passed the correctness gate.
- Total SWAP count: **37**.
- Qiskit baseline comparison: **OFF**, because Qiskit was not installed in the execution environment.

| Circuit | SWAP count |
|---|---:|
| GHZ | 3 |
| QFT line | 15 |
| QFT heavy-hex | 11 |
| BV | 5 |
| QAOA grid | 3 |
| Random | 0 |
| Near-Clifford | 0 |
| **Total** | **37** |

### Additional validation

The following checks were also reported during development:

- 12 additional implementation tests passed.
- Python compilation using `python3 -m compileall -q part2` completed successfully.
- The public router interface and core routing implementation were checked through the supplied harness.

The additional tests were reported by the development validation run; the official harness results above are the supplied grading results.

### Performance comparison limitation

No performance claim is made against Qiskit because the Qiskit comparison was disabled in this environment.

The reported SWAP counts establish the results for the tested circuits, but they do not establish that this implementation outperforms Qiskit or is optimal.

---

## 5. Current Status

The Group 1 implementation provides:

- A dependency-aware SABRE-style routing pass.
- Front-layer and extended look-ahead scoring.
- Candidate SWAP generation and mapping updates.
- A configurable decay penalty.
- A public `Router` interface compatible with the supplied harness.
- Documentation of the implementation and execution workflow.

All seven supplied grading circuits passed the reported correctness checks, with a total of 37 SWAPs.

The implementation is ready for integration with Group 2's reverse-traversal and improved-router components, followed by full-project benchmarking and final evaluation.
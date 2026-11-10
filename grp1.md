# Group 1 Guide — Core SABRE Routing Engine

## 1. Purpose and project context

You are Group 1 in the COL8422 Quantum Computing Systems Part 2 project: **Qubit Allocation & Routing: Beating (or Matching) SABRE**.

Your responsibility is to implement the **core SABRE routing pass**. The router receives a logical circuit (an ordered sequence of operations) and a hardware coupling graph. It must produce a physically executable sequence of gates, inserting SWAPs when required and reporting the initial and final logical-to-physical layouts.

The project specification calls for:
- A front layer of currently dependency-ready two-qubit operations.
- An extended look-ahead set.
- Candidate SWAP generation around physical qubits occupied by front-layer logical qubits.
- A distance-based SWAP cost.
- A decay mechanism to discourage repeatedly using the same physical qubits.
- Correct updates to both logical-to-physical and physical-to-logical mappings.

The minimum-SWAP routing problem is NP-hard. Do not expect a greedy heuristic to be globally optimal.

## 2. Team ownership and boundaries

### Group 1 owns
- `part2/sabre_engine.py` — core routing pass and internal helpers.
- `part2/router.py` — required public `Router` interface.
- Tests specific to core routing, mapping updates, candidate generation, and legality.

### Group 1 must not modify
- `part2/routing_common.py`
- `part2/grader/route_harness.py`
- `part2/reference_router.py`
- `part1/circuits.py`
- `part2_spec.pdf`

Keep `reference_router.py` as the untouched correctness/reference baseline. Do not change the grader to make tests pass.

Group 2 owns reverse traversal/layout optimization, improved-router orchestration, and benchmark/evaluation scripts. Coordinate any shared-interface change before implementing it.

## 3. Existing project structure

```text
part2_student_release/
├── part1/
│   ├── backends/
│   └── circuits.py
├── part2/
│   ├── grader/
│   │   ├── reference_baseline.txt
│   │   └── route_harness.py
│   ├── reference_router.py
│   └── routing_common.py
├── part2_spec.pdf
├── README.md
└── requirements.txt
```

Important existing definitions in `routing_common.py`:
- `Op`: operation representation, with a gate name, qubit tuple, and optional parameters.
- `RoutingResult`: result object containing `ops`, `initial`, and `final`.
- `RoutingResult.initial` and `.final` are logical-to-physical layouts: `layout[logical_qubit] = physical_qubit`.
- Graph helpers include line, grid, and heavy-hex coupling graphs.
- Helpers include shortest-path logic, gate counting, circuit depth, legality checks, and an independent NumPy statevector fidelity oracle.

Read the actual source before coding. Treat `routing_common.py` as the source of truth for exact class signatures and supported gate conventions.

## 4. Public router contract

The grader expects `part2/router.py` to expose:

```python
class Router:
    def __init__(self, edges):
        ...

    def route(self, ops, n):
        ...
```

The returned object must be a `RoutingResult` compatible with `routing_common.py`.

Contract:
- `edges` describes the physical coupling graph.
- `ops` is the ordered logical operation sequence.
- `n` is the number of logical qubits.
- The result's `ops` must use physical-qubit indices.
- Every two-qubit operation in the routed result must act on adjacent physical qubits.
- `initial` and `final` must accurately describe the mapping at the beginning and end.
- Preserve gate identity, parameters, and control/target order. Do not reverse CNOT or controlled-gate operands.
- SWAP operations must be explicit in the routed operation list and must update the internal mapping consistently.

The harness checks legality and equivalence while accounting for the final layout. Aim for fidelity at least `0.999`, as required by the grader.

## 5. Recommended internal architecture

The following is a proposed organization. Confirm exact names and signatures with Group 2 before freezing the interface.

### `part2/sabre_engine.py`

Suggested mapping helper:

```python
class MappingState:
    def __init__(self, n_logical, n_physical, initial_layout):
        ...

    def logical_to_physical(self, logical_qubit):
        ...

    def physical_to_logical(self, physical_qubit):
        ...

    def apply_swap(self, physical_a, physical_b):
        ...

    def snapshot_layout(self):
        ...
```

Mapping invariants:
- `logical_to_physical[l]` gives the physical position of logical qubit `l`.
- `physical_to_logical[p]` gives the logical qubit at physical position `p`, or a documented empty value if unused.
- The two maps must always be inverses for occupied positions.
- A physical SWAP between positions `a` and `b` exchanges the logical occupants of those positions.
- Emit the physical `Op("SWAP", (a, b))` whenever a routing SWAP is applied.

Suggested helper functions:

```python
def build_dependency_dag(ops):
    ...

def get_front_layer(dag_state):
    ...

def get_extended_set(dag_state, front_layer, lookahead_size):
    ...

def generate_candidate_swaps(front_layer, mapping, adjacency):
    ...

def score_candidate_swap(swap, front_layer, extended_set, mapping, config):
    ...

def run_sabre_pass(ops, n, edges, initial_layout=None, config=None):
    ...
```

These are suggested names, not definitions supplied by the starter. Refine them if needed, but keep the public `Router` contract unchanged.

### `part2/router.py`

Keep this file as a small public adapter:
- Import `Op` and `RoutingResult` from `routing_common`.
- Store the coupling graph in `Router.__init__`.
- Validate the requested logical-qubit count.
- Call the core engine.
- Return the required `RoutingResult`.

Avoid placing all algorithm logic in one very large `route()` method.

## 6. SABRE algorithm requirements

Implement based on the assigned Li, Ding & Xie SABRE paper and course specification. Do not assume a simplified teaching formula is the exact paper or Qiskit formula. Record the exact heuristic choices and parameters you implement.

A routing pass should broadly:

1. Build/maintain circuit dependencies.
2. Identify the current front layer: operations whose predecessors have all been completed.
3. Execute front-layer two-qubit operations that are already adjacent under the current mapping.
4. If blocked operations remain, construct an extended look-ahead set.
5. Generate candidate SWAPs from hardware edges incident to the physical locations of logical qubits in the front layer. Do not indiscriminately score every edge unless your documented algorithm explicitly justifies it.
6. Evaluate candidates with the selected distance-based heuristic and decay.
7. Select a candidate, emit the physical SWAP, and update both mapping directions.
8. Repeat until all operations have been routed.

Single-qubit gates should be emitted at the physical location of their logical qubit at the time they are processed.

### Dependency handling

Do not treat the input list as if every gate is independent. Preserve each qubit's operation order and all required dependencies. Operations on disjoint qubits may be independent, but only execute them when the dependency representation says they are ready.

### Decay handling

Decay discourages repeatedly selecting SWAPs involving recently used physical qubits. Implement the decay definition from the paper or a clearly documented, defensible variant. Keep decay parameters configurable so they can be tested.

### Reverse traversal

Reverse traversal/iterative layout feedback is a separate orchestration layer and is primarily Group 2's responsibility. Group 1 should expose a clean one-pass engine that accepts an initial layout and returns a final layout. This is the key integration point.

## 7. Shared interface with Group 2

Agree on this interface before either pair builds dependent code:

```python
run_sabre_pass(
    ops,
    n,
    edges,
    initial_layout=None,
    config=None,
) -> RoutingResult
```

Requirements:
- `initial_layout` is a logical-to-physical list or mapping, with one documented representation.
- If omitted, use a documented default layout.
- `RoutingResult.initial` equals the layout actually used at the start.
- `RoutingResult.final` equals the mapping after all emitted SWAPs.
- Do not mutate caller-owned `ops`, `edges`, or `initial_layout`.
- Be deterministic for fixed inputs/configuration, unless randomness is explicitly seeded and documented.

Group 2 can use `reference_router.py` or a small mock implementation while this function is being developed. Do not make Group 2 wait for the core code to begin independent work.

## 8. Starter environment and commands

Run from the repository root:

```bash
cd ~/Downloads/QT\ project/part2_student_release
python3 --version
python3 -m pip show numpy qiskit scipy matplotlib pandas
```

### Preferred virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If `python3 -m venv` fails because the lab machine lacks the `venv` module and you have no sudo access:
- Do not use sudo to install system packages.
- Use the configured user Python environment and `python3`.
- Install missing user packages with `python3 -m pip install --user -r requirements.txt`.
- Check imports before running the harness.

The previously tested environment used Python 3.10.12, NumPy 2.2.6, SciPy 1.15.3, and Qiskit 2.6.2. Check the repository's actual `requirements.txt` before installing or changing versions.

### Run the reference baseline

```bash
cd part2/grader
python3 route_harness.py
```

Save a fresh log if needed:

```bash
python3 route_harness.py 2>&1 | tee reference_baseline.txt
```

### Run Group 1 router after implementation

```bash
python3 route_harness.py --router router
```

The known working invocation is from `part2/grader`. Check `python3 route_harness.py --help` if options differ in your checkout.

## 9. Historical starter baseline

The reference router previously passed all seven harness tests with Qiskit baseline enabled:

```text
ghz_n5         line5       swaps=3   qiskit_swaps=2
qft_n5_line    line5       swaps=13  qiskit_swaps=10
qft_n5_hhex    heavyhex27  swaps=11  qiskit_swaps=7
bv_n4          line5       swaps=8   qiskit_swaps=1
qaoa_n6_grid   grid2x3     swaps=2   qiskit_swaps=0
rand_n5        line5       swaps=0   qiskit_swaps=0
nearclif_n5    line5       swaps=0   qiskit_swaps=0

correctness gate: ALL PASS | total SWAPs = 37
```

This is a seven-case smoke/baseline suite, not the full required circuit-family × graph benchmark. Re-run and retain your own logs.

## 10. Testing checklist

- [ ] `Router(edges)` constructs successfully.
- [ ] `route(ops, n)` returns the required `RoutingResult`.
- [ ] Initial/final layouts follow the documented convention.
- [ ] Mapping invariants hold after every SWAP.
- [ ] Candidate SWAPs are legal hardware edges.
- [ ] Every routed two-qubit gate acts on adjacent physical qubits.
- [ ] Single-qubit gates use the current physical location.
- [ ] CNOT/control-target ordering is preserved.
- [ ] Circuit dependencies and per-qubit ordering are preserved.
- [ ] The full provided harness passes.
- [ ] Line, grid, and heavy-hex graphs are handled.
- [ ] Results are deterministic or randomness is seeded.
- [ ] No protected starter/grader files were modified.

## 11. Git workflow

The repository currently has `master` and one initial commit. Planned branches:
- `one` — Group 1.
- `two` — Group 2.
- `master` — final integration/submission.

Create Group 1's branch from the agreed current `master`:

```bash
git switch master
git pull origin master
git switch -c one
git push -u origin one
```

Before committing:

```bash
git status
git diff
python3 -m compileall part2
```

Commit only Group 1-owned files:

```bash
git add part2/router.py part2/sabre_engine.py
git commit -m "Implement core SABRE routing engine"
git push -u origin one
```

Use small, meaningful commits. Do not force-push shared branches. On another machine:

```bash
git switch one
git pull origin one
```

Do not merge Group 2's branch into `one`. The project lead will integrate both branches on `master` after review.

## 12. Coding and LLM collaboration expectations

All code must be **human-understandable, maintainable, and explainable by the team**. “Humanized” does not mean adding artificial comments or disguising AI-generated code.

When using an LLM:
- Give it this guide and the relevant source files.
- Ask it to inspect existing code before proposing edits.
- Ask for small, reviewable changes rather than a full repository rewrite.
- Require explanations of algorithms, data structures, invariants, and complexity.
- Require tests for every meaningful change.
- Preserve existing interfaces and protected files.
- Avoid unnecessary abstractions, excessive comments, generic boilerplate, and unexplained magic constants.
- Use meaningful names and concise comments for non-obvious decisions.
- The team must be able to explain every submitted function during the oral defense.
- Never claim a test passed unless it was actually run.

## 13. Handoff to Group 2

Provide:
1. `router.py` and `sabre_engine.py`.
2. Exact one-pass function signature and layout representation.
3. SABRE cost/decay formula and parameter values, with paper/source reference.
4. A short note explaining dependency tracking and candidate generation.
5. Harness output and known limitations.
6. Commit hash for integration.

Group 1 is ready for handoff when the core one-pass router is correct, documented, tested, and exposes the agreed interface.

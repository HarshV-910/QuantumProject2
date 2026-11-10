# Group 2 Guide — Reverse Traversal, Layout Optimization, Improvements & Evaluation

## 1. Purpose and project context

You are Group 2 in the COL8422 Quantum Computing Systems Part 2 project: **Qubit Allocation & Routing: Beating (or Matching) SABRE**.

Your responsibility is to build the optimization and evaluation layer around the core SABRE routing pass:
- Reverse traversal / iterative layout feedback.
- Initial-layout optimization and layout experiments.
- One justified improvement over the team's baseline SABRE.
- Ablation experiments.
- Benchmarking against Qiskit SABRE.
- Result tables, plots, and evaluation notes.

Work in parallel with Group 1. Do not wait for their complete implementation. Use the existing `reference_router.py`, the proposed one-pass interface below, and a small mock/stub where needed. Integrate with Group 1 once their engine is available.

## 2. Team ownership and boundaries

### Group 2 owns
- `part2/layout_optimizer.py` — reverse traversal and layout optimization orchestration.
- `part2/router_improved.py` — improved router entry point and selected improvement.
- `part2/benchmark.py` — benchmark orchestration, if a separate script is useful.
- `part2/results/` — generated CSVs, plots, and concise experiment notes.
- Documentation of experiments and ablation.

### Group 2 must not directly modify
- `part2/sabre_engine.py`
- `part2/router.py`
- `part2/routing_common.py`
- `part2/grader/route_harness.py`
- `part2/reference_router.py`
- `part1/circuits.py`

Group 1 owns the core SABRE engine and baseline router. If a core change is needed, describe the issue and coordinate it; do not independently fork or rewrite the core algorithm.

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

Useful existing components in `routing_common.py`:
- `Op` and `RoutingResult`.
- Coupling graph builders for line, grid, and heavy-hex.
- Shortest-path and graph-neighbor helpers.
- Independent NumPy statevector equivalence/fidelity oracle.
- Legality, gate-count, and circuit-depth helpers.

Read the actual source before coding. `routing_common.py` is authoritative for exact field names and helper signatures.

## 4. Required public interface and Group 1 dependency

The grader expects `part2/router.py` to expose:

```python
class Router:
    def __init__(self, edges):
        ...

    def route(self, ops, n):
        ...
```

Group 1 is implementing the core one-pass engine. The proposed shared internal contract is:

```python
run_sabre_pass(
    ops,
    n,
    edges,
    initial_layout=None,
    config=None,
) -> RoutingResult
```

**Confirm this exact signature and layout representation with Group 1 before writing integration code.** This function does not currently exist in the starter release; it is a proposed team interface.

While Group 1 implements it, you can:
- Study reverse traversal in the SABRE paper.
- Design the optimizer API and tests.
- Use `reference_router.py` as a temporary one-pass implementation.
- Write benchmark CSV/plot code.
- Explore a candidate improvement.
- Build a mock `run_sabre_pass` obeying the proposed contract to test orchestration only.

Do not write code that assumes unverified fields or helper methods exist.

## 5. Recommended file and function structure

```text
part2/
├── router.py                 # Group 1: baseline public Router
├── sabre_engine.py           # Group 1: one-pass SABRE engine
├── layout_optimizer.py       # Group 2: reverse traversal / layout search
├── router_improved.py        # Group 2: improved public Router
├── benchmark.py              # Group 2: benchmark driver
├── results/
│   ├── baseline.csv
│   ├── improved.csv
│   ├── ablation.csv
│   └── plots/
├── reference_router.py       # Existing; keep unchanged
├── routing_common.py         # Existing; keep unchanged
└── grader/
    └── route_harness.py      # Existing; keep unchanged
```

### `part2/layout_optimizer.py`

Suggested API:

```python
def reverse_ops(ops):
    ...

def optimize_initial_layout(
    ops,
    n,
    edges,
    run_one_pass,
    initial_layout=None,
    iterations=2,
    config=None,
):
    ...
```

These are proposed function names, not starter-code APIs.

The optimizer should:
- Work with the shared one-pass router callback.
- Keep layout representation consistent with Group 1.
- Return a valid `RoutingResult` or a clearly documented optimization result object.
- Record the number of passes and objective used.
- Avoid mutating input operations or layouts.

Important conceptual distinction:
- Reverse traversal is a **layout optimization procedure**.
- It is not execution of the quantum circuit backwards and does not mean replacing every gate with its inverse.
- Reverse traversal uses a reversed dependency/order view to obtain a useful layout, then feeds layout information into another routing pass.
- Be careful about reversing operations that share qubits: preserve a valid reverse dependency order and do not casually reverse controlled-gate operand order.

### `part2/router_improved.py`

Suggested responsibilities:
- Expose the same `Router(edges)` / `route(ops, n)` contract expected by the harness when invoked in improved mode.
- Use the core one-pass engine and layout optimizer.
- Implement one selected improvement beyond the team's baseline SABRE, or clearly isolate the improvement being evaluated.
- Keep baseline behavior available so the improvement can be compared fairly.
- Make improvement parameters configurable and record them.

Potential stretch ideas in the project specification include:
- A weighted or larger look-ahead set.
- Tuned decay parameters.
- A better initial layout.
- Bridge gates for suitable two-hop CNOT situations.
- Commutation-aware reordering.

Do not implement all ideas at once. Choose one, justify why it may help, and measure it. If a technique changes circuit semantics or the supported gate model, validate carefully with the independent fidelity oracle.

### `part2/benchmark.py`

Suggested helpers:

```python
def run_benchmark_case(circuit_name, graph_name, router_factory, ...):
    ...

def collect_benchmark_matrix(...):
    ...

def save_results_csv(rows, output_path):
    ...

def plot_swap_comparison(csv_path, output_path):
    ...

def plot_depth_comparison(csv_path, output_path):
    ...
```

Inspect the actual circuit generators and graph builders before choosing function arguments. Do not invent circuit names or graph APIs.

## 6. Reverse traversal: implementation considerations

The required main SABRE implementation includes reverse-traversal initial mapping/layout feedback. Study the assigned Li, Ding & Xie paper and course notes before coding.

At a high level, the layout optimizer should:
1. Obtain a starting layout.
2. Run a forward one-pass routing procedure.
3. Use the resulting layout as feedback for a reverse-oriented pass, following the paper's procedure.
4. Use the layout produced by that procedure to seed a subsequent forward pass.
5. Repeat only the specified/selected number of iterations.
6. Compare candidates using a consistent objective, such as SWAP count, and retain the best valid result.

Do not assume that simply reversing the Python list of operations is always a valid reverse dependency order. Build or use dependency information so operations sharing qubits are handled correctly. Do not invert gate names unless the algorithm specifically requires inverse circuit simulation; layout search itself is not physical reverse execution.

Check the exact SABRE reverse-pass convention and iteration strategy against the paper and document it. Do not present an unverified simplification as the exact algorithm.

## 7. Improvement and ablation plan

The assignment requires one justified improvement over the team's baseline SABRE and an ablation.

Recommended workflow:
1. Run baseline SABRE on a fixed benchmark suite.
2. Select one improvement and state the hypothesis.
3. Change only the relevant parameter or mechanism.
4. Run the same cases with identical seeds and settings.
5. Compare SWAP count first, then depth and two-qubit count.
6. Perform an ablation: disable the improvement while keeping the rest of the improved router unchanged.
7. Report aggregate results and representative per-case outcomes.
8. Discuss cases where the improvement does not help.

Ablation should isolate the effect of the selected change. Avoid comparing unrelated configurations and attributing all differences to one feature.

## 8. Benchmarking requirements

The project specification requires a broader circuit-family × graph evaluation than the seven-case smoke test in the starter harness. Include the required families and supported topologies from the official specification, and record unavailable or optional cases explicitly.

The provided harness's Qiskit comparison protocol is:
- SWAP count: Qiskit `transpile(..., layout_method='sabre', routing_method='sabre', optimization_level=0)`, count SWAPs before decomposition.
- Depth and two-qubit count: Qiskit optimization level 3.
- Use the same circuit and coupling graph for each comparison.
- Record seed and Qiskit version.

Use ratios/overheads relative to the unrouted circuit as specified by the assignment. Define denominators clearly and avoid dividing by zero; document how zero-SWAP or zero-two-qubit baselines are represented.

The current harness has seven built-in cases. These are useful for smoke tests, but are not by themselves the complete required benchmark matrix.

### Historical starter baseline

The reference router previously passed all seven starter harness tests with Qiskit baseline enabled:

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

This is historical starter data, not a guaranteed result on every machine and not a final benchmark conclusion. Re-run and save fresh results.

## 9. Starter environment and commands

From the repository root:

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

If the lab machine lacks the `venv` module and you have no sudo privileges:
- Do not use sudo.
- Use the configured user Python environment.
- Install missing dependencies with `python3 -m pip install --user -r requirements.txt`.
- Use `python3` consistently.

The previously tested environment used Python 3.10.12, NumPy 2.2.6, SciPy 1.15.3, and Qiskit 2.6.2. Check the actual `requirements.txt` before installing or changing versions. Coordinate dependency changes with the project lead.

### Run starter reference baseline

```bash
cd part2/grader
python3 route_harness.py
```

### Run Group 1 baseline after integration

```bash
python3 route_harness.py --router router
```

### Run improved router after integration

```bash
python3 route_harness.py --improved
```

Check `python3 route_harness.py --help` in the actual checkout before relying on optional flags or CSV arguments. The known working directory is `part2/grader`.

## 10. Part 1 simulator stress plot

The assignment also asks for a Part 1 simulator stress plot, such as runtime versus qubit count for unrouted and routed QFT and/or random circuits.

The current `part1/backends/` and `part1/circuits.py` have been retained for this deliverable. They are not the routing correctness oracle; the routing harness uses its own independent NumPy statevector oracle.

Prepare the experiment design early, but inspect the actual Part 1 backend APIs and circuit generator signatures first. Do not assume all backends support the same gate set or that a compiled shared library exists on every machine.

Record:
- Backend and simulator version.
- Circuit family and qubit count.
- Routed/unrouted input and mapping convention.
- Number of repetitions and timing method.
- Runtime units and warm-up policy.
- Whether compilation/setup time is included.
- Backend limitations or failed sizes.

Do not compare runtimes unless the measured work is equivalent and the setup is documented.

## 11. Git workflow

The repository currently has `master` and one initial commit. Planned branches:
- `one` — Group 1.
- `two` — Group 2.
- `master` — final integration/submission.

Create Group 2's branch from the agreed current `master`:

```bash
git switch master
git pull origin master
git switch -c two
git push -u origin two
```

Before committing:

```bash
git status
git diff
python3 -m compileall part2
```

Commit only Group 2-owned files:

```bash
git add part2/layout_optimizer.py part2/router_improved.py part2/benchmark.py part2/results
git commit -m "Add layout optimization and routing evaluation"
git push -u origin two
```

Only add paths that exist. Do not commit generated Python bytecode, `.so` files, virtual environments, or temporary logs unless the team explicitly decides they are deliverables.

On another machine:

```bash
git switch two
git pull origin two
```

Do not routinely merge Group 1's branch into `two`. The project lead will integrate both branches on `master` after review.

## 12. Coding and LLM collaboration expectations

All code must be **human-understandable, maintainable, and explainable by the team**. “Humanized” does not mean adding artificial comments or disguising AI-generated code.

When using an LLM:
- Give it this guide plus the exact source files it needs.
- Ask it to inspect actual source code and confirm interfaces before editing.
- Ask for one focused change at a time.
- Ask it to explain algorithm choices, invariants, complexity, and trade-offs.
- Require tests and reproducible measurements.
- Keep baseline and improved implementations distinguishable.
- Avoid unnecessary abstractions, excessive comments, generic boilerplate, and unexplained magic constants.
- Use meaningful names and concise comments for non-obvious logic.
- Do not fabricate benchmark values or claim unrun experiments passed.
- Every member must understand and explain the code during the oral defense.

## 13. Group 2 handoff and final integration

Provide:
1. `layout_optimizer.py` with documented reverse-traversal behavior.
2. `router_improved.py` with the selected improvement clearly isolated.
3. Ablation methodology and raw data.
4. Benchmark scripts and raw CSV outputs.
5. Plots generated from raw data.
6. Part 1 simulator stress-plot methodology/results.
7. A short note describing the agreed Group 1 interface and integration requirements.
8. Commit hash for Group 2's branch.

Before final merge, verify:
- Baseline and improved routers use the same input/output contract.
- Full harness correctness passes for both.
- SWAP/depth/two-qubit metrics are collected consistently.
- Qiskit comparison uses the specified optimization levels.
- Full benchmark matrix is covered or omissions are explained.
- Ablation isolates the selected improvement.
- Plots are reproducible from committed CSV data.
- No protected starter/grader files were changed.

The final merge into `master` is performed by the project lead after both groups' work is reviewed. Run the complete final test suite after merging; do not rely only on each branch's individual test result.

# COL8422 Project — Part 2: Qubit Allocation & Routing (SABRE)

Turn an arbitrary logical circuit into one that is **executable on a device with
limited connectivity** — choose an initial qubit layout, insert SWAPs to make
every two-qubit gate act on adjacent physical qubits — then prove it is correct
on your Part 1 simulator and benchmark it against **Qiskit's SABRE** transpiler.

Read **`part2_spec.pdf`** first. This README is just the mechanics.

---

## What's in this bundle

```
part1/
  circuits.py          # Part-1 circuit generators (provided; do NOT modify)
part2/
  routing_common.py    # Op, RoutingResult, capture(), coupling graphs,
                        #   legality/fidelity/metric helpers, numpy oracle
                        #   (provided; do NOT modify)
  reference_router.py  # Core-tier starter: identity layout + shortest-path
                        #   SWAP insertion. Your starting point.
  grader/
    route_harness.py   # the auto-grader — run it yourself, early and often
part2_spec.pdf         # the full specification
```

`circuits.py` is the same file you were given in Part 1. If your group already
has it, you do not need this copy — it is included only so the grader runs
standalone.

---

## What you submit

Inside your group's `part2/` directory:

- **`router.py`** — your SABRE implementation, defining a class `Router`
  with the exact contract below (Main tier).
- **`router_improved.py`** — one concrete, justified improvement over your own
  baseline SABRE, same `Router` contract (Stretch tier).
- the report, design-journal update, and the plots described in the spec.

Do **not** modify `routing_common.py`, `circuits.py`, or `route_harness.py` —
the graded run uses the originals.

### The `Router` contract

```python
from routing_common import Op, RoutingResult, neighbours, shortest_path

class Router:
    name = "sabre"                 # short label used in reports

    def __init__(self, edges):     # edges: list of (u, v), undirected
        ...

    def route(self, ops, n):
        # ops : list[Op] on n LOGICAL qubits
        # n   : number of logical qubits
        # returns RoutingResult(ops=<physical Op list>,
        #                       initial=<logical->physical layout, len n>,
        #                       final=<logical->physical layout after routing>)
        ...
```

`RoutingResult.ops` must contain **only legal two-qubit gates** (each pair on a
coupling edge) and must differ from the input only by (a) relabelling qubits per
`initial` and (b) inserted `SWAP` gates. Track where each logical qubit ends up
in `final` — equivalence is checked **after** undoing that output permutation.

---

## Running the auto-grader

From `part2/grader/`:

```bash
# self-test with the provided reference router
python route_harness.py

# test YOUR router (place router.py in part2/)
python route_harness.py --router router

# with your improvement, and save a metrics CSV
python route_harness.py --router router --improved router_improved \
                        --csv results/mine.csv
```

The grader runs, per router:

1. **Legality** — every routed two-qubit gate lies on a coupling edge.
2. **Equivalence** — routed ≡ original at fidelity ≥ 0.999 (a trusted numpy
   oracle; needs neither Qiskit nor your C++ backend).
3. **Metrics** — inserted SWAPs / two-qubit count / depth, and the Qiskit SABRE
   baseline when Qiskit is installed.
4. **Improvement delta** — `--improved` reports SWAP total vs your baseline.

**The correctness gate (1 + 2) is a hard prerequisite** — a routing that fails
legality or equivalence earns no metric credit. The grader names the circuit
that fails.

### Requirements

- `numpy` — required (legality + equivalence + your own metrics).
- `qiskit` (2.x) — optional locally; only needed for the SABRE comparison
  column. It is installed on the lab image, so your graded comparison always
  runs there. Without it, that column shows `n/a`.

---

## Tiers (see the spec for detail)

- **Core** — understand/pass with the reference router (shortest-path).
- **Main** — implement SABRE: front layer + look-ahead cost (with decay) +
  reverse-traversal initial mapping. Benchmark vs Qiskit.
- **Stretch** — improve on your own SABRE and show the gain with an ablation.

**Deadline: Nov 17.**

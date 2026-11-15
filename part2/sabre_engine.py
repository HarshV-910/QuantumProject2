from __future__ import annotations

from collections import defaultdict, deque

from routing_common import Op, RoutingResult, neighbours, shortest_path

DEFAULT_CONFIG = {
    "lookahead": 10,
    "front_weight": 1.0,
    "lookahead_weight": 0.5,
    "decay": 0.1,
    "decay_step": 1,
}


def _effective_config(config):
    """Merge caller configuration with the documented SABRE defaults."""
    merged = DEFAULT_CONFIG.copy()
    if config:
        unknown = set(config) - set(DEFAULT_CONFIG)
        if unknown:
            raise ValueError(f"unknown routing config keys: {sorted(unknown)}")
        merged.update(config)

    for key in ("lookahead", "decay_step"):
        if int(merged[key]) < 0:
            raise ValueError(f"{key} must be non-negative")
    for key in ("front_weight", "lookahead_weight", "decay"):
        if float(merged[key]) < 0:
            raise ValueError(f"{key} must be non-negative")
    if int(merged["decay_step"]) < 1:
        raise ValueError("decay_step must be at least 1")
    return merged


class MappingState:
    """Track the logical-to-physical layout and its inverse."""

    def __init__(self, n_logical, n_physical, initial_layout):
        self.n_logical = int(n_logical)
        self.n_physical = int(n_physical)
        layout = list(initial_layout)
        if len(layout) != self.n_logical:
            raise ValueError(f"layout length mismatch: expected {self.n_logical}, got {len(layout)}")
        if len(set(layout)) != len(layout):
            raise ValueError("layout must assign each logical qubit to a unique physical qubit")
        if any(p < 0 or p >= self.n_physical for p in layout):
            raise ValueError("initial layout contains a physical qubit outside the device range")

        self.log_to_phys = list(layout)
        self.phys_to_log = [None] * self.n_physical
        for logical, physical in enumerate(self.log_to_phys):
            self.phys_to_log[physical] = logical

    def logical_to_physical(self, logical_qubit):
        return self.log_to_phys[int(logical_qubit)]

    def physical_to_logical(self, physical_qubit):
        return self.phys_to_log[int(physical_qubit)]

    def apply_swap(self, physical_a, physical_b):
        if physical_a == physical_b:
            return
        if physical_a < 0 or physical_a >= self.n_physical:
            raise ValueError(f"swap endpoint {physical_a} is outside the device")
        if physical_b < 0 or physical_b >= self.n_physical:
            raise ValueError(f"swap endpoint {physical_b} is outside the device")

        la = self.phys_to_log[physical_a]
        lb = self.phys_to_log[physical_b]
        self.phys_to_log[physical_a], self.phys_to_log[physical_b] = lb, la
        if la is not None:
            self.log_to_phys[la] = physical_b
        if lb is not None:
            self.log_to_phys[lb] = physical_a

    def snapshot_layout(self):
        return list(self.log_to_phys)


def _normalize_layout(layout, n_logical: int) -> list[int]:
    if layout is None:
        return list(range(n_logical))
    if isinstance(layout, dict):
        norm = [None] * n_logical
        for logical, physical in layout.items():
            norm[int(logical)] = int(physical)
        if any(v is None for v in norm):
            raise ValueError("layout dict does not cover every logical qubit")
        return norm
    layout_list = list(layout)
    if len(layout_list) != n_logical:
        raise ValueError(f"layout length mismatch: expected {n_logical}, got {len(layout_list)}")
    return [int(v) for v in layout_list]

def build_distance_table(adj):
    """
    Compute shortest-path distances between all physical qubits once.

    The hardware coupling graph is fixed during routing, so these distances
    can be reused for every candidate SWAP in this SABRE pass.
    """
    distances = {}

    for source in adj:
        dist = {source: 0}
        queue = deque([source])

        while queue:
            u = queue.popleft()

            for v in adj.get(u, ()):
                if v not in dist:
                    dist[v] = dist[u] + 1
                    queue.append(v)

        distances[source] = dist

    return distances


def build_dependency_dag(ops):
    """Build per-op predecessor/successor lists from qubit-wise ordering."""
    preds = [set() for _ in ops]
    succs = [[] for _ in ops]
    last_by_qubit = {}
    for idx, op in enumerate(ops):
        for q in op.qubits:
            prev = last_by_qubit.get(q)
            if prev is not None:
                preds[idx].add(prev)
                succs[prev].append(idx)
            last_by_qubit[q] = idx
    return preds, succs


def get_front_layer(ops, preds, processed):
    return [
        idx for idx in range(len(ops))
        if idx not in processed and all(p in processed for p in preds[idx])
    ]


def get_extended_set(ops, front_layer, processed, lookahead, succs=None):
    """Collect upcoming dependency successors from the current front layer.

    This follows the circuit dependency graph instead of simply choosing the next
    unprocessed operation in original list order. The frontier itself is a set of
    currently ready operations; the extended set grows by traversing each
    operation's immediate successors until the configured look-ahead limit is met.
    """
    if lookahead <= 0 or not front_layer:
        return []

    if succs is None:
        _, succs = build_dependency_dag(ops)

    seen = set(front_layer)
    queue = deque(front_layer)
    chosen = []
    while queue and len(chosen) < lookahead:
        idx = queue.popleft()
        for nxt in succs[idx]:
            if nxt in processed or nxt in seen:
                continue
            seen.add(nxt)
            chosen.append(nxt)
            queue.append(nxt)
    return [ops[idx] for idx in chosen[:lookahead]]


def _gate_distance(op, mapping, adj, distance_table):
    if not op.is_2q:
        return 0

    q0, q1 = op.qubits
    p0 = mapping.logical_to_physical(q0)
    p1 = mapping.logical_to_physical(q1)
    return distance_table.get(p0, {}).get(p1, 10**9)


def generate_candidate_swaps(front_layer_ops, mapping, adj):
    """Select SWAPs incident to the physical qubits occupied by the front layer."""
    positions = set()
    for op in front_layer_ops:
        if not op.is_2q:
            continue
        q0, q1 = op.qubits
        positions.add(mapping.logical_to_physical(q0))
        positions.add(mapping.logical_to_physical(q1))

    candidates = set()
    for p in positions:
        for nb in adj.get(p, set()):
            a, b = sorted((p, nb))
            candidates.add((a, b))
    return sorted(candidates)


def _decay_recent_swaps(recent_swaps, decay_step):
    """Decay the recent-use table between routing choices.

    The penalty increases when a qubit is reused in a newly chosen SWAP and then
    gradually fades after that SWAP is no longer the most recent movement.  The
    decay step is a configurable reduction factor: repeated activity keeps the
    qubit hot for a short window, but a quiet period lowers the penalty back to
    zero instead of letting it grow without bound.
    """
    for p in list(recent_swaps):
        recent_swaps[p] = max(0, recent_swaps[p] - int(decay_step))
        if recent_swaps[p] == 0:
            del recent_swaps[p]


def _decay_penalty(recent_swaps, swap, decay_base):
    """Compute a short-lived SABRE-style decay penalty from recent qubit reuse."""
    total = 0.0
    for p in swap:
        count = recent_swaps.get(p, 0)
        total += decay_base * (count + 1.0)
    return total


def score_candidate_swap(swap,front_layer,extended_set,mapping,adj,distance_table,recent_swaps,config,):
    """Score as: (front_weight * ΔF + lookahead_weight * ΔE) + decay_penalty.

    ΔF and ΔE are the total shortest-path distances of the ready front layer and
    the dependency-based extended look-ahead set.  The decay term is a short-lived
    penalty proportional to the recent activity of the candidate's physical
    qubits.  It increases immediately when a physical qubit is reused in a newly
    selected SWAP and then decays back toward zero when that qubit is not used
    again, instead of growing forever with a monotone accumulator.
    """
    front_weight = float(config.get("front_weight", 1.0))
    lookahead_weight = float(config.get("lookahead_weight", 0.5))
    decay_base = float(config.get("decay", 0.1))

    decay_penalty = _decay_penalty(
        recent_swaps, swap, decay_base
    )

    def cost_for(ops, current_mapping):
        return sum(
            _gate_distance(op, current_mapping, adj, distance_table)
            for op in ops
            if op.is_2q
        )

    before = (
        front_weight * cost_for(front_layer, mapping)
        + lookahead_weight * cost_for(extended_set, mapping)
    )

    trial = MappingState(
        mapping.n_logical,
        mapping.n_physical,
        mapping.snapshot_layout(),
    )
    trial.apply_swap(*swap)

    after = (
        front_weight * cost_for(front_layer, trial)
        + lookahead_weight * cost_for(extended_set, trial)
    )

    return (after - before) + decay_penalty


def run_sabre_pass(ops, n, edges, initial_layout=None, config=None):
    """Run the Group 1 core SABRE routing loop.

    The algorithm keeps a dependency-based front layer; when a ready 2Q gate is not
    adjacent under the current layout, it generates SWAPs from the physical neighbors
    of the front-layer qubits, scores them with a distance-based SABRE heuristic, and
    applies the best candidate. The loop continues until every operation has been
    executed while preserving logical dependencies and output layout tracking.
    """
    ops = list(ops)
    if n <= 0:
        return RoutingResult(ops=[], initial=[], final=[])
    if not edges:
        raise ValueError("routing graph must contain at least one edge")

    n_phys = 1 + max((max(u, v) for u, v in edges), default=0)
    if n > n_phys:
        raise ValueError(f"requested {n} logical qubits on a {n_phys}-qubit graph")

    config = _effective_config(config)
    lookahead = int(config.get("lookahead", 10))
    decay_step = int(config.get("decay_step", 1))
    initial = _normalize_layout(initial_layout, n)
    mapping = MappingState(n, n_phys, initial)
    adj = neighbours(edges)
    distance_table = build_distance_table(adj)
    preds, succs = build_dependency_dag(ops)
    processed = set()
    out = []
    recent_swaps = defaultdict(int)

    while len(processed) < len(ops):
        ready = get_front_layer(ops, preds, processed)
        if not ready:
            raise ValueError("dependency cycle: operations cannot be scheduled")

        executed_gate = False
        for idx in ready:
            op = ops[idx]
            if not op.is_2q:
                continue
            q0, q1 = op.qubits
            p0 = mapping.logical_to_physical(q0)
            p1 = mapping.logical_to_physical(q1)
            if p1 in adj.get(p0, set()):
                out.append(Op(op.gate, (p0, p1), dict(op.params)))
                processed.add(idx)
                executed_gate = True
                break

        if executed_gate:
            _decay_recent_swaps(recent_swaps, decay_step)
            continue

        ready_2q_indices = [idx for idx in ready if ops[idx].is_2q]
        if not ready_2q_indices:
            idx = ready[0]
            op = ops[idx]
            q = op.qubits[0]
            p = mapping.logical_to_physical(q)
            out.append(Op(op.gate, (p,), dict(op.params)))
            processed.add(idx)
            _decay_recent_swaps(recent_swaps, decay_step)
            continue

        front_layer = [ops[idx] for idx in ready_2q_indices]
        extended_set = get_extended_set(ops, ready_2q_indices, processed, lookahead, succs)
        candidate_swaps = generate_candidate_swaps(front_layer, mapping, adj)
        if not candidate_swaps:
            raise ValueError("front layer has no admissible SWAP candidates on the coupling graph")

        for idx in ready_2q_indices:
            op = ops[idx]
            q0, q1 = op.qubits
            p0 = mapping.logical_to_physical(q0)
            p1 = mapping.logical_to_physical(q1)
            if p1 not in adj.get(p0, set()):
                try:
                    if p1 not in distance_table.get(p0, {}):
                        raise ValueError(
                            f"required interaction between logical qubits {q0} and {q1} "
                            f"(physical {p0} and {p1}) is disconnected from the coupling graph"
                        )
                except ValueError as exc:
                    raise ValueError(
                        f"required interaction between logical qubits {q0} and {q1} "
                        f"(physical {p0} and {p1}) is disconnected from the coupling graph"
                    ) from exc

        best_swap = None
        best_score = None
        for swap in candidate_swaps:
            score = score_candidate_swap(swap, front_layer, extended_set, mapping, adj, distance_table, recent_swaps, config)
            if best_score is None or score < best_score:
                best_score = score
                best_swap = swap

        if best_swap is None:
            raise ValueError("failed to choose a valid SWAP candidate")

        a, b = best_swap
        out.append(Op("SWAP", (a, b)))
        mapping.apply_swap(a, b)
        _decay_recent_swaps(recent_swaps, decay_step)
        recent_swaps[a] = recent_swaps.get(a, 0) + 1
        recent_swaps[b] = recent_swaps.get(b, 0) + 1

    final_layout = mapping.snapshot_layout()
    return RoutingResult(ops=out, initial=list(initial), final=final_layout)


__all__ = ["MappingState", "build_dependency_dag", "get_front_layer", "get_extended_set", "run_sabre_pass"]

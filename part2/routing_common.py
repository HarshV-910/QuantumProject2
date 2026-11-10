# COL8422 Quantum Computing Systems -- Project Part 2 (Routing)
# PROVIDED FILE -- do not modify.  The grader imports this exact module.
#
# This module gives you everything you need to turn a logical circuit into an
# Op list, express a coupling graph, and (for your own testing) check that a
# routed circuit is functionally equivalent to the original.
#
# Bit / qubit convention (matches the Part-1 common interface `sample`):
#   qubit 0 is the LEFTMOST character of a bit-string and the MOST significant
#   bit of a basis index:  index = sum_q bit[q] * 2**(n-1-q).
#
# Public API
# ----------
#   Op(gate, qubits, params)            one gate occurrence
#   RoutingResult(ops, initial, final)  what Router.route must return
#   RecordingSimulator                  captures a circuits.py generator -> [Op]
#   capture(generator, n, *a, **k)      convenience wrapper -> [Op]
#   replay(ops, sim)                    apply an Op list to any QuantumSimulator
#   line_edges / grid_edges / heavy_hex_edges   coupling graphs
#   neighbours(edges)                   adjacency dict
#   is_legal(ops, edges)                every 2q gate on adjacent phys qubits?
#   simulate(ops, n)                    trusted numpy statevector oracle
#   fidelity(ops_a, ops_b, n, perm)     |<a|P b>|^2 with output permutation
#   circuit_depth(ops)                  simple ASAP depth
#   gate_counts(ops)                    {'1q':.., '2q':.., 'swap':..}

from __future__ import annotations

import cmath
import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

import numpy as np

__all__ = [
    "Op", "RoutingResult", "RecordingSimulator", "capture", "replay",
    "line_edges", "grid_edges", "heavy_hex_edges", "neighbours",
    "is_legal", "simulate", "fidelity", "circuit_depth", "gate_counts",
]

_ONE_Q = {"H", "X", "Y", "Z", "S", "T", "U"}
_TWO_Q = {"CNOT", "CZ", "SWAP", "CU"}


# ---------------------------------------------------------------------------
# Op / RoutingResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Op:
    """One gate occurrence.

    gate    : gate string, e.g. 'H', 'CNOT', 'U', 'CU', 'SWAP'.
    qubits  : tuple of qubit indices (len 1 for 1q gates, len 2 for 2q gates;
              for controlled gates qubits = (ctrl, tgt)).
    params  : keyword params for parameterised gates (theta/phi/lam), else {}.
    """
    gate: str
    qubits: tuple[int, ...]
    params: dict[str, float] = field(default_factory=dict)

    @property
    def is_2q(self) -> bool:
        return len(self.qubits) == 2


@dataclass
class RoutingResult:
    """Return type of Router.route.

    ops     : routed Op list on PHYSICAL qubits.  Every 2q Op must act on a
              pair of physically adjacent qubits.
    initial : initial layout, initial[logical] = physical (len n).
    final   : layout after routing, final[logical] = physical (len n).
              (Tracks where each logical qubit ends up after SWAPs.)
    """
    ops: list[Op]
    initial: list[int]
    final: list[int]


# ---------------------------------------------------------------------------
# Capturing a circuits.py generator into an Op list
# ---------------------------------------------------------------------------

class RecordingSimulator:
    """A duck-typed stand-in for a QuantumSimulator that records gates.

    Drive any Part-1 `circuits.py` generator with an instance of this class
    and read `.ops` afterwards.  Only the gate-application surface is needed.
    """

    def __init__(self) -> None:
        self.ops: list[Op] = []
        self._n = 0

    def initialize(self, n: int) -> None:
        self._n = n
        self.ops = []

    @property
    def n_qubits(self) -> int:
        return self._n

    def apply_1q_gate(self, gate: str, qubit: int, **params: Any) -> None:
        if gate not in _ONE_Q:
            raise ValueError(f"unknown 1q gate {gate!r}")
        self.ops.append(Op(gate, (int(qubit),), dict(params)))

    def apply_2q_gate(self, gate: str, ctrl: int, tgt: int, **params: Any) -> None:
        if gate not in _TWO_Q:
            raise ValueError(f"unknown 2q gate {gate!r}")
        self.ops.append(Op(gate, (int(ctrl), int(tgt)), dict(params)))


def capture(generator: Callable[..., None], n: int, *args: Any, **kwargs: Any) -> list[Op]:
    """Run `generator(rec, n, *args, **kwargs)` and return the recorded Op list."""
    rec = RecordingSimulator()
    rec.initialize(n)
    generator(rec, n, *args, **kwargs)
    return rec.ops


def replay(ops: Sequence[Op], sim: Any) -> None:
    """Apply an Op list to any object with apply_1q_gate / apply_2q_gate."""
    for op in ops:
        if op.is_2q:
            sim.apply_2q_gate(op.gate, op.qubits[0], op.qubits[1], **op.params)
        else:
            sim.apply_1q_gate(op.gate, op.qubits[0], **op.params)


# ---------------------------------------------------------------------------
# Coupling graphs  (undirected edge lists)
# ---------------------------------------------------------------------------

def line_edges(n: int) -> list[tuple[int, int]]:
    """Linear chain 0-1-2-...-(n-1)."""
    return [(i, i + 1) for i in range(n - 1)]


def grid_edges(rows: int, cols: int) -> tuple[list[tuple[int, int]], int]:
    """2D grid; returns (edges, n). Qubit id = r*cols + c."""
    e: list[tuple[int, int]] = []
    for r in range(rows):
        for c in range(cols):
            q = r * cols + c
            if c + 1 < cols:
                e.append((q, q + 1))
            if r + 1 < rows:
                e.append((q, q + cols))
    return e, rows * cols


# IBM "heavy-hex" 27-qubit (Falcon) coupling map -- a standard sparse topology.
_HEAVY_HEX_27 = [
    (0, 1), (1, 2), (1, 4), (2, 3), (3, 5), (4, 7), (5, 8),
    (6, 7), (7, 8), (8, 9), (8, 11), (9, 10), (10, 12), (11, 14),
    (12, 13), (12, 15), (13, 14), (14, 16), (15, 18), (16, 19),
    (17, 18), (18, 19), (19, 20), (19, 22), (20, 21), (21, 23),
    (22, 25), (23, 24), (24, 25), (25, 26),
]


def heavy_hex_edges() -> tuple[list[tuple[int, int]], int]:
    """IBM 27-qubit heavy-hex coupling map; returns (edges, 27)."""
    return list(_HEAVY_HEX_27), 27


def neighbours(edges: Sequence[tuple[int, int]]) -> dict[int, set[int]]:
    adj: dict[int, set[int]] = defaultdict(set)
    for u, v in edges:
        adj[u].add(v)
        adj[v].add(u)
    return dict(adj)


def shortest_path(adj: dict[int, set[int]], src: int, dst: int) -> list[int]:
    """BFS shortest path [src, ..., dst] (inclusive). Raises if disconnected."""
    if src == dst:
        return [src]
    prev: dict[int, int] = {src: src}
    q = deque([src])
    while q:
        u = q.popleft()
        for w in adj.get(u, ()):
            if w not in prev:
                prev[w] = u
                if w == dst:
                    path = [dst]
                    while path[-1] != src:
                        path.append(prev[path[-1]])
                    return path[::-1]
                q.append(w)
    raise ValueError(f"no path from {src} to {dst} in coupling graph")


# ---------------------------------------------------------------------------
# Legality
# ---------------------------------------------------------------------------

def is_legal(ops: Sequence[Op], edges: Sequence[tuple[int, int]]) -> tuple[bool, str]:
    """Check every 2q gate acts on a physically adjacent pair.

    Returns (ok, message). On failure, message names the first offending gate.
    """
    adj = neighbours(edges)
    for i, op in enumerate(ops):
        if op.is_2q:
            a, b = op.qubits
            if b not in adj.get(a, set()):
                return False, f"gate #{i} {op.gate}{op.qubits} not on an edge"
    return True, "ok"


# ---------------------------------------------------------------------------
# Trusted numpy statevector oracle  (equivalence checking)
# ---------------------------------------------------------------------------

def _u3(theta: float, phi: float, lam: float) -> np.ndarray:
    c, s = math.cos(theta / 2), math.sin(theta / 2)
    return np.array([
        [c, -cmath.exp(1j * lam) * s],
        [cmath.exp(1j * phi) * s, cmath.exp(1j * (phi + lam)) * c],
    ], dtype=np.complex128)


_SQ = 1 / math.sqrt(2)
_GATES_1Q = {
    "H": np.array([[_SQ, _SQ], [_SQ, -_SQ]], dtype=np.complex128),
    "X": np.array([[0, 1], [1, 0]], dtype=np.complex128),
    "Y": np.array([[0, -1j], [1j, 0]], dtype=np.complex128),
    "Z": np.array([[1, 0], [0, -1]], dtype=np.complex128),
    "S": np.array([[1, 0], [0, 1j]], dtype=np.complex128),
    "T": np.array([[1, 0], [0, cmath.exp(1j * math.pi / 4)]], dtype=np.complex128),
}


def _apply_1q(state: np.ndarray, mat: np.ndarray, q: int, n: int) -> np.ndarray:
    # qubit 0 is the MOST significant index  (axis 0 in a (2,)*n reshape)
    st = state.reshape((2,) * n)
    st = np.tensordot(mat, st, axes=([1], [q]))
    st = np.moveaxis(st, 0, q)
    return st.reshape(-1)


def _apply_2q(state: np.ndarray, mat4: np.ndarray, a: int, b: int, n: int) -> np.ndarray:
    st = state.reshape((2,) * n)
    m = mat4.reshape(2, 2, 2, 2)                      # (a_out,b_out,a_in,b_in)
    st = np.tensordot(m, st, axes=([2, 3], [a, b]))   # new axes 0,1 = a_out,b_out
    st = np.moveaxis(st, [0, 1], [a, b])
    return st.reshape(-1)


def _2q_matrix(op: Op) -> np.ndarray:
    g = op.gate
    if g == "CNOT":
        return np.array([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]],
                        dtype=np.complex128)
    if g == "CZ":
        return np.diag([1, 1, 1, -1]).astype(np.complex128)
    if g == "SWAP":
        return np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]],
                        dtype=np.complex128)
    if g == "CU":
        u = _u3(op.params["theta"], op.params["phi"], op.params["lam"])
        m = np.eye(4, dtype=np.complex128)
        m[2:, 2:] = u                                 # control = first qubit
        return m
    raise ValueError(f"unknown 2q gate {g!r}")


def simulate(ops: Sequence[Op], n: int) -> np.ndarray:
    """Return the statevector produced by `ops` from |0...0>."""
    state = np.zeros(2 ** n, dtype=np.complex128)
    state[0] = 1.0
    for op in ops:
        if op.is_2q:
            state = _apply_2q(state, _2q_matrix(op), op.qubits[0], op.qubits[1], n)
        elif op.gate == "U":
            mat = _u3(op.params["theta"], op.params["phi"], op.params["lam"])
            state = _apply_1q(state, mat, op.qubits[0], n)
        else:
            state = _apply_1q(state, _GATES_1Q[op.gate], op.qubits[0], n)
    return state


def fidelity(ops_orig: Sequence[Op], ops_routed: Sequence[Op], n: int,
             final_layout: Sequence[int]) -> float:
    """|<orig | extract(routed)>|^2, undoing the output qubit placement.

    Both circuits start from |0...0>, so only the OUTPUT placement matters:
    logical i of the routed result sits on physical final_layout[i].

    Routed ops may reference arbitrary physical ids (e.g. on heavy-hex). We
    compact the physical qubits actually used to a dense range, simulate there,
    and read off the n logical outputs with every other (ancilla) qubit = |0>.
    """
    sv_orig = simulate(ops_orig, n)

    used = set()
    for op in ops_routed:
        used.update(op.qubits)
    used.update(final_layout)
    phys = sorted(used)
    cmap = {p: j for j, p in enumerate(phys)}     # physical -> compact index
    m = len(phys)

    ops_c = [Op(op.gate, tuple(cmap[q] for q in op.qubits), op.params)
             for op in ops_routed]
    sv_routed = simulate(ops_c, m)

    # read logical basis amplitudes: ancilla positions pinned to |0>
    sv_logical = np.zeros(2 ** n, dtype=np.complex128)
    out_pos = [cmap[final_layout[i]] for i in range(n)]   # compact pos of logical i
    for b in range(2 ** n):
        idx_m = 0
        for i in range(n):
            bit = (b >> (n - 1 - i)) & 1                   # logical i, qubit0 = MSB
            if bit:
                idx_m |= 1 << (m - 1 - out_pos[i])
        sv_logical[b] = sv_routed[idx_m]
    return float(abs(np.vdot(sv_orig, sv_logical)) ** 2)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def gate_counts(ops: Sequence[Op]) -> dict[str, int]:
    one = sum(1 for o in ops if not o.is_2q)
    two = sum(1 for o in ops if o.is_2q)
    swap = sum(1 for o in ops if o.gate == "SWAP")
    return {"1q": one, "2q": two, "swap": swap}


def circuit_depth(ops: Sequence[Op]) -> int:
    """ASAP depth: longest chain of gates sharing a qubit."""
    level: dict[int, int] = defaultdict(int)
    depth = 0
    for op in ops:
        d = 1 + max((level[q] for q in op.qubits), default=0)
        for q in op.qubits:
            level[q] = d
        depth = max(depth, d)
    return depth

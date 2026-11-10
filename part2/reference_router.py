# COL8422 Part 2 -- reference router (instructor baseline).
#
# This is the *Core-tier* behaviour: identity initial layout + shortest-path
# SWAP insertion.  It is deliberately simple -- it is correct but not clever.
# Your job in Part 2 is to replace this with a real SABRE implementation (and
# then an improvement).  Your `router.py` must expose the SAME `Router` contract:
#
#     class Router:
#         name: str
#         def __init__(self, edges: list[tuple[int, int]]): ...
#         def route(self, ops: list[Op], n: int) -> RoutingResult: ...
#
# where RoutingResult.ops is on physical qubits with every 2q gate on an edge,
# and RoutingResult.initial / .final give logical->physical layouts.

from __future__ import annotations

from routing_common import Op, RoutingResult, neighbours, shortest_path


class Router:
    name = "reference-shortestpath"

    def __init__(self, edges):
        self.edges = list(edges)
        self.adj = neighbours(self.edges)
        self.n_phys = 1 + max((max(u, v) for u, v in self.edges), default=0)

    def route(self, ops, n: int) -> RoutingResult:
        if n > self.n_phys:
            raise ValueError(f"{n} logical qubits > {self.n_phys} physical qubits")

        pos = list(range(n))            # pos[logical] = physical  (identity layout)
        occ = {p: p for p in range(n)}  # occ[physical] = logical  (None if free)
        for p in range(n, self.n_phys):
            occ[p] = None
        initial = list(pos)
        out: list[Op] = []

        def do_swap(pa: int, pb: int) -> None:
            out.append(Op("SWAP", (pa, pb)))
            la, lb = occ[pa], occ[pb]
            occ[pa], occ[pb] = lb, la
            if la is not None:
                pos[la] = pb
            if lb is not None:
                pos[lb] = pa

        for op in ops:
            if not op.is_2q:
                out.append(Op(op.gate, (pos[op.qubits[0]],), dict(op.params)))
                continue
            la, lb = op.qubits
            pa, pb = pos[la], pos[lb]
            if pb not in self.adj.get(pa, set()):
                path = shortest_path(self.adj, pa, pb)        # [pa, ..., pb]
                # walk logical `la` forward until adjacent to pb
                for k in range(len(path) - 2):
                    do_swap(path[k], path[k + 1])
                pa = pos[la]
            out.append(Op(op.gate, (pos[la], pos[lb]), dict(op.params)))

        return RoutingResult(ops=out, initial=initial, final=list(pos))

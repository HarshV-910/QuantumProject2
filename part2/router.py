from __future__ import annotations

from sabre_engine import run_sabre_pass


class Router:
    name = "sabre-core"

    def __init__(self, edges):
        self.edges = list(edges)
        self.n_phys = 1 + max((max(u, v) for u, v in self.edges), default=0)

    def route(self, ops, n):
        if n > self.n_phys:
            raise ValueError(f"{n} logical qubits > {self.n_phys} physical qubits")
        return run_sabre_pass(
            ops,
            n,
            self.edges,
            initial_layout=list(range(n)),
            config={"lookahead": 4, "front_weight": 1.0, "lookahead_weight": 0.5, "decay": 0.1},
        )


__all__ = ["Router", "run_sabre_pass"]

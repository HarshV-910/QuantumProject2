from __future__ import annotations

import importlib
import os
import random

from routing_common import RoutingResult
from layout_optimizer import optimize_initial_layout


class Router:
    name = "sabre-multistart"

    def __init__(self, edges):
        self.edges = list(edges)
        self.nodes = sorted({q for edge in self.edges for q in edge})
        self.adj = {q: set() for q in self.nodes}
        for a, b in self.edges:
            self.adj[a].add(b)
            self.adj[b].add(a)

        self.seed = int(os.environ.get("SABRE_IMPROVED_SEED", "17"))
        self.iterations = int(os.environ.get("SABRE_LAYOUT_ITERATIONS", "2"))
        self.candidate_count = int(os.environ.get("SABRE_LAYOUT_CANDIDATES", "8"))
        self.ablation = os.environ.get("SABRE_IMPROVED_ABLATION", "0") == "1"

        if self.iterations < 0:
            raise ValueError("SABRE_LAYOUT_ITERATIONS must be non-negative")
        if self.candidate_count < 1:
            raise ValueError("SABRE_LAYOUT_CANDIDATES must be positive")

        try:
            engine = importlib.import_module("sabre_engine")
            self.run_one_pass = getattr(engine, "run_sabre_pass")
        except (ImportError, AttributeError) as exc:
            raise ImportError(
                "router_improved requires part2/sabre_engine.py exporting "
                "run_sabre_pass(ops, n, edges, initial_layout=None, config=None). "
                "This is the shared Group 1 interface described in grp2.md."
            ) from exc

    def _initial_layouts(self, n):
        if n > len(self.nodes):
            raise ValueError(f"{n} logical qubits cannot fit on {len(self.nodes)} physical qubits")

        identity = self.nodes[:n]
        if self.ablation:
            return [identity]

        degree_order = sorted(
            self.nodes,
            key=lambda q: (-len(self.adj[q]), q),
        )
        layouts = [identity, degree_order[:n]]

        rng = random.Random(self.seed)
        for _ in range(self.candidate_count):
            candidate = self.nodes[:]
            rng.shuffle(candidate)
            layouts.append(candidate[:n])

        unique = []
        seen = set()
        for layout in layouts:
            key = tuple(layout)
            if key not in seen:
                seen.add(key)
                unique.append(layout)
        return unique

    @staticmethod
    def _key(result):
        swaps = sum(op.gate == "SWAP" for op in result.ops)
        used = set()
        for op in result.ops:
            used.update(op.qubits)
        depth = 0
        last = {}
        for op in result.ops:
            level = 1 + max((last.get(q, 0) for q in op.qubits), default=0)
            for q in op.qubits:
                last[q] = level
            depth = max(depth, level)
        return swaps, depth

    def route(self, ops, n):
        layouts = self._initial_layouts(n)
        best = None
        best_key = None

        for layout in layouts:
            result = optimize_initial_layout(
                ops=ops,
                n=n,
                edges=self.edges,
                run_one_pass=self.run_one_pass,
                initial_layout=layout,
                iterations=self.iterations,
                config=None,
            )
            key = self._key(result)
            if best is None or key < best_key:
                best = result
                best_key = key

        if best is None:
            raise RuntimeError("no initial layout candidate was evaluated")
        return best

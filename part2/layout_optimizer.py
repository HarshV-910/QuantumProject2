from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from routing_common import Op, RoutingResult, circuit_depth


@dataclass(frozen=True)
class LayoutSearchStats:
    passes: int
    candidates: int
    swaps: int
    depth: int


def reverse_ops(ops: Sequence[Op]) -> list[Op]:
    return [
        Op(op.gate, tuple(op.qubits), dict(op.params))
        for op in reversed(ops)
    ]


def _layout_key(result: RoutingResult) -> tuple[int, int]:
    swaps = sum(op.gate == "SWAP" for op in result.ops)
    return swaps, circuit_depth(result.ops)


def _validate_layout(layout: Sequence[int], n: int, physical_nodes: Sequence[int]) -> list[int]:
    values = list(layout)
    if len(values) != n:
        raise ValueError(f"layout must contain {n} physical-qubit indices")
    if len(set(values)) != n:
        raise ValueError("layout must map logical qubits to distinct physical qubits")
    allowed = set(physical_nodes)
    if any(p not in allowed for p in values):
        raise ValueError("layout contains a physical qubit not present in the coupling graph")
    return values


def optimize_initial_layout(
    ops: Sequence[Op],
    n: int,
    edges: Sequence[tuple[int, int]],
    run_one_pass: Callable,
    initial_layout: Sequence[int] | None = None,
    iterations: int = 2,
    config=None,
) -> RoutingResult:
    if iterations < 0:
        raise ValueError("iterations must be non-negative")

    nodes = sorted({q for edge in edges for q in edge})
    if not nodes and n:
        raise ValueError("coupling graph has no physical qubits")
    if n > len(nodes):
        raise ValueError(f"{n} logical qubits cannot fit on {len(nodes)} physical qubits")

    current = _validate_layout(
        initial_layout if initial_layout is not None else nodes[:n],
        n,
        nodes,
    )

    forward = run_one_pass(
        ops, n, edges, initial_layout=list(current), config=config
    )
    best = forward
    best_key = _layout_key(best)

    reversed_circuit = reverse_ops(ops)

    for _ in range(iterations):
        backward = run_one_pass(
            reversed_circuit,
            n,
            edges,
            initial_layout=list(forward.final),
            config=config,
        )

        candidate_layout = _validate_layout(backward.final, n, nodes)
        forward = run_one_pass(
            ops,
            n,
            edges,
            initial_layout=candidate_layout,
            config=config,
        )

        candidate_key = _layout_key(forward)
        if candidate_key < best_key:
            best = forward
            best_key = candidate_key

    return best


def summarize_result(result: RoutingResult, passes: int, candidates: int) -> LayoutSearchStats:
    swaps = sum(op.gate == "SWAP" for op in result.ops)
    return LayoutSearchStats(
        passes=passes,
        candidates=candidates,
        swaps=swaps,
        depth=circuit_depth(result.ops),
    )

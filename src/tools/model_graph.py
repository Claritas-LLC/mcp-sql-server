from __future__ import annotations

from typing import Any


def build_fk_graph(rows: list[dict[str, Any]]) -> dict[str, Any]:
    edges: list[dict[str, str]] = []
    nodes: set[str] = set()
    for row in rows:
        parent = f"{row.get('parent_schema')}.{row.get('parent_table')}"
        referenced = f"{row.get('referenced_schema')}.{row.get('referenced_table')}"
        nodes.add(parent)
        nodes.add(referenced)
        edges.append({"from": parent, "to": referenced, "fk_name": str(row.get("fk_name", ""))})

    adjacency: dict[str, set[str]] = {}
    for edge in edges:
        adjacency.setdefault(edge["from"], set()).add(edge["to"])

    cycle_hits: set[str] = set()

    def _dfs(start: str, current: str, seen: set[str]) -> None:
        for nxt in adjacency.get(current, set()):
            if nxt == start:
                cycle_hits.add(start)
            if nxt in seen:
                continue
            _dfs(start, nxt, seen | {nxt})

    for node in nodes:
        _dfs(node, node, {node})

    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "circular_dependency_tables": sorted(cycle_hits),
        "edges": edges,
    }

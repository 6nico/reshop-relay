"""Store layout: walkable graph, shortest paths, and stop ordering.

Distances are in meters. Travel always follows valid connections; blocked
connections are removed before any route is computed.
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field


class UnreachableError(ValueError):
    """Raised when a destination cannot be reached on the walkable graph."""


@dataclass
class Store:
    nodes: dict            # node id -> {"x": float, "y": float, "label": str}
    edges: list            # [a, b, meters]
    departments: dict      # department -> node id where its reshop is placed
    guest_services: str = "GS"
    blocked: list = field(default_factory=list)  # [[a, b], ...]

    def __post_init__(self):
        blocked = {frozenset(b) for b in self.blocked}
        self.adj = {n: [] for n in self.nodes}
        for a, b, d in self.edges:
            if a not in self.nodes or b not in self.nodes:
                raise ValueError(f"Edge {a}-{b} uses an unknown node")
            if frozenset((a, b)) in blocked:
                continue
            self.adj[a].append((b, float(d)))
            self.adj[b].append((a, float(d)))
        for dept, node in self.departments.items():
            if node not in self.nodes:
                raise ValueError(f"Department {dept} points to unknown node {node}")
        self._cache = {}

    # ---- shortest paths -------------------------------------------------
    def _dijkstra(self, src):
        if src in self._cache:
            return self._cache[src]
        dist = {src: 0.0}
        prev = {}
        pq = [(0.0, src)]
        while pq:
            d, u = heapq.heappop(pq)
            if d > dist.get(u, float("inf")):
                continue
            for v, w in self.adj[u]:
                nd = d + w
                if nd < dist.get(v, float("inf")) - 1e-9:
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(pq, (nd, v))
        self._cache[src] = (dist, prev)
        return dist, prev

    def dist(self, a, b):
        if a == b:
            return 0.0
        d, _ = self._dijkstra(a)
        if b not in d:
            raise UnreachableError(f"{self.nodes[b]['label']} ({b}) cannot be reached from {self.nodes[a]['label']} ({a})")
        return d[b]

    def path(self, a, b):
        """Node-by-node walking path from a to b."""
        if a == b:
            return [a]
        self.dist(a, b)  # raises if unreachable
        _, prev = self._dijkstra(a)
        out = [b]
        while out[-1] != a:
            out.append(prev[out[-1]])
        return out[::-1]

    def route_length(self, stops):
        return sum(self.dist(stops[i], stops[i + 1]) for i in range(len(stops) - 1))

    def full_path(self, stops):
        out = [stops[0]]
        for i in range(len(stops) - 1):
            out += self.path(stops[i], stops[i + 1])[1:]
        return out

    def check_reachable(self):
        """Return a list of departments that cannot be reached from Guest Services."""
        bad = []
        for dept, node in self.departments.items():
            try:
                self.dist(self.guest_services, node)
            except UnreachableError:
                bad.append(dept)
        return bad

    # ---- stop ordering: nearest neighbor, then 2-opt -------------------
    def order_stops(self, start, stops, end=None):
        """Order drop-off stops to keep walking short.

        Builds a route with nearest-neighbor, then improves it with 2-opt.
        `start` (and `end`, if given) stay fixed.
        """
        stops = list(dict.fromkeys(s for s in stops if s != start))
        if end is not None:
            stops = [s for s in stops if s != end]
        if len(stops) <= 1:
            return stops
        order, cur, left = [], start, set(stops)
        while left:
            nxt = min(left, key=lambda s: (self.dist(cur, s), s))
            order.append(nxt)
            left.remove(nxt)
            cur = nxt

        def length(o):
            seq = [start] + o + ([end] if end is not None else [])
            return self.route_length(seq)

        best, improved = length(order), True
        while improved:
            improved = False
            for i in range(len(order) - 1):
                for j in range(i + 1, len(order)):
                    cand = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                    L = length(cand)
                    if L < best - 1e-9:
                        order, best, improved = cand, L, True
        return order

    @classmethod
    def from_dict(cls, d):
        return cls(nodes=d["nodes"], edges=d["edges"], departments=d["departments"],
                   guest_services=d.get("guest_services", "GS"), blocked=d.get("blocked", []))

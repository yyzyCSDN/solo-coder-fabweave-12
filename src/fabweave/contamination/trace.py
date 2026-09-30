from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Mapping, Sequence


WIP = "wip"
SHIPPED = "shipped"
DISPOSED = "disposed"
_STATES = frozenset((WIP, SHIPPED, DISPOSED))

FLOW = "flow"
SPLIT = "split"
MERGE = "merge"
CARRIER = "carrier"

MATERIAL = "material"


@dataclass(frozen=True, slots=True)
class FlowEdge:
    """A directed material relationship: ``source`` is an input, ``target`` an output."""

    source: str
    target: str
    relation: str = FLOW

    def __post_init__(self) -> None:
        if not self.source or not self.target or not self.relation:
            raise ValueError("flow edge endpoints and relation are required")


@dataclass(frozen=True, slots=True)
class CarrierContact:
    """A material contacting a carrier during the relevant contamination window."""

    carrier_id: str
    material_id: str

    def __post_init__(self) -> None:
        if not self.carrier_id or not self.material_id:
            raise ValueError("carrier contact endpoints are required")


@dataclass(frozen=True, slots=True)
class TraceHop:
    node_id: str
    kind: str
    relation: str
    direction: str


@dataclass(frozen=True, slots=True)
class TracedObject:
    object_id: str
    state: str
    depth: int
    path: tuple[TraceHop, ...]


@dataclass(frozen=True, slots=True)
class TracedCarrier:
    carrier_id: str
    depth: int
    path: tuple[TraceHop, ...]


@dataclass(frozen=True, slots=True)
class TraceResult:
    seeds: tuple[str, ...]
    wip: tuple[TracedObject, ...]
    shipped: tuple[TracedObject, ...]
    disposed: tuple[TracedObject, ...]
    carriers: tuple[TracedCarrier, ...]

    @property
    def objects(self) -> tuple[TracedObject, ...]:
        return tuple(sorted((*self.wip, *self.shipped, *self.disposed), key=lambda item: item.object_id))

    def as_event_data(self, max_depth: int, hold_ids: Sequence[str] = ()) -> dict[str, object]:
        return {
            "seeds": list(self.seeds),
            "max_depth": max_depth,
            "wip": [item.object_id for item in self.wip],
            "shipped": [item.object_id for item in self.shipped],
            "disposed": [item.object_id for item in self.disposed],
            "carriers": [item.carrier_id for item in self.carriers],
            "hold_ids": list(hold_ids),
        }


class ContaminationGraph:
    """
    Directed split/merge/process edges plus undirected carrier contacts.

    Flow edges point from input material to output material.  Their relation is
    retained as evidence, but every flow edge can be traversed in both
    directions.  Carrier contacts are expanded material -> carrier -> material.
    """

    def __init__(
        self,
        material_states: Mapping[str, str],
        flow_edges: Sequence[FlowEdge] = (),
        carrier_contacts: Sequence[CarrierContact] = (),
        carrier_ids: Sequence[str] = (),
    ) -> None:
        invalid = sorted(set(material_states.values()) - _STATES)
        if invalid:
            raise ValueError(f"invalid material state: {', '.join(invalid)}")

        self._states = dict(material_states)
        self._successors: dict[str, set[str]] = {node: set() for node in self._states}
        self._predecessors: dict[str, set[str]] = {node: set() for node in self._states}
        self._relations: dict[tuple[str, str], str] = {}

        for edge in flow_edges:
            if edge.source not in self._states or edge.target not in self._states:
                raise ValueError("flow edge references unknown material")
            relation_key = (edge.source, edge.target)
            previous = self._relations.get(relation_key)
            if previous is not None and previous != edge.relation:
                raise ValueError("the same flow edge has conflicting relations")
            self._relations[relation_key] = edge.relation
            self._successors[edge.source].add(edge.target)
            self._predecessors[edge.target].add(edge.source)

        self._carriers = set(carrier_ids)
        overlapping = sorted(self._carriers & set(self._states))
        if overlapping:
            raise ValueError(f"carrier id cannot also identify a material: {', '.join(overlapping)}")
        self._carrier_materials: dict[str, set[str]] = {carrier: set() for carrier in self._carriers}
        self._material_carriers: dict[str, set[str]] = {node: set() for node in self._states}
        for contact in carrier_contacts:
            if contact.material_id not in self._states:
                raise ValueError("carrier contact references unknown material")
            if contact.carrier_id in self._states:
                raise ValueError("carrier id cannot also identify a material")
            self._carriers.add(contact.carrier_id)
            self._carrier_materials.setdefault(contact.carrier_id, set()).add(contact.material_id)
            self._material_carriers[contact.material_id].add(contact.carrier_id)

    def trace(self, seeds: Sequence[str], max_depth: int) -> TraceResult:
        if max_depth < 0:
            raise ValueError("max depth cannot be negative")
        if not seeds:
            raise ValueError("at least one trace seed is required")

        starts: set[tuple[str, str]] = set()
        for seed in seeds:
            if seed in self._states:
                starts.add((MATERIAL, seed))
            elif seed in self._carriers:
                starts.add((CARRIER, seed))
            else:
                raise ValueError(f"unknown trace seed: {seed}")

        visited: dict[tuple[str, str], tuple[int, tuple[TraceHop, ...]]] = {}
        queue: deque[tuple[tuple[str, str], int, tuple[TraceHop, ...]]] = deque()
        for node in sorted(starts):
            visited[node] = (0, ())
            queue.append((node, 0, ()))

        while queue:
            (kind, node_id), depth, path = queue.popleft()
            if depth == max_depth:
                continue

            neighbors: list[tuple[tuple[str, str], TraceHop]] = []
            if kind == MATERIAL:
                for predecessor in self._predecessors.get(node_id, set()):
                    relation = self._relations[(predecessor, node_id)]
                    neighbors.append(
                        (
                            (MATERIAL, predecessor),
                            TraceHop(predecessor, MATERIAL, relation, "upstream"),
                        )
                    )
                for successor in self._successors.get(node_id, set()):
                    relation = self._relations[(node_id, successor)]
                    neighbors.append(
                        (
                            (MATERIAL, successor),
                            TraceHop(successor, MATERIAL, relation, "downstream"),
                        )
                    )
                for carrier_id in self._material_carriers.get(node_id, set()):
                    neighbors.append(
                        (
                            (CARRIER, carrier_id),
                            TraceHop(carrier_id, CARRIER, CARRIER, CARRIER),
                        )
                    )
            else:
                for material_id in self._carrier_materials.get(node_id, set()):
                    neighbors.append(
                        (
                            (MATERIAL, material_id),
                            TraceHop(material_id, MATERIAL, CARRIER, CARRIER),
                        )
                    )

            for next_node, hop in sorted(neighbors, key=lambda item: item[0]):
                if next_node in visited:
                    continue
                next_path = path + (hop,)
                visited[next_node] = (depth + 1, next_path)
                queue.append((next_node, depth + 1, next_path))

        wip: list[TracedObject] = []
        shipped: list[TracedObject] = []
        disposed: list[TracedObject] = []
        for (kind, node_id), (depth, path) in visited.items():
            if kind != MATERIAL:
                continue
            item = TracedObject(node_id, self._states[node_id], depth, path)
            if item.state == WIP:
                wip.append(item)
            elif item.state == SHIPPED:
                shipped.append(item)
            else:
                disposed.append(item)

        carriers = [
            TracedCarrier(node_id, depth, path)
            for (kind, node_id), (depth, path) in visited.items()
            if kind == CARRIER
        ]
        return TraceResult(
            seeds=tuple(sorted({node_id for _, node_id in starts})),
            wip=tuple(sorted(wip, key=lambda item: item.object_id)),
            shipped=tuple(sorted(shipped, key=lambda item: item.object_id)),
            disposed=tuple(sorted(disposed, key=lambda item: item.object_id)),
            carriers=tuple(sorted(carriers, key=lambda item: item.carrier_id)),
        )

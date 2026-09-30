from __future__ import annotations

from dataclasses import dataclass

from fabweave.contamination.trace import ContaminationGraph, TraceResult
from fabweave.core.events import EventLog
from fabweave.holds.ledger import ContaminationHold, HoldLedger


@dataclass(frozen=True, slots=True)
class RecallRecord:
    trace: TraceResult
    event_sequence: int
    holds: tuple[ContaminationHold, ...]


def trace_contamination(graph: ContaminationGraph, seeds: list[str], max_depth: int) -> TraceResult:
    return graph.trace(seeds, max_depth)


def recall_contamination(
    log: EventLog,
    hold_ledger: HoldLedger,
    recall_id: str,
    graph: ContaminationGraph,
    seeds: list[str],
    max_depth: int,
    at: int,
) -> RecallRecord:
    """
    Record one bounded contamination recall and place idempotent WIP holds.

    Shipped and disposed objects remain in the trace and event payload.  They
    are deliberately never passed to the hold ledger because physical custody
    is no longer available.
    """
    trace = trace_contamination(graph, seeds, max_depth)
    holds = tuple(hold_ledger.place_hold(recall_id, item.object_id) for item in trace.wip)
    event = log.append(
        f"contamination:{recall_id}",
        0,
        recall_id,
        at,
        "contamination_recall",
        trace.as_event_data(max_depth, [hold.hold_id for hold in holds]),
    )
    return RecallRecord(trace, event.sequence, holds)

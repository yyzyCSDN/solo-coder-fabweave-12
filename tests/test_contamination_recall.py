from __future__ import annotations

from fabweave.contamination.recall import recall_contamination
from fabweave.contamination.trace import CARRIER, MERGE, SPLIT, CarrierContact, ContaminationGraph, FlowEdge
from fabweave.core.events import EventLog
from fabweave.holds.ledger import HoldLedger


def _recall_graph() -> ContaminationGraph:
    return ContaminationGraph(
        material_states={
            "SOURCE": "wip",
            "CHILD-A": "wip",
            "CHILD-B": "wip",
            "MERGED": "wip",
            "SHIPPED": "shipped",
            "SCRAPPED": "disposed",
            "CONTACT": "wip",
        },
        flow_edges=(
            FlowEdge("SOURCE", "CHILD-A", SPLIT),
            FlowEdge("SOURCE", "CHILD-B", SPLIT),
            FlowEdge("CHILD-A", "MERGED", MERGE),
            FlowEdge("CHILD-B", "MERGED", MERGE),
            FlowEdge("MERGED", "SHIPPED", "flow"),
            FlowEdge("MERGED", "SCRAPPED", "flow"),
        ),
        carrier_contacts=(CarrierContact("CART-1", "SOURCE"), CarrierContact("CART-1", "CONTACT")),
        carrier_ids=("CART-2",),
    )


def test_trace_follows_split_merge_and_carrier_edges_with_depth_bound():
    graph = _recall_graph()
    trace = graph.trace(["SOURCE"], 1)

    assert [item.object_id for item in trace.wip] == ["CHILD-A", "CHILD-B", "SOURCE"]
    assert trace.shipped == ()
    assert trace.disposed == ()
    assert tuple(item.carrier_id for item in trace.carriers) == ("CART-1",)

    carrier_scope = graph.trace(["SOURCE"], 2)
    assert [item.object_id for item in carrier_scope.wip] == ["CHILD-A", "CHILD-B", "CONTACT", "MERGED", "SOURCE"]

    full_trace = graph.trace(["SOURCE"], 4)
    assert [item.object_id for item in full_trace.wip] == ["CHILD-A", "CHILD-B", "CONTACT", "MERGED", "SOURCE"]
    assert [item.object_id for item in full_trace.shipped] == ["SHIPPED"]
    assert [item.object_id for item in full_trace.disposed] == ["SCRAPPED"]
    assert {item.object_id: item.depth for item in full_trace.objects}["SHIPPED"] == 3


def test_carrier_seed_traverses_contact_and_result_keeps_path_evidence():
    trace = _recall_graph().trace(["CART-1"], 1)

    assert [item.object_id for item in trace.wip] == ["CONTACT", "SOURCE"]
    contact = next(item for item in trace.wip if item.object_id == "CONTACT")
    assert contact.path[0].relation == CARRIER


def test_graph_cycles_are_deduped_and_do_not_loop():
    graph = ContaminationGraph(
        material_states={"A": "wip", "B": "wip", "C": "wip"},
        flow_edges=(
            FlowEdge("A", "B", SPLIT),
            FlowEdge("B", "C", "flow"),
            FlowEdge("C", "A", "flow"),
        ),
    )

    trace = graph.trace(["A"], 10)
    assert [item.object_id for item in trace.wip] == ["A", "B", "C"]
    assert len({item.object_id for item in trace.wip}) == 3


def test_recall_is_idempotent_and_keeps_non_holdable_objects_in_scope():
    graph = _recall_graph()
    log = EventLog()
    ledger = HoldLedger()

    first = recall_contamination(log, ledger, "RECALL-1", graph, ["SOURCE"], 4, 10)
    replay = recall_contamination(log, ledger, "RECALL-1", graph, ["SOURCE"], 4, 10)

    assert replay == first
    assert replay.event_sequence == 1
    assert [item.object_id for item in replay.trace.shipped] == ["SHIPPED"]
    assert [item.object_id for item in replay.trace.disposed] == ["SCRAPPED"]
    assert tuple(item.object_id for item in replay.holds) == ("CHILD-A", "CHILD-B", "CONTACT", "MERGED", "SOURCE")
    assert len(ledger.holds_for("RECALL-1")) == 5
    assert len(ledger.active_hold_ids("SOURCE")) == 1
    assert log.read("contamination:RECALL-1")[0].data["shipped"] == ["SHIPPED"]

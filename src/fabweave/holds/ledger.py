from __future__ import annotations

from dataclasses import dataclass

from fabweave.contamination.trace import WIP
from fabweave.core.ids import deterministic_id


@dataclass(frozen=True, slots=True)
class ContaminationHold:
    hold_id: str
    recall_id: str
    object_id: str
    state: str = WIP


class HoldLedger:
    """Recall-scoped hold ledger.  Replaying a recall never adds another hold."""

    def __init__(self) -> None:
        self._holds: dict[tuple[str, str], ContaminationHold] = {}
        self._active_by_object: dict[str, set[str]] = {}

    def place_hold(self, recall_id: str, object_id: str) -> ContaminationHold:
        key = (recall_id, object_id)
        existing = self._holds.get(key)
        if existing is not None:
            return existing
        hold_id = deterministic_id("HOLD", recall_id, object_id)
        hold = ContaminationHold(hold_id, recall_id, object_id)
        self._holds[key] = hold
        self._active_by_object.setdefault(object_id, set()).add(hold_id)
        return hold

    def holds_for(self, recall_id: str) -> tuple[ContaminationHold, ...]:
        return tuple(hold for (current_recall, _), hold in sorted(self._holds.items()) if current_recall == recall_id)

    def active_hold_ids(self, object_id: str) -> tuple[str, ...]:
        return tuple(sorted(self._active_by_object.get(object_id, set())))

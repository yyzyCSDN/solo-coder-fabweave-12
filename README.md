# FabWeave Operations Lab

FabWeave is a dependency-light Python reference project for semiconductor-fab
operations.  Its production modules model queue-time protection, dispatch,
reticle reservations, recipe qualification, SPC, metrology sampling,
maintenance, chamber matching, holds, genealogy, chemical aging, cleanroom
excursions, demand control, rework, lot merging, equipment dedication,
contamination, source-contamination recall, takt, route yield and shipment commitments.

The cross-domain workflow layer composes these services for material
readiness, dispatch-after-hold, qualified reservations and assignments,
metrology/SPC gates, containment, powered scheduling, rework release,
merge-to-commit and performance reporting.  It preserves domain rejection
reasons instead of replacing them with a generic success or failure.

Shared infrastructure supplies half-open time intervals, versioned policy
history, immutable decisions, quantity conservation and an append-only event
log with optimistic concurrency.  Domain services use these primitives to keep
event-time, idempotency and fail-closed behavior consistent.

Source-contamination recall traverses directed split/merge relationships and
undirected carrier contacts in both directions within a bounded depth.  A
single node set makes shared ancestry and loops idempotent; WIP objects receive
recall-scoped holds, while shipped and disposed objects remain in separate
recall result buckets even though they cannot be physically held.

Run the tests with `python -m pytest -q`.

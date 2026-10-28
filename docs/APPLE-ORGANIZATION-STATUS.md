# Apple organization status

Apple bookshelf organization is **not complete or accepted**. The existing
Apple shelf supports bounded browsing and restoration; the accepted native
organization evidence in `validation/reader-organization-native.json` covers
read-only APIs and expressly does not accept a UI.

The opt-in `--organization` Apple product build stages the existing desktop
metadata owner, including its durable pending-intent mechanism. The separate
`Apple organization foundation` Actions workflow builds it for macOS and the
iOS simulator and runs the existing metadata recovery checks on macOS. This is
an integration foundation, not an Apple host feature or a platform acceptance
test. It does not alter the existing shelf checks, limits, or schema.

The Apple host still needs a native adapter and UI for shelves, child shelves,
categories and series, including group and membership creation, editing,
removal, explicit restoration and ordering. The adapter must manage the native
owner on its creating thread, retain the exact staged intent and observed heads
through interruption, surface conflicts and committed-but-pending cleanup, and
verify original bytes before bootstrapping legacy book history. A serial
DispatchQueue alone does not ensure a fixed native thread across tasks.

Acceptance remains blocked until the actual host and UI are implemented and
tested on macOS, iPhone and iPad in Actions. The tests must include process
termination and recovery, stale and concurrent changes, retained original
identity, and the existing bounded shelf and restoration contracts. A
successful foundation run alone cannot establish these outcomes.

# Apple organization status

Apple bookshelf organization is **not complete or accepted**. The existing
Apple shelf supports bounded browsing and restoration; the accepted native
organization evidence in `validation/reader-organization-native.json` covers
read-only APIs and expressly does not accept a UI.

The Apple host now stages the existing desktop metadata owner, including its
durable pending-intent mechanism, and exposes group and membership controls.
The separate `Apple organization foundation` Actions workflow builds the owner
for macOS and the iOS simulator and runs existing recovery checks on macOS.
The new `Apple native organization` workflow exercises native UI and process
restart on three destinations. Neither workflow alone grants complete product
acceptance. Existing shelf checks, limits, and schema remain unchanged.

The adapter opens and closes each native owner in a single queue work item,
retains the prepared snapshot across review and commit, exposes pending retry
and safe abandonment, and requires public SDK original verification before
bootstrapping legacy book history. A serial DispatchQueue alone does not ensure
a fixed native thread across tasks; native handles do not cross work items.

Acceptance remains open until the actual host and UI pass on macOS, iPhone and
iPad in Actions, together with the existing bounded shelf and restoration
contracts. The initial UI suite covers process termination and visible recovery;
it does not independently prove stale-write refusal or compare retained intent
IDs and heads. Physical-device acceptance is also outside that suite.

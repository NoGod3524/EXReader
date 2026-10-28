# Apple native history: combined candidate evidence

[Actions 40588875213/1](https://github.com/NoGod3524/EXReader/actions/runs/40588875213)
passed at source `c45ac1a7508842f071e3d892635fdd9af444ae90`.
The actual macOS host and iPhone and iPad simulator hosts each ran
`testNativeHistoryAfterFoundAndLargeRotationExit()`: search selects an
independently authored unique result, then native history navigates back and
forward and checks the displayed destination. This is a real UI test; the iOS
case also exercises rotation and closes the host.

The same run built the installed SDK and modules, ran retained base, reading,
navigation, search and theme suites, and authenticated the original ZIPs.
The fixed-catalog audit rereads the named passing wave3 case from each original
platform ZIP, checking platform, source, run, attempt, size and SHA-256.
The accepted result covers the tested macOS host and iOS simulators; physical
devices, signing and six-platform final delivery have separate requirements.

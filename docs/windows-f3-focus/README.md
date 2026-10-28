# Windows F3 focus/theme correction

## Base selection before host changes

Audited source `1adeabf2a672ddc0c200631e29897cfe76106afd` and precise failed source
`e330a415b733db18dea5aa6010d13cf3063587fd` diverge at
`f34a4f27161061d08ecc40f5cebfb6f5018aa77f`.
The audited source predates the accepted TXT forward-scan/font lifecycle changes
present in the failed current Windows composition. Select **e330a415** as the
minimal compatible base, preserving all its host and frozen SDK source.

Original failure: run 40638398225 attempt 1; original artifact 12795210910.
Authenticated diagnostic: run 40640905795 attempt 1, job 122658557186,
artifact 12795776314. Actual client 797x541; layout [214,4,368,533]; white page
corner, 692 ink samples and minimum RGB sum 0 passed. Only surround (210,1)
was black. Original failed evidence remains intact.

The first independent branch run changes no product source. It measures the
same original sample and real HWND focus/UI-cue changes; it does not edit the
old F3 judge, sample coordinates, checks or thresholds. Hypothesis: unconditional
DrawFocusRect ignores the Windows UI cue state; actual contrast is required
before selecting a host correction. This is not yet acceptance.
# GTK accessibility driver crash diagnostic

The common-source candidate `c45ac1a7508842f071e3d892635fdd9af444ae90`
failed [run 40588875254, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40588875254)
in the current accessibility driver. Its Python process exited with a
segmentation fault after the collections-dialog phase. No result.json was
produced for that driver. The separate account status job passed. Preserve
this failure and the outcome of the still-running retained job.

Diagnostic source `ac1041be1159886e9176f33be6b1798e4bc0e2b4` added phase-start
logging and Python faulthandler, and did not change the product source or the
accessibility assertions. [Run 40590921718, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40590921718)
completed the focused GTK job successfully: 13 phases and 32/32 checks. The
failure did not recur, so no crash stack or root cause was obtained. This
diagnostic branch intentionally skipped retained-account, historical regression
and combined authentication jobs because those had already started in the
original run. Its success is scoped to the focused job on its own source; it
does not replace the failed original combined run.

# D26 GTK independent diagnostic result

[Actions 40587741187, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40587741187)
completed all four jobs successfully on source
`00e370a28ed4b25718154ff68d914cbecb51fdb8`: the current GTK host, retained
account check, historical audit/native regression, and strict evidence job.

The current artifact is `12771144476`, 322613508 bytes, SHA-256
`9bfbcd1815823dd376f02b07d1eeeae708d146dba413a5d65fe48b49cc726318`.
The strict identity artifact is `12775535180`, 4400 bytes, SHA-256
`4bc4859bd7ad79f349bb4397ff41856fa762622f242790b71d6796d431bf2625`.
Both expire 2027-01-25T21:33:12Z.

This result belongs to the stated independent source. The later common-source
run [40588875254](https://github.com/NoGod3524/EXReader/actions/runs/40588875254)
recorded a Python driver segmentation fault after the collections-dialog phase;
its failure is retained. An additional focused diagnosis passed on its own
source without reproducing the crash; it did not establish the root cause.


The GTK host and retained/current D26 test paths are byte-identical between
`00e370a28ed4b25718154ff68d914cbecb51fdb8` and
`c45ac1a7508842f071e3d892635fdd9af444ae90`. The latter does change
`src/formats.c` and `include/exr/formats.h` for the TXT anchor candidate, and
also changes Windows-only host files. This narrows the source comparison but
does not establish the cause of the Python driver crash or chooser failure.

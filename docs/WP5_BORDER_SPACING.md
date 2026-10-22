# WP5 CSS border spacing

`border-spacing` accepts one or two nonnegative CSS lengths through the existing
CSS length parser. One value applies to both physical axes. Two values specify
horizontal then vertical spacing. Percentages, `auto`, negative values and extra
tokens leave the previous valid declaration in effect. The CSS initial value is
zero; the property inherits computed lengths and supports `inherit`, `initial`
and `unset`. Relative lengths resolve against the declaring element's font size.

The separate table model reserves spacing at both outside edges and between
tracks. Column allocation subtracts `(column_count + 1) * inline_spacing` before
fitting columns; a spanning cell includes the gaps between the tracks it spans.
Row positions include the following gap, while cell boxes exclude that final
gap. Table padding and borders remain outside the spacing. Collapsed tables
retain the computed property but use zero spacing. Physical axes swap in the
existing vertical-writing conversion.

The table cursor stores the two used spacings alongside its column and row
geometry. Cursor cloning preserves those scalars and the existing geometry
arrays. The normal copy, independent-border paint, repeated header and tall-row
fragment paths use the same cell extents.

`native-table-spacing` constructs documents through the public API and checks
single/two values, zero, invalid declaration fallback, collapse, inheritance,
CSS-wide keywords, relative units, rowspan/colspan, both vertical directions,
repeated header gaps, tall rows, page rendering, hit tests and seeded random
checkpoint restoration. Existing tests stay registered without changed
tolerances. `.github/workflows/wp5-border-spacing.yml` builds on Ubuntu 22.04 and
Windows and runs the full native CTest suite. Cloud execution results are pending.

No local build, test, fixture generation or benchmark was run for this package.

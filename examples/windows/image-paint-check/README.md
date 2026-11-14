# L02 image slice

Build and run without opening a window:

```powershell
cmake -S examples/windows/image-paint-check -B build/l02-check -G Ninja -DEXR_SDK=<installed-sdk>
cmake --build build/l02-check
$env:PATH = "<installed-sdk>/bin;" + $env:PATH
build/l02-check/check_image_paint.exe
# Or run the registered acceptance test:
ctest --test-dir build/l02-check -V --output-on-failure
```

Include `shell_docedit_image_paint.inc` after `shell_d2d.h` and `exr/edit.h`.
For each `EXR_EDIT_IMAGE` block, call `de_image_measure` with the content inset,
document-space row y, available width, and current DPI. Advance the following
row by `view.height` plus the existing block gap. This reads the public
`block->image` payload and EMU dimensions; no additional engine API is needed.

After painting text and before painting the toolbar, call `de_image_paint` for
each image. Pass the current scroll, toolbar bottom, and selected block index.
Initialize selection to `SIZE_MAX`. On each body click assign the return value
of `de_image_hit` to selection, and only fall through to text hit testing when
it returns `SIZE_MAX`. Invalidate after selection changes. Image hits must not
start a text-selection drag. Suppress the text caret while an image is selected.

Release all views with `de_image_release` before rebuilding layout or closing
the editor. Rebuild after model changes, resize, or DPI changes. Reset selection
on model changes so an old index cannot select a different block after deletion.
Decoded pixels are owned; model payload pointers are never cached.

The existing layout/input includes are outside L02's exclusive file scope.
This slice exposes the integration functions above; it does not modify those
includes. The console check runs the real insert, decode, D2D paint, and hit
functions against a memory DC, including selection and deselection.
It also checks aspect ratio, centering, DPI, scroll coordinates, viewport
edges, toolbar clipping, transparent pixels, and invalid hit-test inputs.

# Engine font manager

Include `exr/font_manager.h` (also included by `exreader.h`). The manager owns an
immutable index and can be shared by query threads. Creation scans configured
locations in order, indexes every Unicode face of TTF/OTF/TTC/OTC files, and
records non-font, damaged and optional missing inputs with reasons. No directory
is mandatory by convention: the host supplies its app/user/system locations,
or opts into platform directory discovery.

`tests/fixtures/font_manager/fonts.conf` is a runnable example. A production
configuration can use:

```ini
version = 1
font_dir = fonts
font_dir? = user-fonts
platform_dirs = yes
fallback = Noto Serif CJK SC
fallback = Noto Sans CJK SC
serif = Noto Serif CJK SC, SimSun, Times New Roman
sans_serif = Noto Sans CJK SC, Microsoft YaHei, Arial
cache = font-index.cache
```

Paths are UTF-8, resolved relative to the configuration file. Repeated
`font_file` entries accept individual files; `font_dir?` and `font_file?` mark
optional inputs. Required missing/unreadable locations return `EXR_IO` with the
path. A configuration with no usable fonts returns `EXR_FONT`. The host should
display the returned error. There is no implicit bundled-font substitution.

The same inputs can be supplied with `exr_font_manager_options` and
`exr_font_manager_create()`, avoiding configuration parsing. All option strings
are copied or consumed during creation. The header documents every function's
ownership and failure results.

```c
exr_font_manager *manager = NULL;
exr_font *font = NULL;
size_t *face_map = NULL, face_count = 0;
exr_error error = {0};
exr_status status = exr_font_manager_open(config_path, &manager, &error);
if (status != EXR_OK) return status;
status = exr_font_manager_create_font(manager, "serif", EXR_FONT_STYLE_REGULAR,
                                      &font, &face_map, &face_count, &error);
if (status != EXR_OK) { exr_font_manager_free(manager); return status; }
/* Pass font to exr_layout_create_ex(), exr_pager_create(), or exr_session_create().
   With embedded_fonts = 0, glyph.font_index indexes face_map, which indexes
   exr_font_manager_face(). EXR_GLYPH_MISSING reports an uncovered scalar.
   Keep manager alive while resolving face_map to borrowed face-info strings. */
/* Free layout/pager/session as usual, then: */
exr_font_free(font);
exr_free(face_map);
exr_font_manager_free(manager);
```

`pick(family, style, codepoint)` and `create_font(family, style)` share one chain:
requested family, its other styles, configured fallback families, serif defaults,
sans-serif defaults. Style distance prefers italic/bold agreement, then weight;
earlier locations break ties. A family contributes one nearest-weight face per
style category, preventing repeated installations from filling the 32 slots.
Localized family aliases are recognized. Generic
`serif` and `sans-serif` resolve through the configured lists. `pick()` reports
the manager face, fallback step and chain position; no coverage is the explicit
`SIZE_MAX` / `EXR_FONT_STEP_NONE` result.

`create_font()` materializes that requested family/style chain as a separate
font object. Layout preserves its base-face order even if document CSS names a
later fallback family; embedded `@font-face` rules retain their existing CSS
priority. Set `embedded_fonts = 0` to restrict layout to the manager chain. The
existing grapheme/UVS shaping rules may prefer a face covering an entire cluster.
Low-level `exr_shape()` still shapes its caller-selected face; layout performs
fallback before calling the shaper. Create a font per layout worker, following
the existing `exr_font` threading rules.

The engine caps loaded fonts at 32 faces / 128 MiB. The manager chain has the
same 32-face cap. Files changed or removed after indexing, and faces beyond the
byte budget, are omitted during materialization; the returned map describes the
faces actually loaded. If none load, creation returns `EXR_FONT`. Recreate the
manager to refresh its disk snapshot.

The cache contains a format/FreeType version, checksum, paths, file sizes,
modification times, names, styles and compressed cmap ranges. Each startup lists
locations again to detect additions/removals; unchanged font files need no
FreeType parsing. Corrupt/stale caches are rebuilt, and cache-write failure is
reported in `summary.cache_write_status`. Cache writes use a private temporary
file and atomic replacement. Keep the cache outside scanned directories to avoid
counting it as a skipped non-font file.

This adds public symbols and a new header, with no public structure or existing
function changes; ABI epoch remains 1. The private `exr_font` marker is propagated
when the engine combines embedded and host fonts. `exr_font_open()` / ordinary
`exr_font_create()` retain their existing CSS matching and fallback behavior.

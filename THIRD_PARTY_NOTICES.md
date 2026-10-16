# Native C dependencies

EXReader's own C sources are GPL-3.0-only. Third-party code keeps its original license.

| Component | Pinned source | License | Use |
| --- | --- | --- | --- |
| FreeType | VER-2-14-1, freetype/freetype | FreeType License OR GPL-2.0-only; FreeType License selected | Font loading, glyph metrics and rasterization |
| Expat | R_2_9_0, libexpat/libexpat | MIT | XML parsing with external entity resolution disabled |
| miniz | 3.1.2, richgel999/miniz | MIT | ZIP containers and decompression |
| SQLite | 3.54.0 amalgamation, sqlite.org | Public domain | Local bookshelf and annotations |
| stb_image | 2c980bb59875b0d32144a71867fbdebb2f77cd20, nothings/stb | MIT OR public domain; MIT selected | PNG/JPEG decoding only |

CMake verifies every source archive using the SHA-256 values in cmake/deps.cmake. CSS matching, line breaking, pagination, image placement, table layout, pixel compositing, document positions, the document model and format extraction are EXReader C code. FreeType supplies glyph metrics and rasterization; stb_image supplies decoded image pixels. License texts are included in the installed SDK under share/exreader/licenses.

The old JavaScript framework and reader are retained in Git history and their respective reader branches. They are not linked into this native engine.

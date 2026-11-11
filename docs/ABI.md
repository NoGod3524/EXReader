# ABI contract — 2026-11-08

> 本页的 389 项表格和平台结果是 2026-11-08 的历史快照。2026-11-09 当前
> `contract.json` 已有 394 项，公开头文件有 427 个函数；完整签名、所有权、线程规则和
> 稳定/实验/内部分类见 [API 参考](API.md)。当前覆盖和实际 DLL 导出由
> `python tools/check_sdk_docs.py --binary <当前构建的 DLL>` 校验；不要用历史表格作为当前函数总数。

基准 Windows DLL：389 个具名导出；SHA-256 `49344b73f2a875b0f5d05cf9c1ca589a46295410290235600a7566cc3d65950f`。SDK `3.42.0`，`exr_abi_version() == 1`。机器可读契约：[contract.json](../tools/abi/contract.json)。

这里的“稳定”表示本交付冻结该符号和公开声明；不代替上游长期兼容承诺。389 个符号均列入契约。签名取自本仓库 `include/exr/*.h`，类型、枚举、回调、结构体字段和所有权规则以对应头文件为准。C 链接名不编码函数类型，导出检查不能证明参数布局或调用行为；Windows 已逐个解析 389 个入口，并运行实际功能探针。

同平台/架构使用匹配头文件和 ABI：Windows x64 为 cdecl，Unix 为平台 C ABI；`size_t`/指针宽度、对齐和静态链接依赖随目标变化，不可把 Win32 结构体布局硬编码到所有目标。跨边界分配的内存用对应释放 API 或 `exr_free`；回调和借用内存遵守头文件生命周期。

## 校验规则

```sh
python tools/abi/check_exports.py /path/to/exreader.dll --output windows-exports.json
python tools/abi/check_exports.py /path/to/libexreader.so --output linux-strict.json
python tools/abi/check_exports.py /path/to/libexreader.a --allow-extra --output ios-required.json
python tools/abi/test_check_exports.py
```

默认要求导出/全局已定义符号与基准集合严格相同，缺失或多余均返回 1；解析/文件错误同样返回 1。`--allow-extra` 仍要求所有 389 个符号，但允许内部/第三方符号；它不是严格同集合通过。通用 Mach-O 每一切片单独校验；静态 `.a` 检查成员中外部已定义符号的集合，不把未定义引用算作实现。Mach-O 去掉 C 链接前缀 `_`；ELF 共享库读 DYNSYM，不把本地/隐藏符号算作导出。

Windows 默认严格校验通过 **389/389，extra=0**。已下载的 Android/macOS/iOS/Linux 动态库均 **389/389**；默认可见性额外暴露 2,410 个内部/第三方符号（Android 2,411 个），所以严格校验失败。原始清单与统计见 [export-reports.json](../evidence/platforms-20261108/export-reports.json)。在本轮禁止修改引擎/CMake 主构建的边界内保留此发布阻塞项；后续收敛导出控制后才能宣称严格一致。JNI 库是另一套 Java 桥接入口，不冒充核心库。

Android x86_64、macOS x86_64、iOS 聚合静态库：**待 CI 产物**，不计为通过。iOS 现有 `.dylib` 仅是替代产物，不能改后缀冒充 `.a`。分组件 reading-core/reading-library preset 禁用了 aggregate shared compat，不能用它们的绿色作业证明存在 `libexreader.dylib`。

读取范围：PE32/PE32+ 具名导出（包含转发条目）；ELF32/64（正常节表）；Mach-O32/64 的 LC_SYMTAB；fat32/64；GNU/BSD ar。剥除 LC_SYMTAB 的 Mach-O export-trie-only、ELF 扩展/缺失节表、LLVM bitcode、thin archive 均明确报错，不猜测通过。静态库的符号存在不代表依赖闭包已可链接，必须执行平台验收。

## 符号和声明

| 符号 | C 声明 | 稳定性 | 声明文件 |
|---|---|---|---|
| `exr_aac_available` | `int exr_aac_available(void);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_aac_format` | `const exr_aac_info *exr_aac_format(const exr_aac *aac);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_aac_free` | `void exr_aac_free(exr_aac *aac);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_aac_open` | `exr_status exr_aac_open(const char *path,const exr_control *control,exr_aac **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_aac_open_source` | `exr_status exr_aac_open_source(const exr_source *source,exr_aac **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_aac_read` | `exr_status exr_aac_read(exr_aac *aac,uint64_t first_frame,size_t frames,float *output,size_t *read, const exr_control *control,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_abi_version` | `uint32_t exr_abi_version(void);` | 本交付冻结（ABI 1） | [include/exr/base.h](../include/exr/base.h) |
| `exr_anchor_create` | `exr_status exr_anchor_create(const exr_document *doc, size_t start, size_t end, exr_anchor *out, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_anchor_free` | `void exr_anchor_free(exr_anchor *anchor);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_anchor_from_range` | `exr_status exr_anchor_from_range(exr_publication *publication,const exr_text_range *range, const exr_control *control,exr_content_anchor *out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_anchor_resolve` | `exr_status exr_anchor_resolve(const exr_document *doc, const exr_anchor *anchor, exr_anchor_match *match, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_anchor_resolve_ex` | `exr_status exr_anchor_resolve_ex(const exr_document *doc,const exr_anchor *anchor,const exr_control *control, exr_anchor_match *match,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_audio_bookmarks_free` | `void exr_audio_bookmarks_free(exr_audio_bookmark *bookmarks,size_t count);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_audio_chapters` | `const exr_audio_chapter *exr_audio_chapters(const exr_audio *audio,size_t *count);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_audio_checkpoint_free` | `void exr_audio_checkpoint_free(exr_audio_checkpoint *position);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_audio_create` | `exr_status exr_audio_create(const exr_audio_input *input,const exr_control *control,exr_audio **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_audio_duration` | `uint64_t exr_audio_duration(const exr_audio *audio);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_audio_free` | `void exr_audio_free(exr_audio *audio);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_audio_locate` | `exr_status exr_audio_locate(const exr_audio *audio,uint64_t time_ms,exr_audio_position *out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_audio_memory_size` | `size_t exr_audio_memory_size(const exr_audio *audio);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_audio_output_backend` | `const char *exr_audio_output_backend(void);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_audio_output_flush` | `exr_status exr_audio_output_flush(exr_audio_output *output,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_audio_output_free` | `void exr_audio_output_free(exr_audio_output *output);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_audio_output_open` | `exr_status exr_audio_output_open(uint32_t sample_rate,uint32_t channels,exr_audio_output **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_audio_output_pause` | `exr_status exr_audio_output_pause(exr_audio_output *output,int paused,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_audio_output_pending` | `exr_status exr_audio_output_pending(exr_audio_output *output,size_t *frames,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_audio_output_write` | `exr_status exr_audio_output_write(exr_audio_output *output,const float *samples,size_t frames,size_t *written,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_audio_player_create` | `exr_status exr_audio_player_create(exr_audio *audio,const exr_audio_backend *backend,exr_audio_player **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_audio_player_free` | `void exr_audio_player_free(exr_audio_player *player);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_audio_player_get` | `exr_status exr_audio_player_get(const exr_audio_player *player,exr_audio_playback *out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_audio_player_pause` | `exr_status exr_audio_player_pause(exr_audio_player *player,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_audio_player_play` | `exr_status exr_audio_player_play(exr_audio_player *player,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_audio_player_rate` | `exr_status exr_audio_player_rate(exr_audio_player *player,double rate,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_audio_player_report` | `exr_status exr_audio_player_report(exr_audio_player *player,uint64_t generation,size_t track,uint64_t offset_ms,int ended,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_audio_player_restore` | `exr_status exr_audio_player_restore(exr_audio_player *player,const char *track_id,uint64_t offset_ms,double rate,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_audio_player_seek` | `exr_status exr_audio_player_seek(exr_audio_player *player,uint64_t time_ms,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_audio_sync_at` | `exr_status exr_audio_sync_at(const exr_audio *audio,uint64_t time_ms,size_t from,const exr_control *control,size_t *index,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_audio_sync_text` | `exr_status exr_audio_sync_text(const exr_audio *audio,const char *part_id,size_t start,size_t end,size_t from, const exr_control *control,size_t *index,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_audio_syncs` | `const exr_audio_sync *exr_audio_syncs(const exr_audio *audio,size_t *count);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_audio_time` | `exr_status exr_audio_time(const exr_audio *audio,size_t track,uint64_t offset_ms,uint64_t *time_ms,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_audio_title` | `const char *exr_audio_title(const exr_audio *audio);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_audio_tracks` | `const exr_audio_track *exr_audio_tracks(const exr_audio *audio,size_t *count);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_bidi_analyze` | `exr_status exr_bidi_analyze(const char *text, size_t size, exr_direction direction, exr_bidi **out, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_bidi_base_level` | `unsigned exr_bidi_base_level(const exr_bidi *bidi, size_t scalar_index);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_bidi_free` | `void exr_bidi_free(exr_bidi *bidi);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_bidi_mirror` | `uint32_t exr_bidi_mirror(uint32_t codepoint);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_bidi_reorder` | `exr_status exr_bidi_reorder(const exr_bidi *bidi, size_t first, size_t count, size_t **out_order, size_t *out_count, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_bidi_scalars` | `const exr_bidi_scalar *exr_bidi_scalars(const exr_bidi *bidi, size_t *count);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_bitmap_free` | `void exr_bitmap_free(exr_bitmap *bitmap);` | 本交付冻结（ABI 1） | [include/exr/base.h](../include/exr/base.h) |
| `exr_bitmap_write_bmp` | `exr_status exr_bitmap_write_bmp(const exr_bitmap *bitmap, const char *path, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/base.h](../include/exr/base.h) |
| `exr_bitmap_write_png` | `exr_status exr_bitmap_write_png(const exr_bitmap *bitmap, const char *path, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/base.h](../include/exr/base.h) |
| `exr_books_free` | `void exr_books_free(exr_book *books, size_t count);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_canvas_begin_group` | `exr_status exr_canvas_begin_group(exr_canvas *canvas,double opacity,exr_blend_mode mode,unsigned flags,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/graphics.h](../include/exr/graphics.h) |
| `exr_canvas_begin_layer` | `exr_status exr_canvas_begin_layer(exr_canvas *canvas,double opacity,exr_blend_mode mode,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/graphics.h](../include/exr/graphics.h) |
| `exr_canvas_bitmap` | `const exr_bitmap *exr_canvas_bitmap(const exr_canvas *canvas);` | 本交付冻结（ABI 1） | [include/exr/graphics.h](../include/exr/graphics.h) |
| `exr_canvas_blend` | `exr_status exr_canvas_blend(exr_canvas *canvas,exr_blend_mode mode,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/graphics.h](../include/exr/graphics.h) |
| `exr_canvas_clip` | `exr_status exr_canvas_clip(exr_canvas *canvas,const exr_path_segment *segments,size_t count, const double matrix[6],exr_fill_rule rule,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/graphics.h](../include/exr/graphics.h) |
| `exr_canvas_create` | `exr_status exr_canvas_create(const exr_canvas_config *config,exr_canvas **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/graphics.h](../include/exr/graphics.h) |
| `exr_canvas_end_layer` | `exr_status exr_canvas_end_layer(exr_canvas *canvas,unsigned commit,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/graphics.h](../include/exr/graphics.h) |
| `exr_canvas_free` | `void exr_canvas_free(exr_canvas *canvas);` | 本交付冻结（ABI 1） | [include/exr/graphics.h](../include/exr/graphics.h) |
| `exr_canvas_get_sink` | `exr_status exr_canvas_get_sink(exr_canvas *canvas,exr_draw_sink *out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/graphics.h](../include/exr/graphics.h) |
| `exr_canvas_get_sink_ex` | `exr_status exr_canvas_get_sink_ex(exr_canvas *canvas,exr_draw_sink_ex *out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/graphics.h](../include/exr/graphics.h) |
| `exr_canvas_image` | `exr_status exr_canvas_image(exr_canvas *canvas,const exr_image_layer *image,const double matrix[6], double alpha,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/graphics.h](../include/exr/graphics.h) |
| `exr_canvas_image_cmyk` | `exr_status exr_canvas_image_cmyk(exr_canvas *canvas,const exr_image_layer *image,const exr_bitmap *inks, const double matrix[6],double alpha,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/graphics.h](../include/exr/graphics.h) |
| `exr_canvas_memory_size` | `size_t exr_canvas_memory_size(const exr_canvas *canvas);` | 本交付冻结（ABI 1） | [include/exr/graphics.h](../include/exr/graphics.h) |
| `exr_canvas_paint` | `exr_status exr_canvas_paint(exr_canvas *canvas,const exr_paint_source *source, const double matrix[6],double alpha,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/graphics.h](../include/exr/graphics.h) |
| `exr_canvas_path` | `exr_status exr_canvas_path(exr_canvas *canvas,const exr_path_segment *segments,size_t count, const double matrix[6],const exr_draw_style *style,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/graphics.h](../include/exr/graphics.h) |
| `exr_canvas_path_cmyk` | `exr_status exr_canvas_path_cmyk(exr_canvas *canvas,const exr_path_segment *segments,size_t count, const double matrix[6],const exr_draw_style *style, const double fill[4],const double stroke[4],exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/graphics.h](../include/exr/graphics.h) |
| `exr_canvas_restore` | `exr_status exr_canvas_restore(exr_canvas *canvas,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/graphics.h](../include/exr/graphics.h) |
| `exr_canvas_save` | `exr_status exr_canvas_save(exr_canvas *canvas,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/graphics.h](../include/exr/graphics.h) |
| `exr_canvas_set_layer_budget` | `exr_status exr_canvas_set_layer_budget(exr_canvas *canvas,size_t bytes,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/graphics.h](../include/exr/graphics.h) |
| `exr_canvas_take` | `exr_status exr_canvas_take(exr_canvas *canvas,exr_bitmap *out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/graphics.h](../include/exr/graphics.h) |
| `exr_chapter_options_defaults` | `exr_chapter_options exr_chapter_options_defaults(void);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_content_anchor_free` | `void exr_content_anchor_free(exr_content_anchor *anchor);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_document_blocks` | `const exr_block *exr_document_blocks(const exr_document *doc, size_t *count);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_document_cfi_create` | `exr_status exr_document_cfi_create(const exr_document *doc,size_t chapter,const exr_cfi_point *point, const exr_control *control,char **cfi,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_document_cfi_create_quoted` | `exr_status exr_document_cfi_create_quoted(const exr_document *doc,size_t chapter,const exr_cfi_point *point, size_t context_scalars,const exr_control *control,char **cfi,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_document_cfi_path_create` | `exr_status exr_document_cfi_path_create(const exr_document *doc,size_t chapter,const exr_cfi_point *point, const exr_control *control,char **path,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_document_cfi_path_create_quoted` | `exr_status exr_document_cfi_path_create_quoted(const exr_document *doc,size_t chapter,const exr_cfi_point *point, size_t context_scalars,const exr_control *control,char **path,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_document_cfi_path_resolve` | `exr_status exr_document_cfi_path_resolve(const exr_document *doc,size_t chapter,const char *path, const exr_control *control,exr_cfi_point *point,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_document_cfi_range_create` | `exr_status exr_document_cfi_range_create(const exr_document *doc,const exr_cfi_range *range, const exr_control *control,char **cfi,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_document_cfi_range_resolve` | `exr_status exr_document_cfi_range_resolve(const exr_document *doc,const char *cfi,const exr_control *control, exr_cfi_range *range,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_document_cfi_resolve` | `exr_status exr_document_cfi_resolve(const exr_document *doc,const char *cfi,const exr_control *control, size_t *chapter,exr_cfi_point *point,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_document_chapters` | `const exr_chapter *exr_document_chapters(const exr_document *doc, size_t *count);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_document_create` | `exr_status exr_document_create(const exr_document_input *input, exr_document **out, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_document_export` | `exr_status exr_document_export(const exr_document *doc, exr_format format, void **data, size_t *size, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/formats.h](../include/exr/formats.h) |
| `exr_document_export_control` | `exr_status exr_document_export_control(const exr_document *doc, exr_format format, const exr_control *control, void **data, size_t *size, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/formats.h](../include/exr/formats.h) |
| `exr_document_export_epub` | `exr_status exr_document_export_epub(const exr_document *doc, const exr_control *control, void **data, size_t *size, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/formats.h](../include/exr/formats.h) |
| `exr_document_export_html_bundle` | `exr_status exr_document_export_html_bundle(const exr_document *doc,const exr_control *control, void **data,size_t *size,char **entry_path,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/formats.h](../include/exr/formats.h) |
| `exr_document_find` | `exr_status exr_document_find(const exr_document *doc, const char *query, size_t from, size_t *start, size_t *end, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_document_format` | `exr_format exr_document_format(const exr_document *doc);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_document_free` | `void exr_document_free(exr_document *doc);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_document_locate` | `exr_status exr_document_locate(const exr_document *document,const char *fragment, exr_location *location,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_document_memory_size` | `size_t exr_document_memory_size(const exr_document *doc);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_document_navigation` | `exr_status exr_document_navigation(const exr_document *doc, exr_navigation **entries, size_t *count, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/formats.h](../include/exr/formats.h) |
| `exr_document_nodes` | `const exr_node *exr_document_nodes(const exr_document *doc, size_t *count);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_document_open` | `exr_status exr_document_open(const char *path, exr_document **out, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/formats.h](../include/exr/formats.h) |
| `exr_document_open_memory` | `exr_status exr_document_open_memory(exr_format format, const void *data, size_t size, exr_document **out, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/formats.h](../include/exr/formats.h) |
| `exr_document_resolve` | `exr_status exr_document_resolve(const exr_document *doc, size_t chapter, const char *uri, size_t *resource, size_t *node, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/formats.h](../include/exr/formats.h) |
| `exr_document_resource` | `exr_status exr_document_resource(const exr_document *doc, size_t resource, void **data, size_t *size, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/formats.h](../include/exr/formats.h) |
| `exr_document_resources` | `const exr_resource *exr_document_resources(const exr_document *doc, size_t *count);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_document_search` | `exr_status exr_document_search(exr_fixed_document *document,size_t offset,const char *needle, const exr_control *control,exr_search_match *match,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_document_text` | `const char *exr_document_text(const exr_document *doc, size_t *size);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_document_title` | `const char *exr_document_title(const exr_document *doc);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_draw_style_defaults` | `exr_draw_style exr_draw_style_defaults(void);` | 本交付冻结（ABI 1） | [include/exr/graphics.h](../include/exr/graphics.h) |
| `exr_epub_location_free` | `void exr_epub_location_free(exr_epub_location *location);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_epub_metadata_write` | `exr_status exr_epub_metadata_write(const void *data,size_t size, const exr_metadata_entry *changes,size_t count,const exr_epub_cover *cover, const exr_control *control,void **out,size_t *out_size,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/formats.h](../include/exr/formats.h) |
| `exr_epub_notes_free` | `void exr_epub_notes_free(exr_epub_note *notes,size_t count);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_epub_validate` | `exr_status exr_epub_validate(const char *path, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/formats.h](../include/exr/formats.h) |
| `exr_epub_validate_memory` | `exr_status exr_epub_validate_memory(const void *data, size_t size, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/formats.h](../include/exr/formats.h) |
| `exr_fixed_anchor_create` | `exr_status exr_fixed_anchor_create(const char *page_id,const exr_fixed_text *text,size_t start,size_t end, exr_fixed_anchor *out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_fixed_anchor_free` | `void exr_fixed_anchor_free(exr_fixed_anchor *anchor);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_fixed_anchor_resolve` | `exr_status exr_fixed_anchor_resolve(const char *page_id,const exr_fixed_text *text,const exr_fixed_anchor *anchor, const exr_control *control,exr_anchor_match *match,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_fixed_character_at` | `exr_status exr_fixed_character_at(exr_fixed_document *document,size_t page,double x,double y, const exr_control *control,exr_text_region *region, uint32_t *character,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_fixed_create` | `exr_status exr_fixed_create(const exr_fixed_input *input,exr_fixed_document **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_fixed_draw` | `exr_status exr_fixed_draw(exr_fixed_document *document,size_t page,const double matrix[6], const exr_draw_sink *sink,const exr_control *control,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_fixed_draw_ex` | `exr_status exr_fixed_draw_ex(exr_fixed_document *document,size_t page,const double matrix[6], const exr_draw_sink_ex *sink,const exr_control *control,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_fixed_free` | `void exr_fixed_free(exr_fixed_document *document);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_fixed_load_annotations` | `exr_status exr_fixed_load_annotations(exr_fixed_document *document,size_t page,const exr_control *control, exr_page_annotation **annotations,size_t *count,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_fixed_load_metadata` | `exr_status exr_fixed_load_metadata(exr_fixed_document *document,const exr_control *control, exr_metadata_entry **entries,size_t *count,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_fixed_load_text` | `exr_status exr_fixed_load_text(exr_fixed_document *document,size_t page,const exr_control *control, exr_fixed_text **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_fixed_memory_size` | `size_t exr_fixed_memory_size(const exr_fixed_document *document);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_fixed_notes_free` | `void exr_fixed_notes_free(exr_fixed_note *notes,size_t count);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_fixed_open` | `exr_status exr_fixed_open(const char *path,const exr_fixed_open_options *options, exr_fixed_document **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/pdf.h](../include/exr/pdf.h) |
| `exr_fixed_open_memory` | `exr_status exr_fixed_open_memory(exr_format format,const void *data,size_t size, const exr_fixed_open_options *options, exr_fixed_document **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/pdf.h](../include/exr/pdf.h) |
| `exr_fixed_page_text` | `exr_status exr_fixed_page_text(exr_fixed_document *document,size_t page,const exr_control *control, exr_fixed_text **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_fixed_pages` | `const exr_fixed_page *exr_fixed_pages(const exr_fixed_document *document,size_t *count);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_fixed_render` | `exr_status exr_fixed_render(exr_fixed_document *document,size_t page,double scale, const exr_fixed_render_options *options,exr_bitmap *out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_fixed_text_create` | `exr_status exr_fixed_text_create(const char *utf8,size_t size,const exr_text_region *regions,size_t count, const exr_control *control,exr_fixed_text **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_fixed_text_find` | `exr_status exr_fixed_text_find(const exr_fixed_text *text,const char *query,size_t query_size,size_t from, const exr_control *control,size_t *start,size_t *end,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_fixed_text_free` | `void exr_fixed_text_free(exr_fixed_text *text);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_fixed_text_hit` | `exr_status exr_fixed_text_hit(const exr_fixed_text *text,double x,double y,double max_distance,unsigned exclude_flags, const exr_control *control,size_t *region,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_fixed_text_memory_size` | `size_t exr_fixed_text_memory_size(const exr_fixed_text *text);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_fixed_text_regions` | `const exr_text_region *exr_fixed_text_regions(const exr_fixed_text *text,size_t *count);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_fixed_text_select` | `exr_status exr_fixed_text_select(const exr_fixed_text *text,size_t start,size_t end,const exr_control *control, exr_text_region **regions,size_t *count,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_fixed_text_string` | `const char *exr_fixed_text_string(const exr_fixed_text *text,size_t *size);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_fixed_title` | `const char *exr_fixed_title(const exr_fixed_document *document);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_flac_format` | `const exr_flac_info *exr_flac_format(const exr_flac *flac);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_flac_free` | `void exr_flac_free(exr_flac *flac);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_flac_open` | `exr_status exr_flac_open(const char *path,const exr_control *control,exr_flac **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_flac_open_source` | `exr_status exr_flac_open_source(const exr_source *source,exr_flac **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_flac_read` | `exr_status exr_flac_read(exr_flac *flac,uint64_t first_frame,size_t frames,float *output,size_t *read, const exr_control *control,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_font_axes` | `exr_status exr_font_axes(const exr_font *font,size_t font_index, exr_font_axis **out,size_t *count,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_font_color_info_get` | `exr_status exr_font_color_info_get(exr_font *font,size_t font_index,uint32_t glyph, exr_font_color_info *out,const exr_control *control,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_font_color_layers` | `exr_status exr_font_color_layers(exr_font *font,size_t font_index,uint32_t glyph, size_t palette,uint32_t foreground,exr_font_color_layer **out,size_t *count, const exr_control *control,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_font_color_palettes` | `exr_status exr_font_color_palettes(const exr_font *font,size_t font_index, size_t *palettes,size_t *entries,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_font_count` | `size_t exr_font_count(const exr_font *font);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_font_create` | `exr_status exr_font_create(const exr_font_input *inputs, size_t count, exr_font **out, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_font_create_glyphs` | `exr_status exr_font_create_glyphs(const exr_font_input *inputs, size_t count, exr_font **out, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_font_create_variable` | `exr_status exr_font_create_variable(const exr_font_input *inputs,size_t count, const exr_font_coordinate *coordinates,size_t coordinate_count,exr_font **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_font_free` | `void exr_font_free(exr_font *font);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_font_glyph_image` | `exr_status exr_font_glyph_image(exr_font *font,size_t font_index,uint32_t glyph,float pixels, exr_glyph_image *out,const exr_control *control,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_font_glyph_outline` | `exr_status exr_font_glyph_outline(exr_font *font,size_t font_index,uint32_t glyph, exr_path_segment **out,size_t *count, const exr_control *control,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_font_has_glyph` | `int exr_font_has_glyph(const exr_font *font, size_t font_index, uint32_t codepoint);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_font_manager_chain` | `exr_status exr_font_manager_chain(const exr_font_manager *manager, const char *family, unsigned style, exr_font_chain_link **out, size_t *count, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/font_manager.h](../include/exr/font_manager.h) |
| `exr_font_manager_create` | `exr_status exr_font_manager_create(const exr_font_manager_options *options, exr_font_manager **out, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/font_manager.h](../include/exr/font_manager.h) |
| `exr_font_manager_create_font` | `exr_status exr_font_manager_create_font(const exr_font_manager *manager, const char *family, unsigned style, exr_font **out, size_t **faces, size_t *count, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/font_manager.h](../include/exr/font_manager.h) |
| `exr_font_manager_face` | `exr_status exr_font_manager_face(const exr_font_manager *manager, size_t index, exr_font_face_info *out, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/font_manager.h](../include/exr/font_manager.h) |
| `exr_font_manager_face_count` | `size_t exr_font_manager_face_count(const exr_font_manager *manager);` | 本交付冻结（ABI 1） | [include/exr/font_manager.h](../include/exr/font_manager.h) |
| `exr_font_manager_face_covers` | `int exr_font_manager_face_covers(const exr_font_manager *manager, size_t index, uint32_t codepoint);` | 本交付冻结（ABI 1） | [include/exr/font_manager.h](../include/exr/font_manager.h) |
| `exr_font_manager_free` | `void exr_font_manager_free(exr_font_manager *manager);` | 本交付冻结（ABI 1） | [include/exr/font_manager.h](../include/exr/font_manager.h) |
| `exr_font_manager_has_family` | `int exr_font_manager_has_family(const exr_font_manager *manager, const char *family);` | 本交付冻结（ABI 1） | [include/exr/font_manager.h](../include/exr/font_manager.h) |
| `exr_font_manager_open` | `exr_status exr_font_manager_open(const char *config_path, exr_font_manager **out, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/font_manager.h](../include/exr/font_manager.h) |
| `exr_font_manager_pick` | `exr_status exr_font_manager_pick(const exr_font_manager *manager, const char *family, unsigned style, uint32_t codepoint, exr_font_pick_result *out, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/font_manager.h](../include/exr/font_manager.h) |
| `exr_font_manager_skip` | `int exr_font_manager_skip(const exr_font_manager *manager, size_t index, exr_font_skip *out);` | 本交付冻结（ABI 1） | [include/exr/font_manager.h](../include/exr/font_manager.h) |
| `exr_font_manager_summary_get` | `exr_status exr_font_manager_summary_get(const exr_font_manager *manager, exr_font_manager_summary *out, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/font_manager.h](../include/exr/font_manager.h) |
| `exr_font_open` | `exr_status exr_font_open(const char *path, exr_font **out, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_font_source` | `exr_status exr_font_source(const exr_font *font, size_t index, exr_font_input *source, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_free` | `void exr_free(void *memory);` | 本交付冻结（ABI 1） | [include/exr/base.h](../include/exr/base.h) |
| `exr_glyph_matrix` | `exr_status exr_glyph_matrix(const exr_glyph *glyph, double matrix[6], exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_hit_test` | `exr_status exr_hit_test(const exr_layout *layout,size_t part,size_t page,float x,float y, exr_text_position *out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_hyphenation_breaks` | `const exr_hyphen_break *exr_hyphenation_breaks(const exr_hyphenation *result,size_t *count);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_hyphenation_free` | `void exr_hyphenation_free(exr_hyphenation *result);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_hyphenation_memory_size` | `size_t exr_hyphenation_memory_size(const exr_hyphenation *result);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_hyphenator_breaks` | `exr_status exr_hyphenator_breaks(exr_hyphenator *hyphenator,const char *language, const char *word,size_t size,unsigned char *breaks,const exr_control *control,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_hyphenator_create` | `exr_status exr_hyphenator_create(const exr_hyphen_provider *provider, exr_hyphenator **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_hyphenator_create_builtin` | `exr_status exr_hyphenator_create_builtin(unsigned left_min,unsigned right_min,int auto_default, const exr_control *control,exr_hyphenator **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_hyphenator_create_discretionary` | `exr_status exr_hyphenator_create_discretionary(const exr_hyphen_discretionary_provider *provider, exr_hyphenator **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_hyphenator_create_patterns` | `exr_status exr_hyphenator_create_patterns(const exr_hyphen_pattern_input *inputs, size_t count,size_t byte_budget,const exr_control *control,exr_hyphenator **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_hyphenator_create_patterns_ex` | `exr_status exr_hyphenator_create_patterns_ex(const exr_hyphen_pattern_input *inputs, size_t count,size_t byte_budget,exr_hyphen_case_policy case_policy,const exr_control *control, exr_hyphenator **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_hyphenator_free` | `void exr_hyphenator_free(exr_hyphenator *hyphenator);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_hyphenator_memory_size` | `size_t exr_hyphenator_memory_size(const exr_hyphenator *hyphenator);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_hyphenator_query` | `exr_status exr_hyphenator_query(exr_hyphenator *hyphenator,const char *language, const char *word,size_t size,const exr_control *control,exr_hyphenation **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_image_decode` | `exr_status exr_image_decode(const void *data, size_t size, exr_bitmap *rgba, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/graphics.h](../include/exr/graphics.h) |
| `exr_image_decode_page` | `exr_status exr_image_decode_page(const void *data,size_t size,size_t page, exr_bitmap *rgba,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/graphics.h](../include/exr/graphics.h) |
| `exr_image_page_count` | `exr_status exr_image_page_count(const void *data,size_t size,size_t *count, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/graphics.h](../include/exr/graphics.h) |
| `exr_image_page_dimensions` | `exr_status exr_image_page_dimensions(const void *data,size_t size,size_t page, uint32_t *width,uint32_t *height,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/graphics.h](../include/exr/graphics.h) |
| `exr_layout_blocks` | `const exr_layout_block *exr_layout_blocks(const exr_layout *layout, size_t *count);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_layout_boxes` | `const exr_box *exr_layout_boxes(const exr_layout *layout, size_t *count);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_layout_config_defaults` | `exr_layout_config exr_layout_config_defaults(void);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_layout_create` | `exr_status exr_layout_create(const exr_document *doc, exr_font *font, const exr_layout_options *options, exr_layout **out, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_layout_create_ex` | `exr_status exr_layout_create_ex(const exr_document *doc, exr_font *font, const exr_layout_config *config, exr_layout **out, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_layout_create_hyphenated` | `exr_status exr_layout_create_hyphenated(const exr_document *doc,exr_font *font, const exr_layout_config *config,exr_hyphenator *hyphenator,exr_layout **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_layout_create_positioned` | `exr_status exr_layout_create_positioned(const exr_document *doc, exr_font *font, const exr_positioned_input *input, const exr_layout_config *config, exr_layout **out, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_layout_defaults` | `exr_layout_options exr_layout_defaults(void);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_layout_font` | `exr_font *exr_layout_font(const exr_layout *layout);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_layout_free` | `void exr_layout_free(exr_layout *layout);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_layout_glyphs` | `const exr_glyph *exr_layout_glyphs(const exr_layout *layout, size_t *count);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_layout_hit_test` | `size_t exr_layout_hit_test(const exr_layout *layout, size_t page, float x, float y);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_layout_image` | `const exr_bitmap *exr_layout_image(const exr_layout *layout, size_t resource);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_layout_lines` | `const exr_line *exr_layout_lines(const exr_layout *layout, size_t *count);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_layout_memory_size` | `size_t exr_layout_memory_size(const exr_layout *layout);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_layout_page_at` | `size_t exr_layout_page_at(const exr_layout *layout, size_t utf8_offset);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_layout_page_kind` | `exr_page_kind exr_layout_page_kind(const exr_layout *layout, size_t page);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_layout_page_structure` | `exr_page_structure exr_layout_page_structure(const exr_layout *layout, size_t page);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_layout_pages` | `const exr_page *exr_layout_pages(const exr_layout *layout, size_t *count);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_layout_paints` | `const exr_paint *exr_layout_paints(const exr_layout *layout, size_t page, size_t *count);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_layout_writing_mode` | `exr_writing_mode exr_layout_writing_mode(const exr_layout *layout);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_library_audio_bookmark` | `exr_status exr_library_audio_bookmark(exr_library *library,const char *audio_id,const exr_audio_bookmark *bookmark,int64_t *id,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_audio_bookmarks` | `exr_status exr_library_audio_bookmarks(exr_library *library,const char *audio_id,exr_audio_bookmark **bookmarks,size_t *count,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_audio_resume` | `exr_status exr_library_audio_resume(exr_library *library,const char *audio_id,const exr_audio_checkpoint *position,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_audio_resume_get` | `exr_status exr_library_audio_resume_get(exr_library *library,const char *audio_id,exr_audio_checkpoint *position,int *found,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_backup` | `exr_status exr_library_backup(exr_library *library, const char *path, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_blob` | `exr_status exr_library_blob(exr_library *library, int64_t id, int cover, void **data, size_t *size, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_books` | `exr_status exr_library_books(exr_library *library, const char *query, exr_book **books, size_t *count, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_clear_audio` | `exr_status exr_library_clear_audio(exr_library *library,const char *audio_id,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_clear_progress` | `exr_status exr_library_clear_progress(exr_library *library,int64_t book_id,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_close` | `void exr_library_close(exr_library *library);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_cover` | `exr_status exr_library_cover(exr_library *library, int64_t id, const void *data, size_t size, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_delete` | `exr_status exr_library_delete(exr_library *library, int64_t id, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_document` | `exr_status exr_library_document(exr_library *library, int64_t id, exr_document **doc, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_epub_info_get` | `exr_status exr_library_epub_info_get(exr_library *library,int64_t id, exr_library_epub_info *info,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_epub_note` | `exr_status exr_library_epub_note(exr_library *library,const exr_epub_note *note, int64_t *id,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_epub_notes` | `exr_status exr_library_epub_notes(exr_library *library,int64_t book_id, exr_epub_note **notes,size_t *count,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_epub_progress` | `exr_status exr_library_epub_progress(exr_library *library,int64_t id, const exr_epub_location *location,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_epub_progress_get` | `exr_status exr_library_epub_progress_get(exr_library *library,int64_t id, exr_epub_location *location,int *present,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_fixed` | `exr_status exr_library_fixed(exr_library *library,int64_t id,const exr_fixed_open_options *options, exr_fixed_document **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_fixed_note` | `exr_status exr_library_fixed_note(exr_library *library,const exr_fixed_note *note,const exr_control *control, int64_t *id,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_fixed_notes` | `exr_status exr_library_fixed_notes(exr_library *library,int64_t book_id,exr_fixed_note **notes, size_t *count,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_fixed_source` | `exr_status exr_library_fixed_source(exr_library *library,int64_t id,const exr_fixed_open_options *options, exr_fixed_document **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_import` | `exr_status exr_library_import(exr_library *library, exr_format format, const void *data, size_t size, const char *title, int64_t *id, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_import_file` | `exr_status exr_library_import_file(exr_library *library,exr_format format,const char *path, const char *title,int64_t *id,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_import_file_unique` | `exr_status exr_library_import_file_unique(exr_library *library,exr_format format,const char *path, const char *title,int64_t *id,int *created,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_import_source` | `exr_status exr_library_import_source(exr_library *library,exr_format format,const exr_source *source, const char *title,int64_t *id,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_import_source_unique` | `exr_status exr_library_import_source_unique(exr_library *library,exr_format format,const exr_source *source, const char *title,int64_t *id,int *created,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_import_unique` | `exr_status exr_library_import_unique(exr_library *library,exr_format format,const void *data, size_t size,const char *title,int64_t *id,int *created,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_note` | `exr_status exr_library_note(exr_library *library, const exr_note *note, int64_t *id, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_note_text` | `exr_status exr_library_note_text(exr_library *library,int64_t note_id,const char *text,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_notes` | `exr_status exr_library_notes(exr_library *library, int64_t book_id, exr_note **notes, size_t *count, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_open` | `exr_status exr_library_open(const char *path, exr_library **out, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_progress` | `exr_status exr_library_progress(exr_library *library,int64_t book_id,const exr_anchor *point,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_progress_get` | `exr_status exr_library_progress_get(exr_library *library,int64_t book_id,exr_anchor *point,exr_anchor_state *state,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_reanchor` | `exr_status exr_library_reanchor(exr_library *library,int64_t book_id,size_t fallback_position, const exr_control *control,exr_library_relocation *report,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_relocation_free` | `void exr_library_relocation_free(exr_library_relocation *report);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_remove_audio_bookmark` | `exr_status exr_library_remove_audio_bookmark(exr_library *library,int64_t id,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_remove_epub_note` | `exr_status exr_library_remove_epub_note(exr_library *library,int64_t id,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_remove_fixed_note` | `exr_status exr_library_remove_fixed_note(exr_library *library,int64_t id,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_remove_note` | `exr_status exr_library_remove_note(exr_library *library, int64_t id, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_source` | `exr_status exr_library_source(exr_library *library,int64_t id,exr_source *source, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_library_update` | `exr_status exr_library_update(exr_library *library, const exr_book *book, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_m4b_available` | `int exr_m4b_available(void);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_m4b_format` | `const exr_m4b_info *exr_m4b_format(const exr_m4b *m4b);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_m4b_free` | `void exr_m4b_free(exr_m4b *m4b);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_m4b_inspect` | `exr_status exr_m4b_inspect(const char *path,const exr_control *control,exr_m4b_inspection **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_m4b_inspect_source` | `exr_status exr_m4b_inspect_source(const exr_source *source,exr_m4b_inspection **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_m4b_inspection_chapters` | `const exr_audio_chapter *exr_m4b_inspection_chapters(const exr_m4b_inspection *inspection,size_t *count);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_m4b_inspection_cover` | `const void *exr_m4b_inspection_cover(const exr_m4b_inspection *inspection,size_t *size,const char **media_type);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_m4b_inspection_duration` | `uint64_t exr_m4b_inspection_duration(const exr_m4b_inspection *inspection);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_m4b_inspection_free` | `void exr_m4b_inspection_free(exr_m4b_inspection *inspection);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_m4b_inspection_metadata` | `const exr_metadata_entry *exr_m4b_inspection_metadata(const exr_m4b_inspection *inspection,size_t *count);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_m4b_open` | `exr_status exr_m4b_open(const char *path,const exr_control *control,exr_m4b **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_m4b_open_source` | `exr_status exr_m4b_open_source(const exr_source *source,exr_m4b **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_m4b_read` | `exr_status exr_m4b_read(exr_m4b *m4b,uint64_t first_frame,size_t frames,float *output,size_t *read, const exr_control *control,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_metadata_free` | `void exr_metadata_free(exr_metadata_entry *entries,size_t count);` | 本交付冻结（ABI 1） | [include/exr/base.h](../include/exr/base.h) |
| `exr_metadata_read_xmp` | `exr_status exr_metadata_read_xmp(const void *data,size_t size,const exr_control *control, exr_metadata_entry **entries,size_t *count,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/formats.h](../include/exr/formats.h) |
| `exr_mp3_available` | `int exr_mp3_available(void);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_mp3_format` | `const exr_mp3_info *exr_mp3_format(const exr_mp3 *mp3);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_mp3_free` | `void exr_mp3_free(exr_mp3 *mp3);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_mp3_open` | `exr_status exr_mp3_open(const char *path,const exr_control *control,exr_mp3 **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_mp3_open_source` | `exr_status exr_mp3_open_source(const exr_source *source,exr_mp3 **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_mp3_read` | `exr_status exr_mp3_read(exr_mp3 *mp3,uint64_t first_frame,size_t frames,float *output,size_t *read, const exr_control *control,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_navigation_free` | `void exr_navigation_free(exr_navigation *entries, size_t count);` | 本交付冻结（ABI 1） | [include/exr/formats.h](../include/exr/formats.h) |
| `exr_node_attribute` | `const char *exr_node_attribute(const exr_node *node, const char *name);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_notes_free` | `void exr_notes_free(exr_note *notes, size_t count);` | 本交付冻结（ABI 1） | [include/exr/library.h](../include/exr/library.h) |
| `exr_page_annotations_free` | `void exr_page_annotations_free(exr_page_annotation *annotations,size_t count);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_pager_anchor_create` | `exr_status exr_pager_anchor_create(exr_pager *pager,size_t start,size_t end, const exr_control *control,exr_anchor *anchor,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_pager_anchor_resolve` | `exr_status exr_pager_anchor_resolve(exr_pager *pager,const exr_anchor *anchor, const exr_control *control,exr_anchor_match *match,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_pager_cached_bytes` | `size_t exr_pager_cached_bytes(const exr_pager *pager);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_pager_cached_count` | `size_t exr_pager_cached_count(const exr_pager *pager);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_pager_cfi_create` | `exr_status exr_pager_cfi_create(exr_pager *pager,const exr_cfi_point *point, size_t context_scalars,const exr_control *control,char **cfi,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_pager_cfi_resolve` | `exr_status exr_pager_cfi_resolve(exr_pager *pager,const char *cfi, const exr_control *control,exr_cfi_point *point,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_pager_chapter_statistics` | `exr_chapter_stats exr_pager_chapter_statistics(const exr_pager *pager);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_pager_create` | `exr_status exr_pager_create(const exr_document *doc, exr_font *font, const exr_layout_config *config, exr_pager **out, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_pager_free` | `void exr_pager_free(exr_pager *pager);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_pager_get` | `exr_status exr_pager_get(exr_pager *pager, size_t page, const exr_layout **out, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_pager_next` | `exr_status exr_pager_next(exr_pager *pager, exr_layout **out, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_pager_position` | `size_t exr_pager_position(const exr_pager *pager);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_pager_read_text` | `exr_status exr_pager_read_text(exr_pager *pager,size_t start,size_t end, exr_text_sink_fn sink,void *context,const exr_control *control,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_pager_set_cache` | `exr_status exr_pager_set_cache(exr_pager *pager, size_t capacity, size_t byte_budget, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_pager_set_checkpoints` | `exr_status exr_pager_set_checkpoints(exr_pager *pager, size_t capacity, size_t byte_budget, size_t interval, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_pager_set_control` | `exr_status exr_pager_set_control(exr_pager *pager, const exr_control *control, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_pager_set_hyphenator` | `exr_status exr_pager_set_hyphenator(exr_pager *pager,exr_hyphenator *hyphenator,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_pager_statistics` | `exr_pager_stats exr_pager_statistics(const exr_pager *pager);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_pcm_create` | `exr_status exr_pcm_create(const exr_pcm_input *input,exr_pcm **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_pcm_format` | `const exr_pcm_info *exr_pcm_format(const exr_pcm *pcm);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_pcm_free` | `void exr_pcm_free(exr_pcm *pcm);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_pcm_open` | `exr_status exr_pcm_open(const char *path,const exr_control *control,exr_pcm **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_pcm_open_source` | `exr_status exr_pcm_open_source(const exr_source *source,exr_pcm **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_pcm_read` | `exr_status exr_pcm_read(exr_pcm *pcm,uint64_t first_frame,size_t frames,float *output,size_t *read, const exr_control *control,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_pdf_annotation_remove` | `exr_status exr_pdf_annotation_remove(const void *data,size_t size,size_t page,const char *id, const exr_control *control,void **out,size_t *out_size,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/pdf_edit.h](../include/exr/pdf_edit.h) |
| `exr_pdf_annotation_write` | `exr_status exr_pdf_annotation_write(const void *data,size_t size,size_t page, const exr_page_annotation *annotation,const exr_pdf_annotation_write_options *options, void **out,size_t *out_size,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/pdf_edit.h](../include/exr/pdf_edit.h) |
| `exr_pdf_annotation_write_defaults` | `exr_pdf_annotation_write_options exr_pdf_annotation_write_defaults(void);` | 本交付冻结（ABI 1） | [include/exr/pdf_edit.h](../include/exr/pdf_edit.h) |
| `exr_pdf_crypto_available` | `int exr_pdf_crypto_available(void);` | 本交付冻结（ABI 1） | [include/exr/pdf.h](../include/exr/pdf.h) |
| `exr_pdf_form_defaults` | `exr_pdf_form_options exr_pdf_form_defaults(void);` | 本交付冻结（ABI 1） | [include/exr/pdf_edit.h](../include/exr/pdf_edit.h) |
| `exr_pdf_form_free` | `void exr_pdf_form_free(exr_pdf_form_field *fields,size_t count);` | 本交付冻结（ABI 1） | [include/exr/pdf_edit.h](../include/exr/pdf_edit.h) |
| `exr_pdf_form_read` | `exr_status exr_pdf_form_read(const void *data,size_t size,const exr_pdf_form_options *options, exr_pdf_form_field **out,size_t *count,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/pdf_edit.h](../include/exr/pdf_edit.h) |
| `exr_pdf_form_write` | `exr_status exr_pdf_form_write(const void *data,size_t size,const exr_pdf_form_change *changes,size_t count, const exr_pdf_form_write_options *options,void **out,size_t *out_size,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/pdf_edit.h](../include/exr/pdf_edit.h) |
| `exr_pdf_form_write_defaults` | `exr_pdf_form_write_options exr_pdf_form_write_defaults(void);` | 本交付冻结（ABI 1） | [include/exr/pdf_edit.h](../include/exr/pdf_edit.h) |
| `exr_pdf_metadata_write` | `exr_status exr_pdf_metadata_write(const void *data,size_t size,const exr_metadata_entry *changes,size_t count, const exr_control *control,void **out,size_t *out_size,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/pdf_edit.h](../include/exr/pdf_edit.h) |
| `exr_publication_cfi_create` | `exr_status exr_publication_cfi_create(exr_publication *publication,size_t part,const exr_document *document, const exr_cfi_point *point,const exr_control *control,char **cfi,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_publication_cfi_create_quoted` | `exr_status exr_publication_cfi_create_quoted(exr_publication *publication,size_t part,const exr_document *document, const exr_cfi_point *point,size_t context_scalars,const exr_control *control,char **cfi,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_publication_cfi_resolve` | `exr_status exr_publication_cfi_resolve(exr_publication *publication,const char *cfi,const exr_control *control, size_t *part,exr_document **document,exr_cfi_point *point,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_publication_create` | `exr_status exr_publication_create(const exr_publication_input *input, exr_publication **out, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_publication_free` | `void exr_publication_free(exr_publication *publication);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_publication_load` | `exr_status exr_publication_load(exr_publication *publication, size_t part, exr_document **out, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_publication_locate` | `exr_status exr_publication_locate(exr_publication *publication, const exr_target *target,exr_location *location,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_publication_missing_targets` | `const exr_target *exr_publication_missing_targets(const exr_publication *publication,size_t *count);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_publication_navigation` | `exr_status exr_publication_navigation(exr_publication *publication, const exr_navigation **entries, size_t *count, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_publication_open` | `exr_status exr_publication_open(const char *path, exr_publication **out, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_publication_open_memory` | `exr_status exr_publication_open_memory(exr_format format, const void *data, size_t size, exr_publication **out, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_publication_open_source` | `exr_status exr_publication_open_source(const exr_source *source, exr_publication **out, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_publication_pager_create` | `exr_status exr_publication_pager_create(exr_publication *publication,size_t part, exr_font *font,const exr_layout_config *config,const exr_chapter_options *options, exr_pager **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_publication_parts` | `const exr_part *exr_publication_parts(const exr_publication *publication, size_t *count);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_publication_resolve_href` | `exr_status exr_publication_resolve_href(const exr_publication *publication, const char *base,const char *href,char fragment[2048],exr_target *target,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_publication_search` | `exr_status exr_publication_search(exr_publication *publication,exr_text_position from, const char *needle,unsigned flags,const exr_control *control,exr_search_result *result,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_publication_search_all` | `exr_status exr_publication_search_all(exr_publication *publication,const char *needle, unsigned flags,exr_search_fn callback,void *context,const exr_control *control,size_t *count,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_publication_target_at` | `exr_status exr_publication_target_at(exr_publication *publication, size_t part,size_t offset,size_t *entry,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_publication_title` | `const char *exr_publication_title(const exr_publication *publication);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_publication_toc` | `exr_status exr_publication_toc(exr_publication *publication, const exr_toc_entry **entries,size_t *count,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_publication_toc_insert_before` | `exr_status exr_publication_toc_insert_before(exr_publication *publication, size_t *part, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_range_expand` | `exr_status exr_range_expand(exr_publication *publication,const exr_text_range *range, exr_range_unit unit,const exr_control *control,exr_text_range *out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_range_from_anchor` | `exr_status exr_range_from_anchor(exr_publication *publication,const exr_content_anchor *anchor, const exr_control *control,exr_text_range_match *out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_render_page` | `exr_status exr_render_page(const exr_layout *layout, exr_font *font, size_t page, exr_bitmap *bitmap, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/render.h](../include/exr/render.h) |
| `exr_render_page_background` | `exr_status exr_render_page_background(const exr_layout *layout, exr_font *font, size_t page, unsigned channels, uint32_t background_rgba, const exr_control *control, exr_bitmap *out, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/render.h](../include/exr/render.h) |
| `exr_render_page_color` | `exr_status exr_render_page_color(const exr_layout *layout, exr_font *font, size_t page, exr_bitmap *bitmap, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/render.h](../include/exr/render.h) |
| `exr_render_page_ex` | `exr_status exr_render_page_ex(const exr_layout *layout, exr_font *font, size_t page, unsigned channels, const exr_control *control, exr_bitmap *out, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/render.h](../include/exr/render.h) |
| `exr_session_cached` | `size_t exr_session_cached(const exr_session *session);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_session_cached_bytes` | `size_t exr_session_cached_bytes(const exr_session *session);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_session_clear` | `void exr_session_clear(exr_session *session);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_session_create` | `exr_status exr_session_create(exr_publication *publication, exr_font *font, const exr_layout_config *config, size_t capacity, exr_session **out, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_session_free` | `void exr_session_free(exr_session *session);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_session_get` | `exr_status exr_session_get(exr_session *session, size_t part, const exr_document **document, const exr_layout **layout, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_session_set_budget` | `exr_status exr_session_set_budget(exr_session *session, size_t bytes, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_session_set_hyphenator` | `exr_status exr_session_set_hyphenator(exr_session *session,exr_hyphenator *hyphenator,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_shape` | `exr_status exr_shape(exr_font *font, size_t font_index, const char *utf8, size_t size, const exr_shape_options *options, exr_shaped_glyph **out, size_t *out_count, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_shape_defaults` | `exr_shape_options exr_shape_defaults(void);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_shape_vertical` | `exr_status exr_shape_vertical(exr_font *font, size_t font_index, const char *utf8, size_t size, const exr_shape_options *options, exr_shaped_glyph **out, size_t *out_count, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_stretch_create` | `exr_status exr_stretch_create(uint32_t sample_rate,uint32_t channels,double rate,exr_stretch **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_stretch_finish` | `exr_status exr_stretch_finish(exr_stretch *stretch,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_stretch_free` | `void exr_stretch_free(exr_stretch *stretch);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_stretch_get` | `exr_status exr_stretch_get(const exr_stretch *stretch,exr_stretch_state *out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_stretch_pull` | `exr_status exr_stretch_pull(exr_stretch *stretch,float *output,size_t frames,size_t *read,const exr_control *control,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_stretch_push` | `exr_status exr_stretch_push(exr_stretch *stretch,const float *input,size_t frames,size_t *accepted,const exr_control *control,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_stretch_reset` | `exr_status exr_stretch_reset(exr_stretch *stretch,double rate,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_text_analyze` | `exr_status exr_text_analyze(const char *text, size_t size, unsigned char **boundaries, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/text.h](../include/exr/text.h) |
| `exr_text_annotation_export` | `exr_status exr_text_annotation_export(const exr_text_annotation *annotation,char **json,size_t *size,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_text_annotation_free` | `void exr_text_annotation_free(exr_text_annotation *annotation);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_text_annotation_import` | `exr_status exr_text_annotation_import(const void *json,size_t size,exr_text_annotation *annotation,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/document.h](../include/exr/document.h) |
| `exr_text_index_available` | `int exr_text_index_available(void);` | 本交付冻结（ABI 1） | [include/exr/textindex.h](../include/exr/textindex.h) |
| `exr_text_index_close` | `void exr_text_index_close(exr_text_index *index);` | 本交付冻结（ABI 1） | [include/exr/textindex.h](../include/exr/textindex.h) |
| `exr_text_index_open` | `exr_status exr_text_index_open(const char *path,exr_text_index **index,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/textindex.h](../include/exr/textindex.h) |
| `exr_text_index_put` | `exr_status exr_text_index_put(exr_text_index *index,const char *source,const char *part,const void *text, size_t size,const exr_control *control,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/textindex.h](../include/exr/textindex.h) |
| `exr_text_index_query` | `exr_status exr_text_index_query(exr_text_index *index,const char *source,const void *query,size_t size, const exr_control *control,exr_text_query **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/textindex.h](../include/exr/textindex.h) |
| `exr_text_index_remove` | `exr_status exr_text_index_remove(exr_text_index *index,const char *source,const char *part, const exr_control *control,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/textindex.h](../include/exr/textindex.h) |
| `exr_text_index_replace` | `exr_status exr_text_index_replace(exr_text_index *index,const char *source,exr_text_part_fn provider,void *context, const exr_control *control,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/textindex.h](../include/exr/textindex.h) |
| `exr_text_query_free` | `void exr_text_query_free(exr_text_query *query);` | 本交付冻结（ABI 1） | [include/exr/textindex.h](../include/exr/textindex.h) |
| `exr_text_query_next` | `exr_status exr_text_query_next(exr_text_query *query,exr_text_hit *hit,int *found,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/textindex.h](../include/exr/textindex.h) |
| `exr_toc_pages_create` | `exr_status exr_toc_pages_create(exr_publication *publication, exr_font *font, const exr_layout_config *config, const exr_toc_page_options *options, exr_layout **out, exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_toc_pages_entries` | `exr_status exr_toc_pages_entries(const exr_layout *layout, size_t page, size_t *first, size_t *count);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_toc_pages_entry_at` | `exr_status exr_toc_pages_entry_at(const exr_layout *layout, size_t page, float x, float y, size_t *entry);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_toc_pages_entry_for_offset` | `size_t exr_toc_pages_entry_for_offset(const exr_layout *layout, size_t offset);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_toc_pages_label` | `const char *exr_toc_pages_label(const exr_layout *layout, size_t page);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_txt_anchor_create_source` | `exr_status exr_txt_anchor_create_source(const exr_source *source,size_t start,size_t end, exr_anchor *anchor,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/formats.h](../include/exr/formats.h) |
| `exr_txt_anchor_resolve_source` | `exr_status exr_txt_anchor_resolve_source(const exr_source *source,const exr_anchor *anchor, exr_anchor_match *match,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/formats.h](../include/exr/formats.h) |
| `exr_txt_cursor_checkpoint` | `exr_status exr_txt_cursor_checkpoint(const exr_txt_cursor *cursor,exr_txt_checkpoint *checkpoint,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/formats.h](../include/exr/formats.h) |
| `exr_txt_cursor_create` | `exr_status exr_txt_cursor_create(const exr_source *source,exr_txt_cursor **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/formats.h](../include/exr/formats.h) |
| `exr_txt_cursor_free` | `void exr_txt_cursor_free(exr_txt_cursor *cursor);` | 本交付冻结（ABI 1） | [include/exr/formats.h](../include/exr/formats.h) |
| `exr_txt_cursor_next` | `exr_status exr_txt_cursor_next(exr_txt_cursor *cursor,uint64_t *offset, const char **text,size_t *size,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/formats.h](../include/exr/formats.h) |
| `exr_txt_cursor_restore` | `exr_status exr_txt_cursor_restore(exr_txt_cursor *cursor,const exr_txt_checkpoint *checkpoint,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/formats.h](../include/exr/formats.h) |
| `exr_txt_find_source` | `exr_status exr_txt_find_source(const exr_source *source,const char *query,uint64_t from, uint64_t *start,uint64_t *end,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/formats.h](../include/exr/formats.h) |
| `exr_txt_pager_create` | `exr_status exr_txt_pager_create(const exr_source *source,exr_font *font, const exr_layout_config *config,exr_pager **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/layout.h](../include/exr/layout.h) |
| `exr_txt_scan_source` | `exr_status exr_txt_scan_source(const exr_source *source,exr_txt_paragraph_fn paragraph, void *context,uint64_t *extent,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/formats.h](../include/exr/formats.h) |
| `exr_version` | `const char *exr_version(void);` | 本交付冻结（ABI 1） | [include/exr/base.h](../include/exr/base.h) |
| `exr_viewport_create` | `exr_status exr_viewport_create(const exr_page_geometry *page,double scale, exr_viewport *out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/base.h](../include/exr/base.h) |
| `exr_wave_format` | `const exr_wave_info *exr_wave_format(const exr_wave *wave);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_wave_free` | `void exr_wave_free(exr_wave *wave);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_wave_open` | `exr_status exr_wave_open(const char *path,const exr_control *control,exr_wave **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_wave_open_source` | `exr_status exr_wave_open_source(const exr_source *source,exr_wave **out,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |
| `exr_wave_read` | `exr_status exr_wave_read(exr_wave *wave,uint64_t first_frame,size_t frames,float *output,size_t *read, const exr_control *control,exr_error *error);` | 本交付冻结（ABI 1） | [include/exr/audio.h](../include/exr/audio.h) |

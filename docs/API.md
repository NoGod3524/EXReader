# EXReader C SDK API 参考

本参考覆盖当前 `include/` 的 **19/19 个公开头文件、469/469 个公开函数声明（100%）**，
按 **15/15 个模块**组织，每个模块附一个完整、独立的 C11 程序。
16 个头文件声明函数；`exreader.h`、`exr/core.h` 为聚合入口，`exr/version.h` 提供版本宏。
`EXR_API` 函数声明是本参考的统计口径；类型、枚举、宏和回调类型不另计为导出函数。

原 SDK 文档验收时，Windows 聚合 DLL 的 427 个具名导出全部覆盖：**427/427（100%）**；
当前 [ABI 契约](../tools/abi/contract.json) 的 **394/394** 项也全部覆盖，现在另外记录 75 个未冻结声明。
任务中的“约 389”是 [历史 ABI 快照](ABI.md) 的数值，不能作为当前总数。
真实编译、运行与导出比对见 [示例验收](examples/README.md)、[编译输出](examples/compile-output.txt)、
[运行输出](examples/test-output.txt)、[机器统计](examples/verification.json)。

合入 main 后新增的编辑模型与重排声明见 `exr/edit.h`、`exr/reflow.h`。当前 main 没有 `src/docx_edit.c`；
模型函数须配置 `EXR_EDIT_MODEL_SOURCE` 接入匹配的 X1 实现，重排函数在缺少模型时返回 `EXR_UNSUPPORTED`。
这里的 469 是头文件声明数，不是默认 DLL 导出实测数；上面的编译和机器统计保留原验收时间点，
新增接口的配置、限制和锚点字段见 [X2 接口说明](X2_REFLOW.md)。

## 阅读约定与 ABI 分类

| 标注 | 本参考中函数数 | 含义 |
|---|---:|---|
| 稳定 | 394 | 已列入当前 ABI 1 符号契约；沿用现有交付冻结口径，不新增跨版本二进制布局保证 |
| 实验 | 75 | 当前公开头文件已声明，尚未加入冻结清单；其中 edit.h 的模型声明需要外部 X1 实现，不能假设默认 DLL 已导出；升级时核对签名与结构布局 |
| 内部 | 0 / 469 | 当前公开声明没有内部入口；`src/` 私有函数及第三方依赖不属于 SDK 合约，不应由外部调用 |

“内部”适用于所有仅出现在 `src/*_internal.h` 等私有声明中的实现，例如
`exr_fail`、`exr_control_poll`、`exr_grow`、`exr_copy`（[私有基础头](../src/base_internal.h)）。
某些平台动态库可能暴露这些实现或第三方符号；可被链接器找到不等于公开 API。
本页 0/469 仅说明公开函数的分类，不表示引擎没有内部函数，也不把历史其他平台的多余导出数量当作本次测量。

所有字符串均为 UTF-8。普通文本范围用规范化文本的 UTF-8 字节半开区间 `[start, end)`，
不是原文件偏移、Unicode 字符序号或 CFI 的 UTF-16 code units。索引通常从 0 起；`SIZE_MAX`
等“未找到”哨兵按具体条目读取。`EXR_OK` 只表示调用成功，不保证存在命中、文本层或下一页。

带 `error` 的接口通常允许 NULL；否则它指向宿主提供的 `exr_error`，失败写入 code/message，
以函数返回值判断成功，不依赖上一次留下的错误文本。下面逐项列出主要失败条件；会调用
provider、读取源、分配内存的接口还可能传播相应回调、I/O、取消和内存错误。

| 状态 | 宿主处理 |
|---|---|
| `EXR_ARGUMENT` | 修正空指针、索引、范围或配置大小 |
| `EXR_MEMORY` / `EXR_LIMIT` | 分别为分配失败 / 显式预算或实现上限；缩小任务或调整允许调整的预算 |
| `EXR_IO` / `EXR_DATABASE` | 检查源回调、文件权限或数据库诊断 |
| `EXR_ENCODING` / `EXR_FORMAT` / `EXR_FONT` | 编码、格式结构或字体不可接受；检查具体 message |
| `EXR_CANCELLED` | 丢弃未完成输出；按该对象的失败恢复规则重试 |
| `EXR_PASSWORD` | PDF 口令缺失/错误，重新打开 |
| `EXR_UNSUPPORTED` | 识别到的功能或组件当前不支持，不能当作成功的空结果 |
| `EXR_NO_TEXT_LAYER` / `EXR_NO_TEXT_AT_POINT` | 分别为没有语义文本 / 点击处未落在可见文字 quad |
| `EXR_DRM_*` | 按口令缺失、口令错误、许可过期、不支持或无效许可分别提示，见 [DRM](DRM.md) |

创建输出使用空指针/零结构；重复写入前释放旧结果。跨 DLL 分配的内存使用对应 `*_free` 或
`exr_free`，不能换成宿主 CRT 的 `free`。借用视图不单独释放。`struct_size`/`size` 按头文件
要求填 `sizeof`，有 defaults 函数就先取默认值，不能假设全零配置等于默认配置。

线程规则按“同一对象”理解：默认由宿主串行调用、更新和释放；`const` 不自动代表内部不写缓存。
显式允许共享的例外在对应条目中列出。同步进度/取消/provider 回调在调用线程运行，不得重入或销毁
当前对象；独立 worker 各自持有可变字体和阅读状态。完整事件循环见 [接入指南](INTEGRATION.md)。

## 模块索引

| 模块 | 函数数 | 完整示例 |
|---|---:|---|
| 基础 | 8 | [base.c](examples/base.c) |
| 图形 | 25 | [graphics.c](examples/graphics.c) |
| 字体与文字 | 49 | [font.c](examples/font.c) |
| 字典 | 6 | [dictionary.c](examples/dictionary.c) |
| 渲染 | 4 | [render.c](examples/render.c) |
| 全文索引 | 9 | [textindex.c](examples/textindex.c) |
| 文档 | 72 | [document.c](examples/document.c) |
| 分页 | 58 | [pagination.c](examples/pagination.c) |
| 搜索 | 10 | [search.c](examples/search.c) |
| 标注 | 45 | [annotation.c](examples/annotation.c) |
| 目录 | 17 | [toc.c](examples/toc.c) |
| 书库 | 49 | [library.c](examples/library.c) |
| 格式与转换 | 34 | [formats.c](examples/formats.c) |
| 固定版面与 PDF | 12 | [pdf.c](examples/pdf.c) |
| 音频 | 76 | [audio.c](examples/audio.c) |

以下示例源码与 `docs/examples/*.c` 一一对应；CMake 在完整测试构建中编译并链接它们，
`tools/check_sdk_docs.py` 校验每段示例与文件一致、每条签名与公开头文件一致。



## 基础

提供版本、坐标变换、跨库内存释放和位图导出。

最小可编译示例：[examples/base.c](examples/base.c)。

<!-- example: docs/examples/base.c -->
```c
/* SPDX-License-Identifier: MIT */
#include <exr/base.h>
#include <stdio.h>

int main(void) {
  exr_page_geometry page = {{0, 0, 612, 792}, 1, 0, 0};
  exr_viewport viewport = {0};
  exr_error error = {0};
  exr_status status = exr_viewport_create(&page, 96.0 / 72.0, &viewport, &error);
  if (status == EXR_OK)
    printf("SDK %s, ABI %u: %.0f x %.0f pixels\n", exr_version(),
           (unsigned)exr_abi_version(), viewport.width, viewport.height);
  else
    fprintf(stderr, "%s\n", error.message);
  return status == EXR_OK ? 0 : 1;
}
```

### `exr_viewport_create`

**签名** `exr_status exr_viewport_create(const exr_page_geometry *page,double scale, exr_viewport *out,exr_error *error);`

**ABI** 稳定；声明：[exr/base.h](../include/exr/base.h)。

**参数** `page`：bounds、正 unit_scale、0/90/180/270 旋转与 y_down；`scale`：正缩放；`out`：尺寸、正逆矩阵。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；非法/空/非有限几何为 EXR_ARGUMENT，坐标或精度预算超限为 EXR_LIMIT。失败清零 out。

**线程** 无共享可变状态；独立输出可并发，输入在调用期间不可修改。

**所有权** 输出为宿主值结构，不需 free。

### `exr_metadata_free`

**签名** `void exr_metadata_free(exr_metadata_entry *entries,size_t count);`

**ABI** 稳定；声明：[exr/base.h](../include/exr/base.h)。

**参数** `entries`：拥有的元数据数组；`count`：条目数（NULL 仅配 count=0）。

**返回与失败** 无返回值；count 必须与分配匹配。

**线程** 与该数组的读取/释放串行。

**所有权** 释放每项 key/value 及数组。

### `exr_version`

**签名** `const char *exr_version(void);`

**ABI** 稳定；声明：[exr/base.h](../include/exr/base.h)。

**参数** 无参数。

**返回与失败** 返回当前 SDK 版本字符串；无失败返回。

**线程** 无共享可变状态；独立输出可并发，输入在调用期间不可修改。

**所有权** 静态字符串，禁止 free。

### `exr_abi_version`

**签名** `uint32_t exr_abi_version(void);`

**ABI** 稳定；声明：[exr/base.h](../include/exr/base.h)。

**参数** 无参数。

**返回与失败** 返回 ABI 调用/二进制布局纪元，当前为 1；无失败返回。

**线程** 无共享可变状态；独立输出可并发，输入在调用期间不可修改。

**所有权** 返回标量。

### `exr_free`

**签名** `void exr_free(void *memory);`

**ABI** 稳定；声明：[exr/base.h](../include/exr/base.h)。

**参数** `memory`：SDK 明确要求用 exr_free 释放的独占分配，允许 NULL。

**返回与失败** 无返回值；不接受借用指针、已释放指针或需要专用析构的对象。

**线程** 不得与同一内存的访问或另一释放并发。

**所有权** 释放该分配；指针随后失效。

### `exr_bitmap_write_png`

**签名** `exr_status exr_bitmap_write_png(const exr_bitmap *bitmap, const char *path, exr_error *error);`

**ABI** 稳定；声明：[exr/base.h](../include/exr/base.h)。

**参数** `bitmap`：灰度或 straight RGBA 像素，channels=0 按灰度；`path`：UTF-8 输出文件路径。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；空像素、错误通道/stride、尺寸>16384 或像素>64 MiB 为 EXR_ARGUMENT；分配 EXR_MEMORY，压缩 EXR_FORMAT，写文件 EXR_IO。

**线程** 只读同一位图可并发；同一目标路径写入须串行。

**所有权** 借用像素，写出 PNG（可覆盖文件）；调用者仍负责 bitmap。

### `exr_bitmap_free`

**签名** `void exr_bitmap_free(exr_bitmap *bitmap);`

**ABI** 稳定；声明：[exr/base.h](../include/exr/base.h)。

**参数** `bitmap`：拥有像素的位图结构地址，允许 NULL。

**返回与失败** 无返回值；有效 bitmap 被清零。

**线程** 与像素访问/上传消费串行。

**所有权** 仅释放 pixels，不释放宿主的 bitmap 结构；不能用于 canvas/layout 借用像素。

### `exr_bitmap_write_bmp`

**签名** `exr_status exr_bitmap_write_bmp(const exr_bitmap *bitmap, const char *path, exr_error *error);`

**ABI** 稳定；声明：[exr/base.h](../include/exr/base.h)。

**参数** `bitmap`：灰度或 straight RGBA、stride 至少 width*channels；`path`：UTF-8 输出路径。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK，输出 24-bit BMP，RGBA 合成到白底；参数/尺寸非法 EXR_ARGUMENT，分配 EXR_MEMORY，写入 EXR_IO。

**线程** 只读位图可并发；同一输出路径写入须串行。

**所有权** 借用像素，调用者仍负责 bitmap；输出文件可被覆盖。

## 图形

用独立 CPU 画布合成路径、图像、裁剪和透明组。

最小可编译示例：[examples/graphics.c](examples/graphics.c)。

<!-- example: docs/examples/graphics.c -->
```c
/* SPDX-License-Identifier: MIT */
#include <exr/graphics.h>
#include <stdio.h>

int main(void) {
  exr_canvas_config config = {0};
  exr_canvas *canvas = NULL;
  exr_bitmap bitmap = {0};
  exr_error error = {0};
  config.width = 32;
  config.height = 32;
  config.channels = 4;
  config.background = 0x336699FFu;
  exr_status status = exr_canvas_create(&config, &canvas, &error);
  if (status == EXR_OK) status = exr_canvas_take(canvas, &bitmap, &error);
  if (status == EXR_OK) printf("canvas transferred: %u x %u\n", bitmap.width, bitmap.height);
  else fprintf(stderr, "%s\n", error.message);
  exr_bitmap_free(&bitmap);
  exr_canvas_free(canvas);
  return status == EXR_OK ? 0 : 1;
}
```

### `exr_draw_style_defaults`

**签名** `exr_draw_style exr_draw_style_defaults(void);`

**ABI** 稳定；声明：[exr/graphics.h](../include/exr/graphics.h)。

**参数** 无参数。

**返回与失败** 返回黑色填充、1 像素描边宽度的默认 style；无失败返回。

**线程** 无共享可变状态；独立输出可并发，输入在调用期间不可修改。

**所有权** 值结构，无需释放。

### `exr_canvas_create`

**签名** `exr_status exr_canvas_create(const exr_canvas_config *config,exr_canvas **out,exr_error *error);`

**ABI** 稳定；声明：[exr/graphics.h](../include/exr/graphics.h)。

**参数** `config`：width/height、channels（0=RGBA，1/4）、RRGGBBAA 背景、mask_budget（0=64 MiB）和 control；`out`：新画布。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；尺寸/通道非法 EXR_ARGUMENT，像素>64 MiB EXR_LIMIT，分配 EXR_MEMORY，取消 EXR_CANCELLED；失败 *out=NULL。

**线程** 无共享可变状态；独立输出可并发，输入在调用期间不可修改。

**所有权** canvas 由 exr_canvas_free；config 值被复制，control.context 活到 free。

### `exr_canvas_free`

**签名** `void exr_canvas_free(exr_canvas *canvas);`

**ABI** 稳定；声明：[exr/graphics.h](../include/exr/graphics.h)。

**参数** `canvas`：画布或 NULL。

**返回与失败** 无返回值。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 释放画布及未 take 的像素、mask、layer；借出的 bitmap/sink 失效。

### `exr_canvas_memory_size`

**签名** `size_t exr_canvas_memory_size(const exr_canvas *canvas);`

**ABI** 稳定；声明：[exr/graphics.h](../include/exr/graphics.h)。

**参数** `canvas`：画布或 NULL。

**返回与失败** 返回当前拥有的分配容量字节数；NULL 返回 0。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 返回标量，不需释放。

### `exr_canvas_bitmap`

**签名** `const exr_bitmap *exr_canvas_bitmap(const exr_canvas *canvas);`

**ABI** 稳定；声明：[exr/graphics.h](../include/exr/graphics.h)。

**参数** `canvas`：待观察画布。

**返回与失败** 返回当前位图；NULL、已 take 或失败画布返回 NULL。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 借用至修改/take/free；不能 exr_bitmap_free 此视图。

### `exr_canvas_take`

**签名** `exr_status exr_canvas_take(exr_canvas *canvas,exr_bitmap *out,exr_error *error);`

**ABI** 稳定；声明：[exr/graphics.h](../include/exr/graphics.h)。

**参数** `canvas`：绘制完成画布；`out`：空位图结构。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；已消费/空画布、未结束 layer 或缺输出 EXR_ARGUMENT；否则传播取消或此前绘制失败。失败 out 清零。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 成功转移 pixels 到 out，用 exr_bitmap_free；canvas 本身仍需 free，不能再绘制。

### `exr_canvas_blend`

**签名** `exr_status exr_canvas_blend(exr_canvas *canvas,exr_blend_mode mode,exr_error *error);`

**ABI** 稳定；声明：[exr/graphics.h](../include/exr/graphics.h)。

**参数** `canvas`：画布；`mode`：EXR_BLEND_*。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；非法 mode/画布 EXR_ARGUMENT；传播取消、既有失败。失败可能将画布置为不可用。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 输入只借用到本次调用结束；不转移所有权。

### `exr_canvas_begin_group`

**签名** `exr_status exr_canvas_begin_group(exr_canvas *canvas,double opacity,exr_blend_mode mode,unsigned flags,exr_error *error);`

**ABI** 稳定；声明：[exr/graphics.h](../include/exr/graphics.h)。

**参数** `canvas`：画布；`opacity`：0..1；`mode`：组提交混合模式；`flags`：ISOLATED/KNOCKOUT/CMYK/RGB 组合。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；非法 opacity/flags/颜色空间组合 EXR_ARGUMENT，不支持组合 EXR_UNSUPPORTED；层预算/深度 EXR_LIMIT，分配 EXR_MEMORY，取消/既有失败透传。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 组由 end_layer 消费；保存父 clip/soft mask，内部 soft mask 清空。

### `exr_canvas_begin_layer`

**签名** `exr_status exr_canvas_begin_layer(exr_canvas *canvas,double opacity,exr_blend_mode mode,exr_error *error);`

**ABI** 稳定；声明：[exr/graphics.h](../include/exr/graphics.h)。

**参数** `canvas`：画布；`opacity`：0..1；`mode`：合成回父层的混合方式。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK，开启隔离透明 RGB layer；参数 EXR_ARGUMENT，层预算 EXR_LIMIT，分配 EXR_MEMORY，取消/既有失败透传。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 需要配对 exr_canvas_end_layer；其余输入按值。

### `exr_canvas_end_layer`

**签名** `exr_status exr_canvas_end_layer(exr_canvas *canvas,unsigned commit,exr_error *error);`

**ABI** 稳定；声明：[exr/graphics.h](../include/exr/graphics.h)。

**参数** `canvas`：画布；`commit`：0 丢弃、非零合成。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；没有未结束 layer 等非法状态 EXR_ARGUMENT；合成错误/取消/已记录失败透传。有效 end 即使失败也消费该层。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 关闭 begin_layer 或 begin_group；commit=0 丢弃并撤销内部 scope。

### `exr_canvas_set_layer_budget`

**签名** `exr_status exr_canvas_set_layer_budget(exr_canvas *canvas,size_t bytes,exr_error *error);`

**ABI** 稳定；声明：[exr/graphics.h](../include/exr/graphics.h)。

**参数** `canvas`：尚未进入层的画布；`bytes`：总 layer 内存预算，0=64 MiB。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；在 layer 中设置或无效画布 EXR_ARGUMENT；取消/既有失败透传。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 仅保存预算标量。

### `exr_canvas_save`

**签名** `exr_status exr_canvas_save(exr_canvas *canvas,exr_error *error);`

**ABI** 稳定；声明：[exr/graphics.h](../include/exr/graphics.h)。

**参数** `canvas`：画布。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK，保存 clip/blend/alpha 状态；堆栈 160 层超限 EXR_LIMIT；非法画布/取消/既有失败透传。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 保存的状态由 restore 或 free 释放。

### `exr_canvas_restore`

**签名** `exr_status exr_canvas_restore(exr_canvas *canvas,exr_error *error);`

**ABI** 稳定；声明：[exr/graphics.h](../include/exr/graphics.h)。

**参数** `canvas`：有可恢复状态的画布。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；空栈或越过当前 layer 边界 EXR_ARGUMENT；取消/既有失败透传。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 消费一次 save；不释放 canvas。

### `exr_canvas_path`

**签名** `exr_status exr_canvas_path(exr_canvas *canvas,const exr_path_segment *segments,size_t count, const double matrix[6],const exr_draw_style *style,exr_error *error);`

**ABI** 稳定；声明：[exr/graphics.h](../include/exr/graphics.h)。

**参数** `canvas`：画布；`segments`：路径段数组；`count`：段数；`matrix`：源到设备的 [a,b,c,d,e,f]，NULL=单位矩阵；`style`：填充/描边、线宽/虚线，NULL=默认。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；无效路径、矩阵、style EXR_ARGUMENT；复杂度/预算 EXR_LIMIT，分配 EXR_MEMORY，取消 EXR_CANCELLED。绘制失败使画布不可继续。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 输入只借用到本次调用结束；不转移所有权。

### `exr_canvas_path_cmyk`

**签名** `exr_status exr_canvas_path_cmyk(exr_canvas *canvas,const exr_path_segment *segments,size_t count, const double matrix[6],const exr_draw_style *style, const double fill[4],const double stroke[4],exr_error *error);`

**ABI** 稳定；声明：[exr/graphics.h](../include/exr/graphics.h)。

**参数** `canvas`：画布；`segments`：路径段数组；`count`：段数；`matrix`：源到设备的 [a,b,c,d,e,f]，NULL=单位矩阵；`style`：绘制 flags/alpha/描边参数；`fill`、`stroke`：C/M/Y/K 四个 0..1 分量，替代 style RGB。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；参数 EXR_ARGUMENT，DeviceGray 组中 CMYK EXR_UNSUPPORTED；复杂度/预算 EXR_LIMIT，分配/取消或绘制错误透传并使画布不可用。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 输入只借用到本次调用结束；不转移所有权。

### `exr_canvas_clip`

**签名** `exr_status exr_canvas_clip(exr_canvas *canvas,const exr_path_segment *segments,size_t count, const double matrix[6],exr_fill_rule rule,exr_error *error);`

**ABI** 稳定；声明：[exr/graphics.h](../include/exr/graphics.h)。

**参数** `canvas`：画布；`segments`：路径段数组；`count`：段数；`matrix`：源到设备的 [a,b,c,d,e,f]，NULL=单位矩阵；`rule`：NONZERO 或 EVENODD 填充规则。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK，路径与现有 clip 相交；参数 EXR_ARGUMENT，mask/路径预算 EXR_LIMIT，分配 EXR_MEMORY，取消/既有失败透传。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 输入只借用到本次调用结束；不转移所有权。

### `exr_canvas_image`

**签名** `exr_status exr_canvas_image(exr_canvas *canvas,const exr_image_layer *image,const double matrix[6], double alpha,exr_error *error);`

**ABI** 稳定；声明：[exr/graphics.h](../include/exr/graphics.h)。

**参数** `canvas`：画布；`image`：带像素、可选 mask/matte/interpolate 的图层；`matrix`：图像到画布变换；`alpha`：0..1 常量透明度 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；像素/矩阵/alpha 非法 EXR_ARGUMENT；工作/分配/取消失败透传；失败画布不可继续。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 输入只借用到本次调用结束；不转移所有权。

### `exr_canvas_image_cmyk`

**签名** `exr_status exr_canvas_image_cmyk(exr_canvas *canvas,const exr_image_layer *image,const exr_bitmap *inks, const double matrix[6],double alpha,exr_error *error);`

**ABI** 稳定；声明：[exr/graphics.h](../include/exr/graphics.h)。

**参数** `canvas`：画布；`image`：带像素、可选 mask/matte/interpolate 的图层；`matrix`：图像到画布变换；`alpha`：0..1 常量透明度；`inks`：与图像同尺寸的四通道 C/M/Y/K 字节位图，matte 已去除。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；参数/尺寸不匹配 EXR_ARGUMENT，预算/分配/取消失败透传；CMYK 组采用 inks，其他空间用 image 的 RGB fallback。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 输入只借用到本次调用结束；不转移所有权。

### `exr_canvas_paint`

**签名** `exr_status exr_canvas_paint(exr_canvas *canvas,const exr_paint_source *source, const double matrix[6],double alpha,exr_error *error);`

**ABI** 稳定；声明：[exr/graphics.h](../include/exr/graphics.h)。

**参数** `canvas`：画布；`source`：struct_size、sample 回调和 context；`matrix`：源到画布变换，NULL=单位；`alpha`：0..1。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；非法结构/矩阵/采样分量 EXR_ARGUMENT，工作预算 EXR_LIMIT，分配/取消和 sample 返回错误透传；失败使画布不可用。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** source/context 同步借用；sample 不得修改当前 canvas 或保留输出指针。

### `exr_canvas_get_sink_ex`

**签名** `exr_status exr_canvas_get_sink_ex(exr_canvas *canvas,exr_draw_sink_ex *out,exr_error *error);`

**ABI** 稳定；声明：[exr/graphics.h](../include/exr/graphics.h)。

**参数** `canvas`：画布；`out`：绘图回调接收器，先设 out->struct_size=sizeof(*out)。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；NULL canvas/out、过小 struct_size 为 EXR_ARGUMENT。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** out 为值结构，context 借用 canvas，必须在 canvas_free 前停止使用。

### `exr_canvas_get_sink`

**签名** `exr_status exr_canvas_get_sink(exr_canvas *canvas,exr_draw_sink *out,exr_error *error);`

**ABI** 稳定；声明：[exr/graphics.h](../include/exr/graphics.h)。

**参数** `canvas`：画布；`out`：绘图回调接收器。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；NULL canvas/out 为 EXR_ARGUMENT。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** out 为值结构，context 借用 canvas，必须在 canvas_free 前停止使用。

### `exr_image_decode`

**签名** `exr_status exr_image_decode(const void *data, size_t size, exr_bitmap *rgba, exr_error *error);`

**ABI** 稳定；声明：[exr/graphics.h](../include/exr/graphics.h)。

**参数** `data`：编码图像字节；`size`：字节数；`rgba`：空输出位图。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK，解码第一页/帧为 RGBA；参数 EXR_ARGUMENT，损坏/未知格式 EXR_FORMAT，禁用 codec EXR_UNSUPPORTED，尺寸/展开超限 EXR_LIMIT，分配 EXR_MEMORY。

**线程** 无共享可变状态；独立输出可并发，输入在调用期间不可修改。

**所有权** 输入仅本次借用；输出由 exr_bitmap_free。

### `exr_image_page_count`

**签名** `exr_status exr_image_page_count(const void *data,size_t size,size_t *count, exr_error *error);`

**ABI** 稳定；声明：[exr/graphics.h](../include/exr/graphics.h)。

**参数** `data`：编码图像；`size`：字节数；`count`：源顺序帧/页数输出。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；参数 EXR_ARGUMENT，损坏 EXR_FORMAT，禁用 codec EXR_UNSUPPORTED；>4096 帧/页、尺寸或展开预算超限 EXR_LIMIT。

**线程** 无共享可变状态；独立输出可并发，输入在调用期间不可修改。

**所有权** 输入借用，输出标量。

### `exr_image_page_dimensions`

**签名** `exr_status exr_image_page_dimensions(const void *data,size_t size,size_t page, uint32_t *width,uint32_t *height,exr_error *error);`

**ABI** 稳定；声明：[exr/graphics.h](../include/exr/graphics.h)。

**参数** `data`：编码图像；`size`：字节数；`page`：零基帧/页号；`width/height`：像素尺寸输出。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；参数/越界页号失败，损坏 EXR_FORMAT、禁用 codec EXR_UNSUPPORTED；尺寸>8192 或像素>1600 万等 EXR_LIMIT。

**线程** 无共享可变状态；独立输出可并发，输入在调用期间不可修改。

**所有权** 输入借用，尺寸标量无需释放。

### `exr_image_decode_page`

**签名** `exr_status exr_image_decode_page(const void *data,size_t size,size_t page, exr_bitmap *rgba,exr_error *error);`

**ABI** 稳定；声明：[exr/graphics.h](../include/exr/graphics.h)。

**参数** `data`：编码图像；`size`：字节数；`page`：零基帧/页号；`rgba`：空输出位图。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；参数/越界页号失败，损坏 EXR_FORMAT、禁用 codec EXR_UNSUPPORTED；尺寸/展开超限 EXR_LIMIT，分配 EXR_MEMORY。

**线程** 无共享可变状态；独立输出可并发，输入在调用期间不可修改。

**所有权** 输入借用，输出 pixels 由 exr_bitmap_free。

## 字体与文字

发现并选择字体，提供 Unicode 分析、OpenType 塑形和断词。

最小可编译示例：[examples/font.c](examples/font.c)。

<!-- example: docs/examples/font.c -->
```c
/* SPDX-License-Identifier: MIT */
#include <exr/font_manager.h>
#include <stdio.h>

int main(int argc, char **argv) {
  exr_font_location location = {0};
  exr_font_manager_options options = {0};
  exr_font_manager *manager = NULL;
  exr_font *font = NULL;
  exr_error error = {0};
  exr_status status;
  size_t count = 0;
  if (argc != 2) { fprintf(stderr, "usage: font font-directory\n"); return 2; }
  location.path = argv[1];
  location.kind = EXR_FONT_LOCATION_DIRECTORY;
  options.struct_size = sizeof(options);
  options.locations = &location;
  options.location_count = 1;
  status = exr_font_manager_create(&options, &manager, &error);
  if (status == EXR_OK)
    status = exr_font_manager_create_font(manager, NULL, EXR_FONT_STYLE_REGULAR,
                                          &font, NULL, &count, &error);
  if (status == EXR_OK) printf("fallback faces=%zu\n", count);
  else fprintf(stderr, "%s\n", error.message);
  exr_font_free(font);
  exr_font_manager_free(manager);
  return status == EXR_OK ? 0 : 1;
}
```

### `exr_text_analyze`

**签名** `exr_status exr_text_analyze(const char *text, size_t size, unsigned char **boundaries, exr_error *error);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `text`：UTF-8 字节；`size`：长度（最多 64 MiB）；`boundaries`：size+1 字节标志数组输出。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；非法参数 EXR_ARGUMENT、UTF-8 EXR_ENCODING、长度/工作超限 EXR_LIMIT、分配 EXR_MEMORY。按 UTF-8 字节索引返回 grapheme/line 边界；末尾含 MANDATORY。

**线程** 无共享可变状态；独立输出可并发，输入在调用期间不可修改。

**所有权** 输入借用；数组由 exr_free。

### `exr_bidi_analyze`

**签名** `exr_status exr_bidi_analyze(const char *text, size_t size, exr_direction direction, exr_bidi **out, exr_error *error);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `text`：UTF-8；`size`：字节数；`direction`：AUTO/LTR/RTL；`out`：段落双向分析结果。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；参数 EXR_ARGUMENT、UTF-8 EXR_ENCODING，超过 4M scalar EXR_LIMIT，分配 EXR_MEMORY。

**线程** 无共享可变状态；独立输出可并发，输入在调用期间不可修改。

**所有权** 新结果由 exr_bidi_free；输入只在调用内借用。

### `exr_bidi_scalars`

**签名** `const exr_bidi_scalar *exr_bidi_scalars(const exr_bidi *bidi, size_t *count);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `bidi`：分析对象；`count`：可选 scalar 数量输出。

**返回与失败** 返回 scalar 数组，NULL 对象返回 NULL/0；start/end 是 UTF-8 字节区间。

**线程** 只读查询可并发；不得并发 free。

**所有权** 数组借用至 bidi_free。

### `exr_bidi_reorder`

**签名** `exr_status exr_bidi_reorder(const exr_bidi *bidi, size_t first, size_t count, size_t **out_order, size_t *out_count, exr_error *error);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `bidi`：分析对象；`first/count`：scalar 索引行片段；`out_order`：视觉顺序 scalar 索引数组；`out_count`：输出项数。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK，排除 X9 controls；非法区间/输出 EXR_ARGUMENT，分配 EXR_MEMORY。

**线程** 只读 bidi 可并发；不得并发 free。

**所有权** 新数组由 exr_free，与 bidi 独立。

### `exr_bidi_free`

**签名** `void exr_bidi_free(exr_bidi *bidi);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `bidi`：结果或 NULL。

**返回与失败** 无返回值。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 销毁分析对象；借用 scalar 视图失效。

### `exr_bidi_mirror`

**签名** `uint32_t exr_bidi_mirror(uint32_t codepoint);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `codepoint`：Unicode scalar。

**返回与失败** 返回 Unicode Bidi_Mirroring_Glyph；没有映射返回原值。

**线程** 无共享可变状态；独立输出可并发，输入在调用期间不可修改。

**所有权** 标量无需释放。

### `exr_bidi_base_level`

**签名** `unsigned exr_bidi_base_level(const exr_bidi *bidi, size_t scalar_index);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `bidi`：分析对象；`scalar_index`：零基 scalar 索引。

**返回与失败** 返回所在段落 embedding base level；NULL/越界返回 UINT_MAX。

**线程** 只读查询可并发；不得并发 free。

**所有权** 返回标量。

### `exr_font_source`

**签名** `exr_status exr_font_source(const exr_font *font, size_t index, exr_font_input *source, exr_error *error);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `font`：字体集合；`index`：零基 face 索引；`source`：编码字节/大小/collection face_index 输出。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；无输出、无字体或越界 EXR_ARGUMENT；失败 source 清零。

**线程** 同一字体实例的查询、排版、塑形、渲染与释放串行；不同实例可独立使用。

**所有权** source.data 借用至 font_free，不可 free/改写。

### `exr_font_open`

**签名** `exr_status exr_font_open(const char *path, exr_font **out, exr_error *error);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `path`：UTF-8 字体文件路径（读取 collection 的 face 0）；`out`：新字体集合。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；缺参数 EXR_ARGUMENT、文件 EXR_IO、字体解析 EXR_FONT、输入超限 EXR_LIMIT、分配 EXR_MEMORY；失败 *out=NULL。

**线程** 无共享可变状态；独立输出可并发，输入在调用期间不可修改。

**所有权** 输出由 exr_font_free。

### `exr_font_create`

**签名** `exr_status exr_font_create(const exr_font_input *inputs, size_t count, exr_font **out, exr_error *error);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `inputs`：编码字体、长度、collection face_index 数组；`count`：1..32；`out`：新字体集合。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；需要 scalable 或 CBDT/CBLC Unicode face；参数 EXR_ARGUMENT，总字节>128 MiB EXR_LIMIT，字体解析 EXR_FONT，分配 EXR_MEMORY；失败 *out=NULL。

**线程** 无共享可变状态；独立输出可并发，输入在调用期间不可修改。

**所有权** 输入字节被复制；输出由 exr_font_free。

### `exr_font_create_glyphs`

**签名** `exr_status exr_font_create_glyphs(const exr_font_input *inputs, size_t count, exr_font **out, exr_error *error);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `inputs`：编码字体、长度、collection face_index 数组；`count`：1..32；`out`：新字体集合。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；也接受无 Unicode cmap 的 face，用于直接 glyph ID；参数 EXR_ARGUMENT，总字节>128 MiB EXR_LIMIT，字体解析 EXR_FONT，分配 EXR_MEMORY；失败 *out=NULL。

**线程** 无共享可变状态；独立输出可并发，输入在调用期间不可修改。

**所有权** 输入字节被复制；输出由 exr_font_free。

### `exr_font_axes`

**签名** `exr_status exr_font_axes(const exr_font *font,size_t font_index, exr_font_axis **out,size_t *count,exr_error *error);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `font`：字体集合；`font_index`：零基 face；`out`：轴快照数组；`count`：轴数量。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；静态字体返回 NULL/0；参数 EXR_ARGUMENT，超过 64 轴 EXR_LIMIT，字体读取/分配错误为 EXR_FONT/EXR_MEMORY。initial 是默认值，value 是实例当前值。

**线程** 同一字体实例的查询、排版、塑形、渲染与释放串行；不同实例可独立使用。

**所有权** 数组独立拥有，exr_free。

### `exr_font_create_variable`

**签名** `exr_status exr_font_create_variable(const exr_font_input *inputs,size_t count, const exr_font_coordinate *coordinates,size_t coordinate_count,exr_font **out,exr_error *error);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `inputs/count`：1..32 编码 face；`coordinates`：font_index/tag/value 稀疏坐标；`coordinate_count`：最多 2048；`out`：新字体集合。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；未知/重复/越界轴或参数 EXR_ARGUMENT，每 face >64 轴、输入超限 EXR_LIMIT，解析 EXR_FONT、分配 EXR_MEMORY；坐标取 16.16 精度。

**线程** 无共享可变状态；独立输出可并发，输入在调用期间不可修改。

**所有权** 复制 inputs 字节；coordinates 借用本次，输出 exr_font_free。

### `exr_font_count`

**签名** `size_t exr_font_count(const exr_font *font);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `font`：字体集合或 NULL。

**返回与失败** 返回 face 数量，NULL 返回 0。

**线程** 同一字体实例的查询、排版、塑形、渲染与释放串行；不同实例可独立使用。

**所有权** 返回标量。

### `exr_font_cache_stats_get`

**签名** `exr_status exr_font_cache_stats_get(const exr_font *font, exr_font_cache_stats *out, exr_error *error);`

**ABI** 实验；声明：[exr/text.h](../include/exr/text.h)。

**参数** `font`：字体实例；`out`：调用前须将 struct_size 设为 sizeof(exr_font_cache_stats)，接收字形位图/整形缓存的累计请求、命中、未命中、绕过与淘汰计数；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：写入快照，不清零计数、不加锁；font/out 为 NULL 或 struct_size 不符 EXR_ARGUMENT。

**线程** 与该字体的 shape 调用同一串行化规则，由宿主串行化；不与整形/渲染并发。

**所有权** 值类型输出由调用者保存，无需释放；不取得字体所有权。

### `exr_font_color_palettes`

**签名** `exr_status exr_font_color_palettes(const exr_font *font,size_t font_index, size_t *palettes,size_t *entries,exr_error *error);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `font`：字体集合；`font_index`：face；`palettes/entries`：CPAL palette 数与每表颜色数输出。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；无 CPAL 返回 0/0；参数 EXR_ARGUMENT，字体访问错误 EXR_FONT。

**线程** 同一字体实例的查询、排版、塑形、渲染与释放串行；不同实例可独立使用。

**所有权** 标量无需释放。

### `exr_font_color_layers`

**签名** `exr_status exr_font_color_layers(exr_font *font,size_t font_index,uint32_t glyph, size_t palette,uint32_t foreground,exr_font_color_layer **out,size_t *count, const exr_control *control,exr_error *error);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `font/font_index`：字体与 face；`glyph`：face 内 glyph ID；`palette`：CPAL 表号；`foreground`：straight RRGGBBAA；`out/count`：COLR v0 背到前的图层数组/数目。 `control`：可选的同步取消/进度回调，context 按本条所有权约定保活。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK，无层 NULL/0；参数/无效 palette EXR_ARGUMENT，字体 EXR_FONT，最多 256 层超限 EXR_LIMIT，分配 EXR_MEMORY，取消 EXR_CANCELLED。

**线程** 同一字体实例的查询、排版、塑形、渲染与释放串行；不同实例可独立使用。

**所有权** 图层数组由 exr_free；CPAL 0xffff 使用 foreground。

### `exr_font_color_info_get`

**签名** `exr_status exr_font_color_info_get(exr_font *font,size_t font_index,uint32_t glyph, exr_font_color_info *out,const exr_control *control,exr_error *error);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `font/font_index`：字体与 face；`glyph`：glyph ID；`out`：先设置 struct_size 的 color info。 `control`：可选的同步取消/进度回调，context 按本条所有权约定保活。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK，kind 按 COLR v1→v0→SVG 优先级，NONE 表示无色彩描述；参数 EXR_ARGUMENT，字体 EXR_FONT、取消 EXR_CANCELLED。

**线程** 同一字体实例的查询、排版、塑形、渲染与释放串行；不同实例可独立使用。

**所有权** 值输出，无位图分配；clip_box 为 1000-em y-up。

### `exr_font_glyph_image`

**签名** `exr_status exr_font_glyph_image(exr_font *font,size_t font_index,uint32_t glyph,float pixels, exr_glyph_image *out,const exr_control *control,exr_error *error);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `font/font_index`：字体与 face；`glyph`：glyph ID；`pixels`：请求像素字号；`out`：sbix/CBDT 图像及 left/top/scale。 `control`：可选的同步取消/进度回调，context 按本条所有权约定保活。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK，无图返回零记录；参数 EXR_ARGUMENT，字体/解码失败、大小/内存预算和取消返回对应非 OK。

**线程** 同一字体实例的查询、排版、塑形、渲染与释放串行；不同实例可独立使用。

**所有权** out.bitmap 由 exr_bitmap_free；不含文本透明度/合成样式。

### `exr_font_has_glyph`

**签名** `int exr_font_has_glyph(const exr_font *font, size_t font_index, uint32_t codepoint);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `font`：字体集合；`font_index`：face；`codepoint`：Unicode scalar。

**返回与失败** 返回 cmap 是否映射非零 glyph；无覆盖/非法输入为 0；不测试塑形序列支持。

**线程** 同一字体实例的查询、排版、塑形、渲染与释放串行；不同实例可独立使用。

**所有权** 无新分配。

### `exr_font_free`

**签名** `void exr_font_free(exr_font *font);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `font`：字体集合或 NULL。

**返回与失败** 无返回值。

**线程** 同一字体实例的查询、排版、塑形、渲染与释放串行；不同实例可独立使用。

**所有权** 释放调用者引用；最后引用释放 face/缓存/复制字节；借用 source 随实际销毁失效。

### `exr_font_glyph_outline`

**签名** `exr_status exr_font_glyph_outline(exr_font *font,size_t font_index,uint32_t glyph, exr_path_segment **out,size_t *count, const exr_control *control,exr_error *error);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `font/font_index`：字体与 face；`glyph`：face 内 glyph ID；`out/count`：路径段数组/数量。 `control`：可选的同步取消/进度回调，context 按本条所有权约定保活。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；仅位图 glyph 返回 NULL/0；参数 EXR_ARGUMENT，字体 EXR_FONT，路径预算 EXR_LIMIT，分配 EXR_MEMORY、取消 EXR_CANCELLED。

**线程** 同一字体实例的查询、排版、塑形、渲染与释放串行；不同实例可独立使用。

**所有权** 输出为独立未 hint 的 1000-em y-up 路径，exr_free；可比字体活得久。

### `exr_shape_defaults`

**签名** `exr_shape_options exr_shape_defaults(void);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** 无参数。

**返回与失败** 返回默认 shaping 选项。

**线程** 无共享可变状态；独立输出可并发，输入在调用期间不可修改。

**所有权** 值结构，无需释放。

### `exr_shape`

**签名** `exr_status exr_shape(exr_font *font, size_t font_index, const char *utf8, size_t size, const exr_shape_options *options, exr_shaped_glyph **out, size_t *out_count, exr_error *error);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `font/font_index`：单个 face；`utf8/size`：一段文本及字节数；`options`：4..256 像素字号、方向、script/language、最多 256 features、上下文/control（NULL 用默认）；`out/out_count`：glyph 数组/数量。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK，逻辑输出顺序；宿主切分方向/脚本/字体 run。非法参数 EXR_ARGUMENT，编码 EXR_ENCODING，字体 EXR_FONT，预算 EXR_LIMIT，分配 EXR_MEMORY，取消 EXR_CANCELLED。失败输出 NULL/0。

**线程** 同一字体实例的查询、排版、塑形、渲染与释放串行；不同实例可独立使用。

**所有权** 输入和 options/context 仅借用本次；返回 glyph 数组由 exr_free。

### `exr_shape_vertical`

**签名** `exr_status exr_shape_vertical(exr_font *font, size_t font_index, const char *utf8, size_t size, const exr_shape_options *options, exr_shaped_glyph **out, size_t *out_count, exr_error *error);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `font/font_index`：单个 face；`utf8/size`：一段文本及字节数；`options`：4..256 像素字号、方向、script/language、最多 256 features、上下文/control（NULL 用默认）；`out/out_count`：glyph 数组/数量。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK，逻辑输出顺序；启用 vert/vrt2 和垂直 metrics，向下 advance_y 为负；宿主切分方向/脚本/字体 run。非法参数 EXR_ARGUMENT，编码 EXR_ENCODING，字体 EXR_FONT，预算 EXR_LIMIT，分配 EXR_MEMORY，取消 EXR_CANCELLED。失败输出 NULL/0。

**线程** 同一字体实例的查询、排版、塑形、渲染与释放串行；不同实例可独立使用。

**所有权** 输入和 options/context 仅借用本次；返回 glyph 数组由 exr_free。

### `exr_glyph_matrix`

**签名** `exr_status exr_glyph_matrix(const exr_glyph *glyph, double matrix[6], exr_error *error);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `glyph`：排版 glyph（含位置、字号及横/竖排 flags）；`matrix`：6 个 double 输出。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；空输入或不合法几何 EXR_ARGUMENT。返回 1000-em y-up 到页面坐标的仿射矩阵。

**线程** 无共享可变状态；独立输出可并发，输入在调用期间不可修改。

**所有权** 宿主数组，无需释放。

### `exr_hyphenator_create`

**签名** `exr_status exr_hyphenator_create(const exr_hyphen_provider *provider, exr_hyphenator **out,exr_error *error);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `provider`：struct_size、hyphenate/release/context；`out`：新断词器。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；provider/大小/回调非法 EXR_ARGUMENT，分配 EXR_MEMORY；失败 *out=NULL。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** context 仅成功后转交；最终 free 调用 release；没有 release 时宿主保活。

### `exr_hyphenator_create_discretionary`

**签名** `exr_status exr_hyphenator_create_discretionary(const exr_hyphen_discretionary_provider *provider, exr_hyphenator **out,exr_error *error);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `provider`：struct_size、带 emit 的 hyphenate/release/context；`out`：新断词器。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；非法 provider EXR_ARGUMENT、分配 EXR_MEMORY。调用 query 时 emit 复制内容；最多 255 个点，每项文本≤128 scalar/512 字节；emit 错误被锁存。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 成功才转交 context；emit 参数仅回调期间借用，不能异步 emit；free 调用 release。

### `exr_hyphenator_create_patterns_ex`

**签名** `exr_status exr_hyphenator_create_patterns_ex(const exr_hyphen_pattern_input *inputs, size_t count,size_t byte_budget,exr_hyphen_case_policy case_policy,const exr_control *control, exr_hyphenator **out,exr_error *error);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `inputs`：语言键、TeX 风格 patterns、长度及 left/right_min（0=文件/默认 2）；`count`：1..64 语言；`byte_budget`：0=32 MiB，最大 128 MiB；`out`：新原生断词器；`case_policy`：LITERAL 或 WORD（保留一致的字形大小写）； `control`：可选的同步取消/进度回调，context 按本条所有权约定保活。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；参数 EXR_ARGUMENT、UTF-8 EXR_ENCODING、规则语法/原始 TeX 命令 EXR_FORMAT；每语言>8 MiB/总输入>32 MiB/内存预算 EXR_LIMIT，分配 EXR_MEMORY、取消 EXR_CANCELLED。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 输入和 control/context 仅本次借用；结果由 exr_hyphenator_free。

### `exr_hyphenator_create_patterns`

**签名** `exr_status exr_hyphenator_create_patterns(const exr_hyphen_pattern_input *inputs, size_t count,size_t byte_budget,const exr_control *control,exr_hyphenator **out,exr_error *error);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `inputs`：语言键、TeX 风格 patterns、长度及 left/right_min（0=文件/默认 2）；`count`：1..64 语言；`byte_budget`：0=32 MiB，最大 128 MiB；`out`：新原生断词器； `control`：可选的同步取消/进度回调，context 按本条所有权约定保活。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；参数 EXR_ARGUMENT、UTF-8 EXR_ENCODING、规则语法/原始 TeX 命令 EXR_FORMAT；每语言>8 MiB/总输入>32 MiB/内存预算 EXR_LIMIT，分配 EXR_MEMORY、取消 EXR_CANCELLED。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 输入和 control/context 仅本次借用；结果由 exr_hyphenator_free。

### `exr_hyphenator_create_builtin`

**签名** `exr_status exr_hyphenator_create_builtin(unsigned left_min,unsigned right_min,int auto_default, const exr_control *control,exr_hyphenator **out,exr_error *error);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `left_min/right_min`：两边最少 grapheme，0=3；`auto_default`：非零让未声明 hyphens 的英语块默认为 auto；`out`：内置英语断词器。 `control`：可选的同步取消/进度回调，context 按本条所有权约定保活。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；只处理 en/en-us；显式 manual/none 和其他语言不被覆盖。非法最小值 EXR_ARGUMENT，预算/分配/取消返回非 OK。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 输出 exr_hyphenator_free；control/context 仅本次借用。

### `exr_hyphenator_breaks`

**签名** `exr_status exr_hyphenator_breaks(exr_hyphenator *hyphenator,const char *language, const char *word,size_t size,unsigned char *breaks,const exr_control *control,exr_error *error);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `hyphenator`：断词器；`language`：语言键（大小写不敏感、逐级父标签）；`word/size`：原始 UTF-8，≤1024 字节/256 scalar；`breaks`：宿主 size+1 字节缓冲，1 表示在该 UTF-8 字节前可断。 `control`：可选的同步取消/进度回调，context 按本条所有权约定保活。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK，首尾/字素内部为 0；只给不改变拼写的机会。无规则可全部为 0。参数/编码/超限/取消或 provider 错误返回非 OK；有效大小请求失败会清空 breaks。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** word/control 借用本次；breaks 由宿主拥有。

### `exr_hyphenator_query`

**签名** `exr_status exr_hyphenator_query(exr_hyphenator *hyphenator,const char *language, const char *word,size_t size,const exr_control *control,exr_hyphenation **out,exr_error *error);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `hyphenator`：断词器；`language`：语言键（大小写不敏感、逐级父标签）；`word/size`：原始 UTF-8，≤1024 字节/256 scalar；`out`：完整 discretionary 断词结果。 `control`：可选的同步取消/进度回调，context 按本条所有权约定保活。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK，按原始字节点排序；失败 *out=NULL。非法参数 EXR_ARGUMENT，编码 EXR_ENCODING，结果载荷>256 KiB 或其他预算 EXR_LIMIT，分配/取消/provider 错误透传。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 独立不可变结果由 exr_hyphenation_free，允许比 word/provider/字典活得久。

### `exr_hyphenation_breaks`

**签名** `const exr_hyphen_break *exr_hyphenation_breaks(const exr_hyphenation *result,size_t *count);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `result`：查询结果或 NULL；`count`：可选条目数量输出。

**返回与失败** 返回断词项数组；NULL 结果返回 NULL/0。

**线程** 不可变结果可并发读取，不得并发 free。

**所有权** 项和 before/after 字符串均借用到 result free。

### `exr_hyphenation_memory_size`

**签名** `size_t exr_hyphenation_memory_size(const exr_hyphenation *result);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `result`：对象或 NULL。

**返回与失败** 返回对象内存载荷/容量计量，NULL 为 0；不包含宿主 provider 自有数据。

**线程** 不可变结果可并发读取，不得并发 free。

**所有权** 标量，无需释放。

### `exr_hyphenation_free`

**签名** `void exr_hyphenation_free(exr_hyphenation *result);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `result`：结果或 NULL。

**返回与失败** 无返回值。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 释放结果及其所有断词文本；借用视图失效。

### `exr_hyphenator_memory_size`

**签名** `size_t exr_hyphenator_memory_size(const exr_hyphenator *hyphenator);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `hyphenator`：对象或 NULL。

**返回与失败** 返回对象内存载荷/容量计量，NULL 为 0；不包含宿主 provider 自有数据。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 标量，无需释放。

### `exr_hyphenator_free`

**签名** `void exr_hyphenator_free(exr_hyphenator *hyphenator);`

**ABI** 稳定；声明：[exr/text.h](../include/exr/text.h)。

**参数** `hyphenator`：断词器或 NULL。

**返回与失败** 无返回值。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 释放引用；最后引用销毁字典并执行已接管 provider.release；布局可能仍保留引用。

### `exr_font_manager_create`

**签名** `exr_status exr_font_manager_create(const exr_font_manager_options *options, exr_font_manager **out, exr_error *error);`

**ABI** 稳定；声明：[exr/font_manager.h](../include/exr/font_manager.h)。

**参数** `options`：struct_size、目录/文件 locations、回退家族、平台目录 flags、可选缓存路径；`out`：新管理器。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；非法选项 EXR_ARGUMENT；必需路径缺失/不可读 EXR_IO；无可用 Unicode face EXR_FONT；超过 65536 face EXR_LIMIT；分配 EXR_MEMORY。损坏字体记 skip，缓存写失败记 summary，非整体失败。

**线程** 不同新 manager 可并发构建；同一 cache 路径写入由宿主串行化。

**所有权** 只在本次读 options/字符串，输出由 exr_font_manager_free。

### `exr_font_manager_open`

**签名** `exr_status exr_font_manager_open(const char *config_path, exr_font_manager **out, exr_error *error);`

**ABI** 稳定；声明：[exr/font_manager.h](../include/exr/font_manager.h)。

**参数** `config_path`：UTF-8 配置文件路径，相对配置项路径以此文件目录解析；`out`：管理器。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；version=1 必须为首项，未知键/坏行 EXR_FORMAT（含行号）；文件 EXR_IO；其他失败同 create，失败 *out=NULL。

**线程** 不同新 manager 可独立打开；同一 cache 路径写入串行。

**所有权** 输出 exr_font_manager_free；路径只借用本次。

### `exr_font_manager_free`

**签名** `void exr_font_manager_free(exr_font_manager *manager);`

**ABI** 稳定；声明：[exr/font_manager.h](../include/exr/font_manager.h)。

**参数** `manager`：管理器或 NULL。

**返回与失败** 无返回值。

**线程** 等待所有并发查询结束后释放。

**所有权** 释放索引和借用字符串；create_font 产生的独立 font 仍由调用者管理。

### `exr_font_manager_summary_get`

**签名** `exr_status exr_font_manager_summary_get(const exr_font_manager *manager, exr_font_manager_summary *out, exr_error *error);`

**ABI** 稳定；声明：[exr/font_manager.h](../include/exr/font_manager.h)。

**参数** `manager`：管理器；`out`：先设 struct_size 的 summary。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；NULL/错误 struct_size 为 EXR_ARGUMENT；含 face/skip/cache/耗时统计。

**线程** 不可变 manager 的查询可并发；free 必须等待全部查询结束。

**所有权** 值输出，无需 free。

### `exr_font_manager_skip`

**签名** `int exr_font_manager_skip(const exr_font_manager *manager, size_t index, exr_font_skip *out);`

**ABI** 稳定；声明：[exr/font_manager.h](../include/exr/font_manager.h)。

**参数** `manager`：管理器；`index`：零基 skip 序号；`out`：路径/reason/detail。

**返回与失败** 有记录返回 1；非法输入/越界返回 0。

**线程** 不可变 manager 的查询可并发；free 必须等待全部查询结束。

**所有权** out 的 path/detail 借用至 manager_free。

### `exr_font_manager_face_count`

**签名** `size_t exr_font_manager_face_count(const exr_font_manager *manager);`

**ABI** 稳定；声明：[exr/font_manager.h](../include/exr/font_manager.h)。

**参数** `manager`：管理器或 NULL。

**返回与失败** 返回已索引 face 数；NULL 为 0。

**线程** 不可变 manager 的查询可并发；free 必须等待全部查询结束。

**所有权** 返回标量。

### `exr_font_manager_face`

**签名** `exr_status exr_font_manager_face(const exr_font_manager *manager, size_t index, exr_font_face_info *out, exr_error *error);`

**ABI** 稳定；声明：[exr/font_manager.h](../include/exr/font_manager.h)。

**参数** `manager`：管理器；`index`：零基 face；`out`：先设 struct_size 的 face info。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；坏 index/struct_size/NULL 为 EXR_ARGUMENT；给家族、样式、路径、覆盖等信息。

**线程** 不可变 manager 的查询可并发；free 必须等待全部查询结束。

**所有权** 字符串借用至 manager_free，结构由宿主拥有。

### `exr_font_manager_face_covers`

**签名** `int exr_font_manager_face_covers(const exr_font_manager *manager, size_t index, uint32_t codepoint);`

**ABI** 稳定；声明：[exr/font_manager.h](../include/exr/font_manager.h)。

**参数** `manager`：管理器；`index`：face；`codepoint`：Unicode scalar。

**返回与失败** 有 cmap 覆盖返回 1；无覆盖/非法输入返回 0，不访问字体文件。

**线程** 不可变 manager 的查询可并发；free 必须等待全部查询结束。

**所有权** 无新分配。

### `exr_font_manager_has_family`

**签名** `int exr_font_manager_has_family(const exr_font_manager *manager, const char *family);`

**ABI** 稳定；声明：[exr/font_manager.h](../include/exr/font_manager.h)。

**参数** `manager`：管理器；`family`：UTF-8 家族或本地化家族名。

**返回与失败** 忽略大小写匹配时返回 1，否则/非法输入为 0。

**线程** 不可变 manager 的查询可并发；free 必须等待全部查询结束。

**所有权** 输入仅本次借用。

### `exr_font_manager_chain`

**签名** `exr_status exr_font_manager_chain(const exr_font_manager *manager, const char *family, unsigned style, exr_font_chain_link **out, size_t *count, exr_error *error);`

**ABI** 稳定；声明：[exr/font_manager.h](../include/exr/font_manager.h)。

**参数** `manager`：管理器；`family`：单家族、CSS 逗号列表、serif/sans-serif，未知家族从配置回退开始；`style`：EXR_FONT_STYLE_*；`out/count`：face/step 回退链与长度。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；空链 NULL/0，不把未知家族当错误；非法参数 EXR_ARGUMENT，分配 EXR_MEMORY；失败清空输出。

**线程** 不可变 manager 的查询可并发；free 必须等待全部查询结束。

**所有权** 输出链由 exr_free。

### `exr_font_manager_pick`

**签名** `exr_status exr_font_manager_pick(const exr_font_manager *manager, const char *family, unsigned style, uint32_t codepoint, exr_font_pick_result *out, exr_error *error);`

**ABI** 稳定；声明：[exr/font_manager.h](../include/exr/font_manager.h)。

**参数** `manager`：管理器；`family`：单家族、CSS 逗号列表、serif/sans-serif，未知家族从配置回退开始；`style`：EXR_FONT_STYLE_*；`codepoint`：Unicode scalar；`out`：先设 struct_size 的选择结果。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；无覆盖仍成功，face/chain_position=SIZE_MAX、step=NONE；非法 scalar/struct_size/NULL 为 EXR_ARGUMENT，链分配可 EXR_MEMORY。

**线程** 不可变 manager 的查询可并发；free 必须等待全部查询结束。

**所有权** 值输出，无需 free；只测试 cmap 覆盖。

### `exr_font_manager_create_font`

**签名** `exr_status exr_font_manager_create_font(const exr_font_manager *manager, const char *family, unsigned style, exr_font **out, size_t **faces, size_t *count, exr_error *error);`

**ABI** 稳定；声明：[exr/font_manager.h](../include/exr/font_manager.h)。

**参数** `manager`：管理器；`family`：单家族、CSS 逗号列表、serif/sans-serif，未知家族从配置回退开始；`style`：EXR_FONT_STYLE_*；`out`：新字体；`faces`：可选 face 索引映射输出；`count`：可选的链映射数量输出。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；读取索引时之后变化/消失或超过 256 MiB 总预算的 face 会省略；无 face 可加载 EXR_FONT，参数 EXR_ARGUMENT、分配 EXR_MEMORY。失败 NULL/0。

**线程** 不可变 manager 的查询可并发；free 必须等待全部查询结束。

**所有权** font 由 exr_font_free；faces 数组由 exr_free；字体独立于 manager。

### `exr_publication_warmup`

**签名** `exr_status exr_publication_warmup(exr_publication *publication, exr_font *font, const exr_layout_config *config, size_t pages, exr_error *error);`

**ABI** 实验；声明：[exr/render.h](../include/exr/render.h)。

**参数** `publication`：出版物；`font`：被预热的字体；`config`：布局配置，config.control 提供取消/进度；`pages`：预热页数，0 为空操作；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：为受限字体缓存预热前若干页，不改变阅读游标；页数不足（EOF）也返回成功；参数错误 EXR_ARGUMENT，取消 EXR_CANCELLED，其余错误透传；已完成的缓存条目在取消后保留。

**线程** 同一出版物与字体的操作由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 调用期间借用 publication、font 与 config；不取得所有权，不保留页面。

## 字典

只读查询 StarDict/dictd 字典并返回纯文本释义。

最小可编译示例：[examples/dictionary.c](examples/dictionary.c)。

<!-- example: docs/examples/dictionary.c -->
```c
/* SPDX-License-Identifier: MIT */
#include <exr/dictionary.h>
#include <stdio.h>

int main(int argc, char **argv) {
  exr_dictionary *dictionary = NULL;
  exr_dictionary_result *results = NULL;
  size_t count = 0;
  exr_error error = {0};
  exr_status status;
  if (argc != 3) { fprintf(stderr, "usage: dictionary book.ifo word\n"); return 2; }
  status = exr_dictionary_open(argv[1], &dictionary, &error);
  if (status == EXR_OK)
    status = exr_dictionary_query(&dictionary, 1, argv[2], 8, &results, &count, &error);
  if (status == EXR_OK) {
    for (size_t i = 0; i < count; ++i) printf("%s: %s\n", results[i].word, results[i].definition);
  } else fprintf(stderr, "%s\n", error.message);
  exr_dictionary_results_free(results, count);
  exr_dictionary_free(dictionary);
  return status == EXR_OK ? 0 : 1;
}
```

### `exr_dictionary_open`

**签名** `exr_status exr_dictionary_open(const char *path, exr_dictionary **out, exr_error *error);`

**ABI** 实验；声明：[exr/dictionary.h](../include/exr/dictionary.h)。

**参数** `path`：UTF-8 StarDict .ifo 或 dictd .index，同 basename 找 companion；`out`：新字典。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；参数 EXR_ARGUMENT，文件 EXR_IO，格式/索引损坏 EXR_FORMAT，编码 EXR_ENCODING，预算 EXR_LIMIT，分配 EXR_MEMORY。dict.dz 必须有 RA table，普通 gzip 不整体展开。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 索引常驻、释义文件按需读；输出由 exr_dictionary_free。

### `exr_dictionary_free`

**签名** `void exr_dictionary_free(exr_dictionary *dictionary);`

**ABI** 实验；声明：[exr/dictionary.h](../include/exr/dictionary.h)。

**参数** `dictionary`：字典或 NULL。

**返回与失败** 无返回值。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 关闭文件并释放索引，metadata 借用失效；已复制查询结果仍有效。

### `exr_dictionary_get_info`

**签名** `const exr_dictionary_info *exr_dictionary_get_info(const exr_dictionary *dictionary);`

**ABI** 实验；声明：[exr/dictionary.h](../include/exr/dictionary.h)。

**参数** `dictionary`：字典。

**返回与失败** 返回元数据；NULL 字典返回 NULL。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 借用至 dictionary_free。

### `exr_dictionary_get_io`

**签名** `exr_dictionary_io exr_dictionary_get_io(const exr_dictionary *dictionary);`

**ABI** 实验；声明：[exr/dictionary.h](../include/exr/dictionary.h)。

**参数** `dictionary`：字典或 NULL。

**返回与失败** 返回块解压、压缩读取字节与展开字节统计；NULL 为零；不计 index/header。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 值输出。

### `exr_dictionary_query`

**签名** `exr_status exr_dictionary_query(exr_dictionary *const *dictionaries, size_t count, const char *query, size_t limit, exr_dictionary_result **out, size_t *result_count, exr_error *error);`

**ABI** 实验；声明：[exr/dictionary.h](../include/exr/dictionary.h)。

**参数** `dictionaries`：按优先级排列的字典数组；`count`：最多 64；`query`：最多 4096 UTF-8 字节的词；`limit`：每字典 1..256；`out/result_count`：结果数组/数量。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK，空 query 无结果；每字典 exact→prefix→synonym→Unicode fold，首个非空阶段停止；非法参数/编码、磁盘或解压错误、预算/分配失败返回非 OK 并清空输出。

**线程** 本次涉及的每个字典均需独占，不并发 query/free。

**所有权** 输入本次借用，输出字符串均独立拥有（含字典名），用 exr_dictionary_results_free。

### `exr_dictionary_results_free`

**签名** `void exr_dictionary_results_free(exr_dictionary_result *results, size_t count);`

**ABI** 实验；声明：[exr/dictionary.h](../include/exr/dictionary.h)。

**参数** `results`：查询结果数组；`count`：条目数量（NULL 仅配 count=0）。

**返回与失败** 无返回值；count 要与数组匹配。

**线程** 与该结果的访问/释放串行。

**所有权** 释放每项字符串及数组。

## 渲染

将已排版页面栅格化为灰度或 RGBA 位图。

最小可编译示例：[examples/render.c](examples/render.c)。

<!-- example: docs/examples/render.c -->
```c
/* SPDX-License-Identifier: MIT */
#include <exr/formats.h>
#include <exr/render.h>
#include <stdio.h>

int main(int argc, char **argv) {
  const char text[] = "Hello from EXReader.";
  exr_document *document = NULL;
  exr_font *font = NULL;
  exr_layout *layout = NULL;
  exr_bitmap bitmap = {0};
  exr_error error = {0};
  exr_status status;
  if (argc != 3) { fprintf(stderr, "usage: render font.ttf output.png\n"); return 2; }
  status = exr_document_open_memory(EXR_TXT, text, sizeof(text) - 1, &document, &error);
  if (status == EXR_OK) status = exr_font_open(argv[1], &font, &error);
  if (status == EXR_OK) status = exr_layout_create(document, font, NULL, &layout, &error);
  if (status == EXR_OK)
    status = exr_render_page_background(layout, font, 0, 4, 0xF5EEDCFFu, NULL,
                                        &bitmap, &error);
  if (status == EXR_OK) {
    printf("RGBA %u x %u, stride=%u bytes\n", bitmap.width, bitmap.height, bitmap.stride);
    status = exr_bitmap_write_png(&bitmap, argv[2], &error);
  }
  if (status != EXR_OK) fprintf(stderr, "%s\n", error.message);
  exr_bitmap_free(&bitmap);
  exr_layout_free(layout);
  exr_font_free(font);
  exr_document_free(document);
  return status == EXR_OK ? 0 : 1;
}
```

### `exr_render_page`

**签名** `exr_status exr_render_page(const exr_layout *layout, exr_font *font, size_t page, exr_bitmap *bitmap, exr_error *error);`

**ABI** 稳定；声明：[exr/render.h](../include/exr/render.h)。

**参数** `layout`：已完成布局；`font`：匹配字体（可传 exr_layout_font(layout)，存在有效布局字体时可为 NULL）；`page`：布局内零基页号；`bitmap`：宿主先清零的输出结构。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK，输出 1 通道灰度，白色不透明底；参数/页号 EXR_ARGUMENT，像素>64 MiB/渲染工作预算 EXR_LIMIT，分配 EXR_MEMORY，字体栅格错误 EXR_FONT。进入绘制后的失败清空像素；旧入口的参数检查失败不保证清空输出，调用前置零。

**线程** 同一字体与同一布局的操作/生命周期串行；渲染会使用字体缓存，回调不可重入。

**所有权** 输入借用本次；SDK 分配像素，用 exr_bitmap_free；复用输出前先 free 旧位图。

### `exr_render_page_ex`

**签名** `exr_status exr_render_page_ex(const exr_layout *layout, exr_font *font, size_t page, unsigned channels, const exr_control *control, exr_bitmap *out, exr_error *error);`

**ABI** 稳定；声明：[exr/render.h](../include/exr/render.h)。

**参数** `layout`：已完成布局；`font`：匹配字体（可传 exr_layout_font(layout)，存在有效布局字体时可为 NULL）；`page`：布局内零基页号；`channels`：1 或 4；`out`：空位图结构。 `control`：可选的同步取消/进度回调，context 按本条所有权约定保活。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK，输出 由 channels 选择，白色不透明底；参数/页号 EXR_ARGUMENT，像素>64 MiB/渲染工作预算 EXR_LIMIT，分配 EXR_MEMORY，字体栅格错误 EXR_FONT，取消 EXR_CANCELLED。进入绘制后的失败清空像素；旧入口的参数检查失败不保证清空输出，调用前置零。

**线程** 同一字体与同一布局的操作/生命周期串行；渲染会使用字体缓存，回调不可重入。

**所有权** 输入借用本次；SDK 分配像素，用 exr_bitmap_free；复用输出前先 free 旧位图。

### `exr_render_page_background`

**签名** `exr_status exr_render_page_background(const exr_layout *layout, exr_font *font, size_t page, unsigned channels, uint32_t background_rgba, const exr_control *control, exr_bitmap *out, exr_error *error);`

**ABI** 稳定；声明：[exr/render.h](../include/exr/render.h)。

**参数** `layout`：已完成布局；`font`：匹配字体（可传 exr_layout_font(layout)，存在有效布局字体时可为 NULL）；`page`：布局内零基页号；`channels`：1 或 4；`out`：空位图结构。 `background_rgba`：straight 0xRRGGBBAA 初始背景。 `control`：可选的同步取消/进度回调，context 按本条所有权约定保活。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK，输出 由 channels 选择，指定底色；参数/页号 EXR_ARGUMENT，像素>64 MiB/渲染工作预算 EXR_LIMIT，分配 EXR_MEMORY，字体栅格错误 EXR_FONT，取消 EXR_CANCELLED。每次失败 out 为空。

**线程** 同一字体与同一布局的操作/生命周期串行；渲染会使用字体缓存，回调不可重入。

**所有权** 输入借用本次；SDK 分配像素，用 exr_bitmap_free；复用输出前先 free 旧位图。

### `exr_render_page_color`

**签名** `exr_status exr_render_page_color(const exr_layout *layout, exr_font *font, size_t page, exr_bitmap *bitmap, exr_error *error);`

**ABI** 稳定；声明：[exr/render.h](../include/exr/render.h)。

**参数** `layout`：已完成布局；`font`：匹配字体（可传 exr_layout_font(layout)，存在有效布局字体时可为 NULL）；`page`：布局内零基页号；`bitmap`：宿主先清零的输出结构。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK，输出 4 通道 straight RGBA，白色不透明底；参数/页号 EXR_ARGUMENT，像素>64 MiB/渲染工作预算 EXR_LIMIT，分配 EXR_MEMORY，字体栅格错误 EXR_FONT。进入绘制后的失败清空像素；旧入口的参数检查失败不保证清空输出，调用前置零。

**线程** 同一字体与同一布局的操作/生命周期串行；渲染会使用字体缓存，回调不可重入。

**所有权** 输入借用本次；SDK 分配像素，用 exr_bitmap_free；复用输出前先 free 旧位图。

## 全文索引

用可重建的 SQLite FTS5 派生数据库检索宿主提供的 UTF-8 文本。

最小可编译示例：[examples/textindex.c](examples/textindex.c)。

<!-- example: docs/examples/textindex.c -->
```c
/* SPDX-License-Identifier: MIT */
#include <exr/textindex.h>
#include <stdio.h>

int main(void) {
  const char text[] = "A searchable paragraph.";
  exr_text_index *index = NULL;
  exr_text_query *query = NULL;
  exr_text_hit hit = {0};
  exr_error error = {0};
  exr_status status;
  int found = 0;
  if (!exr_text_index_available()) { puts("Text index unavailable in this build"); return 0; }
  status = exr_text_index_open(":memory:", &index, &error);
  if (status == EXR_OK)
    status = exr_text_index_put(index, "book-1", "chapter-1", text, sizeof(text) - 1, NULL, &error);
  if (status == EXR_OK)
    status = exr_text_index_query(index, "book-1", "searchable", 10, NULL, &query, &error);
  if (status == EXR_OK) status = exr_text_query_next(query, &hit, &found, &error);
  if (status == EXR_OK && found) printf("%s [%zu, %zu)\n", hit.part, hit.start, hit.end);
  if (status != EXR_OK) fprintf(stderr, "%s\n", error.message);
  exr_text_query_free(query);
  exr_text_index_close(index);
  return status == EXR_OK ? 0 : 1;
}
```

### `exr_text_index_available`

**签名** `int exr_text_index_available(void);`

**ABI** 稳定；声明：[exr/textindex.h](../include/exr/textindex.h)。

**参数** 无参数。

**返回与失败** SQLite 编译含 ENABLE_FTS5 返回非零；否则 0。

**线程** 无共享可变状态；独立输出可并发，输入在调用期间不可修改。

**所有权** 无分配。

### `exr_text_index_open`

**签名** `exr_status exr_text_index_open(const char *path,exr_text_index **index,exr_error *error);`

**ABI** 稳定；声明：[exr/textindex.h](../include/exr/textindex.h)。

**参数** `path`：SQLite 派生索引路径，可为 :memory:；`index`：新句柄。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；缺参数 EXR_ARGUMENT、分配 EXR_MEMORY、数据库打开/schema/SQL EXR_DATABASE；当前实现 FTS5 关闭返回 EXR_FORMAT。失败 *index=NULL。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 新句柄由 exr_text_index_close；数据库文件由宿主管理。

### `exr_text_index_close`

**签名** `void exr_text_index_close(exr_text_index *index);`

**ABI** 稳定；声明：[exr/textindex.h](../include/exr/textindex.h)。

**参数** `index`：索引句柄或 NULL。

**返回与失败** 无返回值。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 释放宿主引用；活查询保留数据库，允许比 close 活得久。

### `exr_text_index_put`

**签名** `exr_status exr_text_index_put(exr_text_index *index,const char *source,const char *part,const void *text, size_t size,const exr_control *control,exr_error *error);`

**ABI** 稳定；声明：[exr/textindex.h](../include/exr/textindex.h)。

**参数** `index`：没有活动查询/写入的索引；`source`：宿主非空 ID（≤4096 UTF-8 字节）；`part`：分部 ID（允许空串，≤4096 字节）；`text/size`：原始 UTF-8 字节/长度，<64 MiB，可含 NUL。 `control`：可选的同步取消/进度回调，context 按本条所有权约定保活。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK，原子替换该 part，不做归一化或折叠；参数/活动查询 EXR_ARGUMENT，编码 EXR_ENCODING，长度 EXR_LIMIT，数据库 EXR_DATABASE，取消 EXR_CANCELLED；失败回滚。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 输入和 control/context 借用本次；索引存储文本副本。

### `exr_text_index_remove`

**签名** `exr_status exr_text_index_remove(exr_text_index *index,const char *source,const char *part, const exr_control *control,exr_error *error);`

**ABI** 稳定；声明：[exr/textindex.h](../include/exr/textindex.h)。

**参数** `index`：没有活动查询/写入的索引；`source`：宿主非空 ID（≤4096 UTF-8 字节）；`part`：要删的分部 ID，NULL 删除 source 的所有分部。 `control`：可选的同步取消/进度回调，context 按本条所有权约定保活。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK，事务删除；非法/活动查询 EXR_ARGUMENT，ID 超限 EXR_LIMIT，编码 EXR_ENCODING，数据库 EXR_DATABASE，取消 EXR_CANCELLED；失败回滚。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 字符串/control 仅本次借用。

### `exr_text_index_replace`

**签名** `exr_status exr_text_index_replace(exr_text_index *index,const char *source,exr_text_part_fn provider,void *context, const exr_control *control,exr_error *error);`

**ABI** 稳定；声明：[exr/textindex.h](../include/exr/textindex.h)。

**参数** `index`：没有活动查询/写入的索引；`source`：宿主非空 ID（≤4096 UTF-8 字节）；`provider`：逐 index 返回 part/found 的同步回调；`context`：宿主回调上下文。 `control`：可选的同步取消/进度回调，context 按本条所有权约定保活。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK，整体原子替换，空序列清除 source；非法 provider/重复 ID/活动查询 EXR_ARGUMENT，编码 EXR_ENCODING，超过 100000 parts/文本预算 EXR_LIMIT，数据库/取消/provider 错误透传；失败回滚。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** provider/context 借用本次；回调输出借用至下次回调或 replace 返回；写入时复制。

### `exr_text_index_query`

**签名** `exr_status exr_text_index_query(exr_text_index *index,const char *source,const void *query,size_t size, const exr_control *control,exr_text_query **out,exr_error *error);`

**ABI** 稳定；声明：[exr/textindex.h](../include/exr/textindex.h)。

**参数** `index`：无其他 live query 的索引；`source`：可选限定 ID，NULL=所有；`query/size`：1..4096 字节的字面 UTF-8 子串；`out`：新查询。 `control`：可选的同步取消/进度回调，context 按本条所有权约定保活。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK；非法/已有查询 EXR_ARGUMENT，长度 EXR_LIMIT，编码 EXR_ENCODING，分配 EXR_MEMORY，数据库 EXR_DATABASE、取消 EXR_CANCELLED；失败 *out=NULL。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 查询由 exr_text_query_free，保留 index；query/source 复制，control.context 借用到 query_free。

### `exr_text_query_next`

**签名** `exr_status exr_text_query_next(exr_text_query *query,exr_text_hit *hit,int *found,exr_error *error);`

**ABI** 稳定；声明：[exr/textindex.h](../include/exr/textindex.h)。

**参数** `query`：活动查询；`hit`：source/part/text 与 UTF-8 半开范围输出；`found`：有命中为 1、EOF 为 0。 `error`：可选诊断输出（code/message），以返回值判断成功。

**返回与失败** EXR_OK，按 row/insertion 顺序及字节区间，允许重叠；非法/失败查询 EXR_ARGUMENT，数据库/取消/分配/编码错误返回非 OK。错误清空输出且查询失效，必须 free 后重建。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** hit 字符串/text 借用至下次 next 或 free；需长期保存时宿主复制。

### `exr_text_query_free`

**签名** `void exr_text_query_free(exr_text_query *query);`

**ABI** 稳定；声明：[exr/textindex.h](../include/exr/textindex.h)。

**参数** `query`：查询或 NULL。

**返回与失败** 无返回值。

**线程** 同一对象的调用与释放须串行；不在回调中重入。

**所有权** 释放查询及其 index 引用，hit 视图失效；此后仍存活的 index 可以写入或发起新查询。


## 文档

构建、打开与释放结构化文档、分章节出版物或固定页面 provider，读取内容快照。

最小调用示例：[examples/document.c](examples/document.c)。

<!-- example: docs/examples/document.c -->
```c
/* SPDX-License-Identifier: MIT */
#include <exr/document.h>
#include <stdio.h>

int main(void) {
  const exr_node_input nodes[] = {
    {EXR_NODE_DOCUMENT, SIZE_MAX, NULL, NULL, NULL, 0},
    {EXR_NODE_CHAPTER, 0, NULL, NULL, NULL, 0},
    {EXR_NODE_PARAGRAPH, 1, NULL, NULL, NULL, 0},
    {EXR_NODE_TEXT, 2, NULL, "Hello reader.", NULL, 0}
  };
  const exr_chapter_input chapter = {"one", "one.txt", 1, 1};
  const exr_document_input input = {"Example", nodes, 4, &chapter, 1, NULL, 0};
  exr_document *document = NULL;
  exr_error error = {0};
  exr_status status = exr_document_create(&input, &document, &error);
  if (status == EXR_OK) {
    size_t size = 0;
    const char *text = exr_document_text(document, &size);
    fwrite(text, 1, size, stdout);
    putchar('\n');
  } else
    fprintf(stderr, "%s\n", error.message);
  exr_document_free(document);
  return status == EXR_OK ? 0 : 1;
}
```

### `exr_fixed_text_create`

**签名** `exr_status exr_fixed_text_create(const char *utf8,size_t size,const exr_text_region *regions,size_t count, const exr_control *control,exr_fixed_text **out,exr_error *error);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `utf8`：带显式 size 的 UTF-8 字节，可包含 NUL；`size`：输入 utf8 的精确字节数，正文内 NUL 也计入；`regions`：按 provider 顺序的字节区间与原生页坐标 quad 数组；`count`：输入 regions 个数；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`out`：接收独立拥有的固定页文字快照指针；用 exr_fixed_text_free 释放；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：复制 UTF-8 及四边形映射；无效 UTF-8/区间/坐标为 EXR_ENCODING/EXR_ARGUMENT，超限 EXR_LIMIT，分配失败 EXR_MEMORY，可取消。

**线程** 无共享可变状态；独立输入/输出可并发调用。

**所有权** 复制输入；*out 用 exr_fixed_text_free。

### `exr_fixed_text_free`

**签名** `void exr_fixed_text_free(exr_fixed_text *text);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `text`：固定页文字快照；由 exr_fixed_text_create 或固定页文字加载 API 返回

**返回与失败** 无返回值；NULL 可传。

**线程** 必须与对象及借用视图的全部使用串行化。

**所有权** 释放文字快照及其映射；借用文本和区域数组失效。

### `exr_fixed_text_string`

**签名** `const char *exr_fixed_text_string(const exr_fixed_text *text,size_t *size);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `text`：固定页文字快照；由 exr_fixed_text_create 或固定页文字加载 API 返回；`size`：可 NULL，接收文本的 UTF-8 字节数（不包含追加的终止 NUL，正文内的 NUL 计入）

**返回与失败** 返回文字字节；NULL 快照返回 NULL/size=0。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 借用至 exr_fixed_text_free；按 *size 读取，不依赖 NUL。

### `exr_fixed_text_regions`

**签名** `const exr_text_region *exr_fixed_text_regions(const exr_fixed_text *text,size_t *count);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `text`：固定页文字快照；由 exr_fixed_text_create 或固定页文字加载 API 返回；`count`：可 NULL，接收区域数量

**返回与失败** 返回区域数组；NULL 快照返回 NULL/count=0。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 借用至 exr_fixed_text_free；不释放。

### `exr_fixed_text_memory_size`

**签名** `size_t exr_fixed_text_memory_size(const exr_fixed_text *text);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `text`：固定页文字快照；由 exr_fixed_text_create 或固定页文字加载 API 返回

**返回与失败** 返回快照自身内存容量字节数；NULL 为 0。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 输入仅借用本次调用；值类型输出由调用者保存，无需释放。

### `exr_fixed_create`

**签名** `exr_status exr_fixed_create(const exr_fixed_input *input,exr_fixed_document **out,exr_error *error);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `input`：先零初始化并设置 struct_size；提供页面、draw、context，可选 text/metadata/annotations/draw_ex；`out`：接收独立拥有的固定页文档指针；用 exr_fixed_free 释放；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：创建固定页面 provider；缺少 draw/页数组、重复有效页 ID、无效几何或 struct_size 返回 EXR_ARGUMENT，分配失败 EXR_MEMORY。

**线程** 无共享可变状态；独立输入/输出可并发调用。

**所有权** 元数据复制；仅成功时接管 input.context，最后由 input.release 释放。*out 用 exr_fixed_free。

### `exr_fixed_free`

**签名** `void exr_fixed_free(exr_fixed_document *document);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `document`：固定页文档句柄

**返回与失败** 无返回值；NULL 可传。

**线程** 必须与对象及借用视图的全部使用串行化。

**所有权** 释放固定文档及 provider context；借用标题和页目录失效。

### `exr_fixed_load_metadata`

**签名** `exr_status exr_fixed_load_metadata(exr_fixed_document *document,const exr_control *control, exr_metadata_entry **entries,size_t *count,exr_error *error);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `document`：固定页文档句柄；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`entries`：接收拥有的键值数组；`count`：接收键值条目数；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：深复制 provider 元数据；缺少 metadata provider 为 EXR_FORMAT；参数错误 EXR_ARGUMENT，超过 4096 条或快照预算 EXR_LIMIT，分配失败 EXR_MEMORY；provider 读失败/取消状态透传。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** *entries 为独立结果，用 exr_metadata_free(*entries,*count)。

### `exr_fixed_title`

**签名** `const char *exr_fixed_title(const exr_fixed_document *document);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `document`：固定页文档句柄

**返回与失败** 返回标题借用字符串；NULL 返回空字符串。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 借用至 exr_fixed_free；不释放。

### `exr_fixed_pages`

**签名** `const exr_fixed_page *exr_fixed_pages(const exr_fixed_document *document,size_t *count);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `document`：固定页文档句柄；`count`：可 NULL，接收固定页数量

**返回与失败** 返回页面目录；NULL 文档返回 NULL/count=0。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 借用至 exr_fixed_free；不释放。

### `exr_fixed_memory_size`

**签名** `size_t exr_fixed_memory_size(const exr_fixed_document *document);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `document`：固定页文档句柄

**返回与失败** 返回 SDK 所有的目录/元数据容量；NULL 为 0；不含 provider 自身载荷。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 输入仅借用本次调用；值类型输出由调用者保存，无需释放。

### `exr_fixed_load_text`

**签名** `exr_status exr_fixed_load_text(exr_fixed_document *document,size_t page,const exr_control *control, exr_fixed_text **out,exr_error *error);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `document`：固定页文档句柄；`page`：零基页面索引；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`out`：接收独立拥有的固定页文字快照指针；用 exr_fixed_text_free 释放；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：得到独立文字快照；旧 load_text 在缺少 text provider 时返回 EXR_FORMAT，页号错误 EXR_ARGUMENT，读取/分配/取消错误透传。无字页仍成功返回空快照。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 独立 *out 用 exr_fixed_text_free；不借用 provider 输出。

### `exr_fixed_page_text`

**签名** `exr_status exr_fixed_page_text(exr_fixed_document *document,size_t page,const exr_control *control, exr_fixed_text **out,exr_error *error);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `document`：固定页文档句柄；`page`：零基页面索引；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`out`：接收独立拥有的固定页文字快照指针；用 exr_fixed_text_free 释放；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：得到独立文字快照；无 text provider 为 EXR_UNSUPPORTED，页号错误 EXR_ARGUMENT，读取/分配/取消错误透传。空文本页返回 EXR_NO_TEXT_LAYER 且 *out=NULL；不做 OCR。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 独立 *out 用 exr_fixed_text_free；不借用 provider 输出。

### `exr_fixed_draw`

**签名** `exr_status exr_fixed_draw(exr_fixed_document *document,size_t page,const double matrix[6], const exr_draw_sink *sink,const exr_control *control,exr_error *error);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `document`：固定页文档句柄；`page`：零基页面索引；`matrix`：6 元仿射变换；NULL 使用单位矩阵；`sink`：宿主绘图回调集合；可省略不需要的回调；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：同步发出页面绘图命令；无效页/矩阵/输出端为 EXR_ARGUMENT；provider 读取、内存、取消错误透传，失败时 sink 可能已有部分命令。不隐式设置 clip 或绘图状态。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 借用 sink/context；回调收到的绘图数据仅在回调期间有效。

### `exr_fixed_draw_ex`

**签名** `exr_status exr_fixed_draw_ex(exr_fixed_document *document,size_t page,const double matrix[6], const exr_draw_sink_ex *sink,const exr_control *control,exr_error *error);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `document`：固定页文档句柄；`page`：零基页面索引；`matrix`：6 元仿射变换；NULL 使用单位矩阵；`sink`：宿主绘图回调集合；可省略不需要的回调；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：同步发出页面绘图命令；无效页/矩阵/输出端为 EXR_ARGUMENT；provider 读取、内存、取消错误透传，失败时 sink 可能已有部分命令。优先 draw_ex，否则退回旧 provider 和 sink.base。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 借用 sink/context；回调收到的绘图数据仅在回调期间有效。

### `exr_fixed_render`

**签名** `exr_status exr_fixed_render(exr_fixed_document *document,size_t page,double scale, const exr_fixed_render_options *options,exr_bitmap *out,exr_error *error);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `document`：固定页文档句柄；`page`：零基页面索引；`scale`：原生页到输出像素的正比例；`options`：可 NULL（白色 RGBA）；channels 为 1 或 4，含 mask_budget/control；`out`：接收拥有像素的位图结构（先零初始化）；用 exr_bitmap_free 释放像素；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：创建自然大小 viewport、裁剪并渲染指定页；参数/scale 无效为 EXR_ARGUMENT，内存/掩码或像素预算失败为 EXR_MEMORY/EXR_LIMIT；provider/取消错误透传，失败不返回部分位图。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** out 应零初始化；成功的 pixels 用 exr_bitmap_free(out)。

### `exr_document_create`

**签名** `exr_status exr_document_create(const exr_document_input *input, exr_document **out, exr_error *error);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `input`：构造树、章节、资源和标题；节点 0 为 DOCUMENT，后续 parent 必须指向此前祖先；`out`：接收独立拥有的结构化文档指针；用 exr_document_free 释放；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：复制输入并返回结构化文档；错误树索引/章节/路径为 EXR_ARGUMENT 或 EXR_FORMAT，非法 UTF-8 为 EXR_ENCODING，分配/大小上限为 EXR_MEMORY/EXR_LIMIT；失败 *out=NULL。

**线程** 无共享可变状态；独立输入/输出可并发调用。

**所有权** 复制所有字符串、属性和资源字节；*out 用 exr_document_free。

### `exr_document_free`

**签名** `void exr_document_free(exr_document *doc);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `doc`：要读取的结构化文档快照

**返回与失败** 无返回值；NULL 可传。

**线程** 必须与对象及借用视图的全部使用串行化。

**所有权** 释放文档和其持有的资源/源引用；全部借用视图失效。

### `exr_document_memory_size`

**签名** `size_t exr_document_memory_size(const exr_document *doc);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `doc`：要读取的结构化文档快照

**返回与失败** 返回文档拥有的分配容量字节数；NULL 为 0。共享源和分配器开销不计入。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 输入仅借用本次调用；值类型输出由调用者保存，无需释放。

### `exr_document_text`

**签名** `const char *exr_document_text(const exr_document *doc, size_t *size);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `doc`：要读取的结构化文档快照；`size`：可 NULL，接收文本的 UTF-8 字节数（不包含追加的终止 NUL，正文内的 NUL 计入）

**返回与失败** 返回规范化 UTF-8 正文；NULL 文档返回 NULL，存在的长度输出置 0。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 返回文档借用视图；有效至 exr_document_free，不得释放或改写。

### `exr_document_title`

**签名** `const char *exr_document_title(const exr_document *doc);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `doc`：要读取的结构化文档快照

**返回与失败** 返回标题；NULL 文档返回空字符串。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 返回文档借用视图；有效至 exr_document_free，不得释放或改写。

### `exr_document_blocks`

**签名** `const exr_block *exr_document_blocks(const exr_document *doc, size_t *count);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `doc`：要读取的结构化文档快照；`count`：可 NULL，接收正文块数量

**返回与失败** 返回正文块数组；NULL 文档返回 NULL，存在的长度输出置 0。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 返回文档借用视图；有效至 exr_document_free，不得释放或改写。

### `exr_document_nodes`

**签名** `const exr_node *exr_document_nodes(const exr_document *doc, size_t *count);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `doc`：要读取的结构化文档快照；`count`：可 NULL，接收DOM 节点数量

**返回与失败** 返回DOM 节点数组；NULL 文档返回 NULL，存在的长度输出置 0。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 返回文档借用视图；有效至 exr_document_free，不得释放或改写。

### `exr_document_chapters`

**签名** `const exr_chapter *exr_document_chapters(const exr_document *doc, size_t *count);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `doc`：要读取的结构化文档快照；`count`：可 NULL，接收章节数量

**返回与失败** 返回章节目录数组；NULL 文档返回 NULL，存在的长度输出置 0。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 返回文档借用视图；有效至 exr_document_free，不得释放或改写。

### `exr_document_resources`

**签名** `const exr_resource *exr_document_resources(const exr_document *doc, size_t *count);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `doc`：要读取的结构化文档快照；`count`：可 NULL，接收资源元数据数量

**返回与失败** 返回资源元数据数组；NULL 文档返回 NULL，存在的长度输出置 0。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 返回文档借用视图；有效至 exr_document_free，不得释放或改写。

### `exr_node_attribute`

**签名** `const char *exr_node_attribute(const exr_node *node, const char *name);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `node`：从 exr_document_nodes 获得的节点；`name`：属性名称；命名空间属性使用 URI|local

**返回与失败** 返回匹配属性值；节点/名称缺失或无该属性返回 NULL。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 返回节点所属文档的借用字符串，有效至 document_free。

### `exr_document_format`

**签名** `exr_format exr_document_format(const exr_document *doc);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `doc`：要读取的结构化文档快照

**返回与失败** 返回解析时的 exr_format；自建文档或 NULL 返回 EXR_CUSTOM。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 输入仅借用本次调用；值类型输出由调用者保存，无需释放。

### `exr_document_media`

**签名** `const exr_media_item *exr_document_media(const exr_document *doc, size_t *count);`

**ABI** 实验；声明：[exr/document.h](../include/exr/document.h)。

**参数** `doc`：结构化文档快照；`count`：输出媒体项数量

**返回与失败** 返回媒体项数组；无媒体的部分返回 NULL 且 count 为 0。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 返回值借用自文档，直到 exr_document_free 前有效，不得释放。

### `exr_publication_media_overlay`

**签名** `exr_status exr_publication_media_overlay(exr_publication *publication,size_t part,exr_media_overlay **overlay,exr_error *error);`

**ABI** 实验；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：出版物；`part`：部分序号；`overlay`：输出叠加层；`error`：可选错误详情

**返回与失败** 成功返回 EXR_OK；部分未声明 media-overlay 时 *overlay 为 NULL。SMIL 缺失或格式错误时失败并给出可读信息，不影响读取该部分本身。仅限 EPUB。

**线程** 同一 publication 不得并发调用；不同对象可并行。

**所有权** 成功时输出的 overlay 归调用者，须用 exr_media_overlay_free 释放。

### `exr_media_overlay_free`

**签名** `void exr_media_overlay_free(exr_media_overlay *overlay);`

**ABI** 实验；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `overlay`：要释放的叠加层，可为 NULL

**返回与失败** 无返回值，不会失败。

**线程** 同一对象不得并发释放；释放期间不得使用该对象。

**所有权** 释放后 overlay 及其内部字符串与片段数组全部失效。

### `exr_publication_create`

**签名** `exr_status exr_publication_create(const exr_publication_input *input, exr_publication **out, exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `input`：标题、part 目录、load/context/release 与可选扁平 navigation；`out`：接收出版物句柄；用 exr_publication_free 释放；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：复制 part/navigation 元数据，创建惰性 provider；目录/回调/导航父索引错误 EXR_ARGUMENT，分配失败 EXR_MEMORY。

**线程** 无共享可变状态；独立输入/输出可并发调用。

**所有权** 成功才接管 context；release 在最后 publication/session/pager 引用释放后调用一次。load 成功交出的 document 所有权归引擎；*out 用 publication_free。

### `exr_publication_open`

**签名** `exr_status exr_publication_open(const char *path, exr_publication **out, exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `path`：输入出版物的 UTF-8 文件路径；`out`：接收出版物句柄；用 exr_publication_free 释放；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：打开EPUB、MOBI/KF8 或 FB2（含 FB2 ZIP）出版物，正文按 load 才解析。无效参数 EXR_ARGUMENT，不支持格式/损坏包 EXR_FORMAT，I/O/编码/内存/大小错误透传，失败 *out=NULL。等价对应 _ex(passphrase=NULL)，遇到 LCP 可能要求口令。

**线程** 无共享可变状态；独立输入/输出可并发调用。

**所有权** 调用期间借用输入路径，打开的文件/资源由出版物管理。*out 用 exr_publication_free。

### `exr_publication_open_source`

**签名** `exr_status exr_publication_open_source(const exr_source *source, exr_publication **out, exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `source`：具有 size/read_at/context/release 的不可变、可寻址原始字节源；所有权见下；`out`：接收出版物句柄；用 exr_publication_free 释放；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：打开寻址源中的 EPUB 包。无效参数 EXR_ARGUMENT，不支持格式/损坏包 EXR_FORMAT，I/O/编码/内存/大小错误透传，失败 *out=NULL。等价对应 _ex(passphrase=NULL)，遇到 LCP 可能要求口令。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 成功接管 source.context，最后保留引用关闭时调用 release；失败不接管。*out 用 exr_publication_free。

### `exr_publication_open_memory`

**签名** `exr_status exr_publication_open_memory(exr_format format, const void *data, size_t size, exr_publication **out, exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `format`：EXR_EPUB、EXR_MOBI 或 EXR_FB2（KF8 用 EXR_MOBI）；`data`：输入格式的原始字节缓冲区，长度由 size 指定；`size`：输入 data 原始格式字节数；`out`：接收出版物句柄；用 exr_publication_free 释放；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：打开EPUB、MOBI/KF8 或 FB2（含 FB2 ZIP）出版物，正文按 load 才解析。无效参数 EXR_ARGUMENT，不支持格式/损坏包 EXR_FORMAT，I/O/编码/内存/大小错误透传，失败 *out=NULL。等价对应 _ex(passphrase=NULL)，遇到 LCP 可能要求口令。

**线程** 无共享可变状态；独立输入/输出可并发调用。

**所有权** 调用期间借用输入字节并保留独立副本。*out 用 exr_publication_free。

### `exr_publication_open_ex`

**签名** `exr_status exr_publication_open_ex(const char *path, const char *passphrase, exr_publication **out, exr_error *error);`

**ABI** 实验；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `path`：输入出版物的 UTF-8 文件路径；`passphrase`：LCP UTF-8 口令，NULL 为未提供，空串也是已提供；仅本次借用；`out`：接收出版物句柄；用 exr_publication_free 释放；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：打开EPUB、MOBI/KF8 或 FB2（含 FB2 ZIP）出版物，正文按 load 才解析。无效参数 EXR_ARGUMENT，不支持格式/损坏包 EXR_FORMAT，I/O/编码/内存/大小错误透传，失败 *out=NULL。LCP 失败区分 PASSPHRASE_REQUIRED/INCORRECT、LICENSE_EXPIRED/INVALID、DRM_UNSUPPORTED；仅 Basic Profile 解码，宿主验证许可签名/证书。

**线程** 无共享可变状态；独立输入/输出可并发调用。

**所有权** 调用期间借用输入路径，打开的文件/资源由出版物管理。*out 用 exr_publication_free。

### `exr_publication_open_source_ex`

**签名** `exr_status exr_publication_open_source_ex(const exr_source *source, const char *passphrase, exr_publication **out, exr_error *error);`

**ABI** 实验；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `source`：具有 size/read_at/context/release 的不可变、可寻址原始字节源；所有权见下；`passphrase`：LCP UTF-8 口令，NULL 为未提供，空串也是已提供；仅本次借用；`out`：接收出版物句柄；用 exr_publication_free 释放；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：打开寻址源中的 EPUB 包。无效参数 EXR_ARGUMENT，不支持格式/损坏包 EXR_FORMAT，I/O/编码/内存/大小错误透传，失败 *out=NULL。LCP 失败区分 PASSPHRASE_REQUIRED/INCORRECT、LICENSE_EXPIRED/INVALID、DRM_UNSUPPORTED；仅 Basic Profile 解码，宿主验证许可签名/证书。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 成功接管 source.context，最后保留引用关闭时调用 release；失败不接管。*out 用 exr_publication_free。

### `exr_publication_open_memory_ex`

**签名** `exr_status exr_publication_open_memory_ex(exr_format format, const void *data, size_t size, const char *passphrase, exr_publication **out, exr_error *error);`

**ABI** 实验；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `format`：EXR_EPUB、EXR_MOBI 或 EXR_FB2（KF8 用 EXR_MOBI）；`data`：输入格式的原始字节缓冲区，长度由 size 指定；`size`：输入 data 原始格式字节数；`passphrase`：LCP UTF-8 口令，NULL 为未提供，空串也是已提供；仅本次借用；`out`：接收出版物句柄；用 exr_publication_free 释放；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：打开EPUB、MOBI/KF8 或 FB2（含 FB2 ZIP）出版物，正文按 load 才解析。无效参数 EXR_ARGUMENT，不支持格式/损坏包 EXR_FORMAT，I/O/编码/内存/大小错误透传，失败 *out=NULL。LCP 失败区分 PASSPHRASE_REQUIRED/INCORRECT、LICENSE_EXPIRED/INVALID、DRM_UNSUPPORTED；仅 Basic Profile 解码，宿主验证许可签名/证书。

**线程** 无共享可变状态；独立输入/输出可并发调用。

**所有权** 调用期间借用输入字节并保留独立副本。*out 用 exr_publication_free。

### `exr_publication_free`

**签名** `void exr_publication_free(exr_publication *publication);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物

**返回与失败** 无返回值；NULL 可传。

**线程** 必须与对象及借用视图的全部使用串行化。

**所有权** 释放调用者的引用；最后引用释放目录/缓存/context；已经独立返回的文档和会话保留所需源引用。

### `exr_publication_title`

**签名** `const char *exr_publication_title(const exr_publication *publication);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物

**返回与失败** 返回标题；NULL 返回空字符串。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 借用至 publication_free；不释放。

### `exr_publication_parts`

**签名** `const exr_part *exr_publication_parts(const exr_publication *publication, size_t *count);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物；`count`：可 NULL，接收part 目录条目数

**返回与失败** 返回 part 目录；NULL 返回 NULL/count=0。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 借用至 publication_free；不释放；part 是目录零基索引，非书页号。

### `exr_publication_load`

**签名** `exr_status exr_publication_load(exr_publication *publication, size_t part, exr_document **out, exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物；`part`：零基 publication 目录索引；`out`：接收独立拥有的结构化文档指针；用 exr_document_free 释放；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：仅载入指定 part 为独立文档；无效 part EXR_ARGUMENT；provider 的 I/O/格式/DRM/内存错误透传。MOBI/KF8 正文损坏可延迟至此失败。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** *out 用 exr_document_free；文档内偏移/节点/章节索引仅对此 part 快照有效。

### `exr_document_ssml`

**签名** `exr_status exr_document_ssml(exr_publication *publication,exr_ssml_position from_position, size_t max_chars,exr_ssml_chunk *out,unsigned flags,const exr_control *control,exr_error *error);`

**ABI** 实验；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物；`from_position`：首次 node=0，part/offset 为章节及规范化 UTF-8 位置；继续调用原样传上次 next；`max_chars`：发音文本 Unicode 标量预算；0=800，上限 65536，有提示时至少 8；`out`：接收 SSML 字符串、句子映射和 next 游标（先零初始化）；用 exr_ssml_chunk_free 释放；`flags`：EXR_SSML_HINT_NOTES/IMAGES/TABLES 的位组合；0 跳过这些子树；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：生成至多一个线性 part 的 SSML 及句子映射；EOF 返回空但有效 speak；未知 flags、无效游标或字符预算返回 EXR_ARGUMENT，分配/解析/取消错误透传。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** out 先清零；每次使用后 exr_ssml_chunk_free，再复用输出。

### `exr_ssml_chunk_free`

**签名** `void exr_ssml_chunk_free(exr_ssml_chunk *chunk);`

**ABI** 实验；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `chunk`：由 document_ssml 返回的拥有 SSML 和句子数组的结构

**返回与失败** 无返回值；NULL 可传。

**线程** 必须与对象及借用视图的全部使用串行化。

**所有权** 释放 chunk.ssml 和 sentences 并清零；chunk 结构本身由调用者保存。

### `exr_document_page_progression`

**签名** `exr_direction exr_document_page_progression(const exr_document *doc);`

**ABI** 实验（[公开头文件](../include/exr/document.h)）。

**参数** doc 为文档，可为 NULL。

**返回与失败** 返回物理翻页方向；显式 OPF ltr/rtl 优先，其次按主语言判断，NULL 默认 LTR；与段落 bidi 分开。

**线程** 同一模型、出版物或分页器的访问由宿主串行化；不与修改、重排或释放并发。

**所有权** 按值返回。

### `exr_edit_begin`

**签名** `exr_edit_tx *exr_edit_begin(exr_edit_doc *doc);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** doc 为编辑模型。

**返回与失败** 返回事务句柄；无效模型、已有事务或分配失败返回 NULL；不支持嵌套事务。 当前 main 仅提供该模型头文件快照；默认构建没有这些符号的实现，须通过 EXR_EDIT_MODEL_SOURCE 接入匹配的 X1 源码后链接。

**线程** 同一模型、出版物或分页器的访问由宿主串行化；不与修改、重排或释放并发。

**所有权** 句柄由 commit/rollback 消费；doc_free 也会回滚活动事务。

### `exr_edit_block_at`

**签名** `const exr_edit_block *exr_edit_block_at(const exr_edit_doc *doc,size_t index);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** doc 为编辑模型，index 为零基块序号。

**返回与失败** 返回只读块视图；调用前确认 index 小于 block_count。 当前 main 仅提供该模型头文件快照；默认构建没有这些符号的实现，须通过 EXR_EDIT_MODEL_SOURCE 接入匹配的 X1 源码后链接。

**线程** 同一模型、出版物或分页器的访问由宿主串行化；不与修改、重排或释放并发。

**所有权** 借用指针，块被修改/删除即失效，不能 free。

### `exr_edit_block_count`

**签名** `size_t exr_edit_block_count(const exr_edit_doc *doc);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** doc 为编辑模型。

**返回与失败** 返回块数量。 当前 main 仅提供该模型头文件快照；默认构建没有这些符号的实现，须通过 EXR_EDIT_MODEL_SOURCE 接入匹配的 X1 源码后链接。

**线程** 同一模型、出版物或分页器的访问由宿主串行化；不与修改、重排或释放并发。

**所有权** 按值返回。

### `exr_edit_commit`

**签名** `exr_status exr_edit_commit(exr_edit_tx *tx);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** tx 为活动事务。

**返回与失败** 返回 exr_status；命令失败会锁存错误，commit 回滚整个事务并返回该错误。空提交保留 redo；成功新编辑在提交时清空 redo。 当前 main 仅提供该模型头文件快照；默认构建没有这些符号的实现，须通过 EXR_EDIT_MODEL_SOURCE 接入匹配的 X1 源码后链接。

**线程** 同一模型、出版物或分页器的访问由宿主串行化；不与修改、重排或释放并发。

**所有权** 消费 tx；无论成功或失败都不可再使用。

### `exr_edit_defaults`

**签名** `exr_edit_options exr_edit_defaults(void);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** 无参数。

**返回与失败** 返回默认 undo_depth=100；显式设置为 0 禁用历史。 当前 main 仅提供该模型头文件快照；默认构建没有这些符号的实现，须通过 EXR_EDIT_MODEL_SOURCE 接入匹配的 X1 源码后链接。

**线程** 同一模型、出版物或分页器的访问由宿主串行化；不与修改、重排或释放并发。

**所有权** 按值返回 options。

### `exr_edit_delete_block`

**签名** `exr_status exr_edit_delete_block(exr_edit_doc *doc,exr_edit_id block_id);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** doc 为模型，block_id 为要删除的块。

**返回与失败** 返回 exr_status；当前表格只保留，不支持删除/编辑。 当前 main 仅提供该模型头文件快照；默认构建没有这些符号的实现，须通过 EXR_EDIT_MODEL_SOURCE 接入匹配的 X1 源码后链接。

**线程** 同一模型、出版物或分页器的访问由宿主串行化；不与修改、重排或释放并发。

**所有权** 成功删除使该块借用视图失效；ID 永不复用。

### `exr_edit_delete_image`

**签名** `exr_status exr_edit_delete_image(exr_edit_doc *doc,exr_edit_id image_id);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** `doc` 为模型；`image_id` 可为新插入的图片块 ID、导入的绘图 run ID（含表格单元格内 run），或要移除绘图并保留文字的段落 ID。

**返回与失败** 成功返回 EXR_OK；新图片块被删除，导入段落/run 仅移除图片绘图，保留文字及其他内容。无效 ID、未找到图片或缺少所需原包部件为 EXR_ARGUMENT；XML 解析、预算或分配错误会传播。写出时清理图片关系及任何 OPC 部件都不再引用的媒体。参与事务及 undo/redo，事务内失败遵循锁存/回滚规则。

**线程** 需要调用方串行；同一模型的读取、写出、修改、事务及释放不得并发；调用期间不得修改输入缓冲区。

**所有权** doc 为借用输入，不被消费；模型管理删除及历史保留的内存。成功后被删除或修改块的原借用视图失效，调用方不单独释放图片或 run。

### `exr_edit_delete_table`

**签名** `exr_status exr_edit_delete_table(exr_edit_doc *doc,exr_edit_id table_id);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** `doc` 为模型；`table_id` 为要整体删除的表格块 ID，亦可指定仅保留原 XML 的表格块。

**返回与失败** 成功返回 EXR_OK，删除整张表格。空模型、无效 ID 或非表格块为 EXR_ARGUMENT；历史记录分配失败可返回 EXR_MEMORY。参与事务及 undo/redo，事务内失败遵循锁存/回滚规则。

**线程** 需要调用方串行；同一模型的读取、写出、修改、事务及释放不得并发；调用期间不得修改输入缓冲区。

**所有权** doc 为借用输入，不被消费；表格、行和单元格内存由模型及历史记录管理。删除后该表格的借用视图失效，ID 永不复用，无返回分配。

### `exr_edit_doc_create`

**签名** `exr_status exr_edit_doc_create(const exr_edit_section *sections,size_t section_count, const exr_edit_block *blocks,size_t block_count,const exr_edit_part *parts,size_t part_count, const exr_edit_options *options,exr_edit_doc **out);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** sections/blocks/parts 与各自数量提供种子数据；options 可为 NULL；out 为非空输出。

**返回与失败** 返回 exr_status。非零 ID 必须全局唯一，零 ID 自动分配且不复用；section_id=0 取首节，NULL/0 sections 创建 Letter 节。需提供保留内容所需全部 OPC part/opaque XML；本接口不解析或写 DOCX。 当前 main 仅提供该模型头文件快照；默认构建没有这些符号的实现，须通过 EXR_EDIT_MODEL_SOURCE 接入匹配的 X1 源码后链接。

**线程** 同一模型、出版物或分页器的访问由宿主串行化；不与修改、重排或释放并发。

**所有权** 深拷贝所有输入；失败清空 out；成功模型用 exr_edit_doc_free 释放。

### `exr_edit_doc_free`

**签名** `void exr_edit_doc_free(exr_edit_doc *doc);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** doc 为编辑模型。

**返回与失败** 释放模型并回滚尚未结束的事务；无返回值。 当前 main 仅提供该模型头文件快照；默认构建没有这些符号的实现，须通过 EXR_EDIT_MODEL_SOURCE 接入匹配的 X1 源码后链接。

**线程** 同一模型、出版物或分页器的访问由宿主串行化；不与修改、重排或释放并发。

**所有权** 消费模型；所有借用视图及活动事务句柄失效，先释放关联 pager。

### `exr_edit_docx_open`

**签名** `exr_status exr_edit_docx_open(const char *path,const exr_edit_options *options, exr_edit_doc **out,exr_error *error);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** `path` 为 UTF-8 DOCX 文件路径；`options` 可为 NULL，使用默认历史深度；`out` 为非空模型输出；`error` 为可选诊断输出。

**返回与失败** 成功返回 EXR_OK，读取 OPC 包并保留未知 XML 与包部件；XML 仅支持 UTF-8/US-ASCII。空参数为 EXR_ARGUMENT，读取失败为 EXR_IO；还可能返回 EXR_FORMAT、EXR_ENCODING、EXR_UNSUPPORTED、EXR_LIMIT 或 EXR_MEMORY。失败时 *out=NULL。

**线程** 需要调用方串行；同一模型的读取、写出、修改、事务及释放不得并发；调用期间不得修改输入缓冲区。

**所有权** 路径和选项仅在调用期间借用，文件数据由 SDK 读取并复制到独立模型；成功后调用方拥有 *out，使用 exr_edit_doc_free 释放。

### `exr_edit_docx_read`

**签名** `exr_status exr_edit_docx_read(const void *data,size_t size, const exr_edit_options *options,exr_edit_doc **out,exr_error *error);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** `data`/`size` 为非空 DOCX 包字节及字节数；`options` 可为 NULL，使用默认历史深度；`out` 为非空模型输出；`error` 为可选诊断输出。

**返回与失败** 成功返回 EXR_OK，解析 DOCX 并保留未知 XML 与包部件；XML 仅支持 UTF-8/US-ASCII。空输入或输出为 EXR_ARGUMENT，输入或解压预算超限为 EXR_LIMIT；格式、编码、不支持内容及分配失败分别可能返回 EXR_FORMAT、EXR_ENCODING、EXR_UNSUPPORTED、EXR_MEMORY。失败时 *out=NULL。

**线程** 需要调用方串行；同一模型的读取、写出、修改、事务及释放不得并发；调用期间不得修改输入缓冲区。

**所有权** 输入缓冲区和选项在调用期间借用；模型深拷贝所需数据，返回后调用方可释放输入。成功后 *out 的所有权转给调用方，用 exr_edit_doc_free 释放。

### `exr_edit_docx_write`

**签名** `exr_status exr_edit_docx_write(const exr_edit_doc *doc,void **data, size_t *size,exr_error *error);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** `doc` 为编辑模型；`data`、`size` 为非空输出指针，接收 DOCX 包内存及字节数；`error` 为可选诊断输出。

**返回与失败** 成功返回 EXR_OK，将模型写入内存中的 DOCX 包，保留未知 XML/部件并清理已删除图片的关系及无引用媒体；编辑会使原数字签名失效。空参数或非法模型为 EXR_ARGUMENT，缺少原始 XML 模板所需主部件可返回 EXR_UNSUPPORTED；还可能返回 EXR_FORMAT、EXR_ENCODING、EXR_LIMIT 或 EXR_MEMORY。失败清空可用的输出：*data=NULL、*size=0。

**线程** 需要调用方串行；同一模型的读取、写出、修改、事务及释放不得并发；调用期间不得修改输入缓冲区。

**所有权** doc 为借用输入，不被消费。成功缓冲区由 SDK 分配，所有权转给调用方，使用 exr_free(*data) 释放；输出不是模型内部的借用视图。

### `exr_edit_find_block`

**签名** `const exr_edit_block *exr_edit_find_block(const exr_edit_doc *doc,exr_edit_id id);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** doc 为编辑模型，id 为稳定非零块 ID。

**返回与失败** 按 ID 查询只读块；调用者检查返回指针是否为空。 当前 main 仅提供该模型头文件快照；默认构建没有这些符号的实现，须通过 EXR_EDIT_MODEL_SOURCE 接入匹配的 X1 源码后链接。

**线程** 同一模型、出版物或分页器的访问由宿主串行化；不与修改、重排或释放并发。

**所有权** 借用指针，块被修改/删除即失效。

### `exr_edit_image_position`

**签名** `exr_status exr_edit_image_position(const exr_edit_doc *doc,const exr_edit_block *block, exr_edit_id *paragraph_id,size_t *run_index,size_t *byte_offset);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** `doc` 为模型；`block` 必须为该模型当前借用的 IMAGE 块；三个非空输出给出段落 ID、run 下标及 drawing/pict 在该 run 原始 XML 内的字节偏移。表格单元格内段落也可定位；独立插入块的三个输出均为 0。

**返回与失败** 成功 EXR_OK；空参数、其他模型/非图片块或失效锚点为 EXR_ARGUMENT，清零所有非空输出；不修改模型或事务状态。`block->image` 提供原始载荷 `data/size`、格式 `format`、精确 `width_emu/height_emu`（635 EMU = 1 twip）。格式 PNG/JPEG/GIF/BMP 分别对应 image/png、image/jpeg、image/gif、image/bmp。导入块紧随所属段落或表格，是原 run 中 drawing/pict 的结构化视图，写回保留原锚点、关系和载荷；同段多图由位置区分。删除图片/段落/run 后相应视图随同一次 undo 记录移除。

**线程** 同一模型的读取、修改、事务、写出及释放均由调用方串行。

**所有权** block、image 及载荷均为只读借用视图，随对应块变更或移出模型失效；三个输出为调用方标量。GIF 只显示第 0 帧；不能解码的 EMF/WMF、损坏或超解码预算的图片继续保留为 opaque run 及原 OPC 媒体。CMYK JPEG 沿用现有解码器的 RGB 显示，原 JPEG 字节不变。无有效显示尺寸时按解码像素以 96 DPI 推导；复杂多载荷 drawing、嵌套未知 XML 保留 opaque。

### `exr_edit_insert_image`

**签名** `exr_status exr_edit_insert_image(exr_edit_doc *doc,exr_edit_id after_id, const void *bytes,size_t size,double width_pt,double height_pt,exr_edit_id *new_id);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** `doc` 为模型；`after_id` 为锚点块 ID，0 表示开头；`bytes`/`size` 为 PNG/JPEG/BMP/GIF 原始字节及非零长度；`width_pt`、`height_pt` 为有限正数，单位为点；`new_id` 为非空新块 ID 输出。

**返回与失败** 成功返回 EXR_OK，插入图片块，保存原始载荷而不重新编码。非法锚点、输出或尺寸为 EXR_ARGUMENT，超输入预算为 EXR_LIMIT，无法识别的格式为 EXR_FORMAT；图片解码错误会传播，分配可返回 EXR_MEMORY。失败清零 *new_id；参与事务及 undo/redo，事务内失败遵循锁存/回滚规则。

**线程** 需要调用方串行；同一模型的读取、写出、修改、事务及释放不得并发；调用期间不得修改输入缓冲区。

**所有权** GIF 显示只取第 0 帧，原始动画载荷仍完整保留。图片字节在调用期间借用并深拷贝，返回后可释放输入；图片及新块由模型分配和释放。new_id 为宿主标量输出，无指针所有权转移。

### `exr_edit_insert_paragraph`

**签名** `exr_status exr_edit_insert_paragraph(exr_edit_doc *doc,exr_edit_id after_id, const exr_edit_run *runs,size_t count,const exr_edit_para_props *props,exr_edit_id *new_id);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** doc 为模型，after_id=0 表示开头；runs/count 为文字片段，props 可为 NULL，new_id 接收新块 ID。

**返回与失败** 返回 exr_status；新 run 获得新 ID，节继承锚点（开头用首节），空 props 为继承属性集；失败清空输出 ID。 当前 main 仅提供该模型头文件快照；默认构建没有这些符号的实现，须通过 EXR_EDIT_MODEL_SOURCE 接入匹配的 X1 源码后链接。

**线程** 同一模型、出版物或分页器的访问由宿主串行化；不与修改、重排或释放并发。

**所有权** 输入可别名借用视图；新内容由模型管理。

### `exr_edit_memory_bytes`

**签名** `size_t exr_edit_memory_bytes(const exr_edit_doc *doc);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** doc 为编辑模型。

**返回与失败** 返回保留分配字节，含历史与容量，不含分配器额外开销。 当前 main 仅提供该模型头文件快照；默认构建没有这些符号的实现，须通过 EXR_EDIT_MODEL_SOURCE 接入匹配的 X1 源码后链接。

**线程** 同一模型、出版物或分页器的访问由宿主串行化；不与修改、重排或释放并发。

**所有权** 按值返回。

### `exr_edit_parts`

**签名** `const exr_edit_part *exr_edit_parts(const exr_edit_doc *doc,size_t *count);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** doc 为编辑模型，count 接收 OPC part 数量。

**返回与失败** 返回只读 part 数组；name 为 OPC 路径，data/size 为内容。 当前 main 仅提供该模型头文件快照；默认构建没有这些符号的实现，须通过 EXR_EDIT_MODEL_SOURCE 接入匹配的 X1 源码后链接。

**线程** 同一模型、出版物或分页器的访问由宿主串行化；不与修改、重排或释放并发。

**所有权** 借用至 doc_free，不能 free。

### `exr_edit_redo`

**签名** `exr_status exr_edit_redo(exr_edit_doc *doc);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** doc 为编辑模型。

**返回与失败** 返回 exr_status；事务打开或重做栈为空时返回 EXR_ARGUMENT。成功的新编辑会清空 redo。 当前 main 仅提供该模型头文件快照；默认构建没有这些符号的实现，须通过 EXR_EDIT_MODEL_SOURCE 接入匹配的 X1 源码后链接。

**线程** 同一模型、出版物或分页器的访问由宿主串行化；不与修改、重排或释放并发。

**所有权** 模型继续持有内容；更新后重新取得借用块/run 视图。

### `exr_edit_rollback`

**签名** `exr_status exr_edit_rollback(exr_edit_tx *tx);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** tx 为活动事务。

**返回与失败** 返回 exr_status 并回滚事务内修改；失败命令后需回滚才能继续。 当前 main 仅提供该模型头文件快照；默认构建没有这些符号的实现，须通过 EXR_EDIT_MODEL_SOURCE 接入匹配的 X1 源码后链接。

**线程** 同一模型、出版物或分页器的访问由宿主串行化；不与修改、重排或释放并发。

**所有权** 消费 tx；之后不可再使用。

### `exr_edit_sections`

**签名** `const exr_edit_section *exr_edit_sections(const exr_edit_doc *doc,size_t *count);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** doc 为编辑模型，count 接收节数量。

**返回与失败** 返回只读节数组，包含纸张、边距、页眉页脚引用。 当前 main 仅提供该模型头文件快照；默认构建没有这些符号的实现，须通过 EXR_EDIT_MODEL_SOURCE 接入匹配的 X1 源码后链接。

**线程** 同一模型、出版物或分页器的访问由宿主串行化；不与修改、重排或释放并发。

**所有权** 借用至 doc_free，不能 free。

### `exr_edit_set_paragraph_props`

**签名** `exr_status exr_edit_set_paragraph_props(exr_edit_doc *doc,exr_edit_id block_id, const exr_edit_para_props *props);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** doc、block_id 指定段落，props 指定属性及 present 位。

**返回与失败** 返回 exr_status；present 区分未设置/继承和显式值。 当前 main 仅提供该模型头文件快照；默认构建没有这些符号的实现，须通过 EXR_EDIT_MODEL_SOURCE 接入匹配的 X1 源码后链接。

**线程** 同一模型、出版物或分页器的访问由宿主串行化；不与修改、重排或释放并发。

**所有权** 属性由模型持有；旧块视图在修改后失效。

### `exr_edit_set_run_props`

**签名** `exr_status exr_edit_set_run_props(exr_edit_doc *doc,exr_edit_id block_id, size_t run_index,const exr_edit_run_props *props);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** doc、block_id、run_index 指定 run，props 提供属性及 present 位。

**返回与失败** 返回 exr_status；显式 false bold/italic 可以覆盖继承。 当前 main 仅提供该模型头文件快照；默认构建没有这些符号的实现，须通过 EXR_EDIT_MODEL_SOURCE 接入匹配的 X1 源码后链接。

**线程** 同一模型、出版物或分页器的访问由宿主串行化；不与修改、重排或释放并发。

**所有权** 属性由模型持有；修改后重新取得视图。

### `exr_edit_set_run_text`

**签名** `exr_status exr_edit_set_run_text(exr_edit_doc *doc,exr_edit_id block_id, size_t run_index,const char *text,size_t text_size);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** `doc` 为模型，`block_id` 为段落块 ID；`run_index` 从 0 起；`text`/`text_size` 为有效 UTF-8/XML 文本及字节数，允许 NULL/0 清空，长度不是字符数。

**返回与失败** 成功返回 EXR_OK，替换一个 TEXT run 的文字，保留 ID、直接属性、原始 XML 模板及相邻 opaque run。无效 ID、索引、长度或文本为 EXR_ARGUMENT，非段落块或 opaque run 为 EXR_UNSUPPORTED，分配失败为 EXR_MEMORY。参与事务及 undo/redo；事务内失败会锁存状态，后续命令失败直至回滚，提交失败事务会整体回滚。

**线程** 需要调用方串行；同一模型的读取、写出、修改、事务及释放不得并发；调用期间不得修改输入缓冲区。

**所有权** 输入文字可别名模型的借用文本，调用期间借用并复制；新文字由模型分配和释放。成功修改使该块原有借用视图失效，无返回内存需要调用方释放。

### `exr_edit_split_paragraph`

**签名** `exr_status exr_edit_split_paragraph(exr_edit_doc *doc,exr_edit_id block_id, size_t run_index,size_t byte_offset);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** doc、block_id 指定顶层段落或 exr_edit_table_cell_paragraph 返回的可编辑单元格段落，run_index/byte_offset 为 run 内 UTF-8 标量边界；(run_count,0) 表示末尾。

**返回与失败** 成功返回 EXR_OK；左块保留 ID，右块新 ID，完整移动的 run 保留 ID，拆开的右片段新 ID；顶层 opaque run 仅允许 offset=0。单元格拆出的两段均留在原单元格。非法模型、ID、位置或 UTF-8 非标量边界为 EXR_ARGUMENT，非段落或受保护单元格为 EXR_UNSUPPORTED；分配失败为 EXR_MEMORY，ID/容量耗尽为 EXR_LIMIT。参与当前事务及 undo/redo，事务内失败遵循锁存/回滚规则。

**线程** 同一模型、出版物或分页器的访问由宿主串行化；不与修改、重排或释放并发。

**所有权** 段落属性复制；修改后重新取得借用视图。

### `exr_edit_table_cell_paragraph`

**签名** `const exr_edit_block *exr_edit_table_cell_paragraph( const exr_edit_doc *doc,exr_edit_id table,size_t row,size_t column,size_t index);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** `doc` 为模型，`table` 为表格块 ID；`row`、`column` 为从 0 起的物理行/单元格索引；`index` 为单元格内按文档顺序排列的可编辑段落索引，从 0 起。

**返回与失败** 返回只读段落块，ID 可传给 exr_edit_split_paragraph，两段留在原单元格。空单元格返回已有占位段落（若存在）。非法模型、ID、越界索引、无表格模型或受保护单元格返回 NULL。普通多段落单元格可查询；含合并、嵌套表、底纹或 opaque 内容的单元格不可编辑。只读查询可在事务内外调用，不产生历史，也不锁存事务失败；拆段参与当前事务及 undo/redo。

**线程** 同一模型的读取、写出、修改、事务及释放由调用方串行化，不得并发。

**所有权** 返回模型持有的借用视图，不可释放；所属表格修改、undo/redo、回滚或模型释放后须重新获取。查询不分配占位段落。

### `exr_edit_table_delete_row`

**签名** `exr_status exr_edit_table_delete_row(exr_edit_doc *doc,exr_edit_id table_id,size_t row_index);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** `doc` 为模型，`table_id` 为已建模的表格块 ID；`row_index` 为从 0 起的物理行索引。

**返回与失败** 成功返回 EXR_OK。非法模型、ID、越界行索引或删除唯一一行为 EXR_ARGUMENT；无表格模型或删除会破坏垂直合并链为 EXR_UNSUPPORTED，分配失败为 EXR_MEMORY。参与事务及 undo/redo，事务内失败遵循锁存/回滚规则。

**线程** 需要调用方串行；同一模型的读取、写出、修改、事务及释放不得并发；调用期间不得修改输入缓冲区。

**所有权** doc 为借用输入；模型及历史记录管理删除行的内存。成功修改使该表格原有借用视图失效，无返回分配，也不需调用方释放行或单元格。

### `exr_edit_table_insert_row`

**签名** `exr_status exr_edit_table_insert_row(exr_edit_doc *doc,exr_edit_id table_id,size_t after_row_index);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** `doc` 为模型，`table_id` 为已建模的表格块 ID；`after_row_index` 为从 0 起的物理行索引，在其后插入；SIZE_MAX 表示在首行前插入。

**返回与失败** 成功返回 EXR_OK，按表格列数创建空单元格并从锚点行（前插时为首行）的可用段落继承格式。非法模型、ID 或行索引为 EXR_ARGUMENT；无表格模型或插入位置会拆开垂直合并链为 EXR_UNSUPPORTED；容量溢出为 EXR_LIMIT，分配失败为 EXR_MEMORY。参与事务及 undo/redo，事务内失败遵循锁存/回滚规则。

**线程** 需要调用方串行；同一模型的读取、写出、修改、事务及释放不得并发；调用期间不得修改输入缓冲区。

**所有权** doc 为借用输入；新行、单元格及段落由模型分配和释放。成功修改使该表格原有借用视图失效，无返回分配。

### `exr_edit_table_set_borders`

**签名** `exr_status exr_edit_table_set_borders(exr_edit_doc *doc,exr_edit_id table_id,exr_edit_borders spec);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** `doc` 为模型，`table_id` 为已建模的表格块 ID；`spec` 为 EXR_EDIT_BORDER_NONE、EXR_EDIT_BORDER_SINGLE 或 EXR_EDIT_BORDER_DOUBLE。

**返回与失败** 成功返回 EXR_OK，更新表格边框供 DOCX 写出。非法模型、ID 或枚举为 EXR_ARGUMENT，无表格模型为 EXR_UNSUPPORTED，分配失败为 EXR_MEMORY。参与事务及 undo/redo，事务内失败遵循锁存/回滚规则。

**线程** 需要调用方串行；同一模型的读取、写出、修改、事务及释放不得并发；调用期间不得修改输入缓冲区。

**所有权** doc 为借用输入，边框枚举按值复制；新表格快照及历史由模型分配和释放。成功修改使该表格原有借用视图失效，无返回分配。

### `exr_edit_table_set_cell_text`

**签名** `exr_status exr_edit_table_set_cell_text(exr_edit_doc *doc,exr_edit_id table_id, size_t row,size_t col,const exr_edit_run *runs,size_t count);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** `doc` 为模型，`table_id` 为已建模的表格块 ID；`row`、`col` 为从 0 起的物理行/单元格索引；`runs`/`count` 为 TEXT run 数组及数量，NULL/0 清空单元格文本。

**返回与失败** 成功返回 EXR_OK，以单个段落替换目标单元格内容，沿用原首块的段落属性，输入 run 取得新 ID。非法索引、数组或非 TEXT run 为 EXR_ARGUMENT；无表格模型或受保护单元格（合并、嵌套表格、底纹、opaque 内容）为 EXR_UNSUPPORTED，分配失败为 EXR_MEMORY；其他行/单元格仍可编辑。参与事务及 undo/redo，事务内失败遵循锁存/回滚规则。

**线程** 需要调用方串行；同一模型的读取、写出、修改、事务及释放不得并发；调用期间不得修改输入缓冲区。

**所有权** 输入 run、文字及属性在调用期间借用，文字和属性复制到模型；输入 run 的 ID 与 opaque XML 不沿用。模型分配和释放新内容；成功修改使该表格原有借用视图失效，无返回分配。

### `exr_edit_table_set_column_width`

**签名** `exr_status exr_edit_table_set_column_width( exr_edit_doc *doc,exr_edit_tx *tx,exr_edit_id table,size_t column,int32_t width_twips);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** `doc` 为模型，`tx` 必须是该模型当前活动事务，`table` 为已建模表格块 ID；`column` 为从 0 起的网格列索引；`width_twips` 为正宽度，单位 twip（1/20 点）。

**返回与失败** 成功返回 EXR_OK，同时设置内存列宽、w:gridCol[column] 和整表宽度 w:tblW（各列之和），参与事务及 undo/redo。非法模型、ID、事务、越界列或非正宽度为 EXR_ARGUMENT；无表格模型为 EXR_UNSUPPORTED；总宽超过 INT32_MAX 为 EXR_LIMIT，分配失败为 EXR_MEMORY。失败不修改模型，事务内失败遵循锁存/提交回滚规则。缺少网格宽度的模型按原整表宽度除以列数初始化其他列；exr_edit_table_set_width 保持仅设置整表宽度的原语义。

**线程** 同一模型的读取、写出、修改、事务及释放由调用方串行化，不得并发。

**所有权** doc、tx 为借用输入，本函数不消费事务；宽度按值复制，列宽数组及历史快照由模型分配和释放。成功修改使原表格及单元格借用视图失效，无返回分配。

### `exr_edit_table_set_width`

**签名** `exr_status exr_edit_table_set_width(exr_edit_doc *doc,exr_edit_id table_id,int32_t twips);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** `doc` 为模型，`table_id` 为已建模的表格块 ID；`twips` 为正表格宽度，单位为 twip（1/20 点）。

**返回与失败** 成功返回 EXR_OK，更新表格宽度供 DOCX 写出。非法模型、ID 或非正宽度为 EXR_ARGUMENT，无表格模型为 EXR_UNSUPPORTED，分配失败为 EXR_MEMORY。参与事务及 undo/redo，事务内失败遵循锁存/回滚规则。

**线程** 需要调用方串行；同一模型的读取、写出、修改、事务及释放不得并发；调用期间不得修改输入缓冲区。

**所有权** doc 为借用输入，宽度按值复制；新表格快照及历史由模型分配和释放。成功修改使该表格原有借用视图失效，无返回分配。

### `exr_edit_undo`

**签名** `exr_status exr_edit_undo(exr_edit_doc *doc);`

**ABI** 实验（[公开头文件](../include/exr/edit.h)）。

**参数** doc 为编辑模型。

**返回与失败** 返回 exr_status；事务打开或撤销栈为空时返回 EXR_ARGUMENT。事务外每个成功命令占一个撤销项。 当前 main 仅提供该模型头文件快照；默认构建没有这些符号的实现，须通过 EXR_EDIT_MODEL_SOURCE 接入匹配的 X1 源码后链接。

**线程** 同一模型、出版物或分页器的访问由宿主串行化；不与修改、重排或释放并发。

**所有权** 模型继续持有内容；更新后重新取得借用块/run 视图。


## 分页

将文字与样式排为完整布局、逐页页器或按章节缓存会话，并查询页面几何。

最小调用示例：[examples/pagination.c](examples/pagination.c)。

<!-- example: docs/examples/pagination.c -->
```c
/* SPDX-License-Identifier: MIT */
#include <exr/formats.h>
#include <exr/layout.h>
#include <stdio.h>

int main(int argc, char **argv) {
  const char text[] = "A page is laid out only when the host requests it.";
  exr_document *document = NULL;
  exr_font *font = NULL;
  exr_pager *pager = NULL;
  const exr_layout *page = NULL;
  exr_error error = {0};
  exr_status status;
  if (argc != 2) { fprintf(stderr, "usage: pagination font.ttf\n"); return 2; }
  status = exr_document_open_memory(EXR_TXT, text, sizeof(text) - 1, &document, &error);
  if (status == EXR_OK) status = exr_font_open(argv[1], &font, &error);
  if (status == EXR_OK) status = exr_pager_create(document, font, NULL, &pager, &error);
  if (status == EXR_OK) status = exr_pager_set_cache(pager, 3, 8u * 1024u * 1024u, &error);
  if (status == EXR_OK) status = exr_pager_get(pager, 0, &page, &error);
  if (status == EXR_OK)
    printf("cached=%zu, scanned=%zu UTF-8 bytes\n",
           exr_pager_cached_count(pager), exr_pager_position(pager));
  else
    fprintf(stderr, "%s\n", error.message);
  /* page is borrowed from pager; do not call layout_free(page). */
  exr_pager_free(pager);
  exr_font_free(font);
  exr_document_free(document);
  return status == EXR_OK ? 0 : 1;
}
```

### `exr_layout_blocks`

**签名** `const exr_layout_block *exr_layout_blocks(const exr_layout *layout, size_t *count);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `layout`：待查询布局；`count`：可 NULL，接收语义块数量

**返回与失败** 返回正文/标题/装饰语义块数组；NULL 布局返回 NULL/count=0。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 借用至布局释放；若布局归 pager/session，则受其更短缓存有效期限制，不释放。

### `exr_layout_page_structure`

**签名** `exr_page_structure exr_layout_page_structure(const exr_layout *layout, size_t page);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `layout`：待查询布局；`page`：零基页面索引

**返回与失败** 按值返回 starts_chapter/contains_title/chapter_index/title_block_count；非法页返回全零。chapter_index 为一基，未知为 0。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 输入仅借用本次调用；值类型输出由调用者保存，无需释放。

### `exr_layout_font`

**签名** `exr_font *exr_layout_font(const exr_layout *layout);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `layout`：待查询布局

**返回与失败** 返回布局实际使用的字体集合（含书内字体）；NULL 布局返回 NULL。glyph.font_index 在此集合中索引。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 借用至布局释放；不可调用 font_free。

### `exr_layout_defaults`

**签名** `exr_layout_options exr_layout_defaults(void);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** 无。

**返回与失败** 按值返回默认页面尺寸、边距、字号、行高、段距；无失败通道。

**线程** 无共享可变状态；独立输入/输出可并发调用。

**所有权** 输入仅借用本次调用；值类型输出由调用者保存，无需释放。

### `exr_layout_config_defaults`

**签名** `exr_layout_config exr_layout_config_defaults(void);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** 无。

**返回与失败** 按值返回默认页面参数、文档 CSS/嵌入字体选项、方向和空回调；无失败通道。

**线程** 无共享可变状态；独立输入/输出可并发调用。

**所有权** 输入仅借用本次调用；值类型输出由调用者保存，无需释放。

### `exr_reader_style_defaults`

**签名** `exr_reader_style exr_reader_style_defaults(void);`

**ABI** 实验；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** 无。

**返回与失败** 按值返回默认阅读器字号、行距、四边距与字距；无失败通道。

**线程** 无共享可变状态；独立输入/输出可并发调用。

**所有权** 输入仅借用本次调用；值类型输出由调用者保存，无需释放。

### `exr_reader_style_config`

**签名** `exr_status exr_reader_style_config(const exr_reader_style *style, float width,float height,float scale,exr_layout_config *config,char css[1024],exr_error *error);`

**ABI** 实验；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `style`：阅读偏好；上下左右边距为 CSS 像素，段距/字距为 em；`width`：目标 viewport 宽；`height`：目标 viewport 高；`scale`：设备像素与 CSS 像素的正比例；`config`：输入/输出配置：先用 exr_layout_config_defaults 初始化；保留原配置其他选项，替换 page/user_css；`css`：调用者提供至少 1024 字节输出缓冲区；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：将阅读偏好转换为内容矩形和 CSS；非有限值、非正缩放/内容尺寸、越界样式为 EXR_ARGUMENT。绘制与命中原点需加 (left,top)*scale。

**线程** 无共享可变状态；独立输入/输出可并发调用。

**所有权** config.user_css 借用调用者 css[1024]；css 必须活到 config 被消费/复制。

### `exr_layout_create_hyphenated`

**签名** `exr_status exr_layout_create_hyphenated(const exr_document *doc,exr_font *font, const exr_layout_config *config,exr_hyphenator *hyphenator,exr_layout **out,exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `doc`：要读取的结构化文档快照；`font`：已打开字体集合；同一字体上的排版/渲染由宿主串行化；`config`：布局配置，含页面、CSS、图片回调、方向、control；可 NULL 使用默认；`hyphenator`：可 NULL；自动断词词典；`out`：接收独立拥有的布局指针；用 exr_layout_free 释放；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：返回完整排版；可保留断词词典；仅 CSS hyphens:auto 开启自动断词；无效文档/字体/尺寸为 EXR_ARGUMENT，字体失败 EXR_FONT，内存/大小为 EXR_MEMORY/EXR_LIMIT，解析及取消错误透传；失败 *out=NULL。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 输入文档仅在创建期间使用；布局持有有效字体集合和解码图片，*out 用 exr_layout_free。不得释放 layout_font 借用视图。

### `exr_layout_create`

**签名** `exr_status exr_layout_create(const exr_document *doc, exr_font *font, const exr_layout_options *options, exr_layout **out, exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `doc`：要读取的结构化文档快照；`font`：已打开字体集合；同一字体上的排版/渲染由宿主串行化；`options`：简化页面参数；NULL 用默认值；`out`：接收独立拥有的布局指针；用 exr_layout_free 释放；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：返回完整排版；使用简化页面参数；无效文档/字体/尺寸为 EXR_ARGUMENT，字体失败 EXR_FONT，内存/大小为 EXR_MEMORY/EXR_LIMIT，解析及取消错误透传；失败 *out=NULL。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 输入文档仅在创建期间使用；布局持有有效字体集合和解码图片，*out 用 exr_layout_free。不得释放 layout_font 借用视图。

### `exr_layout_create_ex`

**签名** `exr_status exr_layout_create_ex(const exr_document *doc, exr_font *font, const exr_layout_config *config, exr_layout **out, exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `doc`：要读取的结构化文档快照；`font`：已打开字体集合；同一字体上的排版/渲染由宿主串行化；`config`：布局配置，含页面、CSS、图片回调、方向、control；可 NULL 使用默认；`out`：接收独立拥有的布局指针；用 exr_layout_free 释放；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：返回完整排版；使用完整 CSS、图片、方向、控制回调配置；无效文档/字体/尺寸为 EXR_ARGUMENT，字体失败 EXR_FONT，内存/大小为 EXR_MEMORY/EXR_LIMIT，解析及取消错误透传；失败 *out=NULL。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 输入文档仅在创建期间使用；布局持有有效字体集合和解码图片，*out 用 exr_layout_free。不得释放 layout_font 借用视图。

### `exr_layout_create_positioned`

**签名** `exr_status exr_layout_create_positioned(const exr_document *doc, exr_font *font, const exr_positioned_input *input, const exr_layout_config *config, exr_layout **out, exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `doc`：要读取的结构化文档快照；`font`：已打开字体集合；同一字体上的排版/渲染由宿主串行化；`input`：零初始化且设置 struct_size；由宿主提供 pages/glyphs/lines/boxes/paints 及计数；`config`：布局配置，含页面、CSS、图片回调、方向、control；可 NULL 使用默认；`out`：接收独立拥有的布局指针；用 exr_layout_free 释放；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：复制已定位数组并按 viewport 拟合页面；不重新 shaping/重排。无效数组范围/尺寸/struct_size 为 EXR_ARGUMENT，分配失败 EXR_MEMORY、数组数量/128 MiB 总预算超限 EXR_LIMIT；仅无 glyph 输入允许 font=NULL，失败 *out=NULL。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 输入数组复制；*out 用 exr_layout_free。

### `exr_pager_create`

**签名** `exr_status exr_pager_create(const exr_document *doc, exr_font *font, const exr_layout_config *config, exr_pager **out, exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `doc`：要读取的结构化文档快照；`font`：已打开字体集合；同一字体上的排版/渲染由宿主串行化；`config`：布局配置，含页面、CSS、图片回调、方向、control；可 NULL 使用默认；`out`：接收页器句柄；用 exr_pager_free 释放；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：创建可恢复逐页排版器；参数/字体/配置错误 EXR_ARGUMENT，内存/限额/解析错误透传。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 复制 config/CSS；借用 doc、font、图片/control context，须活到 pager_free；*out 用 exr_pager_free。

### `exr_txt_pager_create`

**签名** `exr_status exr_txt_pager_create(const exr_source *source,exr_font *font, const exr_layout_config *config,exr_pager **out,exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `source`：具有 size/read_at/context/release 的不可变、可寻址原始字节源；所有权见下；`font`：已打开字体集合；同一字体上的排版/渲染由宿主串行化；`config`：布局配置，含页面、CSS、图片回调、方向、control；可 NULL 使用默认；`out`：接收页器句柄；用 exr_pager_free 释放；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：创建按需 TXT 页器；不可寻址/无效源为 EXR_ARGUMENT，段落解码超过 64 KiB 为 EXR_LIMIT，用户 CSS 为 EXR_UNSUPPORTED；I/O/编码/内存/取消错误透传。此适配器不提供 pager CFI/锚点/选中文本查询。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 成功接管 source.context，由 pager_free 调用 release；失败仍归调用者。源字节必须不变，font/control context 借用至销毁。

### `exr_chapter_options_defaults`

**签名** `exr_chapter_options exr_chapter_options_defaults(void);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** 无。

**返回与失败** 按值返回默认带正确 size 的章节工作区和窗口预算；无失败通道。

**线程** 无共享可变状态；独立输入/输出可并发调用。

**所有权** 输入仅借用本次调用；值类型输出由调用者保存，无需释放。

### `exr_publication_pager_create`

**签名** `exr_status exr_publication_pager_create(exr_publication *publication,size_t part, exr_font *font,const exr_layout_config *config,const exr_chapter_options *options, exr_pager **out,exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物；`part`：零基 publication 目录索引；`font`：已打开字体集合；同一字体上的排版/渲染由宿主串行化；`config`：布局配置，含页面、CSS、图片回调、方向、control；可 NULL 使用默认；`options`：可 NULL；size=sizeof，workspace_budget 覆盖章节索引/XML/window/CSS，window_bytes 是偏好值；图片/字体/页缓存另计；`out`：接收页器句柄；用 exr_pager_free 释放；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：建立单 EPUB 章节的有界页器；不支持的 provider 为 EXR_UNSUPPORTED，无效 part/options 为 EXR_ARGUMENT，工作区不足 EXR_LIMIT；读取/解析/字体/取消错误透传。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 保留 publication 引用；借用 font/回调 context；*out 用 exr_pager_free。

### `exr_pager_chapter_statistics`

**签名** `exr_chapter_stats exr_pager_chapter_statistics(const exr_pager *pager);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `pager`：当前页器

**返回与失败** 按值返回章节输入、索引、解析工作区、窗口、页缓存和恢复点统计；非章节页器/NULL 返回零记录。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 输入仅借用本次调用；值类型输出由调用者保存，无需释放。

### `exr_pager_read_text`

**签名** `exr_status exr_pager_read_text(exr_pager *pager,size_t start,size_t end, exr_text_sink_fn sink,void *context,const exr_control *control,exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `pager`：当前页器；`start`：当前章节的规范化 UTF-8 起始字节边界（含）；`end`：当前章节的规范化 UTF-8 结束字节边界（不含）；`sink`：接收完整 UTF-8 块的回调，返回 exr_status；`context`：sink 的宿主上下文；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：同步流式发送 [start,end) 的规范化 UTF-8，单块至多 32 KiB；无效区间 EXR_ARGUMENT，不支持页器 EXR_UNSUPPORTED，I/O/取消或 sink 状态透传。失败前可能已发送前缀。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** sink 的 utf8 仅在回调内有效；宿主需要复制。输出文件的原子替换由宿主负责。

### `exr_pager_next`

**签名** `exr_status exr_pager_next(exr_pager *pager, exr_layout **out, exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `pager`：当前页器；`out`：接收独立拥有的布局指针；用 exr_layout_free 释放；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK 且 *out 非 NULL：独立单页；EXR_OK 且 *out=NULL：EOF。不得与 get 混用，状态/参数错误 EXR_ARGUMENT；排版/读取/取消错误后重新创建页器。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 每个输出用 exr_layout_free；同页器各页共享不可变图片，页的释放/引用生命周期变化须串行。

### `exr_pager_set_control`

**签名** `exr_status exr_pager_set_control(exr_pager *pager, const exr_control *control, exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `pager`：当前页器；`control`：可 NULL 清空控制回调；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：更新后续工作控制回调；无效/活动页器为 EXR_ARGUMENT。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 复制回调结构；context 借用，须活到替换控制器或 pager_free。

### `exr_pager_set_hyphenator`

**签名** `exr_status exr_pager_set_hyphenator(exr_pager *pager,exr_hyphenator *hyphenator,exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `pager`：当前页器；`hyphenator`：可 NULL 清除自动断词；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：设置/清除断词词典；必须在 set_cache/get/next 前调用，状态不符为 EXR_ARGUMENT。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 保留词典；调用者可释放自己的词典引用，页器销毁释放保留引用。

### `exr_pager_set_cache`

**签名** `exr_status exr_pager_set_cache(exr_pager *pager, size_t capacity, size_t byte_budget, exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `pager`：当前页器；`capacity`：驻留页容量（1..64）；`byte_budget`：页载荷预算字节；0 不限制；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：配置 get 模式页缓存；无效容量/顺序/重入为 EXR_ARGUMENT。降低限制可淘汰页；超大新页返回 EXR_LIMIT 并保留旧页。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 页缓存归 pager；淘汰使相应借用 layout 失效。

### `exr_pager_get`

**签名** `exr_status exr_pager_get(exr_pager *pager, size_t page, const exr_layout **out, exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `pager`：当前页器；`page`：零基页面索引；`out`：接收页器缓存中借用的单页布局；不能 layout_free，有效期见所有权；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：取得指定零基页；越界/已用 next/重入为 EXR_ARGUMENT，新页超预算 EXR_LIMIT，排版/取消失败保留已缓存页面。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 返回页器借用页面；保守地在下一次 get/set_cache/free 前用完，不调用 layout_free。

### `exr_pager_cached_count`

**签名** `size_t exr_pager_cached_count(const exr_pager *pager);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `pager`：当前页器

**返回与失败** 返回当前缓存页数；NULL 返回 0。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 输入仅借用本次调用；值类型输出由调用者保存，无需释放。

### `exr_pager_cached_bytes`

**签名** `size_t exr_pager_cached_bytes(const exr_pager *pager);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `pager`：当前页器

**返回与失败** 返回当前缓存页载荷字节；NULL 返回 0。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 输入仅借用本次调用；值类型输出由调用者保存，无需释放。

### `exr_pager_set_checkpoints`

**签名** `exr_status exr_pager_set_checkpoints(exr_pager *pager, size_t capacity, size_t byte_budget, size_t interval, exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `pager`：当前页器；`capacity`：恢复点最大数；0 关闭；`byte_budget`：独立于页面缓存的恢复点字节预算；`interval`：每隔多少页建立恢复点；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：配置内存恢复点；capacity>64 或启用时 byte_budget/interval 为 0 返回 EXR_ARGUMENT。默认 4 项/2 MiB/每 16 页。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 恢复点归 pager，不可直接持久化。

### `exr_pager_statistics`

**签名** `exr_pager_stats exr_pager_statistics(const exr_pager *pager);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `pager`：当前页器

**返回与失败** 按值返回累计生成页、恢复点数/字节和恢复次数；NULL 为全零。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 输入仅借用本次调用；值类型输出由调用者保存，无需释放。

### `exr_pager_position`

**签名** `size_t exr_pager_position(const exr_pager *pager);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `pager`：当前页器

**返回与失败** 返回已经扫描的规范化 UTF-8 源位置（可因前瞻领先最后页面，不是恢复令牌）；NULL 返回 0。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 输入仅借用本次调用；值类型输出由调用者保存，无需释放。

### `exr_pager_free`

**签名** `void exr_pager_free(exr_pager *pager);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `pager`：当前页器

**返回与失败** 无返回值；NULL 可传。

**线程** 必须与对象及借用视图的全部使用串行化。

**所有权** 释放页器、缓存、恢复点和持有的 publication/source 引用；借用 doc/font 的宿主引用不由此释放。

### `exr_session_create`

**签名** `exr_status exr_session_create(exr_publication *publication, exr_font *font, const exr_layout_config *config, size_t capacity, exr_session **out, exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物；`font`：已打开字体集合；同一字体上的排版/渲染由宿主串行化；`config`：布局配置，含页面、CSS、图片回调、方向、control；可 NULL 使用默认；`capacity`：驻留 part 最大数（1..64）；`out`：接收章节缓存会话句柄；用 exr_session_free 释放；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：创建按章节缓存排版会话；capacity 不在 1..64、参数/配置错误为 EXR_ARGUMENT，分配失败 EXR_MEMORY。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 复制 config/CSS、保留 publication；font 与图片/control context 须活到 session_free；*out 用 exr_session_free。

### `exr_session_get`

**签名** `exr_status exr_session_get(exr_session *session, size_t part, const exr_document **document, const exr_layout **layout, exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `session`：当前章节排版会话；`part`：零基 publication 目录索引；`document`：接收章节文档借用指针；`layout`：接收章节布局借用指针；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：按需载入/排版 part，命中则复用；part 错误 EXR_ARGUMENT，新条目超预算 EXR_LIMIT；载入/排版/取消失败保留旧缓存。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** *document/*layout 均为会话借用对象，有效到下次 get/clear/free 或会淘汰缓存的设置；不单独释放。

### `exr_session_cached`

**签名** `size_t exr_session_cached(const exr_session *session);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `session`：当前章节排版会话

**返回与失败** 返回驻留 part 数；NULL 返回 0。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 输入仅借用本次调用；值类型输出由调用者保存，无需释放。

### `exr_session_set_budget`

**签名** `exr_status exr_session_set_budget(exr_session *session, size_t bytes, exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `session`：当前章节排版会话；`bytes`：字节预算；0 不限制；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：设置驻留文档+布局载荷预算，降低时淘汰 LRU；无效会话 EXR_ARGUMENT。共享源、字体、临时解析和位图不在此预算中。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 淘汰条目的借用指针失效；无新输出。

### `exr_session_set_hyphenator`

**签名** `exr_status exr_session_set_hyphenator(exr_session *session,exr_hyphenator *hyphenator,exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `session`：当前章节排版会话；`hyphenator`：可 NULL 清除词典；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：更新断词词典，变更时清空布局缓存；无效会话 EXR_ARGUMENT。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 保留新词典并释放旧引用；旧缓存借用视图失效。

### `exr_session_cached_bytes`

**签名** `size_t exr_session_cached_bytes(const exr_session *session);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `session`：当前章节排版会话

**返回与失败** 返回驻留缓存载荷字节数；NULL 返回 0。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 输入仅借用本次调用；值类型输出由调用者保存，无需释放。

### `exr_session_clear`

**签名** `void exr_session_clear(exr_session *session);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `session`：当前章节排版会话

**返回与失败** 无返回值；NULL 可传。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 释放全部缓存章节文档/布局，借用视图失效；会话继续可用。

### `exr_session_free`

**签名** `void exr_session_free(exr_session *session);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `session`：当前章节排版会话

**返回与失败** 无返回值；NULL 可传。

**线程** 必须与对象及借用视图的全部使用串行化。

**所有权** 释放会话、缓存、publication/词典引用；font 和回调 context 由宿主另行释放。

### `exr_layout_free`

**签名** `void exr_layout_free(exr_layout *layout);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `layout`：待查询布局

**返回与失败** 无返回值；NULL 可传。

**线程** 必须与对象及借用视图的全部使用串行化。

**所有权** 释放自有布局引用、字体集合与图片；不能传 pager_get/session_get 的借用指针。

### `exr_layout_memory_size`

**签名** `size_t exr_layout_memory_size(const exr_layout *layout);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `layout`：待查询布局

**返回与失败** 返回布局自有容量字节；NULL 为 0；共享对象预算须按相关 API 另计。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 输入仅借用本次调用；值类型输出由调用者保存，无需释放。

### `exr_layout_writing_mode`

**签名** `exr_writing_mode exr_layout_writing_mode(const exr_layout *layout);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `layout`：待查询布局

**返回与失败** 返回布局书写方向；NULL 返回默认水平书写值。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 输入仅借用本次调用；值类型输出由调用者保存，无需释放。

### `exr_layout_pages`

**签名** `const exr_page *exr_layout_pages(const exr_layout *layout, size_t *count);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `layout`：待查询布局；`count`：可 NULL，接收布局页数量

**返回与失败** 返回页范围数组；NULL 布局返回 NULL/count=0。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 借用至布局释放；若布局归 pager/session，则受其更短缓存有效期限制，不释放。

### `exr_layout_lines`

**签名** `const exr_line *exr_layout_lines(const exr_layout *layout, size_t *count);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `layout`：待查询布局；`count`：可 NULL，接收布局行数量

**返回与失败** 返回行几何与源范围数组；NULL 布局返回 NULL/count=0。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 借用至布局释放；若布局归 pager/session，则受其更短缓存有效期限制，不释放。

### `exr_layout_glyphs`

**签名** `const exr_glyph *exr_layout_glyphs(const exr_layout *layout, size_t *count);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `layout`：待查询布局；`count`：可 NULL，接收字形数量

**返回与失败** 返回字形、cluster 与字体索引数组；NULL 布局返回 NULL/count=0。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 借用至布局释放；若布局归 pager/session，则受其更短缓存有效期限制，不释放。

### `exr_layout_boxes`

**签名** `const exr_box *exr_layout_boxes(const exr_layout *layout, size_t *count);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `layout`：待查询布局；`count`：可 NULL，接收布局盒数量

**返回与失败** 返回块/图片/边框几何数组；NULL 布局返回 NULL/count=0。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 借用至布局释放；若布局归 pager/session，则受其更短缓存有效期限制，不释放。

### `exr_layout_paints`

**签名** `const exr_paint *exr_layout_paints(const exr_layout *layout, size_t page, size_t *count);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `layout`：待查询布局；`page`：零基页面索引；`count`：可 NULL，接收该页绘制命令数量

**返回与失败** 返回定位页面有序绘制命令；重排布局、非法页或无命令返回 NULL/count=0。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 数组借用至布局释放/缓存淘汰；不释放。

### `exr_layout_image`

**签名** `const exr_bitmap *exr_layout_image(const exr_layout *layout, size_t resource);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `layout`：待查询布局；`resource`：文档资源零基索引

**返回与失败** 返回对应资源的解码 RGBA 位图视图；无资源、未解码或无效布局返回 NULL。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 位图和像素借用至布局释放/缓存淘汰；不调用 bitmap_free。

### `exr_layout_page_at`

**签名** `size_t exr_layout_page_at(const exr_layout *layout, size_t utf8_offset);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `layout`：待查询布局；`utf8_offset`：布局源文本的规范化 UTF-8 字节位置

**返回与失败** 返回包含/最接近此前起点的页面索引；无布局/页面为 SIZE_MAX。该函数不验证 offset 是否在全文内，超大偏移可能落到最后页。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 无分配；布局只读。

### `exr_layout_hit_test`

**签名** `size_t exr_layout_hit_test(const exr_layout *layout, size_t page, float x, float y);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `layout`：待查询布局；`page`：零基页面索引；`x`：页内布局坐标 x，原点左上；`y`：页内布局坐标 y，向下为正

**返回与失败** 返回最近文字行的 cluster 边缘 UTF-8 位置；无效页/非有限坐标为 SIZE_MAX，无行页面返回 page.start。页面空白也可能吸附最近行。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 输入仅借用本次调用；值类型输出由调用者保存，无需释放。

### `exr_hit_test`

**签名** `exr_status exr_hit_test(const exr_layout *layout,size_t part,size_t page,float x,float y, exr_text_position *out,exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `layout`：待查询布局；`part`：宿主给定的 publication part 索引，写入命中结果；`page`：零基页面索引；`x`：页内布局坐标 x，原点左上；`y`：页内布局坐标 y，向下为正；`out`：接收 part 与规范化 UTF-8 字节 offset；未命中为 {SIZE_MAX,SIZE_MAX}；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：得到最近 cluster 边缘位置；图片/行外未命中返回 {SIZE_MAX,SIZE_MAX}。无效参数/页号为 EXR_ARGUMENT；不把连字拆成虚构字符几何。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** out 为调用者值结构，不分配。

### `exr_edit_anchor_capture`

**签名** `exr_status exr_edit_anchor_capture(const exr_pager *pager,size_t page_index, exr_edit_id block_id,size_t byte_offset,exr_edit_view_anchor *out,exr_error *error);`

**ABI** 实验（[公开头文件](../include/exr/reflow.h)）。

**参数** pager、page_index 指定编辑页；block_id 与 byte_offset 为块内拼接 run 的 UTF-8 字节边界；out、error 接收输出。

**返回与失败** 编辑前捕获；返回 EXR_OK，无效页、块、UTF-8 边界或文字不在该页为 EXR_ARGUMENT；缺少模型实现时 EXR_UNSUPPORTED。

**线程** 同一模型、出版物或分页器的访问由宿主串行化；不与修改、重排或释放并发。

**所有权** out 为值记录；宿主另存相对像素位移。

### `exr_edit_anchor_restore`

**签名** `exr_status exr_edit_anchor_restore(const exr_pager *pager, const exr_edit_view_anchor *before,exr_edit_view_anchor *out,exr_error *error);`

**ABI** 实验（[公开头文件](../include/exr/reflow.h)）。

**参数** pager 为更新后的编辑分页器；before 为保存的锚点，out 接收恢复位置，error 为诊断。

**返回与失败** 返回 exr_status；只接受当前及上一成功修订，过期/无效锚点为 EXR_ARGUMENT，缺少模型实现时 EXR_UNSUPPORTED。插入取右亲和，删除文字收缩到替换末端，删块优先向后找，EOF 再向前。

**线程** 同一模型、出版物或分页器的访问由宿主串行化；不与修改、重排或释放并发。

**所有权** 输入输出可为同一记录；page_offset 为页内源字节偏移，宿主自行恢复像素位移。

### `exr_edit_layout_after`

**签名** `exr_status exr_edit_layout_after(exr_edit_doc *doc,exr_pager *pager, exr_edit_id changed_block_id,size_t *pages_repaginated,exr_error *error);`

**ABI** 实验（[公开头文件](../include/exr/reflow.h)）。

**参数** doc 为当前或保留 ID 的替换模型；pager 为编辑分页器；changed_block_id=0 自动检测，否则仅作提示；pages_repaginated、error 接收输出。

**返回与失败** 返回 exr_status；比较快照汇总全部编辑、事务和 undo/redo。失败不提交新目录、不失效旧缓存；缺少模型实现时 EXR_UNSUPPORTED。

**线程** 同一模型、出版物或分页器的访问由宿主串行化；不与修改、重排或释放并发。

**所有权** 成功后替换绑定模型，所有旧借用页失效；保留模型直至 pager 释放或成功换绑。

### `exr_edit_pager_create`

**签名** `exr_status exr_edit_pager_create(exr_edit_doc *doc,exr_font *font, const exr_layout_config *config,exr_pager **out,exr_error *error);`

**ABI** 实验（[公开头文件](../include/exr/reflow.h)）。

**参数** doc 为编辑模型，font 为字体，config 为宿主几何配置（可为 NULL 取默认），out 为分页器输出，error 为诊断。

**返回与失败** 返回 EXR_OK 或参数/分配/排版错误；缺少模型实现时 EXR_UNSUPPORTED。opaque run/表格、编号、keep-next、user CSS 不支持；页大小不取节纸张大小。

**线程** 同一模型、出版物或分页器的访问由宿主串行化；不与修改、重排或释放并发。

**所有权** 模型必须比 pager 活得久；font 保留引用；成功 pager 用 exr_pager_free 释放，失败清空 out。

### `exr_edit_reflow_statistics`

**签名** `exr_edit_reflow_stats exr_edit_reflow_statistics(const exr_pager *pager);`

**ABI** 实验（[公开头文件](../include/exr/reflow.h)）。

**参数** pager 为编辑分页器。

**返回与失败** 按值返回 revision、page_count、pages_repaginated、pages_reused、cache_invalidated 和 dirty；非编辑分页器返回零。dirty 的 old/new 区间为半开块顺序，first_page/end_page 为旧脏页区间，不能按 ID 大小排序。

**线程** 同一模型、出版物或分页器的访问由宿主串行化；不与修改、重排或释放并发。

**所有权** 统计为值拷贝。

### `exr_layout_fixed_viewport`

**签名** `exr_fixed_viewport exr_layout_fixed_viewport(const exr_layout *layout);`

**ABI** 实验（[公开头文件](../include/exr/layout.h)）。

**参数** layout 为已排版页面。

**返回与失败** 返回 fixed、source、原生 width/height、统一 scale 和居中偏移 x/y；可重排页面返回零记录。

**线程** 同一模型、出版物或分页器的访问由宿主串行化；不与修改、重排或释放并发。

**所有权** 按值返回。

### `exr_pager_cache_stats_get`

**签名** `exr_status exr_pager_cache_stats_get(const exr_pager *pager, exr_pager_cache_stats *out, exr_error *error);`

**ABI** 实验；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `pager`：分页器；`out`：调用前须将 struct_size 设为 sizeof(exr_pager_cache_stats)，接收终身 requests/hits/misses 计数；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：写入快照；顺序 next() 每交付一页计一次请求与未命中，get() 模式每次有效查询均计数；pager/out 为 NULL 或 struct_size 不符 EXR_ARGUMENT。

**线程** 同一分页器的访问由宿主串行化；不与翻页、重排或释放并发。

**所有权** 值类型输出由调用者保存，无需释放；不取得分页器所有权。

### `exr_pager_cache_statistics`

**签名** `exr_pager_cache_stats exr_pager_cache_statistics(const exr_pager *pager);`

**ABI** 实验（[公开头文件](../include/exr/layout.h)）。

**参数** pager 为分页器，可为 NULL。

**返回与失败** 返回页缓存 requests/hits/misses（struct_size 已填充）；NULL 返回零统计。

**线程** 同一模型、出版物或分页器的访问由宿主串行化；不与修改、重排或释放并发。

**所有权** 按值返回，不取得缓存页所有权。

### `exr_publication_page_progression`

**签名** `exr_direction exr_publication_page_progression(const exr_publication *publication);`

**ABI** 实验（[公开头文件](../include/exr/layout.h)）。

**参数** publication 为出版物，可为 NULL。

**返回与失败** 返回物理方向，NULL/自定义出版物默认 LTR；用于左右键和跨页槽位，不倒转 spine 或 pager_next 顺序。

**线程** 同一模型、出版物或分页器的访问由宿主串行化；不与修改、重排或释放并发。

**所有权** 按值返回。

### `exr_publication_rendition`

**签名** `exr_status exr_publication_rendition(const exr_publication *publication, size_t part, exr_part_rendition *out, exr_error *error);`

**ABI** 实验（[公开头文件](../include/exr/layout.h)）。

**参数** publication 和 part 指定零基章节；out 必须非空，error 接收诊断。

**返回与失败** 返回 EXR_OK；无效章节/输出返回 EXR_ARGUMENT。out 包含 layout、spread、viewport_width/height；非 EPUB 为可重排，缺失 viewport 为零。

**线程** 同一模型、出版物或分页器的访问由宿主串行化；不与修改、重排或释放并发。

**所有权** 写入调用者的 out，无新增分配。

### `exr_publication_spreads`

**签名** `exr_status exr_publication_spreads(const exr_publication *publication, exr_spread **spreads, size_t *count, exr_error *error);`

**ABI** 实验（[公开头文件](../include/exr/layout.h)）。

**参数** publication 为出版物；spreads、count 为非空输出，error 接收诊断。

**返回与失败** 返回 EXR_OK；无效输入为 EXR_ARGUMENT，分配失败为 EXR_MEMORY。输出阅读顺序的屏幕，left/right 为物理槽位的 part 索引，空槽为 SIZE_MAX；EXR_SPREAD_SINGLE 时单页在 left。

**线程** 同一模型、出版物或分页器的访问由宿主串行化；不与修改、重排或释放并发。

**所有权** 成功数组用 exr_free 释放；有效输出先置 NULL/0。


## 搜索

分别在文档快照、固定页全文、章节正文和磁盘索引中返回可导航的 UTF-8 位置。

最小调用示例：[examples/search.c](examples/search.c)。

<!-- example: docs/examples/search.c -->
```c
/* SPDX-License-Identifier: MIT */
#include <exr/formats.h>
#include <stdio.h>

int main(void) {
  const char text[] = "Find this word, then find another word.";
  exr_document *document = NULL;
  exr_error error = {0};
  size_t start = SIZE_MAX, end = SIZE_MAX;
  exr_status status = exr_document_open_memory(EXR_TXT, text, sizeof(text) - 1,
                                               &document, &error);
  if (status == EXR_OK)
    status = exr_document_find(document, "word", 0, &start, &end, &error);
  if (status == EXR_OK) {
    if (start != SIZE_MAX) printf("UTF-8 byte range [%zu, %zu)\n", start, end);
    else puts("No match");
  } else fprintf(stderr, "%s\n", error.message);
  exr_document_free(document);
  return status == EXR_OK ? 0 : 1;
}
```

### `exr_fixed_text_find`

**签名** `exr_status exr_fixed_text_find(const exr_fixed_text *text,const char *query,size_t query_size,size_t from, const exr_control *control,size_t *start,size_t *end,exr_error *error);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `text`：固定页文字快照；由 exr_fixed_text_create 或固定页文字加载 API 返回；`query`：带 query_size 的 UTF-8 查询，允许嵌入 NUL；`query_size`：查询字节数，1..1 MiB；`from`：快照内包含起点的 UTF-8 字节偏移；向前对齐边界；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`start`：接收首个匹配的起始 UTF-8 字节偏移（含）；未命中为 SIZE_MAX；`end`：接收首个匹配的结束 UTF-8 字节偏移（不含）；未命中为 SIZE_MAX；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：快照中区分大小写的精确字节匹配（支持嵌入 NUL）；未命中 start/end=SIZE_MAX。无效参数/UTF-8 为 EXR_ARGUMENT/EXR_ENCODING，query_size>1 MiB 为 EXR_LIMIT，可取消。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 只写调用者的 start/end；输入快照不变。

### `exr_document_search`

**签名** `exr_status exr_document_search(exr_fixed_document *document,size_t offset,const char *needle, const exr_control *control,exr_search_match *match,exr_error *error);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `document`：固定页文档句柄；`offset`：所有固定页文字连接后的全局 UTF-8 字节起点（包含）；`needle`：非空 NUL 结尾 UTF-8 查询（至多 1 MiB）；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`match`：接收全局 start/end 与起止 page/页内 offset；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：固定页按 provider 顺序、无插入页分隔符连接后首个精确命中，可跨页；未命中 match 全部字段 SIZE_MAX。全书无文字 EXR_NO_TEXT_LAYER；参数/编码/1 MiB 查询上限/读取/取消错误透传，每次最多载入一页。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** match 为调用者值结构；临时文字页由实现释放。

### `exr_document_find`

**签名** `exr_status exr_document_find(const exr_document *doc, const char *query, size_t from, size_t *start, size_t *end, exr_error *error);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `doc`：要读取的结构化文档快照；`query`：非空 NUL 结尾 UTF-8 查询；`from`：包含的规范化 UTF-8 搜索起点；`start`：接收首个匹配的起始 UTF-8 字节偏移（含）；未命中为 SIZE_MAX；`end`：接收首个匹配的结束 UTF-8 字节偏移（不含）；未命中为 SIZE_MAX；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：返回区分大小写的精确首个命中；未命中 start/end=SIZE_MAX。空查询/非法参数 EXR_ARGUMENT，非法 UTF-8 EXR_ENCODING，查询超过 1 MiB EXR_LIMIT；from 向前对齐 UTF-8 边界。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 输入仅借用本次调用；值类型输出由调用者保存，无需释放。

### `exr_publication_search`

**签名** `exr_status exr_publication_search(exr_publication *publication,exr_text_position from, const char *needle,unsigned flags,const exr_control *control,exr_search_result *result,exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物；`from`：包含的起点 part+章节内 UTF-8 字节 offset；`needle`：非空 NUL 结尾 UTF-8 查询（至多 1 MiB）；`flags`：0 默认有限大小写折叠；EXR_SEARCH_CASE_SENSITIVE/WHOLE_WORD 位组合；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`result`：接收 found/part/offset/length；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：首个线性 part 内命中，result.found=0 表示无匹配；跨 part 不拼接，不环绕。默认只折叠 ASCII/Latin-1 大小写；非法查询/flags 为 EXR_ARGUMENT/EXR_ENCODING，查询>1 MiB 为 EXR_LIMIT；载入/取消失败清空结果。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 文本快照缓存在 publication，释放出版物才清除；结果值由宿主保存。

### `exr_publication_search_all`

**签名** `exr_status exr_publication_search_all(exr_publication *publication,const char *needle, unsigned flags,exr_search_fn callback,void *context,const exr_control *control,size_t *count,exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物；`needle`：非空 NUL 结尾 UTF-8 查询（至多 1 MiB）；`flags`：EXR_SEARCH_CASE_SENSITIVE/WHOLE_WORD 位组合；`callback`：非零继续，0 停止；可 NULL 仅计数；`context`：宿主回调上下文，本次借用；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`count`：接收本次已交付命中数；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：按阅读顺序枚举包括重叠的匹配，count 含触发 callback=0 的命中；NULL callback 仅计数。查询/flags/UTF-8/长度校验同 publication_search；取消/错误清零 count。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** callback result 仅回调期间借用；需留存则复制值；publication 拥有懒加载快照。

### `exr_publication_index_build`

**签名** `exr_status exr_publication_index_build(exr_publication *publication,size_t memory_limit, size_t max_parts,const exr_control *control,exr_index_stats *stats,exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物；`memory_limit`：索引 handle+单个 build/query 缓冲预算；0 按 UTF-8 字节 30%（至少 512）决定；provider 解析不计入；`max_parts`：本次最多推进目录条目数，0 不限；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`stats`：可 NULL，接收文本/内存峰值/磁盘/已建 part/完成状态；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：推进磁盘位置索引，stats.complete 表示完成；max_parts=0 完成全部。非零内存预算<512 返回 EXR_LIMIT；参数/源载入/临时文件/内存/取消失败透传，已完成 part 可继续。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 索引及临时文件归 publication；stats 为值结构，可 NULL。

### `exr_publication_index_search`

**签名** `exr_status exr_publication_index_search(exr_publication *publication,const char *needle, unsigned flags,exr_index_cursor *cursor,size_t max_results,exr_search_fn callback,void *context, const exr_control *control,size_t *count,exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物；`needle`：非空 NUL 结尾 UTF-8 查询（至多 1 MiB）；`flags`：基础搜索 flags，可加 EXR_INDEX_IGNORE_DIACRITICS（Latin-1 和 U+0300..036F）；`cursor`：首次全零；续查保持同一 needle/flags，返回 next 与 done；`max_results`：0 流式全部；否则本次交付上限；`callback`：非零继续，0 提前停止；可 NULL 只计数；`context`：宿主回调上下文，本次借用；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`count`：本次已交付命中数；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：索引分页枚举，保留重叠匹配；缺少索引时自动建立，并按搜索进度补建未完成 part；查询/游标/flags 不合法时失败；I/O、内存、取消错误清零 count 并保持输入 cursor。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** cursor 由宿主保存；callback 结果仅在回调期间借用；不释放 publication 内部索引。

### `exr_publication_index_info`

**签名** `exr_status exr_publication_index_info(exr_publication *publication,exr_index_stats *stats, exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物；`stats`：接收当前索引统计；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：读取当前索引统计（不存在时零记录）；publication/stats 缺失为 EXR_ARGUMENT。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** stats 值结构，无需释放。

### `exr_publication_index_save`

**签名** `exr_status exr_publication_index_save(exr_publication *publication,const char *path, const char *revision,const exr_control *control,exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物；`path`：索引输出文件路径；`revision`：非空不可变内容标识；源字节或投影选项变化必须改变，例如 SHA-256；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：保存完整或部分索引；缺少索引/路径/非空 revision 为 EXR_ARGUMENT，I/O/取消失败可留下未完成文件。先写新路径再由宿主 rename 实现替换。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 借用 path/revision；写出的索引文件由宿主管理。

### `exr_publication_index_load`

**签名** `exr_status exr_publication_index_load(exr_publication *publication,const char *path, const char *revision,size_t memory_limit,const exr_control *control,exr_index_stats *stats,exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物；`path`：已保存索引路径；`revision`：当前原文和投影选项的不可变标识，必须匹配；`memory_limit`：非零至少 512，0 自动预算；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`stats`：可 NULL，接收载入后的统计；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：载入索引并可继续剩余 part；版本/目录/内容 revision/校验和/边界不符失败，I/O/内存/预算/取消错误透传；失败保留旧索引可用。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 新索引归 publication；stats 为值结构，可 NULL。

## 标注

用文本范围、引文锚点、固定页四边形与 EPUB CFI 捕获并恢复选择和书签。

最小调用示例：[examples/annotation.c](examples/annotation.c)。

<!-- example: docs/examples/annotation.c -->
```c
/* SPDX-License-Identifier: MIT */
#include <exr/formats.h>
#include <stdio.h>

int main(void) {
  const char text[] = "Keep this sentence.";
  exr_document *document = NULL;
  exr_anchor anchor = {0};
  exr_text_annotation input = {0}, restored = {0};
  exr_anchor_match match = {0};
  char *json = NULL;
  size_t size = 0;
  exr_error error = {0};
  exr_status status = exr_document_open_memory(EXR_TXT, text, sizeof(text) - 1,
                                               &document, &error);
  if (status == EXR_OK)
    status = exr_anchor_create(document, 0, sizeof(text) - 1, &anchor, &error);
  input.id = "urn:example:note:1";
  input.source = "urn:example:book:1";
  input.text = "My comment";
  input.anchor = anchor; /* Borrowed shallow copy for export only. */
  if (status == EXR_OK) status = exr_text_annotation_export(&input, &json, &size, &error);
  if (status == EXR_OK) status = exr_text_annotation_import(json, size, &restored, &error);
  if (status == EXR_OK) status = exr_anchor_resolve(document, &restored.anchor, &match, &error);
  if (status == EXR_OK && match.state == EXR_ANCHOR_FOUND)
    printf("restored [%zu, %zu), JSON bytes=%zu\n", match.start, match.end, size);
  else {
    fprintf(stderr, "%s\n", status == EXR_OK ? "Anchor was not uniquely resolved" : error.message);
    if (status == EXR_OK) status = EXR_FORMAT;
  }
  exr_text_annotation_free(&restored);
  exr_free(json);
  exr_anchor_free(&anchor);
  exr_document_free(document);
  return status == EXR_OK ? 0 : 1;
}
```

`exr_anchor` 的 start/end 为规范化 UTF-8 字节；`exr_text_range` 为 part+字节的半开范围；`exr_cfi_point` 的文本 offset 为原始 DOM UTF-16 code units。保存锚点字段与内容版本，不保存指针。

### `exr_fixed_text_select`

**签名** `exr_status exr_fixed_text_select(const exr_fixed_text *text,size_t start,size_t end,const exr_control *control, exr_text_region **regions,size_t *count,exr_error *error);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `text`：固定页文字快照；由 exr_fixed_text_create 或固定页文字加载 API 返回；`start`：当前文字快照的规范化 UTF-8 起始字节边界（含）；`end`：当前文字快照的规范化 UTF-8 结束字节边界（不含）；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`regions`：接收新分配的 quad+范围数组；`count`：接收区域数；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：按 provider 顺序复制与 [start,end) 重叠的完整区域；不细分连字。非法 UTF-8 边界/范围 EXR_ARGUMENT，分配/取消失败透传。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 返回 *regions 由 exr_free 释放。

### `exr_fixed_text_hit`

**签名** `exr_status exr_fixed_text_hit(const exr_fixed_text *text,double x,double y,double max_distance,unsigned exclude_flags, const exr_control *control,size_t *region,exr_error *error);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `text`：固定页文字快照；由 exr_fixed_text_create 或固定页文字加载 API 返回；`x`：原生页坐标 x；`y`：原生页坐标 y；`max_distance`：允许的最大非负距离；`exclude_flags`：过滤 EXR_REGION_VERTICAL/INVISIBLE 等区域 flags；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`region`：接收 regions 数组索引；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：返回 max_distance 内最近区域索引；相等距离取首个；未命中 *region=SIZE_MAX。非有限坐标/负距离等 EXR_ARGUMENT，可取消。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 只返回索引，区域仍归 text。

### `exr_fixed_anchor_create`

**签名** `exr_status exr_fixed_anchor_create(const char *page_id,const exr_fixed_text *text,size_t start,size_t end, exr_fixed_anchor *out,exr_error *error);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `page_id`：当前页面稳定非空 UTF-8 ID；`text`：固定页文字快照；由 exr_fixed_text_create 或固定页文字加载 API 返回；`start`：当前文字快照的规范化 UTF-8 起始字节边界（含）；`end`：当前文字快照的规范化 UTF-8 结束字节边界（不含）；`out`：接收拥有 page_id/引文/上下文与显式字节长度的页面选择器（先零初始化）；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：创建页面范围选择器，保留显式文本字节长度；page_id 为空、范围/UTF-8 边界无效为 EXR_ARGUMENT，超限 EXR_LIMIT，分配失败 EXR_MEMORY。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** out 零初始化；字符串由 exr_fixed_anchor_free(out) 释放。

### `exr_fixed_anchor_free`

**签名** `void exr_fixed_anchor_free(exr_fixed_anchor *anchor);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `anchor`：锚点/选择器输入（见签名类型）

**返回与失败** 无返回值；NULL 可传。

**线程** 必须与对象及借用视图的全部使用串行化。

**所有权** 释放 SDK 生成的 page_id/exact/prefix/suffix 并清零；不能释放宿主借用输入。

### `exr_fixed_anchor_resolve`

**签名** `exr_status exr_fixed_anchor_resolve(const char *page_id,const exr_fixed_text *text,const exr_fixed_anchor *anchor, const exr_control *control,exr_anchor_match *match,exr_error *error);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `page_id`：当前文字快照对应的稳定页面 ID；`text`：固定页文字快照；由 exr_fixed_text_create 或固定页文字加载 API 返回；`anchor`：锚点/选择器输入（见签名类型）；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`match`：接收定位结果和 FOUND/MISSING/AMBIGUOUS/LEGACY 状态；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：match.state 报 FOUND/MISSING/AMBIGUOUS/LEGACY；不让旧偏移覆盖歧义。页面 ID 不匹配不能得到 FOUND；非法选择器/边界/UTF-8、分配或取消失败透传。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** anchor 输入借用；match 为值结构。

### `exr_fixed_load_annotations`

**签名** `exr_status exr_fixed_load_annotations(exr_fixed_document *document,size_t page,const exr_control *control, exr_page_annotation **annotations,size_t *count,exr_error *error);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `document`：固定页文档句柄；`page`：零基页面索引；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`annotations`：接收标注数组，bounds/quads 使用原生页坐标；`count`：接收返回原生页面标注数；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：复制页面原生标注及 properties；缺少 annotations provider 为 EXR_FORMAT，无效页 EXR_ARGUMENT；provider/I/O/内存/取消错误透传。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** *annotations 深复制，用 exr_page_annotations_free(*annotations,*count)。

### `exr_page_annotations_free`

**签名** `void exr_page_annotations_free(exr_page_annotation *annotations,size_t count);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `annotations`：原生页面标注数组（含 bounds/quads/properties）；`count`：待释放数组的原始条目数，须与对应查询返回的 count 一致

**返回与失败** 无返回值；NULL/0 可传。

**线程** 必须与对象及借用视图的全部使用串行化。

**所有权** 释放整个标注数组以及复制的 ID/kind/quads/properties；count 必须是返回条目数。

### `exr_fixed_character_at`

**签名** `exr_status exr_fixed_character_at(exr_fixed_document *document,size_t page,double x,double y, const exr_control *control,exr_text_region *region, uint32_t *character,exr_error *error);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `document`：固定页文档句柄；`page`：零基页面索引；`x`：原生页面 x；屏幕点先经 viewport.inverse；`y`：原生页面 y；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`region`：接收命中四边形和字节范围；`character`：接收该区域的首个 Unicode 标量；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：返回包含该点的首个可见文字 quad/完整 UTF-8 范围及首个 Unicode 标量；无文字 EXR_NO_TEXT_LAYER，有文字但点未命中 EXR_NO_TEXT_AT_POINT；参数/读取/取消失败清空两个输出。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** region/character 为调用者值输出；不生成虚构的连字内逐字符几何。

### `exr_anchor_create`

**签名** `exr_status exr_anchor_create(const exr_document *doc, size_t start, size_t end, exr_anchor *out, exr_error *error);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `doc`：要读取的结构化文档快照；`start`：当前文档的规范化 UTF-8 起始字节边界（含）；`end`：当前文档的规范化 UTF-8 结束字节边界（不含）；`out`：接收拥有 exact/prefix/suffix/chapter 字符串的选择器（先零初始化）；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：捕获半开区间或空区间书签、至多 64 KiB 引文及每侧 32 Unicode 标量上下文；无效 UTF-8 边界/范围为 EXR_ARGUMENT，过长 EXR_LIMIT，分配失败 EXR_MEMORY。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** out 必须为空；成功的 exact/prefix/suffix/chapter 用 exr_anchor_free(out)，失败清空。

### `exr_anchor_free`

**签名** `void exr_anchor_free(exr_anchor *anchor);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `anchor`：锚点/选择器输入（见签名类型）

**返回与失败** 无返回值；NULL 可传。

**线程** 必须与对象及借用视图的全部使用串行化。

**所有权** 释放 SDK 捕获的字符串并清零结构；不要对指向字面量/借用字符串的自建输入使用此释放函数。

### `exr_anchor_resolve`

**签名** `exr_status exr_anchor_resolve(const exr_document *doc, const exr_anchor *anchor, exr_anchor_match *match, exr_error *error);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `doc`：要读取的结构化文档快照；`anchor`：锚点/选择器输入（见签名类型）；`match`：接收定位结果和 FOUND/MISSING/AMBIGUOUS/LEGACY 状态；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK 仍须检查 match.state：仅 FOUND 提供可用区间；MISSING/AMBIGUOUS/LEGACY 不猜测旧偏移附近位置。非法选择器为 EXR_ARGUMENT/EXR_ENCODING/EXR_LIMIT，内存失败 EXR_MEMORY。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** anchor 输入借用；match 为值结构，未找到的 start/end 为 SIZE_MAX。

### `exr_cfi_parse`

**签名** `exr_status exr_cfi_parse(const char *text,exr_cfi **out, exr_cfi_diagnostic *diagnostic,exr_error *error);`

**ABI** 实验；声明：[exr/document.h](../include/exr/document.h)。

**参数** `text`：NUL 结尾的 CFI 文本；`out`：接收解析后的 CFI 对象指针；用 exr_cfi_free 释放；`diagnostic`：可 NULL；接收具体错误码和输入 UTF-8 字节位置；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：解析 epubcfi(...) 或裸 scheme data，不做 URI percent 解码；语法错误 EXR_FORMAT 并设置 diagnostic，编码错误 EXR_ENCODING，大小/数字上限 EXR_LIMIT，内存失败 EXR_MEMORY；失败 *out=NULL。

**线程** 无共享可变状态；独立输入/输出可并发调用。

**所有权** 解析对象用 exr_cfi_free；text 借用本次。

### `exr_cfi_serialize`

**签名** `exr_status exr_cfi_serialize(const exr_cfi *cfi,char **out,exr_error *error);`

**ABI** 实验；声明：[exr/document.h](../include/exr/document.h)。

**参数** `cfi`：由 exr_cfi_parse 返回的解析对象；`out`：接收新分配的 NUL 结尾完整 CFI 字符串；用 exr_free 释放；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：加 epubcfi(...) 包装并保留断言、转义和参数原顺序；NULL 参数 EXR_ARGUMENT，分配失败 EXR_MEMORY，失败 *out=NULL。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** *out 用 exr_free；cfi 输入只读。

### `exr_cfi_is_range`

**签名** `int exr_cfi_is_range(const exr_cfi *cfi);`

**ABI** 实验；声明：[exr/document.h](../include/exr/document.h)。

**参数** `cfi`：由 exr_cfi_parse 返回的解析对象

**返回与失败** 返回 1 为范围，0 为点或 NULL；无失败通道。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 输入仅借用本次调用；值类型输出由调用者保存，无需释放。

### `exr_cfi_endpoints`

**签名** `exr_status exr_cfi_endpoints(const exr_cfi *cfi,char **start,char **end,exr_error *error);`

**ABI** 实验；声明：[exr/document.h](../include/exr/document.h)。

**参数** `cfi`：由 exr_cfi_parse 返回的解析对象；`start`：接收新分配的完整起点 CFI 字符串；`end`：接收新分配的完整终点 CFI 字符串；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：把公共路径 P 与端点 S/E 展开为完整 PS/PE；点产生两个相等字符串。输出地址必须不同，非法参数 EXR_ARGUMENT，分配失败 EXR_MEMORY，两输出失败清空。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** *start、*end 各自用 exr_free。

### `exr_cfi_free`

**签名** `void exr_cfi_free(exr_cfi *cfi);`

**ABI** 实验；声明：[exr/document.h](../include/exr/document.h)。

**参数** `cfi`：由 exr_cfi_parse 返回的解析对象

**返回与失败** 无返回值；NULL 可传。

**线程** 必须与对象及借用视图的全部使用串行化。

**所有权** 释放解析 CFI 及内部文本。

### `exr_document_cfi_point_at`

**签名** `exr_status exr_document_cfi_point_at(const exr_document *doc,size_t chapter,size_t offset, const exr_control *control,exr_cfi_point *out,exr_error *error);`

**ABI** 实验；声明：[exr/document.h](../include/exr/document.h)。

**参数** `doc`：要读取的结构化文档快照；`chapter`：零基文档章节索引；`offset`：章节内规范化 UTF-8 字节边界；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`out`：接收当前快照内 DOM node、原始 UTF-16 offset 和 side；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：规范化 UTF-8 边界映射为原始 DOM UTF-16 文本点；隐藏节点、UTF-8 内部或不可投影位置拒绝，返回 EXR_ARGUMENT/EXR_FORMAT；内存/取消错误透传。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** out 值结构；point.node 是当前快照节点 ID。

### `exr_document_cfi_point_offset`

**签名** `exr_status exr_document_cfi_point_offset(const exr_document *doc,size_t chapter,const exr_cfi_point *point, const exr_control *control,size_t *offset,exr_error *error);`

**ABI** 实验；声明：[exr/document.h](../include/exr/document.h)。

**参数** `doc`：要读取的结构化文档快照；`chapter`：零基文档章节索引；`point`：原始 DOM 点；TEXT offset 是 UTF-16 code units，不是 UTF-8；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`offset`：接收章节内规范化 UTF-8 字节偏移；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：DOM 点映射到章节内规范化 UTF-8 边界；原始折叠空白/元素边界按投影处理，隐藏节点、代理对内部或无投影拒绝；无效参数 EXR_ARGUMENT，不可映射 EXR_FORMAT，可取消。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** offset 为调用者值输出。

### `exr_document_cfi_path_create`

**签名** `exr_status exr_document_cfi_path_create(const exr_document *doc,size_t chapter,const exr_cfi_point *point, const exr_control *control,char **path,exr_error *error);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `doc`：要读取的结构化文档快照；`chapter`：零基文档章节索引；`point`：章节原始 DOM 点；文本 offset 用 UTF-16，element offset=SIZE_MAX 指元素本身；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`path`：接收新分配的章节内 CFI 路径字符串；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：生成内容文档路径（不含 package spine 和 epubcfi 包装）；章节须有单个 XML 根元素。非法节点/边界/范围为 EXR_ARGUMENT，DOM/格式不适用为 EXR_FORMAT，内存/取消失败透传；失败输出清空。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 新 path/cfi 字符串用 exr_free；文档输入只读。

### `exr_document_cfi_path_resolve`

**签名** `exr_status exr_document_cfi_path_resolve(const exr_document *doc,size_t chapter,const char *path, const exr_control *control,exr_cfi_point *point,exr_error *error);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `doc`：要读取的结构化文档快照；`chapter`：文档内零基章节号；`path`：内容文档 CFI 组件字符串（不是文件路径）；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`point`：接收快照内 DOM 节点与 UTF-16 点；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：解析章节内 CFI path。非法语法/路由/断言/DOM 不匹配为 EXR_FORMAT，参数/编码/限额/取消错误透传；不进行 URI percent 解码。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 输出 chapter/point 为值，不分配给调用者。

### `exr_document_cfi_create`

**签名** `exr_status exr_document_cfi_create(const exr_document *doc,size_t chapter,const exr_cfi_point *point, const exr_control *control,char **cfi,exr_error *error);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `doc`：要读取的结构化文档快照；`chapter`：零基文档章节索引；`point`：章节原始 DOM 点；文本 offset 用 UTF-16，element offset=SIZE_MAX 指元素本身；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`cfi`：接收新分配、NUL 结尾的完整 EPUB CFI 字符串；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：生成保留原 package spine 的完整点 CFI；要求完整 EPUB 快照且章节在 spine。非法节点/边界/范围为 EXR_ARGUMENT，DOM/格式不适用为 EXR_FORMAT，内存/取消失败透传；失败输出清空。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 新 path/cfi 字符串用 exr_free；文档输入只读。

### `exr_document_cfi_resolve`

**签名** `exr_status exr_document_cfi_resolve(const exr_document *doc,const char *cfi,const exr_control *control, size_t *chapter,exr_cfi_point *point,exr_error *error);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `doc`：要读取的结构化文档快照；`cfi`：NUL 结尾的完整 EPUB CFI 字符串；调用者先处理 URI percent 解码；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`chapter`：接收零基章节号；`point`：接收快照内 DOM 节点与 UTF-16 点；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：解析完整 EPUB 点 CFI；范围输入只返回起点（验证两端用 range_resolve）。非法语法/路由/断言/DOM 不匹配为 EXR_FORMAT，参数/编码/限额/取消错误透传；不进行 URI percent 解码。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 输出 chapter/point 为值，不分配给调用者。

### `exr_document_cfi_path_create_quoted`

**签名** `exr_status exr_document_cfi_path_create_quoted(const exr_document *doc,size_t chapter,const exr_cfi_point *point, size_t context_scalars,const exr_control *control,char **path,exr_error *error);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `doc`：要读取的结构化文档快照；`chapter`：零基文档章节索引；`point`：章节原始 DOM 点；文本 offset 用 UTF-16，element offset=SIZE_MAX 指元素本身；`context_scalars`：每侧原始文本上下文，1..32（仅 quoted）；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`path`：接收新分配的章节内 CFI 路径字符串；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：生成内容文档路径（不含 package spine 和 epubcfi 包装）；章节须有单个 XML 根元素。捕获每侧 1..32 原始文本 Unicode 标量断言，可唯一校正过期偏移。非法节点/边界/范围为 EXR_ARGUMENT，DOM/格式不适用为 EXR_FORMAT，内存/取消失败透传；失败输出清空。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 新 path/cfi 字符串用 exr_free；文档输入只读。

### `exr_document_cfi_create_quoted`

**签名** `exr_status exr_document_cfi_create_quoted(const exr_document *doc,size_t chapter,const exr_cfi_point *point, size_t context_scalars,const exr_control *control,char **cfi,exr_error *error);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `doc`：要读取的结构化文档快照；`chapter`：零基文档章节索引；`point`：章节原始 DOM 点；文本 offset 用 UTF-16，element offset=SIZE_MAX 指元素本身；`context_scalars`：每侧原始文本上下文，1..32（仅 quoted）；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`cfi`：接收新分配、NUL 结尾的完整 EPUB CFI 字符串；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：生成保留原 package spine 的完整点 CFI；要求完整 EPUB 快照且章节在 spine。捕获每侧 1..32 原始文本 Unicode 标量断言，可唯一校正过期偏移。非法节点/边界/范围为 EXR_ARGUMENT，DOM/格式不适用为 EXR_FORMAT，内存/取消失败透传；失败输出清空。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 新 path/cfi 字符串用 exr_free；文档输入只读。

### `exr_document_cfi_range_create`

**签名** `exr_status exr_document_cfi_range_create(const exr_document *doc,const exr_cfi_range *range, const exr_control *control,char **cfi,exr_error *error);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `doc`：要读取的结构化文档快照；`range`：start/end 章节号和原始 DOM UTF-16 端点；不是规范化 UTF-8；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`cfi`：接收新分配、NUL 结尾的完整 EPUB CFI 字符串；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：生成跨一个或多个 spine 章节的标准简单范围；端点 side 必须 0，隐含 after-start/before-end；非法范围 EXR_ARGUMENT，非完整 EPUB/路由问题 EXR_FORMAT，内存/取消错误透传。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** *cfi 用 exr_free。

### `exr_document_cfi_range_resolve`

**签名** `exr_status exr_document_cfi_range_resolve(const exr_document *doc,const char *cfi,const exr_control *control, exr_cfi_range *range,exr_error *error);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `doc`：要读取的结构化文档快照；`cfi`：NUL 结尾的完整 EPUB CFI 字符串；调用者先处理 URI percent 解码；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`range`：接收 start_chapter/end_chapter 及原始 DOM UTF-16 端点；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：验证并解析完整 EPUB 范围两端；语法、断言或 spine 路由不匹配 EXR_FORMAT，参数/编码/限额/取消错误透传。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** range 是值结构。

### `exr_anchor_resolve_ex`

**签名** `exr_status exr_anchor_resolve_ex(const exr_document *doc,const exr_anchor *anchor,const exr_control *control, exr_anchor_match *match,exr_error *error);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `doc`：要读取的结构化文档快照；`anchor`：锚点/选择器输入（见签名类型）；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`match`：接收定位结果和 FOUND/MISSING/AMBIGUOUS/LEGACY 状态；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK 仍须检查 match.state：仅 FOUND 提供可用区间；MISSING/AMBIGUOUS/LEGACY 不猜测旧偏移附近位置。非法选择器为 EXR_ARGUMENT/EXR_ENCODING/EXR_LIMIT，内存失败 EXR_MEMORY。control 可取消。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** anchor 输入借用；match 为值结构，未找到的 start/end 为 SIZE_MAX。

### `exr_text_annotation_export`

**签名** `exr_status exr_text_annotation_export(const exr_text_annotation *annotation,char **json,size_t *size,exr_error *error);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `annotation`：id、宿主资源 source、评论 text 和引文 anchor；`json`：接收新分配 UTF-8 JSON；`size`：接收 JSON 字节数；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：输出单个 plain-text body + TextQuoteSelector 的 Web Annotation JSON；缺少/非法 id/source/引文、UTF-8 或大小失败，分配失败 EXR_MEMORY。JSON 不包含 SDK 偏移或章节路径。

**线程** 无共享可变状态；独立输入/输出可并发调用。

**所有权** *json 用 exr_free；*size 为 JSON 字节数。

### `exr_text_annotation_import`

**签名** `exr_status exr_text_annotation_import(const void *json,size_t size,exr_text_annotation *annotation,exr_error *error);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `json`：长度明确的 JSON 字节输入；`size`：输入 JSON 字节数；`annotation`：接收拥有的 id/source/text/anchor；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：导入支持的紧凑 JSON profile；无效 JSON/profile/UTF-8、超限或分配失败返回非 OK。anchor.start/end=SIZE_MAX，必须在宿主选定文档/章节中 resolve。

**线程** 无共享可变状态；独立输入/输出可并发调用。

**所有权** annotation 全零输入；成功所有字段用 exr_text_annotation_free。

### `exr_text_annotation_free`

**签名** `void exr_text_annotation_free(exr_text_annotation *annotation);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `annotation`：Web Annotation 的 id/source/text/anchor 结构

**返回与失败** 无返回值；NULL 可传。

**线程** 必须与对象及借用视图的全部使用串行化。

**所有权** 释放导入结果全部字符串和选择器并清零；结构本身由调用者保存。

### `exr_anchor_from_range`

**签名** `exr_status exr_anchor_from_range(exr_publication *publication,const exr_text_range *range, const exr_control *control,exr_content_anchor *out,exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物；`range`：输入起止 part 与章节内规范化 UTF-8 offset，构成半开范围；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`out`：接收拥有 start/end 两端字符串的内容锚点（先零初始化）；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：捕获两个 endpoint（可跨 part），含稳定 ID/path、文本 FNV-1a revision/size 和点上下文；无效 part/UTF-8 边界/范围为 EXR_ARGUMENT；读取/内存/取消错误透传。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** out 全零；用 exr_content_anchor_free 释放两端字符串；宿主持久化结构字段。

### `exr_range_from_anchor`

**签名** `exr_status exr_range_from_anchor(exr_publication *publication,const exr_content_anchor *anchor, const exr_control *control,exr_text_range_match *out,exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物；`anchor`：锚点/选择器输入（见签名类型）；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`out`：接收恢复 state 与 part+UTF-8 字节范围；仅 FOUND 可用于导航；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：out.state 指示恢复状态；仅 FOUND 使用 range。同版本直接恢复精确位置，变更文本按引文重定位；MISSING/AMBIGUOUS 不退回旧偏移。非法结构/读取/内存/取消错误透传。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 输入 anchor 借用；out 是值结构。

### `exr_content_anchor_free`

**签名** `void exr_content_anchor_free(exr_content_anchor *anchor);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `anchor`：锚点/选择器输入（见签名类型）

**返回与失败** 无返回值；NULL 可传。

**线程** 必须与对象及借用视图的全部使用串行化。

**所有权** 释放两个 endpoint 的 part_id/part_path/selector 字符串并清零；只释放 SDK 所有输出。

### `exr_range_to_cfi`

**签名** `exr_status exr_range_to_cfi(exr_publication *publication,const exr_text_range *range, const exr_control *control,char **out,exr_error *error);`

**ABI** 实验；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物；`range`：输入起止 part 与章节内规范化 UTF-8 offset，构成半开范围；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`out`：接收新分配的 NUL 结尾完整 CFI 字符串；用 exr_free 释放；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：将范围转换为标准完整 EPUB CFI；仅内置 EPUB provider，其他为 EXR_UNSUPPORTED；缺失/歧义定位为 EXR_FORMAT，参数/DOM/内存/取消错误透传。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** *out 是新字符串，用 exr_free；输入不转移。

### `exr_range_from_cfi`

**签名** `exr_status exr_range_from_cfi(exr_publication *publication,const char *cfi, const exr_control *control,exr_text_range *out,exr_error *error);`

**ABI** 实验；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物；`cfi`：NUL 结尾的完整 EPUB CFI 字符串；调用者先处理 URI percent 解码；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`out`：接收 part+规范化 UTF-8 字节构成的半开范围；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：完整 EPUB CFI 转为章节内字节范围；点 CFI 成为空范围。仅内置 EPUB provider；不支持 EXR_UNSUPPORTED，语法/DOM 不匹配 EXR_FORMAT，参数/编码/内存/取消错误透传。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** out 为值结构，无需释放。

### `exr_anchor_to_cfi`

**签名** `exr_status exr_anchor_to_cfi(exr_publication *publication,const exr_content_anchor *anchor, const exr_control *control,char **out,exr_error *error);`

**ABI** 实验；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物；`anchor`：锚点/选择器输入（见签名类型）；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`out`：接收新分配的 NUL 结尾完整 CFI 字符串；用 exr_free 释放；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：将内容锚点转换为标准完整 EPUB CFI；仅内置 EPUB provider，其他为 EXR_UNSUPPORTED；缺失/歧义定位为 EXR_FORMAT，参数/DOM/内存/取消错误透传。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** *out 是新字符串，用 exr_free；输入不转移。

### `exr_anchor_from_cfi`

**签名** `exr_status exr_anchor_from_cfi(exr_publication *publication,const char *cfi, const exr_control *control,exr_content_anchor *out,exr_error *error);`

**ABI** 实验；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物；`cfi`：NUL 结尾的完整 EPUB CFI 字符串；调用者先处理 URI percent 解码；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`out`：接收拥有 start/end 两端字符串的内容锚点（先零初始化）；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：完整 EPUB CFI 转为内容锚点；点 CFI 成为空范围。仅内置 EPUB provider；不支持 EXR_UNSUPPORTED，语法/DOM 不匹配 EXR_FORMAT，参数/编码/内存/取消错误透传。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** out 全零，用 exr_content_anchor_free 释放。

### `exr_range_expand`

**签名** `exr_status exr_range_expand(exr_publication *publication,const exr_text_range *range, exr_range_unit unit,const exr_control *control,exr_text_range *out,exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物；`range`：输入起止 part 与章节内规范化 UTF-8 offset，构成半开范围；`unit`：EXR_RANGE_CHAR/WORD/SENTENCE/PARAGRAPH；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`out`：接收 part+规范化 UTF-8 字节构成的半开范围；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：按 grapheme、词、句、段向外扩展（end 排他）；空范围取右侧单元，EOF 保持空。CJK 逐字作为词，无词典分词；无效范围/单位 EXR_ARGUMENT，载入/取消错误透传。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** out 值结构；仅载入起止 part，结果可覆盖中间 part。

### `exr_publication_cfi_create`

**签名** `exr_status exr_publication_cfi_create(exr_publication *publication,size_t part,const exr_document *document, const exr_cfi_point *point,const exr_control *control,char **cfi,exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物；`part`：零基 publication 目录索引；`document`：来自该 publication/part 的独立单章节快照；`point`：快照本地 node ID 与原始 UTF-16 offset；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`cfi`：接收新分配、NUL 结尾的完整 EPUB CFI 字符串；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：从此出版物的单章节快照生成完整 EPUB 点 CFI；只支持内置 indexed EPUB，辅助 part 拒绝；参数/节点/路由不符为 EXR_ARGUMENT/EXR_FORMAT/EXR_UNSUPPORTED，内存/取消错误透传。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** document 借用；*cfi 用 exr_free。

### `exr_publication_cfi_create_quoted`

**签名** `exr_status exr_publication_cfi_create_quoted(exr_publication *publication,size_t part,const exr_document *document, const exr_cfi_point *point,size_t context_scalars,const exr_control *control,char **cfi,exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物；`part`：零基 publication 目录索引；`document`：来自该 publication/part 的独立单章节快照；`point`：快照本地 node ID 与原始 UTF-16 offset；`context_scalars`：每侧原始文本上下文，1..32；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`cfi`：接收新分配、NUL 结尾的完整 EPUB CFI 字符串；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：从此出版物的单章节快照生成完整 EPUB 点 CFI；只支持内置 indexed EPUB，辅助 part 拒绝；参数/节点/路由不符为 EXR_ARGUMENT/EXR_FORMAT/EXR_UNSUPPORTED，内存/取消错误透传。文本上下文为每侧 1..32 标量。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** document 借用；*cfi 用 exr_free。

### `exr_publication_cfi_resolve`

**签名** `exr_status exr_publication_cfi_resolve(exr_publication *publication,const char *cfi,const exr_control *control, size_t *part,exr_document **document,exr_cfi_point *point,exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物；`cfi`：NUL 结尾的完整 EPUB CFI 字符串；调用者先处理 URI percent 解码；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`part`：接收 publication part 索引；`document`：接收独立单章节文档；`point`：接收该文档内节点与 UTF-16 点；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：仅解析 CFI 指向章节，返回独立文档和本地 DOM 点；非内置 EPUB/辅助 part 或语法/路由/断言错误失败，读取/内存/取消错误透传。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** *document 用 exr_document_free；part/point 为值结构。

### `exr_pager_cfi_create`

**签名** `exr_status exr_pager_cfi_create(exr_pager *pager,const exr_cfi_point *point, size_t context_scalars,const exr_control *control,char **cfi,exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `pager`：当前页器；`point`：稳定章节本地节点 ID 与原始 DOM UTF-16 点；`context_scalars`：每侧上下文 Unicode 标量数，0..32；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`cfi`：接收新分配、NUL 结尾的完整 EPUB CFI 字符串；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：有界章节节点生成完整 CFI；context_scalars=0 无文本断言，1..32 加断言。非有界 EPUB 页器为 EXR_UNSUPPORTED，无效点/上下文 EXR_ARGUMENT，读取/DOM/取消错误透传；可能换出活动窗口。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** *cfi 用 exr_free；不得在回调重入同 pager。

### `exr_pager_cfi_resolve`

**签名** `exr_status exr_pager_cfi_resolve(exr_pager *pager,const char *cfi, const exr_control *control,exr_cfi_point *point,exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `pager`：当前页器；`cfi`：NUL 结尾的完整 EPUB CFI 字符串；调用者先处理 URI percent 解码；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`point`：接收稳定章节本地节点 ID/UTF-16 点；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：解析当前章节完整 CFI 为稳定节点点；不适配页器 EXR_UNSUPPORTED，错误章节/CFI/断言失败，读取/取消错误透传；可能换出活动窗口，不改变页面遍历。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** point 为值结构。

### `exr_pager_anchor_create`

**签名** `exr_status exr_pager_anchor_create(exr_pager *pager,size_t start,size_t end, const exr_control *control,exr_anchor *anchor,exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `pager`：当前页器；`start`：当前章节的规范化 UTF-8 起始字节边界（含）；`end`：当前章节的规范化 UTF-8 结束字节边界（不含）；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`anchor`：接收章节内选择器（输出）；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：捕获章节内规范化 UTF-8 范围引文；不支持页器 EXR_UNSUPPORTED，无效区间 EXR_ARGUMENT，过长 EXR_LIMIT；读取/分配/取消错误透传，可能换窗。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** anchor 全零输入；成功字符串用 exr_anchor_free。

### `exr_pager_anchor_resolve`

**签名** `exr_status exr_pager_anchor_resolve(exr_pager *pager,const exr_anchor *anchor, const exr_control *control,exr_anchor_match *match,exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `pager`：当前页器；`anchor`：锚点/选择器输入（见签名类型）；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`match`：接收定位结果和 FOUND/MISSING/AMBIGUOUS/LEGACY 状态；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：match.state 报告 FOUND/MISSING/AMBIGUOUS/LEGACY，只有 FOUND 可用于导航；不支持页器 EXR_UNSUPPORTED，非法选择器/读取/分配/取消失败透传；可换窗。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** anchor 借用；match 为值结构。

## 目录

读取和恢复导航目录、解析目标、建立可点击的独立目录前页。

最小调用示例：[examples/toc.c](examples/toc.c)。

<!-- example: docs/examples/toc.c -->
```c
/* SPDX-License-Identifier: MIT */
#include <exr/layout.h>
#include <stdio.h>

int main(int argc, char **argv) {
  exr_publication *publication = NULL;
  const exr_toc_entry *entries = NULL;
  size_t count = 0;
  exr_error error = {0};
  exr_status status;
  if (argc != 2) { fprintf(stderr, "usage: toc book.epub\n"); return 2; }
  status = exr_publication_open(argv[1], &publication, &error);
  if (status == EXR_OK) status = exr_publication_toc(publication, &entries, &count, &error);
  if (status == EXR_OK) {
    for (size_t i = 0; i < count; ++i)
      printf("level=%zu part=%zu %s\n", entries[i].level, entries[i].target.part, entries[i].title);
  } else fprintf(stderr, "%s\n", error.message);
  /* entries and their strings belong to publication. */
  exr_publication_free(publication);
  return status == EXR_OK ? 0 : 1;
}
```

### `exr_document_locate`

**签名** `exr_status exr_document_locate(const exr_document *document,const char *fragment, exr_location *location,exr_error *error);`

**ABI** 稳定；声明：[exr/document.h](../include/exr/document.h)。

**参数** `document`：当前单 part 的结构化文档快照；`fragment`：已解码 UTF-8 片段，不带 #；空字符串表示 part 起点；`location`：接收 part/offset/状态或章节选择器（见签名）；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：id/xml:id/a@name 的精确匹配优先，再试唯一 Unicode 大写等价；找不到锚点仍 OK、offset=0、ANCHOR_MISSING；空 fragment 为章节起点。非法参数 EXR_ARGUMENT，分配/编码错误透传。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** location 为值结构；fragment 借用。

### `exr_publication_navigation`

**签名** `exr_status exr_publication_navigation(exr_publication *publication, const exr_navigation **entries, size_t *count, exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物；`entries`：接收扁平导航树，parent 先于 child，SIZE_MAX 表示根或未解析 part；`count`：接收导航条目数；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：取得扁平导航树；EPUB 首次调用惰性解析。无效参数 EXR_ARGUMENT，解析/I/O/内存错误透传。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** *entries 是出版物借用目录，有效至 publication_free。

### `exr_publication_toc`

**签名** `exr_status exr_publication_toc(exr_publication *publication, const exr_toc_entry **entries,size_t *count,exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物；`entries`：接收 TOC 数组，含标题、level、target、source、play_order；`count`：接收TOC 条目数；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：取得惰性 TOC；优先 nav toc，再 NCX navMap，再在线性正文恢复 h1..h6/独立中文章标题（无有效链接目录或全为许可声明时）。无目录 count=0；参数/正文解析/I/O/内存错误透传。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** *entries 借用至 publication_free；恢复可能读取正文，应放宿主 worker。

### `exr_publication_resolve_href`

**签名** `exr_status exr_publication_resolve_href(const exr_publication *publication, const char *base,const char *href,char fragment[2048],exr_target *target,exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物；`base`：内容或资源的相对虚拟路径；`href`：相对内部链接 URI；`fragment`：调用者至少 2048 字节缓冲，接收解码片段；`target`：接收 part/fragment/offset；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：解析内部相对 URI；缺失/歧义 part 得 target.part=SIZE_MAX。外部/非法 URI 为 EXR_ARGUMENT；超长片段/路径与编码错误失败。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** target.fragment 借用调用者 fragment[2048]；该缓冲须活到使用 target 完成。

### `exr_publication_locate`

**签名** `exr_status exr_publication_locate(exr_publication *publication, const exr_target *target,exr_location *location,exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物；`target`：part 与片段，或 offset != SIZE_MAX 的已知文本位置；`location`：接收 part/offset/状态或章节选择器（见签名）；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：将 target 解析成章节内规范化 UTF-8 位置；缺锚点降到 part 起点并给 ANCHOR_MISSING，缺 part 给 PART_MISSING；参数/加载/DOM 错误失败。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** location 值输出；缺失目标在 publication 中去重记录。

### `exr_publication_locate_report`

**签名** `exr_locate_report exr_publication_locate_report(const exr_publication *publication);`

**ABI** 实验；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物

**返回与失败** 按值返回调用计数；NULL 返回零。total_entries 包含非 NULL publication 的失败调用；missing_anchor 同时增加 resolved_part_start；重复调用重复计数。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 输入仅借用本次调用；值类型输出由调用者保存，无需释放。

### `exr_publication_locate_report_reset`

**签名** `void exr_publication_locate_report_reset(exr_publication *publication);`

**ABI** 实验；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物

**返回与失败** 无返回值；NULL 可传。只重置计数，不清 missing_targets，不使缓存 TOC 失效。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 输入仅借用本次调用；值类型输出由调用者保存，无需释放。

### `exr_publication_missing_targets`

**签名** `const exr_target *exr_publication_missing_targets(const exr_publication *publication,size_t *count);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物；`count`：可 NULL，接收缺失目标数量

**返回与失败** 返回去重的缺失链接目标数组；NULL 返回 NULL/count=0。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** 借用到下一次 locate/target_at 或 publication_free；不要保留数组地址。

### `exr_publication_target_at`

**签名** `exr_status exr_publication_target_at(exr_publication *publication, size_t part,size_t offset,size_t *entry,exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物；`part`：零基 publication 目录索引；`offset`：part 内规范化 UTF-8 字节偏移；`entry`：接收 TOC 条目索引；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：查找阅读顺序上位于 (part,offset) 之前/此处的最后 TOC 条目，同位置取更深项；之前没有目标时 *entry=SIZE_MAX。非法 part/offset EXR_ARGUMENT；TOC/加载/定位错误透传。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** entry 为 publication_toc 数组索引，值输出；已解析位置由 publication 缓存。

### `exr_publication_footnotes`

**签名** `exr_status exr_publication_footnotes(exr_publication *publication, const exr_footnote **footnotes,size_t *count, const exr_footnote_reference **references,size_t *reference_count,exr_error *error);`

**ABI** 实验；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物；`footnotes`：接收脚注 id/label/target/text 数组；`count`：脚注条目数输出；`references`：接收正文引用范围及零基 footnote 索引；`reference_count`：引用条目数输出；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：惰性提取脚注及引用；缺失/外部链接不生成引用；无效参数 EXR_ARGUMENT，载入/解析/内存错误透传。不改变阅读顺序和正文偏移。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** footnotes/references 均借用至 publication_free；不释放。

### `exr_layout_page_kind`

**签名** `exr_page_kind exr_layout_page_kind(const exr_layout *layout, size_t page);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `layout`：待查询布局；`page`：零基页面索引

**返回与失败** 返回 EXR_PAGE_TOC 或 EXR_PAGE_BODY；普通布局、NULL 或非法页返回 BODY。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 输入仅借用本次调用；值类型输出由调用者保存，无需释放。

### `exr_publication_toc_insert_before`

**签名** `exr_status exr_publication_toc_insert_before(exr_publication *publication, size_t *part, exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物；`part`：接收插入点的 publication part 索引；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：给出合成目录应插入之前的 reading-order part；前导封面后插入，否则首个阅读 part 前；无阅读 part 为 SIZE_MAX。参数/载入错误透传。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** part 值输出；不修改出版物目录。

### `exr_toc_pages_create`

**签名** `exr_status exr_toc_pages_create(exr_publication *publication, exr_font *font, const exr_layout_config *config, const exr_toc_page_options *options, exr_layout **out, exr_error *error);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `publication`：当前分章节出版物；`font`：已打开字体集合；同一字体上的排版/渲染由宿主串行化；`config`：布局配置，含页面、CSS、图片回调、方向、control；可 NULL 使用默认；`options`：可 NULL；否则 struct_size=sizeof，labels 非 NULL 时 label_count 等于 TOC 数；title/continued_title 可 NULL 自动选择；`out`：接收独立拥有的布局指针；用 exr_layout_free 释放；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：生成独立水平目录布局，续页标题、缩进、引导点、可选右标签；无 TOC 时 *out=NULL。无效 options/label_count/尺寸为 EXR_ARGUMENT，目录/字体/排版/内存错误透传。

**线程** 同一对象的操作与销毁由宿主串行化；回调同步运行于调用线程，不得重入或销毁活动对象。

**所有权** *out 用 exr_layout_free；labels/title/continued_title 仅调用期借用；正文页号、搜索、锚点不包含此布局。

### `exr_toc_pages_label`

**签名** `const char *exr_toc_pages_label(const exr_layout *layout, size_t page);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `layout`：待查询布局；`page`：零基页面索引

**返回与失败** 返回该合成目录页罗马数字标签；非目录/非法页返回 NULL。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 借用到 layout_free 或缓存失效；不释放。

### `exr_toc_pages_entries`

**签名** `exr_status exr_toc_pages_entries(const exr_layout *layout, size_t page, size_t *first, size_t *count);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `layout`：待查询布局；`page`：零基页面索引；`first`：可 NULL，接收首条目录索引；`count`：可 NULL，接收本页条目数

**返回与失败** EXR_OK：页面包含 TOC 区间 [*first,*first+*count)；非目录或非法页 EXR_ARGUMENT（输出先清 0）。first/count 可 NULL。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 只输出索引与计数。

### `exr_toc_pages_entry_at`

**签名** `exr_status exr_toc_pages_entry_at(const exr_layout *layout, size_t page, float x, float y, size_t *entry);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `layout`：待查询布局；`page`：零基页面索引；`x`：页内布局坐标 x，原点左上；`y`：页内布局坐标 y，向下为正；`entry`：接收 publication_toc 索引

**返回与失败** EXR_OK：命中行对应 TOC 索引，标题/空白为 SIZE_MAX；非目录/非法页/缺 entry 为 EXR_ARGUMENT。x 不影响判定，同一行任意 x 都算命中。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** entry 为值输出，无分配。

### `exr_toc_pages_entry_for_offset`

**签名** `size_t exr_toc_pages_entry_for_offset(const exr_layout *layout, size_t offset);`

**ABI** 稳定；声明：[exr/layout.h](../include/exr/layout.h)。

**参数** `layout`：待查询布局；`offset`：从 layout_hit_test/hit_test 取得的目录合成文本 UTF-8 偏移

**返回与失败** 返回目录布局文字位置对应的 TOC 索引；无对应项/非目录布局为 SIZE_MAX。

**线程** 可并发读取不可变快照；调用期间不得销毁对象或其借用视图。

**所有权** 只返回值，无分配。

## 书库与持久化

用 SQLite 保存原始字节、元数据、阅读进度、三种文本注释和音频续播。

最小调用示例：[examples/library.c](examples/library.c)。

<!-- example: docs/examples/library.c -->
```c
/* SPDX-License-Identifier: MIT */
#include <exr/library.h>
#include <stdio.h>

int main(void) {
  const char text[] = "A stored book.";
  exr_library *library = NULL;
  exr_book *books = NULL;
  size_t count = 0;
  int64_t id = 0;
  exr_error error = {0};
  exr_status status = exr_library_open(":memory:", &library, &error);
  if (status == EXR_OK)
    status = exr_library_import(library, EXR_TXT, text, sizeof(text) - 1, "Example", &id, &error);
  if (status == EXR_OK) status = exr_library_books(library, NULL, &books, &count, &error);
  if (status == EXR_OK) printf("stored books=%zu\n", count);
  else fprintf(stderr, "%s\n", error.message);
  exr_books_free(books, count);
  exr_library_close(library);
  return status == EXR_OK ? 0 : 1;
}
```

### `exr_audio_checkpoint_free`

**签名** `void exr_audio_checkpoint_free(exr_audio_checkpoint *position);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `position`：由续播查询获得的拥有 track_id 的结构

**返回与失败** 无返回值；NULL 可传。

**线程** 必须与对象及借用视图的全部使用串行化。

**所有权** 释放 position.track_id 并清零；结构本身由调用者保存。

### `exr_library_audio_resume`

**签名** `exr_status exr_library_audio_resume(exr_library *library,const char *audio_id,const exr_audio_checkpoint *position,exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`audio_id`：宿主选择的非空稳定音频 ID，与源 URI/书籍 ID 无关；`position`：track_id、毫秒 offset_ms、正播放 rate；独立于书籍 ID；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：保存 audio_id 的续播位置；ID/track_id/offset/rate 无效为 EXR_ARGUMENT，编码/大小/SQLite 错误透传。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** 输入 position 只借用；SQLite 保存 track_id 副本。

### `exr_library_audio_resume_get`

**签名** `exr_status exr_library_audio_resume_get(exr_library *library,const char *audio_id,exr_audio_checkpoint *position,int *found,exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`audio_id`：宿主选择的非空稳定音频 ID，与源 URI/书籍 ID 无关；`position`：全零输出，接收续播位置；`found`：接收记录是否存在；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：读取续播；不存在 found=0、position 清零；非法 ID/编码/数据库字段或分配失败返回错误。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** position 拥有 track_id，调用 exr_audio_checkpoint_free。

### `exr_library_audio_bookmark`

**签名** `exr_status exr_library_audio_bookmark(exr_library *library,const char *audio_id,const exr_audio_bookmark *bookmark,int64_t *id,exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`audio_id`：宿主选择的非空稳定音频 ID，与源 URI/书籍 ID 无关；`bookmark`：id=0 新建，label 和 track_id/offset_ms/rate 位置；`id`：接收音频书签 ID；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：新建/更新音频书签并返回 ID；无效 audio_id/书签位置/ID 或标签、SQLite 错误失败。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** 输入 bookmark/label/track_id 借用本次；库复制保存。

### `exr_library_audio_bookmarks`

**签名** `exr_status exr_library_audio_bookmarks(exr_library *library,const char *audio_id,exr_audio_bookmark **bookmarks,size_t *count,exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`audio_id`：宿主选择的非空稳定音频 ID，与源 URI/书籍 ID 无关；`bookmarks`：接收拥有的书签数组；`count`：接收返回音频书签数；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：返回 audio_id 的书签数组（可为空）；无效 ID/库字段、内存/SQLite 错误失败。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** *bookmarks 用 exr_audio_bookmarks_free(*bookmarks,*count)。

### `exr_audio_bookmarks_free`

**签名** `void exr_audio_bookmarks_free(exr_audio_bookmark *bookmarks,size_t count);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `bookmarks`：exr_library_audio_bookmarks 返回的拥有数组；`count`：待释放数组的原始条目数，须与对应查询返回的 count 一致

**返回与失败** 无返回值；NULL/0 可传。

**线程** 必须与对象及借用视图的全部使用串行化。

**所有权** 释放书签数组以及 label/position.track_id；count 为返回条目数。

### `exr_library_remove_audio_bookmark`

**签名** `exr_status exr_library_remove_audio_bookmark(exr_library *library,int64_t id,exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`id`：音频书签 ID；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：删除指定音频书签；非法 ID EXR_ARGUMENT，SQLite 失败 EXR_DATABASE。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** 无新分配；ID 属于音频书签命名空间。

### `exr_library_clear_audio`

**签名** `exr_status exr_library_clear_audio(exr_library *library,const char *audio_id,exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`audio_id`：宿主选择的非空稳定音频 ID，与源 URI/书籍 ID 无关；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：删除 audio_id 的续播与全部音频书签；非法 ID/编码或 SQLite 错误失败。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** 不删除音频源文件；无新分配。

### `exr_library_open`

**签名** `exr_status exr_library_open(const char *path, exr_library **out, exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `path`：SQLite 数据库路径，或 :memory: 内存书库；`out`：接收打开的 SQLite 书库句柄；用 exr_library_close 释放；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：打开或创建 SQLite 书库；空/无效路径 EXR_ARGUMENT，数据库打开/迁移失败 EXR_DATABASE，分配失败 EXR_MEMORY。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** *out 用 exr_library_close；path 只借用本次。

### `exr_library_close`

**签名** `void exr_library_close(exr_library *library);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄

**返回与失败** 无返回值；NULL 可传。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** 释放书库宿主引用；仍存活的 library_source 保留数据库直至其 release。

### `exr_library_source`

**签名** `exr_status exr_library_source(exr_library *library,int64_t id,exr_source *source, exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`id`：目标书籍的数据库 ID（正整数）；`source`：接收含 size/read_at/release/context 的可寻址字节源；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：取得可寻址原始字节源，避免整本 heap 拷贝；非法参数/不存在或不匹配的 ID 为 EXR_ARGUMENT；SQLite 失败 EXR_DATABASE，结果分配失败 EXR_MEMORY。源删除、其他连接提交、底层存储错误会永久失效，后续读取失败为 EXR_IO，须重新打开。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** 成功 source.context 归调用者：调用 source.release(source.context)，或成功转交接管源的 reader；源可活过 library_close。

### `exr_library_epub_info_get`

**签名** `exr_status exr_library_epub_info_get(exr_library *library,int64_t id, exr_library_epub_info *info,exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`id`：目标书籍的数据库 ID（正整数）；`info`：输入 struct_size=sizeof；接收存储模式，source/file EPUB 通常全局文本范围未知；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：查询 EPUB bounded_storage/global_extent_known；非 EPUB EXR_FORMAT；struct_size 太短 EXR_ARGUMENT 且不写尾部，其他有效大小输出失败清空。非法参数/不存在或不匹配的 ID 为 EXR_ARGUMENT；SQLite 失败 EXR_DATABASE，结果分配失败 EXR_MEMORY。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** info 值输出，无需释放。

### `exr_epub_location_free`

**签名** `void exr_epub_location_free(exr_epub_location *location);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `location`：接收 part/offset/状态或章节选择器（见签名）

**返回与失败** 无返回值；NULL 可传。

**线程** 必须与对象及借用视图的全部使用串行化。

**所有权** 释放 location.path 和 selector 字符串并清零。

### `exr_library_epub_progress`

**签名** `exr_status exr_library_epub_progress(exr_library *library,int64_t id, const exr_epub_location *location,exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`id`：目标书籍的数据库 ID（正整数）；`location`：已由 bounded pager 捕获的 part、path、点 selector；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：保存章节内点选择器而不解析正文；要求空 exact、start=end、part/path 匹配包目录，selector.chapter 若有须等于 path；不宣称当前文本匹配。非法参数/不存在或不匹配的 ID 为 EXR_ARGUMENT；SQLite 失败 EXR_DATABASE，结果分配失败 EXR_MEMORY。非 EPUB 为 EXR_FORMAT；内存与流式 EPUB 都可保存章节位置。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** 复制 location/path/selector 到数据库；输入仍归调用者。

### `exr_library_epub_progress_get`

**签名** `exr_status exr_library_epub_progress_get(exr_library *library,int64_t id, exr_epub_location *location,int *present,exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`id`：目标书籍的数据库 ID（正整数）；`location`：全零输出，接收拥有的路径/选择器；`present`：接收是否有记录（不是 FOUND 匹配状态）；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：读取已存章节位置；无记录 present=0，存在仅表示记录存在，需 pager resolve 才能跳转；失败清空 location/present。非法参数/不存在或不匹配的 ID 为 EXR_ARGUMENT；SQLite 失败 EXR_DATABASE，结果分配失败 EXR_MEMORY。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** 输出字符串用 exr_epub_location_free；不把旧 global progress 转换为章节模式。

### `exr_library_epub_note`

**签名** `exr_status exr_library_epub_note(exr_library *library,const exr_epub_note *note, int64_t *id,exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`note`：零初始化；id=0 新建，book_id、part/path、章节内 selector、text；不能用全书偏移；`id`：接收新建或更新的记录 ID；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：新建/更新单章节 EPUB 注释并输出 ID；新建/变更范围必须提供非空引文，id>0 且 exact=NULL 仅改评论并保留旧 selector；同时检查 note/book ID。非法参数/不存在或不匹配的 ID 为 EXR_ARGUMENT；SQLite 失败 EXR_DATABASE，结果分配失败 EXR_MEMORY。不解析正文；非 EPUB 为 EXR_FORMAT；内存与流式 EPUB 都可保存章节注释。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** 输入仅借用；数据复制到 SQLite。

### `exr_library_epub_notes`

**签名** `exr_status exr_library_epub_notes(exr_library *library,int64_t book_id, exr_epub_note **notes,size_t *count,exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`book_id`：书库中已有书籍 ID；`notes`：接收新分配的注释数组；`count`：接收返回章节注释数；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：列出书籍章节注释；非法参数/不存在或不匹配的 ID 为 EXR_ARGUMENT；SQLite 失败 EXR_DATABASE，结果分配失败 EXR_MEMORY。结果中的选择器仍需 resolve，不能直接当命中。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** *notes 用 exr_epub_notes_free(*notes,*count)。

### `exr_epub_notes_free`

**签名** `void exr_epub_notes_free(exr_epub_note *notes,size_t count);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `notes`：对应查询返回的拥有注释数组；`count`：待释放数组的原始条目数，须与对应查询返回的 count 一致

**返回与失败** 无返回值；NULL/0 可传。

**线程** 必须与对象及借用视图的全部使用串行化。

**所有权** 释放 notes 数组、text、location.path 与 selector 字符串，count 为原返回数。

### `exr_library_remove_epub_note`

**签名** `exr_status exr_library_remove_epub_note(exr_library *library,int64_t id,exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`id`：EPUB 章节注释 ID；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：删除章节注释；ID 属于独立命名空间，不能传给 remove_note。非法参数 EXR_ARGUMENT；SQLite 失败 EXR_DATABASE。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** 没有新分配；数据库拥有存储记录。

### `exr_library_import`

**签名** `exr_status exr_library_import(exr_library *library, exr_format format, const void *data, size_t size, const char *title, int64_t *id, exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`format`：输入原文格式；必须与字节一致；`data`：输入格式的原始字节缓冲区，长度由 size 指定；`size`：输入 data 原始格式字节数；`title`：可选宿主标题覆盖；NULL 使用解析的标题；`id`：接收新建/复用的书籍 ID；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：导入并返回新书 ID，允许重复内容。保存原字节；重排书提取首个声明封面（至多 8 MiB），封面读取失败中止插入。解析/格式/编码/输入上限失败不插入。无效参数 EXR_ARGUMENT；I/O、内存、SQLite 失败分别 EXR_IO/EXR_MEMORY/EXR_DATABASE。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** 输入data/title本次借用；原字节复制到 SQLite。

### `exr_library_import_unique`

**签名** `exr_status exr_library_import_unique(exr_library *library,exr_format format,const void *data, size_t size,const char *title,int64_t *id,int *created,exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`format`：输入原文格式；必须与字节一致；`data`：输入格式的原始字节缓冲区，长度由 size 指定；`size`：输入 data 原始格式字节数；`title`：可选宿主标题覆盖；NULL 使用解析的标题；`id`：接收新建/复用的书籍 ID；`created`：接收 1=新建、0=复用；失败清零；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：同格式且原字节相同复用最早 ID，否则原子导入；created=1 仅表示新增，旧元数据/进度/封面/注释保留。保存原字节；重排书提取首个声明封面（至多 8 MiB），封面读取失败中止插入。解析/格式/编码/输入上限失败不插入。无效参数 EXR_ARGUMENT；I/O、内存、SQLite 失败分别 EXR_IO/EXR_MEMORY/EXR_DATABASE。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** 输入data/title本次借用；原字节复制到 SQLite。

### `exr_library_import_source`

**签名** `exr_status exr_library_import_source(exr_library *library,exr_format format,const exr_source *source, const char *title,int64_t *id,exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`format`：输入原文格式；必须与字节一致；`source`：输入可 seek 的不变源，含分块取消控制；`title`：可选宿主标题覆盖；NULL 使用解析的标题；`id`：接收新建/复用的书籍 ID；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：导入并返回新书 ID，允许重复内容。支持 EPUB/CBZ；其他格式 EXR_UNSUPPORTED。64 KiB 分块写库，EPUB 不载入 XHTML，ZIP 源限 128 MiB，author/cover 为空，全局 extent 未知；失败/取消回滚行和 blob。无效参数 EXR_ARGUMENT；I/O、内存、SQLite 失败分别 EXR_IO/EXR_MEMORY/EXR_DATABASE。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** source/context 仅本次借用，不接管或调用 release；原字节复制到数据库。

### `exr_library_import_source_unique`

**签名** `exr_status exr_library_import_source_unique(exr_library *library,exr_format format,const exr_source *source, const char *title,int64_t *id,int *created,exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`format`：输入原文格式；必须与字节一致；`source`：输入可 seek 的不变源，含分块取消控制；`title`：可选宿主标题覆盖；NULL 使用解析的标题；`id`：接收新建/复用的书籍 ID；`created`：接收 1=新建、0=复用；失败清零；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：同格式且原字节相同复用最早 ID，否则原子导入；created=1 仅表示新增，旧元数据/进度/封面/注释保留。支持 EPUB/CBZ；其他格式 EXR_UNSUPPORTED。64 KiB 分块写库，EPUB 不载入 XHTML，ZIP 源限 128 MiB，author/cover 为空，全局 extent 未知；失败/取消回滚行和 blob。无效参数 EXR_ARGUMENT；I/O、内存、SQLite 失败分别 EXR_IO/EXR_MEMORY/EXR_DATABASE。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** source/context 仅本次借用，不接管或调用 release；原字节复制到数据库。

### `exr_library_import_file`

**签名** `exr_status exr_library_import_file(exr_library *library,exr_format format,const char *path, const char *title,int64_t *id,exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`format`：输入原文格式；必须与字节一致；`path`：输入出版物的 UTF-8 文件路径；`title`：可选宿主标题覆盖；NULL 使用解析的标题；`id`：接收新建/复用的书籍 ID；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：导入并返回新书 ID，允许重复内容。支持 EPUB/CBZ，文件路径另支持 PDF（只读映射元数据）；其他格式 EXR_UNSUPPORTED。64 KiB 分块写库，EPUB 不载入 XHTML，ZIP 源限 128 MiB，author/cover 为空，全局 extent 未知；失败/取消回滚行和 blob。无效参数 EXR_ARGUMENT；I/O、内存、SQLite 失败分别 EXR_IO/EXR_MEMORY/EXR_DATABASE。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** 输入文件路径本次借用；原字节复制到 SQLite。

### `exr_library_import_file_unique`

**签名** `exr_status exr_library_import_file_unique(exr_library *library,exr_format format,const char *path, const char *title,int64_t *id,int *created,exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`format`：输入原文格式；必须与字节一致；`path`：输入出版物的 UTF-8 文件路径；`title`：可选宿主标题覆盖；NULL 使用解析的标题；`id`：接收新建/复用的书籍 ID；`created`：接收 1=新建、0=复用；失败清零；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：同格式且原字节相同复用最早 ID，否则原子导入；created=1 仅表示新增，旧元数据/进度/封面/注释保留。支持 EPUB/CBZ，文件路径另支持 PDF（只读映射元数据）；其他格式 EXR_UNSUPPORTED。64 KiB 分块写库，EPUB 不载入 XHTML，ZIP 源限 128 MiB，author/cover 为空，全局 extent 未知；失败/取消回滚行和 blob。无效参数 EXR_ARGUMENT；I/O、内存、SQLite 失败分别 EXR_IO/EXR_MEMORY/EXR_DATABASE。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** 输入文件路径本次借用；原字节复制到 SQLite。

### `exr_library_fixed_source`

**签名** `exr_status exr_library_fixed_source(exr_library *library,int64_t id,const exr_fixed_open_options *options, exr_fixed_document **out,exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`id`：目标书籍的数据库 ID（正整数）；`options`：可 NULL；固定页打开选项（密码/control 等）；`out`：接收独立拥有的固定页文档指针；用 exr_fixed_free 释放；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：打开所存 PDF/CBZ 固定页文档；不支持的格式/流式路径为 EXR_UNSUPPORTED，书不存在 EXR_ARGUMENT；I/O/内存/解析/密码错误透传。CBZ 按需读取 library_source；PDF 原字节进入匿名映射而不是整本 heap buffer；删除书或其他连接提交使源失效。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** *out 用 exr_fixed_free；源保留数据库 owner，可活过 library_close。

### `exr_library_books`

**签名** `exr_status exr_library_books(exr_library *library, const char *query, exr_book **books, size_t *count, exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`query`：元数据子串查询，不是正文全文搜索；`books`：接收拥有的 exr_book 数组；`count`：接收返回书籍数；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：按 title/author/tags 子串匹配，ID 降序返回；query=NULL/空串列全库，LIKE 通配字符按字面匹配；query>4096 字节 EXR_LIMIT。非法参数/不存在或不匹配的 ID 为 EXR_ARGUMENT；SQLite 失败 EXR_DATABASE，结果分配失败 EXR_MEMORY。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** *books 用 exr_books_free(*books,*count)。

### `exr_books_free`

**签名** `void exr_books_free(exr_book *books, size_t count);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `books`：exr_library_books 返回的拥有数组；`count`：待释放数组的原始条目数，须与对应查询返回的 count 一致

**返回与失败** 无返回值；NULL/0 可传。

**线程** 必须与对象及借用视图的全部使用串行化。

**所有权** 释放 books 数组及每条 title/author/tags；count 为原返回数。

### `exr_library_update`

**签名** `exr_status exr_library_update(exr_library *library, const exr_book *book, exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`book`：含已有 id；重排 position 为全书 UTF-8 字节，PDF/CBZ 为零基页进度；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：更新标题、作者、tags、favorite、status 和 position；title 非空、favorite=0/1、status=0..2、position 不超过 extent。bounded EPUB 不允许非零全书 position（EXR_UNSUPPORTED）；非法参数/不存在或不匹配的 ID 为 EXR_ARGUMENT；SQLite 失败 EXR_DATABASE，结果分配失败 EXR_MEMORY。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** 输入 book 及字符串借用本次；SQLite 保存副本。

### `exr_library_document`

**签名** `exr_status exr_library_document(exr_library *library, int64_t id, exr_document **doc, exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`id`：目标书籍的数据库 ID（正整数）；`doc`：接收新文档输出；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：解析所存重排书为独立快照；固定页格式需 fixed API；此旧接口会对 bounded EPUB 取整块原文并尝试全量解析（不提供有界读取保证）；缺书、数据库、解析、编码、大小或内存错误透传。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** *doc 用 exr_document_free。

### `exr_library_fixed`

**签名** `exr_status exr_library_fixed(exr_library *library,int64_t id,const exr_fixed_open_options *options, exr_fixed_document **out,exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`id`：目标书籍的数据库 ID（正整数）；`options`：可 NULL；固定页打开选项（密码/control 等）；`out`：接收独立拥有的固定页文档指针；用 exr_fixed_free 释放；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：打开所存 PDF/CBZ 固定页文档；不支持的格式/流式路径为 EXR_UNSUPPORTED，书不存在 EXR_ARGUMENT；I/O/内存/解析/密码错误透传。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** *out 用 exr_fixed_free；读者持有所需独立原始数据。

### `exr_library_fixed_note`

**签名** `exr_status exr_library_fixed_note(exr_library *library,const exr_fixed_note *note,const exr_control *control, int64_t *id,exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`note`：id=0 新建；book_id、零基 page、该页 UTF-8 [start,end)、text；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`id`：接收新建或更新的记录 ID；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：保存固定页注释并捕获存储原文的页文字锚点；页号/文本范围/书与注释 ID 不符 EXR_ARGUMENT，非固定格式 EXR_FORMAT，无文本/读取/取消/数据库错误透传。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** 输入 note 本次借用；SQLite 拷贝评论与选择器。

### `exr_library_fixed_notes`

**签名** `exr_status exr_library_fixed_notes(exr_library *library,int64_t book_id,exr_fixed_note **notes, size_t *count,exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`book_id`：书库中已有书籍 ID；`notes`：接收新分配的注释数组；`count`：接收返回固定页注释数；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：读取固定页注释；非法参数/不存在或不匹配的 ID 为 EXR_ARGUMENT；SQLite 失败 EXR_DATABASE，结果分配失败 EXR_MEMORY。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** *notes 用 exr_fixed_notes_free(*notes,*count)。

### `exr_fixed_notes_free`

**签名** `void exr_fixed_notes_free(exr_fixed_note *notes,size_t count);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `notes`：对应查询返回的拥有注释数组；`count`：待释放数组的原始条目数，须与对应查询返回的 count 一致

**返回与失败** 无返回值；NULL/0 可传。

**线程** 必须与对象及借用视图的全部使用串行化。

**所有权** 释放数组、评论及每条 fixed_anchor 字符串。

### `exr_library_remove_fixed_note`

**签名** `exr_status exr_library_remove_fixed_note(exr_library *library,int64_t id,exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`id`：固定页注释 ID；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：删除固定页注释；非法 ID EXR_ARGUMENT，SQLite 失败 EXR_DATABASE。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** 没有新分配；使用固定页独立 ID 命名空间。

### `exr_library_cover`

**签名** `exr_status exr_library_cover(exr_library *library, int64_t id, const void *data, size_t size, exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`id`：目标书籍的数据库 ID（正整数）；`data`：编码后的封面图像字节；NULL/0 清空；`size`：封面编码字节数；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：保存/替换封面 blob；无效参数或缺书 EXR_ARGUMENT，超过 8 MiB 同样 EXR_ARGUMENT，SQLite 失败 EXR_DATABASE。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** data 仅本次借用并复制到 SQLite。

### `exr_library_note`

**签名** `exr_status exr_library_note(exr_library *library, const exr_note *note, int64_t *id, exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`note`：零初始化；id=0 新建，book_id、全书 UTF-8 [start,end)、text 和可选 anchor；`id`：接收新建或更新的记录 ID；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：新建/更新全书重排注释，新建/改区间从存储原文捕获 selector；仅改评论保留旧 selector，anchor.exact 非 NULL 表示显式替换且 range 必须一致。非法参数/不存在或不匹配的 ID 为 EXR_ARGUMENT；SQLite 失败 EXR_DATABASE，结果分配失败 EXR_MEMORY。固定页 EXR_FORMAT；bounded EPUB EXR_UNSUPPORTED；解析/编码/限额错误透传。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** note 及 selector 本次借用，SQLite 复制；id 返回已写记录 ID。

### `exr_library_notes`

**签名** `exr_status exr_library_notes(exr_library *library, int64_t book_id, exr_note **notes, size_t *count, exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`book_id`：书库中已有书籍 ID；`notes`：接收新分配的注释数组；`count`：接收返回全书重排注释数；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：读取重排注释数组；非法参数/不存在或不匹配的 ID 为 EXR_ARGUMENT；SQLite 失败 EXR_DATABASE，结果分配失败 EXR_MEMORY。bounded EPUB 使用 epub_notes。未解决的范围为 SIZE_MAX，不应画高亮。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** *notes 用 exr_notes_free(*notes,*count)。

### `exr_library_note_text`

**签名** `exr_status exr_library_note_text(exr_library *library,int64_t note_id,const char *text,exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`note_id`：全书重排注释 ID；`text`：UTF-8 评论正文；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：只更新评论，允许当前范围未解决；无效 text/ID 为 EXR_ARGUMENT，UTF-8/大小校验及 SQLite 失败透传。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** text 仅本次借用，SQLite 复制；旧 selector 不变。

### `exr_notes_free`

**签名** `void exr_notes_free(exr_note *notes, size_t count);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `notes`：对应查询返回的拥有注释数组；`count`：待释放数组的原始条目数，须与对应查询返回的 count 一致

**返回与失败** 无返回值；NULL/0 可传。

**线程** 必须与对象及借用视图的全部使用串行化。

**所有权** 释放数组、评论和每条 anchor 字符串；count 必须是原返回数。

### `exr_library_progress`

**签名** `exr_status exr_library_progress(exr_library *library,int64_t book_id,const exr_anchor *point,exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`book_id`：书库中已有书籍 ID；`point`：宿主用当前文档 anchor_create 捕获的全书点选择器；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：原子保存全书重排 position/点选择器，不重新解析原文；要求 point 是空 exact 且 start=end 的有效点。固定页 EXR_FORMAT、bounded EPUB EXR_UNSUPPORTED；非法范围/选择器或 SQLite 错误失败。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** 输入 point 借用，字段复制入库。

### `exr_library_progress_get`

**签名** `exr_status exr_library_progress_get(exr_library *library,int64_t book_id,exr_anchor *point,exr_anchor_state *state,exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`book_id`：书库中已有书籍 ID；`point`：接收全书点选择器；`state`：接收已存状态，LEGACY 表示只有旧数字位置；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：读取选择器和已存 state；无 selector 时返回 LEGACY 和数字位置；这不是对当前修订重新 resolve。固定页 EXR_FORMAT、bounded EPUB EXR_UNSUPPORTED；缺书/非法库字段/分配/数据库错误透传。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** point 全零，拥有的字符串用 exr_anchor_free。

### `exr_library_clear_progress`

**签名** `exr_status exr_library_clear_progress(exr_library *library,int64_t book_id,exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`book_id`：书库中已有书籍 ID；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：移除全书选择器、保留数字 book.position；非法参数/ID EXR_ARGUMENT，bounded EPUB EXR_UNSUPPORTED，SQLite 失败 EXR_DATABASE。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** 没有新分配；不删除书或注释。

### `exr_library_blob`

**签名** `exr_status exr_library_blob(exr_library *library, int64_t id, int cover, void **data, size_t *size, exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`id`：目标书籍的数据库 ID（正整数）；`cover`：0 原文，非零封面；`data`：接收拥有的二进制副本；`size`：接收 blob 字节数；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：复制原文或封面 blob；空 blob 返回 data=NULL/size=0；缺书 EXR_ARGUMENT，原文超整块上限 EXR_LIMIT，数据库/分配失败透传。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** *data 用 exr_free；大书原文优先 library_source。

### `exr_library_remove_note`

**签名** `exr_status exr_library_remove_note(exr_library *library, int64_t id, exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`id`：全书重排 note ID；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：删除全书重排注释；非法 ID EXR_ARGUMENT，SQLite 失败 EXR_DATABASE。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** 没有新分配；不接受 EPUB 章节/固定页/音频注释 ID。

### `exr_library_reanchor`

**签名** `exr_status exr_library_reanchor(exr_library *library,int64_t book_id,size_t fallback_position, const exr_control *control,exr_library_relocation *report,exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`book_id`：书库中已有书籍 ID；`fallback_position`：进度无法重定位时宿主指定的有效 UTF-8 边界位置；`control`：可 NULL，同步取消/进度回调；context 借用，回调不得重入活动对象；`report`：接收旧/新大小与进度、每条注释 relocation；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：重解析存储原文并原子更新 extent/进度/注释位置；唯一匹配移动，缺失/歧义注释保留评论/selector、范围 SIZE_MAX。非法 fallback/书/模式、解析、内存、取消、SQLite 错误回滚。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** report 全零，成功拥有 notes 数组，用 exr_library_relocation_free。

### `exr_library_relocation_free`

**签名** `void exr_library_relocation_free(exr_library_relocation *report);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `report`：查询/重定位报告输出或待释放报告

**返回与失败** 无返回值；NULL 可传。

**线程** 必须与对象及借用视图的全部使用串行化。

**所有权** 释放 report.notes 并清零；report 结构仍归调用者。

### `exr_library_backup`

**签名** `exr_status exr_library_backup(exr_library *library, const char *path, exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`path`：备份目标 SQLite 文件路径；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：SQLite backup 到指定路径；无效参数 EXR_ARGUMENT，目标打开/复制失败 EXR_DATABASE。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** path 只借用；目标数据库文件由宿主管理。

### `exr_library_delete`

**签名** `exr_status exr_library_delete(exr_library *library, int64_t id, exr_error *error);`

**ABI** 稳定；声明：[exr/library.h](../include/exr/library.h)。

**参数** `library`：已打开的 SQLite 书库句柄；`id`：要删除的书籍 ID；`error`：可 NULL，接收 exr_status 和 UTF-8 错误说明

**返回与失败** EXR_OK：删除书籍及关联记录；无效 ID EXR_ARGUMENT，SQLite 失败 EXR_DATABASE。所属 owner 的已有源永久失效，即使后来 ID 被重用。

**线程** 同一 library 及其 source 的使用、关闭由宿主串行化；不要从 source/control 回调重入所属数据库。

**所有权** 数据库删除存储记录；仍需照常释放已打开 source/reader 句柄。


## 格式与转换

打开流式格式、扫描 TXT、访问归档与资源，并导出正文或保留结构的资源包。

最小可编译示例：[formats.c](examples/formats.c)。

<!-- example: docs/examples/formats.c -->
```c
/* SPDX-License-Identifier: MIT */
#include <exr/formats.h>
#include <exr/opds.h>
#include <string.h>
#include <stdio.h>

int main(void) {
  const char html[] = "<html><body><h1>Chapter</h1><p>Hello.</p></body></html>";
  exr_document *document = NULL;
  exr_error error = {0};
  exr_status status = exr_document_open_memory(EXR_HTML, html, sizeof(html) - 1,
                                               &document, &error);
  if (status == EXR_OK)
    printf("format=%d\n", (int)exr_document_format(document));
  else
    fprintf(stderr, "%s\n", error.message);
  exr_document_free(document);
  if (status != EXR_OK) return 1;
  const char atom[] = "<feed xmlns='http://www.w3.org/2005/Atom'><title>Catalog</title>"
    "<entry><title>Example</title><link rel='http://opds-spec.org/acquisition' "
    "type='application/epub+zip' href='../books/a.epub'/></entry></feed>";
  exr_opds_feed feed = {0};
  status = exr_opds_parse(atom, sizeof(atom) - 1, "https://example.test/catalog/root.xml", &feed, &error);
  int catalog_ok = status == EXR_OK && feed.entry_count == 1 && feed.entries[0].download_url &&
    !strcmp(feed.entries[0].download_url, "https://example.test/books/a.epub");
  if (catalog_ok) printf("OPDS entries=%zu title=%s\n", feed.entry_count, feed.title);
  else fprintf(stderr, "OPDS parse failed: %s\n", error.message);
  exr_opds_feed_free(&feed);
  return catalog_ok ? 0 : 1;
}
```

### `exr_sevenz_options_defaults`

**签名** `exr_sevenz_options exr_sevenz_options_defaults(void);`

**ABI** 实验。声明：[formats.h](../include/exr/formats.h)。

**参数** 无。

**返回与失败** 返回含 struct_size 的默认选项：解码阶段 128 MiB、头部 16 MiB；无失败。

**线程** 无共享可变状态，可并发。

**所有权** 值返回，无需释放。

### `exr_sevenz_open`

**签名** `exr_status exr_sevenz_open(const char *path,const exr_sevenz_options *options, exr_sevenz **out,exr_error *error);`

**ABI** 实验。声明：[formats.h](../include/exr/formats.h)。

**参数** `path`：UTF-8 文件路径；`options`：可选限额，NULL 用默认；非 NULL 初始化 struct_size；`out`：接收归档，失败为 NULL；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 得到只读 7Z；ARGUMENT 为无效参数/选项，IO 为读取失败，FORMAT 为损坏/危险路径/CRC，UNSUPPORTED 为加密、多输入编码器或外部表，LIMIT 为预算超限；也可 MEMORY/CANCELLED。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** 成功结果由 exr_sevenz_free 释放。path/options 仅调用期间借用。

### `exr_sevenz_open_source`

**签名** `exr_status exr_sevenz_open_source(const exr_source *source,const exr_sevenz_options *options, exr_sevenz **out,exr_error *error);`

**ABI** 实验。声明：[formats.h](../include/exr/formats.h)。

**参数** `source`：不可变随机读取源（size/read_at/context/release/control）；`options`：可选限额，NULL 用默认；非 NULL 初始化 struct_size；`out`：接收归档，失败为 NULL；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 得到只读 7Z；ARGUMENT 为无效参数/选项，IO 为读取失败，FORMAT 为损坏/危险路径/CRC，UNSUPPORTED 为加密、多输入编码器或外部表，LIMIT 为预算超限；也可 MEMORY/CANCELLED。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** 成功结果由 exr_sevenz_free 释放。source.context 仅成功时转移，关闭时调用 release；失败仍归宿主。

### `exr_sevenz_entries`

**签名** `const exr_sevenz_entry *exr_sevenz_entries(const exr_sevenz *archive,size_t *count);`

**ABI** 实验。声明：[formats.h](../include/exr/formats.h)。

**参数** `archive`：已打开的归档；`count`：可选接收条目数。

**返回与失败** 返回条目数组；NULL 归档返回 NULL/count=0；不执行解压。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 借用数组与 path 到 exr_sevenz_free；不可单独释放。

### `exr_sevenz_extract`

**签名** `exr_status exr_sevenz_extract(exr_sevenz *archive,size_t index, void **data,size_t *size,exr_error *error);`

**ABI** 实验。声明：[formats.h](../include/exr/formats.h)。

**参数** `archive`：已打开的 7Z 归档；`index`：entries 数组中的零基文件索引；`data`：接收独立解压字节；`size`：接收字节数；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 返回文件字节；越界/目录索引 ARGUMENT，预算 LIMIT，不支持编码 UNSUPPORTED，损坏/CRC FORMAT，读取 IO；可 MEMORY/CANCELLED。固实块每次完整解码。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 成功 data 用 exr_free；失败 data=NULL、size=0；归档继续由调用方持有。

### `exr_sevenz_free`

**签名** `void exr_sevenz_free(exr_sevenz *archive);`

**ABI** 实验。声明：[formats.h](../include/exr/formats.h)。

**参数** `archive`：待关闭归档，可 NULL。

**返回与失败** 无返回值；NULL 无操作。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 消费 archive，释放条目、解码状态及成功接管的 source.context。

### `exr_txt_scan_source`

**签名** `exr_status exr_txt_scan_source(const exr_source *source,exr_txt_paragraph_fn paragraph, void *context,uint64_t *extent,exr_error *error);`

**ABI** 稳定。声明：[formats.h](../include/exr/formats.h)。

**参数** `source`：不可变随机读取源（size/read_at/context/release/control）；`paragraph`：每段的同步回调；接收全书规范化 UTF-8 字节偏移；`context`：原样传入 paragraph 的宿主上下文；`extent`：接收规范化正文总字节数；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 扫描全部规范化正文并写 extent；ENCODING 为无效 UTF-8/UTF-16，单段（含空白）超过 64 KiB 为 LIMIT；另有 IO/MEMORY/CANCELLED/回调错误。失败 extent=0，已投递段落不回滚。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** source/context 保留宿主所有权；paragraph 收到的去首尾空白非空段只在回调内有效，段间投影为一个 LF。

### `exr_txt_cursor_create`

**签名** `exr_status exr_txt_cursor_create(const exr_source *source,exr_txt_cursor **out,exr_error *error);`

**ABI** 稳定。声明：[formats.h](../include/exr/formats.h)。

**参数** `source`：不可变随机读取源（size/read_at/context/release/control）；`out`：接收游标，失败 NULL；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 创建游标；参数缺失 ARGUMENT，来源读取 IO、分配 MEMORY、取消 CANCELLED；成功不代表后续正文编码全部有效。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** 游标由 exr_txt_cursor_free 释放；仅复制 source 描述符，来源及 context 须不可变且比游标活得久，不转移 release。

### `exr_txt_cursor_next`

**签名** `exr_status exr_txt_cursor_next(exr_txt_cursor *cursor,uint64_t *offset, const char **text,size_t *size,exr_error *error);`

**ABI** 稳定。声明：[formats.h](../include/exr/formats.h)。

**参数** `cursor`：TXT 投影游标；`offset`：接收段首全书规范化 UTF-8 字节偏移；`text`：接收段落视图，使用 size 而非假定 NUL 结尾；`size`：接收段落字节数；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 给下一非空段；EOF 同样 OK 且 text=NULL、size=0。无效/已失败游标 ARGUMENT；编码 ENCODING、段超限 LIMIT、IO/MEMORY/CANCELLED。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** text 借用至下次游标操作；不要释放。

### `exr_txt_cursor_checkpoint`

**签名** `exr_status exr_txt_cursor_checkpoint(const exr_txt_cursor *cursor,exr_txt_checkpoint *checkpoint,exr_error *error);`

**ABI** 稳定。声明：[formats.h](../include/exr/formats.h)。

**参数** `cursor`：TXT 投影游标；`checkpoint`：接收源位置、投影位置、编码和 CR 状态；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 复制恢复点；空指针或失败游标 ARGUMENT。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** checkpoint 为调用方值对象，不含需释放内存。

### `exr_txt_cursor_restore`

**签名** `exr_status exr_txt_cursor_restore(exr_txt_cursor *cursor,const exr_txt_checkpoint *checkpoint,exr_error *error);`

**ABI** 稳定。声明：[formats.h](../include/exr/formats.h)。

**参数** `cursor`：TXT 投影游标；`checkpoint`：由同源 cursor_checkpoint 取得的恢复点；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 恢复并清除结束/失败状态；源偏移越界、编码不匹配或无效状态 ARGUMENT。只能使用同一不可变来源、已返回段落边界的检查点。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 借用 checkpoint；此前 text 视图失效。

### `exr_txt_cursor_free`

**签名** `void exr_txt_cursor_free(exr_txt_cursor *cursor);`

**ABI** 稳定。声明：[formats.h](../include/exr/formats.h)。

**参数** `cursor`：TXT 投影游标。

**返回与失败** 无返回值；NULL 无操作。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 释放游标与段缓存，不释放 source.context。

### `exr_txt_find_source`

**签名** `exr_status exr_txt_find_source(const exr_source *source,const char *query,uint64_t from, uint64_t *start,uint64_t *end,exr_error *error);`

**ABI** 稳定。声明：[formats.h](../include/exr/formats.h)。

**参数** `source`：不可变随机读取源（size/read_at/context/release/control）；`query`：NUL 结尾的精确 UTF-8 查询，可跨规范化段间 LF；`from`：全书规范化 UTF-8 起始字节偏移；`start`：接收匹配起始字节偏移；`end`：接收匹配末尾后一字节偏移；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK；无匹配 start=end=UINT64_MAX。from 越界/空查询 ARGUMENT；查询临时空间超过 4 MiB 或段超过 64 KiB 为 LIMIT；可 ENCODING/IO/MEMORY/CANCELLED。即使命中仍校验完整来源。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** 所有输入借用；start/end 为调用方数值输出。

### `exr_txt_anchor_create_source`

**签名** `exr_status exr_txt_anchor_create_source(const exr_source *source,size_t start,size_t end, exr_anchor *anchor,exr_error *error);`

**ABI** 稳定。声明：[formats.h](../include/exr/formats.h)。

**参数** `source`：不可变随机读取源（size/read_at/context/release/control）；`start`：全书规范化 UTF-8 起始字节偏移；`end`：半开范围末尾字节偏移；`anchor`：接收 quote 与两侧最多 32 scalar 上下文；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 生成 TextQuote 选择器；无效范围/UTF-8 边界 ARGUMENT，quote 超过 64 KiB/段预算 LIMIT；也可 ENCODING/IO/MEMORY/CANCELLED。完整验证来源。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** 成功 anchor 中的 quote/prefix/suffix 用 exr_anchor_free；source 仍属宿主。宿主另存原始文件身份。

### `exr_txt_anchor_resolve_source`

**签名** `exr_status exr_txt_anchor_resolve_source(const exr_source *source,const exr_anchor *anchor, exr_anchor_match *match,exr_error *error);`

**ABI** 稳定。声明：[formats.h](../include/exr/formats.h)。

**参数** `source`：不可变随机读取源（size/read_at/context/release/control）；`anchor`：已持久化的偏移、quote/prefix/suffix 选择器；`match`：接收位置、匹配等级与歧义信息；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 给匹配等级与位置，未匹配/歧义见 match 而非把 OK 当唯一命中；无效选择器 ARGUMENT/LIMIT，来源 ENCODING/IO，另有 MEMORY/CANCELLED。排序与 exr_anchor_resolve_ex 一致。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** 借用来源与 anchor；match 为值输出，无需释放。

### `exr_metadata_read_xmp`

**签名** `exr_status exr_metadata_read_xmp(const void *data,size_t size,const exr_control *control, exr_metadata_entry **entries,size_t *count,exr_error *error);`

**ABI** 稳定。声明：[formats.h](../include/exr/formats.h)。

**参数** `data`：输入文件/资源字节，至少 size 字节；`size`：输入字节长度；`control`：可 NULL；同步进度/协作取消回调与宿主上下文；`entries`：接收元数据条目数组；`count`：接收条目数；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 给文档主体的简单 RDF 属性、Seq/Bag 和首选 Alt；无效参数 ARGUMENT，XML/结构 FORMAT，预算 LIMIT，另有 MEMORY/CANCELLED。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** entries 为独立快照，使用 exr_metadata_free(entries,count)。

### `exr_epub_metadata_write`

**签名** `exr_status exr_epub_metadata_write(const void *data,size_t size, const exr_metadata_entry *changes,size_t count,const exr_epub_cover *cover, const exr_control *control,void **out,size_t *out_size,exr_error *error);`

**ABI** 稳定。声明：[formats.h](../include/exr/formats.h)。

**参数** `data`：输入文件/资源字节，至少 size 字节；`size`：输入字节长度；`changes`：以完整 dcterms URI 为键的替换/删除项，NULL value 删除可选属性；`count`：changes 条目数；`cover`：可选 PNG/JPEG 封面及 media_type；初始化 struct_size；`control`：可 NULL；同步进度/协作取消回调与宿主上下文；`out`：接收完整包字节；`out_size`：接收字节数；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 输出完整 EPUB 副本（无变化也复制）；无效字段/必填 title、language 删除 ARGUMENT，损坏包 FORMAT，签名/权限控制/标识符修改及加密封面 UNSUPPORTED；另有 LIMIT/MEMORY/CANCELLED。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** 输入全借用；out 用 exr_free。替换保留章节/资源原字节；NULL cover 不改，零数据 cover 仅清除封面指定。

### `exr_document_open`

**签名** `exr_status exr_document_open(const char *path, exr_document **out, exr_error *error);`

**ABI** 稳定。声明：[formats.h](../include/exr/formats.h)。

**参数** `path`：UTF-8 文件路径；`out`：接收独立文档；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 返回含支持正文的文档；无效参数 ARGUMENT，编码 ENCODING，未知格式/空正文/损坏 FORMAT，输入或资源超限 LIMIT，分配 MEMORY，文件读取 IO。按扩展名选择解析器。 PDF/CBZ 阅读使用 fixed_open；此入口不是固定页渲染器。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** 输入仅借用，成功文档用 exr_document_free；有效 path/out 后失败 *out=NULL；调用前置零。

### `exr_document_open_memory`

**签名** `exr_status exr_document_open_memory(exr_format format, const void *data, size_t size, exr_document **out, exr_error *error);`

**ABI** 稳定。声明：[formats.h](../include/exr/formats.h)。

**参数** `format`：EXR_TXT/HTML/FB2/EPUB/DOCX/RTF/MOBI 等正文格式；`data`：输入文件/资源字节，至少 size 字节；`size`：输入字节长度；`out`：接收独立文档；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 返回含支持正文的文档；无效参数 ARGUMENT，编码 ENCODING，未知格式/空正文/损坏 FORMAT，输入或资源超限 LIMIT，分配 MEMORY。必须显式指定 format。 PDF/CBZ 阅读使用 fixed_open；此入口不是固定页渲染器。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** 输入仅借用，成功文档用 exr_document_free；out 非 NULL 时失败 *out=NULL；调用前置零。

### `exr_epub_validate`

**签名** `exr_status exr_epub_validate(const char *path, exr_error *error);`

**ABI** 稳定。声明：[formats.h](../include/exr/formats.h)。

**参数** `path`：UTF-8 文件路径；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 通过严格 OCF 结构检查；FORMAT 指首个 stored mimetype、唯一成员、目录/本地头/CRC、container/OPF/spine 或资源路径不符；另有 ARGUMENT/IO/MEMORY/LIMIT。不是完整 EPUB 内容规范或渲染符合性认证。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** 输入借用，无持久结果，无需释放。

### `exr_epub_validate_memory`

**签名** `exr_status exr_epub_validate_memory(const void *data, size_t size, exr_error *error);`

**ABI** 稳定。声明：[formats.h](../include/exr/formats.h)。

**参数** `data`：输入文件/资源字节，至少 size 字节；`size`：输入字节长度；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 通过严格 OCF 结构检查；FORMAT 指首个 stored mimetype、唯一成员、目录/本地头/CRC、container/OPF/spine 或资源路径不符；另有 ARGUMENT/IO/MEMORY/LIMIT。不是完整 EPUB 内容规范或渲染符合性认证。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** 输入借用，无持久结果，无需释放。

### `exr_document_navigation`

**签名** `exr_status exr_document_navigation(const exr_document *doc, exr_navigation **entries, size_t *count, exr_error *error);`

**ABI** 稳定。声明：[formats.h](../include/exr/formats.h)。

**参数** `doc`：已打开的文档；`entries`：接收导航节点数组；`count`：接收节点数；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 给作者 nav/NCX 快照；没有导航时为空数组。参数 ARGUMENT，解析 FORMAT，分配 MEMORY，预算 LIMIT。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** entries 独立于 doc 寿命，用 exr_navigation_free(entries,count)。

### `exr_navigation_free`

**签名** `void exr_navigation_free(exr_navigation *entries, size_t count);`

**ABI** 稳定。声明：[formats.h](../include/exr/formats.h)。

**参数** `entries`：navigation 返回的数组；`count`：原条目数。

**返回与失败** 无返回值；释放完整快照，NULL 可用。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 消费 entries 及其字符串；count 必须是返回的数量。

### `exr_document_resource`

**签名** `exr_status exr_document_resource(const exr_document *doc, size_t resource, void **data, size_t *size, exr_error *error);`

**ABI** 稳定。声明：[formats.h](../include/exr/formats.h)。

**参数** `doc`：已打开的文档；`resource`：资源目录的零基索引；`data`：接收资源字节；`size`：接收字节数；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 复制嵌入资源；无效资源索引 ARGUMENT，缺失/损坏 FORMAT，读取 IO、预算 LIMIT、分配 MEMORY。无网络读取。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** data 是独立副本，用 exr_free；doc 保持宿主持有。

### `exr_document_resolve`

**签名** `exr_status exr_document_resolve(const exr_document *doc, size_t chapter, const char *uri, size_t *resource, size_t *node, exr_error *error);`

**ABI** 稳定。声明：[formats.h](../include/exr/formats.h)。

**参数** `doc`：已打开的文档；`chapter`：基准章节零基索引；`uri`：相对章节的本地 URI，可含 fragment；`resource`：接收资源索引，未找到 SIZE_MAX；`node`：接收已解析 DOM 节点索引，未找到 SIZE_MAX；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK；缺失目标以 resource/node 的 SIZE_MAX 表示。外部/危险 URI、无效章索引 ARGUMENT；解析与内存错误可返回非 OK。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 所有输入借用，数值输出无需释放。

### `exr_document_export_epub`

**签名** `exr_status exr_document_export_epub(const exr_document *doc, const exr_control *control, void **data, size_t *size, exr_error *error);`

**ABI** 稳定。声明：[formats.h](../include/exr/formats.h)。

**参数** `doc`：已打开的文档；`control`：可 NULL；同步进度/协作取消回调与宿主上下文；`data`：接收导出字节；`size`：接收导出字节数；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 输出字节；结构保留 EPUB：保留章路径、属性和资源；缺失资源、非法 XML 名称、冲突/保留路径失败，受加密/权利限制包拒绝导出。 无效参数 ARGUMENT、不支持目标 FORMAT、非法编码/结构 ENCODING/FORMAT、资源预算 LIMIT、分配 MEMORY；带 control 的路径可 CANCELLED，失败不发布部分归档。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 输入借用；data 用 exr_free。成功字节独立于 doc。

### `exr_document_export_html_bundle`

**签名** `exr_status exr_document_export_html_bundle(const exr_document *doc,const exr_control *control, void **data,size_t *size,char **entry_path,exr_error *error);`

**ABI** 稳定。声明：[formats.h](../include/exr/formats.h)。

**参数** `doc`：已打开的文档；`control`：可 NULL；同步进度/协作取消回调与宿主上下文；`data`：接收导出字节；`size`：接收导出字节数；`entry_path`：接收 ZIP 中入口的 UTF-8 路径；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 输出字节；结构保留 HTML ZIP：复制章节、样式、字体与资源并返回无冲突 XHTML 入口；需要将整个包解压后访问入口。 无效参数 ARGUMENT、不支持目标 FORMAT、非法编码/结构 ENCODING/FORMAT、资源预算 LIMIT、分配 MEMORY；带 control 的路径可 CANCELLED，失败不发布部分归档。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 输入借用；data 用 exr_free。entry_path 也用 exr_free；失败清除全部输出。

### `exr_document_export`

**签名** `exr_status exr_document_export(const exr_document *doc, exr_format format, void **data, size_t *size, exr_error *error);`

**ABI** 稳定。声明：[formats.h](../include/exr/formats.h)。

**参数** `doc`：已打开的文档；`format`：目标 EXR_TXT/HTML/FB2/EPUB/DOCX/RTF；MOBI/PDF/CBZ 非此转换目标；`data`：接收导出字节；`size`：接收导出字节数；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 输出字节；正文转换，只保留正文/段落/顺序/Unicode；不保证样式、标注或资源往返。等价 export_control(control=NULL)。 无效参数 ARGUMENT、不支持目标 FORMAT、非法编码/结构 ENCODING/FORMAT、资源预算 LIMIT、分配 MEMORY；带 control 的路径可 CANCELLED，失败不发布部分归档。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 输入借用；data 用 exr_free。成功字节独立于 doc。

### `exr_document_export_control`

**签名** `exr_status exr_document_export_control(const exr_document *doc, exr_format format, const exr_control *control, void **data, size_t *size, exr_error *error);`

**ABI** 稳定。声明：[formats.h](../include/exr/formats.h)。

**参数** `doc`：已打开的文档；`format`：目标 EXR_TXT/HTML/FB2/EPUB/DOCX/RTF；MOBI/PDF/CBZ 非此转换目标；`control`：可 NULL；同步进度/协作取消回调与宿主上下文；`data`：接收导出字节；`size`：接收导出字节数；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 输出字节；正文转换，支持每 64 块、RTF 每 4096 scalar 及发布归档前的协作取消，不是逐字节取消。 无效参数 ARGUMENT、不支持目标 FORMAT、非法编码/结构 ENCODING/FORMAT、资源预算 LIMIT、分配 MEMORY；带 control 的路径可 CANCELLED，失败不发布部分归档。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 输入借用；data 用 exr_free。成功字节独立于 doc。

### `exr_opds_parse`

**签名** `exr_status exr_opds_parse(const void *data, size_t size, const char *base_url, exr_opds_feed *out, exr_error *error);`

**ABI** 实验；声明：[exr/opds.h](../include/exr/opds.h)。

**参数** `data`：Atom 字节（无需 NUL 结尾，上限 16 MiB）；`size`：字节数；`base_url`：用于解析相对链接的基地址；`out`：新 feed；`error`：可选诊断输出。

**返回与失败** EXR_OK；参数 EXR_ARGUMENT，XML 非法 EXR_FORMAT，超出 4096 条目/嵌套 64/输入上限 EXR_LIMIT，分配 EXR_MEMORY。失败时 out 清零。

**线程** 纯函数，无全局状态；对互不相关的对象可并行。

**所有权** feed 及其字符串归调用方，由 exr_opds_feed_free 释放。

### `exr_opds_feed_free`

**签名** `void exr_opds_feed_free(exr_opds_feed *feed);`

**ABI** 实验；声明：[exr/opds.h](../include/exr/opds.h)。

**参数** `feed`：由 exr_opds_parse 填充的 feed 或 NULL。

**返回与失败** 无返回值；NULL 为空操作，释放后 feed 清零。

**线程** 纯函数，无全局状态；对互不相关的对象可并行。

**所有权** 释放 feed 拥有的全部条目与字符串，不释放 feed 结构本身。

### `exr_opds_parse_search`

**签名** `exr_status exr_opds_parse_search(const void *data, size_t size, const char *base_url, char **template_url, exr_error *error);`

**ABI** 实验；声明：[exr/opds.h](../include/exr/opds.h)。

**参数** `data`、`size`：OpenSearch 描述文档字节；`base_url`：解析基地址；`template_url`：接收结果 URL 模板；`error`：可选诊断输出。

**返回与失败** EXR_OK；参数 EXR_ARGUMENT，文档非法或无 Atom/OPDS 结果模板 EXR_FORMAT，分配 EXR_MEMORY。

**线程** 纯函数，无全局状态；对互不相关的对象可并行。

**所有权** *template_url 归调用方，用 exr_free 释放。

### `exr_opds_search_url`

**签名** `exr_status exr_opds_search_url(const char *template_url, const char *query, char **out, exr_error *error);`

**ABI** 实验；声明：[exr/opds.h](../include/exr/opds.h)。

**参数** `template_url`：含 {searchTerms} 的模板；`query`：UTF-8 查询词；`out`：展开后的 URL；`error`：可选诊断输出。

**返回与失败** EXR_OK；空查询、模板缺少 {searchTerms} 或参数为 NULL 返回 EXR_ARGUMENT，分配 EXR_MEMORY。

**线程** 纯函数，无全局状态；对互不相关的对象可并行。

**所有权** *out 归调用方，用 exr_free 释放。

### `exr_opds_resolve_url`

**签名** `exr_status exr_opds_resolve_url(const char *base_url, const char *reference, char **out, exr_error *error);`

**ABI** 实验；声明：[exr/opds.h](../include/exr/opds.h)。

**参数** `base_url`：http/https 基地址；`reference`：相对或绝对引用；`out`：解析结果；`error`：可选诊断输出。

**返回与失败** EXR_OK；参数为 NULL 或基地址非 http/https 返回 EXR_ARGUMENT，分配 EXR_MEMORY。按 RFC 3986 解析。

**线程** 纯函数，无全局状态；对互不相关的对象可并行。

**所有权** *out 归调用方，用 exr_free 释放。

## 固定版面与 PDF

打开 PDF/CBZ 固定页，并以增量修订读写受支持的 PDF 标注、元数据和表单。

最小可编译示例：[pdf.c](examples/pdf.c)。

<!-- example: docs/examples/pdf.c -->
```c
/* SPDX-License-Identifier: MIT */
#include <exr/pdf.h>
#include <stdio.h>

int main(int argc, char **argv) {
  exr_fixed_document *document = NULL;
  exr_bitmap bitmap = {0};
  exr_error error = {0};
  exr_status status;
  if (argc != 3) { fprintf(stderr, "usage: pdf input.pdf output.png\n"); return 2; }
  status = exr_fixed_open(argv[1], NULL, &document, &error);
  if (status == EXR_OK)
    status = exr_fixed_render(document, 0, 96.0 / 72.0, NULL, &bitmap, &error);
  if (status == EXR_OK) status = exr_bitmap_write_png(&bitmap, argv[2], &error);
  if (status != EXR_OK) fprintf(stderr, "%s\n", error.message);
  exr_bitmap_free(&bitmap);
  exr_fixed_free(document);
  return status == EXR_OK ? 0 : 1;
}
```

### `exr_pdf_crypto_available`

**签名** `int exr_pdf_crypto_available(void);`

**ABI** 稳定。声明：[pdf.h](../include/exr/pdf.h)。

**参数** 无。

**返回与失败** 返回 1 表示编入 PDF 密码学，0 表示关闭；不验证具体文档。

**线程** 无共享可变状态，可并发。

**所有权** 无分配。

### `exr_fixed_open_memory`

**签名** `exr_status exr_fixed_open_memory(exr_format format,const void *data,size_t size, const exr_fixed_open_options *options, exr_fixed_document **out,exr_error *error);`

**ABI** 稳定。声明：[pdf.h](../include/exr/pdf.h)。

**参数** `format`：EXR_PDF 或 EXR_CBZ；`data`：输入文件/资源字节，至少 size 字节；`size`：输入字节长度；`options`：可 NULL；否则 struct_size，fallback_font、control、pdf_password/size；pdf_security 初始化 struct_size；`out`：接收文档，失败 NULL；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 创建惰性固定页文档；ARGUMENT/LIMIT 为参数或输入预算，FORMAT 为不支持格式/损坏，PASSWORD 为缺失或错误 PDF 口令，UNSUPPORTED 为不支持安全处理器/特性；另有 IO/MEMORY/CANCELLED。打开成功不保证每一页都能绘制。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** 成功 out 用 exr_fixed_free；输入内存被复制。options/password 仅调用内借用；fallback_font 被保留到 fixed_free。

### `exr_fixed_open`

**签名** `exr_status exr_fixed_open(const char *path,const exr_fixed_open_options *options, exr_fixed_document **out,exr_error *error);`

**ABI** 稳定。声明：[pdf.h](../include/exr/pdf.h)。

**参数** `path`：UTF-8 文件路径；`options`：可 NULL；否则 struct_size，fallback_font、control、pdf_password/size；pdf_security 初始化 struct_size；`out`：接收文档，失败 NULL；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 创建惰性固定页文档；ARGUMENT/LIMIT 为参数或输入预算，FORMAT 为不支持格式/损坏，PASSWORD 为缺失或错误 PDF 口令，UNSUPPORTED 为不支持安全处理器/特性；另有 IO/MEMORY/CANCELLED。打开成功不保证每一页都能绘制。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** 成功 out 用 exr_fixed_free；文件读取/映射由文档管理。options/password 仅调用内借用；fallback_font 被保留到 fixed_free。

### `exr_pdf_annotation_write_defaults`

**签名** `exr_pdf_annotation_write_options exr_pdf_annotation_write_defaults(void);`

**ABI** 稳定。声明：[pdf_edit.h](../include/exr/pdf_edit.h)。

**参数** 无。

**返回与失败** 返回 struct_size、黄色 0xFFFF00、opacity=0.35 及零 control；无失败。

**线程** 无共享可变状态，可并发。

**所有权** 值返回，无需释放。

### `exr_pdf_annotation_write`

**签名** `exr_status exr_pdf_annotation_write(const void *data,size_t size,size_t page, const exr_page_annotation *annotation,const exr_pdf_annotation_write_options *options, void **out,size_t *out_size,exr_error *error);`

**ABI** 稳定。声明：[pdf_edit.h](../include/exr/pdf_edit.h)。

**参数** `data`：输入文件/资源字节，至少 size 字节；`size`：输入字节长度；`page`：零基页号；`annotation`：NM ID、类型、bounds、五种支持 URI 属性；文字标记 1..32768 个凸四边形，Text 无 quads；`options`：可 NULL（黄色/0.35，更新也同样）；否则 struct_size、0xRRGGBB、[0,1] opacity 与 control；`out`：接收完整 PDF；`out_size`：接收字节数；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 按页面内非空 NM ID 创建/替换 Text/Highlight/Underline/StrikeOut/Squiggly 并生成外观；重复 ID、非法几何/UTF-8/元数据 ARGUMENT/ENCODING，旧于 PDF 1.4、加密或权限限制 UNSUPPORTED；另有 FORMAT/LIMIT/MEMORY/CANCELLED。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** 输入借用，out 是保留全部原字节的完整增量 PDF，用 exr_free。

### `exr_pdf_annotation_remove`

**签名** `exr_status exr_pdf_annotation_remove(const void *data,size_t size,size_t page,const char *id, const exr_control *control,void **out,size_t *out_size,exr_error *error);`

**ABI** 稳定。声明：[pdf_edit.h](../include/exr/pdf_edit.h)。

**参数** `data`：输入文件/资源字节，至少 size 字节；`size`：输入字节长度；`page`：零基页号；`id`：非空 UTF-8 NM 标识；`control`：可 NULL；同步进度/协作取消回调与宿主上下文；`out`：接收完整 PDF；`out_size`：接收字节数；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 删除对应 ID 及同页 Popup；ID 不存在返回逐字节相同独立副本。无效参数 ARGUMENT，损坏 FORMAT，加密/权限限制 UNSUPPORTED，另有 LIMIT/MEMORY/CANCELLED；失败清除输出。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** 输入借用，out 用 exr_free；增量删除保留历史内容，不能用作安全擦除。

### `exr_pdf_metadata_write`

**签名** `exr_status exr_pdf_metadata_write(const void *data,size_t size,const exr_metadata_entry *changes,size_t count, const exr_control *control,void **out,size_t *out_size,exr_error *error);`

**ABI** 稳定。声明：[pdf_edit.h](../include/exr/pdf_edit.h)。

**参数** `data`：输入文件/资源字节，至少 size 字节；`size`：输入字节长度；`changes`：Info URI 修改项；日期用 PDF D: 或 ISO8601 秒精度，可保留时区；`count`：changes 数量；`control`：可 NULL；同步进度/协作取消回调与宿主上下文；`out`：接收完整 PDF；`out_size`：接收字节数；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 增量修改八种 PDF Info URI 及已有 XMP；未列键保持，NULL 删除，空串保留（日期除外）。不支持键/无效日期 ARGUMENT，损坏 FORMAT，加密/权限限制 UNSUPPORTED；另有 ENCODING/LIMIT/MEMORY/CANCELLED。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** 输入借用，out 为完整独立 PDF，用 exr_free。

### `exr_pdf_form_defaults`

**签名** `exr_pdf_form_options exr_pdf_form_defaults(void);`

**ABI** 稳定。声明：[pdf_edit.h](../include/exr/pdf_edit.h)。

**参数** 无。

**返回与失败** 返回默认表单限额：4096 字段、16384 widget、64 层、8 MiB 文本及 struct_size/control；无失败。

**线程** 无共享可变状态，可并发。

**所有权** 值返回，无需释放。

### `exr_pdf_form_read`

**签名** `exr_status exr_pdf_form_read(const void *data,size_t size,const exr_pdf_form_options *options, exr_pdf_form_field **out,size_t *count,exr_error *error);`

**ABI** 稳定。声明：[pdf_edit.h](../include/exr/pdf_edit.h)。

**参数** `data`：输入文件/资源字节，至少 size 字节；`size`：输入字节长度；`options`：可 NULL；struct_size、上限（0 选默认）、control；`out`：接收字段数组，含继承后 FT/Ff/V/DV/DA/Q/MaxLen/Opt；`count`：接收字段数；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 返回字段独立快照；无表单为 NULL/0。环、共享子节点、重名和 Parent 不一致 FORMAT；无效参数 ARGUMENT，预算 LIMIT；另有 UNSUPPORTED/MEMORY/CANCELLED。XFA/actions 记录 issues，不执行。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** out 数组及内嵌字符串用 exr_pdf_form_free(out,count)。

### `exr_pdf_form_free`

**签名** `void exr_pdf_form_free(exr_pdf_form_field *fields,size_t count);`

**ABI** 稳定。声明：[pdf_edit.h](../include/exr/pdf_edit.h)。

**参数** `fields`：form_read 的快照；`count`：原字段数。

**返回与失败** 无返回值；NULL 无操作。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 消费 fields 及其子数组/字符串，count 用原返回数量。

### `exr_pdf_form_write_defaults`

**签名** `exr_pdf_form_write_options exr_pdf_form_write_defaults(void);`

**ABI** 稳定。声明：[pdf_edit.h](../include/exr/pdf_edit.h)。

**参数** 无。

**返回与失败** 返回已初始化 struct_size、font=NULL、font_index=0 和零 control；无失败。

**线程** 无共享可变状态，可并发。

**所有权** 值返回，无需释放。

### `exr_pdf_form_write`

**签名** `exr_status exr_pdf_form_write(const void *data,size_t size,const exr_pdf_form_change *changes,size_t count, const exr_pdf_form_write_options *options,void **out,size_t *out_size,exr_error *error);`

**ABI** 稳定。声明：[pdf_edit.h](../include/exr/pdf_edit.h)。

**参数** `data`：输入文件/资源字节，至少 size 字节；`size`：输入字节长度；`changes`：限定字段名及 UTF-8 values，空列表清除；按钮用导出名或 Off；`count`：changes 数量；`options`：可 NULL（ASCII Helvetica）；Unicode LTR 指定 outline font/font_index 与 control，font 与其他使用串行；`out`：接收完整 PDF；`out_size`：接收字节数；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 原子增量修改 Tx/checkbox/radio/Ch 值及所有关联 widget 外观；只读/Required/MaxLen/选项/选择基数违例 ARGUMENT；多行、password、file-select、rich-text、comb、可编辑 combo、签名/按钮、XFA/actions/旋转/权限、双向文字或缺失可见字形 UNSUPPORTED；另有 FORMAT/ENCODING/LIMIT/MEMORY/CANCELLED。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** 输入借用，options.font 也仅借用；out 完整 PDF 用 exr_free；失败清空输出；不执行 JS 或动作。

## 音频

用不可变时间线组织音频，以宿主回调驱动播放，并提供解码、PCM 变速及系统输出。

最小可编译示例：[audio.c](examples/audio.c)。

<!-- example: docs/examples/audio.c -->
```c
/* SPDX-License-Identifier: MIT */
#include <exr/audio.h>
#include <stdio.h>

int main(void) {
  const exr_audio_track track = {"track-1", "one.wav", "audio/wav", 1000};
  exr_audio_input input = {0};
  exr_audio *audio = NULL;
  exr_audio_position position = {0};
  exr_error error = {0};
  input.struct_size = sizeof(input);
  input.title = "A host timeline";
  input.tracks = &track;
  input.track_count = 1;
  exr_status status = exr_audio_create(&input, NULL, &audio, &error);
  if (status == EXR_OK) status = exr_audio_locate(audio, 500, &position, &error);
  if (status == EXR_OK)
    printf("track=%zu offset=%llu ms\n", position.track, (unsigned long long)position.offset_ms);
  else fprintf(stderr, "%s\n", error.message);
  /* Timeline creation does not open the URI or start an audio device. */
  exr_audio_free(audio);
  return status == EXR_OK ? 0 : 1;
}
```

### `exr_audio_create`

**签名** `exr_status exr_audio_create(const exr_audio_input *input,const exr_control *control,exr_audio **out,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `input`：struct_size、title、轨道/章节/同步数组；轨道时长为正，章节 parent 为前序父节点或 SIZE_MAX；`control`：可 NULL；同步进度/协作取消回调与宿主上下文；`out`：接收不可变时间线，失败 NULL；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 深拷贝时间线；缺轨道、重复 ID、无效/溢出时长或章节/同步范围 ARGUMENT，UTF-8 ENCODING、表或字符串预算 LIMIT、分配 MEMORY、取消 CANCELLED。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** input 内容复制，成功 out 用 exr_audio_free。

### `exr_audio_free`

**签名** `void exr_audio_free(exr_audio *audio);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `audio`：不可变音频时间线。

**返回与失败** 无返回值；NULL 无操作。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 释放一个时间线引用；播放器保留引用时实际数据继续有效。

### `exr_audio_title`

**签名** `const char *exr_audio_title(const exr_audio *audio);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `audio`：不可变音频时间线。

**返回与失败** 返回 UTF-8 标题，NULL audio 返回空串。

**线程** 仅查询不可变数据；可并行只读，但不得与释放、引用计数变更或底层来源变更并发。

**所有权** 借用至最后一个 audio 引用释放。

### `exr_audio_duration`

**签名** `uint64_t exr_audio_duration(const exr_audio *audio);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `audio`：不可变音频时间线。

**返回与失败** 返回拼接后的总毫秒数，NULL audio 返回 0。

**线程** 仅查询不可变数据；可并行只读，但不得与释放、引用计数变更或底层来源变更并发。

**所有权** 输入仅借用，输出结构由调用方提供；没有新分配需要释放。

### `exr_audio_tracks`

**签名** `const exr_audio_track *exr_audio_tracks(const exr_audio *audio,size_t *count);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `audio`：不可变音频时间线；`count`：可 NULL，接收轨道数量。

**返回与失败** 返回轨道数组；NULL audio 返回 NULL/count=0。

**线程** 仅查询不可变数据；可并行只读，但不得与释放、引用计数变更或底层来源变更并发。

**所有权** 借用数组及字符串至最后一个 audio 引用释放。

### `exr_audio_chapters`

**签名** `const exr_audio_chapter *exr_audio_chapters(const exr_audio *audio,size_t *count);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `audio`：不可变音频时间线；`count`：可 NULL，接收章节数量。

**返回与失败** 返回章节数组；NULL audio 返回 NULL/count=0。

**线程** 仅查询不可变数据；可并行只读，但不得与释放、引用计数变更或底层来源变更并发。

**所有权** 借用数组及字符串至最后一个 audio 引用释放。

### `exr_audio_syncs`

**签名** `const exr_audio_sync *exr_audio_syncs(const exr_audio *audio,size_t *count);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `audio`：不可变音频时间线；`count`：可 NULL，接收文字同步数量。

**返回与失败** 返回文字同步数组；NULL audio 返回 NULL/count=0。

**线程** 仅查询不可变数据；可并行只读，但不得与释放、引用计数变更或底层来源变更并发。

**所有权** 借用数组及字符串至最后一个 audio 引用释放。

### `exr_audio_memory_size`

**签名** `size_t exr_audio_memory_size(const exr_audio *audio);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `audio`：不可变音频时间线。

**返回与失败** 返回时间线已计入的数据与字符串字节数；NULL 返回 0。

**线程** 仅查询不可变数据；可并行只读，但不得与释放、引用计数变更或底层来源变更并发。

**所有权** 输入仅借用，输出结构由调用方提供；没有新分配需要释放。

### `exr_audio_locate`

**签名** `exr_status exr_audio_locate(const exr_audio *audio,uint64_t time_ms,exr_audio_position *out,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `audio`：不可变音频时间线；`time_ms`：全局毫秒，范围 [0,duration]；`out`：接收零基 track 与 offset_ms；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 得到轨道及轨内毫秒；边界选下一轨，总时长选最后轨 EOF。time_ms 超总时长/空参数 ARGUMENT。

**线程** 仅查询不可变数据；可并行只读，但不得与释放、引用计数变更或底层来源变更并发。

**所有权** 输入仅借用，输出结构由调用方提供；没有新分配需要释放。

### `exr_audio_sync_at`

**签名** `exr_status exr_audio_sync_at(const exr_audio *audio,uint64_t time_ms,size_t from,const exr_control *control,size_t *index,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `audio`：不可变音频时间线；`time_ms`：全局毫秒；`from`：同步表开始索引；`control`：可 NULL；同步进度/协作取消回调与宿主上下文；`index`：接收匹配索引或 SIZE_MAX；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 查半开时间区间，未命中 index=SIZE_MAX；位置/from 无效 ARGUMENT，取消 CANCELLED。后续以 from=index+1 枚举重叠结果。

**线程** 仅查询不可变数据；可并行只读，但不得与释放、引用计数变更或底层来源变更并发。

**所有权** 输入仅借用，输出结构由调用方提供；没有新分配需要释放。

### `exr_audio_sync_text`

**签名** `exr_status exr_audio_sync_text(const exr_audio *audio,const char *part_id,size_t start,size_t end,size_t from, const exr_control *control,size_t *index,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `audio`：不可变音频时间线；`part_id`：宿主文字分片 ID，SDK 不对文档验证；`start`：半开文字字节范围起点；`end`：范围末尾，允许 start==end 点查询；`from`：同步表开始索引；`control`：可 NULL；同步进度/协作取消回调与宿主上下文；`index`：接收匹配索引或 SIZE_MAX；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 查指定 part_id 下与 UTF-8 字节范围相交项；空范围按点查询，未命中 SIZE_MAX。无效范围/参数 ARGUMENT、part_id 编码 ENCODING/长度 LIMIT、取消 CANCELLED。

**线程** 仅查询不可变数据；可并行只读，但不得与释放、引用计数变更或底层来源变更并发。

**所有权** 输入仅借用，输出结构由调用方提供；没有新分配需要释放。

### `exr_audio_time`

**签名** `exr_status exr_audio_time(const exr_audio *audio,size_t track,uint64_t offset_ms,uint64_t *time_ms,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `audio`：不可变音频时间线；`track`：零基轨道索引；`offset_ms`：该轨道内毫秒（可等于时长）；`time_ms`：接收全局毫秒；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 将轨内位置转全局毫秒；无效轨道/超过轨长 ARGUMENT。

**线程** 仅查询不可变数据；可并行只读，但不得与释放、引用计数变更或底层来源变更并发。

**所有权** 输入仅借用，输出结构由调用方提供；没有新分配需要释放。

### `exr_audio_player_create`

**签名** `exr_status exr_audio_player_create(exr_audio *audio,const exr_audio_backend *backend,exr_audio_player **out,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `audio`：不可变音频时间线；`backend`：struct_size、同步 command 回调、context、可选 release；`out`：接收播放器，失败 NULL；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 创建暂停播放器，不立即打开设备/解码器；无效 backend/结构大小 ARGUMENT、分配 MEMORY、引用计数上限 LIMIT。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 保留 audio 引用；backend.context 仅成功时接管，free 调 release；out 用 exr_audio_player_free。

### `exr_audio_player_free`

**签名** `void exr_audio_player_free(exr_audio_player *player);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `player`：宿主驱动播放器。

**返回与失败** 无返回值；NULL 无操作。若使用过 backend 则发送 CLOSE，关闭错误不返回。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 释放播放器及 backend.context，释放所保留 audio 引用；回调不能再使用此播放器。

### `exr_audio_player_get`

**签名** `exr_status exr_audio_player_get(const exr_audio_player *player,exr_audio_playback *out,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `player`：宿主驱动播放器；`out`：接收 time_ms、generation、轨道、rate、playing、needs_reload；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 写当前进度快照；player/out 缺失 ARGUMENT。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** out 值字段归调用方；track_id 借用至 player_free。

### `exr_audio_player_play`

**签名** `exr_status exr_audio_player_play(exr_audio_player *player,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `player`：宿主驱动播放器；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 开始/恢复播放；结束位置再次播放会进入下一轨或从头开始；缺失/回调重入 ARGUMENT、generation 溢出 LIMIT；透传 backend 失败并设置 needs_reload/暂停状态。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 输入仅借用，输出结构由调用方提供；没有新分配需要释放。

### `exr_audio_player_pause`

**签名** `exr_status exr_audio_player_pause(exr_audio_player *player,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `player`：宿主驱动播放器；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 暂停播放；已经暂停时成功且无动作；缺失/回调重入 ARGUMENT、generation 溢出 LIMIT；透传 backend 失败并设置 needs_reload/暂停状态。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 输入仅借用，输出结构由调用方提供；没有新分配需要释放。

### `exr_audio_player_seek`

**签名** `exr_status exr_audio_player_seek(exr_audio_player *player,uint64_t time_ms,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `player`：宿主驱动播放器；`time_ms`：目标全局毫秒，可等于 duration；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 跳转全局时间；未首次播放前仅更新状态。时间越界/重入 ARGUMENT，generation LIMIT，backend 错误透传。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 输入仅借用，输出结构由调用方提供；没有新分配需要释放。

### `exr_audio_player_rate`

**签名** `exr_status exr_audio_player_rate(exr_audio_player *player,double rate,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `player`：宿主驱动播放器；`rate`：有限播放倍率 (0,16]，不是 WSOLA 的 [0.5,2] 限额；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 设置播放倍率；非有限数、rate<=0 或 >16、重入 ARGUMENT；generation LIMIT，backend 错误透传。具体可播放倍率仍由 backend 决定。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 输入仅借用，输出结构由调用方提供；没有新分配需要释放。

### `exr_audio_player_restore`

**签名** `exr_status exr_audio_player_restore(exr_audio_player *player,const char *track_id,uint64_t offset_ms,double rate,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `player`：宿主驱动播放器；`track_id`：持久化的非空轨道 ID；`offset_ms`：轨内毫秒；`rate`：有限倍率 (0,16]；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 按稳定轨道 ID 恢复为暂停；ID 不存在/空、越界 offset、无效 rate 或重入 ARGUMENT，generation LIMIT，backend 错误透传。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 输入仅借用，输出结构由调用方提供；没有新分配需要释放。

### `exr_audio_player_report`

**签名** `exr_status exr_audio_player_report(exr_audio_player *player,uint64_t generation,size_t track,uint64_t offset_ms,int ended,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `player`：宿主驱动播放器；`generation`：最近发给 backend 的命令代号；`track`：当前零基轨道；`offset_ms`：实际轨内毫秒，不得倒退；`ended`：仅 0/1；1 要求 offset_ms 正好轨末；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 接收 backend 实际进度；匹配 ended 会推进轨道/结束播放。过期 generation、倒退时间、错误轨道/末端、未加载或重入 ARGUMENT；generation LIMIT，推进时 backend 错误透传。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 输入仅借用，输出结构由调用方提供；没有新分配需要释放。

### `exr_wave_open`

**签名** `exr_status exr_wave_open(const char *path,const exr_control *control,exr_wave **out,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `path`：UTF-8 文件路径；`control`：可 NULL；同步进度/协作取消回调与宿主上下文；`out`：接收解码对象，失败 NULL；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 打开 RIFF/WAVE 整数/浮点 PCM（含支持的 extensible 格式）；ARGUMENT 为参数，FORMAT 为不支持/损坏，IO 为读取，LIMIT 为预算，另有 MEMORY/CANCELLED。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** 成功 out 用 exr_wave_free。path/control 仅调用内借用，底层文件由对象关闭。

### `exr_wave_open_source`

**签名** `exr_status exr_wave_open_source(const exr_source *source,exr_wave **out,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `source`：不可变随机读取源（size/read_at/context/release/control）；`out`：接收解码对象，失败 NULL；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 打开 RIFF/WAVE 整数/浮点 PCM（含支持的 extensible 格式）；ARGUMENT 为参数，FORMAT 为不支持/损坏，IO 为读取，LIMIT 为预算，另有 MEMORY/CANCELLED。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** 成功 out 用 exr_wave_free。source.context 仅成功时接管；失败宿主仍负责 release。

### `exr_wave_free`

**签名** `void exr_wave_free(exr_wave *wave);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `wave`：WAVE 解码对象。

**返回与失败** 无返回值；NULL 无操作。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 消费 wave，关闭解码器并调用成功接管来源的 release。

### `exr_wave_format`

**签名** `const exr_wave_info *exr_wave_format(const exr_wave *wave);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `wave`：WAVE 解码对象。

**返回与失败** 返回采样率、声道和帧数等格式信息；NULL 对象返回 NULL。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 借用到对应 free；读取可更新帧数，需同步查询。

### `exr_wave_read`

**签名** `exr_status exr_wave_read(exr_wave *wave,uint64_t first_frame,size_t frames,float *output,size_t *read, const exr_control *control,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `wave`：WAVE 解码对象；`first_frame`：零基 PCM 帧位置，非毫秒/字节；`frames`：请求帧数，最多 65536；`output`：接收声道交错 float 样本；`read`：接收实际读取帧数；`control`：可 NULL；同步进度/协作取消回调与宿主上下文；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK，read 为实际帧数，EOF 可为 0；无效范围/指针 ARGUMENT，每次 >65536 帧 LIMIT，坏数据 FORMAT、来源 IO、取消 CANCELLED，解码资源还可 MEMORY/LIMIT。运行时失败清零输出且 read=0。按帧随机访问。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** output 是调用方分配的 float 数组（至少 frames*channels），不转移所有权；解码对象保留源。

### `exr_flac_open`

**签名** `exr_status exr_flac_open(const char *path,const exr_control *control,exr_flac **out,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `path`：UTF-8 文件路径；`control`：可 NULL；同步进度/协作取消回调与宿主上下文；`out`：接收解码对象，失败 NULL；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 打开 原始 FLAC（CRC8/CRC16 校验，不校验全流 MD5）；ARGUMENT 为参数，FORMAT 为不支持/损坏，IO 为读取，LIMIT 为预算，另有 MEMORY/CANCELLED。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** 成功 out 用 exr_flac_free。path/control 仅调用内借用，底层文件由对象关闭。

### `exr_flac_open_source`

**签名** `exr_status exr_flac_open_source(const exr_source *source,exr_flac **out,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `source`：不可变随机读取源（size/read_at/context/release/control）；`out`：接收解码对象，失败 NULL；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 打开 原始 FLAC（CRC8/CRC16 校验，不校验全流 MD5）；ARGUMENT 为参数，FORMAT 为不支持/损坏，IO 为读取，LIMIT 为预算，另有 MEMORY/CANCELLED。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** 成功 out 用 exr_flac_free。source.context 仅成功时接管；失败宿主仍负责 release。

### `exr_flac_free`

**签名** `void exr_flac_free(exr_flac *flac);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `flac`：FLAC 解码对象。

**返回与失败** 无返回值；NULL 无操作。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 消费 flac，关闭解码器并调用成功接管来源的 release。

### `exr_flac_format`

**签名** `const exr_flac_info *exr_flac_format(const exr_flac *flac);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `flac`：FLAC 解码对象。

**返回与失败** 返回采样率、声道和帧数等格式信息；NULL 对象返回 NULL。 frames 可为 UINT64_MAX（未知），经过验证 EOF 后可能更新。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 借用到对应 free；读取可更新帧数，需同步查询。

### `exr_flac_read`

**签名** `exr_status exr_flac_read(exr_flac *flac,uint64_t first_frame,size_t frames,float *output,size_t *read, const exr_control *control,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `flac`：FLAC 解码对象；`first_frame`：零基 PCM 帧位置，非毫秒/字节；`frames`：请求帧数，最多 65536；`output`：接收声道交错 float 样本；`read`：接收实际读取帧数；`control`：可 NULL；同步进度/协作取消回调与宿主上下文；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK，read 为实际帧数，EOF 可为 0；无效范围/指针 ARGUMENT，每次 >65536 帧 LIMIT，坏数据 FORMAT、来源 IO、取消 CANCELLED，解码资源还可 MEMORY/LIMIT。运行时失败清零输出且 read=0。有界扫描可 LIMIT，保留已验证 seek 检查点以重试。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** output 是调用方分配的 float 数组（至少 frames*channels），不转移所有权；解码对象保留源。

### `exr_mp3_available`

**签名** `int exr_mp3_available(void);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** 无。

**返回与失败** 返回是否编入minimp3（EXR_ENABLE_MP3），1 可用、0 关闭；不验证输入。

**线程** 无共享可变状态，可并发。

**所有权** 无分配。

### `exr_mp3_open`

**签名** `exr_status exr_mp3_open(const char *path,const exr_control *control,exr_mp3 **out,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `path`：UTF-8 文件路径；`control`：可 NULL；同步进度/协作取消回调与宿主上下文；`out`：接收解码对象，失败 NULL；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 打开 MPEG-1/2/2.5 Layer III 普通码率；不支持 free-format；ARGUMENT 为参数，FORMAT 为不支持/损坏或 codec 关闭，IO 为读取，LIMIT 为预算，另有 MEMORY/CANCELLED。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** 成功 out 用 exr_mp3_free。path/control 仅调用内借用，底层文件由对象关闭。

### `exr_mp3_open_source`

**签名** `exr_status exr_mp3_open_source(const exr_source *source,exr_mp3 **out,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `source`：不可变随机读取源（size/read_at/context/release/control）；`out`：接收解码对象，失败 NULL；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 打开 MPEG-1/2/2.5 Layer III 普通码率；不支持 free-format；ARGUMENT 为参数，FORMAT 为不支持/损坏或 codec 关闭，IO 为读取，LIMIT 为预算，另有 MEMORY/CANCELLED。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** 成功 out 用 exr_mp3_free。source.context 仅成功时接管；失败宿主仍负责 release。

### `exr_mp3_free`

**签名** `void exr_mp3_free(exr_mp3 *mp3);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `mp3`：MP3 解码对象。

**返回与失败** 无返回值；NULL 无操作。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 消费 mp3，关闭解码器并调用成功接管来源的 release。

### `exr_mp3_format`

**签名** `const exr_mp3_info *exr_mp3_format(const exr_mp3 *mp3);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `mp3`：MP3 解码对象。

**返回与失败** 返回采样率、声道和帧数等格式信息；NULL 对象返回 NULL。 frames 可为 UINT64_MAX（未知），经过验证 EOF 后可能更新。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 借用到对应 free；读取可更新帧数，需同步查询。

### `exr_mp3_read`

**签名** `exr_status exr_mp3_read(exr_mp3 *mp3,uint64_t first_frame,size_t frames,float *output,size_t *read, const exr_control *control,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `mp3`：MP3 解码对象；`first_frame`：零基 PCM 帧位置，非毫秒/字节；`frames`：请求帧数，最多 65536；`output`：接收声道交错 float 样本；`read`：接收实际读取帧数；`control`：可 NULL；同步进度/协作取消回调与宿主上下文；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK，read 为实际帧数，EOF 可为 0；无效范围/指针 ARGUMENT，每次 >65536 帧 LIMIT，坏数据 FORMAT、来源 IO、取消 CANCELLED，解码资源还可 MEMORY/LIMIT。运行时失败清零输出且 read=0。有效 Xing/LAME 时使用去首尾延迟的 gapless 帧索引；有界 seek 可 LIMIT。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** output 是调用方分配的 float 数组（至少 frames*channels），不转移所有权；解码对象保留源。

### `exr_aac_available`

**签名** `int exr_aac_available(void);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** 无。

**返回与失败** 返回是否编入FAAD2（EXR_ENABLE_AAC，默认 OFF），1 可用、0 关闭；不验证输入。

**线程** 无共享可变状态，可并发。

**所有权** 无分配。

### `exr_aac_open`

**签名** `exr_status exr_aac_open(const char *path,const exr_control *control,exr_aac **out,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `path`：UTF-8 文件路径；`control`：可 NULL；同步进度/协作取消回调与宿主上下文；`out`：接收解码对象，失败 NULL；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 打开 ADTS AAC，单 raw block、channel_configuration 1..7；不支持 ADIF/LATM、不校验 CRC；ARGUMENT 为参数，FORMAT 为不支持/损坏或 codec 关闭，IO 为读取，LIMIT 为预算，另有 MEMORY/CANCELLED。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** 成功 out 用 exr_aac_free。path/control 仅调用内借用，底层文件由对象关闭。

### `exr_aac_open_source`

**签名** `exr_status exr_aac_open_source(const exr_source *source,exr_aac **out,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `source`：不可变随机读取源（size/read_at/context/release/control）；`out`：接收解码对象，失败 NULL；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 打开 ADTS AAC，单 raw block、channel_configuration 1..7；不支持 ADIF/LATM、不校验 CRC；ARGUMENT 为参数，FORMAT 为不支持/损坏或 codec 关闭，IO 为读取，LIMIT 为预算，另有 MEMORY/CANCELLED。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** 成功 out 用 exr_aac_free。source.context 仅成功时接管；失败宿主仍负责 release。

### `exr_aac_free`

**签名** `void exr_aac_free(exr_aac *aac);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `aac`：ADTS AAC 解码对象。

**返回与失败** 无返回值；NULL 无操作。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 消费 aac，关闭解码器并调用成功接管来源的 release。

### `exr_aac_format`

**签名** `const exr_aac_info *exr_aac_format(const exr_aac *aac);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `aac`：ADTS AAC 解码对象。

**返回与失败** 返回采样率、声道和帧数等格式信息；NULL 对象返回 NULL。 frames 可为 UINT64_MAX（未知），经过验证 EOF 后可能更新。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 借用到对应 free；读取可更新帧数，需同步查询。

### `exr_aac_read`

**签名** `exr_status exr_aac_read(exr_aac *aac,uint64_t first_frame,size_t frames,float *output,size_t *read, const exr_control *control,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `aac`：ADTS AAC 解码对象；`first_frame`：零基 PCM 帧位置，非毫秒/字节；`frames`：请求帧数，最多 65536；`output`：接收声道交错 float 样本；`read`：接收实际读取帧数；`control`：可 NULL；同步进度/协作取消回调与宿主上下文；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK，read 为实际帧数，EOF 可为 0；无效范围/指针 ARGUMENT，每次 >65536 帧 LIMIT，坏数据 FORMAT、来源 IO、取消 CANCELLED，解码资源还可 MEMORY/LIMIT。运行时失败清零输出且 read=0。倒退从头重放；有界扫描 LIMIT 时保留进度，可重试同一目标。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** output 是调用方分配的 float 数组（至少 frames*channels），不转移所有权；解码对象保留源。

### `exr_m4b_available`

**签名** `int exr_m4b_available(void);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** 无。

**返回与失败** 返回是否编入FAAD2（EXR_ENABLE_AAC，默认 OFF），1 可用、0 关闭；不验证输入。

**线程** 无共享可变状态，可并发。

**所有权** 无分配。

### `exr_m4b_open`

**签名** `exr_status exr_m4b_open(const char *path,const exr_control *control,exr_m4b **out,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `path`：UTF-8 文件路径；`control`：可 NULL；同步进度/协作取消回调与宿主上下文；`out`：接收解码对象，失败 NULL；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 打开 非分片 ISO-BMFF mp4a AAC；拒绝加密、外部数据引用、多 sample description 与不连续/变速 edit；ARGUMENT 为参数，FORMAT 为不支持/损坏或 codec 关闭，IO 为读取，LIMIT 为预算，另有 MEMORY/CANCELLED。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** 成功 out 用 exr_m4b_free。path/control 仅调用内借用，底层文件由对象关闭。

### `exr_m4b_open_source`

**签名** `exr_status exr_m4b_open_source(const exr_source *source,exr_m4b **out,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `source`：不可变随机读取源（size/read_at/context/release/control）；`out`：接收解码对象，失败 NULL；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 打开 非分片 ISO-BMFF mp4a AAC；拒绝加密、外部数据引用、多 sample description 与不连续/变速 edit；ARGUMENT 为参数，FORMAT 为不支持/损坏或 codec 关闭，IO 为读取，LIMIT 为预算，另有 MEMORY/CANCELLED。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** 成功 out 用 exr_m4b_free。source.context 仅成功时接管；失败宿主仍负责 release。

### `exr_m4b_free`

**签名** `void exr_m4b_free(exr_m4b *m4b);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `m4b`：M4A/M4B 解码对象。

**返回与失败** 无返回值；NULL 无操作。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 消费 m4b，关闭解码器并调用成功接管来源的 release。

### `exr_m4b_format`

**签名** `const exr_m4b_info *exr_m4b_format(const exr_m4b *m4b);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `m4b`：M4A/M4B 解码对象。

**返回与失败** 返回采样率、声道和帧数等格式信息；NULL 对象返回 NULL。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 借用到对应 free；读取可更新帧数，需同步查询。

### `exr_m4b_read`

**签名** `exr_status exr_m4b_read(exr_m4b *m4b,uint64_t first_frame,size_t frames,float *output,size_t *read, const exr_control *control,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `m4b`：M4A/M4B 解码对象；`first_frame`：零基 PCM 帧位置，非毫秒/字节；`frames`：请求帧数，最多 65536；`output`：接收声道交错 float 样本；`read`：接收实际读取帧数；`control`：可 NULL；同步进度/协作取消回调与宿主上下文；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK，read 为实际帧数，EOF 可为 0；无效范围/指针 ARGUMENT，每次 >65536 帧 LIMIT，坏数据 FORMAT、来源 IO、取消 CANCELLED，解码资源还可 MEMORY/LIMIT。运行时失败清零输出且 read=0。支持的 edit/sample 时长裁掉 priming/tail，并包含前置空 edit 静音；倒退有界重放。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** output 是调用方分配的 float 数组（至少 frames*channels），不转移所有权；解码对象保留源。

### `exr_pcm_create`

**签名** `exr_status exr_pcm_create(const exr_pcm_input *input,exr_pcm **out,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `input`：struct_size、info（帧数 UINT64_MAX 可未知）、read、context、release；info.sample_rate=1..1048575、channels=1..32、channel_mask=0 或其置位数等于 channels；frames=UINT64_MAX 表示未知；`out`：接收 PCM 对象，失败 NULL；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 封装自定义 PCM provider；结构大小/回调/采样率/声道或 channel_mask 不一致 ARGUMENT，分配 MEMORY。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** input.context 仅成功时转移，pcm_free 调 release；out 用 exr_pcm_free。

### `exr_pcm_open`

**签名** `exr_status exr_pcm_open(const char *path,const exr_control *control,exr_pcm **out,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `path`：UTF-8 文件路径；`control`：可 NULL；同步进度/协作取消回调与宿主上下文；`out`：接收解码对象，失败 NULL；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 打开 自动探测 WAV/FLAC/启用的 MP3、ADTS AAC、M4A/M4B；ARGUMENT 为参数，FORMAT 为不支持/损坏或 codec 关闭，IO 为读取，LIMIT 为预算，另有 MEMORY/CANCELLED。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** 成功 out 用 exr_pcm_free。path/control 仅调用内借用，底层文件由对象关闭。

### `exr_pcm_open_source`

**签名** `exr_status exr_pcm_open_source(const exr_source *source,exr_pcm **out,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `source`：不可变随机读取源（size/read_at/context/release/control）；`out`：接收解码对象，失败 NULL；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 打开 自动探测 WAV/FLAC/启用的 MP3、ADTS AAC、M4A/M4B；ARGUMENT 为参数，FORMAT 为不支持/损坏或 codec 关闭，IO 为读取，LIMIT 为预算，另有 MEMORY/CANCELLED。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** 成功 out 用 exr_pcm_free。source.context 仅成功时接管；失败宿主仍负责 release。

### `exr_pcm_free`

**签名** `void exr_pcm_free(exr_pcm *pcm);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `pcm`：PCM provider/解码对象。

**返回与失败** 无返回值；NULL 无操作。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 消费 pcm，关闭解码器并调用成功接管来源的 release。

### `exr_pcm_format`

**签名** `const exr_pcm_info *exr_pcm_format(const exr_pcm *pcm);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `pcm`：PCM provider/解码对象。

**返回与失败** 返回采样率、声道和帧数等格式信息；NULL 对象返回 NULL。 frames 可为 UINT64_MAX（未知），经过验证 EOF 后可能更新。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 借用到对应 free；读取可更新帧数，需同步查询。

### `exr_pcm_read`

**签名** `exr_status exr_pcm_read(exr_pcm *pcm,uint64_t first_frame,size_t frames,float *output,size_t *read, const exr_control *control,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `pcm`：PCM provider/解码对象；`first_frame`：零基 PCM 帧位置，非毫秒/字节；`frames`：请求帧数，最多 65536；`output`：接收声道交错 float 样本；`read`：接收实际读取帧数；`control`：可 NULL；同步进度/协作取消回调与宿主上下文；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK，read 为实际帧数，EOF 可为 0；无效范围/指针 ARGUMENT，每次 >65536 帧 LIMIT，坏数据 FORMAT、来源 IO、取消 CANCELLED，解码资源还可 MEMORY/LIMIT。运行时失败清零输出且 read=0。provider 须返回有限交错样本；过量/提前 EOF 或非有限样本 FORMAT。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** output 是调用方分配的 float 数组（至少 frames*channels），不转移所有权；解码对象保留源。

### `exr_stretch_create`

**签名** `exr_status exr_stretch_create(uint32_t sample_rate,uint32_t channels,double rate,exr_stretch **out,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `sample_rate`：固定输入输出采样率，Hz；`channels`：交错声道数 1..8；`rate`：播放速度 [0.5,2]，内部 Q32 表示；`out`：接收变速器，失败 NULL；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 创建 WSOLA 保调变速器；采样率非 7350..192000、声道非 1..8、rate 非有限 [0.5,2] 为 ARGUMENT；分配 MEMORY。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** out 用 exr_stretch_free。

### `exr_stretch_free`

**签名** `void exr_stretch_free(exr_stretch *stretch);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `stretch`：WSOLA 变速对象。

**返回与失败** 无返回值；NULL 无操作。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 释放变速器和所有环形缓冲。

### `exr_stretch_get`

**签名** `exr_status exr_stretch_get(const exr_stretch *stretch,exr_stretch_state *out,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `stretch`：WSOLA 变速对象；`out`：接收格式、Q32 转回 rate、帧计数、缓冲量、延迟与结束状态；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 给统计/finished/drained；空参数或重入 ARGUMENT。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** out 是值快照，无需释放。

### `exr_stretch_push`

**签名** `exr_status exr_stretch_push(exr_stretch *stretch,const float *input,size_t frames,size_t *accepted,const exr_control *control,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `stretch`：WSOLA 变速对象；`input`：声道交错有限 float 样本；`frames`：请求输入帧数，最多 65536；`accepted`：接收实际接受帧数；`control`：可 NULL；同步进度/协作取消回调与宿主上下文；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 接收 accepted 帧，背压可为 0，应先 pull 再重试；已 finish/重入/无效或非有限输入 ARGUMENT，>65536 帧/计数溢出 LIMIT，取消 CANCELLED。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 仅复制已接受帧；input 可在返回后复用。

### `exr_stretch_pull`

**签名** `exr_status exr_stretch_pull(exr_stretch *stretch,float *output,size_t frames,size_t *read,const exr_control *control,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `stretch`：WSOLA 变速对象；`output`：接收交错 float；`frames`：输出容量（帧），最多 65536；`read`：接收实际帧数；`control`：可 NULL；同步进度/协作取消回调与宿主上下文；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 返回 read 帧，等待输入或排空可为 0；一般最多一 hop，rate=1 可按容量直通。无效/重入 ARGUMENT、>65536 帧 LIMIT、内部时长/计算错误 FORMAT/LIMIT、取消 CANCELLED。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** output 由调用方分配至少 frames*channels float。

### `exr_stretch_finish`

**签名** `exr_status exr_stretch_finish(exr_stretch *stretch,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `stretch`：WSOLA 变速对象；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 关闭输入（重复调用无害），随后持续 pull 到 drained；缺失/重入 ARGUMENT、最终帧数溢出 LIMIT、已生成量不一致 FORMAT。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 输入仅借用，输出结构由调用方提供；没有新分配需要释放。

### `exr_stretch_reset`

**签名** `exr_status exr_stretch_reset(exr_stretch *stretch,double rate,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `stretch`：WSOLA 变速对象；`rate`：新倍率 [0.5,2]，采样率/声道保持；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 丢弃全部旧流状态并设置倍率；无效/重入/非有限或 [0.5,2] 外 rate 为 ARGUMENT。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 输入仅借用，输出结构由调用方提供；没有新分配需要释放。

### `exr_audio_output_backend`

**签名** `const char *exr_audio_output_backend(void);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** 无。

**返回与失败** 返回编译后端名称；该目标无后端返回 NULL。不表示当前存在可用设备。

**线程** 无共享可变状态，可并发。

**所有权** 静态字符串，不释放。

### `exr_audio_output_open`

**签名** `exr_status exr_audio_output_open(uint32_t sample_rate,uint32_t channels,exr_audio_output **out,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `sample_rate`：设备采样率，Hz，8000..192000；`channels`：1 或 2；`out`：接收输出端，失败 NULL；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 打开默认设备，初始为活动态；采样率非 8000..192000 或声道非 1/2 ARGUMENT，无编译后端 FORMAT，设备/系统运行库失败 IO，分配 MEMORY。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** out 用 exr_audio_output_free；移动平台 audio session/后台策略由宿主管理。

### `exr_audio_output_free`

**签名** `void exr_audio_output_free(exr_audio_output *output);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `output`：待关闭系统音频输出端。

**返回与失败** 无返回值；NULL 无操作。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 停止/释放设备与队列缓存，消费 output。

### `exr_audio_output_write`

**签名** `exr_status exr_audio_output_write(exr_audio_output *output,const float *samples,size_t frames,size_t *written,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `output`：系统音频输出端；`samples`：声道交错有限 float；`frames`：请求帧数，最多 65536；`written`：接收实际提交帧数，错误时仍有效；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 提交 written 帧，可部分/零写；暂停时为 0。输入被裁剪 [-1,1] 并转 PCM16；无效/非有限数据 ARGUMENT、>65536 帧 LIMIT、设备错误 IO。IO 也可能已提交部分，始终处理 written。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** samples 调用内借用，已接受部分已复制；output 仍由宿主持有。

### `exr_audio_output_pause`

**签名** `exr_status exr_audio_output_pause(exr_audio_output *output,int paused,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `output`：系统音频输出端；`paused`：非零暂停，零恢复；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 暂停/恢复设备；缺失参数 ARGUMENT、设备失败 IO。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 输入仅借用，输出结构由调用方提供；没有新分配需要释放。

### `exr_audio_output_flush`

**签名** `exr_status exr_audio_output_flush(exr_audio_output *output,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `output`：系统音频输出端；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 清除排队音频；无效对象 ARGUMENT、设备失败 IO。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 输入仅借用，输出结构由调用方提供；没有新分配需要释放。

### `exr_audio_output_pending`

**签名** `exr_status exr_audio_output_pending(exr_audio_output *output,size_t *frames,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `output`：系统音频输出端；`frames`：接收估计队列帧数；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 给近似排队帧数，不是采样精确播放时钟；无效参数 ARGUMENT、设备失败 IO。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 输入仅借用，输出结构由调用方提供；没有新分配需要释放。

### `exr_m4b_inspect`

**签名** `exr_status exr_m4b_inspect(const char *path,const exr_control *control,exr_m4b_inspection **out,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `path`：UTF-8 文件路径；`control`：可 NULL；同步进度/协作取消回调与宿主上下文；`out`：接收元数据检查快照；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 读取 ISO-BMFF 元数据，即使 AAC 关闭也可用；支持 iTunes ilst 文本/PNG/JPEG 封面、Nero chpl/引用的 QuickTime 文字章节；参数 ARGUMENT、损坏 FORMAT、预算 LIMIT、读取 IO、另有 MEMORY/CANCELLED。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** out 是独立快照，用 exr_m4b_inspection_free；path/control 仅调用内借用。

### `exr_m4b_inspect_source`

**签名** `exr_status exr_m4b_inspect_source(const exr_source *source,exr_m4b_inspection **out,exr_error *error);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `source`：不可变随机读取源（size/read_at/context/release/control）；`out`：接收元数据检查快照；`error`：可 NULL；接收状态码和诊断文本，不分配内存。

**返回与失败** EXR_OK 读取 ISO-BMFF 元数据，即使 AAC 关闭也可用；支持 iTunes ilst 文本/PNG/JPEG 封面、Nero chpl/引用的 QuickTime 文字章节；参数 ARGUMENT、损坏 FORMAT、预算 LIMIT、读取 IO、另有 MEMORY/CANCELLED。

**线程** 独立输入/输出可在不同线程调用；共享文档、来源、字体和回调上下文须串行，调用期间输入不得变更。

**所有权** out 是独立快照，用 exr_m4b_inspection_free；source 仅调用内借用，从不调用 release。

### `exr_m4b_inspection_free`

**签名** `void exr_m4b_inspection_free(exr_m4b_inspection *inspection);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `inspection`：M4B 独立元数据快照。

**返回与失败** 无返回值；NULL 无操作。

**线程** 同一对象及共享回调上下文的操作由宿主串行；同步回调在调用线程运行，不要重入当前对象。

**所有权** 消费 inspection，释放元数据、章节与封面。

### `exr_m4b_inspection_duration`

**签名** `uint64_t exr_m4b_inspection_duration(const exr_m4b_inspection *inspection);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `inspection`：M4B 独立元数据快照。

**返回与失败** 返回毫秒时长；未知时长或 NULL inspection 为 UINT64_MAX。

**线程** 仅查询不可变数据；可并行只读，但不得与释放、引用计数变更或底层来源变更并发。

**所有权** 输入仅借用，输出结构由调用方提供；没有新分配需要释放。

### `exr_m4b_inspection_metadata`

**签名** `const exr_metadata_entry *exr_m4b_inspection_metadata(const exr_m4b_inspection *inspection,size_t *count);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `inspection`：M4B 独立元数据快照；`count`：可 NULL，接收元数据数量。

**返回与失败** 返回元数据数组；NULL inspection 返回 NULL/count=0。

**线程** 仅查询不可变数据；可并行只读，但不得与释放、引用计数变更或底层来源变更并发。

**所有权** 借用到 inspection_free，不单独释放。

### `exr_m4b_inspection_chapters`

**签名** `const exr_audio_chapter *exr_m4b_inspection_chapters(const exr_m4b_inspection *inspection,size_t *count);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `inspection`：M4B 独立元数据快照；`count`：可 NULL，接收章节数量。

**返回与失败** 返回章节数组；NULL inspection 返回 NULL/count=0。

**线程** 仅查询不可变数据；可并行只读，但不得与释放、引用计数变更或底层来源变更并发。

**所有权** 借用到 inspection_free，不单独释放。

### `exr_m4b_inspection_cover`

**签名** `const void *exr_m4b_inspection_cover(const exr_m4b_inspection *inspection,size_t *size,const char **media_type);`

**ABI** 稳定。声明：[audio.h](../include/exr/audio.h)。

**参数** `inspection`：M4B 独立元数据快照；`size`：可 NULL，接收封面字节数；`media_type`：可 NULL，接收 image/png 或 image/jpeg。

**返回与失败** 返回封面字节；无封面/NULL inspection 返回 NULL、size=0、media_type=NULL。

**线程** 仅查询不可变数据；可并行只读，但不得与释放、引用计数变更或底层来源变更并发。

**所有权** 字节与 MIME 字符串借用到 inspection_free。


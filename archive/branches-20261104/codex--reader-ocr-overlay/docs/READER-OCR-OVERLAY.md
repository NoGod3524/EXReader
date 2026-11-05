# J15 — 扫描页 OCR 临时文字覆盖层（`reader_ocr_overlay`）

**组件**：`apps/reader/ocr-overlay`（公开 C ABI + 独立 CMake 安装包）
**消费者**：`tests/reader_ocr_overlay/consumer`（安装后 C 与 C++ 消费者）
**云端作业**：`.github/workflows/reader-ocr-overlay.yml`
**固定起点**：`f43baf9182d75907c0cb5d6f77048f27bca8c950`　**分支**：`codex/reader-ocr-overlay`
**受测源码**：`614b14ab6d031c3571e8b60d7c3d615b33878867`

本页只记录本包自己的模块级结论。产品接线（四套宿主、默认 reading 配置）由 root 负责；未接线不授予宿主功能。

## 1. 它是什么 / 不是什么

把**一张已渲染的 SDK 固定页**识别成会话内的临时文字/区域快照，并把每个识别框映射回页面坐标。用于扫描页的阅读辅助。

* 不是原生 PDF/页面文字：`info->native_text` 与 `info->permanent_anchor` 恒为 `0`，`info->source` 恒为 `tesseract-ocr`。
* 不写 SDK notes、书库、阅读进度、文字层，也不改原件字节；除后端读取语言模型外不打开文件。
* 不产生 `exr_fixed_anchor` / reading anchor。`reader_ocr_overlay_to_fixed_text` 产出的 `exr_fixed_text` 只供会话内 find/select/hit，禁止持久化为锚点。
* 不随默认 reading 包启用；不新增常驻服务、WebView、插件框架或第二套解析器。

## 2. 契约（实现即文档）

| 项 | 行为 |
| --- | --- |
| 输入 | `recognize_page`：`exr_fixed_document` + 页号 + `scale`；`recognize_bitmap`：宿主位图（灰/RGBA），尺寸须等于 `exr_viewport_create` 在该 scale 下的 `ceil` 尺寸 |
| 输出 | 拥有的 `reader_ocr_overlay`：行记录 + 词记录、UTF-8 文本、页面坐标 quad、Tesseract 置信度 0..100 |
| 内存归属 | 位图/几何仅借用一次调用；快照私有复制所有字符串与记录，可活过位图、文档与引擎 |
| 线程 | 引擎绑定打开线程；异线程调用（含 close）返回 `THREAD` 且不改变状态 |
| 重入 | 从同一引擎的 control / still-current 回调内调用返回 `BUSY` |
| 提交边界 | 仅 `OK` 产生快照；其余状态 `*out` 保持 NULL，无半成品记录 |
| 取消 | 合作式：渲染与识别期间轮询 `exr_control.cancelled`，提交前再轮询一次 |
| 截止时间 | `timeout_ms` 以经过时间覆盖渲染+识别；模型加载（`engine_open`）在其外 |
| 硬上限 | 64 Mpx / 20 000 条记录 / 4 MiB 快照 / 300 s / scale ≤ 16；默认 16 Mpx / 5 000 / 1 MiB / 30 s |
| 旋转 | 送后端的位图按 `(720 - geometry.rotation - content_rotation) % 360` 顺时针矫正，页面 quad 与旋转无关 |
| 失效 | `check_current` 比较页 id、几何、scale、（可选）位图尺寸 + 像素 FNV-1a；`still_current` 把关提交 |

错误码：`OK / ARGUMENT / MEMORY / LIMIT / CANCELLED / TIMEOUT / MODEL_MISSING / BACKEND / RENDER / STALE / BUSY / THREAD`，`sdk_code` 保留底层 `exr_status`。

## 3. 安装与消费

```
cmake -S apps/reader/ocr-overlay -B build/overlay -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_PREFIX_PATH="$SDK;$OCR" -DCMAKE_INSTALL_PREFIX="$PREFIX"
cmake --build build/overlay && cmake --install build/overlay
```

```cmake
find_package(EXReaderOCROverlay 0.1.0 EXACT CONFIG REQUIRED)
target_link_libraries(app PRIVATE EXReaderOCROverlay::reader_ocr_overlay)
```

依赖只读：冻结 SDK `EXReader::exr_core`（3.40.0 / ABI1，SDK 提交 `9854061be331fe603a1822d9b2b36ee357154927`）与可选适配器 `EXReader::exreader_ocr`（`extras/ocr`）。二者都必须来自**安装前缀**；本包不读 SDK 私有头、不重建 Tesseract。

## 4. 云端验收做了什么

作业矩阵 `overlay (ubuntu-24.04)` 与 `overlay (macos-14)` 各自完成整套流程，全部动作只在 GitHub Actions：

1. **守卫**：`HEAD == GITHUB_SHA`；`f43baf91` 是祖先；保护树（`src/ include/ cmake/ CMakeLists.txt tests/fixtures/ bindings/ native.yml reliability.yml`）与 SDK 冻结提交逐字相等；`apps/reader/store/001_catalog.sql` 与起点相等；`git diff --name-only f43baf91 HEAD` 全部落在本包白名单。
2. **依赖**：`libtesseract-dev`/`libleptonica-dev`/`pkg-config`/`ninja`/`python3-pil`/字体；tessdata_fast `eng`+`chi_sim` 与 `LICENSE` 按提交 `87416418657359cb625c412a48b6e1d6d41c29bd` 下载，并写 `identity.json`（仓库/提交/Apache-2.0/逐文件 sha256）。
3. **构建链**：未改动的 SDK（`-B …/sdk-build`，装到独立 `…/sdk` 前缀）→ `extras/ocr` → 本包；两份安装前缀里只有公开头与导出的 CMake 包。
4. **夹具**：`make_fixtures.py` 当次生成 900×1200 合成清洁扫描页与纯图像页，记录每个词的实测墨迹框、字体身份与逐文件摘要，并写探针用的 `lines.tsv`。
5. **消费者**：`tests/reader_ocr_overlay/consumer` 只 `find_package(EXReaderOCROverlay 0.1.0 EXACT CONFIG)`；C11 消费者（`api.c`，不需模型）与 C++ 探针（`probe.cpp`，8 页固定文档 + 真实 Tesseract）。
6. **判分**：`check_overlay.py` 先散列夹具与模型，跑探针，再核对 55 项具名结论、夹具/模型/二进制身份、`accepted` 与 `source/run/attempt`，写 `report.json` 与 `summary.json`（含 report 摘要）。
7. **同次工件汇总**：`check_artifacts.py` 用 GitHub API 逐个下载本次 run 的 ZIP，比对 API 的 id/字节/digest/有效期/head_sha，重算 ZIP 摘要，并在 ZIP 内重算 report、results、夹具、模型、消费者二进制与清单的摘要；缺失/跨源码/跨 attempt/篡改一律拒绝。

## 5. 具名结论（本轮真实结果）

run **40127504830**，attempt **1**，源码 `614b14ab6d031c3571e8b60d7c3d615b33878867`：

| job | ID | 结论 |
| --- | --- | --- |
| `overlay (ubuntu-24.04)` | 120971969878 | success |
| `overlay (macos-14)` | 120971969787 | success |
| `same-run artifact evidence` | 120972221425 | success（`accepted=true`，`problems=[]`） |

两个平台都是 **55 项具名结论：PASS 53 / SKIP 2 / FAIL 0 / PENDING 0**。关键观测：

| 结论 | Linux 观测 | macOS 观测 |
| --- | --- | --- |
| `recognize_page_source_labels` | Tesseract 5.3.4，`dpi=300`，12 条记录 | Tesseract 5.5.3，`dpi=300`，12 条记录 |
| `render_fixture_page` | 900×1200 RGBA，暗像素 13 303 | 900×1200 RGBA，暗像素 12 660（字体不同） |
| `recognize_page_line_and_word_mix` | 4 行 + 8 词 | 4 行 + 8 词 |
| `recognize_page_locate_rows` | 4/4 定位到实测墨迹框 | 4/4 |
| `recognize_page_pixel_quad_consistent` | 页面/位图 quad 互映偏差 0.000000 | 0.000000 |
| `recognize_page_confidence_filter` | 以 96.85 为下限，12 → 1（真实掉落） | 以 96.90 为下限，12 → 1 |
| `rotation_90/180/270_page` | 均 4/4；`clockwise` 270/180/90 | 同 |
| `rotation_quads_invariant` | 三种旋转相对未旋转页最大偏差 0.000000 | 0.000000 |
| `content_rotation_90_upright` | 页内顺转 90° 仍 4/4 正立定位 | 同 |
| `scale_1_5_page` / `_quads_agree` | 1350×1800、dpi 450、4/4；偏差 0.667 页面单位 | 4/4；偏差 0.333 |
| `blank_page_empty` / `bars_page_no_letters` | 0 条/空文本/空 `exr_fixed_text`；图像页 0 条无字母 | 同 |
| `cancel_before_render` / `cancel_during_recognition` | 均 `CANCELLED` 且 `*out` NULL（后者第 30 次轮询） | 同 |
| `timeout_deadline` | `timeout_ms=1` + scale 2.0 → `TIMEOUT` | 同 |
| `stale_still_current` / `still_current_commits` | 0 → `STALE`；1 → 提交 | 同 |
| `missing_model_directory` / `_file` / `empty_model_file` | 三条路径均 `MODEL_MISSING` | 同 |
| `limit_pixels_before_render` | `LIMIT`，provider 调用 0 次 | 同 |
| `limit_snapshot_budget` | `LIMIT`（后端输出预算先触发，`sdk_code=6`） | 同 |
| `render_failure_propagates` | provider 返回 `EXR_IO` → `RENDER` + `sdk_code=EXR_IO` | 同 |
| `busy_reentrant` | 回调内嵌套 → `BUSY`，外层 `OK` | 同 |
| `to_fixed_text_lines` / `_words` / `_independent` | 4/8 条区域，find/hit/select 命中；释放快照后文本仍有效 | 同 |
| `thread_foreign_call_rejected` / `_close_rejected` | 异线程 `THREAD`，拒绝后引擎仍可用 | 同 |
| `document_untouched` | 内存 754→754，文本 provider 仍 `EXR_FORMAT(5)`，页 id 不变 | 同 |
| `model_chi_sim` | `eng+chi_sim` 可打开 | 可打开 |
| `windows_host_scope` / `mobile_host_scope` | 显式 SKIP（未实测不授予） | 同 |

工件（同一 run/attempt，都在 Actions 内下载并重算摘要）：

| 名称 | ID | 字节 | sha256 | 有效期 |
| --- | --- | --- | --- | --- |
| `reader-ocr-overlay-Linux-40127504830-1` | 12573648790 | 5 327 270 | `6d7f157dab1e962078c469d93786cfec58aabf08f78b9164d46d44d957cf62d1` | 2027-01-22T19:55:47Z |
| `reader-ocr-overlay-macOS-40127504830-1` | 12573409160 | 5 146 619 | `f51f2473d2531ce2bc682836a9af513d2c2a7d02ed2f8925b01dc078659746ad` | 2027-01-22T19:55:47Z |
| `reader-ocr-overlay-evidence-40127504830-1` | 12572694090 | 1 888 | `4edeff8a0b895a70f5a573a9a01b37e22dc929026f35963d5d3ea554009030cd` | 2027-01-22T19:55:47Z |

消费者二进制（ZIP 内重算）：Linux `reader-ocr-overlay-probe` 1 369 992 B `fbd9c4f8…786dc5b1`、`reader-ocr-overlay-c-consumer` 1 141 792 B `c20f0a42…d889f3cb`；macOS `probe` `2bc6dbd2…818665df`、`c-consumer` `cdb77b18…626291f3b`。

`docs/validation/reader-ocr-overlay.json` 与本页绑定同一 `source`/run/attempt。

## 6. 保留的失败（未删除、未改断言）

| run | 根因 | 处理 |
| --- | --- | --- |
| 40123250843 | SDK 装到 `build/j15/sdk`，与构建树同目录，`EXReaderConfig.cmake` 指向不存在的 `EXReaderTargets.cmake` | 构建目录与安装前缀分离 |
| 40123989938 | 适配器导出名是 `EXReader::exreader_ocr`，包内误写 `EXReaderOCR::exreader_ocr` | 改用真实导出名 |
| 40124528190 | `-Werror=format-truncation`：256 字节的 SDK 消息塞进 160 字节错误字段 | `fail()` 改有界拷贝；模型缺失消息走 `std::string` |
| 40125032038 | 探针把 `exr_fixed_load_text` 的 `exr_status` 塞给 `Status` | 改为 `exr_status` |
| 40125410749 | 页面 provider 传给 draw sink 的矩阵语义错（应传 `(u,v)∈[0,1]²` 归一化纹理变换），整页白纸，20 项识别结论失败 | 按 CBZ 页面 provider 的 `m*[w,0,0,h,0,0]` 约定修正，并新增暗像素守卫 |
| 40125893580 | 诊断轮（取 detail 用），保留 | — |
| 40126276548 | 工件校验按 `j15/…` 找成员，实际上传根是 `build/j15` | 成员改为 `evidence/…`、`fixtures/…` 等 |
| 40126918224 / 40127068074 | 单平台（Linux）绿轮，被后续提交取代 | 保留为过程证据 |

同批还有三次 run 的 `overlay (macos-14)` 作业在排队 18 分钟以上仍未启动（GitHub 侧 macOS runner 供给），最终由 40127504830 正常跑到并全绿；排队本身不改写任何断言。

## 7. 未覆盖 / 明确不授予

* **Windows 宿主**：本包 CI 不跑 Windows；`windows_host_scope` 显式 SKIP。
* **Android / iOS 宿主**：同上，`mobile_host_scope` SKIP。
* 真实用户扫描件质量（污点、倾斜、手写）：夹具是合成清洁印刷页，只证明“同一管线能识别并定位确定夹具”，不证明扫描鲁棒性。
* 中文/其它语言的识别准确率：只验证 `eng+chi_sim` 能开模型，未做中文 CER/WER 评测。
* 硬 CPU/RSS 隔离：`timeout_ms` 是合作式截止，不是硬上限；需要硬上限时由宿主把后端放进子进程。
* 宿主 UI 接线、默认 reading 配置、产品事务/sidecar：不在本包范围。
* 冻结适配器的边界框约定在旋转后带来约 1 页面单位的边角偏移（见 `pixel_quad` 说明），本包未改适配器。
* macOS/Linux 的字体不同（Arial vs DejaVuSans），所以两平台工件里的 PNG 摘要不同；跨平台约束的是**结论状态与夹具文本**，不是位图字节。

## 8. 复现

```
git checkout codex/reader-ocr-overlay            # 或指定完整 SHA 614b14ab
gh workflow run reader-ocr-overlay.yml --ref codex/reader-ocr-overlay
```

作业内等价步骤（与 workflow 同序）：`make_fixtures.py --out <dir> --font <font>` → 构建/安装 SDK、`extras/ocr`、本包 → 编译 `tests/reader_ocr_overlay/consumer` → `check_overlay.py` → `check_artifacts.py`。本地不构建、不跑探针、不下载工件。

# HANDOFF-RESULT-C06（accepted=false，三轮 CI 用尽，未通过）

分支 `codex/reader-next-c06`，固定起点 `e67d87cbeabb2457e0852f681ef0b27b2c0da4d8`，既有导入源码取自 `9c7e276f13f42cb61a32507c36d1c22c4489bd01`。
受测源码（最后一轮）`1015f2ca397c6411e6f67fc061ce64ee2e57384c`；本文件封存提交带 `[skip ci]`，不是受测源码。

## 已实现（源码，设计见 `docs/reader-next-c06/RAW3-PORTABLE-ANNOTATIONS.md`）

* 旧 `annotation-export` 头文件、旧 `annotation-import` 头文件与旧导入源码前缀字节不变；raw 入口为新增头文件
  `reader_annotation_export_raw3.h`／`reader_annotation_import_raw3.h`，仅在 `-DEXR_READER_SELECTOR_BYTES_CANDIDATE=ON` 时编译安装，
  包版本 0.2.0，EXACT 依赖 Revisions 0.4.0／ReadingState 0.2.0；默认仍 0.1.0。
* 新格式 `exreader-annotation-export-raw3` v1：原件字节长度、每头独立解码的 `location`（NULL／已分配空值／NUL 与字节长度、源 anchor1/2/3、parser、路由），
  导入端逐字节比对。导入：预览（只读）／显式提交（需预览指纹）、原件身份核对、宿主公开 FOUND 回调、NULL 保留不可导航、不伪造祖先。

## CI 轮次（均 attempt 1，全部失败，保留）

| 轮 | run | 源 SHA | 结果 |
|---|---|---|---|
| 1 | 40227792202 | bb6e83e0 | 两平台失败：我对默认库的“无 raw 字符串”判定过宽（命中 Markdown 三元表达式里的 “raw3” 字面量）。该字面量已移入 `#ifdef`。 |
| 2 | 40228225687 | 178b1351 | 两平台失败：旧导出遇 raw store 实际返回 `ARGUMENT`（revision_code=1），我预期 `REVISION`；已按真实行为改预期并改文档。 |
| 3 | 40228668273 | 1015f2ca | 两平台失败：**raw 导出遇旧 store 实际返回 `REVISION`(3)，revision_code=1**（旧导出遇 raw store 却是 `ARGUMENT`，两个方向状态码不一致，属真实行为，不是被吞掉的错误）。测试预期写成了 `ARGUMENT`，未修。 |

第三轮工件（原 ZIP，均 attempt 1，有效期至 2027-01-23）：Linux `12611877471`（6,165,739 B，sha256 `c7ea6c8dadf1fbe8acf8c27335bc1e6c03bcb3b37a8971fcdfc8528fb5ff3cf7`）、
Windows `12612592211`（5,702,925 B，sha256 `2eeaf7bdb3fa3eecb3ed45d090d39a27df57f35e1378d61562d5028f2c920626`）、
evidence `12611962526`（失败汇总）。作业：Linux `121275506574`，Windows `121275506401`，evidence `121276519619`。
第 1、2 轮工件：run 40227792202 → Linux 12611796618／Windows 12612001997；run 40228225687 → Linux 12611548199／Windows 12611792207。

## 第三轮已通过（两平台，到失败点之前）

保留起点／SDK 冻结树／所有权守卫；产品、SDK 3.41、默认(0.3/0.1)、基线(固定源码)、raw(0.4/0.2)三套安装族构建；四个混配 configure 拒绝；
默认安装头文件与基线逐字节一致、默认库无 raw 符号；legacy 导出字节在 基线／默认／raw 构建三者一致（旧 JSONL v1 头不变）；
raw 种子（真实 PDF，anchor3，含 NULL／空值／NUL）、四本书 raw3 导出及 Python 独立解析（location 与 wire 独立重算一致、footer、源 anchor1/2/3、NULL／空值／NUL 字节长度、墓碑、Markdown 标记）、旧导出拒绝 raw store 且无输出。

## 未验证 / 未执行（因第三轮在“raw 导出遇旧 store”处中止）

之后的全部阶段**从未运行**：预算超限、混用导入拒绝、预览／指纹确认／取消续传／重复导入、公开 FOUND（PDF、anchor1/2、歧义不被旧偏移打破）、
全部负例文件、冲突 ID 预检，以及复用固定 Mac 认证包（15dab6b2 / run 40196978163 / ZIP 12600789926）的真实记录往返与 NULL 负例。
因此 raw 导入器（`annotation_import.cpp` 新增段）**尚无任何运行证据**，只有编译通过（两平台 MSVC/GCC 的 -Werror 构建成功）。
修复只需把测试里 raw 导出遇旧 store 的预期改为 `REVISION`；按规则不再开第四轮。

## 其他如实说明

* 违规一次：在本地对 `run.py` 做过一次 `ast.parse` 语法检查（未编译、未运行任何构建或测试）；其余构建／测试均仅在 Actions。
* 未改任何其他 owner、SDK 冻结树、raw 七模块；未发布 PR/tag/Release；未派子代理。
* 未授予：宿主 UI、真机、性能、Windows 长路径、Apple/Android 构建、最终 root 对新 portable 契约的审查。

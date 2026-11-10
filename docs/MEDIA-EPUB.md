# EPUB 音频/视频/Media Overlay

引擎只做**识别 + 给数据**，不解码、不播放、不联网。播放由宿主负责。

## 引擎现在提供什么

| 能力 | 接口 | 说明 |
| --- | --- | --- |
| 媒体元素识别 | `exr_document_media(doc, &n)` | 每个部件（`exr_publication_load` 得到的文档）一张表，覆盖 `<audio>`、`<video>`、`<object>`、`<embed>` |
| 可见占位 | 部件正文文本 | 每个媒体元素在正文里是一个独立段落，如 `[Audio: tone.mp3, 0:04]`；不再是空白 |
| SMIL 解析 | `exr_publication_media_overlay(pub, part, &ov, &err)` | 每个 `<par>` → 文本片段（部件号 + UTF-8 偏移区间）↔ 音频片段（路径 + 起止毫秒）；`exr_media_overlay_free` 释放 |

### 媒体表（`exr_media_item`）

`kind`（audio/video/embedded）、`state`、`flags`、`element`/`placeholder`（节点下标）、`src`（原写法）、
`path`（容器内规范路径）、`media_type`（manifest 优先，其次 `type` 属性，再次扩展名）、`poster`、
`duration_ms`（未知为 −1）、`source_count`（`src` + `<source>`/`<param>` 候选数）、`label`（占位文字）。

`state`：

| 值 | 含义 | 占位文字 |
| --- | --- | --- |
| `AVAILABLE` | 书内存在且是 audio/video 类型 | `[Audio: 文件名, m:ss]`，时长未知为 `duration unknown`，估算为 `about m:ss` |
| `MISSING` | 引用的本地文件不在书内 | `[Audio unavailable: 路径 is missing from this book]` |
| `UNSUPPORTED` | Flash/WMV/FLV/RealMedia/MIDI/Java 等过时类型，或 `<object>`/`<embed>` 的非音视频类型 | `[Video not supported: 文件名 (类型)]` |
| `REMOTE` | 带协议的外部地址（`http:`、`data:` 等）；引擎从不取回 | `[Video is online: 地址 - not loaded]` |
| `NO_SOURCE` | 没有 `src`/`<source>` | `[Audio: no source given]` |

`flags`：`AUTOPLAY`、`LOOP`、`CONTROLS`、`MUTED`、`HIDDEN`（不画占位）、`COVER`（祖先带 `epub:type="cover"`/`doc-cover`，或部件路径含 cover）、
`BACKGROUND`（audio + autoplay + loop 且无 controls）、`DURATION_ESTIMATED`。

占位文字取代元素自带的后备内容（如 “Your browser does not support audio”），避免与可播放文件的标签互相矛盾。
`<object>` 指向图片/SVG/XHTML 时不算媒体，保持原行为（不显示）。

### 时长从哪来

只读容器头：WAV（`fmt`/`data`）、MP3（Xing/Info 帧数；无则按首帧码率估算并置 `DURATION_ESTIMATED`）、
MP4/M4A/MOV（`moov/mvhd`）。其他格式（Ogg/WebM/FLAC 等）为未知。超过 32 MiB 的成员不读取（时长未知）。

### SMIL（`exr_media_overlay`）

- 定位：部件对应 manifest 项的 `media-overlay` 属性 → SMIL 项；`media:duration`（`refines` 该 SMIL 项）、全局 `media:active-class`、`media:playback-active-class` 一并返回。
- 每个 `<par>` 取其 `<text src="部件#片段">` 与 `<audio src clipBegin clipEnd>`；嵌套 `<seq>` 递归（上限 64 层）。
- 时间支持完整/部分时钟值（`0:00:01.500`、`1:05`）与带单位的计时值（`1.5s`、`3000ms`、`2min`、`1h`）。`clipEnd` 缺省为 −1（播到媒体结尾）。
- 文本区间是**该部件加载后** `exr_document_text` 的 UTF-8 偏移（半开区间），与高亮/CFI 使用同一坐标；找不到片段时为 `SIZE_MAX` 并计入 `unresolved_text`；音频不在书内计入 `missing_audio`。
- 声明了 `media-overlay` 但 SMIL 缺失或不合法时返回 `EXR_FORMAT` 与可读消息；部件正文读取不受影响。没有声明时 `*overlay` 为 NULL 且返回 `EXR_OK`。

## 已知限制

- 占位文字只在“完整部件文档”路径出现；超大章的有界章窗口（`chapter_window`）按原行为不处理媒体。
- 占位文字是英文固定串；宿主要本地化请用 `kind`/`state`/`duration_ms`/`path` 自行生成。
- 引擎不检查编码格式是否真能被宿主解码，只按类型/扩展名判断“过时类型”。

## 要让宿主真正播放，引擎还需要提供什么（未实现）

1. **页面上的媒体位置**：布局目前没有输出占位段落在页内的矩形。宿主要叠加原生播放控件，需要 `exr_layout` 提供 “页内媒体框列表”（媒体项下标 + 矩形）。现在只能用文本范围 `placeholder` 节点的 `start/end` 加 `exr_hit_test`/范围矩形自行推算。
2. **点击命中 → 媒体项**：需要 `exr_document_media_at(doc, offset)`，由文本偏移直接返回媒体项。
3. **流式/随机读取成员**：`exr_document_resource` 一次拷贝整个成员；长音频/视频需要按范围读取（或导出到临时文件、返回可被系统播放器打开的路径）。内部已有带预算的分配器接口，尚未公开。
4. **按时间找句子**：宿主播放时需要“当前音频 + 毫秒 → 要高亮的文本区间”，即 `exr_media_overlay_clip_at(...)`，且要跨部件按阅读顺序拼接叠加累计时间；目前宿主需自行遍历 `clips`。
5. **高亮样式**：`media:active-class` 已给出，但把区间画成页内矩形需要宿主用现有范围/命中 API 完成。
6. **更多时长/元数据**：Ogg/WebM/FLAC 时长；`<track>` 字幕；封面视频的 `poster` 图片解码交给宿主（路径已给出）。
7. **大章窗口一致性**：`chapter_window` 路径要同步占位文字，否则同一本书在两条路径下文本偏移会不同。

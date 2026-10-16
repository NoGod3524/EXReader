# 框架 API（0.2.0）

所有入口由 `src/index.js` 导出；公开方法仍为实验性 API。

## 书库

`createLibrary({ name = 'exreader', storage } = {})` 返回独立书库服务。默认 IndexedDB 名称与旧阅读器一致，可直接读取旧书库；自定义 `name` 隔离多个书库。调用 `close()` 释放连接。`storage` 可注入实现 `src/store.js` 返回对象的方法集，渲染层与存储不绑定。

| 方法 | 结果 |
| --- | --- |
| `importFile(file)` | `{ book, duplicate }`，以文件名、大小、修改时间检查本实例书库重复 |
| `listBooks({ query, filter, sort })` | Book 数组；filter 为 all / reading / favorite / audio / finished，sort 为 recent / added / title |
| `getBook(id)`, `getFile(id)` | Book 或原始 File；不存在的书籍记录抛错，原文件不存在返回 undefined |
| `updateBook(id, patch)` | 新 Book；仅允许 title / author / tags / favorite / status / cover |
| `setCover(id, file)` | 验证并缩小封面；传 null 清除封面 |
| `saveProgress(id, location)` | 保存 progress（0–1）、cfi、page（1 起）、seconds；更新 lastRead |
| `removeBook(id)` | 同一事务删除书籍、原文件及关联标注 |
| `listNotes(bookId?)` | 指定书籍或全部标注 |
| `saveNote(bookId, data)` | 返回标注；data 可包含 id / quote / note / value（CFI）/ page / rects / seconds；同 id 更新 |
| `removeNote(id)` | 删除标注 |
| `exportBook(id, format = 'original')` | Blob / File；输出 original / epub / txt / html / fb2 / rtf / docx |
| `createBackup()`, `restoreBackup(blob)` | ZIP Blob；恢复返回书籍数，同 ID 书籍被备份覆盖、标注按 ID 合并 |
| `exportNotes()` | Markdown Blob |
| `close()` | 等待本实例正在进行的修改，然后关闭存储 |

Book 字段兼容旧版：id / filename / size / modified / added / format / audio / title / author / cover / tags / favorite / status / progress / lastRead，阅读位置包含 cfi / page / seconds。同一服务实例串行处理修改；独立实例 / 多标签页并发修改暂不提供跨实例锁。搜索目前在内存执行，不适合百万级书库。

## 格式与正文

`supports(filename)`、`extension(filename)`、`supportedFormats()` 可在无 DOM 环境查询能力，支持 `.fb2.zip` 等复合扩展名。格式清单描述的是内置适配能力，未实现任意第三方插件自动发现。

`readMetadata(file)`、`openReflow(file, encoding = 'auto')` 在浏览器环境提取信息 / 解析流式书籍。返回 Foliate Book 模型，调用者负责 `destroy()` 回收资源。CBZ 返回固定布局模型。

`createReader(container, file, book, notes = [], callbacks = {})` 创建正文渲染器，无工具栏。宿主设置容器尺寸，并引入 `src/render.css`。回调有 relocate(location)、settings()、keydown(event)、error(error)，`DEFAULT_SETTINGS` 提供排版默认值。`settings()` 返回当前排版设置，调用 `reader.apply()` 应用。

渲染器提供 toc、next / prev / seek / goTo、selected / location、addAnnotation / removeAnnotation、search、apply、close。音频额外提供 `media`（HTMLAudioElement），宿主自行提供播放 / 暂停 / 倍速控件，框架不显示原生 controls。

标注新增 / 删除后，宿主需要同步更新传给渲染器的 notes 数组，再调用 addAnnotation / removeAnnotation。进度持久化由 relocate 回调完成。宿主关闭渲染器前应等待自己的持久化任务。

`await configurePDF({ cMapUrl, standardFontDataUrl, wasmUrl })` 配置资源位置（目录 URL 以 `/` 结束）。`convert(file, book, format)`、`notesExport(notes, books)` 返回 Blob，可独立于书库使用。

## 内容安全

书籍内容视为不可信输入，保留 DOMPurify 清理、禁用内容脚本和外部资源过滤。宿主仍应配置 CSP：禁止书籍脚本、远程跟踪资源、表单与对象嵌入；参考旧阅读器 `index.html` 的策略。宿主界面显示书名和笔记时使用 `textContent` 或 HTML 转义。

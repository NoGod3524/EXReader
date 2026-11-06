# Real books · Pass A · 2026-11-05

后续验收：扫描构造件已获 owner 确认并登记；真实竖排缺口的 CSS 属性别名修复及 462 页自洽性检查见 [CSS-ALIASES.md](CSS-ALIASES.md)。原始 15 本与补充样本的旧二进制结果仍保留用于追溯。

语料为本地商业书，不入库；本目录只含元数据与结果。书籍、封面、渲染位图和正文片段均未写入本目录或仓库。

状态：负例复核完成；三个损坏/错格式输入均被拒绝。原始实测 16 个文件，其中 1 份重复；RESULTS.csv 去重后为 **15 本**（13 EPUB / 1 MOBI / 1 PDF），通过 **15**、失败 **0**、未执行 **0**。未记账。详见 [负例实际输出与去重记录](NEGATIVE-CONTROLS.md)。

## 语言分布（去重后的15本）

逐本按 EPUB OPF 的 dc:language（若有）及本地全文词频/文字系统复核；全文只在内存中处理，未保存正文、片段或词表。逐文件语言元数据与统计计数见 [LANGUAGES.csv](LANGUAGES.csv)。

| 语言 | 原始15本 | 补充公开样本（不计入15本） |
| --- | ---: | ---: |
| 英文 | 13 | 0 |
| 葡语 | 1 | 0 |
| 日文 | 0 | 1（草枕） |
| 意大利语 | 1 | 0 |
| 合计 | 15 | 1 |

- **Pachinko 是葡语版本**，OPF声明 `pt`，与 owner 视觉确认及全文词频一致；不能按英文书名归为英文。
- 另核得 **Crying in H Mart 是意大利语版本**，OPF声明 `it-IT`，全文意语标记计数10876、英语31；因此不能为了只列英/葡/日三种而把它并入英文或葡语。
- 草枕为日文公开补充样本；扫描构造件来自已有英文 Malcolm X，不重复计作品数。
- 每行字符数、行宽体验的比较必须保留语言及字体条件，不将葡语/意语样本标为英文统计。

### CJK 验收口径

“每行28–34汉字”的现有样本验证仅限日文补充样本《草枕》；原15本没有中文样本。中文行宽仍缺验证，补齐需另行提供中文书，不把日文观察记为中文通过。第3步后的独立中文验收见 [最小清单](CJK-READABILITY-CHECKLIST.md)。

缺口归属已分开：宿主第3步负责正文行宽与上边距；作者CSS未指定时的CJK默认2em缩进是第5步设置项（本次两书均有声明，见 [TEXT-INDENT.md](TEXT-INDENT.md)）；断词归后续引擎版本、不在2a范围。

Pachinko第257页的“首行齐平／缩进缺失”观察已撤回：[像素判定A](TEXT-INDENT-PIXELS.md)，正文同段首行/续行66/44px，差22px；布局原点差21.600002px，匹配1.2em×18px。作者样式已生效，不登记为引擎缩进缺陷。

后续视觉验收：owner 已确认草枕竖排有效；Pachinko第257页已定性为正常章末。详见 [VISUAL-REVIEW.md](VISUAL-REVIEW.md)。SDK最大行宽配置缺口与仅登记的第3步排版项见 [SDK-GAPS.md](SDK-GAPS.md)。

## 隐藏运行证据

本轮未在交互桌面上创建任何可见窗口。仅使用 CLI，未启动 GUI 宿主，也未调用 SetForegroundWindow、鼠标或键盘注入。
- 每一次书籍 CLI 均通过 `Start-Process -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput <external-temp> -RedirectStandardError <external-temp>` 启动；父 PowerShell 使用 CREATE_NO_WINDOW（0x08000000）及 SW_HIDE。运行器自身也通过 Start-Process -WindowStyle Hidden -Wait 启动。
- stdout/stderr 先重定向到仓库外临时文件，读取所需 JSON 与错误首行后删除；CSV/本 README 不含原始诊断日志。外部 HIDDEN-CLI-CALLS-3cde779e.jsonl 逐次记录 CLI 名、输入文件名、启动方式、SDK 哈希、UTC 时间与退出码。
- 加入隐藏运行约束前的部分试跑已停止，其数值不复用；本表全部书籍在显式隐藏模式下重新执行。
- 原始 16 文件（含一份重复）的隐藏启动记录：16 / 16。

## 方法与字段

- 源码：main `9733d8fcb46f27ceb79c1dd902b3c00c5320ec89`；引擎报告版本 `3.42.0`。本次未修改产品代码，未运行 CI。
- 逐文件、独立进程、串行执行仓库 `tools/check_document.c`（exreader-check-document），不传 max_pages，以取得完整页数。原 CLI 会逐页验证渲染和固定页文本 API；因此本轮还检查了第一页之后的页面，并非只完成首屏就判通过。
- 原 CLI 无计时字段。外部包装仅拦截相同 open/render API 调用，以 QueryPerformanceCounter 记录耗时，随后返回原状态和原位图；CLI 源文件原样 include。没有替换分页、解析、渲染实现。位图仅在内存中，随后由原 CLI 释放。
- 首屏计时 `first_render_ms` 为第一次栅格化 API 调用的墙钟耗时，不含打开、分页、进程启动或屏幕显示；单位 ms，单次观测，未控制磁盘缓存。打开耗时和进程总耗时见下表。
- 可重排格式参数为 CLI 原值：720×1040，margin=36，font_size=28，line_height=1.5，paragraph_spacing=10；字体为 Windows Arial，书内字体按引擎原逻辑处理。PDF 比例为 min(1,720/max(width,height))。
- `parts` 是引擎 publication parts 数（包含封面等部分），不等同于语义章节或目录标题数；MOBI/PDF 按该 CLI 的单 document 口径为 1。`pages` 是同一字体及上述分页参数下的完整处理页数；失败时若只有部分页数则留空，PDF 能枚举总页数时保留该总数。
- `open=ok` 仅表示 open API 成功；整本通过还要求退出码 0、complete=true、首个 RGBA 位图有效。打开成功仍可能在后续解析/分页或渲染失败。未知值留空，不用 0 代替。
- 每本总进程上限 120s，超时终止并归为“超时”；未自动重试失败文件。`first_error` 只保留错误类型及错误首行，不保存原始 stderr、书内文本或输出图片。
- 复用已验证交付 SDK DLL：来源为 Windows 单作业 run 41909199114 / source 4efd33666640e8bd8409e15c432767572894226c，SHA-256 与既有 build.json 的 files.exreader.dll 一致。其 src/include/cmake/CMakeLists.txt、检查 CLI 与 Windows 入口，与本次 main 逐字节相同（git diff 为空）。外部计时包装与未包装 CLI 在仓库公开 fixture 上的完整 JSON、退出码一致。
- SDK DLL 与两个 CLI 均置于仓库外同一目录，按 Windows 的可执行文件目录优先规则加载该已核验 DLL。构建身份复核前的试跑不计入本表。
- SDK DLL SHA-256：`3cde779eb65b0ace00165b9dbe18d85a44833653d374567301a8a0bf1e0c4ab8`；计时程序 SHA-256：`c0aa73928a5a8458e12e442efed9acdaedc707abbd4073a7e02ba6fca72ce510`；原 CLI SHA-256：`96d31f94a5f4a9a95678db0000ed29d2b7406027fc11d197b6de6e100b895396`；Arial SHA-256：`b3658eadae55e682b5f69eb64c439c1ecc8f196c0bb8d4756d145d13bc86476a`。
- 测量环境：Windows 11 / AMD64；包装编译为 gcc -O2 -std=c11，链接既有 SDK DLL。所有构建与外部运行材料留在仓库外。

## 失败归类

| 类别 | 数量 | 代表文件 |
| --- | ---: | --- |
| 解析失败 | 0 | — |
| 渲染失败 | 0 | — |
| 超时 | 0 | — |
| 其它 | 0 | — |

## Between The World and Me 双版本

| 文件 | bytes | SHA-256 | 打开 | parts | pages | 首次渲染 ms | 整本结果 |
| --- | ---: | --- | --- | ---: | ---: | ---: | --- |
| Between The World and Me (Ta-Nehisi Coates) (z-library.sk, 1lib.sk, z-lib.sk) (1).epub | 415133 | 3d909ac99c4388022a6576475b81c5d458490337aba08b0e7ba311bc18ab68a5 | ok | 14 | 178 | 17.634 | pass |
| Between The World and Me (Ta-Nehisi Coates) (z-library.sk, 1lib.sk, z-lib.sk).epub | 415133 | 3d909ac99c4388022a6576475b81c5d458490337aba08b0e7ba311bc18ab68a5 | ok | 14 | 178 | 17.012 | pass |

- 字节与身份：bytes 相同；SHA-256 相同。
- 能否打开：ok / ok；一致。
- parts 数：14 / 14；一致。
- 完整页数：178 / 178；一致。
- 以上为结构与机器执行比较，不作正文、排版视觉一致性或版本内容完整性的判断。

## 打开与整本处理耗时

| 文件 | open ms | 总进程 ms | 退出码 | 最终阶段 |
| --- | ---: | ---: | --- | --- |
| A Raisin in the Sun (Lorraine Hansberry) (z-library.sk, 1lib.sk, z-lib.sk).epub | 1.486 | 3294.725 | 0 | paginate |
| Between The World and Me (Ta-Nehisi Coates) (z-library.sk, 1lib.sk, z-lib.sk) (1).epub | 1.927 | 2274.724 | 0 | paginate |
| Between The World and Me (Ta-Nehisi Coates) (z-library.sk, 1lib.sk, z-lib.sk).epub | 1.403 | 2297.557 | 0 | paginate |
| Black Boy (Richard Wright) (z-library.sk, 1lib.sk, z-lib.sk).epub | 2.105 | 7343.563 | 0 | paginate |
| Born a Crime (Trevor Noah) (z-library.sk, 1lib.sk, z-lib.sk).epub | 1.524 | 4289.34 | 0 | paginate |
| Crying in H Mart (Michelle Zauner) (z-library.sk, 1lib.sk, z-lib.sk).epub | 2.261 | 4333.695 | 0 | paginate |
| How Does It Feel to Be a Problem Being Young and Arab in America (Moustafa Bayoumi) (z-library.sk, 1lib.sk, z-lib.sk).epub | 1.521 | 5322.637 | 0 | paginate |
| I Know Why the Caged Bird Sings (Maya Angelou) (z-library.sk, 1lib.sk, z-lib.sk).epub | 1.532 | 6309.349 | 0 | paginate |
| Pachinko (Min Jin Lee) (z-library.sk, 1lib.sk, z-lib.sk).epub | 1.708 | 8363.092 | 0 | paginate |
| The Absolutely True Diary of a Part-Time Indian (Sherman Alexie) (z-library.sk, 1lib.sk, z-lib.sk).epub | 2.166 | 4340.089 | 0 | paginate |
| The Autobiography of Malcolm X. (Malcolm X, Alex Haley) (z-library.sk, 1lib.sk, z-lib.sk).pdf | 2.143 | 16663.801 | 0 | text |
| The Distance Between Us A Memoir (Grande Reyna) (z-library.sk, 1lib.sk, z-lib.sk).epub | 2.417 | 6347.579 | 0 | paginate |
| The Fire Next Time (James Baldwin) (z-library.sk, 1lib.sk, z-lib.sk).epub | 1.546 | 2313.222 | 0 | paginate |
| The Fire This Time A New Generation Speaks about Race (Jesmyn Ward) (z-library.sk, 1lib.sk, z-lib.sk).epub | 1.567 | 3290.121 | 0 | paginate |
| The House on Mango Street (Sandra Cisneros) (z-library.sk, 1lib.sk, z-lib.sk).epub | 1.549 | 1269.831 | 0 | paginate |
| Zami A New Spelling of My Name - A Biomythography (Audre Lorde) (z-library.sk, 1lib.sk, z-lib.sk).mobi | 11.003 | 5349.333 | 0 | paginate |

## 复核方式

将 BOOK_DIR 指向原始 FinalBooks，FONT 指向 Arial，TIMED_CLI 指向外部计时程序；逐本执行 `"$TIMED_CLI" "$book" "$FONT"`，不传 max_pages。核对书籍 SHA-256，再比对 CLI 的 parts/pages/status/complete 与本表。不要把输入、解包内容或渲染图片复制到仓库。

通过只代表本轮机器侧打开、完整分页/逐页 API 与渲染返回成功；不代表人工阅读、字体覆盖或视觉质量验收。

## 原始正例调用记录核对

- 隐藏 CLI 调用共 18 次：16 次真书、2 次仓库公开 fixture 对照；每次均记录 `Start-Process -WindowStyle Hidden -Wait`。
- UTC 调用起始范围：`2026-11-06T02:36:01.755100+00:00` 至 `2026-11-06T02:37:23.680600+00:00`。全部进程退出码：0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0。
- 两份 Between The World and Me 除 SHA-256 相同外，也已从原路径按字节直接比较，全等；未复制书籍。

## 扫描/竖排补充覆盖

来源、许可、构造标注和引擎实测见 [SOURCES.md](SOURCES.md)，两项结果单列 [SUPPLEMENTAL-RESULTS.csv](SUPPLEMENTAL-RESULTS.csv)，不改变去重后的 15 本原始语料配额。

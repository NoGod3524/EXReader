# SDK 所有权与生命周期契约

覆盖 `include/exr/*.h` 和聚合头 `include/exreader.h` 的全部公开 `exr_*` typedef 与 `EXR_API` 函数；宏常量不拥有资源。`python tools/check_ownership.py` 检查逐项表格覆盖，正文偶然提及不计入覆盖。

## 共同规则

| 规则 | 契约 |
| --- | --- |
| 拥有 | 成功返回的拥有型结果有一个调用者释放责任；用对应 SDK 释放函数，不能跨 CRT 使用宿主 `free`。指针赋值不新增引用。 |
| 借用 | 不调用释放函数，不修改只读视图；复制含指针结构不会复制其内容。跨 owner 寿命保存时，复制数据或使用独立快照 API。 |
| 保留引用 | SDK 内部 retain 允许子对象活过调用者释放父引用；已经交还的父引用不得继续使用或再次释放。 |
| 失败 | 构造/open 的拥有输出为空；source/provider context 只在成功时转移。回调已经产生的宿主副作用不会回滚。输入有效性和错误码详见头文件。 |
| 宿主值结构 | bitmap、anchor、选项、错误和结果记录可以位于栈上。SDK 只释放自己生成的动态字段；先置零拥有字段，复用前释放旧结果。 |
| 空值 | 释放函数接受 NULL；清空的宿主记录可复用。重复释放保留旧地址的拥有句柄/数组违反契约。 |
| R | 允许不可变数据并发读；释放、引用变更、缓存失效、写入须与读取互斥。 |
| S | 外部串行化同一对象及共享依赖（可包括 const 查询）；锁覆盖借用视图的整个使用期。无共享依赖的对象可在不同线程调用。 |
| T | 单线程所有；dictionary 的创建、调用、释放由同一宿主线程负责。 |
| I | 无共享 SDK 对象；并发调用提供独立可写输出及有效只读输入；共享回调 context 由宿主同步。 |
| C | 回调在发起操作的线程同步执行；允许无关对象/纯值操作。不得修改或销毁活动对象/依赖链；S/T 操作不得重入，R 只读观测允许。 |

## 对象关系与回调

| 关系/场景 | 生命周期或行为 | 释放责任 |
| --- | --- | --- |
| publication → load document | 独立 document 可活过 publication，保留所需源 | `exr_document_free` |
| document/font → 完成的 layout | layout 保留 font/图像；输入 document 与调用者 font 引用可释放 | `exr_layout_free` |
| document/font → 普通 pager | 借 document/context，保留有效 font；document 要活过 pager | `exr_pager_free` |
| publication → session / EPUB pager | 内部 retain，可先释放调用者 publication 引用 | `exr_session_free` / `exr_pager_free` |
| font/context → session | session 借 caller font/context；必须持续有效 | 原 owner 最后释放 |
| session → get document/layout | 借用，下一 get/clear/驱逐/hyphenator 更改/free 后不能沿用 | 不得释放借用子对象 |
| pager → next layout | 独立拥有，可活过 pager；同源资源引用变更串行 | `exr_layout_free` |
| pager → get layout | 借用缓存；驱逐/cache 更改/free 失效 | 不得释放借用页面 |
| fixed document → text/metadata/annotations | 加载结果独立，可活过 fixed document | 对应结果释放函数 |
| audio → audio_player | player retain audio，可先释放 caller audio 引用 | `exr_audio_player_free` |
| text_index → text_query | query retain index，可活过 close；一个 index 一个 query | `exr_text_query_free` |
| library → library_source | retain 数据库，可活过 close；删除 book/其他连接提交使源失效 | `source.release(source.context)` |
| source/provider → 成功 open/create | context 转移，最后引用调用 release；失败不转移 | 宿主不再重复 release |
| dictionary → query results；manager → create_font | 结果独立，可先释放 dictionary/manager | results_free / font_free；faces 用 exr_free |
| part loader / fixed-text provider | 可以创建独立 document/text，成功后移交给 SDK | SDK 负责释放移交结果 |
| fixed draw → 独立 canvas sink | 允许向独立 canvas 绘制；不得再次 draw/free 活动 fixed document | 各自 owner |
| progress/cancel/provider/sink/search 回调 | 活动对象的 S/T 操作拒绝重入，status API 返回 `EXR_ARGUMENT`；Debug 的同对象 free/clear 断言；R 只读观测允许 | 等外层调用返回后释放 |
| audio backend → `exr_audio_player_get` | 允许读观测快照；回调时可能看到上一提交状态；play/pause/seek/report 等重入拒绝 | track_id 仍借 player |
| release 回调 | 只释放 context；不得访问/销毁正在终结的 owner | 成功接管后最终调用一次 |
| SDK 返回的 callback closure | canvas sink 的函数/context 借 canvas；library_source 的 read_at/release 操作拥有的源 context。Debug 调用先验证并保持活动 scope，旧 sink、源释放后 read、源重复 release 均断言 | canvas 由 canvas_free；source 由其 release |

## Debug 验证与计数

| API/机制 | 契约 |
| --- | --- |
| 魔术字和登记 | Debug 分配写入魔术字，销毁清零；入口先查对象外部登记，再读取对象，防止通过悬空对象读取魔术字。 |
| 隔离区 | 已销毁 opaque 句柄的地址保留到诊断 epoch 结束，防止地址复用把旧句柄误认成新对象；对象负载已释放。31 种 opaque 句柄单独计数，SDK 普通分配统一计入 `sdk_buffer`；栈值和借用视图登记不增加拥有对象计数。 |
| `exr_validate(object)` | 检查登记对象/借用视图及依赖链；有效返回 1，NULL/未知地址返回 0，已释放对象或依赖触发带“对象已释放”的断言。验证期间仍须与释放互斥。 |
| `exr_debug_counts(out,capacity)` | 返回全部 31 种 opaque 句柄及 `sdk_buffer` 的类型数（共 32 行），包括 created=freed=live=0 的行；最多写 capacity 行。created/freed/live 是实际对象分配/销毁累计数，不是公共 API 调用数；type 为静态借用名；宿主提供数组。 |
| `exr_debug_cleanup()` | 所有 SDK 调用返回、所有拥有资源释放后终结诊断 epoch；有 live 对象则断言。释放隔离区和借用登记，保留累计计数；此后不能再使用任何旧指针。 |
| Release / `NDEBUG` | 不执行 Debug 契约断言；validate 不检查并返回 1，counts 返回 0，cleanup 无操作。调用者仍须遵守本契约。 |
| 裸 C 指针访问 | `p[i]`、`strlen(p)`、宿主 `memcpy` 不经过 SDK，不能被 SDK 转成契约断言。访问前用 SDK 入口或 `exr_validate` 校验已登记视图，并保持 owner 存活；ASan 检测绕过入口的越界访问。 |

## 全部公开类型

分配/释放列描述 SDK 输出；同名类型作为宿主输入时仍由宿主所有。C 为共同回调规则；纯值没有可重入状态。

覆盖基线：**233/233 类型，430/430 函数**。

### `include/exr/audio.h`

| 类型 | 分配与释放 | 拥有/借用 | 生命周期 | 线程 | 重入 |
| --- | --- | --- | --- | --- | --- |
| `exr_audio` | SDK 分配；调用者用 `exr_audio_free` 释放 | 拥有一个引用；指针复制不增加引用 | 本对象释放后，其借用视图失效 | R；释放/引用变更 S | C |
| `exr_audio_track` | 宿主输入或 SDK 数组 | create 输入借用；getter 借 audio；inspection chapters 借 inspection | getter 至所属 audio/inspection_free；不单独 free | R | C |
| `exr_audio_chapter` | 宿主输入或 SDK 数组 | create 输入借用；getter 借 audio；inspection chapters 借 inspection | getter 至所属 audio/inspection_free；不单独 free | R | C |
| `exr_audio_sync` | 宿主输入或 SDK 数组 | create 输入借用；getter 借 audio；inspection chapters 借 inspection | getter 至所属 audio/inspection_free；不单独 free | R | C |
| `exr_audio_input` | 宿主分配/释放；create 复制所需内容 | 输入指针仅调用期间借用 | create 返回后输入可释放，输出独立 | I | C |
| `exr_audio_position` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_audio_player` | SDK 分配；调用者用 `exr_audio_player_free` 释放 | 拥有一个引用；指针复制不增加引用 | 保留 audio；成功 create 接管 backend.context；free 调 release | S | C |
| `exr_audio_command_kind` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_audio_command` | SDK 临时结构；不释放 | command/source 只借给 callback | callback 返回即失效 | 回调同线程 | C |
| `exr_audio_command_fn` | 宿主提供函数；SDK 不 free | 参数仅回调期间借用；context 见注册输入契约 | 同步调用线程；不得保留临时参数 | C | C |
| `exr_audio_backend` | 宿主输入；SDK 最后引用调 `release(context)` | 元数据复制；context 仅成功时转移；无 release 则宿主持有 | 结构可在 create 后销毁；context 至最后引用释放 | S provider/context | C |
| `exr_audio_playback` | 宿主输出结构 | 数值复制；track_id 借 player | 数值独立；track_id 至 player_free | S player | C |
| `exr_wave` | SDK 分配；调用者用 `exr_wave_free` 释放 | 拥有一个引用；指针复制不增加引用 | 本对象释放后，其借用视图失效 | S | C |
| `exr_wave_info` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_flac` | SDK 分配；调用者用 `exr_flac_free` 释放 | 拥有一个引用；指针复制不增加引用 | 本对象释放后，其借用视图失效 | S | C |
| `exr_flac_info` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_mp3` | SDK 分配；调用者用 `exr_mp3_free` 释放 | 拥有一个引用；指针复制不增加引用 | 本对象释放后，其借用视图失效 | S | C |
| `exr_mp3_info` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_aac` | SDK 分配；调用者用 `exr_aac_free` 释放 | 拥有一个引用；指针复制不增加引用 | 本对象释放后，其借用视图失效 | S | C |
| `exr_aac_info` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_m4b` | SDK 分配；调用者用 `exr_m4b_free` 释放 | 拥有一个引用；指针复制不增加引用 | 本对象释放后，其借用视图失效 | S | C |
| `exr_m4b_info` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_pcm` | SDK 分配；调用者用 `exr_pcm_free` 释放 | 拥有一个引用；指针复制不增加引用 | 本对象释放后，其借用视图失效 | S | C |
| `exr_pcm_info` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_pcm_read_fn` | 宿主提供函数；SDK 不 free | 参数仅回调期间借用；context 见注册输入契约 | 同步调用线程；不得保留临时参数 | C | C |
| `exr_pcm_input` | 宿主输入；SDK 最后引用调 `release(context)` | 元数据复制；context 仅成功时转移；无 release 则宿主持有 | 结构可在 create 后销毁；context 至最后引用释放 | S provider/context | C |
| `exr_stretch` | SDK 分配；调用者用 `exr_stretch_free` 释放 | 拥有一个引用；指针复制不增加引用 | 本对象释放后，其借用视图失效 | S | C |
| `exr_stretch_state` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_audio_output` | SDK 分配；调用者用 `exr_audio_output_free` 释放 | 拥有一个引用；指针复制不增加引用 | 本对象释放后，其借用视图失效 | S | C |
| `exr_m4b_inspection` | SDK 分配；调用者用 `exr_m4b_inspection_free` 释放 | 拥有一个引用；指针复制不增加引用 | 本对象释放后，其借用视图失效 | R；释放/引用变更 S | C |

### `include/exr/base.h`

| 类型 | 分配与释放 | 拥有/借用 | 生命周期 | 线程 | 重入 |
| --- | --- | --- | --- | --- | --- |
| `exr_status` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_format` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_error` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_stage` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_control` | 宿主分配/释放 | 回调/context 借用 | 至同步调用结束；保存 control 的 pager/canvas/query 等至替换/free | 回调同线程；共享 context 宿主同步 | C |
| `exr_document` | SDK 分配；调用者用 `exr_document_free` 释放 | 拥有一个引用；指针复制不增加引用 | 独立快照可活过 publication/library；内部保留所需源；普通 pager 借用它 | R 纯内存读；S 资源/源操作 | C |
| `exr_font` | SDK 分配；调用者用 `exr_font_free` 释放 | 拥有一个引用；指针复制不增加引用 | layout/fixed reader 保留引用；session 借用字体；调用者 free 后不能再使用自身引用 | S，包括 const 字体查询 | C |
| `exr_layout` | SDK 分配；调用者用 `exr_layout_free` 释放 | 拥有一个引用；指针复制不增加引用 | 保留字体和图像，可活过输入 document、pager 和调用者字体引用；缓存借用布局例外 | R 数组读；S 字体渲染/共享引用释放 | C |
| `exr_library` | SDK 分配；调用者用 `exr_library_close` 释放 | 拥有一个引用；指针复制不增加引用 | 导出快照独立；source 保留数据库至 release | S | C |
| `exr_publication` | SDK 分配；调用者用 `exr_publication_free` 释放 | 拥有一个引用；指针复制不增加引用 | session/EPUB pager 保留引用；已 load 的 document 独立 | S | C |
| `exr_session` | SDK 分配；调用者用 `exr_session_free` 释放 | 拥有一个引用；指针复制不增加引用 | 保留 publication/hyphenator；借 font/context；get/clear/驱逐/free 使旧借用子对象不可沿用 | S | C |
| `exr_pager` | SDK 分配；调用者用 `exr_pager_free` 释放 | 拥有一个引用；指针复制不增加引用 | 普通 pager 借 document/context 并保留有效 font；EPUB pager 保留 publication；next 页面拥有，get 页面借缓存 | S | C |
| `exr_context_release_fn` | 宿主函数；最终 owner 调用 | 释放已转移 context；成功转移后恰好一次 | 不能访问已终结 owner | C | C |
| `exr_read_at_fn` | 宿主提供函数；SDK 不 free | 参数仅回调期间借用；context 见注册输入契约 | 同步调用线程；不得保留临时参数 | C | C |
| `exr_source` | 宿主结构；context owner 调 `release(context)` | open_source/TXT pager 成功转移 context；scan/inspect/import/cursor 只借 | 字节不可变；document 可保留源；library_source 保留数据库 | S；回调不重入 owner | C |
| `exr_bitmap` | 宿主结构；SDK pixels 用 `exr_bitmap_free(&bitmap)` | 输出拥有 pixels；canvas/layout getter 借用，不 free | 拥有像素独立；借用随 canvas/layout 失效 | R 只读；写/释放 S | C |
| `exr_page_geometry` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_viewport` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_metadata_entry` | SDK 数组用 `exr_metadata_free(entries,count)` | load/read 拥有；provider/inspection getter 借用；写入参数属宿主 | 拥有结果独立；借用至 provider 下一操作或 inspection_free | R | C |
| `exr_lifetime_count` | 宿主输出数组；SDK 不释放 | 数值复制；type 借静态类型名 | 数值独立；type 至 SDK 模块卸载 | S 诊断快照 | C |

### `include/exr/dictionary.h`

| 类型 | 分配与释放 | 拥有/借用 | 生命周期 | 线程 | 重入 |
| --- | --- | --- | --- | --- | --- |
| `exr_dictionary` | SDK 分配；调用者用 `exr_dictionary_free` 释放 | 拥有一个引用；指针复制不增加引用 | 本对象释放后，其借用视图失效 | T 单线程所有 | C |
| `exr_dictionary_info` | SDK 分配；随 dictionary_free | getter 借字符串 | 至 dictionary_free | T | C |
| `exr_dictionary_match` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_dictionary_result` | SDK 数组；`exr_dictionary_results_free(results,count)` | 拥有数组/全部字符串 | 可活过所有输入 dictionary | R | C |
| `exr_dictionary_io` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |

### `include/exr/document.h`

| 类型 | 分配与释放 | 拥有/借用 | 生命周期 | 线程 | 重入 |
| --- | --- | --- | --- | --- | --- |
| `exr_block` | document 内数组 | 借 document；可复制纯值 | 至 document_free；复制值独立 | R | C |
| `exr_node_kind` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_attribute` | document 内数组；随 document_free | getter 和嵌套字段借 document；构造输入属宿主 | 至 document_free；session 缓存还受驱逐失效约束 | R | C |
| `exr_node` | document 内数组；随 document_free | getter 和嵌套字段借 document；构造输入属宿主 | 至 document_free；session 缓存还受驱逐失效约束 | R | C |
| `exr_chapter` | document 内数组；随 document_free | getter 和嵌套字段借 document；构造输入属宿主 | 至 document_free；session 缓存还受驱逐失效约束 | R | C |
| `exr_resource` | document 内数组；随 document_free | getter 和嵌套字段借 document；构造输入属宿主 | 至 document_free；session 缓存还受驱逐失效约束 | R | C |
| `exr_node_input` | 宿主分配/释放；create 复制所需内容 | 输入指针仅调用期间借用 | create 返回后输入可释放，输出独立 | I | C |
| `exr_chapter_input` | 宿主分配/释放；create 复制所需内容 | 输入指针仅调用期间借用 | create 返回后输入可释放，输出独立 | I | C |
| `exr_resource_input` | 宿主分配/释放；create 复制所需内容 | 输入指针仅调用期间借用 | create 返回后输入可释放，输出独立 | I | C |
| `exr_document_input` | 宿主分配/释放；create 复制所需内容 | 输入指针仅调用期间借用 | create 返回后输入可释放，输出独立 | I | C |
| `exr_anchor` | 宿主结构；字段用 `exr_anchor_free` | create/get 拥有字段；手工输入属宿主 | 输出独立于 document/source；不 free 结构本身 | R | C |
| `exr_anchor_state` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_anchor_match` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_part` | publication 内数组 | 只读借用；不单独 free | 至 publication_free | R | C |
| `exr_part_load_fn` | 宿主函数；SDK 接管成功输出 | 成功输出必须是独立拥有 document/text，不能交借用对象 | SDK 负责对应 document_free/fixed_text_free | C | C |
| `exr_navigation` | document_navigation 输出用 `exr_navigation_free(entries,count)` | document_navigation 拥有；publication_navigation 借；输入属宿主 | 独立结果可活过 document；借用至 publication_free | R | C |
| `exr_toc_source` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_target` | 宿主结构或 publication 数组 | fragment 借 TOC/missing_targets 或宿主 fragment 缓冲 | TOC 至 free；missing 至 next locate/target_at；宿主缓冲至其释放 | R | C |
| `exr_toc_entry` | publication 内数组 | 只读借用；不单独 free | 至 publication_free | R | C |
| `exr_link_state` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_location` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_fixed_document` | SDK 分配；调用者用 `exr_fixed_free` 释放 | 拥有一个引用；指针复制不增加引用 | 拥有 provider context；内建 reader 保留 fallback_font；load_text/metadata/annotations 结果独立 | S | C |
| `exr_fixed_text` | SDK 分配；调用者用 `exr_fixed_text_free` 释放 | 拥有一个引用；指针复制不增加引用 | 本对象释放后，其借用视图失效 | R；释放/引用变更 S | C |
| `exr_text_region` | 宿主输入、fixed_text 内数组或 select 数组 | regions getter 借 text；select 输出拥有，用 `exr_free` | getter 至 text_free；select 结果独立 | R | C |
| `exr_fixed_anchor` | 宿主结构；字段用 `exr_fixed_anchor_free` | create 拥有字段；手工输入属宿主 | 输出独立于 fixed_text；不 free 结构本身 | R | C |
| `exr_fixed_page` | fixed document 内数组 | getter 借；create 输入复制 | 至 fixed_free | R | C |
| `exr_fixed_draw_fn` | 宿主提供函数；SDK 不 free | 参数仅回调期间借用；context 见注册输入契约 | 同步调用线程；不得保留临时参数 | C | C |
| `exr_fixed_draw_ex_fn` | 宿主提供函数；SDK 不 free | 参数仅回调期间借用；context 见注册输入契约 | 同步调用线程；不得保留临时参数 | C | C |
| `exr_fixed_text_fn` | 宿主函数；SDK 接管成功输出 | 成功输出必须是独立拥有 document/text，不能交借用对象 | SDK 负责对应 document_free/fixed_text_free | C | C |
| `exr_fixed_metadata_fn` | 宿主 provider 拥有输出；SDK 不释放 provider 数组 | entries/strings 借给 SDK，load_metadata 随后复制为独立结果 | provider 输出至其下一操作；load 结果用 metadata_free | C | C |
| `exr_page_annotation` | load 输出用 `exr_page_annotations_free(annotations,count)` | load 拥有字段；provider 借至下一操作；write 输入借用 | load 结果独立于 fixed document | R | C |
| `exr_fixed_annotations_fn` | 宿主 provider 拥有输出；SDK 不释放 provider 数组 | annotations/字段借给 SDK，load_annotations 复制为独立结果 | provider 输出至其下一操作；load 结果用 page_annotations_free | C | C |
| `exr_fixed_input` | 宿主输入；SDK 最后引用调 `release(context)` | 元数据复制；context 仅成功时转移；无 release 则宿主持有 | 结构可在 create 后销毁；context 至最后引用释放 | S provider/context | C |
| `exr_fixed_render_options` | 宿主结构；无 SDK free | control/context 借用 | 至同步调用结束 | I；共享 context S | C |
| `exr_search_match` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_cfi_point` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_cfi` | SDK 分配；调用者用 `exr_cfi_free` 释放 | 拥有一个引用；指针复制不增加引用 | 本对象释放后，其借用视图失效 | R；释放/引用变更 S | C |
| `exr_cfi_error_code` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_cfi_diagnostic` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_cfi_range` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_text_annotation` | 宿主结构；`exr_text_annotation_free` | import 拥有字符串/anchor；export 输入借用 | import 独立；export JSON 另用 exr_free | R | C |

### `include/exr/font_manager.h`

| 类型 | 分配与释放 | 拥有/借用 | 生命周期 | 线程 | 重入 |
| --- | --- | --- | --- | --- | --- |
| `exr_font_location` | 宿主分配/释放 | 同步调用借用；SDK 不释放指针字段 | 字段和 control.context 至调用返回 | I | C |
| `exr_font_manager_options` | 宿主分配/释放 | 同步调用借用；SDK 不释放指针字段 | 字段和 control.context 至调用返回 | I | C |
| `exr_font_manager` | SDK 分配；调用者用 `exr_font_manager_free` 释放 | 拥有一个引用；指针复制不增加引用 | 本对象释放后，其借用视图失效 | R；释放/引用变更 S | C |
| `exr_font_manager_summary` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_font_skip` | 宿主输出结构；无 SDK free | 字符串借 manager | 至 font_manager_free | R | C |
| `exr_font_face_info` | 宿主输出结构；无 SDK free | 字符串借 manager | 至 font_manager_free | R | C |
| `exr_font_chain_link` | SDK 数组用 `exr_free`；宿主单值无需 free | 输出独立拥有数组 | 可活过 font/manager；索引/字形 ID 对应原字体 | R | C |
| `exr_font_pick_result` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |

### `include/exr/formats.h`

| 类型 | 分配与释放 | 拥有/借用 | 生命周期 | 线程 | 重入 |
| --- | --- | --- | --- | --- | --- |
| `exr_sevenz` | SDK 分配；调用者用 `exr_sevenz_free` 释放 | 拥有一个引用；指针复制不增加引用 | 本对象释放后，其借用视图失效 | S | C |
| `exr_sevenz_options` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_sevenz_entry` | archive 内数组 | path/数组借 archive | 至 sevenz_free | S archive | C |
| `exr_txt_paragraph_fn` | 宿主提供函数；SDK 不 free | 参数仅回调期间借用；context 见注册输入契约 | 同步调用线程；不得保留临时参数 | C | C |
| `exr_txt_cursor` | SDK 分配；调用者用 `exr_txt_cursor_free` 释放 | 拥有一个引用；指针复制不增加引用 | 借 source/context 至 cursor_free；paragraph 仅到下一 cursor 操作 | S | C |
| `exr_txt_checkpoint` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_epub_cover` | 宿主分配/释放 | 同步调用借用；SDK 不释放指针字段 | 字段和 control.context 至调用返回 | I | C |

### `include/exr/graphics.h`

| 类型 | 分配与释放 | 拥有/借用 | 生命周期 | 线程 | 重入 |
| --- | --- | --- | --- | --- | --- |
| `exr_path_point` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_path_verb` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_path_segment` | 宿主输入或 SDK outline 数组 | draw 借输入；outline 输出拥有，用 `exr_free` | outline 可活过 font；callback 数据只在 callback 内有效 | R | C |
| `exr_fill_rule` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_line_cap` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_line_join` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_path_stroke` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_image_layer` | 宿主/回调临时结构 | bitmap、mask 链和像素借用，不接管 | 至调用/回调结束；宿主数据由宿主决定寿命 | R 输入；canvas S | C |
| `exr_draw_style` | 宿主值；无 SDK free | dashes/stroke_matrix 借用 | 至调用/回调返回 | I | C |
| `exr_blend_mode` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_canvas` | SDK 分配；调用者用 `exr_canvas_free` 释放 | 拥有一个引用；指针复制不增加引用 | 本对象释放后，其借用视图失效 | S | C |
| `exr_canvas_config` | 宿主结构；context 由宿主释放 | create 复制 config；control.context 借用 | context 至 canvas_free | S | C |
| `exr_draw_state` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_draw_path_fn` | 宿主提供函数；SDK 不 free | 参数仅回调期间借用；context 见注册输入契约 | 同步调用线程；不得保留临时参数 | C | C |
| `exr_draw_image_fn` | 宿主提供函数；SDK 不 free | 参数仅回调期间借用；context 见注册输入契约 | 同步调用线程；不得保留临时参数 | C | C |
| `exr_draw_clip_fn` | 宿主提供函数；SDK 不 free | 参数仅回调期间借用；context 见注册输入契约 | 同步调用线程；不得保留临时参数 | C | C |
| `exr_draw_state_fn` | 宿主提供函数；SDK 不 free | 参数仅回调期间借用；context 见注册输入契约 | 同步调用线程；不得保留临时参数 | C | C |
| `exr_draw_sink` | 宿主结构；canvas_get_sink 填充 | 回调/context 借用；canvas sink.context 借 canvas | 调用期间有效；canvas sink 至 canvas_free | S canvas/context | C |
| `exr_draw_blend_fn` | 宿主提供函数；SDK 不 free | 参数仅回调期间借用；context 见注册输入契约 | 同步调用线程；不得保留临时参数 | C | C |
| `exr_draw_layer_begin_fn` | 宿主提供函数；SDK 不 free | 参数仅回调期间借用；context 见注册输入契约 | 同步调用线程；不得保留临时参数 | C | C |
| `exr_draw_layer_end_fn` | 宿主提供函数；SDK 不 free | 参数仅回调期间借用；context 见注册输入契约 | 同步调用线程；不得保留临时参数 | C | C |
| `exr_draw_group_begin_fn` | 宿主提供函数；SDK 不 free | 参数仅回调期间借用；context 见注册输入契约 | 同步调用线程；不得保留临时参数 | C | C |
| `exr_draw_soft_mask_fn` | 宿主提供函数；SDK 不 free | 参数仅回调期间借用；context 见注册输入契约 | 同步调用线程；不得保留临时参数 | C | C |
| `exr_draw_extent_fn` | 宿主提供函数；SDK 不 free | 参数仅回调期间借用；context 见注册输入契约 | 同步调用线程；不得保留临时参数 | C | C |
| `exr_draw_shading_fn` | 宿主提供函数；SDK 不 free | 参数仅回调期间借用；context 见注册输入契约 | 同步调用线程；不得保留临时参数 | C | C |
| `exr_draw_path_cmyk_fn` | 宿主提供函数；SDK 不 free | 参数仅回调期间借用；context 见注册输入契约 | 同步调用线程；不得保留临时参数 | C | C |
| `exr_draw_image_cmyk_fn` | 宿主提供函数；SDK 不 free | 参数仅回调期间借用；context 见注册输入契约 | 同步调用线程；不得保留临时参数 | C | C |
| `exr_draw_image_space_fn` | 宿主提供函数；SDK 不 free | 参数仅回调期间借用；context 见注册输入契约 | 同步调用线程；不得保留临时参数 | C | C |
| `exr_draw_alpha_source_fn` | 宿主提供函数；SDK 不 free | 参数仅回调期间借用；context 见注册输入契约 | 同步调用线程；不得保留临时参数 | C | C |
| `exr_paint_sample_fn` | 宿主提供函数；SDK 不 free | 参数仅回调期间借用；context 见注册输入契约 | 同步调用线程；不得保留临时参数 | C | C |
| `exr_paint_source` | 宿主结构；无 SDK free | sample/context 同步借用 | 至 canvas_paint 返回；输出指针只在 callback 内有效 | S；sample 不得改活动 canvas | C |
| `exr_draw_paint_fn` | 宿主提供函数；SDK 不 free | 参数仅回调期间借用；context 见注册输入契约 | 同步调用线程；不得保留临时参数 | C | C |
| `exr_draw_sink_ex` | 宿主结构；canvas_get_sink 填充 | 回调/context 借用；canvas sink.context 借 canvas | 调用期间有效；canvas sink 至 canvas_free | S canvas/context | C |

### `include/exr/layout.h`

| 类型 | 分配与释放 | 拥有/借用 | 生命周期 | 线程 | 重入 |
| --- | --- | --- | --- | --- | --- |
| `exr_publication_input` | 宿主输入；SDK 最后引用调 `release(context)` | 元数据复制；context 仅成功时转移；无 release 则宿主持有 | 结构可在 create 后销毁；context 至最后引用释放 | S provider/context | C |
| `exr_line` | layout 内数组 | getter 借 layout；positioned create 复制输入 | 至 layout_free/驱逐；复制数值独立 | R | C |
| `exr_page` | layout 内数组 | getter 借 layout；positioned create 复制输入 | 至 layout_free/驱逐；复制数值独立 | R | C |
| `exr_block_kind` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_layout_block` | layout 内数组 | getter 借 layout；positioned create 复制输入 | 至 layout_free/驱逐；复制数值独立 | R | C |
| `exr_page_structure` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_box_kind` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_box` | layout 内数组 | getter 借 layout；positioned create 复制输入 | 至 layout_free/驱逐；复制数值独立 | R | C |
| `exr_paint_kind` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_paint` | layout 内数组 | getter 借 layout；positioned create 复制输入 | 至 layout_free/驱逐；复制数值独立 | R | C |
| `exr_positioned_page` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_positioned_input` | 宿主分配/释放；create 复制所需内容 | 输入指针仅调用期间借用 | create 返回后输入可释放，输出独立 | I | C |
| `exr_layout_options` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_image_decode_fn` | 宿主分配 RGBA；配对 image_release_fn 释放 | SDK 同步消费；不直接接管宿主像素 | 复制/消费后调用 release；失败也可调用 | C | C |
| `exr_image_release_fn` | 宿主释放 decode RGBA | 不得释放其他 SDK 借用 bitmap | SDK 对配对 decode 输出调用 | C | C |
| `exr_layout_config` | 宿主结构；CSS 由宿主释放 | create/pager/session 复制 config/CSS；image/control context 借用 | context 至使用它的创建/分页/session 工作结束 | S 共享 font/context | C |
| `exr_text_position` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_text_range` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_ssml_position` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_ssml_sentence` | chunk 内数组；随 chunk_free | 借 chunk.sentences；可复制纯值 | 数组至 chunk_free；复制值独立 | R | C |
| `exr_ssml_chunk` | 宿主结构；`exr_ssml_chunk_free` | 拥有 ssml/sentences | 可活过 publication；复用前先 free | R | C |
| `exr_search_result` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_search_fn` | 宿主提供函数；SDK 不 free | 参数仅回调期间借用；context 见注册输入契约 | 同步调用线程；不得保留临时参数 | C | C |
| `exr_index_cursor` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_index_stats` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_content_endpoint` | 宿主结构；整体 `exr_content_anchor_free` | 拥有 endpoint 字符串/嵌套 anchor | 独立于 publication；endpoint 不单独 free | R | C |
| `exr_content_anchor` | 宿主结构；整体 `exr_content_anchor_free` | 拥有 endpoint 字符串/嵌套 anchor | 独立于 publication；endpoint 不单独 free | R | C |
| `exr_text_range_match` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_range_unit` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_locate_report` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_reader_style` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_footnote` | publication 内数组 | 只读借用；不单独 free | 至 publication_free | R | C |
| `exr_footnote_reference` | publication 内数组 | 只读借用；不单独 free | 至 publication_free | R | C |
| `exr_chapter_options` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_chapter_stats` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_page_kind` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_toc_page_options` | 宿主分配/释放 | 同步调用借用；SDK 不释放指针字段 | 字段和 control.context 至调用返回 | I | C |
| `exr_text_sink_fn` | 宿主提供函数；SDK 不 free | 参数仅回调期间借用；context 见注册输入契约 | 同步调用线程；不得保留临时参数 | C | C |
| `exr_pager_stats` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |

### `include/exr/library.h`

| 类型 | 分配与释放 | 拥有/借用 | 生命周期 | 线程 | 重入 |
| --- | --- | --- | --- | --- | --- |
| `exr_book` | SDK 查询数组；`exr_books_free(items,count)` | 输出拥有嵌套字段；write 输入借用 | 独立于 library | R | C |
| `exr_note` | SDK 查询数组；`exr_notes_free(items,count)` | 输出拥有嵌套字段；write 输入借用 | 独立于 library | R | C |
| `exr_library_epub_info` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_epub_location` | 宿主结构；`exr_epub_location_free` | get 输出拥有动态字段；write 输入借用 | 独立于 library | R | C |
| `exr_epub_note` | SDK 查询数组；`exr_epub_notes_free(items,count)` | 输出拥有嵌套字段；write 输入借用 | 独立于 library | R | C |
| `exr_fixed_note` | SDK 查询数组；`exr_fixed_notes_free(items,count)` | 输出拥有嵌套字段；write 输入借用 | 独立于 library | R | C |
| `exr_audio_checkpoint` | 宿主结构；`exr_audio_checkpoint_free` | get 输出拥有动态字段；write 输入借用 | 独立于 library | R | C |
| `exr_audio_bookmark` | SDK 查询数组；`exr_audio_bookmarks_free(items,count)` | 输出拥有嵌套字段；write 输入借用 | 独立于 library | R | C |
| `exr_note_relocation` | report 内数组；随 relocation_free | 借 report.notes；可复制纯值 | 数组至 report_free；复制值独立 | R | C |
| `exr_library_relocation` | 宿主结构；`exr_library_relocation_free` | get 输出拥有动态字段；write 输入借用 | 独立于 library | R | C |

### `include/exr/pdf.h`

| 类型 | 分配与释放 | 拥有/借用 | 生命周期 | 线程 | 重入 |
| --- | --- | --- | --- | --- | --- |
| `exr_pdf_security_info` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_fixed_open_options` | 宿主结构/密码；SDK 不释放 | 密码/control 只在 open 借用；fallback_font retain；security 为宿主输出 | 输入可在 open 后释放；fixed reader 保留 font 引用 | S fallback_font | C |

### `include/exr/pdf_edit.h`

| 类型 | 分配与释放 | 拥有/借用 | 生命周期 | 线程 | 重入 |
| --- | --- | --- | --- | --- | --- |
| `exr_pdf_annotation_write_options` | 宿主结构；无 SDK free | control/context 借用 | 至同步调用结束 | I；共享 context S | C |
| `exr_pdf_field_kind` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_pdf_field_option` | form_field 内数组；随 form_free | 字段/数组借 form snapshot | 至 form_free；不单独 free | R | C |
| `exr_pdf_field_widget` | form_field 内数组；随 form_free | 字段/数组借 form snapshot | 至 form_free；不单独 free | R | C |
| `exr_pdf_form_field` | SDK 数组；`exr_pdf_form_free(fields,count)` | 拥有 strings/options/widgets | 独立于 PDF 输入；整体一次释放 | R | C |
| `exr_pdf_form_options` | 宿主结构；无 SDK free | control/context 借用 | 至同步调用结束 | I；共享 context S | C |
| `exr_pdf_form_change` | 宿主分配/释放 | 同步调用借用；SDK 不释放指针字段 | 字段和 control.context 至调用返回 | I | C |
| `exr_pdf_form_write_options` | 宿主结构 | font/control 借用至同步写入返回 | font/context 在调用中有效；PDF 输出独立 | S font | C |

### `include/exr/text.h`

| 类型 | 分配与释放 | 拥有/借用 | 生命周期 | 线程 | 重入 |
| --- | --- | --- | --- | --- | --- |
| `exr_direction` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_bidi` | SDK 分配；调用者用 `exr_bidi_free` 释放 | 拥有一个引用；指针复制不增加引用 | 本对象释放后，其借用视图失效 | R；释放/引用变更 S | C |
| `exr_bidi_scalar` | bidi 内数组；随 bidi_free | 借 scalars；复制纯值无所有权 | 数组至 bidi_free；复制值独立 | R | C |
| `exr_shape_feature` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_shape_options` | 宿主分配/释放 | 同步调用借用；SDK 不释放指针字段 | 字段和 control.context 至调用返回 | I | C |
| `exr_shaped_glyph` | SDK 数组用 `exr_free`；宿主单值无需 free | 输出独立拥有数组 | 可活过 font/manager；索引/字形 ID 对应原字体 | R | C |
| `exr_writing_mode` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_text_orientation` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_font_input` | 宿主分配/释放；create 复制所需内容 | 输入指针仅调用期间借用 | create 返回后输入可释放，输出独立 | I | C |
| `exr_glyph` | layout 内数组 | getter 借 layout；positioned create 复制输入 | 至 layout_free/驱逐；复制数值独立 | R | C |
| `exr_font_axis` | SDK 数组用 `exr_free`；宿主单值无需 free | 输出独立拥有数组 | 可活过 font/manager；索引/字形 ID 对应原字体 | R | C |
| `exr_font_coordinate` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_font_color_layer` | SDK 数组用 `exr_free`；宿主单值无需 free | 输出独立拥有数组 | 可活过 font/manager；索引/字形 ID 对应原字体 | R | C |
| `exr_font_color_info` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |
| `exr_glyph_image` | 宿主结构；`exr_bitmap_free(&image.bitmap)` | 输出拥有 bitmap.pixels | 可活过 font；结构不由 SDK free | R | C |
| `exr_hyphenator` | SDK 分配；调用者用 `exr_hyphenator_free` 释放 | 拥有一个引用；指针复制不增加引用 | 本对象释放后，其借用视图失效 | S | C |
| `exr_hyphenate_fn` | 宿主提供函数；SDK 不 free | 参数仅回调期间借用；context 见注册输入契约 | 同步调用线程；不得保留临时参数 | C | C |
| `exr_hyphen_provider` | 宿主输入；SDK 最后引用调 `release(context)` | 元数据复制；context 仅成功时转移；无 release 则宿主持有 | 结构可在 create 后销毁；context 至最后引用释放 | S provider/context | C |
| `exr_hyphen_break` | result 内数组；随 hyphenation_free | query 视图借 result；emit 输入借到 emit 返回并复制 | 结果独立于 dictionary；视图至 result_free | R | C |
| `exr_hyphenation` | SDK 分配；调用者用 `exr_hyphenation_free` 释放 | 拥有一个引用；指针复制不增加引用 | 本对象释放后，其借用视图失效 | R；释放/引用变更 S | C |
| `exr_hyphen_emit_fn` | SDK 提供 emit 回调；宿主不释放 | provider 在本次 hyphenate callback 内调用；SDK 复制 item 字段 | emit/context 不得保留到 callback 返回之后 | 同线程 | 允许规定的 emit 调用 |
| `exr_hyphenate_discretionary_fn` | 宿主提供 provider 函数 | 参数借用；emit 是本次调用期间可调用的 SDK continuation | 不保留 word、emit 或 emit_context；emit 复制输出 | 同线程 | 允许 emit；禁止重入 hyphenator |
| `exr_hyphen_discretionary_provider` | 宿主输入；SDK 最后引用调 `release(context)` | 元数据复制；context 仅成功时转移；无 release 则宿主持有 | 结构可在 create 后销毁；context 至最后引用释放 | S provider/context | C |
| `exr_hyphen_pattern_input` | 宿主分配/释放；create 复制所需内容 | 输入指针仅调用期间借用 | create 返回后输入可释放，输出独立 | I | C |
| `exr_hyphen_case_policy` | 宿主值/枚举；无需 SDK free | 纯值复制；不转移资源 | 复制值独立；数组元素仍受所属数组有效期约束 | R；同一输出修改 S | C |

### `include/exr/textindex.h`

| 类型 | 分配与释放 | 拥有/借用 | 生命周期 | 线程 | 重入 |
| --- | --- | --- | --- | --- | --- |
| `exr_text_index` | SDK 分配；调用者用 `exr_text_index_close` 释放 | 拥有一个引用；指针复制不增加引用 | query 保留 index；每 handle 仅一个活 query；写入前先 query_free | S | C |
| `exr_text_query` | SDK 分配；调用者用 `exr_text_query_free` 释放 | 拥有一个引用；指针复制不增加引用 | 保留 index，可活过 close；control.context 借至 query_free；hit 至 next/free | S | C |
| `exr_text_hit` | 宿主结构；无 SDK free | source/part/text 借 query | 至 next/free；保留须复制 | S query | C |
| `exr_text_part` | provider/宿主结构；SDK 不释放 | id/text 借给 replace | 至下一 provider callback 或 replace 返回 | S index/provider | C |
| `exr_text_part_fn` | 宿主提供函数；SDK 不 free | 参数仅回调期间借用；context 见注册输入契约 | 同步调用线程；不得保留临时参数 | C | C |

<!-- FUNCTION CONTRACTS -->

## 全部公开函数

每行适用共同规则：未明确转移或保留的输入仅借用至同步调用返回。输出列给出拥有资源的释放函数。C 允许无关对象操作与 R 只读观测，禁止活动对象/依赖链的 S/T 操作重入；音频 getter 的观测例外单列。

### `include/exr/audio.h`

| 函数 | 所有权 / 释放 | 生命周期 | 线程 | 重入 |
| --- | --- | --- | --- | --- |
| `exr_audio_create` | SDK 分配 `out`；成功转移引用；`exr_audio_free` | 依 `exr_audio` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_audio_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_audio_title` | 借用 audio 的视图/字段；不转移所有权，不 free | 至 audio_free | R；释放/引用变更互斥 | C |
| `exr_audio_duration` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | C |
| `exr_audio_tracks` | 借用 audio 的视图/字段；不转移所有权，不 free | 至 audio_free | R；释放/引用变更互斥 | C |
| `exr_audio_chapters` | 借用 audio 的视图/字段；不转移所有权，不 free | 至 audio_free | R；释放/引用变更互斥 | C |
| `exr_audio_syncs` | 借用 audio 的视图/字段；不转移所有权，不 free | 至 audio_free | R；释放/引用变更互斥 | C |
| `exr_audio_memory_size` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | C |
| `exr_audio_locate` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | 允许只读观测 |
| `exr_audio_sync_at` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | 允许只读观测 |
| `exr_audio_sync_text` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | 允许只读观测 |
| `exr_audio_time` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | 允许只读观测 |
| `exr_audio_player_create` | SDK 分配；`exr_audio_player_free`；retain audio；成功接管 backend.context | audio 外部引用可释放；context 最后经 backend.release 释放 | R；释放/引用变更互斥 | C |
| `exr_audio_player_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_audio_player_get` | 借用 player 的视图/字段；不转移所有权，不 free | 至 player_free（track_id） | S 所有涉及 owner | 允许 backend 回调观测 |
| `exr_audio_player_play` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_audio_player_pause` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_audio_player_seek` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_audio_player_rate` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_audio_player_restore` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_audio_player_report` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_wave_open` | SDK 分配 `out`；成功转移引用；`exr_wave_free` | 依 `exr_wave` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_wave_open_source` | SDK 分配 `out`；成功转移引用；`exr_wave_free`；成功转移 source.context | 依 `exr_wave` 类型行；输入借用至调用返回；最终源引用调 release；失败不转移 | I 独立输入/输出 | C |
| `exr_wave_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_wave_format` | 借用 wave 的视图/字段；不转移所有权，不 free | 至 wave_free | S 所有涉及 owner | C |
| `exr_wave_read` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_flac_open` | SDK 分配 `out`；成功转移引用；`exr_flac_free` | 依 `exr_flac` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_flac_open_source` | SDK 分配 `out`；成功转移引用；`exr_flac_free`；成功转移 source.context | 依 `exr_flac` 类型行；输入借用至调用返回；最终源引用调 release；失败不转移 | I 独立输入/输出 | C |
| `exr_flac_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_flac_format` | 借用 flac 的视图/字段；不转移所有权，不 free | 至 flac_free | S 所有涉及 owner | C |
| `exr_flac_read` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_mp3_available` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | I 独立输入/输出 | C |
| `exr_mp3_open` | SDK 分配 `out`；成功转移引用；`exr_mp3_free` | 依 `exr_mp3` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_mp3_open_source` | SDK 分配 `out`；成功转移引用；`exr_mp3_free`；成功转移 source.context | 依 `exr_mp3` 类型行；输入借用至调用返回；最终源引用调 release；失败不转移 | I 独立输入/输出 | C |
| `exr_mp3_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_mp3_format` | 借用 mp3 的视图/字段；不转移所有权，不 free | 至 mp3_free | S 所有涉及 owner | C |
| `exr_mp3_read` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_aac_available` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | I 独立输入/输出 | C |
| `exr_aac_open` | SDK 分配 `out`；成功转移引用；`exr_aac_free` | 依 `exr_aac` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_aac_open_source` | SDK 分配 `out`；成功转移引用；`exr_aac_free`；成功转移 source.context | 依 `exr_aac` 类型行；输入借用至调用返回；最终源引用调 release；失败不转移 | I 独立输入/输出 | C |
| `exr_aac_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_aac_format` | 借用 aac 的视图/字段；不转移所有权，不 free | 至 aac_free | S 所有涉及 owner | C |
| `exr_aac_read` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_m4b_available` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | I 独立输入/输出 | C |
| `exr_m4b_open` | SDK 分配 `out`；成功转移引用；`exr_m4b_free` | 依 `exr_m4b` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_m4b_open_source` | SDK 分配 `out`；成功转移引用；`exr_m4b_free`；成功转移 source.context | 依 `exr_m4b` 类型行；输入借用至调用返回；最终源引用调 release；失败不转移 | I 独立输入/输出 | C |
| `exr_m4b_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_m4b_format` | 借用 m4b 的视图/字段；不转移所有权，不 free | 至 m4b_free | S 所有涉及 owner | C |
| `exr_m4b_read` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_pcm_create` | SDK 分配 `out`；成功转移引用；`exr_pcm_free`；成功接管 provider.context | 依 `exr_pcm` 类型行；输入借用至调用返回；最终 release；无 release 则宿主保持 context 有效 | I 独立输入/输出 | C |
| `exr_pcm_open` | SDK 分配 `out`；成功转移引用；`exr_pcm_free` | 依 `exr_pcm` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_pcm_open_source` | SDK 分配 `out`；成功转移引用；`exr_pcm_free`；成功转移 source.context | 依 `exr_pcm` 类型行；输入借用至调用返回；最终源引用调 release；失败不转移 | I 独立输入/输出 | C |
| `exr_pcm_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_pcm_format` | 借用 pcm 的视图/字段；不转移所有权，不 free | 至 pcm_free | S 所有涉及 owner | C |
| `exr_pcm_read` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_stretch_create` | SDK 分配 `out`；成功转移引用；`exr_stretch_free` | 依 `exr_stretch` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_stretch_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_stretch_get` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_stretch_push` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_stretch_pull` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_stretch_finish` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_stretch_reset` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_audio_output_backend` | 静态借用字符串；不得 free | SDK 模块加载期间有效 | I 独立输入/输出 | C |
| `exr_audio_output_open` | SDK 分配 `out`；成功转移引用；`exr_audio_output_free` | 依 `exr_audio_output` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_audio_output_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_audio_output_write` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_audio_output_pause` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_audio_output_flush` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_audio_output_pending` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_m4b_inspect` | SDK 分配 `out`；成功转移引用；`exr_m4b_inspection_free` | 依 `exr_m4b_inspection` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_m4b_inspect_source` | SDK inspection；`exr_m4b_inspection_free`；只借 source | 结果独立；不调用 source.release | I 独立输入/输出 | C |
| `exr_m4b_inspection_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_m4b_inspection_duration` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | C |
| `exr_m4b_inspection_metadata` | 借用 inspection 的视图/字段；不转移所有权，不 free | 至 inspection_free | R；释放/引用变更互斥 | C |
| `exr_m4b_inspection_chapters` | 借用 inspection 的视图/字段；不转移所有权，不 free | 至 inspection_free | R；释放/引用变更互斥 | C |
| `exr_m4b_inspection_cover` | 借用 inspection 的视图/字段；不转移所有权，不 free | 至 inspection_free | R；释放/引用变更互斥 | C |

### `include/exr/base.h`

| 函数 | 所有权 / 释放 | 生命周期 | 线程 | 重入 |
| --- | --- | --- | --- | --- |
| `exr_viewport_create` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | I 独立输入/输出 | C |
| `exr_metadata_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_version` | 静态借用字符串；不得 free | SDK 模块加载期间有效 | I 独立输入/输出 | C |
| `exr_abi_version` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | I 独立输入/输出 | C |
| `exr_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_validate` | 无分配/转移；检查 handle 或已登记借用视图及依赖链 | Debug：有效为 1，NULL/未知为 0，已释放对象/依赖断言；Release 不检查并返回 1 | S 与对象释放互斥 | C |
| `exr_debug_counts` | 写宿主数组；type 借静态名；无须 free | 返回全部 32 种计数行，最多写 capacity 行；累计计数；Release 返回 0 | S 全局诊断；cleanup 须无活调用 | C |
| `exr_debug_cleanup` | 释放 Debug 已销毁对象的隔离区/登记；不代替对象 free | 仅全部 SDK 调用返回且 live=0 时；结束诊断 epoch，旧指针不得再用；Release 无操作 | S 全局诊断；cleanup 须无活调用 | 仅无活调用时 |
| `exr_bitmap_write_png` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | I 独立输入/输出 | C |
| `exr_bitmap_free` | 释放 SDK 生成字段并清空宿主结构；不 free 结构本身 | 不用于宿主拼接的非 SDK 字段；清空记录可再次初始化 | S 资源读取/引用变更互斥 | C |
| `exr_bitmap_write_bmp` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | I 独立输入/输出 | C |

### `include/exr/dictionary.h`

| 函数 | 所有权 / 释放 | 生命周期 | 线程 | 重入 |
| --- | --- | --- | --- | --- |
| `exr_dictionary_open` | SDK 分配 `out`；成功转移引用；`exr_dictionary_free` | 依 `exr_dictionary` 类型行；输入借用至调用返回 | T | C |
| `exr_dictionary_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_dictionary_get_info` | 借用 dictionary 的视图/字段；不转移所有权，不 free | 至 dictionary_free | T | C |
| `exr_dictionary_get_io` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | T | C |
| `exr_dictionary_query` | SDK 分配字段/数组；调用者用 `exr_dictionary_results_free(results,count)` | 拥有结果独立；宿主输出结构不由 SDK free | T | C |
| `exr_dictionary_results_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |

### `include/exr/document.h`

| 函数 | 所有权 / 释放 | 生命周期 | 线程 | 重入 |
| --- | --- | --- | --- | --- |
| `exr_document_locate` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | 允许只读观测 |
| `exr_fixed_text_create` | SDK 分配 `out`；成功转移引用；`exr_fixed_text_free` | 依 `exr_fixed_text` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_fixed_text_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_fixed_text_string` | 借用 text 的视图/字段；不转移所有权，不 free | 至 fixed_text_free | R；释放/引用变更互斥 | C |
| `exr_fixed_text_regions` | 借用 text 的视图/字段；不转移所有权，不 free | 至 fixed_text_free | R；释放/引用变更互斥 | C |
| `exr_fixed_text_memory_size` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | C |
| `exr_fixed_text_find` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | 允许只读观测 |
| `exr_fixed_text_select` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | R；释放/引用变更互斥 | 允许只读观测 |
| `exr_fixed_text_hit` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | 允许只读观测 |
| `exr_fixed_anchor_create` | SDK 分配字段/数组；调用者用 `exr_fixed_anchor_free` | 拥有结果独立；宿主输出结构不由 SDK free | R；释放/引用变更互斥 | 允许只读观测 |
| `exr_fixed_anchor_free` | 释放 SDK 生成字段并清空宿主结构；不 free 结构本身 | 不用于宿主拼接的非 SDK 字段；清空记录可再次初始化 | S 资源读取/引用变更互斥 | C |
| `exr_fixed_anchor_resolve` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | 允许只读观测 |
| `exr_fixed_create` | SDK 分配 `out`；成功转移引用；`exr_fixed_free`；成功接管 provider.context | 依 `exr_fixed_document` 类型行；输入借用至调用返回；最终 release；无 release 则宿主保持 context 有效 | I 独立输入/输出 | C |
| `exr_fixed_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_fixed_load_metadata` | SDK 分配字段/数组；调用者用 `exr_metadata_free(entries,count)` | 拥有结果独立；宿主输出结构不由 SDK free | S 所有涉及 owner | C |
| `exr_fixed_load_annotations` | SDK 分配字段/数组；调用者用 `exr_page_annotations_free(annotations,count)` | 拥有结果独立；宿主输出结构不由 SDK free | S 所有涉及 owner | C |
| `exr_page_annotations_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_fixed_title` | 借用 fixed document 的视图/字段；不转移所有权，不 free | 至 fixed_free | S 所有涉及 owner | C |
| `exr_fixed_pages` | 借用 fixed document 的视图/字段；不转移所有权，不 free | 至 fixed_free | S 所有涉及 owner | C |
| `exr_fixed_memory_size` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_fixed_load_text` | SDK 分配 `out`；成功转移引用；`exr_fixed_text_free` | 依 `exr_fixed_text` 类型行；输入借用至调用返回 | S 所有涉及 owner | C |
| `exr_fixed_page_text` | SDK 分配 `out`；成功转移引用；`exr_fixed_text_free` | 依 `exr_fixed_text` 类型行；输入借用至调用返回 | S 所有涉及 owner | C |
| `exr_document_search` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_fixed_character_at` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_fixed_draw` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_fixed_draw_ex` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_fixed_render` | SDK 分配字段/数组；调用者用 `exr_bitmap_free` | 拥有结果独立；宿主输出结构不由 SDK free | S 所有涉及 owner | C |
| `exr_document_create` | SDK 分配 `out`；成功转移引用；`exr_document_free` | 依 `exr_document` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_document_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_document_memory_size` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | C |
| `exr_document_text` | 借用 document 的视图/字段；不转移所有权，不 free | 至 document_free/缓存驱逐 | R；释放/引用变更互斥 | C |
| `exr_document_title` | 借用 document 的视图/字段；不转移所有权，不 free | 至 document_free/缓存驱逐 | R；释放/引用变更互斥 | C |
| `exr_document_blocks` | 借用 document 的视图/字段；不转移所有权，不 free | 至 document_free/缓存驱逐 | R；释放/引用变更互斥 | C |
| `exr_document_nodes` | 借用 document 的视图/字段；不转移所有权，不 free | 至 document_free/缓存驱逐 | R；释放/引用变更互斥 | C |
| `exr_document_chapters` | 借用 document 的视图/字段；不转移所有权，不 free | 至 document_free/缓存驱逐 | R；释放/引用变更互斥 | C |
| `exr_document_resources` | 借用 document 的视图/字段；不转移所有权，不 free | 至 document_free/缓存驱逐 | R；释放/引用变更互斥 | C |
| `exr_node_attribute` | 借用 document 的视图/字段；不转移所有权，不 free | 至 document_free/缓存驱逐 | R；释放/引用变更互斥 | C |
| `exr_document_format` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | C |
| `exr_document_find` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | 允许只读观测 |
| `exr_anchor_create` | SDK 分配字段/数组；调用者用 `exr_anchor_free` | 拥有结果独立；宿主输出结构不由 SDK free | R；释放/引用变更互斥 | 允许只读观测 |
| `exr_anchor_free` | 释放 SDK 生成字段并清空宿主结构；不 free 结构本身 | 不用于宿主拼接的非 SDK 字段；清空记录可再次初始化 | S 资源读取/引用变更互斥 | C |
| `exr_anchor_resolve` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | 允许只读观测 |
| `exr_cfi_parse` | SDK 分配 `out`；成功转移引用；`exr_cfi_free` | 依 `exr_cfi` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_cfi_serialize` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | R；释放/引用变更互斥 | 允许只读观测 |
| `exr_cfi_is_range` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | C |
| `exr_cfi_endpoints` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | R；释放/引用变更互斥 | 允许只读观测 |
| `exr_cfi_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_document_cfi_point_at` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | 允许只读观测 |
| `exr_document_cfi_point_offset` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | 允许只读观测 |
| `exr_document_cfi_path_create` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | R；释放/引用变更互斥 | 允许只读观测 |
| `exr_document_cfi_path_resolve` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | 允许只读观测 |
| `exr_document_cfi_create` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | S 共享 source；纯内存读取 R | C |
| `exr_document_cfi_resolve` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 共享 source；纯内存读取 R | C |
| `exr_document_cfi_path_create_quoted` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | R；释放/引用变更互斥 | 允许只读观测 |
| `exr_document_cfi_create_quoted` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | S 共享 source；纯内存读取 R | C |
| `exr_document_cfi_range_create` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | S 共享 source；纯内存读取 R | C |
| `exr_document_cfi_range_resolve` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 共享 source；纯内存读取 R | C |
| `exr_anchor_resolve_ex` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | 允许只读观测 |
| `exr_text_annotation_export` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | I 独立输入/输出 | C |
| `exr_text_annotation_import` | SDK 分配字段/数组；调用者用 `exr_text_annotation_free` | 拥有结果独立；宿主输出结构不由 SDK free | I 独立输入/输出 | C |
| `exr_text_annotation_free` | 释放 SDK 生成字段并清空宿主结构；不 free 结构本身 | 不用于宿主拼接的非 SDK 字段；清空记录可再次初始化 | S 资源读取/引用变更互斥 | C |

### `include/exr/font_manager.h`

| 函数 | 所有权 / 释放 | 生命周期 | 线程 | 重入 |
| --- | --- | --- | --- | --- |
| `exr_font_manager_create` | SDK 分配 `out`；成功转移引用；`exr_font_manager_free` | 依 `exr_font_manager` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_font_manager_open` | SDK 分配 `out`；成功转移引用；`exr_font_manager_free` | 依 `exr_font_manager` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_font_manager_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_font_manager_summary_get` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | C |
| `exr_font_manager_skip` | 借用 manager 的视图/字段；不转移所有权，不 free | 至 font_manager_free | R；释放/引用变更互斥 | C |
| `exr_font_manager_face_count` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | C |
| `exr_font_manager_face` | 借用 manager 的视图/字段；不转移所有权，不 free | 至 font_manager_free | R；释放/引用变更互斥 | C |
| `exr_font_manager_face_covers` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | C |
| `exr_font_manager_has_family` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | C |
| `exr_font_manager_chain` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | R；释放/引用变更互斥 | C |
| `exr_font_manager_pick` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | C |
| `exr_font_manager_create_font` | font 用 `exr_font_free`；可选 faces 数组用 `exr_free` | 输出独立于 manager | R；释放/引用变更互斥 | C |

### `include/exr/formats.h`

| 函数 | 所有权 / 释放 | 生命周期 | 线程 | 重入 |
| --- | --- | --- | --- | --- |
| `exr_sevenz_options_defaults` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | I 独立输入/输出 | C |
| `exr_sevenz_open` | SDK 分配 `out`；成功转移引用；`exr_sevenz_free` | 依 `exr_sevenz` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_sevenz_open_source` | SDK 分配 `out`；成功转移引用；`exr_sevenz_free`；成功转移 source.context | 依 `exr_sevenz` 类型行；输入借用至调用返回；最终源引用调 release；失败不转移 | I 独立输入/输出 | C |
| `exr_sevenz_entries` | 借用 archive 的视图/字段；不转移所有权，不 free | 至 sevenz_free | S 所有涉及 owner | C |
| `exr_sevenz_extract` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | S 所有涉及 owner | C |
| `exr_sevenz_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_txt_scan_source` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | I 独立输入/输出 | C |
| `exr_txt_cursor_create` | SDK 分配；`exr_txt_cursor_free`；只借 source/context | 源不可变并活至 cursor_free；不调用 source.release | I 独立输入/输出 | C |
| `exr_txt_cursor_next` | 借用 cursor 的视图/字段；不转移所有权，不 free | 至 下一 cursor 操作或 cursor_free | S 所有涉及 owner | C |
| `exr_txt_cursor_checkpoint` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_txt_cursor_restore` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_txt_cursor_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_txt_find_source` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | I 独立输入/输出 | C |
| `exr_txt_anchor_create_source` | SDK 分配字段/数组；调用者用 `exr_anchor_free` | 拥有结果独立；宿主输出结构不由 SDK free | I 独立输入/输出 | C |
| `exr_txt_anchor_resolve_source` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | I 独立输入/输出 | C |
| `exr_metadata_read_xmp` | SDK 分配字段/数组；调用者用 `exr_metadata_free(entries,count)` | 拥有结果独立；宿主输出结构不由 SDK free | I 独立输入/输出 | C |
| `exr_epub_metadata_write` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | I 独立输入/输出 | C |
| `exr_document_open` | SDK 分配 `out`；成功转移引用；`exr_document_free` | 依 `exr_document` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_document_open_memory` | SDK 分配 `out`；成功转移引用；`exr_document_free` | 依 `exr_document` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_epub_validate` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | I 独立输入/输出 | C |
| `exr_epub_validate_memory` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | I 独立输入/输出 | C |
| `exr_document_navigation` | SDK 分配字段/数组；调用者用 `exr_navigation_free(entries,count)` | 拥有结果独立；宿主输出结构不由 SDK free | S 共享 source；纯内存读取 R | C |
| `exr_navigation_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_document_resource` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | S 共享 source；纯内存读取 R | C |
| `exr_document_resolve` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 共享 source；纯内存读取 R | C |
| `exr_document_export_epub` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | S 共享 source；纯内存读取 R | C |
| `exr_document_export_html_bundle` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | S 共享 source；纯内存读取 R | C |
| `exr_document_export` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | S 共享 source；纯内存读取 R | C |
| `exr_document_export_control` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | S 共享 source；纯内存读取 R | C |

### `include/exr/graphics.h`

| 函数 | 所有权 / 释放 | 生命周期 | 线程 | 重入 |
| --- | --- | --- | --- | --- |
| `exr_draw_style_defaults` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | I 独立输入/输出 | C |
| `exr_canvas_create` | SDK 分配 `out`；成功转移引用；`exr_canvas_free` | 依 `exr_canvas` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_canvas_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_canvas_memory_size` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_canvas_bitmap` | 借用 canvas 的视图/字段；不转移所有权，不 free | 至 canvas_take/free；绘图可改写 pixels | S 所有涉及 owner | C |
| `exr_canvas_take` | pixels 转移到宿主 bitmap；`exr_bitmap_free` | 取得像素可活过 canvas；原 canvas bitmap 借用失效 | S 所有涉及 owner | C |
| `exr_canvas_blend` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_canvas_begin_group` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_canvas_begin_layer` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_canvas_end_layer` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_canvas_set_layer_budget` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_canvas_save` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_canvas_restore` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_canvas_path` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_canvas_path_cmyk` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_canvas_clip` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_canvas_image` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_canvas_image_cmyk` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_canvas_paint` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_canvas_get_sink_ex` | 填充宿主 sink；context 借 canvas，无新 owner | sink 只能在 canvas 存活时调用 | S 所有涉及 owner | C |
| `exr_canvas_get_sink` | 填充宿主 sink；context 借 canvas，无新 owner | sink 只能在 canvas 存活时调用 | S 所有涉及 owner | C |
| `exr_image_decode` | SDK 分配字段/数组；调用者用 `exr_bitmap_free` | 拥有结果独立；宿主输出结构不由 SDK free | I 独立输入/输出 | C |
| `exr_image_page_count` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | I 独立输入/输出 | C |
| `exr_image_page_dimensions` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | I 独立输入/输出 | C |
| `exr_image_decode_page` | SDK 分配字段/数组；调用者用 `exr_bitmap_free` | 拥有结果独立；宿主输出结构不由 SDK free | I 独立输入/输出 | C |

### `include/exr/layout.h`

| 函数 | 所有权 / 释放 | 生命周期 | 线程 | 重入 |
| --- | --- | --- | --- | --- |
| `exr_layout_blocks` | 借用 layout 的视图/字段；不转移所有权，不 free | 至 layout_free/驱逐；font 不得 free | R；释放/引用变更互斥 | C |
| `exr_layout_page_structure` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | C |
| `exr_layout_font` | 借用 layout 的视图/字段；不转移所有权，不 free | 至 layout_free/驱逐；font 不得 free | R；释放/引用变更互斥 | C |
| `exr_publication_create` | SDK 分配 `out`；成功转移引用；`exr_publication_free`；成功接管 provider.context | 依 `exr_publication` 类型行；输入借用至调用返回；最终 release；无 release 则宿主保持 context 有效 | I 独立输入/输出 | C |
| `exr_publication_open` | SDK 分配 `out`；成功转移引用；`exr_publication_free` | 依 `exr_publication` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_publication_open_source` | SDK 分配 `out`；成功转移引用；`exr_publication_free`；成功转移 source.context | 依 `exr_publication` 类型行；输入借用至调用返回；最终源引用调 release；失败不转移 | I 独立输入/输出 | C |
| `exr_publication_open_memory` | SDK 分配 `out`；成功转移引用；`exr_publication_free` | 依 `exr_publication` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_publication_open_ex` | SDK 分配 `out`；成功转移引用；`exr_publication_free` | 依 `exr_publication` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_publication_open_source_ex` | SDK 分配 `out`；成功转移引用；`exr_publication_free`；成功转移 source.context | 依 `exr_publication` 类型行；输入借用至调用返回；最终源引用调 release；失败不转移 | I 独立输入/输出 | C |
| `exr_publication_open_memory_ex` | SDK 分配 `out`；成功转移引用；`exr_publication_free` | 依 `exr_publication` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_publication_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_publication_title` | 借用 publication 的视图/字段；不转移所有权，不 free | 至 publication_free | S 所有涉及 owner | C |
| `exr_publication_parts` | 借用 publication 的视图/字段；不转移所有权，不 free | 至 publication_free | S 所有涉及 owner | C |
| `exr_publication_navigation` | 借用 publication 的视图/字段；不转移所有权，不 free | 至 publication_free | S 所有涉及 owner | C |
| `exr_publication_load` | SDK 独立 document；`exr_document_free` | 可活过 publication/library；document 保留所需源 | S 所有涉及 owner | C |
| `exr_document_ssml` | SDK 分配字段/数组；调用者用 `exr_ssml_chunk_free` | 拥有结果独立；宿主输出结构不由 SDK free | S 所有涉及 owner | C |
| `exr_ssml_chunk_free` | 释放 SDK 生成字段并清空宿主结构；不 free 结构本身 | 不用于宿主拼接的非 SDK 字段；清空记录可再次初始化 | S 资源读取/引用变更互斥 | C |
| `exr_publication_search` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_publication_search_all` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_publication_index_build` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_publication_index_search` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_publication_index_info` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_publication_index_save` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_publication_index_load` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_anchor_from_range` | SDK 分配字段/数组；调用者用 `exr_content_anchor_free` | 拥有结果独立；宿主输出结构不由 SDK free | S 所有涉及 owner | C |
| `exr_range_from_anchor` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_content_anchor_free` | 释放 SDK 生成字段并清空宿主结构；不 free 结构本身 | 不用于宿主拼接的非 SDK 字段；清空记录可再次初始化 | S 资源读取/引用变更互斥 | C |
| `exr_range_to_cfi` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | S 所有涉及 owner | C |
| `exr_range_from_cfi` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_anchor_to_cfi` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | S 所有涉及 owner | C |
| `exr_anchor_from_cfi` | SDK 分配字段/数组；调用者用 `exr_content_anchor_free` | 拥有结果独立；宿主输出结构不由 SDK free | S 所有涉及 owner | C |
| `exr_range_expand` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_publication_toc` | 借用 publication 的视图/字段；不转移所有权，不 free | 至 publication_free | S 所有涉及 owner | C |
| `exr_publication_resolve_href` | target 为宿主输出；fragment 借宿主 fragment[2048] | fragment 随宿主缓冲有效，无 SDK free | S 所有涉及 owner | C |
| `exr_publication_locate` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_publication_locate_report` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_publication_locate_report_reset` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_publication_missing_targets` | 借用 publication 的视图/字段；不转移所有权，不 free | 至 下一 locate/target_at 或 publication_free | S 所有涉及 owner | C |
| `exr_publication_target_at` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_publication_cfi_create` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | S 所有涉及 owner | C |
| `exr_publication_cfi_create_quoted` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | S 所有涉及 owner | C |
| `exr_publication_cfi_resolve` | SDK 独立 document；`exr_document_free` | 可活过 publication/library；document 保留所需源 | S 所有涉及 owner | C |
| `exr_layout_defaults` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | I 独立输入/输出 | C |
| `exr_layout_config_defaults` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | I 独立输入/输出 | C |
| `exr_reader_style_defaults` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | I 独立输入/输出 | C |
| `exr_reader_style_config` | 宿主 config 输出；config.user_css 借 css[1024] | css 活到使用 config 的 create 复制完成 | I 独立输入/输出 | C |
| `exr_publication_footnotes` | 借用 publication 的视图/字段；不转移所有权，不 free | 至 publication_free | S 所有涉及 owner | C |
| `exr_layout_create_hyphenated` | SDK 分配 `out`；成功转移引用；`exr_layout_free` | 依 `exr_layout` 类型行；输入借用至调用返回 | S font 及共享使用者 | C |
| `exr_layout_create` | SDK 分配 `out`；成功转移引用；`exr_layout_free` | 依 `exr_layout` 类型行；输入借用至调用返回 | S font 及共享使用者 | C |
| `exr_layout_create_ex` | SDK 分配 `out`；成功转移引用；`exr_layout_free` | 依 `exr_layout` 类型行；输入借用至调用返回 | S font 及共享使用者 | C |
| `exr_layout_create_positioned` | SDK 分配 `out`；成功转移引用；`exr_layout_free` | 依 `exr_layout` 类型行；输入借用至调用返回 | S font 及共享使用者 | C |
| `exr_pager_create` | SDK 分配；`exr_pager_free`；借 document，保留 font | document/context 至 pager_free；config/CSS 复制 | S font 及共享使用者 | C |
| `exr_txt_pager_create` | SDK 分配；`exr_pager_free`；成功接管 source.context，保留 font | 失败 source 仍属调用者；其他 context 至 pager_free | S font 及共享使用者 | C |
| `exr_chapter_options_defaults` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | I 独立输入/输出 | C |
| `exr_layout_page_kind` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | C |
| `exr_publication_toc_insert_before` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_toc_pages_create` | SDK 分配 `out`；成功转移引用；`exr_layout_free` | 依 `exr_layout` 类型行；输入借用至调用返回 | S font 及共享使用者 | C |
| `exr_toc_pages_label` | 借用 layout 的视图/字段；不转移所有权，不 free | 至 layout_free/驱逐；font 不得 free | R；释放/引用变更互斥 | C |
| `exr_toc_pages_entries` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | 允许只读观测 |
| `exr_toc_pages_entry_at` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | 允许只读观测 |
| `exr_toc_pages_entry_for_offset` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | C |
| `exr_publication_pager_create` | SDK 分配；`exr_pager_free`；保留 publication/font | 借 image/control context 至最后工作结束；config/CSS 复制 | S font 及共享使用者 | C |
| `exr_pager_chapter_statistics` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_pager_cfi_create` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | S 所有涉及 owner | C |
| `exr_pager_cfi_resolve` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_pager_anchor_create` | SDK 分配字段/数组；调用者用 `exr_anchor_free` | 拥有结果独立；宿主输出结构不由 SDK free | S 所有涉及 owner | C |
| `exr_pager_anchor_resolve` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_pager_read_text` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_pager_next` | 转移独立单页 layout；`exr_layout_free`；EOF 为 NULL | 可活过 pager/document；保留字体/图像；共享引用释放串行 | S 所有涉及 owner | C |
| `exr_pager_set_control` | 复制 control；借 context；无输出资源 | 新 context 至替换/pager_free；替换后旧 context 可释放 | S 所有涉及 owner | C |
| `exr_pager_set_hyphenator` | 保留新 hyphenator，释放旧引用；无输出资源 | 可释放调用者字典引用；session 更改时清缓存 | S 所有涉及 owner | C |
| `exr_pager_set_cache` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_pager_get` | 借用 pager 缓存 的视图/字段；不转移所有权，不 free | 至 驱逐/cache 更改/pager_free | S 所有涉及 owner | C |
| `exr_pager_cached_count` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_pager_cached_bytes` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_pager_set_checkpoints` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_pager_statistics` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_pager_position` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_pager_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_session_create` | SDK 分配；`exr_session_free`；保留 publication | font/image/control context 借至 session_free；config/CSS 复制 | S font 及共享使用者 | C |
| `exr_session_get` | 借用 session 缓存 的视图/字段；不转移所有权，不 free | 至 下一 get/clear/预算驱逐/hyphenator 更改/free | S 所有涉及 owner | C |
| `exr_session_cached` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_session_set_budget` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_session_set_hyphenator` | 保留新 hyphenator，释放旧引用；无输出资源 | 可释放调用者字典引用；session 更改时清缓存 | S 所有涉及 owner | C |
| `exr_session_cached_bytes` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_session_clear` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_session_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_layout_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_layout_memory_size` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | C |
| `exr_layout_writing_mode` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | C |
| `exr_layout_pages` | 借用 layout 的视图/字段；不转移所有权，不 free | 至 layout_free/驱逐；font 不得 free | R；释放/引用变更互斥 | C |
| `exr_layout_lines` | 借用 layout 的视图/字段；不转移所有权，不 free | 至 layout_free/驱逐；font 不得 free | R；释放/引用变更互斥 | C |
| `exr_layout_glyphs` | 借用 layout 的视图/字段；不转移所有权，不 free | 至 layout_free/驱逐；font 不得 free | R；释放/引用变更互斥 | C |
| `exr_layout_boxes` | 借用 layout 的视图/字段；不转移所有权，不 free | 至 layout_free/驱逐；font 不得 free | R；释放/引用变更互斥 | C |
| `exr_layout_paints` | 借用 layout 的视图/字段；不转移所有权，不 free | 至 layout_free/驱逐；font 不得 free | R；释放/引用变更互斥 | C |
| `exr_layout_image` | 借用 layout 的视图/字段；不转移所有权，不 free | 至 layout_free/驱逐；font 不得 free | R；释放/引用变更互斥 | C |
| `exr_layout_page_at` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | C |
| `exr_layout_hit_test` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | C |
| `exr_hit_test` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | 允许只读观测 |

### `include/exr/library.h`

| 函数 | 所有权 / 释放 | 生命周期 | 线程 | 重入 |
| --- | --- | --- | --- | --- |
| `exr_audio_checkpoint_free` | 释放 SDK 生成字段并清空宿主结构；不 free 结构本身 | 不用于宿主拼接的非 SDK 字段；清空记录可再次初始化 | S 资源读取/引用变更互斥 | C |
| `exr_library_audio_resume` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_library_audio_resume_get` | SDK 分配字段/数组；调用者用 `exr_audio_checkpoint_free` | 拥有结果独立；宿主输出结构不由 SDK free | S 所有涉及 owner | C |
| `exr_library_audio_bookmark` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_library_audio_bookmarks` | SDK 分配字段/数组；调用者用 `exr_audio_bookmarks_free(bookmarks,count)` | 拥有结果独立；宿主输出结构不由 SDK free | S 所有涉及 owner | C |
| `exr_audio_bookmarks_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_library_remove_audio_bookmark` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_library_clear_audio` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_library_open` | SDK 分配 `out`；成功转移引用；`exr_library_close` | 依 `exr_library` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_library_close` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_library_source` | 拥有 source.context；调 `source.release(source.context)` 或成功转交 reader | 保留 library，可活过 close；删 book/其他连接提交使源失效 | S 所有涉及 owner | C |
| `exr_library_epub_info_get` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_epub_location_free` | 释放 SDK 生成字段并清空宿主结构；不 free 结构本身 | 不用于宿主拼接的非 SDK 字段；清空记录可再次初始化 | S 资源读取/引用变更互斥 | C |
| `exr_library_epub_progress` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_library_epub_progress_get` | SDK 分配字段/数组；调用者用 `exr_epub_location_free` | 拥有结果独立；宿主输出结构不由 SDK free | S 所有涉及 owner | C |
| `exr_library_epub_note` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_library_epub_notes` | SDK 分配字段/数组；调用者用 `exr_epub_notes_free(notes,count)` | 拥有结果独立；宿主输出结构不由 SDK free | S 所有涉及 owner | C |
| `exr_epub_notes_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_library_remove_epub_note` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_library_import` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_library_import_unique` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_library_import_source` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_library_import_source_unique` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_library_import_file` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_library_import_file_unique` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_library_fixed_source` | SDK fixed document；`exr_fixed_free`；保留所需 library source | 可活过 library_close；仍受源失效规则约束 | S 所有涉及 owner | C |
| `exr_library_books` | SDK 分配字段/数组；调用者用 `exr_books_free(books,count)` | 拥有结果独立；宿主输出结构不由 SDK free | S 所有涉及 owner | C |
| `exr_books_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_library_update` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_library_document` | SDK 独立 document；`exr_document_free` | 可活过 publication/library；document 保留所需源 | S 所有涉及 owner | C |
| `exr_library_fixed` | SDK 分配 `out`；成功转移引用；`exr_fixed_free` | 依 `exr_fixed_document` 类型行；输入借用至调用返回 | S 所有涉及 owner | C |
| `exr_library_fixed_note` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_library_fixed_notes` | SDK 分配字段/数组；调用者用 `exr_fixed_notes_free(notes,count)` | 拥有结果独立；宿主输出结构不由 SDK free | S 所有涉及 owner | C |
| `exr_fixed_notes_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_library_remove_fixed_note` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_library_cover` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_library_note` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_library_notes` | SDK 分配字段/数组；调用者用 `exr_notes_free(notes,count)` | 拥有结果独立；宿主输出结构不由 SDK free | S 所有涉及 owner | C |
| `exr_library_note_text` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_notes_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_library_progress` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_library_progress_get` | SDK 分配字段/数组；调用者用 `exr_anchor_free` | 拥有结果独立；宿主输出结构不由 SDK free | S 所有涉及 owner | C |
| `exr_library_clear_progress` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_library_blob` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | S 所有涉及 owner | C |
| `exr_library_remove_note` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_library_reanchor` | SDK 分配字段/数组；调用者用 `exr_library_relocation_free` | 拥有结果独立；宿主输出结构不由 SDK free | S 所有涉及 owner | C |
| `exr_library_relocation_free` | 释放 SDK 生成字段并清空宿主结构；不 free 结构本身 | 不用于宿主拼接的非 SDK 字段；清空记录可再次初始化 | S 资源读取/引用变更互斥 | C |
| `exr_library_backup` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_library_delete` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |

### `include/exr/pdf.h`

| 函数 | 所有权 / 释放 | 生命周期 | 线程 | 重入 |
| --- | --- | --- | --- | --- |
| `exr_pdf_crypto_available` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | I 独立输入/输出 | C |
| `exr_fixed_open_memory` | SDK 分配 `out`；成功转移引用；`exr_fixed_free` | 依 `exr_fixed_document` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_fixed_open` | SDK 分配 `out`；成功转移引用；`exr_fixed_free` | 依 `exr_fixed_document` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |

### `include/exr/pdf_edit.h`

| 函数 | 所有权 / 释放 | 生命周期 | 线程 | 重入 |
| --- | --- | --- | --- | --- |
| `exr_pdf_annotation_write_defaults` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | I 独立输入/输出 | C |
| `exr_pdf_annotation_write` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | I 独立输入/输出 | C |
| `exr_pdf_annotation_remove` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | I 独立输入/输出 | C |
| `exr_pdf_metadata_write` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | I 独立输入/输出 | C |
| `exr_pdf_form_defaults` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | I 独立输入/输出 | C |
| `exr_pdf_form_read` | SDK 分配字段/数组；调用者用 `exr_pdf_form_free(fields,count)` | 拥有结果独立；宿主输出结构不由 SDK free | I 独立输入/输出 | C |
| `exr_pdf_form_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_pdf_form_write_defaults` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | I 独立输入/输出 | C |
| `exr_pdf_form_write` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | S options.font；其他输入 I | C |

### `include/exr/render.h`

| 函数 | 所有权 / 释放 | 生命周期 | 线程 | 重入 |
| --- | --- | --- | --- | --- |
| `exr_render_page` | SDK 分配字段/数组；调用者用 `exr_bitmap_free` | 拥有结果独立；宿主输出结构不由 SDK free | S 共享 font | C |
| `exr_render_page_ex` | SDK 分配字段/数组；调用者用 `exr_bitmap_free` | 拥有结果独立；宿主输出结构不由 SDK free | S 共享 font | C |
| `exr_render_page_background` | SDK 分配字段/数组；调用者用 `exr_bitmap_free` | 拥有结果独立；宿主输出结构不由 SDK free | S 共享 font | C |
| `exr_render_page_color` | SDK 分配字段/数组；调用者用 `exr_bitmap_free` | 拥有结果独立；宿主输出结构不由 SDK free | S 共享 font | C |

### `include/exr/text.h`

| 函数 | 所有权 / 释放 | 生命周期 | 线程 | 重入 |
| --- | --- | --- | --- | --- |
| `exr_text_analyze` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | I 独立输入/输出 | C |
| `exr_bidi_analyze` | SDK 分配 `out`；成功转移引用；`exr_bidi_free` | 依 `exr_bidi` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_bidi_scalars` | 借用 bidi 的视图/字段；不转移所有权，不 free | 至 bidi_free | R；释放/引用变更互斥 | C |
| `exr_bidi_reorder` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | R；释放/引用变更互斥 | 允许只读观测 |
| `exr_bidi_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_bidi_mirror` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | I 独立输入/输出 | C |
| `exr_bidi_base_level` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | C |
| `exr_font_source` | 借用 font 的视图/字段；不转移所有权，不 free | 至 font_free；encoded data 不得 free | S font 及共享使用者 | C |
| `exr_font_open` | SDK 分配 `out`；成功转移引用；`exr_font_free` | 依 `exr_font` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_font_create` | SDK 分配 `out`；成功转移引用；`exr_font_free` | 依 `exr_font` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_font_create_glyphs` | SDK 分配 `out`；成功转移引用；`exr_font_free` | 依 `exr_font` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_font_axes` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | S font 及共享使用者 | C |
| `exr_font_create_variable` | SDK 分配 `out`；成功转移引用；`exr_font_free` | 依 `exr_font` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_font_count` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S font 及共享使用者 | C |
| `exr_font_color_palettes` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S font 及共享使用者 | C |
| `exr_font_color_layers` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | S font 及共享使用者 | C |
| `exr_font_color_info_get` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S font 及共享使用者 | C |
| `exr_font_glyph_image` | SDK 分配字段/数组；调用者用 `exr_bitmap_free(&out->bitmap)` | 拥有结果独立；宿主输出结构不由 SDK free | S font 及共享使用者 | C |
| `exr_font_has_glyph` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S font 及共享使用者 | C |
| `exr_font_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_font_glyph_outline` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | S font 及共享使用者 | C |
| `exr_shape_defaults` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | I 独立输入/输出 | C |
| `exr_shape` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | S 共享 font | C |
| `exr_shape_vertical` | SDK 分配输出；调用者用 `exr_free` 逐个释放 | 结果独立，可活过输入/对象 | S 共享 font | C |
| `exr_glyph_matrix` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | I 独立输入/输出 | C |
| `exr_hyphenator_create` | SDK 分配 `out`；成功转移引用；`exr_hyphenator_free`；成功接管 provider.context | 依 `exr_hyphenator` 类型行；输入借用至调用返回；最终 release；无 release 则宿主保持 context 有效 | I 独立输入/输出 | C |
| `exr_hyphenator_create_discretionary` | SDK 分配 `out`；成功转移引用；`exr_hyphenator_free`；成功接管 provider.context | 依 `exr_hyphenator` 类型行；输入借用至调用返回；最终 release；无 release 则宿主保持 context 有效 | I 独立输入/输出 | C |
| `exr_hyphenator_create_patterns_ex` | SDK 分配 `out`；成功转移引用；`exr_hyphenator_free` | 依 `exr_hyphenator` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_hyphenator_create_patterns` | SDK 分配 `out`；成功转移引用；`exr_hyphenator_free` | 依 `exr_hyphenator` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_hyphenator_create_builtin` | SDK 分配 `out`；成功转移引用；`exr_hyphenator_free` | 依 `exr_hyphenator` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_hyphenator_breaks` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_hyphenator_query` | SDK 分配 `out`；成功转移引用；`exr_hyphenation_free` | 依 `exr_hyphenation` 类型行；输入借用至调用返回 | S 所有涉及 owner | C |
| `exr_hyphenation_breaks` | 借用 result 的视图/字段；不转移所有权，不 free | 至 hyphenation_free | R；释放/引用变更互斥 | C |
| `exr_hyphenation_memory_size` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | R；释放/引用变更互斥 | C |
| `exr_hyphenation_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_hyphenator_memory_size` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_hyphenator_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |

### `include/exr/textindex.h`

| 函数 | 所有权 / 释放 | 生命周期 | 线程 | 重入 |
| --- | --- | --- | --- | --- |
| `exr_text_index_available` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | I 独立输入/输出 | C |
| `exr_text_index_open` | SDK 分配 `index`；成功转移引用；`exr_text_index_close` | 依 `exr_text_index` 类型行；输入借用至调用返回 | I 独立输入/输出 | C |
| `exr_text_index_close` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |
| `exr_text_index_put` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_text_index_remove` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_text_index_replace` | 输入仅借用；返回纯值/写宿主缓冲；无拥有型结果 | 输出存储归宿主；输入至返回，不接管 context | S 所有涉及 owner | C |
| `exr_text_index_query` | SDK 分配；`exr_text_query_free`；保留 index | 可活过 index_close；control.context 借至 query_free | S 所有涉及 owner | C |
| `exr_text_query_next` | 借用 query 的视图/字段；不转移所有权，不 free | 至 下一 query_next 或 query_free | S 所有涉及 owner | C |
| `exr_text_query_free` | 释放调用者拥有资源/一个引用；不得传借用视图 | 本引用与借用视图不可再用；NULL 无操作 | S 资源读取/引用变更互斥 | C |


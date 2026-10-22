# R5 SDK 冻结跟踪

状态：候选已实现，尚未冻结。目标是在同一 SDK 上支持书库存储原件、有界 EPUB 导入、章内进度及同章标注，
再交 Windows pilot，随后 Apple/Android/Linux 并行接入。宿主仍采用原生 UI。

## 源码与验证记录

| 源码 | 云端运行 | 当前授予范围 |
| --- | --- | --- |
| `a0c35f5f01ff88244470ef395886410b78293693` | source `39857282570` 两作业成功；native `39857283787` 七作业成功 | 原件随机读第一阶段，不含有界导入/章内存储 |
| `b68776345ebc7956991d5d056a59828e1b305d78` | source `39859278474`、native `39859304551` | 首轮编译失败保留；两处 guarded output 同行触发 `-Werror=misleading-indentation`，未授予通过 |
| `f3dabe04e37e773ccbf20d6595421a890f3feff2` | source `39859742229` | 新增长章测量；继承上述待修编译问题，不能授予通过 |
| `2bece1b7a04b6ceb4542711f4a6c85f202e6fd0d` | source `39859836493`、native `39859836728` | native 七作业成功；source ON 成功，OFF 长章测量尚未结束 |
| `96c4f2c035a737ccf3f5be890d127d6efdd946f8` | source `39861407735`、native `39861408078` | 修复 CBZ 原件游标在 metadata/progress 更新后失效；source ON 成功，OFF 长章和 native Apple 尚未结束 |
| `352bb2d5f4007c62cd821da24b053d20abcd060d` | source `39863165651`、native `39863164990` | 边界点锚点快路；重复路径回归夹具误用公开构造器，后续修正，不能授予通过 |
| `fd210224a4eba206762c08de435a5e9edfdf2a90` | source `39863218905`、native `39863217247` | 当前候选；修正夹具，云端运行中 |

源码变更以完整 SHA 识别；不能将第一阶段通过项拼入后续源码的整体验收。
后续纯文档提交不改变受测实现身份。

长章观察到章首点恢复仍扫描整章。当前候选仅在空引文、单侧上下文为空且边界已得满分时
跳过该 scope 的其余扫描；外层重复章节仍全部比较。回归覆盖虚拟 100 MiB 源的读取次数、
取消和重复路径歧义。这不解决任意章中位置的扫描，也不授予整体性能预算。

## 候选契约

- 原件 `exr_library_source` 保留内部 owner 引用，不复制整本到堆；删除旧书永久作废旧 source。
  其他连接任意提交保守地使 source 失效，宿主必须重新开 reader。
- schema 7 在原升级事务内一次创建 bounded marker、章内 progress 和独立 notes 三表。
  旧 schema 1–6 升级不扫描正文，不转换旧全书坐标，旧 SDK 明确拒绝新 schema。
- source/file EPUB 导入只读取 ZIP/package 元数据，分块保存原件。原 ZIP 上限 128 MiB；
  作者/封面暂不提取，精确全书文本长度未知；重复原件保留已存在的存储模式与数据。
- 新位置采用稳定 part 索引 + 已解码 package path + 章内 normalized UTF-8 selector。
  写入/读取只验证存储与路由；正文 FOUND/MISSING/AMBIGUOUS 由 bounded pager 解析。
- 新标注要求显式同章 quote；评论修改保留 selector。旧全书 progress/notes 不接受新模式。
  不提供跨章单条标注或自动旧坐标转换。

完整设计与限制见 [存储契约](R5-BOUNDED-STORAGE-CONTRACT.md)、[原件随机读](R5-LIBRARY-SOURCE.md)。

## 冻结出口

1. 普通与 ASan/UBSan 的 source、schema/数据兼容、导入失败回滚、位置与 notes 测试成功。
2. 安装后公共消费者验证 file 导入→书库原件→bounded pager→保存→关库重开/改字号恢复。
3. 10/50/100 MiB 的单章/分章固定合成工作负载真实走 SQLite 原件，保留顺序与随机恢复、
   尾部读取、进度重开、页面 hash 及内存数据。沿用现有 WP6 工作区门槛，进程 RSS 单列，
   不把它改称完整绝对性能预算或真实语料。
4. 同源完整 native 七作业与工件核对完成；新候选的失败、跳过、缺证据不算通过。
5. 固定 API 头、源码和 schema，再开始 H8；新模式不能静默全文回退。

## 宿主接续

H8–H11 已由主代理团队接回，外部不再分派。Windows pilot 已开始开发，
保留并重验原 26 项/158 步，新增跨章与长章闭环。Apple/Android 已分到独立工作树并行准备，
最终验收等待固定 SDK 与 Windows pilot；Linux 按同一契约接续。各平台原验收独立保留。

H5 后续修补已在 `72c1e89` / `39862694733` 两 preset 严格通过，尚未合入共同源码，
见 [许可证复核](READING-LICENSE-REVIEW.md)；
H6 跨平台证据门禁的受测身份与新日志候选分列，见 [门禁复核](READING-PLATFORM-GATE-REVIEW.md)。
这些结果均不代表 SDK 已冻结或产品完成。

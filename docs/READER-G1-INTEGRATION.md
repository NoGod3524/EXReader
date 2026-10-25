# G1 共同源码候选

固定起点 `f43baf9182d75907c0cb5d6f77048f27bca8c950`，分支 `codex/reader-g1-integration`。
G01–G16 的交回提交以普通 merge 保留历史；完整身份见
[`inputs.json`](../tests/reader_g1_integration/inputs.json)。原单包 run 仅证明各自源码，不能授予本候选。

## 本次集成修改

- 从 `79af34fd0fd0dbfd2d2313dc34a6484685b7f2d2c0` 只取 reading-state 编解码拆分及其独立测试，不合入该提交的其它分支历史或 Android 工作流修改。
- 阅读命令、标注列表、标注导出仅链接 `EXReaderReadingState::reader_reading_state_codec`。实际调用 SDK 的测试消费者显式声明 SDK/resolve 依赖；产品模块不通过传递依赖引入第二个 SDK owner。
- 上述集成修改固定于 `ba25961961ae69222bfed4f7a98cb02bb1dc6847`。新门禁认证16份交付的逐文件Git对象及该次明确修改，拒绝未知路径、删除原材料或更改审查字节。
- SDK 3.40.0/ABI1、保护树、产品 schema1、wire/anchor 和冻结预算不改。

## 首轮共同验收出口

三桌面平台使用同一提交、同一 run/attempt：

1. SDK 安装一次，原13个可选包和G02–G06新增5包全部安装到同一 prefix。
2. 原G08 C11/C++实际TLS同步、第二SDK锚点解析、重定位、单SQLite及原正反例全部保留。
3. 从这个prefix重跑G02–G06原安装消费者/具名判定，包括分配失败和旧实现失败控制。
4. 新组合路径：真实侧载→产品元数据→书内搜索→具型标注命令→列表→JSONL/Markdown导出→仅移除本机下载→同原件重导入→重开SDK与产品→独立FOUND。
5. 新组合路径在删除原prefix后重新编译和运行；新公开头逐个以C11/C++17消费。
6. C消费者实际抽取阅读命令/列表/导出归档，并执行v1/v2 codec往返，链接图不得出现SDK调用或第二SQLite。
7. 同源码重新执行Windows原UI158、产品10、worker5、书架13、metadata18、账户32和定向键盘/UIA24；不使用只跑账户的诊断模式。
8. 严格汇总核对上游成功、ZIP大小/digest/有效期、报告和消费者身份；旧G08拒绝控制另增缺新包、错来源/attempt等负例。

所有构建、语法检查、夹具、测试与工件解析只在Actions执行。本地只做源码/文档/Git。

## 未完成范围

受测源码 `4e2dad0bc40aa5b523b98175f19fcb8ddde3eaa3` 在 [run 40118190108](https://github.com/NoGod3524/EXReader/actions/runs/40118190108)、attempt 1 的7个作业全部成功。root读取两个严格汇总及最终作业原始日志，最终记录 `accepted=true`、`problems=[]`；范围为三桌面安装组合与保留的Windows原生宿主检查。三平台初始/搬移后的新链均通过，G02–G06原判定器全部重跑；Windows实际计数为158/10/5/13/18、账户32、定向键盘/UIA24。

两套严格汇总在Actions内下载并复核同次ZIP的ID、字节、digest、有效期和报告/消费者身份，最终作业再次认证两份汇总。最终工件 `12570591453` 为624字节，SHA-256 `9ba538081f6f368f021c76e454e2776cf12f2e855a68d826095ebb9fa8e09fab`，有效期至 `2027-01-22T17:53:34Z`。七份工件、作业、消费者摘要和各平台具名判定见[验收JSON](validation/reader-g1-integration.json)。

首次失败 run `40116411109` 保留：集成探针把公开位置类型 `reflow_global` 写成 `reflow`；修复探针后整轮重执行，未放宽模块断言。Apple链接图检查复用既有ld64解析路径。此次证据登记仅改两份文档，受测源码保持以上完整SHA。

`cycle_complete=false`、`complete_product=false`。GTK、Android、Apple宿主新改动尚在各自owner分支；后续须固定交回并接入共同源码，再执行适用宿主和组合回归。Windows账户检查尚未覆盖真实远程云盘、接收/导入阶段取消、读屏朗读和Credential Manager不可用；部分接收分支由测试直接植入产品库，没有第二远端生产者。

G09分发路径缺口、G10/G11性能观测及G12–G16无障碍审计仍按原记录保留；报告完成不授予性能、读屏或真机。发布tag/Release另取授权。J01–J25手动工作包未在本候选实现。

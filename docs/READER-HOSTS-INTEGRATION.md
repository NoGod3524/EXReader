# 原生宿主共同源码候选

## 最新共同轮与后续候选

共同候选现普通合入 T01 Windows 云盘导入及批量整理交付 `7d8a2ef5aa2b12444bb4f968efc8828080c1bb53`，生产基点 `434075ff2367bad5834c2aa375b32f61a55e8d69`。原交付 run [40167556466](https://github.com/NoGod3524/EXReader/actions/runs/40167556466) attempt 1 已 success：46 项真实界面检查、J01 原47项、J10 原21项以及原 F1 264 / F2 130 / NavUI31 / records32 / UI158 及其余保留宿主套件，原 strict 链与新增12项拒绝均通过。root 复核了实际日志、来源、原件回读、提交后清理及独立意图恢复路径。

共同 workflow 复制原 T01 全部 Windows 生产步骤，在同一个宿主开启可选接入；原 J01/J10 消费者及宿主回归不改。T01 verifier 仅增加明确调用方 workflow 参数，由共同入口调用整个原严格链；最终汇总另核本轮 T01 summary 与原搜索报告使用同一实际程序，新增八项拒绝检查。尚未给共同源码授予这46项；先做 Actions 语法/协议预检，待 Android 最终导入交付合入后再跑完整共同轮。SDK 仍为原冻结3.40。

原程序目录诊断最终 run `40162074331` 通过29项，包括实际扫描中关闭父窗口。程序仍为 `e4356a6e` 工件中的原始二进制，测试 source 为 `cb7497dd`；初两轮诊断 `40161497966`、`40161675780` 的失败保留。窄交付 `600ef981` 只修目录输入驱动：读取实时 AT-SPI 主窗口焦点，再要求新 action、可见扫描阶段及非零 poll，保留全部业务断言。

生产候选先普通合入 Apple records `25eeb6aa`，随后普通合入最终交付 `0f0cf3ba374b13d0e8a3c8fc1e04b3f3cfb6c9f6`，共同生产基点更新为 `c1123b78819ab1fcadfaee33c72679213b9cc219`。最终受测source `19fde18968e03bb4e87d86b0ed650716ac02c9fa` 的 records full [40163099176](https://github.com/NoGod3524/EXReader/actions/runs/40163099176) 和 WP13 [40163097702](https://github.com/NoGod3524/EXReader/actions/runs/40163097702) 均完整success，包含各自严格汇总。iOS选择面板加原生ScrollView后，旧iPhone横屏关闭按钮与原选区失效断言通过；旧失败 `40161458572` 保留。

四套Nav/Search/Mapping/Shelf原回归已在先前25eeb源码上通过，尚不转授19fde或本共同源码。共同分支为原六套 Apple workflow 增加精确来源守卫入口，保留原分支守卫及全部构建、UI、工件认证。Actions额外核对六文件除守卫入口外与固定原版逐项相同。等Android最终交回后，在唯一完整共同SHA重跑六套；当前仍未授予共同源码。

source `e4356a6e13223469fdf3b2f3d5171a6e99ab10a6` / run `40159425518` 已终态 failure。
本轮最终认证确认三桌面18包组合和Windows搜索/目录/records32及其原回归；GTK目录 required step 失败，不能称为仅两项palette失败。
GTK新批范围的包内认证已核 UI27、原668、review4、后端684、真实receipt分配故障3场景/2次及records30；保留目录失败，strict仍为false。
Android作业已success，但共同最终认证在GTK处拒绝，未到达原始Pan截图/原件的最终重新认证，不把旧Pan proof转授本轮。

目录失败仍是第四次扫描：15秒内未观测到phase2，最后实测visible=1、running=0、phase3、40次poll、9000项，parent-close断言尚未执行。root已保留全部断言，补GTK实际焦点确认、fresh action条件和扫描状态时间序列；run `40161497966`仅复用已重新散列的本轮原程序做诊断，明确分开program source与test source，不授予当前生产候选。

后续候选普通合入 `2df6040666635bcd7b0349b035b8f4885757fdd0`，用真实owner存活位处理无需MAP的枚举分配失败；新增第4场景、累计3次分配失败。尚未共同复验。此前 `c49f24ab` / run `40159238563` 因root复制的GTK sideload pin仍是旧树而中止，已核差异仅为此前验过的Android专属无覆盖导出修复，并固定正确树；原轮保留。

下文此前各节仍分别归其固定source。

候选分支 `codex/reader-hosts-integration`；当前未验收，不能拼接原分支绿灯。直接普通merge保留以下来源及其失败历史：

| 来源 | 固定交回HEAD | 原范围 |
| --- | --- | --- |
| G1 | `3bcc6511c928665c0889a33bc98cf5e1bfadaccc` | 三桌面18包组合及原Windows账号 |
| Windows搜索 | `12f4f06cae2115fba90d3d43ebb0c291ea11e99a` | TXT13、多格式/生命周期25、键盘17及全部保留套件 |
| GTK阅读记录 | `401729ba9537b58c8566372fb953384ce61381d7` | 阅读30/后端261、Nav/Search及保留套件；真实页面配色2项失败 |
| Android阅读记录 | `5d7da81495e545901f7fc802af00e0b779d1d8c4` | API34 default x86_64模拟器，阅读16及保留套件 |

合并基点 `33167f2faa6cabae6656b8c1089a799dc7e5549e`。唯一冲突是codec安装消费者的Apple链接map参数，保留G1已有 `elseif(APPLE)`。Android来源带来原样已验的sideload导出分支：Android用 `renameat2(..., RENAME_NOREPLACE)` 发布原件，其余平台行为不变。SDK仍冻结 `9854061be331fe603a1822d9b2b36ee357154927`，3.40.0/ABI1，schema/wire/anchor不改。

新流程复用原workflow作业内容及原消费者，在同一run/attempt执行三桌面组合、Windows搜索及原回归、GTK全部原回归、Android原全套。原始检查不删断言。GTK设置仍按实际35项报告登记，不把两项失败变成预期拒绝；整体accepted保持false，只有各自真实通过的声明范围可独立登记。Apple宿主原回归、Android后续Preferences和GTK新批量导入尚由各自owner推进，不在本候选中预先授予。

前一受测源码 `7adda19cb5dd4108d4b4a434a8f2bb619519529d`， [run 40141520772](https://github.com/NoGod3524/EXReader/actions/runs/40141520772) / attempt 1 已结束。最终认证作业 `121018373358` 真实读取同一轮工件，`problems=[]`，各分项结果如下。整体 `accepted=false`，保留两项实际页面配色失败。

| 同源范围 | 结果 |
| --- | --- |
| 三桌面18包组合及严格汇总 | 通过 |
| Windows 搜索及所有保留套件、严格汇总 | 通过 |
| GTK 阅读记录、搜索、目录 | 通过 |
| Android 阅读16 / 搜索15 / 目录18，API34 x86_64模拟器 | 通过 |
| GTK 设置35项 | 33通过、2失败 |

两项失败仍为 `dark_theme_and_palette_change_page_pixels` 和 `light_foreground_and_background_change_page_pixels`。不授予完整设置、Apple宿主、真机读屏、性能或六目标产品验收。

原严格Windows与三桌面组合验证器只显式改调用workflow身份，保留原全部工件认证；最终读取真实GTK/Android报告，核同源/同轮/逐项结果与实际二进制。工作流、语法、负例、构建、测试及所有工件处理仅Actions。

首轮已终态：除GTK设置步骤外的全部生产作业通过，最后汇总遇到Python3.10不支持 `hashlib.file_digest`。改为标准分块SHA-256并在Actions前置自测已知摘要。原run及全部工件保留；新增只读诊断入口仅认证同一个原run，明确区分受测source与validator source、`diagnostic_only=true/accepted=false`，不拼接跨源码或跨attempt证据。正常新源码流程仍独立整轮运行。

后续源码 `f09148ba` / run `40140496079` 的 Windows 初始导入点击未生效，尚未进入搜索测试。探针原来只等待书架和按钮就绪，没有保证 BM_CLICK 的父窗口处于激活状态。`7adda19c` 在唯一一次点击前激活真实窗口、回读输入并记录按钮与书架状态；这一新源码的全部 Windows 搜索、账号和原有套件已通过。生产 `apps/examples/extras` 仍与合并基点逐字相同，两个失败 run 均保留。

## 新增导航与排版设置的共同候选

在上述已认证来源上普通合入 Windows 目录导航证据 HEAD `89252d4f1377c37917b2ad59cf54faa8103d6b67`（source `53dc10c6` / run `40142663081`）和 Android 设置证据 HEAD `91270f8e7b5a3085430992b97dd27f612666480a`（source `657ea2cc` / run `40138266576`）。新生产基点为 `e90c55885b95d14036b9ab2da6983b6cad01a779`，SDK、schema、wire 和锚点格式继续冻结。

新共同轮将原样重跑 Windows 导航31项、F2安装消费者130项及全部原Windows套件，并由同轮ZIP同时认证原搜索和新增目录报告；Android改跑已交回的设置完整作业，包含原Reading16/Search15/Nav18和新增Prefs17。Android仍明确保留 `page_colors_accepted=false`，不把记录公开API缺口的检查算作页面配色通过。

在新共同轮终态并完成认证之前，本文上面的分项通过只归属 `7adda19c`，新增两宿主的独立通过分别归属它们自己的受测源码。尚未合入Apple新宿主、GTK批量导入或Android新CBZ包。

## 导航与设置同源认证结果

共同源码 `f0c272c87b2402979292d0cd973d4f5e7a9f62fd` / [run 40143985644](https://github.com/NoGod3524/EXReader/actions/runs/40143985644) / attempt 1 已终态。认证作业 `121026966594` 重新读取本轮工件，`problems=[]`。Windows 搜索、目录导航及全部原回归、三桌面18包组合及严格汇总、GTK阅读记录／搜索／目录、Android Reading16／Search15／Nav18／Prefs17 均在这一个源码上通过。

整体 `accepted=false`；仅有的实际失败仍为 GTK 两项整页配色。Android设置控件有实际通过，但 `android_page_colors=false`。旧7adda轮原始记录、工件身份及失败历史保留在JSON中。Apple新宿主、GTK批量导入和Android CBZ仍未纳入这个共同源码的范围。
# CBZ 共同轮与原生选择器驱动修正

普通合入 Android CBZ 后生产基点为 `5a4168893e4c96f6496de26c9b284fca4f512daf`。共同 source `c217b29f86b78fa4e6d9a599690e8f6c42a9a56a` / run `40146977543` 终态 failure：三桌面 composition、Windows 搜索/目录与严格汇总、Android 作业 success；GTK 账户原生选择器在 Local-08 输入路径之前未收到剪贴板内容，账户 required step 失败，最终认证明确拒绝。不能把这次称为只有 palette 失败，也不能将 f0 的证据转授本轮。

日志中原生 entry 已聚焦但内容 SHA-256 为空文本摘要、selected 为空、accept=0。root 保留产品实现和全部原断言，只修账户测试夹具的输入驱动：先核活动 chooser 的真实 entry 焦点，再向该 entry 输入 ASCII 夹具路径，核 entry 与 selected 摘要及 accept 敏感状态后才确认。此变化限定在测试驱动，守卫明确列出该文件；`apps/examples/extras` 仍与合并基点逐字一致。两项 palette 旧失败继续保留，当前整体仍未验收。

# Windows 阅读记录接入共同候选

已普通合入 Windows 阅读记录证据 HEAD `2dcd325b31590bbb5374842e6c7f26fa2dcedd21`。独立受测 source `fdd625f3a45907a178db07ac8d0e4c06a635321d` / run `40153457202` 的32项真实记录与原请求恢复、24项记录协议拒绝、原F1/F2及全部Windows宿主回归均通过。共同生产基点更新为 `e0c28defc7f2113cb4ccdab5dfe1d2b072915a82`，守卫保持SDK与schema冻结，生产目录固定到该普通合并。

共同Windows作业复用完整 records 原作业，启用可选记录UI并安装既有G03/G04，保留原导航/搜索/宿主回归。严格汇总先执行原F1/F2认证，再认证记录32项及真实公开定位；共同最终汇总要求三个报告的宿主二进制摘要一致。尚未完成新共同轮之前，不把独立记录证据授予共同源码，也不授予Apple、GTK批量导入或Android平移。

## Windows 记录与 Android CBZ 的共同源码认证结果

source `15926e56034e26916b1e585cd9d907825379f17f` / [run 40154395150](https://github.com/NoGod3524/EXReader/actions/runs/40154395150) / attempt1 已终态，认证 job `121056256969` 实际读取同轮工件，`problems=[]`。三桌面18包组合、Windows搜索/目录/记录32项与全部原回归、GTK记录/搜索/目录、Android原92项（含CBZ10）均在同一源码上通过。Windows严格汇总同时保留原F1/F2和记录三个报告的相同宿主摘要。

整体仍为`accepted=false`，仅保留GTK的两个实际整页配色失败：`dark_theme_and_palette_change_page_pixels`、`light_foreground_and_background_change_page_pixels`；Android `page_colors=false`。原账户chooser输入故障已修正，本轮账户全套通过，不能继续将它列作当前失败。Apple宿主、GTK文件夹批量导入和Android平移仍由独立候选推进，不在本次共同授予范围。

前一 source `c2f652b97a0dda5f2bbd46fa3386dec231990185` / run `40153783967` 同样完成CBZ与原宿主认证，`problems=[]`、仅两palette失败；它尚无Windows记录。两轮身份及原f0证据完整保留于JSON，旧绿不转授不同源码。本次后续证据提交只改本文和JSON。


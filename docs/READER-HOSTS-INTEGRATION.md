# 原生宿主共同源码候选

候选分支 `codex/reader-hosts-integration`；当前未验收，不能拼接原分支绿灯。直接普通merge保留以下来源及其失败历史：

| 来源 | 固定交回HEAD | 原范围 |
| --- | --- | --- |
| G1 | `3bcc6511c928665c0889a33bc98cf5e1bfadaccc` | 三桌面18包组合及原Windows账号 |
| Windows搜索 | `12f4f06cae2115fba90d3d43ebb0c291ea11e99a` | TXT13、多格式/生命周期25、键盘17及全部保留套件 |
| GTK阅读记录 | `401729ba9537b58c8566372fb953384ce61381d7` | 阅读30/后端261、Nav/Search及保留套件；真实页面配色2项失败 |
| Android阅读记录 | `5d7da81495e545901f7fc802af00e0b779d1d8c4` | API34 default x86_64模拟器，阅读16及保留套件 |

合并基点 `33167f2faa6cabae6656b8c1089a799dc7e5549e`。唯一冲突是codec安装消费者的Apple链接map参数，保留G1已有 `elseif(APPLE)`。Android来源带来原样已验的sideload导出分支：Android用 `renameat2(..., RENAME_NOREPLACE)` 发布原件，其余平台行为不变。SDK仍冻结 `9854061be331fe603a1822d9b2b36ee357154927`，3.40.0/ABI1，schema/wire/anchor不改。

新流程复用原workflow作业内容及原消费者，在同一run/attempt执行三桌面组合、Windows搜索及原回归、GTK全部原回归、Android原全套。原始检查不删断言。GTK设置仍按实际35项报告登记，不把两项失败变成预期拒绝；整体accepted保持false，只有各自真实通过的声明范围可独立登记。Apple宿主原回归、Android后续Preferences和GTK新批量导入尚由各自owner推进，不在本候选中预先授予。

最新受测源码 `7adda19cb5dd4108d4b4a434a8f2bb619519529d`， [run 40141520772](https://github.com/NoGod3524/EXReader/actions/runs/40141520772) / attempt 1 已结束。最终认证作业 `121018373358` 真实读取同一轮工件，`problems=[]`，各分项结果如下。整体 `accepted=false`，保留两项实际页面配色失败。

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

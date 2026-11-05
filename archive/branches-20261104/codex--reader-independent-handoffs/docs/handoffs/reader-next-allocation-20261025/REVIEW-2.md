# 第二次接入审查记录

2026-10-25，root 重新读取 GitHub run/source/attempt/job 状态；本地未下载工件、未执行项目检查。

| 包 | 受测源码与完整 run/attempt | 当前结论 |
| --- | --- | --- |
| C06 | 909d05c31afdce27a7d8fbe861ead89f5b4552cf；40230743482/1，3/3 success | root 修复后 Windows/Linux 各216项；raw Markdown 导出的身份预检、完整 spool SHA-256 与分类补齐。Mac 实例为 ALREADY_VERIFIED，found_checked=0；不授该路径的公开 FOUND。封存8bf3c904。 |
| C08 | d521585af1a540f082b6cf4de42203480795b83f；40232710223/1，3/3 success | 三个独立公共 API 读回进程的只读复制路径通过；同 UID SELinux 拒绝仍为 pending，exact_page3=false。不授真机/六端。封存6a7c85ac。 |
| S14 | 74121fc2b24897c04ccaf0e1d4e5247bc9aa36b1；40231313668/1，6/6 success | 四个 SDK/桌面系统组合；修正裁判负例选择，42个真实拒绝控制通过。模块 header/src 保持1563f4ab；不含移动/UI/产品性能。封存2118eeeb。 |
| S17 | 537460e563874de1237d2e9d9bf2b0ca130c64d9；40230047146/1，3/3 success | 实际合同字段/API端点/attempt核验修复；各平台 legacy22/raw20/混用拒绝5。无宿主UI接入。封存abd3d841。 |

上述四包尚未合入共同应用源码。各自成功只授其原验证记录范围。

## 仍需处理

- C04：root 第一轮40234424624保留失败；Windows/Linux各169个原生测试和100边界检查通过。Crowley 真实书的原F5查询未命中，不能授完整F5。诊断40235597650的公开 SDK 正文表明原查询“Policy and Procedure TTR”在精确、casefold、空白折叠后均不存在；Procedure 不在正文。原清单/失败保留，后续独立提案不得覆盖旧预期。
- S13：原工作者超过三轮限制。root 单独修复原ZIP/实际程序/同次producer认证；40235577328、40235804635 的 Windows 均在新坏路径负例上失败。第二轮揭露 Windows ZipInfo 读取时也规范化名字，root 改查 orig_filename。最后完整轮尚未启动；Linux仍运行，不能与将来的Windows拼接授予。
- S15：原40227960455的独立新进程图检查成功，不覆盖宿主预加载3.40 imported targets后再找3.41包的场景。源码审查发现可能继续复用旧 targets；独立root修复中，不能授“已有target绝不混用”。
- S16：原40229935121通过但超过三轮限制（6完整+1取消）；接口与裁判源码继续审查，未合入。
- C07：原双向owner协议证据不等于完整GUI、六端或真机；继续审查。
- C02：旧40214285241超时失败；独立诊断封存fd03b888证明持久过滤/隐藏书架的旧测量谓词缺陷。root adapter按自然首屏与明确warm catalog策略实现中，不混旧profile样本，预算保持。

## 共同源码

新共同候选9a432d865a89c47201314ce54fb719e75d079676已发布到功能分支。
来源保护40235643699/1已success。Windows完整原链40235643579、完整raw owner40235643617、
GTK full40235651127、Android40235643574、macOS raw40235643642、移动raw40235643623、
Apple原记录40235643633均需各自完整终态和证据认证。40235643598仅GTK预检，不计full。

新候选补上旧共同源码遗漏的Windows raw owner链，并采用严格生成投影刷新Android查询缓存。
旧bd8的Android失败40229070687、Apple attempt1失败/attempt2成功均保留。
诊断40233907741只在另一个检查点观察到陈旧缓存，不能直接归因旧Group失败。

## 执行约束

所有编译、测试、语法检查、夹具、性能和工件处理只在Actions；本地仅源码/文档/Git与轻量任务管理。
追加保留C08一次本地工件处理尝试、S13/S16超轮数问题；这些均不构成验收证据。
SDK/模块/宿主/真机/性能分别授予。真实tag/Release仍待用户另行授权，完整产品目标保持进行中。

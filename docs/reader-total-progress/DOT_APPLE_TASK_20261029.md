# EXReader：交给 Dot 的完整 Apple 修复与验收任务

这是独立任务交接包，不是项目最终 closure handoff。用户本轮指令：“你把一整个任务交给dot吧”。

## 要完成的结果
端到端负责 Apple 手机/平板当前已确认故障：批注原生导入导出流程、分享关闭与详情恢复、历史跳转，以及相关原生组织开关回归。先把原5功能用例在iPhone/iPad同源码跑齐通过，再保留原规则完成Apple原39用例×macOS/iPhone/iPad及12组font/original/organization/sync补充验证与原ZIP认证，提交代码、精确证据和清晰剩余项后停止。不得以只读审查、计划、worker结束或部分用例绿灯当完成。

root保留共同整合分支、C1/C2/C3/Windows合入、最终总体验证与总handoff职责。Dot只修改Apple独立范围，不与root并改源码。真实发送并收到接手回执前，本包只表示准备完毕，没有完成委派。

## 接手与工作位置
仓库NoGod3524/EXReader。
当前修复分支codex/repair-apple-features-20261029，HEAD55e9c203fc58c5b94d3d951dad17c32d7f15a08f。
当前run40992359608：
- macOS SDK job123857527698、simulator SDK123857527508已success。
- iPad原5 job123858647139已failure：借用字体/分享、目录取消、history、null/concurrent通过，annotation240s超时。原ZIP12950219035/180602163B/SHA25668e47e9213e87b1d95c65b100603863be279031c0abb2d4875931b2af7610538。
- iPhone原5 job123858647168请接手时刷新，不能把本包写入时的运行状态当最终结论。
运行链接：https://github.com/NoGod3524/EXReader/actions/runs/40992359608

源码/Git/docs必须通过正常保存登录的官方InstaBox CLI：
npx --yes instabox@0.8.52 exec m_agqxv2s72g5vwdtsifu5cnmml4 --json --cwd /data/workspace/exreader-apple-features-repair-20261029 -- <命令>
机器agent-browser-mol0，ID m_agqxv2s72g5vwdtsifu5cnmml4。
不能另建/替换机器，不能改autoSuspend1800；root已有instabox-28维护，不重复建监控。
须使用用户已连接电脑上的正常CLI通路，不复制/读取/导出登录文件或凭据。若Dot无法访问此通路，先明确报告这一执行阻塞，不换执行器绕限制、不创建Claude云任务。

先向用户确认接手的任务范围、当前实际HEAD/运行状态及InstaBox通路，写一个可供root从GitHub读取的接手回执。root确认接手后停止Apple源码修改。此前root已在此分支工作，不得reset/force-push历史或重启其已停worker。

## 可修改范围
examples/apple/HostWave3Views.swift及必要最小Apple宿主修复；
tests/reader_team24_apple/ui/FeaturesUITests.swift只允许辅助查找/原生输入/稳定同步，原5个test函数正文、setup/teardown、原等待/拖动/测试预算不变；
tests/apple_features_repair_20261029/、tools/reader_composition/repair_apple_features_admission_20261029.py、对应独立workflow和docs/reader-total-progress/repair-apple-features-20261029.md。
组织修复examples/apple/HostViews.swift当前来自a6e2e506，手机/平板原6已独立通过，Mac分支保持原版。
需要完整39+12时，可以建立codex/dot-apple-complete-20261029独立分支及明确的wrapper/workflow/source admission；复制原运行正文，只改变独立分支触发、准确source准入与helper blob pin。原checkers/严格owner guard保留，不放松断言或删失败病例。不得在全套分支误调用只接受7路径的focused guard；完整source需声明自身精确路径/旧5正文冻结比较。

不可修改共享SDK/public ABI、C1/C2/C3/Windows迁移源码、冻结108目录或原始验收规则。
不得动/data/workspace/exreader-resume-20261029：其HEAD9330be495bffdf3bf421bdc32b963e3fbfc4c9fe，有89路径STAGED未commit（79producer/docs+10composition），仍暂绑定908/helper95ec6a73093d4a9b0a150f2010b66cad86c19fa6；root会自行更新整合。
共同remote codex/public-product-resume-20261029仍343bb94eb6513beaf5b344e7828342f6602a3b7b；Dot不推共同分支。默认分支、PR、tag/Release均禁止。

## 全部强制约束
所有构建、语法检查、测试、fixture生成、benchmark、原始ZIP下载/解包/xcresult解析，只能GitHub Actions。Windows/InstaBox/Dot自有电脑均仅源码、Git、docs和轻量状态。
保留原用例正文/断言/数量/预算及全部失败；原5的90s wait、24drag cap、240/360 native预算与setup/teardown均冻结。不能通过预建测试文件夹、直接模型调用、伪造hittable/native UI、跳过系统选择器等代替原输入。
不拼不同source/attempt，不重试未解释D13，不改固定108目录计分。只能用本轮同一实际源码的原始结果授予该源码通过。
不能读取/导出凭据；不能绕网络/审批或关闭TLS。
原Windows dirty C:/Users/Oscar/OneDrive/文档/ChatGPT/EXReader不碰；旧VM /data/workspace/exreader-composition/2f215f57不切换/覆盖。
原3Claude本机BG、原3内置开发worker、新增2只读复核都已停止，不重启它们。不要创建Claude云任务或额外开发范围。

## 已定位的故障与当前修复
先完整读当前分支docs/reader-total-progress/repair-apple-features-20261029.md（含每次精确原工件pins、首断言、诊断run）。
审计分支codex/handoff-evidence-resume-20261029的repair-current-failures-20261029.md、closure-repair-readonly-reviews-20261029.md、instabox-resume-20261029.md、Apple A/B final docs/evidence JSON也必须读取。
1 旧generic features.cancel查询在Files关闭后触发remote kAXErrorInvalidUIElement，61.07s重试。typed Button/Text/Scroll查询已修；当前不能再笼统把所有延迟归为模块解析。
2 分享adapter marker可能消失而真实ActivityList仍开。当前native query要求ActivityList包含实际header.closeButton；观察到真实share后，features.close helper最多3秒等实际ActivityList消失且原close可点，防原body即时outsidefallback误关父sheet。没有额外隐藏tap/model调用。产品completion callback清空SwiftUI sharing绑定保留。
3 Files异步加载：Recents的On My侧栏可能迟到；也可能已在真实local browsingRoot，无需不存在的侧栏cell。55e9同时识别local root和真实侧栏入口；Markdown等首个JSONL已创建folder，仍原生创建/Open/内容核对。最新iPad仍annotation timeout需从原ZIP定位最后实际动作，不能盲调预算。
4 远处原生1600px/s、0.78viewport bounded手势，近处controlled slow；按真实12px可见交集+enabled+hittable输入，每次重新查目标，24cap不变。8eda的iPad annotation216s曾通过，但该source借用字体/分享整例失败，不能拼src。
5 两只读复核已完成。Apple复核提示local存在但不可点时Browse分支和目录内容加载边界；整合复核未见确定schema/path/count阻塞，均不是运行验收。

## 保留历史
550/run40982450461 iPad4/5、iPhone3/5失败；
908/run40986067818两端4/5，share/history等过，但annotation iPad导航断言、iPhone完成全部功能后253s超原240s；
8eda/run40989249100 iPad4/5（annotation216s过、share返回失败）、iPhone3/5（share返回及localcell等待失败）；root原ZIP诊断40991581897/source08fbabe9f999b485c3e4a5aed25c47efdbeed84c success。
21194/run40985138048、04f8/run40985492438为明确superseded取消，不授产品通过。
更早329d/343全套fail、141 iPad BlobNotFound/historyfail、9019Togglefail全部保留。
组织a6/run40981500259两端原6已过；GTK c1de/run40980931719和独立40983431462已过，但仅各自source有效。

## 交付与完成标准
先刷新当前Actions，对失败在Actions内重新绑定source/run/attempt/job/artifact ID/bytes/SHA256、读取真实首断言与原树/输入事件，再最小修复。所有producer与收尾必须保留原始ZIP和失败。
只有当前原5两端全过后再跑原完整39×3+12补充及同源SDK/程序身份/原ZIP认证；只改wrapper准入/触发，不改原运行/计数/判定。若在完整阶段发现当前修复造成的回归，仍归本任务，修好后重跑必要同源检查。
在独立分支提交docs/reader-total-progress/DOT_APPLE_RESULT_20261029.md，给root：
- 最终实际源SHA、相对a6/343精确文件列表与blob来源，哪些是runtime、helper、wrapper、docs；
- 每个run/attempt/job真实结果、artifact ID/bytes/SHA256、原39和12组是否完整、SDK/program/manifest身份；
- 历次失败链接/原因、尚缺证据或明确阻塞；
- 不授完整产品/P0/真机/F07/F08/F12，不改95/108（最近真实目录40928834086 attempt2/source5d4ec0ebd94fa3fabbf19af016073aef2877ac20；F01–05/F07–12 pending，F06仅旧8f8acf/run40678657371）。
root从GitHub取该结果独立核验，之后在共同最终source重新跑必要组合检查，再合入共同分支。Dot不得自行宣称已合入/最终项目完成。交回结果后停止本任务，不自动下一包，不向其他人发送消息。

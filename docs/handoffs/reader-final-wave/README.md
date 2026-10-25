# 最终阅读器并行工作包共同约束

固定实现起点：`0889f7d1e9a537c6c1b05456547e016b26e1cd85`。文档分支HEAD不是实现起点。
每包独立worktree/分支，以任务页命名为准（C/S为`codex/reader-fw-<id>`，Dot为`codex/reader-final-dNN`）；一个包只有一个writer。

目标是六平台原生互通阅读器。主线当前独占Windows/GTK raw3接入、Apple失败收口及共同源码整合；本批不得改这些owner文件。
原3.40冻结SDK=`9854061be331fe603a1822d9b2b36ee357154927`；批准3.41 SDK=`edddc463c06ed5731195cdb8f06b2df6dff7699e`。
旧schema1、wire、冻结预算、1710计数、历史失败不变。禁止WebView或新增服务器作为产品必需依赖。

## 执行规则

- 仅允许各任务页列出的新增路径。不得修改现有apps/、examples/、SDK、原tests/、原workflow/、保护树、预算或系统账号配置。先查已有模块/检查，复用，不重复实现J/G系列已交付功能。
- 本地仅阅读源码/文档、编辑、Git。全部构建、测试、语法检查、夹具生成、截图、benchmark及工件下载/解压/解析只能在GitHub Actions。禁止cpuse。
- 授权独立功能分支commit/push与自有Actions，无需再问用户是否push。不得推默认分支、开/合PR、tag、Release、签名/公证或删除任何会话/文件。
- 新workflow只能触发自己的分支/路径；矩阵max-parallel=2，每包同时最多一个live run。先确认原run已terminal再修复重跑；不因轮询超时重启。最多三轮失败后交明确阻塞与完整源码，不刷CI。
- 使用现有官方账号/工具；不读取或打印用户真实令牌/密码。测试凭据仅CI临时生成，扫描日志和工件，测试隔离目录由job创建。
- 不另起子代理，不转交，不扩任务。需要改owner代码时交精确诊断/建议和真实失败，root统一修；不降低断言、删失败或改成预期拒绝。
- 不把不同source/run/attempt、不同job的成功片段拼成完整通过。二次checkout/原工件消费者须明确分开实现source、producer source、SDK source、verifier source；认证原ZIP字节/digest/有效期及真实程序hash。
- 真机/读屏/USB线缆/性能预算只按实际执行分别授予；模拟器、元数据静态检查、AX树或read-only清单不授更大范围。缺项pending并具体说明。
- 输出失败必须可以复现，记录原始source/run/attempt和原log；没有证据就accepted=false。最终产品授予由root控制。

## 可只读引用的当前交付

| 内容 | 不可变源码/证据 |
| --- | --- |
| 共同原生基础 | `25bc0c67971f81491f50e0a3caaaf7e509bb7e35`；原11个workflow九过两拒，不能称完整产品通过 |
| Windows简洁UI | 受测 `eab342ef456be4a8a1811e5249e3c217d906ce8a`，封存 `f355525b74ae261db536c56200e46643919ef323`，run40201283788 |
| GTK简洁UI | 受测 `57203a52aee439be5194ee0a4b13563a975e8daf`，封存 `9fc407a5cce5a0bfe644a60bd8dc29f84dea6d0e`，run40206458217 |
| Android实际raw3 | 受测 `4a04a9cc74dde67f755c87e87b278d63a254a3ac`，封存 `caa84411ae79c866c28cf982243b6cb80b4bbe49`，run40207467982 |
| Mac实际raw3 | 受测 `15dab6b2270dc296ed6239db67ced2e22d255e65`，封存 `44eabdc86b3b84d986f81dbaf8cee92b1829cea8`，run40196978163 |
| Android→Mac接收 | 受测 `5062d5cd570eb9be9449e790895b5430d344d11d`，封存 `cd6fbe2e4f86c8ebd564d06518427c2642d045f6`，run40210925809；不是共同源码双向 |
| Apple移动候选 | `72c6bbdd14ebf3be453fa7f0da81119d52675eb5`/40203714083整轮失败，iPad单叶过不授整轮 |
| Raw metadata独立包 | 受测实现起点0889；run40209325599四作业过，Win/Linux两配置各29项；不授host |
| 私有capture codec | `5eb0ea09c53e37a371be558d52ec9c958aed80fc`/40211344040单元通过；不授SDK/host/wire |

平台测试可从上述固定producer另checkout/下载认证原工件，不能把它替换成当前branchHEAD，也不能隐瞒source不同。最终统一源码尚待root整合，各包提供可重新输入source/run表的工具。

## 交回格式

提交自有实现+workflow+文档+`docs/reader-final-<id>/validation.json`；未跑时accepted=false。
交回完整受测SHA、docs-only封存SHA、远端branch、run/attempt、job及artifact ID/字节/SHA-256/有效期、实际检查项、原失败和未验证项。
状态写到worktree根 `HANDOFF-RESULT.md`（可提交），并在最终消息给出结果。CLI日志供root查收。
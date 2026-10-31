# C02 原始产物审计

仅在 GitHub Actions 执行此目录的 Python。需要 Python 3.12、Git、已按通常方式认证的 gh CLI，以及 contents:read / actions:read。脚本不会构建 SDK、改注册表或修复生产文件。

```sh
python tests/migration/c02_completion_audit_20261031/audit.py \
  --manifest qualification.json --output audit-evidence --require-complete
```

qualification.json 按 manifest.template.json 填入最终合格源码的真实 run、attempt、job、artifact ID、原 ZIP 字节数与 SHA256。模板的 null 必须替换。所有包必须属于同一 producer source。失败历史继续保留，不能将别的源码的绿步骤拼入这一份请求。

脚本依次保存每个包的 run.json、jobs.json、artifact.json 和 original.zip；核对 GitHub API、指定 attempt 的作业与上传时间、ZIP 字节数和摘要。随后在内存读取原 ZIP，验证路径、CRC、完整文件清单和内部语义。结束时重新计算保留的每份 original.zip 摘要。运行失败时也应使用 workflow 的 always() 上传整个输出目录。

## 已实现的协议

- Windows / Linux 原 ABI2 都要求 81 项、准确六行已知失败、原始 exit=1；ABI3 都要求 16 场景 / 64 项 / 0 失败。
- Windows 原生日志要求 46 场景 / 301 项，十个原生进程 barrier 与原始 46 对 journal/intent。独立重算完整事件 FSM、行 seal、BEGIN/ACK 哈希链、manifest、连续旧 count 和完整 tip。
- 持久 gate 要求原 28 场景 / 309 项、四个进程 barrier；独立解码原始 344B gate 记录，包括保留的损坏负例。
- Registry 要求请求中明确指定的最新案例数与检查数，保留 50 / 530 下限；逐项核对 11 个准入命令场景和 6 个真实 Windows 产品场景。
- Windows 产品原件还须核对 18 个 guarded legacy 场景和三个产品 profile 各 6 个场景、实际执行与正式包内 PE 字节、进程与 owner probe、SDK 数据、窗口、PNG 和 23 个模块。静态 SDK map 与无替换运行时 DLL 检查按实际强度报告，不声称独立 MSVC 重链接。
- read-only scanner 核验请求中的最新 cases/checks/observations（当前29/91794/6603），逐条重建6603份带SHA的输入观察，并独立拒绝保留的19份完整语义负例。它仍是组件证据，不冒充生产修复。
- 原迁移器回归必须执行对应源码的全部 @case 场景，逐项检查每条断言。
- 实际迁移案例数来自对应源码的最终 len(r.rows) 断言，不固定为历史 25 项。逐案例核对 barrier、被终止的进程、命令退出码、注册表导出的 INPUT / PREPARED、实际原始文件、保留旧产物与最终数据库和账本。provider 文件清单逐项与 producer source 的 Git 内容核对；只接受 Git blob 字节或 Git checkout 的 CRLF 形式。
- 实际 journal 切点要求 phase 1..10 × sequence 0/5/9/10。repair 切点由 required_repair_phases 指定，目前必须包括 950..955 × 原始 sequence 0/10。还要求 gate 短写 201/203 和 repair archive 字节 / 身份拒绝两例。
- 独立解码 WH3RPR01 修复计划，核对 INPUT 权威、封存三份原始字节、最后完整 ACK 前缀、计划 gate、修复历史和退休状态。额外核对225字符真实root，以及保留FileID将当前完整ACK9回退至ACK5时的拒绝和原文件不再改变。候选下一行由 INPUT 的原生对象、快照 / 内容摘要和完整 FSM 独立推导，不能跳过一个完整 ACK。
- 使用 Python SQLite 的内存 deserialize 与 query_only 直接核对实际数据库：应用与 schema、原文、内部账本与外部 mirror 原字节、reflow / fixed / audio 批注，并核对唯一引用与歧义引用两个独立 TXT 场景。没有导入生产 verifier。

## 跨平台实际产物与独立解码

完整请求包含十二个角色：native-windows、native-linux、persistent-gate、registry-product、host-android、host-macos、host-ios、host-gtk、posix-native-linux、posix-native-macos、posix-migration-linux、posix-migration-macos。manifest.template.json 列出真实工作流与作业名，所有 source/run/attempt/job/artifact 字段必须取自同一生产源码的实际运行。runtime_prefix 与 binaries 是原 ZIP 的精确成员路径；提交请求前须在 Actions 核实，不能按 basename 搜索或遇错切换前缀。

- Android：独立重读原 app-raw.tar、原生 FD/fstat 观察、固定 Context 目录、A/B/S 原字节与 SQLite；核对实际原生 source 最后释放及进程死亡后的 PENDING 拒绝。普通 Debug/Release APK 的 ELF 导入/导出与 SDK PT_LOAD 段须绑定原安装 SDK，检查原件而非仅信 receipt。
- GTK：检查实际运行的四份原生快照、UID 与目录/文件身份、实际 SDK 借用顺序以及普通产品包。保留三个实际程序的完整链接输入、原始构建 ELF 和执行 ELF；在固定编译器/链接器 SHA、严格参数白名单下独立重链接，要求三个 ELF 整字节相同，并从链接 map 验证 SDK 与 C02 实际符号来源。
- macOS/iOS：核对原始五阶段、九条路由、实际 SDK 资源、进程观察、两个真实 app bundle 和安装的 C02 archives。分别校验原始安装 SDK 与签名后 SDK 的全部 CodeDirectory 代码页、签名结构和特殊槽；只归一化已验证的 20 字节 LINKEDIT 长度/签名长度，签名前其余全部字节须精确相同。
- POSIX native：独立解码实际原生输出、INPUT/PREPARED、floor/head 及每项 native ID，保留原 28/207、目录 scope 10/81 和迁移 API 17/130。按 qualified source 中的开关强制新源码保留 confirm 前后的 head 原件；旧工件缺原件时不得伪造补齐。
- POSIX 实际迁移：生产 profile 必须使用 352B FLOOR 与 296B ACK header，绑定实际执行二进制、真实 SDK 数据库、原书/批注/账本、两成员发布和 fresh process recovery。272B 组件 FLOOR 不可替代。独立生产 adapter 已验证实际 owner 的原始 36 场景、65/135 历史回归、INPUT/PREPARED、原生 ACK/FLOOR/head 和 SDK 数据；d326 源码另有 20 个实际 Repair 场景，覆盖残缺 B/C/head、六个真实 SIGKILL 切点、连续中断、完成后的终端 ACK 丢失与 pre-BEGIN 修复后的新一轮迁移。独立 Repair 审计重建 PLAN/APPLIED/DONE、原件封存、原生身份、完整 ACK/FLOOR/head 和实际 SDK 克隆证明。十二角色齐全本身不表示完成。

所有 host 报告仍须保留六个核心运行观察（clean、PENDING、missing binding、最后借用阻止 owner、最后释放允许 owner、fresh process PENDING 拒绝），但 JSON 的 passed/complete 字段不能代替原生文件、SDK 与对象身份检查。生产输入、provider 文件和旧回归案例均从 qualified Git source 独立核对。

实际迁移 runner 的成功 detail 应包含 evidence_dir（相对 actual-migration/cases 的目录名）。二次修复进程案例还需 repair_phase、repair_owner_exit、origin_phase、origin_sequence；原始日志分别为 killed-owner.log / repair-owner.log。篡改案例保存 prior_stage / after_stage 的 dev、ino、sha；repair archive 拒绝案例保留 raw_before 三文件摘要。新增未知协议应补 decoder，不得删掉缺口判断。

## 重新封装负例

从已通过的 Windows 原 ZIP 文件集生成 9 份新的 ZIP。每次都重新生成文件清单、文件摘要、ZIP CRC 和新 ZIP 摘要；内部 BEGIN/ACK 篡改还重新计算记录 seal 与后继链。包括 source/run/attempt 重绑、假 full-P0、保留字节、重复旧 count、错误 ACK 绑定、内部行损坏、降低原 301 项计数。每份新 ZIP 与拒绝原因均保留，原 ZIP 不变。

Android 另有 8 个原生语义负例；Apple 每个平台包含 8 个原生负例和 8 个 SDK 字节对负例；GTK 包含 8 个原生负例和 8 个链接/二进制负例；Windows 产品另有 8 个完整重放负例；POSIX 实际 owner 每个平台保留原 8 个重封装负例，并追加独立 Repair 的重封装负例。每个有效包另需拒绝其余 11 个角色替换。新负例保存篡改包、原 ZIP 来源、重新生成的清单及精确拒绝原因，再调用相同独立解码路径。原始 ZIP 始终保留。

只有明确检查当前局部证据时才使用 --allow-incomplete；其输出 scope 为 component-evidence，缺口原样列出。完整验收使用默认行为或 --require-complete。此脚本不会更新正式 95/108，也不授予 F12 / 全 P0 验收。

## 独立 Actions 入口

workflow 为 .github/workflows/dot-c02-completion-audit-20261031.yml，每个作业最多15分钟，contents/actions均只读。audit代码始终checkout本次运行的github.sha，并核对本地HEAD；producer source独立固定，不会把audit提交当生产提交。

默认 push / dispatch 选择 windows-components，仅允许 qualification.windows-faae.json 已固定的 faae61879441085d800879332699d0b6fd5e2307：原Windows/Linux native包、persistent gate包、Windows registry/83项真实迁移/scanner/CLI/host包。四包的run/attempt/job/artifact ID、字节数和SHA均写死，并再次经API校验；组件模式保留full_c02_complete:false。

dispatch输入：
- producer_source：完整40位生产提交SHA，默认上述faae提交。
- scope：windows-components、selected-components 或 complete-c02。
- qualification_manifest：selected-components 与 complete-c02 使用完整 JSON。前者可选择显式局部角色，后者必须包含十二种角色并与 producer_source 相同。

固定 windows-components 模式拒绝自定义 manifest 或更换 producer_source。selected-components 必须带 Windows native 或实际 host 的独立篡改负例，输出保持 component-evidence。完整模式使用 --require-complete，任何尚未实现的原生能力、实际修复或 SDK 字节绑定都会留下缺口并失败。工作流先在Actions做Python语法检查，始终上传准备日志、API响应、已下载的原ZIP、失败输出、最终scope与摘要清单。

示例调用（workflow发布到可dispatch的ref后）：
```sh
gh workflow run dot-c02-completion-audit-20261031.yml \
  --ref codex/dot-c02-native-journal-20261030 \
  -f producer_source=faae61879441085d800879332699d0b6fd5e2307 \
  -f scope=windows-components
```


## 同一源码的十二角色请求

qualification.d326.json 固定生产提交 d32603dc65bccfd65901239d21cb65cd10bca168 的十二份原 ZIP。审计器可以来自后续提交；请求中的生产源码与所有原件身份保持不变。复验通过以下 dispatch 启动，脚本及 ZIP 读取仍只在 GitHub Actions 执行：

```sh
gh workflow run dot-c02-completion-audit-20261031.yml \
  --ref codex/dot-c02-native-journal-20261030 \
  -f producer_source=d32603dc65bccfd65901239d21cb65cd10bca168 \
  -f scope=complete-c02 \
  -f qualification_manifest="$(cat tests/migration/c02_completion_audit_20261031/qualification.d326.json)"
```

只有该运行的最终 workflow receipt 同时记录 passed:true、full_c02_complete:true、12 份原件、空 missing_capabilities，且原始文件与所有独立负例均通过，才能据此报告完整 C02。分组审计的成功继续作为局部证据保存。


## 完成记录

[最终 complete-c02 运行 41194417880/A1](https://github.com/NoGod3524/EXReader/actions/runs/41194417880) 已成功：12 份原始 ZIP 摘要保持不变，105 项语义篡改负例和 132 项角色替换负例全部通过，missing_capabilities 为空，最终回执 passed:true、full_c02_complete:true、audit_exit:0。

生产源码固定为 d32603dc65bccfd65901239d21cb65cd10bca168，实际执行的独立审计源码为 5d9fc903ab015c50c3ce25b57a2680218bb0d419。结果 JSON 的 SHA256 为 d121c13ed27c0a9f0eb735be13f08118c1da41083bcca9caab6c9bc1d2fa8474。审计产物 13039319680 共 1055858172 字节，SHA256 为 a0dbd292b2196fa0086fe87ba08174c9df58a20c7b19a246a370521f90dcd33f；其中保留原 ZIP、API 元数据、负例包、拒绝记录与摘要清单。

POSIX 每个平台均保留原 36 个实际场景和 65/135 历史回归，另通过 20 个实际 Repair 场景、原 8 个 owner 负例和新 8 个 Repair 负例。SDK/C01 与原 ABI2/ABI3 基线保持原样，全部失败历史保存在中央交付记录；正式 95/108、F12 与全 P0 的边界仍按前文执行。

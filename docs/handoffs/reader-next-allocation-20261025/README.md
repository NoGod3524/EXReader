# 新一轮并行包：五Claude、七Dot、五DeepSeek

实现固定起点 `e67d87cbeabb2457e0852f681ef0b27b2c0da4d8`，已在远端
`codex/reader-raw3-common-integration`。它是已组合的源码候选，尚未通过共同源码六端验收。
每包从该SHA建立独立worktree与指定分支，不能追移动主线或重置别人的目录。

批准SDK3.41为 `edddc463c06ed5731195cdb8f06b2df6dff7699e`，旧3.40冻结为
`9854061be331fe603a1822d9b2b36ee357154927`；七raw模块为 `56793e7c`，版本revisions0.4与companions0.2。
旧SDK、ABI、预算、产品schema1、wire envelope1和旧anchor1/2均保留。禁止改root宿主、原测试/裁判、
其他包或SDK保护树。仅任务明确拥有的模块可以改；SDK修复只交自己目录内的patch，CI在隔离副本应用，不能提交改写冻结树。

任务页列的是完整工作，不只交设计或空接口。优先复用已有静态组件、原模块和安装后的公开API，不引入WebView、
重复解析器、新产品数据库或动态插件框架。无实际不兼容时交真实复用证据，不为凑改动添加新API。
SDK只通过公开API读取；产品SQL只读且限测试观察，不能改SDK私有SQL、修数据或注入偏好来过验收。

所有构建/测试/语法/夹具/截图/benchmark、工件下载/解包/解析均仅GitHub Actions。本地仅源码/文档/Git。
每包独立新增workflow，只触发自己的功能分支；自行push，无需另问。不推默认分支、不开合PR、不打tag/Release，不用cpuse。
凭据只用runner生成测试秘密，不读真实账号、用户书库或用户密码；TLS校验不得关闭。

每包最多三轮完整CI。等上一轮terminal后看根因再修，不反复轮询未变的CI；日志读取限定所需错误段。
超过三轮如实交回。冻结预算、原断言、来源与原失败不得放宽/抹除；崩溃、超时、注入和缺观察都不是通过。
汇总必须认证同source/run/attempt/jobs、唯一原ZIP、size/digest/expiry、实际程序及完整具名检查；不能只信accepted字段或静态库hash。

明确harness、目标源码、补丁前后树、SDK和程序来源。新SDK patch的产物标为未接纳候选，即使version字符串未改，
也不能冒充批准SDK；真正接纳与最终同源验证由root负责。模块默认旧行为保持，raw入口显式、混用拒绝、失败不写、可取消、
所有权和资源释放写清。文档和代码证据分开：未跑accepted=false，文档封存用 `[skip ci]`。

每包最终交完整源码/目标/文档SHAs、run/attempt/jobs、工件ID/bytes/SHA-256/expiry、程序hash、完整结果、
旧失败及未验证项。交回文件为 `HANDOFF-RESULT-C04.md` 等唯一名字，不覆盖其他包。不要再派子代理。

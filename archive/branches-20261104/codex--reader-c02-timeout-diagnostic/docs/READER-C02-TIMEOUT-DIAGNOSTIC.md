# C02 Windows 超时独立诊断

固定原 source：`169b0be3c1c8199be0211649412d23d9e34041e4`；原 run：`40214285241/1`。
只新增独立诊断脚本、工作流和本记录，不改原 C02 工作区、生产、旧预算、计划或裁判，也不控制原 run。
所有 ZIP 解析、语法与原生窗口观察仅在 Actions。诊断已完成；它不授予原 C02 性能验收。

原 Windows 两作业 `121232981888`、`121232981941` 已 cancelled。
round1 ZIP `12612017276` 为 1,733,980B，SHA-256 `290f9061d18cd30bd3152fe05b95a113678a6070bf09d26015e6cab69aa041e0`；
round2 ZIP `12612261619` 为 1,828,201B，SHA-256 `09f5936fb56a2d5b8f34f9d65e4463855d4b5987631bed237f39bafcbf1f27c9`。
诊断先核对 API 的原 source/run/attempt/job、ZIP 大小/digest/有效期，再只在 Actions 解析每轮21个原文件。
只打印文件散列/大小、有限元数据、launch/错误类型及内存采样数，不输出书名、作者、正文或任意原日志。

源码候选根因：warm 复用 `warm-shared`；上一轮搜索 `LONG_TITLE`、开书/翻页/回书架后不清搜索。
宿主 `settings_save` 持久化 `Shelf.Query`，`settings_load` 恢复该过滤；旧 `op_first_screen` 却始终等待至少50行。
compact 模式也可能将书架隐藏，而旧谓词不检查书架可见性。原3600秒是等待期限，不能靠放宽它获得性能通过。

有界复现复用原 build ZIP `12606728463` 的 EXReaderProduct.exe、Reader.otf、公开 SDK seed，核对各自真实 SHA 后，
在 Actions 生成同样的500本合成书目。先用真实搜索框隔离过滤持久性：搜索、关闭、重开同一私有配置，
用原谓词的4秒诊断窗口保留真实失败，再从真实搜索框清过滤观察是否恢复50行。
随后在50行的同一配置打开长书，观察 compact 隐藏书架时旧首屏谓词是否仍会通过，再执行八次翻页、回书架、关闭。
整个窗口观察有55秒杀进程 watchdog、60秒总观察上限；这些是诊断边界，不是改动旧性能预算。
不重编原程序、不写旧 C02 样本、不自动修改任何旧/新 Claude 工作包。

诊断即使完成，仍为 `accepted=false`、`performance_accepted=false`。

诊断首次运行 `40230533020` 的云端语法和首个原 ZIP/21文件读取完成，额外历史 job-log CLI 请求失败，
所以有界复现被跳过。该失败保留。历史 job-log 改为可缺失的补充来源并记录失败状态/散列；
两份固定 ZIP 的元数据、大小、全 ZIP digest、成员解析与其中真实 `external/driver.log` 仍严格必需。

## 已封存云端证据

[诊断 run `40230793806/1`](https://github.com/NoGod3524/EXReader/actions/runs/40230793806)
两作业成功，受测诊断源码 `5dc9ad0612f80dc0a94e2879bb770538b6bfc978`。
原程序完全复用：7,820,800B，SHA-256
`a8fdc858b2e6b5ee7dcccd4f3a9e6f1fe9201906f992b70f3749ab99f9ccf7a0`。

| 工件 | ID | ZIP字节 | SHA-256 |
| --- | ---: | ---: | --- |
| 21文件×2原始证据检查 | 12612704993 | 3584 | `a3a4d4017e78c7136cfb892346bdaa4390bd4268dfcf091545d2791af64c8827` |
| 有界原生复现 | 12612763647 | 2182 | `a3151195575f15faf8ee7a7ee553991e2daaedc3780a57209e8ad636fe7de3b7` |

两份诊断工件有效期为 `2027-01-23T20:26:43Z`。原 ZIP 认证后各21文件全部读取：
每轮4次cold与warm-00成功，warm-01/02均为真实 `TimeoutError/no transition`。
500本两次失败的内存采样跨度为3,600,062.99/3,600,061.38ms；5000本为3,600,048.63/3,600,044.16ms。
两轮均缺少最终 `samples/launches/memory/plan/bundle.json`，原 profile 未上传，各宿主stdout日志为空；
不能用它们虚构原窗口快照。补充job-log请求不可用已明确记录，原 ZIP 内的实际 driver.log 已认证并保留失败。

有界观察总共 **6.219秒**，watchdog未触发，实际控制状态是：

1. 真实搜索后关闭，`host.ini` 的 `Shelf.Query` 持久为10字符的合成查询。
2. 同 profile 重开，原 `op_first_screen` 在4秒观察边界真实报 `TimeoutError/no transition`；
   等待后的稳定状态为1行、metadata已启用、旧偏移行标记为false、WM_NULL往返0.031ms。
3. 通过真实搜索框清过滤，回到50行，原谓词通过，WM_NULL往返0.028ms。
4. 进入compact阅读视图后书架不可见、阅读页可见，后台仍有100行，原首屏谓词仍直接通过。
5. 八次翻页并真实回书架/关闭后，`ActiveBook=1` 仍持久化。源码启动路径会自动打开该书；
   单纯回书架不会清掉继续阅读身份。

原复现报告的派生 `persistent_query_wait_condition_confirmed` 为false：诊断脚本错用了重开后尚在SDK旧列表阶段的
早期快照（50行但metadata未启用、含旧偏移标记），而没有用4秒等待后的稳定1行快照。
该原报告保持不变。当前脚本已改用等待后的稳定快照；封存后未再次启动原生观察，以上结论依据原始逐状态事实。

## 根因与最小修复边界

主要根因是**工具输入状态与等待谓词冲突**：共享warm profile带回上轮搜索过滤，合法的1行结果永远不满足≥50行；
不是UI线程冻结，也不能靠延长3600秒等待来解决。独立第二问题是旧通用helper没有验证compact的实际可见界面，
隐藏书架的行数可能被误授为“首屏已显示”。

后续只能在独立自有adapter审查修复：每轮计时结束后用真实UI回书架、清查询并记录复位成功，保留共享profile；
cold/warm入口必须确认真实书架可见、阅读页不在前台后才使用原行数/ready/roundtrip标准。
`ActiveBook`恢复与书架任务的入口需要显式记录，不能假装窗口创建就是书架显示。
resume保留独立真实恢复测量。原预算、样本计划、两轮及500/5000书目不变；
不写SQL、不重建warm profile，不自动修改旧C02或其他Claude工作区。

# C02 Windows 超时独立诊断

固定原 source：`169b0be3c1c8199be0211649412d23d9e34041e4`；原 run：`40214285241/1`。
只新增独立诊断脚本、工作流和本记录，不改原 C02 工作区、生产、旧预算、计划或裁判，也不控制原 run。
当前尚未运行本诊断；所有 ZIP 解析、语法与原生窗口观察仅在 Actions。

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

云端结果出来后补入真实状态、根因及最小修复提案。诊断即使完成，仍为 `accepted=false`、`performance_accepted=false`。

诊断首次运行 `40230533020` 的云端语法和首个原 ZIP/21文件读取完成，额外历史 job-log CLI 请求失败，
所以有界复现被跳过。该失败保留。历史 job-log 改为可缺失的补充来源并记录失败状态/散列；
两份固定 ZIP 的元数据、大小、全 ZIP digest、成员解析与其中真实 `external/driver.log` 仍严格必需。

# P acceptance results

验证代码提交：a2af0a57975de7f2f4dbdc343df6657f380432e2。其后提交仅保存证据。

| 项目 | run | 结果 |
|---|---|---|
| 初次四项正例 | [41711806430](https://github.com/NoGod3524/EXReader/actions/runs/41711806430) | success |
| Apple 产品安装（三平台） | [41711815286](https://github.com/NoGod3524/EXReader/actions/runs/41711815286) | success |
| 删除一次产品安装调用 | [41711848661](https://github.com/NoGod3524/EXReader/actions/runs/41711848661) | failure |
| 移除一次严格 shell | [41711853150](https://github.com/NoGod3524/EXReader/actions/runs/41711853150) | failure |
| 新增一次裸 test -n | [41711857541](https://github.com/NoGod3524/EXReader/actions/runs/41711857541) | failure |
| 漏掉一次预期失败退出码捕获 | [41711861779](https://github.com/NoGod3524/EXReader/actions/runs/41711861779) | failure |
| 新增违规 | [41711866195](https://github.com/NoGod3524/EXReader/actions/runs/41711866195) | failure |
| 修改基线行 | [41711870049](https://github.com/NoGod3524/EXReader/actions/runs/41711870049) | failure |
| 修复但保留基线条目 | [41711874772](https://github.com/NoGod3524/EXReader/actions/runs/41711874772) | failure |
| 最终四项正例 | [41712283042](https://github.com/NoGod3524/EXReader/actions/runs/41712283042) | success |

红色 failure 均为主动注入且与预期一致；每个负例仅运行对应规则 job，实际错误见同名 txt。负例修改临时副本或独立 Git fixture，不写入仓库。

最终四项规则 job 全部成功；Apple macos / iphoneos / iphonesimulator 三个安装 job 全部成功。原 desktop/sanitizers/fuzz/android/apple-mobile 作业全部 skipped。

Apple 与七个负例验证源码 db0d2c1f；最终正例验证 a2af0a57。两者除 ci-hygiene job 的调度 diff 基点与文档外完全一致，Apple 源码等价证明见 apple-source-equivalence.json。没有为纯证据提交追加运行。

精确历史基线：1786 条（failfast 1760 / negative 15 / diagnostic 7 / packaging 4），无目录级豁免；只允许删除。新增行采用 git diff --no-renames -U0；行移动、哈希改变、修复后残留、试图新增条目均拒绝。

受保护树改变 .github/workflows/native.yml；R 候选须在 P 与 F07 provider 落地之后重取。本 PR 保持 draft，不执行 C/R、不合并、不改 SDK/catalog/产品断言/F07/Settings/默认分支。

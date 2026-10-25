# Apple原完整记录套件：只读查询就绪准备候选

独立起点 `7c457fb68a24d917ac3bd60aa1f961b16fe9ae6b`，分支 `codex/reader-apple-records-ready`。原完整记录套件在同源码、同轮三目标通过。

生产、SDK、原ReadingUITests七case、native19、两SDK构建、原collector和strict逐字不变。新工作流投影原records工作流，只增加实际分支/新守卫、设备环境准备、准备证据入原工件及严格复核。原SDK3.41/ON的有效配置明确绑定新分支，不伪造GITHUB_REF。原90秒断言、180/300秒用例预算不改。

原设备选择和erase完成后，在原xcodebuild前显式boot/bootstatus，再复用7c457fb6已完成的原Simulator窗口/bootstatus及最多180秒只读appearance查询就绪。准备不写appearance，不添加业务点击，不改或替换原七个用例。macOS记录无需模拟器准备。真实准备命令、退出码、耗时、stdout/stderr进入原UI工件，原严格裁判完成后再独立核对准备身份。

本轮目的为在系统实际就绪后完整重跑记录套件，判断原间歇tap失败是否仍发生；不将准备视作已确认的生产点击修复。失败保留完整xcresult/原日志/截图，不拼旧单平台结果，不重复刷短两case。raw3 iOS72、真机及完整产品保持未授。所有执行与工件下载/解析只在Actions，本地仅源码、文档与Git。

## 同源完整结果

受测源码 `1c2ce4a1262b171a2f90ea4b92c998795c289435`，[run40214214442](https://github.com/NoGod3524/EXReader/actions/runs/40214214442) / attempt1，全部7作业 success：SDK iphonesimulator `121231740471`、SDK macOS `121231740797`、原native19 `121232238317`、原UI iPhone `121232550016` / macOS `121232550031` / iPad `121232550041`、原strict与新增准备复核 `121235837090`。

| 原完整套件 | 实际目标 | 用例 | 原附件 | 测试耗时 |
| --- | --- | ---: | ---: | ---: |
| macOS | macOS宿主 | 7/7 | 38 | 106.466s |
| iPhone | SE第三代 / iOS26.2 Simulator | 7/7 | 38 | 259.443s |
| iPad | mini A17 Pro / iOS26.2 Simulator | 7/7 | 38 | 334.445s |

两个移动目标均真实完成erase后的显式boot和bootstatus、Simulator窗口打开、第二次bootstatus，再只读查询appearance。iPhone首次45秒查询实际超时，第二次17.828s返回light；iPad首次3.307s返回light。就绪后才执行原xcodebuild及原全部用例，没有业务点击重试或预算变更。

原strict实际下载6个上游ZIP，核对同源码/轮次、大小、散列、有效期、程序及原具名证据；新增复核再次认证三个UI ZIP内的真实准备命令与查询结果。原strict和准备复核均输出 `accepted=true`。本轮完整21个UI用例未复现先前tap失败；这不能单独确认先前点击失败的根因。

| 工件 | ID | 字节 | SHA256 |
| --- | ---: | ---: | --- |
| SDK macOS | 12606274463 | 20526634 | `99626cecc756d18341c7dff5b085bb0cf876baa03f4f8b5e7852ef24bf11cfae` |
| SDK iOS Simulator | 12606538366 | 20534028 | `95ed8b7858ef339c33ec189bf1b2df130588eb5b554a9d46b4c71de411dd39ae` |
| 原native19 | 12607355104 | 1620640 | `f900ada6d820590f390c15b9009de3d7be84ca89c0e420c7ab67ac92586ede45` |
| 原UI macOS | 12606698549 | 38064975 | `ada1ab61fc5097e40c9f0cf2bcbce2e927816fcc88b2e8fca3171cf7600a68e4` |
| 原UI iPhone | 12606979282 | 40909101 | `fd1dedfb921c5f55a58f5f21e59598ca19010a021ff379f0685746411f45ab65` |
| 原UI iPad | 12606884645 | 60831051 | `54e9e03181d7587899cd2d358078bee05b9608989d2e71fcd84d160920565558` |
| 原strict及准备复核 | 12607049125 | 115325 | `183fceb836065510af6f4f481738b069ed975e9f0cf25f50a81cf548cb74cb67` |

有效期均为 `2027-01-23T16:58:29Z`。封存仅改本说明与验收JSON，受测源码保持1c2ce4a1；旧72候选失败保留，raw3 iOS仍未授。

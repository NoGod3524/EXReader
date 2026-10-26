# D16 交付：Apple 大字体驱动修复，三目标同源全套通过

## 身份、轮次与结论

- 固定 seed / 初始真实 HEAD：`d263ce5228838ac90c0a0dc13a5193d4a7739681`；任务书 `f8808893f8deafaaeed042ec58ad64a9acc56465`。seed 不是已验收生产 BASE。
- 分支：`codex/reader-wave3-d16`。**功能受测完整 SHA：`8104bcd872c49da2c683fb482b8c67e958aa4747`**；树 `9e0d29f88840c289585e44fa4c3f4ad991019dcb`；author/committer 均 Yinuo Xu。
- [run 40275499967 / attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40275499967)：**success**；只用 **1/3** 完整轮次，无 attempt 重跑。
- 最终文档 HEAD 是包含本文件的独立 `[skip ci]` 封存提交，完整 SHA 在最终交回和外部 `D16-status.md` 返回；它不是功能受测 source。封存后没有新功能运行。
- **限定结果：Mac 6/6、iPhone 10/10、iPad 10/10，共 26/26；真实 PNG 64 / 148 / 134。** 新 source 三目标完全重放，不拼接 D10 的旧目标结果。

| Job | ID | 结果 |
|---|---:|---|
| 原 D10 失败证据重新认证 | 121417266325 | success，原 iPhone 失败仍保留 |
| Mac 完整 replay | 121417392741 | success |
| iPhone 完整 replay | 121417392698 | success |
| iPad 完整 replay | 121417392713 | success |
| 同 run/attempt 原 ZIP 严格验证 | 121428125589 | success，47 项负例拒绝 |

## 修复内容与原失败→新结果

原 D10 文档 HEAD `7e4fcac25120199dd4818a86039e2257f28132a1`，受测 harness `d2e1b55c9cd4ded4201cbb4d1351bc490ef644df`，run `40229896420/1` 的 iPhone large-light/large-dark reader journey 都在 `DefaultUITests.swift:64` 离屏查询 `isHittable` 失败。字体减小控件 x=-119/-164，原生视口 x=0..375；原结果 Mac6/6、iPhone8/10、iPad10/10保持失败原貌。

本包仅新增 D16 驱动投影：把 12 次全幅 swipe 改为按新鲜 frame/原生滚动视口测量的低速短拖，位移封顶 0.55×实际视口宽度，停止后抬起；最终 hit-test 前增加完整几何可见性前置断言。全部原业务断言、点击语义、字体级别和等待预算保留。原 recorder、原 observation contract 与原 regression 字节一致；Actions guard 已证明完整投影，不改旧 D10 或 Apple owner。

本次 iPhone 两个大字场景都实际把字体减小控件由 x=-10.5 经一次 +147.75 点原生拖动移到 x=127.5（宽100.5，视口375），再通过原 enabled/hittable 断言并真实点击。随后查找、目录、标注打开/关闭、More、阅读记录、旋转和返回书架全完成；两条 reader journey 分别 123.292/113.919 秒通过。详见 `docs/reader-wave3-d16/iphone-driver-replay.txt`；完整 AX 树、截图、日志及 xcresult 在原 ZIP。

同 source 环境：iPhone SE（第3代）和 iPad mini（A17 Pro），iOS Simulator 26.2；medium / accessibility-extra-extra-extra-large × light/dark，实际大字 body=53pt、caption1=43pt。Mac执行 light/dark 和原 compact regression。原单 XCTest 420/900 秒、90分钟 job、12次滚动上限不变。

## 原工件身份：Actions 内下载原 ZIP 后逐字节验证

三目标 ZIP 由 verifier `121428125589` 在 Actions 内重新下载，核验实际 ZIP 长度/SHA与 API digest、有效期、唯一 artifact、manifest、程序/plist、同 source/run/attempt/job、完整命名 XCTest；没有本地下载或解析工件。

| 目标 / artifact ID | 原 ZIP bytes | SHA-256 | 有效期 UTC |
|---|---:|---|---|
| Mac / 12630541714 | 22437300 | `983b2490de7852cdf7b1ac1b101e71b5c82fa8e017150e00bac00b1fde7f5759` | 2026-11-25T05:53:02Z |
| iPhone / 12630208854 | 43783323 | `a519e16167e478b13b6760ce8d4d4a5ebeb1559aefa9a96087a24cb37b11b69e` | 2026-11-25T06:03:28Z |
| iPad / 12632035202 | 82079002 | `044b9be40216d29068c78c1852a8f3584b10961c7194310af35f397915fb8cee` | 2026-11-25T06:18:28Z |

实际 `EXReaderHost` 可执行文件 SHA-256：
- Mac：`688a6eb8ecd811daf3cb72029b5861458f710230b605f5598fde5656d6553461`；Info.plist SHA `8315c9844e9a30f4452055825d0f5dc93c9b99a34717ca90584d8846c206640b`。
- iPhone / iPad：`9b3dbb19748c608b6f1a021a03a0b928b2147711df9c4a78dc52863907417443`；Info.plist SHA `143961eb2400f2e995e7247c141c242b056ab2b05ffe7141bad0a6c284cb6957`。
- 三份真实程序的 EXRSourceSHA 都是受测 `8104bcd8…`；SDK3.41.0，page-theme OFF，无实际 project/compiler review 宏。SDK `edddc463c06ed5731195cdb8f06b2df6dff7699e` 的 src/include/cmake/CMakeLists/bindings 树冻结不变。
- 每个测试分组都由原生 `ps` 捕获真实正在运行的 PID、可执行文件路径与 SHA，再与 app 实物匹配。例：Mac large流程不适用，light reader PID28503、dark reader31134；iPhone large reader47930/64229；iPad large reader38499/54400。全部记录见 `runtime-targets.json` 与 `validation-summary.json`。

附属 summary ZIP 仅 API 元数据，**未下游重哈希，不冒充原目标 ZIP 认证**：
- validation 12631741005：16205 bytes，digest `e8a2e5aed05a259d41b00775ff008faabc63439dfb1ab20c46e2cb4614300b6e`，2026-11-25T06:19:09Z 到期。
- prior-review 12630395319：12808 bytes，digest `9fad6b9d4a7eaeb6033b6cc0c0f5e2b3930283af55af12ade02f082d98168fad`，2026-11-25T05:41:00Z 到期。

## 保留失败和验收边界

D04、D10 round1编译失败、round2 iPhone readiness失败及最终两处驱动失败均未重写为成功；旧报告原文保存在 `retained-d10-*` 和 `upstream/HANDOFF-RESULT-D10.md`。本轮 prior job 重新认证 D10 三份原 ZIP/程序，并明确旧 iPhone `audit_completed=false`；它不计入本轮26条。

本包消除了所委托的两处驱动缺口；本轮限定26条无失败、三平台 problems=[]。未发现需要越界修 D15 的产品缺陷。**不授予完整产品/AX/VoiceOver/Dynamic Type整体验收**：保守几何/命名观察继续原样保留；原 Menu wrapper `isHittable=false` 不因原生可见触发成功而变真；物理设备、VoiceOver读音/转子、完整焦点顺序/恢复、移动硬件键盘、macOS系统大字体、文字裁剪目视结论、真实搜索查询导航、系统picker导入及完整主题设置仍非本包验证范围。安装库 hash 是 producer 报告，不等于完整签名 bundle/ZIP link模式认证。

## 执行与接入

仅 Dot 原生工具；未启动 Codex/cloud_threads/cpuse/子代理。所有构建、语法、fixtures、XCTest、截图、下载/解析工件仅 Actions。普通 HTTPS git push 因无 Username 凭据未执行成功，随后用已授权 Git Data API 发布同树，核验 Yinuo Xu 作者与远端身份。最初本地候选 `8d58510e7ec8e27ba2cc03d82cbfa4b941d38217` 与实际 API提交树完全一致；以真正受测 SHA 为准。未 reset 工作树，未改主线/PR/tag/Release/SDK或其他包。

仅新增 `tests/reader_wave3_d16/`、`.github/workflows/reader-wave3-d16.yml`、`docs/reader-wave3-d16/` 和此 handoff。测试后只封存文档，无源码更改。接入命令（由协调者审查后执行；不意味着本包已合并）：

```sh
git fetch origin refs/heads/codex/reader-wave3-d16
git cherry-pick 8104bcd872c49da2c683fb482b8c67e958aa4747 FETCH_HEAD
```

`FETCH_HEAD` 应为交回的 docs-only seal；功能 source 和 seal 不混同。无需为本包再造测试工程或消耗第二轮。

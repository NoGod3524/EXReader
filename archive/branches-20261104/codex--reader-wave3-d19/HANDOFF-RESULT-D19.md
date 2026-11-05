# D19 GTK 长驻生命周期：完整双阶段通过

## 交付身份与状态

- 分支：`codex/reader-wave3-d19`；作者：Yinuo Xu。
- 固定 seed：`d263ce5228838ac90c0a0dc13a5193d4a7739681`（开发起点，**不是**已验收生产 BASE）。
- **实际受测完整 SHA：`97bec4a338719923b71ef88fb42f5ba3c4d20da8`**。
- SDK 冻结：`edddc463c06ed5731195cdb8f06b2df6dff7699e`，安装版本 `3.41.0`。
- [Actions run 40273253922](https://github.com/NoGod3524/EXReader/actions/runs/40273253922)，attempt **1**，2026-10-26 05:33:35 UTC 终态 `success`。
- 实际 job：`lifecycle (gtk)` / `121410472425` 与 `authenticate` / `121415308053` 均 `success`；全部本包检查步实际执行。
- 完整云端轮次 **1/3**；没有重跑 attempt，没有拼接其他 source/run 的测试结果。
- 本文及 `final-evidence.json` 是受测源码之后的独立 **[skip ci] 文档提交**；完整文档 HEAD 在最终交付消息列出。文档没有冒充已受测源码。

## 实际通过范围

| 项目 | 实际结果 |
|---|---|
| GTK 原四格式周期 | TXT / EPUB / PDF / CBZ，每阶段三轮；两阶段各 12，共 **24** 完成周期 |
| 原动作裁判 | **244** 完成动作；240 周期动作 + in-flight close、重开无重放、final close、原件不变 |
| 驻留 | 24 次均完成 **至少 30 秒** live reading dwell；至少 720 秒，不计构建/等待时间 |
| 实测总生命周期 | **862.659090104 秒**，低于原 2700 秒上限 |
| 独立宿主 | stage 1 PID **10229**，stage 2 PID **11187**，两者实际 executable hash 相同，各 exit **0** |
| 相位握手 | 控制器 PID **10207**；phase **2** / running **1** / polls **1** / host busy **1** 时，发出真实父窗口 `WM_DELETE` |
| 实际工作线程 | stage 1 `reading` TID **10238**；stage 2 `reading` TID **11195**；原资源采样持续运行 |
| 资源收据 | **1704** 组真实 PID/create time、RSS、CPU、线程、fd、子进程观测 |
| 重开 | 旧 PID 已结束，新 PID 活着；search visible/running/count/actions/polls 均 0，无查询重放；第二阶段全部完成 |
| SDK / catalog | 关机后、重开前及最终关机后，public SDK 读出 **6** 份真实导入原件；ID/格式/大小/SHA 与同一安装 catalog provider 映射一致 |
| 写入限制 | 只有原件导入和隐式阅读进度；pending 文件为空，三类 SDK notes 表均 0；全部夹具最终 SHA 不变 |
| 拒绝控制 | 原 D14 七类负控、本包边界六类拒绝、新增 missing-second-host / no-live-phase / missing-worker / catalog-source-mismatch 四类负控均通过 |

相位时间线（相对驱动启动）：`434.563898500s` 确认真实扫描活跃；`434.570091798s` 记录 native close 已发送（input PID 11184、close PID 11185）；`434.640441162s` 宿主 clean exit；`435.535651983s` 新宿主无重放。没有在待测 live interval 前 cleanup/kill。

## 原工件和程序身份

[GTK 原始 ZIP](https://github.com/NoGod3524/EXReader/actions/runs/40273253922/artifacts/12629258856)

- 名称 `d19-gtk-40273253922-1`；ID **12629258856**。
- 原 ZIP **23,837,002 bytes**。
- SHA-256 `3087812893576b00b1d5e78cc6913bc84bc3e1069e0db51d3fa1dc4524dc8eca`。
- 有效期 **2026-11-25 05:33:15 UTC**。
- 同 run/attempt 的 authentication job 在 Actions 下载原 ZIP，复算大小/SHA、比对 GitHub digest/expiry，验证每个成员、实际程序、字体、SDK header 和完整原裁判；不是只信上传名或 job 绿灯。

[验真报告 ZIP](https://github.com/NoGod3524/EXReader/actions/runs/40273253922/artifacts/12629757765)

- 名称 `d19-authentication-40273253922-1`；ID **12629757765**。
- 服务/上传日志记录 **57,470 bytes**；SHA-256 `11ed219900350b108c093d36d9362d5c8ffe8b3838fe1b496dbc5d96ef02649b`。
- 有效期 **2026-11-25 05:33:32 UTC**。该 ZIP 的自身身份来自 GitHub 元数据与实际 upload 日志；不冒称它自行下载验证了自己。

程序 SHA-256：

- `exreader-linux`：`0821447fcaf8a1a311e92dc867c6a8192160149cd00d39caf7abb766a1f3e4e7`。
- `d19-catalog`：`c7e66157af0c1a9ad1f0169623e24cd5820887b035f67e43099b19be23e800aa`。
- 安装 `sdk-base.h`：`461f33b1f17c4650229935630179d369b715b5a9a24d2181f3f653864bed47a0`。

## 驱动修复、保留失败及限制

原 D14 `93c2f583c7e54eb2aebcba13a18b532bd0a967f5` / [run 40226870656](https://github.com/NoGod3524/EXReader/actions/runs/40226870656) 失败保留：GTK 12 周期后错过 TXT phase 2，仅看见 phase 3 / polls 1；旧 cleanup 超时 kill，stage 2 从未运行。原 Windows 24 周期/244 检查不变，也不计入 D19 本次 GTK 验收。

本包不改 GTK 产品 owner、SDK、旧测试、旧 guard 或预算。原 D14 `run.py`、`contract.py`、builder、普通 GTK 周期方法按固定提交逐字读取执行；仅明确将 GTK 目标身份映射为真实本次源码，验真入口只替换本包工件命名。所有原文件字节保留在 ZIP 的 `judge/d14/`。

**预先声明的工作负载增补**：原 `Processing.txt` 3,120,000 bytes 原样生成、真实导入、SDK 读回；SHA `18a90b761f3d0694cc1054eadff07e3662c1946cabbd30cc22b5078a6f0efd5b`。其瞬时 reflow phase2 不冒充可观测长扫描。另复用现有 GTK search 原夹具生成器的 bounded `cancel.epub`（5,911,219 bytes；SHA `297da75a319aa6c5c467b7517ba8bb56aa077cb79705a27f49e730dbfbad276b`）承载本次真实 in-flight close。此次通过证明 bounded EPUB live-scan close/reopen，不追认旧 TXT 瞬时扫描用例通过，也不授予旧 9 MB TXT 导入能力。

D19 新轮次没有失败。限定结论是云端 GTK 的 24 周期/至少 12 分钟 dwell 和明确关闭重开路径；不是多日稳定、泄漏自由、性能预算、物理设备、读屏、Windows 复测或完整产品验收。没有新增产品能力、PR、默认分支改动、tag 或 Release。证据 ZIP 到期后不得继续引用为可下载证据，需保留正式归档。

## 接入命令（由集成者执行）

本包尚未接入任何主线；先确保集成分支含固定 seed，且独占路径无冲突：

```bash
git fetch origin codex/reader-wave3-d19
git cherry-pick 97bec4a338719923b71ef88fb42f5ba3c4d20da8
# 文档封存提交是远端分支最后一个 [skip ci] 提交：
git cherry-pick origin/codex/reader-wave3-d19
```

最终交付消息提供封存提交完整 SHA，可用它替换最后一行。组合接入改变源码后，本次结果仅作为该受测 SHA 的独立包证据，不能自动授予组合候选验收。

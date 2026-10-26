# D19 GTK 双阶段生命周期（待云端验证）

固定 seed `d263ce5228838ac90c0a0dc13a5193d4a7739681`；SDK `edddc463c06ed5731195cdb8f06b2df6dff7699e`。seed 不是已验收生产 BASE。

本包仅新建 D19 独占文件。原 D14 `93c2f583c7e54eb2aebcba13a18b532bd0a967f5` 的 contract、run、build 和 GTK 普通周期方法逐字复用；原裁判不改，明确将 GTK 目标身份从旧候选绑定为本次真实 `GITHUB_SHA`，不伪造环境变量、报告或旧验收。原 Windows 24 周期/244 检查不动，不计入本次结果。

## 已知失败与预先声明的驱动修复

原 run `40226870656` attempt 1：GTK 12 周期后，3 MB Processing.txt 的 reflow 搜索很快完成（phase 3、polls 1），旧驱动没捕获 phase 2；cleanup 在模态窗下超时并 kill，stage 2 未执行。旧失败保留，不能视为通过。

保留原四格式、两个独立进程、每阶段三轮、共 24 周期、每周期 30 秒 dwell、244 动作、45 分钟总测试上限、原 resource/owner 进程和取消/重开断言。原 Processing.txt 仍原样生成、真实导入并纳入 public SDK/catalog 原件身份校验。**新增**现有 `reader_search/make_search_fixtures.py` 与 `reader_gtk_search/make_inputs.py` 的 bounded `cancel.epub`，以其真实 SDK 分章扫描承载 in-flight close；不扩大原 TXT 能力结论，不将 phase 3 当 phase 2，不降低预算。相位监听在 native input 前武装；观察 phase 2、polls>0、running=1，并在发出父窗口 WM_DELETE 前再次确认。任何错过相位/提前退出都失败。

记录驱动 PID、真实 host PID/create time、Linux 线程 ID/名称（reading owner）、相位和实际 native input/close 子进程 PID 时间线。未到所测 live interval 不 cleanup。关闭退出必须为 0，然后 public SDK 原始 source hash 与同一安装 catalog provider 映射校验；新 PID 重开无 query replay 后必须走完第二阶段。最终再次退出、SDK/catalog readback，并比对六份真实导入原件身份。

所有构建、语法、夹具、测试、截图、原 ZIP 下载/解析仅 Actions。本地仅源文件/文档/Git。最多三次完整轮次（attempt 重跑亦计）；原始 ZIP 每成员、真实程序 SHA、大小、服务 digest、有效期、run/attempt 同源检查使用原 D14 裁判。D19 再加阶段/worker/phase/catalog 负控。资源仅观测，不授予性能、泄漏自由、物理设备、读屏或完整产品验收。

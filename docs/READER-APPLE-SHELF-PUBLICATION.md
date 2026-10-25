# Apple 初始化接纳与书架提交发布

独立后继分支基于 `f4aa876c`，不改其冻结分支、原六个测试消费者/断言或 parser 规则。

## 初始化门禁

保留失败录像的真实末帧为“书架为空”“就绪”，没有“已导入”；它不支持把三次首次点击失败直接归因为已提交后的刷新。旧模型的 `busy` 初值为 false，`start/onAppear` 才改为 true，初次 UI 可能在 owner 初始化前呈现可用状态。新增独立 `libraryReady`：初值 false，只有实际 SDK session、catalog 和初始读取成功后才在 main 发布 true；界面启用与 `importFile` 接纳均依赖它。`start()` 仍只按 `started` 防重入，未增加依赖初始 busy 的自拒绝条件。

确定性初始化场景在 review-only 模式下停在真实 `start()` 入口之前，保留 `busy=false` 来证明门禁独立于 busy。断言普通导入按钮禁用；从独立 review 入口直接调用原 `importFile`，必须在 `begin` 前拒绝（token 仍 0、SDK UI 书数仍 0）；释放后执行真实初始化，再用原普通导入按钮导入并打开真实 SDK 页。它没有用 sleep 或放宽原首次导入断言。

## 提交事件刷新

正常书架来自独立 `HostShelf.rows`。导入完成已经发布 `model.books`，旧界面却仅靠 `busy` 变为 false 时刷新；一次 SwiftUI 帧内的 `false → true → false` 会被合并，实际已提交的书籍可能留在旧空书架之外。修复直接接收现有 `model.$books` 发布事件，原忙状态观察保留。

确定性 UI 回归通过 review-only 按钮在同一个主线程动作内完成真实串行 owner 的 `HostSession.importBook` 和共享生产 mutation 发布。中间不交还主线程；记录界面实际观察到的 busy 变化数必须为 0，而 SDK 书数、书架缓存数均必须为 1，并能打开实际 SDK 页面。原生产异步导入仍走同一个 mutation 发布函数；没有增加等待来掩盖缺失通知。

该独立消费者显式复用 `6d53f3c0` / `40173677171` attempt 1 的冻结 SDK3.41 安装工件，原 producer 身份、ZIP 字节/散列、全部安装文件散列及 Mach-O 身份保留，不重标为当前 host 源码。SDK及所有安装模块的生产树与该 producer 精确相同；最终共同源的原六组回归仍需另行授予。

## 真实云端结果

受测 host 源码 `e6c0ef2d2a3d9289dc415d16cb46d0eafa7f340d`，run [40181355084](https://github.com/NoGod3524/EXReader/actions/runs/40181355084) attempt 1，consumer `121132916448` success。iPad mini (A17 Pro) / iOS 26.2 simulator 两个实际 XCTest 场景均 Passed。

- 初始化接纳：停止在真实 `start` 之前时 `busy=false / libraryReady=false / started=false / token=0`；普通导入控件禁用，直接调用原后端入口后 `rejected_unready=1`，token 与 UI 书数仍为 0。释放后 `libraryReady=true`，通过原普通导入按钮导入并打开真实 SDK 页。
- 同帧提交发布：真实 owner 导入后 `observed_busy_changes=0`，SDK 书数 1；HostShelf 缓存 `0→1`，generation `3→4` 且 applied=4，页面真实文字含 `C00P000W00`。
- 当前消费程序为唯一动态 SDK 链接，provider accepted=true、static_sdk_linked=false；实际程序 SHA-256 `4ba7ce459e15b5c9c00a94b2050b12d8977375d62676ce1776d959fabe555aaa`。

工件 `12594511272`，50,989,276 字节，ZIP `sha256:66304f0c02b5a7b0beded56eb3684a3dfccec4046d05ed19143d7cc7e5264cd6`，有效期至 `2027-01-23T09:36:38Z`。原报告、实际应用、两场景的六张截图和 xcresult 都由该运行保留。

授予分别限于 iPad simulator 的初始化接纳场景与同主线程回合导入发布场景。没有把该独立消费者记为原六组回归或六平台互通；原 `f4aa` 首次点击失败记录和后续诊断继续保留。构建、语法检查、夹具生成、工件恢复和实际 UI 全在 Actions。

# Apple 原生 WebDAV 传输

本包在 `extras/webdav` 的既有公开 C ABI 后接入 Foundation `NSURLSession`。
iOS 默认使用此实现；macOS 默认继续使用原系统 libcurl，显式
`EXR_WEBDAV_APPLE_URLSESSION=ON` 才选择 Foundation。Windows/Linux/Android 的实现保持各自分支。

## 所有权与传输

- 客户端固定在创建它的 owner 工作线程；跨线程操作、回调重入返回 `ARGUMENT`，
  这两种情况下的 `free` 不释放活动客户端。iOS 网络调用拒绝主线程。
- Foundation delegate 只持有内部状态。公开取消、进度和文件读取回调全部由 caller worker 调用，
  delegate 不借用 SDK、调用者控制结构或输出指针。
- 接收桥使用一个 64 KiB 槽；上传使用系统 `CFStreamCreateBoundPair` 的 64 KiB 管道及
  owner 的 64 KiB 缓冲，保留源文件的既有稳定性检查。系统网络栈自身的分配另计。
- 整次请求使用 steady-clock deadline；取消后关闭管道、停止内部状态并取消 session。
  系统取消完成可晚于函数返回，但后续 delegate 不能访问调用者上下文。
- 沿用共享路径、源边界、重定向、下载/列表/XML 限额和文件原子发布规则；
  HTTP 响应头另保留 32 KiB 上限。不可变 PUT 不跟随重定向，使用 `If-None-Match: *`。
- ephemeral session 禁用 cookie、凭据存储和缓存；证书与主机名由系统验证。
  没有自定义信任通过、生产测试 CA 或 WebView。

## 云端出口

分支 push 仅运行 iOS 聚焦检查。最终使用 `reader-webdav-apple.yml` 的
`workflow_dispatch full=true`，在同一源码、同次运行完成：

1. Windows/Linux/macOS 原七套原生同步检查与 12 项兼容检查；macOS 额外 11 项
   原生上传、不可变重试、取消、deadline、owner、回调及响应头限制检查。
2. arm64 iOS Simulator 的实际 UIKit app worker 执行原 77 项、兼容 12 项与上述 11 项。
   安装后 C++ 消费者直接链接安装包；runner 适配器只负责启动 app 和复制私有目录结果。
3. 严格汇总重新下载四份 ZIP，核对来源、run/attempt、大小、digest、命名检查、实际 Mach-O
   与依赖。缺项或任一 producer 失败即拒绝。

测试 CA 只通过 Actions 临时 runner / Simulator 的系统信任库安装。
构建、测试、夹具和 ZIP 检查均只在 Actions 运行。

## 当前状态

尚未获得本包最终联合验收。早期 `e2049f5c` / run `40069002968` 因 CFStream 回调
类型不匹配编译失败；修正后的 `f0453f70` / run `40069232620` 三平台七套原生检查均成功，
该次没有 iOS 或最终严格汇总。`e39f5f3e` / run `40069514068` 的 iOS 安装后消费者
因交叉编译包搜索路径失败，后继已改用明确的安装包目录。所有失败保留。

本包只验证网络传输；完整 iOS `reader_session`、SDK 原件导出/导入调度、账号 UI、
真机和六目标互通继续独立验收。

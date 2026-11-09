# Apple 运行时复验

本轮结论：macOS、iOS **只能静态校验**。执行主机是 Windows，没有 Xcode、Apple SDK 或 Simulator；已重新读取实际 Mach-O 文件的 SHA-256、导出表和 `LC_BUILD_VERSION`。macOS / iOS device / iOS simulator 三种平台标识各自匹配，不能互换。

## 已经可以下载的 artifact

无需修改 workflow：[native.yml](../../.github/workflows/native.yml) 已对 macOS `stage/` 和 iOS 的 `stage/iphoneos`、`stage/iphonesimulator` 使用 `actions/upload-artifact@v4`。

已核对 [run 42474080320](https://github.com/NoGod3524/EXReader/actions/runs/42474080320) 的 API 返回 `expired=false`，过期时间为 2027-02-06。这批库来自 **bd15cddb4d0928abde07c90e34b52f567a169d2d**，不是本轮 Windows/Linux/Android 源码基线 ed252fb6。

| 平台 | artifact 名称 | artifact ID | 包含内容 |
|---|---|---|---|
| macOS | `EXReader-C-macOS` | 13615043046 | arm64 SDK、`lib/libexreader.dylib` 及版本别名 |
| iOS | `EXReader-C-iOS-iPadOS-arm64` | 13615073113 | arm64 device 与 arm64 simulator 两套 SDK |

`gh run download` 会通过当前 GitHub 登录获取 ZIP。完整解压，保留 `libexreader.1.dylib`；不要只复制无版本别名。各库完整 SHA-256 与导出数见 [artifacts.json](../../evidence/platforms2-20261109/artifacts.json)。

## macOS：三条命令

在本 PR 的源码根目录执行；前提为 Apple Silicon Mac、Xcode Command Line Tools、Python 3、GitHub CLI 已登录。使用新的输出目录，脚本遇到旧证据会拒绝覆盖。

```sh
gh run download 42474080320 -R NoGod3524/EXReader -n EXReader-C-macOS -D evidence/platforms2-20261109/work/apple-macos
python3 -B tools/platforms/run_native.py --library evidence/platforms2-20261109/work/apple-macos/lib/libexreader.dylib --out evidence/platforms2-20261109/macos-runtime
cat evidence/platforms2-20261109/macos-runtime/reopen.log evidence/platforms2-20261109/macos-runtime/result.json
```

第二条会生成固定 EPUB/字体、显式 `dlopen`、编译动态链接 consumer、启动 create/reopen 两个独立进程，并要求五项全部通过。还会故意把落盘页码改错，要求负向测试失败。第三条应看到 `PASS platform checks=5/5`、`passed: 5` 和被拒绝的负向测试退出码。

## iOS Simulator：三条命令

前提为 Apple Silicon Mac、完整 Xcode、至少一个已安装的 iOS Simulator runtime、Python 3 和已登录的 GitHub CLI。脚本创建专用 iPhone Simulator，不占用已有设备。

```sh
gh run download 42474080320 -R NoGod3524/EXReader -n EXReader-C-iOS-iPadOS-arm64 -D evidence/platforms2-20261109/work/apple-ios
python3 -B tools/platforms/run_ios.py --sdk evidence/platforms2-20261109/work/apple-ios/iphonesimulator --out evidence/platforms2-20261109/ios-runtime
cat evidence/platforms2-20261109/ios-runtime/reopen.log evidence/platforms2-20261109/ios-runtime/result.json
```

第二条将实际 simulator dylib 嵌入最小 UIKit app，构建、签名、安装、运行、终止进程，再启动 reopen。脚本核对两个 PID 不同、五项日志全部存在，复制 Documents 证据并关闭专用模拟器。超时或失败返回非零并保留模拟器供检查。**本轮未在 Mac 上执行此脚本**，不能把这份操作步骤计为已跑通。

iOS device dylib 的静态核对不等于装机通过。真机还需要配对设备、开发者模式与开发签名；上述三条命令完成的是用户允许的 Simulator 等价验证。Intel Mac 必须另构建 x86_64 的 macOS/simulator 库，现有 arm64 artifact 不能直接使用。

## 刷新成新的 main 产物

现有 workflow 可直接手动触发，无须 patch：

```sh
gh workflow run native.yml -R NoGod3524/EXReader --ref main -f scope=full
gh run list -R NoGod3524/EXReader -w native.yml --event workflow_dispatch --limit 5 --json databaseId,headSha,status,conclusion
gh run download <已完成且headSha正确的run-id> -R NoGod3524/EXReader -n EXReader-C-macOS -n EXReader-C-iOS-iPadOS-arm64 -D evidence/platforms2-20261109/work/apple-current
```

更新下载 run ID 和源码 SHA 后，再用上面的两套三条命令验证。`scope=p-apple` 只检查包装，不会产生这里需要的两个上传 artifact；必须使用 `scope=full`。

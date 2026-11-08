# iOS / iPadOS 验收

当前：arm64 device 与 arm64 simulator 的聚合 **dylib** 和组件 **.a** 已由 native CI 归档。目标 `libexreader.a` **待 CI 聚合**；两种动态库均为 389 个契约入口 + 2,410 个额外符号。Windows 不能执行 Apple libtool、签名或 Simulator；本清单的构建/装机步骤尚未执行，不把现有 dylib 算作目标静态库。

## 在 macOS CI 生成目标静态库

先解压 `EXReader-C-iOS-iPadOS-arm64`，保留 `iphoneos`、`iphonesimulator` 两套 SDK。不能把二者合为同一 arm64 fat 库，因为 CPU 相同、平台不同；需要统一交付时应另组 XCFramework。

```sh
set -e
export IOS_STAGE="$PWD/downloads/EXReader-C-iOS-iPadOS-arm64"
python3 tools/abi/merge_ios.py --sdk "$IOS_STAGE/iphoneos" \
  --output delivery/ios/arm64-device/libexreader.a
python3 tools/abi/merge_ios.py --sdk "$IOS_STAGE/iphonesimulator" \
  --output delivery/ios/arm64-simulator/libexreader.a
python3 tools/abi/check_exports.py delivery/ios/arm64-device/libexreader.a --allow-extra
python3 tools/abi/check_exports.py delivery/ios/arm64-simulator/libexreader.a --allow-extra
shasum -a 256 delivery/ios/*/libexreader.a
```

合并使用 Apple `xcrun libtool -static`，只选引擎十二个组件及其已安装 vendor 归档，排除 reader 产品模块；保留原 SDK 的 CMake 系统依赖信息。静态库没有动态“导出表”，这里的符号数是归档中外部已定义符号集合。`--allow-extra` 只能证明公共入口齐全，实际链接与启动仍是下面的门槛。

## arm64 Simulator 上安装与运行

```sh
set -e
python3 tools/abi/prepare_smoke.py build/smoke
export SDK="$IOS_STAGE/iphonesimulator"
cmake -S tools/abi -B build/probe-ios-sim -G Xcode \
  -DCMAKE_SYSTEM_NAME=iOS -DCMAKE_OSX_SYSROOT=iphonesimulator \
  -DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_OSX_DEPLOYMENT_TARGET=14.0 \
  -DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO -DEXR_SDK="$SDK" \
  -DEXR_SMOKE_INPUT="$PWD/build/smoke" \
  -DEXR_ACCEPTANCE_ARCHIVE="$PWD/delivery/ios/arm64-simulator/libexreader.a"
cmake --build build/probe-ios-sim --config Release --parallel 4
export APP="$PWD/build/probe-ios-sim/Release-iphonesimulator/exreader-acceptance.app"
codesign --force --sign - "$APP"
xcrun simctl list devices available
# 选择一台尚未安装本探针的 arm64 iPhone 或 iPad Simulator。
export SIM_UDID='<从上一命令选择的 UDID>'
xcrun simctl boot "$SIM_UDID"  # 已 booted 时略过这一条
xcrun simctl bootstatus "$SIM_UDID" -b
xcrun simctl install "$SIM_UDID" "$APP"
xcrun simctl launch "$SIM_UDID" org.exreader.acceptance
export CONTAINER="$(xcrun simctl get_app_container "$SIM_UDID" org.exreader.acceptance data)"
# 等界面显示 PASS/FAIL 后读取；不能在文件写到一半时判断成功。
cat "$CONTAINER/Documents/acceptance.log"
mkdir -p build/ios-acceptance
cp -R "$CONTAINER/Documents/." build/ios-acceptance/
xcrun simctl io "$SIM_UDID" screenshot build/ios-acceptance/simulator.png
```

UI 会显示最终 `PASS acceptance checks=5` 或失败位置。`acceptance.log` 与所有图像位于 Documents；在全新 iPad Simulator 上再执行一次。Intel Mac 需要另建 x86_64 simulator SDK，本轮只给 arm64 simulator。

## 真机安装路径（待设备与签名）

静态库本身不能安装。用同一个 CMake consumer，改为 `-DCMAKE_OSX_SYSROOT=iphoneos`、device SDK 和 device archive，改用新输出目录 `build/probe-ios-device`。移除 `CODE_SIGNING_ALLOWED=NO`，设置 `-DCMAKE_XCODE_ATTRIBUTE_DEVELOPMENT_TEAM=$TEAM_ID -DCMAKE_XCODE_ATTRIBUTE_CODE_SIGN_STYLE=Automatic`；由 `cmake --build build/probe-ios-device --config Release -- -allowProvisioningUpdates` 完成开发签名。连接已配对设备并启用开发者模式后：

```sh
xcrun devicectl list devices
export DEVICE_UDID='<已配对设备 identifier>'
export APP="$PWD/build/probe-ios-device/Release-iphoneos/exreader-acceptance.app"
codesign --verify --deep --strict "$APP"
xcrun devicectl device install app --device "$DEVICE_UDID" "$APP"
xcrun devicectl device process launch --device "$DEVICE_UDID" org.exreader.acceptance
```

在 Xcode Devices and Simulators 下载该应用 container，读取 `AppData/Documents/acceptance.log` 和图像。签名、授权和 device run 均须有真实记录才能通过；native CI 的 unsigned IPA 不能直接当作已签名真机包。

## 五项最小功能验收

以下五项均由同一次 `exreader-acceptance` 执行；任何条件不满足返回非零。PNG 是实际引擎渲染产物，不是界面示意图。各端使用相同 EPUB 和固定字体；探针验证 SDK 功能，原生阅读器的触控、菜单、无障碍和平台持久化仍需另做装机验收。

1. [ ] **打开一本书**：`acceptance.log` 必须出现 `PASS open status=0 pages=`，页数至少 20；打开 `page-01.png` 可见英文正文。这里使用生成的一章 EPUB，避免封面/版权页不足 20 页影响验证；19 本真书属于独立回归。
2. [ ] **连续翻 20 页**：必须出现 `PASS turn status=0 rendered=20 last=page-20.png`；`page-01.png` 至 `page-20.png` 共 20 个文件，均可打开。它验证连续页渲染和读取；触控翻页与应用帧率不在此探针范围内。
3. [ ] **搜索一个词**：查询 `deliveryneedle`，必须出现 `PASS search status=0 found=1 part=0 offset=0 length=14`；这是 `exr_publication_search` 的实际返回值，不是用字符串查找模拟。
4. [ ] **修改字号**：必须出现 `PASS fontsize status=0 from=18 to=24 pages_before=... pages_after=...`，after 大于 before；`font-24.png` 字号大于 `page-01.png`，首页结束偏移减少。探针会同时断言这些值。
5. [ ] **添加一个高亮**：必须出现 `PASS highlight status=0 stored=1 resolved=FOUND changed_pixels=` 且值大于 0；`highlight.json` 为导出的 W3C 标注，探针写入、关闭、重新读入并解析；锚点恢复到相同 UTF-8 范围。`highlight.png` 的第一个 `deliveryneedle` 有黄色背景。绘制由参考宿主按引擎字形坐标完成，不能据此宣称产品菜单已验收。

最后必须出现 `PASS acceptance checks=5`。保留完整日志、22 张 PNG（20 页 + 字号 + 高亮）、标注 JSON、设备/模拟器型号、OS 版本、实际库 SHA-256 和命令；失败时保留输出，不能把本页勾选项当成已通过记录。

## 已知限制

- `.a` 聚合和本轮新增 UIKit 探针尚未在 Apple CI 执行；产物状态保持“仅 CI 可产”，不是已验证可安装。
- 原有 native CI 的 iPhone/iPad 参考宿主模拟器检查全绿，结果属于原有宿主；不替代本轮五项或新静态库的验收。
- Simulator 通过不代表真机通过。设备/模拟器 ABI、平台标记和签名分别验收。

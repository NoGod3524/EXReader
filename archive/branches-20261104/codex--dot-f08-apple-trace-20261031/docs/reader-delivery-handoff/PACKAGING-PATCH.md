# 包级补丁声明（唯一一处，最小）

本包只改了下面这一个非本包路径的文件，用于把已发现缺失的许可文本补进 Android 压缩包。`check.py guard` 与
`android_admission.py guard` 只接受本清单里声明的路径：

- `tests/android_sdk342_package/run.py`

## 原因

Actions 对已发布压缩包的只读检查（run 40948655722 / 40949203489，见 [EVIDENCE.md](EVIDENCE.md)）显示：Windows、Linux、macOS、iPhone、iPad
压缩包的 `licenses/` 与按各自 CMakeCache 推导的期望集合一致，而 **Android 压缩包没有 `licenses/`，15 个应随包的许可文件缺失**
（只有包根的 `LICENSE` 与 `THIRD_PARTY_NOTICES.md`）。

## 改动（只增加，在复制 `LICENSE`、`THIRD_PARTY_NOTICES.md` 之后）

1. 把 SDK 安装树 `build/wave3/sdk-stage/share/exreader/licenses` 整目录复制为压缩包载荷的 `licenses/`（与桌面/Apple 脚本相同）。
2. 把产品前缀 `build/wave3/stage/share` 下文件名含 `licen`、`copying`、`notice`、`public-domain` 的文件，按相对路径复制到
   `product-licenses/`（其中包含产品目录自带 SQLite 的声明 `exreader-product/sqlite-public-domain.txt`）。

没有改动构建参数、SDK、APK、断言、预算，也没有改动原来的冻结 guard。`android_admission.py guard` 用精确字符串断言
`run.py == 基线 run.py + 上述 8 行`，并要求原配方、`tests/reader_f06_packages`、`android-composition-candidate.yml`、
`android-sdk342-package.yml` 与全部 SDK/应用/工具树和基线逐字节相同。

## 验证

专属 workflow [`reader-delivery-android-sdk342-licenses.yml`](../../.github/workflows/reader-delivery-android-sdk342-licenses.yml)
在 Actions 里真实运行：已安装的规范 OPDSHash 前缀（`EXREADER_ORIGINAL_HASH_PREFIX`，不使用私有回退，不删除 provider 检查）→
原 `build()`（同一份 composition 配方）→ 原 `identity.py package` → `android_verify.py verify`（归档 `licenses/` 与 SDK 安装树逐字节、
闭集比较；按 CMakeCache 的登记集合；安装的 vendor 归档；产品前缀许可与 SQLite 声明；APK 的原生库依赖）→ 原 `identity.py android`
模拟器安装。结果见 [EVIDENCE.md](EVIDENCE.md)“追加”一节（run 40950703390，success）。

## 仍然不覆盖

- 编译产物内部是否真的含某第三方代码：由 CMake 开关与已安装归档推断，没有反汇编。
- NDK `c++_static` 运行时与 Android 系统库不由 EXReader 随包提供许可。
- 许可文本与上游逐字一致由 `tools/check_reading_licenses.py` 在 SDK 安装树上检查，这里只绑定“压缩包 = 安装树”。
- 旧的 `tests/reader_f06_packages/build.py` 的 `android()` 同样缺此目录，但该文件被 F06 `guard` 冻结，故未改。
- 不授予 F12，也不是完整产品或 F01/F07/F08 的通过证据。

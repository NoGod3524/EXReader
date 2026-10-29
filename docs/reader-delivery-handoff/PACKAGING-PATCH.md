# 包级补丁声明（唯一一处，最小）

本包只改了下面这一个非本包路径的文件，用于把已发现缺失的许可文本补进 Android 压缩包。`check.py guard` 只接受本清单里声明的路径：

- `tests/android_sdk342_package/run.py`

## 原因

Actions 对已发布压缩包的读取（run 40948655722，见 [EVIDENCE.md](EVIDENCE.md)）显示：Windows、Linux、macOS、iPhone、iPad 压缩包的
`licenses/` 与按各自 CMakeCache 推导的期望集合一致，而 **Android 压缩包没有 `licenses/`，15 个应随包的许可文件缺失**
（只有包根的 `LICENSE` 与 `THIRD_PARTY_NOTICES.md`）。

## 改动

在复制 `LICENSE`、`THIRD_PARTY_NOTICES.md` 之后增加一行：把 SDK 安装树 `build/wave3/sdk-stage/share/exreader/licenses`
整目录复制为压缩包载荷的 `licenses/`，与桌面/Apple 打包脚本的做法相同。没有改动构建参数、SDK、APK、断言或预算。

## 状态：未验证

- 这一行**没有**在真实的 Android 打包流水线里运行过：`android-sdk342-package.yml` 的 `guard` 要求相对其基线的改动路径全部在固定白名单内，
  本分支的文档/测试路径不在其中，不应在本分支上触发它。需由整合分支把该行与流水线一起在同一 SHA 上重跑后，才能确认
  Android 压缩包出现 `licenses/`。本分支的 Actions 只证明：该脚本能被 Python 编译、且源码里确实复制了该目录。
- 只补 SDK 安装树里的许可；Android 产品目录（`share/exreader-product/`）里的 SQLite 声明不在这一行范围内，仍未核对。
- `tests/reader_f06_packages/build.py` 的旧 `android()` 同样缺此目录，但该文件被 F06 `guard` 冻结，故未改。

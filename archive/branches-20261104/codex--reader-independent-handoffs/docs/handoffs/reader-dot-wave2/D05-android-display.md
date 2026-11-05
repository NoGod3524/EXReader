# D05：Android阅读窗口常亮与临时亮度

先读[共同约束](README.md)。固定起点a826a65c9c66e43620eff61b49cb79f941a3c953；唯一分支 **codex/dot-reader-android-display**。

## 目标

独立Android原生library和实际probe app，管理当前阅读Window的FLAG_KEEP_SCREEN_ON与WindowManager.LayoutParams.screenBrightness；供正式宿主以后接入。复用既有原生Gradle约定，不改examples/android或正在收口的导入owner，不写系统Settings、不要求WRITE_SETTINGS、不用后台wake lock/服务。

## 合同与行为

- 显式attach当前Window、设定跟随系统(-1)/有限0..1亮度和是否常亮、前后台activate/deactivate、恢复/close。主线程owner，错线程/重入/重复attach/关闭后调用可验证地拒绝，失败不半改窗口。
- 只在阅读窗口可见且宿主明确active时生效。pause、失焦/销毁、取消和close按合同撤销自己的设置；旋转必须释放旧window再绑定新window，迟到回调不能修改新窗口。
- 保存接管前的实际Window属性；释放仅撤销自己仍持有的改动。若宿主或系统在中途改变属性，不能盲目写回旧值覆盖外部更新。两个独立窗口/多实例采用明确独占lease或拒绝冲突，不能互相清掉常亮。
- 拒绝NaN/Inf/越界、空/已销毁window；跟随系统不偷偷转换固定数值。不持久化用户偏好、不加产品SQL/同步实体，不改色彩/字体/翻页API。

## 范围

extras/android-reader-display/**；tests/reader_android_display/**；.github/workflows/reader-android-display.yml；docs/READER-ANDROID-DISPLAY.md；docs/validation/reader-android-display.json。

Actions编译并安装真实library/probe，API34模拟器实际UI线程读取Window flags/brightness，正常切换/跟随系统/前后台/旋转/窗口重建、错线程、双lease、宿主外部修改、真实进程终止重开和权限清单。逐项证明没有全局设置/后台服务。窗口属性生效与物理屏幕亮度/省电策略严格分开；没有真机就不授予物理效果、耗电或读屏。

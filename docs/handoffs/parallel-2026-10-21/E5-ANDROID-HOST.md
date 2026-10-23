# E5：WP13 Android 原生宿主闭环

你负责Android原生参考阅读应用及模拟器验收。先读同目录`README.md`；当前只有SDK交叉编译/JNI适配，不能用库构建成功代替应用运行。

## 起点与技术边界

- 分支`codex/wp13-android`，实现基线`a2552d7feb786cd2345d2b0b3eb894777b3254db`。
- 参考`bindings/jni/EXReader.java`、`exreader_jni.c`和`Smoke.java`的既有句柄/所有权约定；复用Android平台控件与最少依赖方案。
- 源码级别与最低平台沿当前SDK兼容声明。云端模拟器架构必须有匹配的实际原生库，不把arm64库交叉编译算成x86_64模拟器运行。
- 用户暂不做真机安装；本包只交付云端模拟器验收和可安装测试APK，不请求账号、证书或设备。

## 必做功能

1. 系统文件选择/导入、书架、元数据与重复书籍处理；正确保留URI权限或复制原书到app存储，重开不丢访问。
2. 重排与固定页阅读、翻页、字号/缩放、触摸命中、屏幕旋转；清晰呈现打开/取消/超限/格式错误。
3. 实际文字选择和复制、标注增改删、标注列表回读；重排锚点与固定页位置分别保存。
4. 持久化书架、进度与标注，Activity重建、后台/前台、进程终止后重启可恢复；不能只依赖内存ViewModel。
5. 原生SDK句柄串行使用，页面/字体/图像生命周期明确；旋转、切书和取消时旧结果不会回写新画面，JNI异常不跨边界泄漏。
6. 控件语义、可访问名称与稳定测试标识，为后续TalkBack/WP14提供入口；完整真人屏幕阅读器验收另列。

## 文件所有权

独占`examples/android/**`、`tools/build_android_host.py`、`tools/check_android_host.py`、`tests/android_host/**`、`.github/workflows/wp13-android.yml`、`docs/WP13-ANDROID.md`、`docs/validation/wp13-android*.json`。

共享`bindings/jni/**`只读。缺少书库/锚点包装时，在app目录实现小型局部JNI桥接，直接消费安装的公开SDK，不修改核心或共享JNI以免与其他包冲突。固定NDK/Gradle/工具版本，使用独立app构建；默认SDK不新增Android UI依赖。

## 云端量化出口

- GitHub云端构建匹配ABI的SDK/JNI/app，实际启动至少一种Android模拟器，完成APK安装与应用运行。
- 至少20条真实UI/生命周期步骤：系统导入、书架切换、前后翻页、字号/缩放、触摸选择、标注增改删和导航、旋转、后台恢复、Activity重建、进程重开、取消与失败重试。
- 使用仪器化/UI自动化验证真实事件和持久化状态；仅adb启动、Java编译、JNI smoke或模型单测均不满足应用出口。
- EPUB和PDF阅读/定位至少各一条闭环；其他格式、字体回退及大章路径按实际能力明确列出，不放宽SDK预算。
- 检查重启恢复、歧义位置、句柄关闭及取消，不丢失已保存书籍/标注。字节预算和UI线程耗时如实计量，不臆造“低内存”结论。
- 上传APK、原生日志、逐case JSON、屏幕截图、工具/SDK/字体/输入散列和构建身份；`physical_device_execution=false`。

## 最终交付

可构建消费的原生应用、独立云端工作流、验收表和JSON。提交推送本分支，不合并。交付SHA、文件路径、云端run、模拟器/API/ABI身份、实际通过与未满足项。OPDS、迁移、TTS、真机和其他平台留给各自包，不扩大本次完成声明。

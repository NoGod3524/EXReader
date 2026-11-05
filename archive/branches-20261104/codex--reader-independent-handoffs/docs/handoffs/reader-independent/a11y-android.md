# G15：Android 可访问性与大字体审计

先读[共同约束](README.md)，接受其中全部不变项与云端执行限制。
固定实现起点：`f43baf9182d75907c0cb5d6f77048f27bca8c950`。新建独立工作树和分支 `codex/reader-a11y-android`。
类型：审计；优先级：P1；分发：DeepSeek Harness。

## 文件归属

- `tests/reader_a11y_android/**`
- `.github/workflows/reader-a11y-android.yml`
- `docs/READER-A11Y-ANDROID.md`
- `docs/validation/reader-a11y-android.json`

除此之外的目录只读。不要修改共享构建、已有工作流或本交接目录。

## 实现与边界

仅新增独立设备审计/测试APK构建目录，安装基线真实宿主，通过UiAutomator/AccessibilityNodeInfo读取语义与操作；不改MainActivity、现有manifest/JNI、Gradle或其他owner文件。
审计书架/导入/整理/阅读/标注、名字/角色/状态、焦点/触达、返回导航、大字体/显示缩放、横竖屏；未实现账号页面列未覆盖。
给出实际节点/步骤/截图和最小补丁建议。模拟器语义树不授予TalkBack真机验收，不启用真实用户账号或私人文件。
如平台需要新增生产hook，交root最小建议，本包不得增加隐蔽测试捷径。

## 云端出口

API34模拟器真实宿主与独立测试进程；保持原APK身份，保存原始节点树和截图。audit_completed与accessibility_accepted分开，有问题不宣称通过。
若其他API/真机/读屏未执行，逐项保持未验证，不借交叉编译授予。
同一source/run/attempt逐项验收；参考通过记录不转移到本包源码。任何未覆盖能力继续保持未授予。

## 先读的实际代码

- `examples/android/app`
- `tests/android_host`
- `docs/READER-ANDROID-ORGANIZATION.md`

## 交回

推送功能分支；完整受测SHA、最终纯文档HEAD/差异、run/attempt/job、具名结果、工件ID/字节/digest/有效期、原失败及剩余工作。不要替root合入。


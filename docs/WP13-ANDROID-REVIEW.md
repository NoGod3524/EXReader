# Android 宿主审计修复与重新验收

本轮源码修复已准备，新的 GitHub Actions 验收尚待执行。所有构建、夹具生成、模拟器、
证据门禁正反例都只在云端运行；本地只读源码/Git 并编辑源码。原交付的历史运行保留于
`docs/WP13-ANDROID.md` 与 `docs/validation/wp13-android.json`，不能替代本轮新源码验收。

## 修复范围

| 已发现问题 | 修复与验收入口 |
| --- | --- |
| 导入取消误清理重复书、发布结果与取消竞态、存储回滚 | `examples/android/app/src/main/java/org/exreader/host/MainActivity.java`、`HostTask.java`、`BookStore.java` 以及 `examples/android/app/src/main/cpp/exreader_host_jni.c` |
| 打开、翻页、进度写入失败破坏已接受会话；失效选择；Activity 销毁后的工作线程释放 | `examples/android/app/src/main/java/org/exreader/host/ReflowSession.java`、`FixedSession.java`、`PageLoad.java`、`ReaderView.java`、`MainActivity.java` |
| 普通分页缺少可达的取消入口；旧 Activity 迟到的进度写入覆盖新位置 | `MainActivity.java` 的普通分页 loading、Activity epoch 与后台进度提交锁；移除生命周期重复写回 |
| JNI 非 ASCII 注释往返 | `examples/android/app/src/main/cpp/exreader_host_jni.c` |
| 原测试只检查状态文案，无法证明复制、缩放、恢复结果 | `examples/android/uitest/src/androidTest/java/org/exreader/host/uitest/HostWalkthroughTest.java` |
| 汇总接受缺项、重复、跳过、不一致的逐项证据或失效截图 | `tools/android_host_evidence.py`、`tools/check_android_host.py` |
| run/source/APK/SDK/夹具身份未形成同次实际执行证据 | `tools/build_android_host.py`、`tools/run_android_host_evidence.py` |
| 上游失败仍可生成通过汇总；未验证门禁本身会拒绝错误输入 | `.github/workflows/wp13-android.yml`、`tests/android_host/check_evidence_gate.py` |

原 45 项保留 ID、顺序和标题。字号比较阅读区域实际像素，复制通过前台输入框真实粘贴核对，
PDF 缩放核对同书同页实际位图字节，旋转/重建/重启核对页码、首行和书名；同尺寸重建/重启
还比较阅读区域像素。独立的 `HostReviewTest.java` 增加 10 项实际操作：重复导入取消、新副本
取消、原生插入取消回滚、重复插入取消保留、提交后迟到取消、打开失败、进度失败、忙时选择、
Unicode 注释、销毁工作线程。复核使用真实复制、SDK 插入、SQLite 失败和 Activity 重建，
阶段控制只对 debug 构建开放。

第 10 项实际显示 `Large.epub` 第 1 至 49 页，要求原生 next 调用共 49 次、恢复重放 0 次，
记录实际耗时；随后在旧进度提交中重建 Activity，确认新旧提交顺序、旧线程完成释放、
恢复第 49 页并继续第 50 页，终止进程后仍恢复第 50 页。
汇总同时核对独立 JSON 与原始分页计数日志。

普通翻页、字号和标注定位立即显示取消入口，测试阶段门只更新提示文字。进度锁仅由后台
线程获取，覆盖 SDK 的快照解析及数据库写入；Activity 创建时递增所有者版本，尚未开始的
旧提交被拒绝，已开始的旧提交先于新提交完成。UI 不等待该锁。

## 所有权与身份

- SDK 保护树基线：`a2552d7feb786cd2345d2b0b3eb894777b3254db`；`src`、`include`、
  `bindings`、`cmake` 和顶层 `CMakeLists.txt` 在当前受测 HEAD 必须与该基线一致。
- 审计所有权基线：`9b57cc64094a9c5fc0474ec87ca660d2dc935b74`。默认审计到当前 HEAD，
  只允许 Android 宿主、测试、专用工具、工作流与本包文档。
- 集成时可在工作流以完整提交 SHA 登记 `ANDROID_OWNERSHIP_HEAD`，限定本包审计终点；
  该提交必须是当前受测 HEAD 的祖先。原交付至该终点仍执行同一白名单，SDK 保护树仍检查到
  当前 HEAD。构建证据分别记录 `ownership_head`、`tested_source`。
- `source_sha/run_id/attempt/job` 绑定同次云端执行；源码文件清单、安装 SDK 清单、三个打包
  APK 和从模拟器回拉的三个已安装 APK 均核对实际字节。引擎/JNI 打包库与安装 SDK 核对
  GNU Build ID；三个实际运行库还核对 ELF x86_64、16 KiB LOAD 对齐及 SHA-256。
- 字体核对 APK 内实际资源，夹具核对本次生成清单、主机文件和模拟器文件；两套仪器化
  原始日志分别要求准确类/方法、开始/通过状态及成功终止码。

## 必须拒绝的条件

任一上游 build/static/emulator 非 success；45 或 10 项缺失、重复、乱序、未知或跳过；
逐项 JSON 与汇总不同；截图缺失、空、损坏、逃逸、复用或字节散列不符；来源/run/attempt/
APK/SDK/字体/夹具身份不同；原始日志缺失、失败或不符；49 页计数不符；门禁正反例未完成，
均写出 `accepted=false` 并让最终步骤失败。

`tests/android_host/check_evidence_gate.py` 首先接受本次完整原始证据，再在隔离的硬链接副本
上以原子替换施加受控差异，要求全部拒绝。原证据文件不会被修改。门禁结果记录脚本散列、
同次云端身份和固定检查清单，最终汇总再次验证该结果。

## 单作业、单工件

`.github/workflows/wp13-android.yml` 保留一个 `android-host` 作业和一个
`EXReader-WP13-Android` 工件。工件包括三个 APK、已安装 APK 回拉件、完整夹具、安装 SDK、
构建身份和日志、两套原始仪器化/应用日志、45+10 逐项 JSON/截图、执行采集记录、门禁正反例
结果以及最终 `docs/validation/wp13-android.json`。失败时仍收集并上传现有证据；最终验收
使用上游原始 outcome，预检查的 `continue-on-error` 不能使失败验收变绿。

本轮仍只验收 API 34 x86_64 模拟器，`physical_device_execution=false`；真机安装/签名与
TalkBack 真人验收保持独立跟踪。

## 2026-10-22 美东截止前候选

最新受测候选为 `ac7aecc4d3c2e6e65a6797ab556cd31546ca3a5c`，完整云端运行
[`39816104855`](https://github.com/NoGod3524/EXReader/actions/runs/39816104855)，attempt 1。
截至 16:52 UTC（美东 12:52），最后读取状态为 **in_progress，未授予验收**，作业正在上传
工件，尚未核得最终 45 项、独立 10 项与 48 项门禁的同源通过结果。此时停止后续轮询；云端
运行自然结束。后续文档提交不替代受测提交身份。

历史失败保留：

- `c19854a2aeaefaa5a0c70b6865c17597c7caf21f` / run `39806252140`：原 45 项为 44/45；
  PDF 重启用例仍尝试点击保存标注后已清除的选择取消控件。独立评审在前三项系统文件选择器
  查找失败后，第 4 项的 `am start -W` 等待启动卡住，达到原 900 秒预算；严格汇总拒绝。
- `5a04a27bf518766e03f20f2679e31d77bb42d8ce` / run `39813713535`：原 45 项为 45/45，
  独立评审完整执行为 4/10；销毁 Activity 的 49 页、49 次原生 next、0 次恢复重放和跨 Activity
  提交锁用例通过。6 项失败涉及重复取消时旧 UI 对象、两个新副本取消的空源文件观测、删除源后
  打开失败提示，以及两项选择控件观测；不能以设备命令 exit 0 替代用例通过。
  检查器另有后缀 glob 将普通注释与 PDF 注释的逐项 JSON 混匹配，拒绝 per-case/aggregate
  一致性；当前候选已改为按 suite、顺序编号和完整 case ID 的精确文件名验证，仍拒绝额外文件。
  该改动不代表上述 6 项已修复或通过。

已修复的测试驱动包括：Downloads 文件列表先滚动再定位；保存标注后严格核对选择已清除；
启动使用已有界限的 UI 可见性断言替代无界 `am start -W` 等待。900 秒设备预算、真实操作和
原断言均保留。`sources()`/删除源的嵌套 shell 引号及 glob 执行、选择对象与控件就绪仍待
结合原日志逐项定位，不通过放宽断言收口。

只读云诊断 run `39813325746`、`39813596556` 校验首轮固定 ZIP；run `39816105063`
校验第二轮固定 ZIP：artifact `12441886741`、149894678 字节、
`sha256:eb16d88ddd738cf8905905b18140c25907d620103de1ef4dad54b8554dfc188d`。
诊断始终 `diagnostic_only=true`、`accepted=false`。诊断路径只精确加入 Android 所有权白名单；
SDK 保护树仍与 `a2552d7feb786cd2345d2b0b3eb894777b3254db` 一致。所有旧失败和原件保留，
未下载工件、未跨源拼接，也未启动长期监控。

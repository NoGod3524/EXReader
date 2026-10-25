# Apple SDK3.41 整页主题候选

独立分支 `codex/reader-apple-page-theme` 使用 SDK `edddc463c06ed5731195cdb8f06b2df6dff7699e`，版本 3.41.0、ABI1、core3.40.0。旧 3.40 分支封存。

## 契约

- 默认构建仍选择 SDK3.40，主题 OFF。只有显式选择 3.41 和主题 ON 的候选才调用新 canvas API。安装头与所选版本不符时在构建产品前拒绝。
- ON 初始是原书，无 CSS 覆盖。用户可以在阅读主题中选原书、浅色、深色、跟随系统；选择仅在当前窗口会话内有效。
- 浅/深主题把前景 `#1a1a1aff` / `#e6e6e6ff` 作为用户 CSS，并用公开 `exr_render_page_background` 初始化白 / `#101010ff` canvas。作者显式背景与原图片保留，PDF/CBZ 保持原色。
- 系统颜色由 SwiftUI 的真实 `colorScheme` 通知采样为不可变 palette，交串行 owner 重建 candidate。忙时只保留最新通知，旧 epoch 不发布。
- 改色不保存 SDK 进度、笔记、产品修订、outbox 或旧字号设置。取消和失败保留旧 session、帧与 capture；没有更新请求时恢复已接受的主题选择，继续接收它的系统通知。
- 不授予旧 3.40 记录迁移、性能、真机或完整产品。

## 验证计划与当前状态

当前 `accepted:false`，尚无候选通过记录。构建、语法检查、夹具生成、像素解析均只在 Actions。

独立主题流程先认证 SDK 生产树及六原流程业务步骤未变，再对安装后的唯一动态 SDK 构建 OFF/ON 原生消费者。ON 37 个命名检查、OFF 10 个命名检查覆盖原书逐字一致、TXT/EPUB 实际 canvas 与前景、作者背景/图片保留、固定页逐字不变、非零 capture 不变、逐 SDK 轮询取消、失败及重试，以及 owner 忙时通知合并和过期帧不发布。新入口只允许 ON 消费者作为动态 SDK 导入，OFF 不导入它；两者都拒绝静态 renderer。

独立真实 UI 为 macOS、iPhone 和 iPad 各四个场景：非零文本位置、EPUB 主题与原生控件可达、PDF/CBZ 原色、系统通知。系统场景只从应用写测试请求；Actions 调用 macOS 原生外观设置或 `simctl ui appearance` 改变真实环境，XCTest 等待应用接受帧中的 canvas 像素变色，再请求切回浅色。请求函数不修改 model 的系统布尔值或 palette。原始屏幕附件、已接受 SDK 位图散列和操作日志保留在工件中。

十个协议负例拒绝缺项、重复、乱序、错误 canvas、偏移漂移、坏散列、未知主题、位置变化、未变化的深色位图以及原书回切不一致。

## 历史尝试

- `c2530f54ab43a6a085d5f6afd6c830ed95d05d9a` / [40170929666](https://github.com/NoGod3524/EXReader/actions/runs/40170929666) attempt 1：macOS/iOS simulator SDK 与产品安装两作业通过；原生 OFF 编译运行成功，ON 编译成功，整轮在作者背景精确色像素总数相等的断言处失败。此轮不授予主题。
- 后续保留原/新精确颜色计数诊断，并比较原书实际实色区域的同坐标 8×8 RGBA 像素块；前景抗锯齿边缘不作为背景像素总数相等的依据。图片仍核对实色总数和实际像素块。尚待后续实测确认。
- `049d90ca8b8d64d60d32fdf751b0c5f135de205b` / [40171561915](https://github.com/NoGod3524/EXReader/actions/runs/40171561915) attempt 1：SDK 两目标、原生 OFF 10/ON 37 项、macOS 四个真实主题 UI 场景及 collector 通过。作者背景精确色像素数原书 15329、深色 15308、浅色 15345，同坐标实色块与原图片通过。iPhone/iPad 驱动在 Xcode 尚未产出应用时查询容器，查询 20 秒超时导致驱动提前终止构建，collector 因此缺应用；strict 汇总正确拒绝。后续延后查询到实际应用已构建，并保留、间隔重试只读查询的暂态失败；没有删改四个 UI 场景、真实 OS 命令或像素断言。
- `eea3087c2ef27b9d45e00333ef0a16e586a0ac6e` / [40172575970](https://github.com/NoGod3524/EXReader/actions/runs/40172575970) attempt 1：SDK 两目标、OFF 10/ON 37、十个协议负例、macOS 四场景和 iPad 四场景及 collector 全部通过。iPhone 在初次 `simctl list devices available` 的 45 秒冷启动等待上超时，尚未进入 Xcode，因此整轮仍拒绝。后续把该独立启动等待设为 180 秒，job 总时限仍为 35 分钟；所有业务断言、原六流程和原预算保持原样。早期失败也保存命令诊断，Xcode 失败会打印保留日志尾部。

原 navigation/search/reading-records/shelf/import-mapping/WP13 流程仅添加候选分支守卫、显式 SDK 版本与开关环境。原业务步骤、消费者、collector、strict summary 原样保留；旧色彩断言不改。

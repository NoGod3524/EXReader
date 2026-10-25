# Apple SDK3.41 整页主题候选

独立分支 `codex/reader-apple-page-theme` 使用 SDK `edddc463c06ed5731195cdb8f06b2df6dff7699e`，版本 3.41.0、ABI1、core3.40.0。旧 3.40 分支封存。

## 契约

- 默认构建仍选择 SDK3.40，主题 OFF。只有显式选择 3.41 和主题 ON 的候选才调用新 canvas API。安装头与所选版本不符时在构建产品前拒绝。
- ON 初始是原书，无 CSS 覆盖。用户可以在阅读主题中选原书、浅色、深色、跟随系统；选择仅在当前窗口会话内有效。
- 浅/深主题把前景 `#1a1a1aff` / `#e6e6e6ff` 作为用户 CSS，并用公开 `exr_render_page_background` 初始化白 / `#101010ff` canvas。作者显式背景与原图片保留，PDF/CBZ 保持原色。
- 系统颜色由 SwiftUI 的真实 `colorScheme` 通知采样为不可变 palette，交串行 owner 重建 candidate。忙时只保留最新通知，旧 epoch 不发布。
- 改色不保存 SDK 进度、笔记、产品修订、outbox 或旧字号设置。取消和失败保留旧 session、帧与 capture。
- 不授予旧 3.40 记录迁移、性能、真机或完整产品。

## 验证计划与当前状态

当前 `accepted:false`，尚无候选通过记录。构建、语法检查、夹具生成、像素解析均只在 Actions。

独立主题流程先认证 SDK 生产树及六原流程业务步骤未变，再对安装后的唯一动态 SDK 构建 OFF/ON 原生消费者。计划检查原书逐字一致、TXT/EPUB 实际 canvas 与前景、作者背景/图片保留、固定页逐字不变、非零 capture 不变、逐轮询取消、失败及重试。真实 macOS/iPhone/iPad UI 与系统外观变化还需单独执行。

原 navigation/search/reading-records/shelf/import-mapping/WP13 流程仅添加候选分支守卫、显式 SDK 版本与开关环境。原业务步骤、消费者、collector、strict summary 原样保留；旧色彩断言不改。

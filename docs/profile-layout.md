# GitHub 主页展示约定

- 目标仓库：Freya-Qian/Freya-Qian。
- 区块顺序：精选项目 → 项目 → AI Skills → 最近在写。
- 普通项目简洁卡片，与精选关卡卡片区分；展示尺寸与精选卡片一致。
- AI Skills 每排两张独立圆角卡片，保留完整标题、简介和链接。
- 2026-10-02，Yizhitu 要求文章区改成一条条卡片：一行一篇，跟随系统浅色/深色模式、圆角、简洁排版，保留原有标题、标签、简介、原文链接和顺序，整张卡片可点击。
- 文章卡片资源位于 assets/article-cards/。

- 文章卡片使用 picture 与 prefers-color-scheme 切换浅色、深色资源；不通过时间判断主题。

- Yizhitu 最终确认：所有普通项目、AI Skills、文章卡片均跟随系统主题，精选区两张超级玛丽关卡风格卡片保持原图。

## 独立仓库入口与长期维护（2026-10-07）

- Yizhitu 选择 B：主页上全部项目分别使用独立仓库首页，展示文件列表、README 和 About。
- 普通项目：`Freya-Qian/Lingyu`、`Freya-Qian/AI-Avatar-Twin`。
- AI Skills：`Freya-Qian/ai-pm-skill-evaluator`、`Freya-Qian/ai-product-opportunity-evaluator`、`Freya-Qian/agent-workflow-cost-diagnostician`、`Freya-Qian/data-to-decision-brief`、`Freya-Qian/creative-image-production`、`Freya-Qian/model-evaluation`、`Freya-Qian/model-selector`。
- 精选项目保留已存在的独立入口：`MN0709/MotoViz`、`Freya-Qian/ProdForge-AI`。
- 卡片链接必须指向仓库根 URL，避免使用 `/blob/main/.../README.md`，否则会打开文件预览页。
- 后续源码更新以各独立仓库为目标；个人主页仓库负责展示卡片和入口。原有子目录保留为迁移前归档，兼容旧链接。
- 新独立仓库保留按项目拆分的 Git 提交历史；README 放在根目录，About 简介与主题依据实际项目内容设置。

## 只言片语主页入口（2026-10-08）

- Yizhitu 选择 A：在主页“项目”区添加卡片，沿用现有已发布卡片样式，保留其他区块与入口。
- 新入口为 `https://github.com/Freya-Qian/ZhiYanPianYu`，公开独立仓库；放在灵屿和数字人之后。
- 卡片资源：`assets/project-cards/zhiyanpianyu-white-logo-v1.svg`、`zhiyanpianyu-white-logo-mobile-v1.svg`。桌面为960×340，移动端为320×214，README显示宽度48%，600px以下切换移动资源。
- 卡片介绍：“从一句灵感，到 AI 视频片段。”保留项目已验证单片段生成、完整六阶段仍待验收的事实边界。
- 本轮按实际主页使用白底卡片；旧主题约定不用于改变其他既有卡片。
- 后续源码更新到只言片语独立仓库；主页仓库仅维护展示与链接。

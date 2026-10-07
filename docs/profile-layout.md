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
- 新入口为 `https://github.com/Freya-Qian/ZhiYanPianYu`，公开独立仓库；最新位置为 Featured projects（核心项目）区，在 MotoViz 和 ProdForge AI 之后。
- 卡片资源：`assets/project-cards/zhiyanpianyu-white-logo-v1.svg`、`zhiyanpianyu-white-logo-mobile-v1.svg`。桌面为960×340，移动端为320×214，README显示宽度48%，600px以下切换移动资源。
- 卡片介绍：“从一句灵感，到 AI 视频片段。”保留项目已验证单片段生成、完整六阶段仍待验收的事实边界。
- 本轮按实际主页使用白底卡片；旧主题约定不用于改变其他既有卡片。
- 后续源码更新到只言片语独立仓库；主页仓库仅维护展示与链接。

- 2026-10-08 后续指令覆盖此前普通项目位置：Yizhitu 指定只言片语进入核心项目区。保留卡片与链接，移除普通“项目”区的重复入口，其他卡片顺序不变。

## 核心项目卡片排版修正（2026-10-08）

- Yizhitu 选择 A：核心项目每行两张，第三张只言片语放第二行左侧。
- 三张核心卡片统一960×300、48%显示宽度、标题/英文简介/View project层级；只言片语使用 `assets/project-cards/zhiyanpianyu-simple-v2.svg`，取消原普通项目图标和技术标签。
- 核心区两行均左对齐，删除区块末尾额外br；其他区块、卡片、顺序与链接保留。
- 本条覆盖此前只言片语居中和白底logo卡片入口约定；旧资源保留但不再用于核心区。

- 后续同轮指令：MotoViz 移到非核心“项目”区，放在灵屿和数字人之后；核心项目剩 ProdForge AI、只言片语，两张同排左对齐。此条覆盖三张核心项目的排布数量，统一卡片尺寸与收紧留白要求继续适用。

- 2026-10-08：Yizhitu 要求给 MotoViz 添加图标。普通项目区入口使用 `assets/project-cards/motoviz-icon-v2.svg`，新增浅橙底摩托车线条图标，64×64，与其他普通项目图标同尺寸；保留960×300卡片、文案、链接、排序。

- 2026-10-08：Yizhitu 指出v2图标像自行车，纠正为 `motoviz-motorcycle-v3.svg`：使用明确油箱、发动机块、排气管和前叉的摩托车侧面轮廓。覆盖v2图标入口；卡片其他内容保留。

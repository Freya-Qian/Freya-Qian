<div align="center">
  <img src="build/to-do-panel-icon.png" width="96" alt="灵屿图标" />
  <h1>灵屿 · Lingyu</h1>
  <p>把待办、笔记和正在播放的音乐，收进屏幕顶部。</p>
</div>

灵屿是基于 [TO-DO Panel](https://github.com/xiaopu-ai/TO-DO-Panel) 定制的本地桌面工作台。本目录是 Freya Qian 的项目源码归档，与原作者仓库独立维护。

**当前归档版本：1.2.2**。已在本机 macOS Apple Silicon 使用；Windows 的基础代码沿用原项目，本次 QQ 音乐与外观定制未做 Windows 安装包验收。

## 功能

- **QQ 音乐**：读取当前歌曲与播放状态，控制上一首、播放/暂停、下一首；读取会话提供的真实封面。
- **歌词**：自动匹配，可切换聚焦视图/完整歌词，选择自动滚动/手动浏览；随播放时间逐行推进。
- **待办与计时**：分类待办、搜索、截止日期、重复任务、备注、标签、子步骤和番茄钟。
- **笔记与链接**：Markdown 速记、保存和整理笔记、收藏链接。
- **录音与工作区**：录音、可配置的转写与待办提取，工作区备份和恢复。
- **桌面组件**：按需开启镜子、查看当前窗口，以及本机 AI 任务完成提醒。

外观保留贴顶展开、细青紫渐变边框和唱片装饰；折叠时不显示横线。音乐卡片的边框始终位于唱片上方。首页与其他 Tab 统一深蓝黑底色，普通卡片不加描边，鼠标悬停时显示淡青蓝光晕；照片移除后沿用相同底色。

## 从源码运行

需要 Node.js 18+、npm；当前 Mac 打包配置为 macOS 13+ Apple Silicon。系统权限通过应用设置按实际使用的功能开启。

```bash
git clone https://github.com/Freya-Qian/Freya-Qian.git
cd Freya-Qian/projects/Lingyu
npm ci
npm start
```

在 QQ 音乐中播放歌曲后，首页音乐卡片会接收系统播放会话。封面持续接收系统会话更新，晚到的图片也能显示，并有短时补取机制；图片仍取决于客户端是否提供；歌词匹配依赖 QQ 音乐网络接口，未匹配时界面显示相应状态。

## 本地打包

```bash
npm run build
```

Mac 构建产物位于 `dist.noindex/`，例如 `Lingyu-1.2.2-arm64.dmg`；该目录不提交到源码仓库。本源码归档没有发布下载用的安装包，不会把原作者安装包当成灵屿下载入口。

## 目录

| 路径 | 内容 |
| --- | --- |
| `main.js` / `main-services.js` | 窗口、系统音乐会话、工作区与服务 |
| `renderer/` | 页面、交互、主题与图片资源 |
| `preload.js` / `platform.js` | 安全桥接与平台能力 |
| `vendor/` | 随应用分发的音乐会话适配器和歌词解码器 |
| `build/` | 图标、Mac 权限声明及签名钩子 |
| `scripts/` / `tests/` | 本机通知脚本和已有检查 |
| `docs/` | 设计偏好、说明与来源资料 |

开发检查入口为 `npm test`。本次归档保留原有桌面检查，移除了依赖原作者官网和发布工作流的检查假设。

## 数据与来源

用户数据写入本机 Electron 用户数据目录，不在源码中。为兼容原有数据和系统权限，本版本保留原应用标识与 `Dynamic Panel` 数据目录。

原项目：[xiaopu-ai/TO-DO-Panel](https://github.com/xiaopu-ai/TO-DO-Panel)，基于 v1.2.0 定制。原版权和 [MIT 许可证](LICENSE) 保留；第三方组件的来源和许可证见各自 `vendor/` 目录。灵屿名称、外观及 QQ 音乐定制由 Freya Qian 整理维护。

[更新记录](CHANGELOG.md) · [已确认的设计偏好](docs/music-player-design-preferences.md) · [返回项目主页](../../README.md#-项目)

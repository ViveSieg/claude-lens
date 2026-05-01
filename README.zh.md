<p align="center">
  <img src="assets/logo.svg" width="120" alt="claude-lens logo" />
</p>

<h1 align="center">claude-lens</h1>

<p align="center">
  <i>让 Claude 看得清楚</i><br>
  把 Claude Code 终端的回复实时镜像到浏览器，原生渲染 markdown、数学公式、Mermaid 图、代码高亮。
</p>

<p align="center">
  <a href="https://github.com/ViveSieg/claude-lens/stargazers"><img alt="stars" src="https://img.shields.io/github/stars/ViveSieg/claude-lens?style=for-the-badge&logo=github&color=cc785c&labelColor=141413"></a>
  <a href="https://www.npmjs.com/package/claude-lens"><img alt="npm version" src="https://img.shields.io/npm/v/claude-lens?style=for-the-badge&logo=npm&color=cb3837&labelColor=141413"></a>
  <a href="https://www.npmjs.com/package/claude-lens"><img alt="npm downloads" src="https://img.shields.io/npm/dm/claude-lens?style=for-the-badge&logo=npm&color=e8a55a&labelColor=141413&label=downloads"></a>
  <a href="https://github.com/ViveSieg/claude-lens/blob/main/LICENSE"><img alt="license" src="https://img.shields.io/badge/license-MIT-5db8a6?style=for-the-badge&labelColor=141413"></a>
</p>

<p align="center">
  <a href="README.md">English</a> · <b>中文</b>
</p>

---

## 这是什么？

终端把所有东西压成等宽字符。数学公式变乱码、表格被截断、流程图只剩源代码。**claude-lens** 把你在 Claude Code 收到的每条回复**同步到 Chrome 标签页**里，按它本来的样子渲染出来。

你照样在终端打字。浏览器只是一块漂亮的只读窗口——**同一段对话，两种看法**。

```
┌─ 终端 ─────────────────────┐    ┌─ 浏览器 ──────────────────────┐
│ > 帮我推一下 bessel 函数    │    │  ## Bessel 函数               │
│                            │ ──►│                               │
│ <回复在这里流式出现>         │    │  J_n(x) = …   （数学渲染好了） │
│                            │    │  ┌────────┐                   │
│                            │    │  │ 表格    │                   │
│                            │    │  └────────┘                   │
└────────────────────────────┘    └───────────────────────────────┘
```

---

## 安装：一行命令

```bash
npm install -g claude-lens
```

完事。包会自己跑 setup，slash 命令立刻可用。**不需要再敲什么 `claude-lens setup`**。

环境要求：macOS 或 Linux、Python 3.10+、Node 18+、Claude Code。

---

## 怎么用

在任意 Claude Code 会话里打：

```
/lens on
```

这一句同时做三件事：起本地镜像服务、打开 Chrome 标签页、注册 hook。之后每条回复自动渲染到标签页。要停 `/lens off`。

### 浏览器里你能干什么

- **看回复实时渲染** — markdown、$\LaTeX$、Mermaid 图、代码高亮、表格全都正常
- **多对话切换** — 你在任何终端开的 `claude` 会话都会作为侧栏的一个 feed 出现
- **打字回终端** — 底部有输入框。你打的字既会作为消息存到 feed，也会**自动打进你正在用的 Claude Code 终端**（不用切窗口）
- **粘贴截图** — `Cmd+V` 直接在输入框粘贴截图。会自动上传 + 把文件路径加到消息里 + 让 Claude 能读
- **改名 / 删 feed** — 点标题改名，鼠标悬停 feed 出现 `×` 删除

### Slash 命令

| 命令 | 干什么 |
|---|---|
| `/lens on` | 起服务 + 注册 hook + 开浏览器 |
| `/lens off` | 全停 |
| `/lens open` | 重新打开浏览器 |
| `/lens status` | 服务在跑吗？ |
| `/lens restart` | 重启服务 |

---

## 可选：接 NotebookLM 知识库

如果你有一个 NotebookLM notebook（课程资料、论文、文档）想让 Claude 从里面取事实，跑 `/tutor init` 走向导。

向导会：

1. 检查工具装齐没有
2. 列出你的 notebook，让你挑一个当**知识库**
3. 让你挑一个**角色**给 Claude
4. 生成一份 `CLAUDE.md`，把契约锁进去

### 5 个内置角色

| 角色 | 适用 |
|---|---|
| **research-advisor** | 一堆论文 — 研究流程，带引用 |
| **exam-reviewer** | 课程资料 — 考前复习、考点、易错点 |
| **socratic** | 用反问让你自己想明白，不直接给答案 |
| **librarian** | 纯检索，零评论，只给原文引用 |
| **general** | 兜底通用 |

### 让这套真正有用的契约

每个角色都强制一条铁律：**Claude 输出的每一条领域事实，都必须来自 notebook**。Claude 可以重组、加类比、出题、写代码——**但不能编 notebook 没有的事实**。如果资料没覆盖，必须明说。

这让你能信任答案的程度，远超普通聊天。Notebook 是事实源，Claude 是上面的"会讲课的解释器"。

---

## 它怎么工作（一段话）

Claude 在终端结束一条回复时，hook 把消息读出来发给本地小服务器。服务器存档 + 通过 WebSocket 推到你的浏览器标签页渲染。你在浏览器打字时反向走：消息被打进你正在用的终端。如果服务器没起，hook 静默 no-op，**永远不会阻塞你的终端**。

---

## 配置（基本用不上）

| 变量 | 默认 | 控制什么 |
|---|---|---|
| `CLAUDE_LENS_HOST` | `127.0.0.1` | 监听地址 |
| `CLAUDE_LENS_PORT` | `7456` | 端口 |
| `CLAUDE_LENS_DATA` | `~/.claude-lens` | session 文件存哪 |
| `CLAUDE_LENS_LISTEN_GRACE` | `30` | 浏览器关闭后多少秒内停掉打字注入器 |

---

## 故障排查

**浏览器显示 "disconnected — retrying…"**
服务没起。`/lens on` 或 `claude-lens start`。

**浏览器打字到不了终端**
macOS 第一次必须给终端 Accessibility 权限。系统设置 → 隐私与安全性 → 辅助功能 → 勾选 Terminal.app 或 iTerm.app。

**回复不再在浏览器里出现**
Stop hook 可能被从 `~/.claude/settings.json` 里删了。再跑一次 `/lens on` 把它合并回去。

**`/tutor init` 报 NotebookLM 工具缺失**
`npm i -g notebooklm-client`，然后 `npx notebooklm export-session` 登录 Google。然后重跑向导。

---

## 路线图

- 流式部分消息渲染
- 公网穿透模式（让队友看你的镜像）
- 更多角色（翻译、案例分析、演讲教练）

## 贡献

欢迎 issue / PR。两条铁律：

1. **Stop hook 永远不能阻塞 shell**
2. **"事实来自 notebook" 契约是 tutor 层的脊柱**。新角色必须强制执行

## 鸣谢

- 站在 [Claude Code](https://docs.claude.com/en/docs/claude-code/overview) 之上
- NotebookLM 访问通过 [`notebooklm-client`](https://github.com/icebear0828/notebooklm-client)
- 渲染层：[marked](https://marked.js.org/) · [KaTeX](https://katex.org/) · [Mermaid](https://mermaid.js.org/) · [highlight.js](https://highlightjs.org/)

## Star 趋势

<p align="center">
  <a href="https://star-history.com/#ViveSieg/claude-lens&Date">
    <img src="https://api.star-history.com/svg?repos=ViveSieg/claude-lens&type=Date" alt="Star history" width="640">
  </a>
</p>

## License

[MIT](LICENSE)

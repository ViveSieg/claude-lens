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

**安装时它做了什么：** post-install 在包目录里建一个**独立 Python venv**，然后把 `server/requirements.txt` 里的依赖全装进去（FastAPI/uvicorn，以及 macOS 上的 PyObjC `Quartz` + `Cocoa` 做背景粘贴）。**完全不动你的全局 Python**。安装日志最后一行在 macOS 上应该是 `>>> macOS background-paste ready (PyObjC Quartz + AppKit)`；如果看到的是 `PyObjC import failed`，提示里会给一行重装命令。

> **macOS 首次必做——不做"浏览器打字回终端"功能用不了**
>
> 浏览器 → 终端的打字会把合成键盘事件发到你的终端 App。**默认走 Quartz
> `CGEventPostToPid`**，背景粘贴不抢焦点（终端不会跳到前台）。
> **请在第一次 Send 之前先把权限授好**——否则 listener 静默失败，浏览器
> 看得到你发的消息但终端没反应。
>
> **① 辅助功能（Accessibility）**（永远需要，必须手动添加）
> **系统设置 → 隐私与安全性 → 辅助功能** → 点 `+` 把跑 `claude` 的那个
> **终端 App** 加进去——`Terminal.app`、`iTerm`、`Ghostty`、`WezTerm`、
> `Alacritty` 等任意一个——然后**把开关打到 ON**。光加不打勾不算授权。
>
> **② 自动化（Automation）**（只在 Quartz 回退到 AppleScript 时才需要）
> 如果 `pyobjc-framework-Quartz` 没装上（很少见，requirements 里有），
> listener 会回退到 `osascript`，那个走 Automation。第一次 Send 时 macOS
> 会弹 "xxx 想要控制 'System Events.app'"，点 **好**。手抖点错的话去
> **系统设置 → 隐私与安全性 → 自动化** → 展开你的终端 App → 勾上
> `System Events`。
>
> **③ Cmd+Q 完全退出终端 App** 再重新打开，然后跑 `/lens restart`。
> macOS 的权限只在进程启动时读一次，必须重启才会重新加载。
>
> 检查方法：`~/.claude-lens/listen.log` 应该是空的。出现
> `not allowed assistive access` / `osascript 不允许发送按键 (1002)`
> 是辅助功能没开；出现 `Not authorized to send Apple events to
> System Events` 是自动化没开。
>
> **接收回复不需要这两个权限**，只有从浏览器输入框打字回终端才需要。

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

`/tutor` 是个向导，把一个 **NotebookLM notebook**（课程资料 / 论文 / 内部文档）当作**只读知识库**接进当前项目，并把 Claude 锁进一条铁律：**回答里出现的每一条领域事实都必须来自 notebook，覆盖不到就明说**。

### 第一次接入 — `/tutor init`

在你项目目录里：

```
cd path/to/your/project
claude
```

进入 Claude Code 后：

```
/tutor init
```

向导四步：

**1. Doctor** —— 检查 Node、npm、`notebooklm-client` 包、Google 登录态。`notebooklm-client` 没装会问你 `npm i -g notebooklm-client`；Google session 没有会跑 `npx notebooklm export-session` 弹浏览器让你登录一次。

**2. 选 notebook** —— 列出你账号下所有 NotebookLM notebook，选一个绑给**当前项目**。向导记下它的 id 和 title。

**3. 选角色** —— 5 个内置角色 + 1 个 custom（见下表）。

**4. 生成 `CLAUDE.md` + `AGENTS.md`** 到项目根，把 notebook id、title、角色全 bake 进去。以后这个目录里跑 `claude`，自动加载这套契约。

### 子命令

| 命令 | 功能 |
|---|---|
| `/tutor init` | 完整向导（上面四步） |
| `/tutor doctor` | 只跑工具检查——`npm i` 完或者重新登录 Google 后用 |
| `/tutor notebook` | 重新选 notebook（角色不变） |
| `/tutor role` | 重新选角色（notebook 不变） |
| `/tutor ask "<问题>"` | 一次性问当前 notebook，原样保留 `[1][2]` 引用 |

### 内置角色

| 角色 | 适用 |
|---|---|
| **research-advisor** | 一堆论文 — 研究流程，输出 `资料显示 / 我做了什么 / 结论 / 资料没覆盖的` |
| **exam-reviewer** | 课程资料 — 考前复习，输出 `资料显示 / 我怎么讲 / 考点整理 / 解题方法 / 易错点 / 结论 / 资料没覆盖的` |
| **socratic** | 用反问让你自己想明白，输出 `我反问你 (3 题) / 校对 / 资料没覆盖的` |
| **librarian** | 纯检索零评论，输出 `资料显示 / 来源对照表 / 资料未覆盖` |
| **general** | 兜底通用，输出 `资料显示 / 我的处理 / 结论 / 资料没覆盖的` |
| **custom** | 自己定义（向导第 3 步选 6），契约部分仍然由向导帮你锁好 |

### 设置完就直接对话

`CLAUDE.md` 生成后，这个项目里 Claude 的每一条回复都会先通过 `notebooklm-client` 查 notebook，再按所选角色的格式重新打包。**不用再敲任何命令**。

配合 `/lens on`，回复就实时渲染到浏览器 tab 里——LaTeX 公式、Mermaid 图、代码高亮全有，对带公式的课特别合适（`exam-reviewer` 角色就是默认假设你开了 lens 的）。

### 让这套真正有用的契约

每个角色都强制：**Claude 输出的每一条领域事实，都必须来自 notebook**。Claude 可以重组、加类比、出题、写代码——**但不能编 notebook 没有的事实**。如果资料没覆盖，必须明说。Notebook 答案里的 `[1][2]` 引用会**原样保留**。

这让你能信任答案的程度，远超普通聊天。Notebook 是事实源，Claude 是上面的"会讲课的解释器"。

---

## 它怎么工作（一段话）

Claude 在终端结束一条回复时，hook 把消息读出来发给本地小服务器。服务器存档 + 通过 WebSocket 推到你的浏览器标签页渲染。你在浏览器打字时反向走：listener 通过剪贴板把消息粘到终端。**macOS 上默认走 Quartz `CGEventPostToPid` 背景粘贴**——终端不会被抢到前台，焦点一直留在你的浏览器 tab。服务器没起的话 hook 静默 no-op，**永远不会阻塞你的终端**。

**浏览器 → 终端 链路（macOS）：**
1. 你在 lens 输入框打字 → Send
2. server 把文本写到 FIFO；listener 读出来
3. listener 调 `pbcopy` 设剪贴板（`keystroke` 注入对中文/emoji 不可靠，pbcopy 全 Unicode 都稳）
4. listener 通过 `NSWorkspace` 找到终端 App 的 pid，用 `CGEventPostToPid` 把 Cmd+V + Return 发到那个 pid。**不 activate，不抢焦点，不闪屏**
5. 终端 App 收到合成按键，正常粘贴 + 回车

如果 PyObjC 没装（少见，requirements 里有），listener 回退到 AppleScript activate-paste-restore，能用但终端会跳前台再跳回来，看着会闪一下。

**粘图片：** 把图拖/粘到 lens 输入框会上传到 `~/.claude-lens/uploads/<session>-<时间戳>-<随机>.<扩展>`。输入框只显示短的 `[imageN]` 别名；Send 时展开成 `[image: /full/path]` 让终端那边的 Claude 能直接 `Read`。Feed 里渲染成 280×220 的缩略图。旧 upload 默认 7 天后自动清理。

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

**浏览器打字到不了终端（macOS）**
按键注入走 `osascript`，需要终端 App 有 **辅助功能（Accessibility）** 权限。
具体步骤见上面 [macOS 首次必做](#安装一行命令)。
确认是不是这个原因：看 `~/.claude-lens/listen.log` 里有没有
`osascript 不允许发送按键 (1002)` / `not allowed assistive access`。
授权后重启终端，再 `/lens restart`。

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

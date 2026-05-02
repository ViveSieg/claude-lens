<p align="center">
  <img src="assets/logo.svg" width="120" alt="claude-iris logo" />
</p>

<h1 align="center">claude-iris</h1>

<p align="center">
  <i>让 Claude 看得清楚</i><br>
  将 Claude Code 终端的回复实时镜像至浏览器，原生渲染 Markdown、数学公式、Mermaid 图与代码高亮。
</p>

<p align="center">
  <a href="https://github.com/ViveSieg/claude-iris/stargazers"><img alt="stars" src="https://img.shields.io/github/stars/ViveSieg/claude-iris?style=for-the-badge&logo=github&color=cc785c&labelColor=141413"></a>
  <a href="https://www.npmjs.com/package/claude-iris"><img alt="npm version" src="https://img.shields.io/npm/v/claude-iris?style=for-the-badge&logo=npm&color=cb3837&labelColor=141413"></a>
  <a href="https://www.npmjs.com/package/claude-iris"><img alt="npm downloads" src="https://img.shields.io/npm/dm/claude-iris?style=for-the-badge&logo=npm&color=e8a55a&labelColor=141413&label=downloads"></a>
  <a href="https://github.com/ViveSieg/claude-iris/blob/main/LICENSE"><img alt="license" src="https://img.shields.io/badge/license-MIT-5db8a6?style=for-the-badge&labelColor=141413"></a>
</p>

<p align="center">
  <a href="README.md">English</a> · <b>中文</b>
</p>

---

## 项目简介

终端将所有内容压缩为等宽字符显示——数学公式无法呈现、表格被截断、流程图仅以源码形式存在。**claude-iris** 将 Claude Code 中的每一条回复**同步至 Chrome 标签页**，按其原本的格式进行渲染。

用户仍在终端中输入指令，浏览器仅作为只读的可视化窗口——**同一段对话，提供两种视图**。

```
┌─ 终端 ─────────────────────┐    ┌─ 浏览器 ──────────────────────┐
│ > 帮我推一下 bessel 函数    │    │  ## Bessel 函数               │
│                            │ ──►│                               │
│ <回复在终端流式输出>         │    │  J_n(x) = …  （数学公式渲染） │
│                            │    │  ┌────────┐                   │
│                            │    │  │  表格   │                   │
│                            │    │  └────────┘                   │
└────────────────────────────┘    └───────────────────────────────┘
```

---

## 安装

```bash
npm install -g claude-iris
```

安装包会自动执行初始化流程，slash 命令即时可用，无需手动运行 `claude-iris setup`。

环境要求：macOS 或 Linux、Python 3.10+、Node 18+、Claude Code。

**安装过程说明：** post-install 脚本会在 npm 包目录内创建一个**独立的 Python 虚拟环境**，并将 `server/requirements.txt` 中声明的依赖安装至该虚拟环境（包括 FastAPI、uvicorn，以及 macOS 平台所需的 PyObjC `Quartz` 与 `Cocoa` 用于背景粘贴）。**全程不修改用户的全局 Python 环境**。安装完成时，macOS 平台应输出 `>>> macOS background-paste ready (PyObjC Quartz + AppKit)`；若提示 `PyObjC import failed`，输出中将包含手动重装命令。

> **macOS 首次安装必读 —— "浏览器输入回写终端" 功能依赖系统权限**
>
> 浏览器至终端的输入由合成键盘事件实现。**默认采用 Quartz `CGEventPostToPid`**，在后台完成粘贴，不会抢占焦点（终端不会切换到前台）。
> **请在首次发送之前完成以下权限授予**，否则 listener 将静默失败——浏览器侧可见用户消息，但终端不会接收任何输入。
>
> **① 辅助功能（Accessibility）**（必需，需手动添加）
> **系统设置 → 隐私与安全性 → 辅助功能** → 点击 `+` 将运行 `claude` 的**终端 App**（`Terminal.app`、`iTerm`、`Ghostty`、`WezTerm`、`Alacritty` 等）添加进入列表，并**将开关切换为开启状态**。仅添加而未启用开关不构成有效授权。
>
> **② 自动化（Automation）**（仅在 Quartz 路径回退至 AppleScript 时需要）
> 若 `pyobjc-framework-Quartz` 未能安装（属罕见情况，requirements 中已声明），listener 将回退至 `osascript`，此路径需要 Automation 权限。首次发送时 macOS 将弹出 "xxx 想要控制 'System Events.app'"，请点击 **好**。如误选拒绝，可前往 **系统设置 → 隐私与安全性 → 自动化**，展开对应终端 App 并启用 `System Events`。
>
> **③ 通过 Cmd+Q 完全退出终端 App** 后重新启动，再执行 `/iris restart`。
> macOS 仅在进程启动时读取一次权限配置，必须重启进程方能生效。
>
> 验证方法：`~/.claude-iris/listen.log` 应保持空白。若出现
> `not allowed assistive access` / `osascript 不允许发送按键 (1002)`，
> 表明辅助功能权限未启用；若出现 `Not authorized to send Apple events to
> System Events`，表明自动化权限未启用。
>
> **接收回复无需上述权限**，仅浏览器输入框向终端写入功能依赖于此。

---

## 使用方法

在任意 Claude Code 会话中执行：

```
/iris on
```

该命令同时完成三项操作：启动本地镜像服务、打开 Chrome 标签页、注册 Stop hook。其后所有回复将自动渲染至该标签页。停止服务请使用 `/iris off`。

### 浏览器端功能

- **回复实时渲染** —— Markdown、$\LaTeX$、Mermaid 图、代码高亮、表格均完整支持
- **多会话切换** —— 任意终端中开启的 `claude` 会话均会作为侧栏中的独立 feed 出现
- **输入回写终端** —— 底部输入框中输入的文本既会作为消息存入 feed，也会**自动写入当前活动的 Claude Code 终端**（无需切换窗口）
- **截图粘贴** —— `Cmd+V` 可直接在输入框粘贴截图，文件将自动上传，路径插入消息中，供 Claude 直接读取
- **会话重命名 / 删除** —— 点击标题进行重命名，鼠标悬停 feed 后可见 `×` 按钮用于删除

### Slash 命令

| 命令 | 功能 |
|---|---|
| `/iris on` | 启动服务、注册 hook、打开浏览器 |
| `/iris off` | 停止全部服务并解除 hook |
| `/iris open` | 在浏览器中重新打开镜像页面 |
| `/iris status` | 查询服务运行状态 |
| `/iris restart` | 重启服务 |

---

## 可选：连接 NotebookLM 知识库

`/tutor` 是一个配置向导，将指定的 **NotebookLM notebook**（课程资料、论文、内部文档等）作为**只读知识库**接入当前项目，并约束 Claude 遵守一条核心契约：**回答中涉及的所有领域事实必须源自 notebook，未覆盖的内容须明确声明**。

### 首次接入 — `/tutor init`

在项目目录中执行：

```
cd path/to/your/project
claude
```

进入 Claude Code 后执行：

```
/tutor init
```

向导分为四个步骤：

**1. 环境检查（Doctor）** —— 检查 Node、npm、`notebooklm-client` 包及 Google 登录状态。若 `notebooklm-client` 未安装，向导将询问是否执行 `npm i -g notebooklm-client`；若未登录 Google，将运行 `npx notebooklm export-session` 并打开浏览器进行登录。

**2. 选择 notebook** —— 列出账号下所有 NotebookLM notebook，由用户选择一个绑定至**当前项目**。向导将记录该 notebook 的 id 与 title。

**3. 选择角色** —— 提供 5 个内置角色及 1 个自定义选项，详见下表。

**4. 生成 `CLAUDE.md` 与 `AGENTS.md`** 至项目根目录，将 notebook id、title 及角色信息写入。此后该目录中执行 `claude`，将自动加载契约配置。

### 子命令

| 命令 | 功能 |
|---|---|
| `/tutor init` | 完整向导（上述四步） |
| `/tutor doctor` | 仅执行环境检查——适用于 `npm i` 完成后或重新登录 Google 后 |
| `/tutor notebook` | 重新选择 notebook（保留当前角色） |
| `/tutor role` | 重新选择角色（保留当前 notebook） |
| `/tutor ask "<问题>"` | 单次查询当前 notebook，原样保留 `[1][2]` 引用标记 |

### 内置角色

| 角色 | 适用场景 |
|---|---|
| **research-advisor** | 论文集合 —— 研究流程，输出 `资料显示 / 我做了什么 / 结论 / 资料没覆盖的` |
| **exam-reviewer** | 课程资料 —— 考前复习，输出 `资料显示 / 我怎么讲 / 考点整理 / 解题方法 / 易错点 / 结论 / 资料没覆盖的` |
| **socratic** | 通过反问引导用户独立思考，输出 `我反问你 (3 题) / 校对 / 资料没覆盖的` |
| **librarian** | 纯检索模式，无主观评论，输出 `资料显示 / 来源对照表 / 资料未覆盖` |
| **general** | 通用默认配置，输出 `资料显示 / 我的处理 / 结论 / 资料没覆盖的` |
| **custom** | 用户自定义（向导第 3 步选择 6），契约部分仍由向导自动写入 |

### 配置完成后的使用方式

`CLAUDE.md` 生成后，该项目中 Claude 的每一条回复都将先通过 `notebooklm-client` 查询 notebook，再按所选角色的格式重新组织输出。**无需运行额外命令**。

配合 `/iris on` 启用浏览器镜像，回复将实时渲染为带 LaTeX 公式、Mermaid 图与代码高亮的页面，特别适合带公式的学科课程（`exam-reviewer` 角色默认假设此模式已启用）。

### 知识库契约

每个角色均强制执行以下约定：**Claude 输出的所有领域事实必须来自 notebook**。Claude 可以重组内容、引入类比、设计题目、编写代码，但**不得编造 notebook 中未提及的事实**。如资料未覆盖某一问题，必须明确声明。Notebook 答复中的 `[1][2]` 等引用标记将**原样保留**。

此约定使得回答的可信度远高于普通对话——notebook 是事实来源，Claude 是其上的解释器。

---

## 工作原理

Claude 在终端结束一条回复时，Stop hook 读取该消息并发送至本地服务。服务将其持久化存档，并通过 WebSocket 推送至浏览器标签页进行渲染。用户在浏览器中输入时执行反向流程：listener 通过剪贴板将内容粘贴至终端。**macOS 平台默认采用 Quartz `CGEventPostToPid` 实现后台粘贴**——终端不会被切换至前台，焦点始终保持在浏览器标签页。如服务未启动，hook 静默退出，**不会阻塞终端**。

**双路径兜底：** Claude Code 仅在会话启动时读取一次 hook 配置。在 `/iris on` 之前就已开启的会话不会持有 Stop hook，因此其回复不会推送至 iris。为此服务每 2 秒（`CLAUDE_IRIS_POLL_INTERVAL`）扫描一次 `~/.claude/projects/*/<sid>.jsonl` 中最近 10 分钟内修改过的转录文件，将新轮次自动回填至 iris session 并广播至浏览器。两条路径共用基于 `(role, content[:200])` 的指纹去重，不会重复入库。**结果：无论 Stop hook 是否生效，所有 Claude 会话的最新对话最迟 2 秒后必然出现在浏览器中。**

**浏览器至终端链路（macOS）：**
1. 用户在浏览器输入框输入文本并发送
2. 服务器将文本写入 FIFO；listener 读取
3. listener 调用 `pbcopy` 设置剪贴板（`keystroke` 注入对中文与 emoji 不可靠，pbcopy 对全部 Unicode 均稳定）
4. listener 通过 `NSWorkspace` 解析终端 App 的 pid，使用 `CGEventPostToPid` 将 Cmd+V 与 Return 事件发送至该 pid。**不调用 activate，不抢占焦点，无窗口切换**
5. 终端 App 接收合成按键事件，正常执行粘贴与回车

如 PyObjC 未安装（罕见，requirements 中已声明），listener 将回退至 AppleScript 的 activate-paste-restore 路径，功能可用，但终端会出现短暂的前台切换。

**图片粘贴：** 拖拽或粘贴图片至 iris 输入框时，文件将上传至 `~/.claude-iris/uploads/<session>-<时间戳>-<随机串>.<扩展名>`。输入框中仅显示简短的 `[imageN]` 别名；发送时自动展开为 `[image: /full/path]`，使终端侧的 Claude 能直接 `Read` 该文件。Feed 中以 280×220 像素的缩略图渲染。超过 7 天的旧 upload 文件将在服务启动时自动清理。

---

## 配置项（通常无需调整）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `CLAUDE_IRIS_HOST` | `127.0.0.1` | 监听地址 |
| `CLAUDE_IRIS_PORT` | `7456` | 监听端口 |
| `CLAUDE_IRIS_DATA` | `~/.claude-iris` | session 文件存储位置 |
| `CLAUDE_IRIS_LISTEN_GRACE` | `30` | 浏览器关闭后停止输入注入器的延迟秒数 |
| `CLAUDE_IRIS_FOCUS` | *(自动检测)* | macOS：粘贴目标终端 App 名称（如 `Ghostty`、`Terminal`、`iTerm`），默认基于 `$TERM_PROGRAM` 自动识别；可手动指定以覆盖默认值 |
| `CLAUDE_IRIS_UPLOAD_TTL_DAYS` | `7` | 清理超过 N 天的图片文件（启动时与每 6h 自动复查），设为 `0` 禁用清理 |
| `CLAUDE_IRIS_SESSION_TTL_DAYS` | `30` | 清理 N 天未修改的 session jsonl，设为 `0` 禁用清理 |
| `CLAUDE_IRIS_POLL_INTERVAL` | `2` | transcript 兜底轮询间隔（秒）；设为 `0` 完全关闭轮询，仅依赖 Stop hook |
| `CLAUDE_IRIS_POLL_WINDOW` | `600` | 轮询只考虑最近 N 秒内修改过的 transcript |
| `CLAUDE_IRIS_CLEANUP_INTERVAL` | `21600` | 后台 TTL 清理周期（秒，默认 6h） |

---

## 故障排查

**浏览器显示 "disconnected — retrying…"**
本地服务未运行。执行 `/iris on` 或 `claude-iris start`。

**浏览器输入未到达终端（macOS）**
按键注入路径需要终端 App 持有**辅助功能（Accessibility）** 权限。详见上文 [macOS 首次安装必读](#安装) 章节。
排查依据：检查 `~/.claude-iris/listen.log` 中是否包含
`osascript 不允许发送按键 (1002)` / `not allowed assistive access`。
授权后重启终端，并执行 `/iris restart`。

**回复不再出现于浏览器**
Stop hook 可能已从 `~/.claude/settings.json` 中移除。重新执行 `/iris on` 即可恢复。即便 Stop hook 真的没装，最迟 2 秒后 transcript 轮询会兜底把新轮次同步进来。

**侧栏 × 删除的 session 凭空消失但 transcript 还在**
属于设计：DELETE 会写一份 `~/.claude-iris/sessions/<id>.deleted` 墓碑文件，阻止轮询将其复活。如需恢复某个被删除的会话：
```bash
rm ~/.claude-iris/sessions/<session-id>.deleted
```
或直接在 iris 输入框对该 session 打字，墓碑将被自动移除。

**`/tutor init` 提示 NotebookLM 工具缺失**
执行 `npm i -g notebooklm-client`，再运行 `npx notebooklm export-session` 完成 Google 登录，最后重新运行向导。

---

## 设计层限制

claude-iris 面向**单机单用户、单 Claude Code 终端**场景设计。以下三点是架构选择的直接结果，无法通过代码修复，使用前请先确认你的工作方式与之相容：

- **listener 全局共用，不区分 session**：Cmd+V 注入由一个 `listen.py` 进程负责，按当前焦点终端（或 `CLAUDE_IRIS_FOCUS` 指定）粘贴。同时跑两个 Claude Code 终端时，浏览器输入仍只会进入 focus 终端，与 `session_id` 无关。
- **`/push` 信任 localhost**：服务监听 `127.0.0.1` 且无鉴权，任何同机进程都可写入会话。在受信任的开发机以外不要把端口暴露到外网。
- **`DATA_DIR` 同机独占**：默认 `~/.claude-iris/`，多个 Unix 用户共用同台机器时各自独立。同一用户跑多个 server 实例会冲突（PID 文件、FIFO、session jsonl 都共享）。

## 路线图

- 流式增量消息渲染
- 公网穿透模式（多人共享镜像视图）
- 扩充角色库（翻译、案例分析、演讲教练等）

## 贡献

欢迎提交 issue 与 PR。两条核心约定：

1. **Stop hook 不得阻塞 shell**
2. **"事实来源于 notebook" 契约是 tutor 层的核心**，新角色必须强制执行该约定

## 鸣谢

- 基于 [Claude Code](https://docs.claude.com/en/docs/claude-code/overview) 构建
- NotebookLM 接入通过 [`notebooklm-client`](https://github.com/icebear0828/notebooklm-client)
- 渲染层：[marked](https://marked.js.org/) · [KaTeX](https://katex.org/) · [Mermaid](https://mermaid.js.org/) · [highlight.js](https://highlightjs.org/)

## Star 趋势

<p align="center">
  <a href="https://star-history.com/#ViveSieg/claude-iris&Date">
    <img src="https://api.star-history.com/svg?repos=ViveSieg/claude-iris&type=Date" alt="Star history" width="640">
  </a>
</p>

## License

[MIT](LICENSE)

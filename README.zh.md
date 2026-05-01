<p align="center">
  <img src="assets/logo.svg" width="120" alt="claude-lens logo" />
</p>

<h1 align="center">claude-lens</h1>

<p align="center">
  <i>让 Claude 看得清楚</i><br>
  把 Claude Code 的终端回复实时镜像到浏览器，原生渲染 markdown · LaTeX · Mermaid · 代码高亮。
</p>

<p align="center">
  <a href="https://github.com/ViveSieg/claude-lens/stargazers"><img alt="stars" src="https://img.shields.io/github/stars/ViveSieg/claude-lens?style=for-the-badge&logo=github&color=cc785c&labelColor=141413"></a>
  <a href="https://www.npmjs.com/package/claude-lens"><img alt="npm version" src="https://img.shields.io/npm/v/claude-lens?style=for-the-badge&logo=npm&color=cb3837&labelColor=141413"></a>
  <a href="https://www.npmjs.com/package/claude-lens"><img alt="npm downloads" src="https://img.shields.io/npm/dm/claude-lens?style=for-the-badge&logo=npm&color=e8a55a&labelColor=141413&label=downloads"></a>
  <a href="https://github.com/ViveSieg/claude-lens/blob/main/LICENSE"><img alt="license" src="https://img.shields.io/badge/license-MIT-5db8a6?style=for-the-badge&labelColor=141413"></a>
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-3776ab?style=for-the-badge&logo=python&logoColor=white&labelColor=141413">
  <img alt="Node" src="https://img.shields.io/badge/node-18%2B-339933?style=for-the-badge&logo=nodedotjs&logoColor=white&labelColor=141413">
  <img alt="macOS · Linux" src="https://img.shields.io/badge/platform-macOS%20%C2%B7%20Linux-faf9f5?style=for-the-badge&labelColor=141413">
</p>

<p align="center">
  <a href="README.md">English</a> · <b>中文</b>
</p>

---

## 它解决什么问题

Claude Code 是终端应用。终端能渲染 markdown，但所有不适合等宽网格的内容都会被压扁：

| 你写的 | 终端显示 |
|---|---|
| `$\beta = i_C / i_B$` | `β = i_C / i_B`（字符化、丑、有时直接错位） |
| ```mermaid\nflowchart …``` | 源码原样显示，没有图 |
| 宽表格 / 高亮代码 / 引用 / 脚注 | 尽力而为，常常被截 |

变通做法（复制 → 粘到 markdown 预览器 → 切回终端）会打断你正在做的事。**claude-lens 把这步省掉**：终端里出现的回复，同时也会在 Chrome 标签里**实时**渲染好。

```
┌─ 终端 ─────────────────────┐    ┌─ http://127.0.0.1:7456 ──────┐
│ > /lens on                 │    │  Claude Lens                 │
│ > help me with bessel ...  │ ──►│  ─────────────────────────── │
│                            │    │  ## Bessel functions         │
│ <回复在这里流式出现>         │    │  J_n(x) = …    (KaTeX)       │
│                            │    │  ┌─────┬─────┐               │
│                            │    │  │ 表格正常渲染 │              │
│                            │    │  └─────┴─────┘               │
│                            │    │  ```python … ``` 高亮         │
└────────────────────────────┘    └──────────────────────────────┘
```

## 它能给你什么

| | |
|---|---|
| 🪞 **Mirror** | Stop hook + 本地 FastAPI + Chrome 标签。每轮回复 ~100 ms 内自动渲染。 |
| 🎓 **Tutor**（可选） | 交互式向导：把当前项目绑定到一个固定的 NotebookLM 知识库 + 选好角色模板，生成 `CLAUDE.md`。 |
| 🔭 **多 session 流** | 每个 Claude Code 会话独立 URL，JSONL 持久化历史。可在浏览器里 ➕ 新建 / × 删除 / ✎ 重命名。 |
| ↩️ **双向输入** | 浏览器输入框写入命名管道；同时作为 user 消息持久化到 session，Claude 端可 `curl /session/<id>` 读到。 |
| ✂️ **复制按钮** | 每条消息可复制 markdown 源码或纯文本。 |
| 🗂️ **TOC 边栏** | 自动从 `##`/`###` 抽目录。 |
| 🎨 **Editorial 设计** | 米色画布 + 珊瑚色点缀 + 衬线大标题。 |
| 🛡️ **静默失败** | 如果服务没起，hook 自动 no-op。**永远不会阻塞你的 shell**。 |

## 快速开始

```bash
npm install -g claude-lens
claude-lens setup           # 创建 venv、装插件、注册 slash 命令、体检 NotebookLM 工具链

# 在任意 Claude Code 会话里：
/lens on                    # 起服务、注册 Stop hook、开 Chrome
/tutor init                 # （可选）把当前项目绑到一个 NotebookLM 知识库
```

要从源码装：

```bash
git clone https://github.com/ViveSieg/claude-lens.git
cd claude-lens
./install.sh
```

## Mirror — 核心镜像层

### 数据流

```
Claude Code 会话
        │
        │（一轮 assistant 输出结束）
        ▼
   Stop hook ──► hooks/stop_lens.py
        │
        │ 读 transcript_path，取最后一条 assistant 消息
        ▼
   POST /push ──► FastAPI (server/main.py)
                   │
                   ├─► 写 ~/.claude-lens/sessions/<id>.jsonl
                   └─► WebSocket 广播到所有连接的浏览器
                              │
                              ▼
                       Chrome 渲染
                       (marked + KaTeX + Mermaid + highlight.js)
```

### Stop hook 推送格式

```json
{
  "session_id":    "<claude code 会话 id>",
  "session_label": "<cwd 目录名>",
  "role":          "assistant",
  "content":       "<markdown 回复>"
}
```

### 命令

```
/lens on        起服务、注册 Stop hook、开浏览器
/lens off       停服务、卸 hook
/lens open      重新打开浏览器标签
/lens status    服务运行中？
/lens restart   重启服务
```

浏览器自动选择：Chrome → Chromium → Brave → Edge → 系统默认。

## Tutor — 可选 NotebookLM 向导

第二个 slash 命令 `/tutor` 把当前项目**绑定**到一个固定的 NotebookLM notebook。NotebookLM 在这个工作流里是**只读的资料检索源**——不是老师、不能写入。所有教学/分析由 Claude 完成；NotebookLM 只负责事实检索。

### 资料锚定原则（Source Anchoring）

> **Claude 输出里的每一条领域性论断，都必须能溯源到某次 `/notecraft chat` 的引用。** Claude 可以重组结构、加类比、出题、讲解、做对比、写代码——**但不能凭空编出资料里没有的领域事实**。如果 notebook 里没有，Claude 必须明确写「资料未覆盖」并停止。

每个角色模板都把这条原则锁死。机械操作（算术、化简、代码执行、文件 I/O、排版）不需要引用；新增的领域事实需要。

### 向导流程

```
/tutor init
  ├─ ① doctor         检查 node / npm / notebooklm-client / Google session / lens 服务
  ├─ ② notebook       列出你的 notebook，让你挑一个当知识库
  ├─ ③ role           从 5 个模板里选一个（或自定义）
  ├─ ④ scaffold       生成 ./CLAUDE.md, ./AGENTS.md, ./.claude-lens.json
  ├─ ⑤ start          启动 mirror 服务 + 打开 Chrome
  └─ ⑥ smoke test     跑一句查询，让你直接看到全链路通畅
```

子命令：

```
/tutor init        完整向导
/tutor notebook    切换当前项目的 notebook
/tutor role        切换当前项目的角色
/tutor doctor      只体检不修复
/tutor ask "..."   一次性查询当前项目的 notebook+角色
```

### v0.1 自带 5 个角色

| 角色 | 适用场景 | 输出 schema |
|---|---|---|
| `research-advisor` | 论文堆 / 文献语料 | 资料显示 / 我做了什么 / 结论 / 资料未覆盖 |
| `exam-reviewer` | 课程资料（讲义、教材、习题） | 资料显示 / 我怎么讲 / 考点整理 / 解题方法 / 易错点 / 结论 / 资料未覆盖 |
| `socratic` | 探究式学习——只反问、用资料做事实校对 | 我反问你 / 校对(资料显示) / 资料未覆盖 |
| `librarian` | 严格检索、零评论、原文引用 | 资料显示 / 来源对照表 / 资料未覆盖 |
| `general` | 兜底：以上都不太合适时 | 资料显示 / 我的处理 / 结论 / 资料未覆盖 |

`/tutor init` → 选 `6` 可以现场写自定义角色（三个简短问题），向导会自动把资料锚定原则注入到结果里。

## 配置

| 变量 | 默认值 | 含义 |
|---|---|---|
| `CLAUDE_LENS_HOST` | `127.0.0.1` | 监听地址 |
| `CLAUDE_LENS_PORT` | `7456` | 端口 |
| `CLAUDE_LENS_DATA` | `~/.claude-lens` | session JSONL + pid 文件 |
| `CLAUDE_LENS_ENDPOINT` | `http://127.0.0.1:7456/push` | Stop hook 的 POST 目标 |
| `CLAUDE_LENS_TIMEOUT` | `1.5` | Stop hook HTTP 超时（秒） |

如果同一台机器要跑两份（多用户共享），改 `CLAUDE_LENS_PORT` 和 `CLAUDE_LENS_DATA` 即可。

## 双向输入

浏览器底部输入框，回车后做两件事：

1. **存为当前 session 的一条 user 消息** —— Claude 端可 `curl http://127.0.0.1:7456/session/<id>` 读到，全部历史保留。
2. **写入命名管道 `~/.claude-lens/input.pipe`** —— 任意终端 wrapper 都能读：

```bash
cat ~/.claude-lens/input.pipe   # 阻塞直到有内容
```

claude-lens **不会**自动注入到 Claude Code 的 prompt——这一段留给你自己接。

## 故障排查

**浏览器空白 / 显示 "disconnected — retrying…"**
跑 `claude-lens status`。没起就 `claude-lens start`。如果 7456 被占用，设 `CLAUDE_LENS_PORT` 到一个空闲端口，再 `/lens on`。

**`/tutor init` 报 `notebooklm-client: MISSING`**
`npm i -g notebooklm-client`。如果遇到 `EACCES`，前面加 `sudo`。

**`/tutor init` 报 session 缺失**
跑 `npx notebooklm export-session`——会开浏览器让你登录 Google，session 写到 `~/.notebooklm/session.json`。然后重跑向导。

**回复不再出现在浏览器**
Stop hook 可能从 `~/.claude/settings.json` 里被删了。再跑一次 `/lens on` 会安全合并回去。

## 开发路线

- [ ] 流式部分消息渲染（目前是回合结束时整段推）
- [ ] 公网穿透模式（Cloudflare Tunnel / ngrok 包装）
- [ ] 角色 lint：当一段输出本应带引用却没带时给警告
- [ ] 更多角色：`case-analyst`、`translator`、`speech-coach`
- [ ] 把命名管道消费者内置成 `claude-lens listen` 子命令

## 贡献

欢迎 issue / PR。改核心代码请记住两条铁律：

1. **Stop hook 永远不能阻塞 shell**。任何与服务通信的路径必须快速超时 + 失败时静默 no-op。
2. **资料锚定原则是 tutor 层的脊柱**。新角色必须强制执行；任何"放宽"该原则的 PR 需要充分论证。

## 鸣谢

- 站在 [Claude Code](https://docs.claude.com/en/docs/claude-code/overview) 之上。
- NotebookLM 访问通过 [`notebooklm-client`](https://github.com/icebear0828/notebooklm-client)。
- 渲染层：[marked](https://marked.js.org/) · [KaTeX](https://katex.org/) · [Mermaid](https://mermaid.js.org/) · [highlight.js](https://highlightjs.org/)。

## Star 趋势

<p align="center">
  <a href="https://star-history.com/#ViveSieg/claude-lens&Date">
    <img src="https://api.star-history.com/svg?repos=ViveSieg/claude-lens&type=Date" alt="Star history" width="640">
  </a>
</p>

## License

[MIT](LICENSE)。

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&color=0:cc785c,100:e8a55a&height=120&section=footer" alt="" />
</p>

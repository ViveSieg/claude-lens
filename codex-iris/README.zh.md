# Codex Iris 使用说明

Codex Iris 是把 [`ViveSieg/claude-iris`](https://github.com/ViveSieg/claude-iris)
改造成 Windows + Codex Desktop 可用版本的一套本地工具。

它包含两部分：

- `codex_iris.py`：读取本机 Codex 会话 JSONL，把 Codex 输出镜像到浏览器。
- `tutor.ps1`：把当前项目绑定到只读 NotebookLM notebook，让 Codex 回答专业问题前先查询资料库，并保留 `[1-3]` 这类引用标记。

Codex Iris 不会向 NotebookLM 写入内容，只读取资料并整理答案。

## 一、安装依赖

在项目根目录运行：

```powershell
npm install notebooklm notebooklm-client playwright undici
npx playwright install chromium
```

需要：

- Windows PowerShell
- Python 3
- Node.js 20 或更新版本
- Google Chrome
- 一个能打开目标 NotebookLM 的 Google 账号

## 二、启动 Codex 浏览器镜像

```powershell
cd "C:\Users\Administrator\Documents\New project 2"
.\codex-iris\start.ps1
```

然后打开：

```text
http://127.0.0.1:7456
```

停止：

```powershell
.\codex-iris\stop.ps1
```

## 三、登录 NotebookLM

最稳定的方式是用真实 Chrome 登录，然后让脚本通过 CDP 控制这个 Chrome。

```powershell
cd "C:\Users\Administrator\Documents\New project 2"

$env:CODEX_TUTOR_CHROME_PORT="9555"
$env:CODEX_TUTOR_PROFILE_DIR="$env:USERPROFILE\.notebooklm\manual-chrome-profile-9555"

.\codex-iris\tutor.ps1 login
```

Chrome 打开后：

1. 登录能访问 NotebookLM 的 Google 账号。
2. 打开目标 notebook。
3. 回到 PowerShell，按 Enter 保存 session。

使用 Tutor 功能时，这个 Chrome 窗口要保持打开。

## 四、新开 PowerShell 后怎么用

每次新开 PowerShell，先设置这两个环境变量：

```powershell
cd "C:\Users\Administrator\Documents\New project 2"

$env:CODEX_TUTOR_CHROME_PORT="9555"
$env:CODEX_TUTOR_TRANSPORT="cdp"
```

检查绑定：

```powershell
.\codex-iris\tutor.ps1 detail
```

提问：

```powershell
.\codex-iris\tutor.ps1 ask "用三句话总结 PID 控制"
```

如果 `detail` 能看到 notebook 标题和资料源，说明绑定和登录都正常。

## 五、绑定项目

```powershell
.\codex-iris\tutor.ps1 init
```

它会生成：

- `.codex-tutor.json`
- `AGENTS.md`
- `CLAUDE.md`

这些文件告诉 Codex：专业事实必须先查 NotebookLM，回答时保留 NotebookLM 引用。

## 六、常用命令

```powershell
.\codex-iris\tutor.ps1 doctor
.\codex-iris\tutor.ps1 login
.\codex-iris\tutor.ps1 list
.\codex-iris\tutor.ps1 detail
.\codex-iris\tutor.ps1 init
.\codex-iris\tutor.ps1 ask "你的问题"
```

## 七、乱码处理

如果中文变成：

```text
浠ヤ笅鏄...
```

说明 PowerShell 正在用 GBK 显示 UTF-8。先运行：

```powershell
chcp 65001
```

当前版本的 `tutor.ps1` 已经把 PowerShell 输出和 Node 子进程输出都强制设为 UTF-8。

## 八、卡住处理

如果 PowerShell 一直闪烁但不返回，先查是不是有 Node 进程卡在 Chrome 调试端口：

```powershell
netstat -ano | Select-String -Pattern ':9555'
Get-Process node
```

如果看到某个 `node.exe` 和 `127.0.0.1:9555` 长时间保持 `ESTABLISHED`，结束它：

```powershell
taskkill /PID <pid> /F
```

现在脚本已经加了外层超时，正常情况下不会无限等待。

## 九、几个关键环境变量

- `CODEX_TUTOR_CHROME_PORT`：Chrome 调试端口，通常用 `9555`。
- `CODEX_TUTOR_TRANSPORT`：设置为 `cdp`，强制使用已登录 Chrome。
- `CODEX_TUTOR_PROFILE_DIR`：手动登录时使用的 Chrome profile。
- `CODEX_TUTOR_PROXY`：代理地址，例如 `http://127.0.0.1:7890`。
- `CODEX_TUTOR_API_TIMEOUT_MS`：PowerShell 外层超时。
- `CODEX_TUTOR_CONNECT_TIMEOUT_MS`：连接 Chrome/NotebookLM 超时。
- `CODEX_TUTOR_FETCH_TIMEOUT_MS`：浏览器内 fetch 超时。
- `CODEX_TUTOR_ASK_TIMEOUT_MS`：NotebookLM ask 超时。

## 十、限制

- NotebookLM 只读，不写回。
- 需要目标 Chrome 窗口保持打开。
- NotebookLM 的内部 RPC 不是公开稳定 API，后续 Google 改接口时可能需要更新脚本。
- Codex Desktop 没有 Claude Code 的 hook 输入管线，所以浏览器镜像只负责查看，不负责把浏览器输入送回 Codex。

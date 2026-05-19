[CmdletBinding()]
param(
  [Parameter(Position = 0)]
  [string]$Command = "doctor",

  [string]$NotebookId = "",
  [string]$NotebookTitle = "",
  [string]$Role = "",
  [string]$ProjectRoot = "",

  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$Rest
)

$ErrorActionPreference = "Stop"

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = $Utf8NoBom
try {
  [Console]::InputEncoding = $Utf8NoBom
  [Console]::OutputEncoding = $Utf8NoBom
} catch {}

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ProjectRoot) {
  $ProjectRoot = Split-Path -Parent $Root
}
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$ConfigPath = Join-Path $ProjectRoot ".codex-tutor.json"
$AgentsPath = Join-Path $ProjectRoot "AGENTS.md"
$ClaudePath = Join-Path $ProjectRoot "CLAUDE.md"
$RolesDir = Join-Path $Root "tutor\roles"
$NodeProxyScript = Join-Path $Root "node-proxy.cjs"
$NotebookApiScript = Join-Path $Root "notebooklm-api.mjs"
$SessionExportScript = Join-Path $Root "export-notebooklm-session.mjs"
$NotebookLoginScript = Join-Path $Root "notebooklm-login.mjs"
$NotebookManualLoginScript = Join-Path $Root "notebooklm-manual-login.mjs"
$NotebookLegacyCli = Join-Path $ProjectRoot "node_modules\notebooklm\dist\cli\index.js"
$NotebookClientCli = Join-Path $ProjectRoot "node_modules\notebooklm-client\dist\cli.js"
$Today = Get-Date -Format "yyyy-MM-dd"

$RoleChoices = @(
  "research-advisor",
  "exam-reviewer",
  "socratic",
  "librarian",
  "general"
)

function Write-Step($Text) {
  Write-Output ""
  Write-Output "== $Text =="
}

function Test-Tool($Name) {
  $cmd = Get-Command $Name -ErrorAction SilentlyContinue
  if ($cmd) {
    return $cmd.Source
  }
  return $null
}

function Get-AuthPath {
  $candidates = @(
    (Join-Path $HOME ".notebooklm\session.json"),
    (Join-Path $HOME ".notebooklm\storage-state.json")
  )
  foreach ($path in $candidates) {
    if (Test-Path -LiteralPath $path) {
      return $path
    }
  }
  return $null
}

function Read-TutorConfig {
  if (-not (Test-Path -LiteralPath $ConfigPath)) {
    return $null
  }
  return Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Save-TutorConfig($Config) {
  $Config | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ConfigPath -Encoding UTF8
}

function Test-TutorDisabled {
  $config = Read-TutorConfig
  if ($config -and $null -ne $config.enabled -and $config.enabled -eq $false) {
    return $true
  }
  return $false
}

function Assert-TutorEnabled {
  if (Test-TutorDisabled) {
    throw "NotebookLM tutor mode is disabled for this project. Skipping NotebookLM as requested. Re-enable with .\codex-iris\tutor.ps1 init -NotebookId <id> -NotebookTitle <title> -Role general"
  }
}

function Invoke-NotebookLm([string[]]$NotebookArgs) {
  Enable-NodeProxy
  & npx notebooklm @NotebookArgs
}

function Get-SystemProxy {
  try {
    $settings = Get-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    if ($settings.ProxyEnable -eq 1 -and $settings.ProxyServer) {
      $server = [string]$settings.ProxyServer
      if ($server -match "=") {
        $parts = @{}
        foreach ($part in ($server -split ";")) {
          if ($part -match "^([^=]+)=(.+)$") {
            $parts[$Matches[1].ToLowerInvariant()] = $Matches[2]
          }
        }
        if ($parts.ContainsKey("https")) {
          $server = $parts["https"]
        } elseif ($parts.ContainsKey("http")) {
          $server = $parts["http"]
        }
      }
      if ($server -notmatch "^[a-z]+://") {
        $server = "http://$server"
      }
      return $server
    }
  } catch {
    return $null
  }
  return $null
}

function Enable-NodeProxy {
  Enable-ProxyEnv | Out-Null
  if ($env:CODEX_TUTOR_PROXY -and (Test-Path -LiteralPath $NodeProxyScript)) {
    $shortProxyScript = (& cmd /d /c "for %I in (`"$NodeProxyScript`") do @echo %~sI").Trim()
    if (-not $shortProxyScript) {
      $shortProxyScript = $NodeProxyScript
    }
    $requireArg = "--require=$shortProxyScript"
    if (-not $env:NODE_OPTIONS -or $env:NODE_OPTIONS -notlike "*node-proxy.cjs*") {
      $env:NODE_OPTIONS = (($env:NODE_OPTIONS, $requireArg) -join " ").Trim()
    }
  }
}

function Enable-ProxyEnv {
  $proxy = $env:CODEX_TUTOR_PROXY
  if (-not $proxy) {
    $proxy = Get-SystemProxy
  }
  if ($proxy) {
    $env:CODEX_TUTOR_PROXY = $proxy
    $env:HTTPS_PROXY = $proxy
    $env:HTTP_PROXY = $proxy
  }
  return $proxy
}

function Get-EnvInt([string]$Name, [int]$Default) {
  $value = [Environment]::GetEnvironmentVariable($Name)
  $parsed = 0
  if ($value -and [int]::TryParse($value, [ref]$parsed) -and $parsed -gt 0) {
    return $parsed
  }
  return $Default
}

function Get-NotebookApiTimeoutMs([string[]]$ApiArgs) {
  $commandName = ""
  if ($ApiArgs.Count -gt 0) {
    $commandName = $ApiArgs[0]
  }

  $base = 90000
  switch ($commandName) {
    "ask" { $base = Get-EnvInt "CODEX_TUTOR_ASK_TIMEOUT_MS" 180000 }
    "detail" { $base = Get-EnvInt "CODEX_TUTOR_DETAIL_TIMEOUT_MS" 90000 }
    "list" { $base = 90000 }
  }

  return Get-EnvInt "CODEX_TUTOR_API_TIMEOUT_MS" ($base + 15000)
}

function Quote-ProcessArgument([string]$Argument) {
  if ($null -eq $Argument -or $Argument.Length -eq 0) {
    return '""'
  }

  if ($Argument -notmatch '[\s"]') {
    return $Argument
  }

  $result = '"'
  $slashes = 0

  foreach ($char in $Argument.ToCharArray()) {
    if ($char -eq [char]92) {
      $slashes += 1
      continue
    }

    if ($char -eq '"') {
      $result += ('\' * (($slashes * 2) + 1))
      $result += '"'
      $slashes = 0
      continue
    }

    if ($slashes -gt 0) {
      $result += ('\' * $slashes)
      $slashes = 0
    }
    $result += $char
  }

  if ($slashes -gt 0) {
    $result += ('\' * ($slashes * 2))
  }

  $result += '"'
  return $result
}

function Join-ProcessArguments([string[]]$Arguments) {
  return (($Arguments | ForEach-Object { Quote-ProcessArgument $_ }) -join " ")
}

function Invoke-NotebookApi([string[]]$ApiArgs) {
  Enable-ProxyEnv | Out-Null
  $oldNodeOptions = $env:NODE_OPTIONS
  $oldHttpsProxy = $env:HTTPS_PROXY
  $oldHttpProxy = $env:HTTP_PROXY
  $oldAllProxy = $env:ALL_PROXY
  $env:NODE_OPTIONS = ""
  $env:HTTPS_PROXY = ""
  $env:HTTP_PROXY = ""
  $env:ALL_PROXY = ""
  try {
    $nodeArgs = @($NotebookApiScript) + $ApiArgs
    $argumentLine = Join-ProcessArguments $nodeArgs
    $timeoutMs = Get-NotebookApiTimeoutMs $ApiArgs

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = "node"
    $startInfo.Arguments = $argumentLine
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    try {
      $startInfo.StandardOutputEncoding = $Utf8NoBom
      $startInfo.StandardErrorEncoding = $Utf8NoBom
    } catch {}
    $startInfo.CreateNoWindow = $true

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    [void]$process.Start()
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()

    if (-not $process.WaitForExit($timeoutMs)) {
      try {
        $process.Kill()
      } catch {}
      [void]$process.WaitForExit(5000)

      $script:NotebookApiExitCode = 124
      $lines = @()
      $stderrText = ""
      $stdoutText = ""
      if ($stderrTask.Wait(1000)) { $stderrText = $stderrTask.Result }
      if ($stdoutTask.Wait(1000)) { $stdoutText = $stdoutTask.Result }
      if ($stderrText) { $lines += ($stderrText -split "`r?`n" | Where-Object { $_ -ne "" }) }
      if ($stdoutText) { $lines += ($stdoutText -split "`r?`n" | Where-Object { $_ -ne "" }) }
      $lines += (@{
        ok = $false
        error = "NotebookLM command timed out after $([math]::Round($timeoutMs / 1000)) seconds."
        name = "TimeoutError"
        code = "CODEX_TUTOR_WRAPPER_TIMEOUT"
      } | ConvertTo-Json -Depth 4)
      return $lines
    }

    $process.WaitForExit()
    $script:NotebookApiExitCode = $process.ExitCode
    $output = @()
    $stderrText = $stderrTask.Result
    $stdoutText = $stdoutTask.Result
    if ($stderrText) { $output += ($stderrText -split "`r?`n" | Where-Object { $_ -ne "" }) }
    if ($stdoutText) { $output += ($stdoutText -split "`r?`n" | Where-Object { $_ -ne "" }) }
    return $output
  } finally {
    $env:NODE_OPTIONS = $oldNodeOptions
    $env:HTTPS_PROXY = $oldHttpsProxy
    $env:HTTP_PROXY = $oldHttpProxy
    $env:ALL_PROXY = $oldAllProxy
  }
}

function Convert-JsonFromMixedOutput($Raw) {
  $lines = @($Raw | ForEach-Object { [string]$_ })
  for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match "^\s*\{") {
      $candidate = ($lines[$i..($lines.Count - 1)] -join "`n")
      try {
        return $candidate | ConvertFrom-Json
      } catch {
        continue
      }
    }
  }
  throw "No JSON object found in command output: $($lines -join ' ')"
}

function Get-NotebookList {
  Assert-TutorEnabled
  $oldPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $raw = Invoke-NotebookApi @("list")
    $code = $script:NotebookApiExitCode
  } finally {
    $ErrorActionPreference = $oldPreference
  }
  if ($code -ne 0) {
    $message = $null
    try {
      $errData = Convert-JsonFromMixedOutput $raw
      $message = "NotebookLM list failed: $($errData.error). Run: .\codex-iris\tutor.ps1 login"
    } catch {
      $message = $null
    }
    if ($message) {
      throw $message
    }
    Write-Output $raw
    throw "NotebookLM list failed. Run: .\codex-iris\tutor.ps1 login"
  }

  $data = Convert-JsonFromMixedOutput $raw
  if (-not $data.ok) {
    throw "NotebookLM list failed: $($data.error). Run: .\codex-iris\tutor.ps1 login"
  }
  $items = @($data.notebooks | ForEach-Object {
    [PSCustomObject]@{
      Id = $_.id
      Title = $_.title
      SourceCount = $_.sourceCount
      UpdatedAt = $_.updatedAt
    }
  })

  if (-not $items.Count) {
    throw @"
NotebookLM returned zero notebooks for the current CLI login.

This usually means the Google account used by .\codex-iris\tutor.ps1 login
does not own or cannot access the bound notebook:
$((Read-TutorConfig).notebook_id)

Open that notebook URL in the same Google account, or re-run login and choose
the account that can see it:
.\codex-iris\tutor.ps1 login
"@
  }
  return $items
}

function Select-Notebook {
  Write-Step "NotebookLM notebooks"
  $items = Get-NotebookList
  for ($i = 0; $i -lt $items.Count; $i++) {
    $n = $i + 1
    Write-Output ("{0}. {1}  {2}" -f $n, $items[$i].Id, $items[$i].Title)
  }
  if ($items.Count -eq 1) {
    Write-Output "Only one notebook found; selecting it automatically."
    return $items[0]
  }
  $choice = Read-Host "Pick a notebook number"
  if (-not ([string]$choice).Trim()) {
    Write-Output "No notebook choice entered; selecting the first notebook."
    return $items[0]
  }
  $idx = [int]$choice - 1
  if ($idx -lt 0 -or $idx -ge $items.Count) {
    throw "Invalid notebook choice: $choice"
  }
  return $items[$idx]
}

function Select-Role {
  Write-Step "Tutor role"
  Write-Output "1. research-advisor - paper/research notebooks"
  Write-Output "2. exam-reviewer    - courses, textbooks, exam review"
  Write-Output "3. socratic         - guided questions before final answers"
  Write-Output "4. librarian        - strict retrieval with minimal commentary"
  Write-Output "5. general          - default assistant grounded in NotebookLM"
  $choice = Read-Host "Pick a role number"
  if (-not ([string]$choice).Trim()) {
    Write-Output "No role choice entered; using general."
    return "general"
  }
  switch ($choice) {
    "1" { return "research-advisor" }
    "2" { return "exam-reviewer" }
    "3" { return "socratic" }
    "4" { return "librarian" }
    "5" { return "general" }
    default { throw "Invalid role choice: $choice" }
  }
}

function Backup-IfNeeded($Path) {
  if (-not (Test-Path -LiteralPath $Path)) {
    return
  }
  $existing = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
  if ($existing -like "*CODEX TUTOR GENERATED*") {
    return
  }
  $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
  Copy-Item -LiteralPath $Path -Destination "$Path.bak-$stamp" -Force
  Write-Output "Backed up existing file: $Path.bak-$stamp"
}

function Render-TutorFiles($Config) {
  $roleId = [string]$Config.role
  $templatePath = Join-Path $RolesDir "$roleId.md"
  if (-not (Test-Path -LiteralPath $templatePath)) {
    throw "Role template not found: $templatePath"
  }

  $template = Get-Content -LiteralPath $templatePath -Raw -Encoding UTF8
  $body = $template `
    -replace [regex]::Escape("{{NOTEBOOK_ID}}"), [string]$Config.notebook_id `
    -replace [regex]::Escape("{{NOTEBOOK_TITLE}}"), [string]$Config.notebook_title `
    -replace [regex]::Escape("{{TODAY}}"), $Today

  $header = @"
<!-- CODEX TUTOR GENERATED. Re-run .\codex-iris\tutor.ps1 init/role/notebook to update. -->

# Codex Tutor Binding

This project is bound to a read-only NotebookLM notebook.

- Notebook title: $($Config.notebook_title)
- Notebook id: $($Config.notebook_id)
- Tutor role: $($Config.role)
- Query command: `.\codex-iris\tutor.ps1 ask "<question>"`

For any domain-specific claim about the notebook's topic, first query NotebookLM with
the command above. Preserve NotebookLM citation markers such as `[1][2]` exactly.
If NotebookLM does not cover the requested fact, say `资料未覆盖` instead of guessing.

"@

  Backup-IfNeeded $AgentsPath
  Backup-IfNeeded $ClaudePath
  ($header + $body) | Set-Content -LiteralPath $AgentsPath -Encoding UTF8
  ($header + $body) | Set-Content -LiteralPath $ClaudePath -Encoding UTF8
  Write-Output "Wrote $AgentsPath"
  Write-Output "Wrote $ClaudePath"
}

function Run-Doctor {
  Write-Step "Tools"
  $node = Test-Tool "node"
  $npm = Test-Tool "npm"
  $npx = Test-Tool "npx"
  Write-Output ("node: {0}" -f ($(if ($node) { & node --version } else { "MISSING" })))
  Write-Output ("npm:  {0}" -f ($(if ($npm) { & npm --version } else { "MISSING" })))
  Write-Output ("npx:  {0}" -f ($(if ($npx) { "present" } else { "MISSING" })))
  try {
    $playwrightVersion = & npx playwright --version 2>&1
    Write-Output "playwright: $playwrightVersion"
  } catch {
    Write-Output "playwright: MISSING - run npm install playwright and npx playwright install chromium"
  }

  Write-Step "NotebookLM"
  try {
    $version = & node $NotebookClientCli --version 2>&1
    Write-Output "notebooklm-client: $version"
  } catch {
    Write-Output "notebooklm-client: unavailable"
  }
  $proxy = Get-SystemProxy
  if ($proxy) {
    Write-Output "proxy: $proxy"
  } else {
    Write-Output "proxy: none"
  }

  $auth = Get-AuthPath
  if ($auth) {
    Write-Output "auth: present ($auth)"
  } else {
    Write-Output "auth: MISSING - run .\codex-iris\tutor.ps1 login"
  }

  Write-Step "Project binding"
  if (Test-Path -LiteralPath $ConfigPath) {
    Write-Output "config: present ($ConfigPath)"
    Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8
  } else {
    Write-Output "config: MISSING - run .\codex-iris\tutor.ps1 init"
  }
  Write-Output ("AGENTS.md: {0}" -f ($(if (Test-Path -LiteralPath $AgentsPath) { "present" } else { "missing" })))
  Write-Output ("CLAUDE.md: {0}" -f ($(if (Test-Path -LiteralPath $ClaudePath) { "present" } else { "missing" })))
}

function Run-Init {
  $selectedNotebook = $null
  if (-not $NotebookId) {
    $selectedNotebook = Select-Notebook
    $NotebookId = $selectedNotebook.Id
    $NotebookTitle = $selectedNotebook.Title
  }
  if (-not $NotebookTitle) {
    $NotebookTitle = $NotebookId
  }
  if (-not $Role) {
    $Role = Select-Role
  }
  if ($RoleChoices -notcontains $Role) {
    throw "Unknown role '$Role'. Valid roles: $($RoleChoices -join ', ')"
  }

  $config = [PSCustomObject]@{
    notebook_id = $NotebookId
    notebook_title = $NotebookTitle
    role = $Role
    created_at = (Get-Date).ToString("o")
    query_command = ".\codex-iris\tutor.ps1 ask `"<question>`""
  }
  Save-TutorConfig $config
  Render-TutorFiles $config

  Write-Step "Smoke test"
  Write-Output "Run this after login succeeds:"
  Write-Output ".\codex-iris\tutor.ps1 ask `"Summarize the core topic of this notebook in one sentence.`""
}

function Run-Ask {
  Assert-TutorEnabled
  $question = ($Rest -join " ").Trim()
  if (-not $question) {
    throw "Usage: .\codex-iris\tutor.ps1 ask `"your question`""
  }
  $config = Read-TutorConfig
  if (-not $config) {
    throw "Tutor is not initialized. Run .\codex-iris\tutor.ps1 init first."
  }
  Enable-NodeProxy
  $oldPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $raw = Invoke-NotebookApi @("ask", ([string]$config.notebook_id), $question)
    $code = $script:NotebookApiExitCode
  } finally {
    $ErrorActionPreference = $oldPreference
  }
  $data = Convert-JsonFromMixedOutput $raw
  if ($code -ne 0 -or -not $data.ok) {
    Write-Output "NotebookLM ask failed: $($data.error)"
    if ($data.rpcId) {
      Write-Output "rpcId: $($data.rpcId)"
    }
    Write-Output "Common cause: the selected notebook has no sources yet, or NotebookLM rejected the chat endpoint for this notebook."
    exit 1
  }
  Write-Output $data.answer
  if ($data.references -and $data.references.Count -gt 0) {
    Write-Output ""
    Write-Output "References:"
    $data.references | ConvertTo-Json -Depth 8
  }
}

function Run-Detail {
  Assert-TutorEnabled
  $config = Read-TutorConfig
  if (-not $config) {
    throw "Tutor is not initialized. Run .\codex-iris\tutor.ps1 init first."
  }
  $oldPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $raw = Invoke-NotebookApi @("detail", ([string]$config.notebook_id))
    $code = $script:NotebookApiExitCode
  } finally {
    $ErrorActionPreference = $oldPreference
  }
  $data = Convert-JsonFromMixedOutput $raw
  if ($code -ne 0 -or -not $data.ok) {
    Write-Output "NotebookLM detail failed: $($data.error)"
    exit 1
  }
  $data.notebook | ConvertTo-Json -Depth 8
}

switch ($Command.ToLowerInvariant()) {
  "doctor" { Run-Doctor }
  "login" {
    Assert-TutorEnabled
    if (-not (Test-Path -LiteralPath $NotebookManualLoginScript)) {
      throw "NotebookLM manual login helper not found: $NotebookManualLoginScript"
    }
    $loginArgs = @()
    $config = Read-TutorConfig
    if ($config -and $config.notebook_id) {
      $loginArgs += "--notebook-id"
      $loginArgs += [string]$config.notebook_id
    }
    Enable-ProxyEnv | Out-Null
    $oldNodeOptions = $env:NODE_OPTIONS
    $env:NODE_OPTIONS = ""
    try {
      & node $NotebookManualLoginScript @loginArgs
    } finally {
      $env:NODE_OPTIONS = $oldNodeOptions
    }
    Run-Doctor
  }
  "list" {
    $items = Get-NotebookList
    $items | Format-Table Id, Title -AutoSize
  }
  "init" { Run-Init }
  "notebook" {
    $config = Read-TutorConfig
    if (-not $config) { throw "Tutor is not initialized. Run init first." }
    $selected = Select-Notebook
    $config.notebook_id = $selected.Id
    $config.notebook_title = $selected.Title
    $config.updated_at = (Get-Date).ToString("o")
    Save-TutorConfig $config
    Render-TutorFiles $config
  }
  "role" {
    $config = Read-TutorConfig
    if (-not $config) { throw "Tutor is not initialized. Run init first." }
    $newRole = if ($Role) { $Role } else { Select-Role }
    if ($RoleChoices -notcontains $newRole) {
      throw "Unknown role '$newRole'. Valid roles: $($RoleChoices -join ', ')"
    }
    $config.role = $newRole
    $config.updated_at = (Get-Date).ToString("o")
    Save-TutorConfig $config
    Render-TutorFiles $config
  }
  "ask" { Run-Ask }
  "detail" { Run-Detail }
  "config" {
    $config = Read-TutorConfig
    if ($config) { $config | ConvertTo-Json -Depth 8 } else { Write-Output "No config found." }
  }
  default {
    Write-Output "Usage:"
    Write-Output "  .\codex-iris\tutor.ps1 doctor"
    Write-Output "  .\codex-iris\tutor.ps1 login"
    Write-Output "  .\codex-iris\tutor.ps1 list"
    Write-Output "  .\codex-iris\tutor.ps1 init"
    Write-Output "  .\codex-iris\tutor.ps1 init -NotebookId <id> -NotebookTitle <title> -Role general"
    Write-Output "  .\codex-iris\tutor.ps1 detail"
    Write-Output "  .\codex-iris\tutor.ps1 ask `"question`""
    exit 2
  }
}

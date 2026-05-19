# Codex Tutor

This is the Codex adaptation of claude-iris `/tutor`.

It binds the current project to a read-only NotebookLM notebook and writes
`AGENTS.md`/`CLAUDE.md` so future Codex sessions know to query NotebookLM before
making domain-specific claims.

## Commands

Run from the project root:

```powershell
.\codex-iris\tutor.ps1 doctor
.\codex-iris\tutor.ps1 login
.\codex-iris\tutor.ps1 list
.\codex-iris\tutor.ps1 init
.\codex-iris\tutor.ps1 ask "your question"
```

`login` opens a Google sign-in browser window. The user must complete that step.

## Roles

- `general`
- `research-advisor`
- `exam-reviewer`
- `socratic`
- `librarian`

To initialize non-interactively after you know the notebook id:

```powershell
.\codex-iris\tutor.ps1 init -NotebookId "<id>" -NotebookTitle "<title>" -Role general
```

## Contract

NotebookLM is read-only. Codex can restructure, explain, calculate, write code,
and format answers, but every domain fact must come from NotebookLM and preserve
NotebookLM citation markers such as `[1][2]`.

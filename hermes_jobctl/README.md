# Hermes plugin: jobctl

Declarative Hermes cron jobs from Markdown files: YAML **front matter** for metadata and a Markdown **body** as the Hermes agent prompt—think apply/delete/status for cron specs.

## Requirements

- Hermes Agent

---

## Installation

> Note: there is currently an upstream bug in Hermes CLI plugin command registration (`register_cli_command` wiring). See [NousResearch/hermes-agent#13643](https://github.com/NousResearch/hermes-agent/pull/13643).  
> Until the official fix lands, prefer the standalone `hermes-jobctl` CLI for reliable usage. See [mikewei/hermes-jobctl](https://github.com/mikewei/hermes-jobctl).  
> For now if you really want to use it by plugin, just prompt `fix hermes-agent issue #13643 for me` in your hermes chat.  

Install this plugin from Hermes registry:

```bash
hermes plugins install mikewei/hermes-plugin-jobctl
```

Or copy the repo directory to ~/.hermes/plugins manually and enable it.

---

## Quick Start


```bash
# Scaffold a spec next to cwd
hermes jobctl new nightly-report --schedule "every 24h" --dir .

# Edit nightly-report.md: set YAML header and write the Markdown prompt body

# Push spec to Hermes cron
hermes jobctl apply ./nightly-report.md

# See sync state vs jobs.json
hermes jobctl status ./nightly-report.md
```

Notes:

- You can pass **multiple** paths; each argument may be a `.md` file or a directory (every `*.md` in that directory, non-recursive).
- See **`Spec format`** at the bottom of **`hermes jobctl --help`** for the full field list.

---

## Front matter (YAML header)

Everything between the first `---` and the closing `---` is YAML. **Do not put the Hermes prompt in YAML**—put it below the closing `---` as Markdown.

| Field | Required | Description |
|-------|----------|-------------|
| `type` | yes | Task kind. Only **`hermes-cron`** is supported today (reserved for future kinds). |
| `schedule` | yes | Hermes cron schedule string (e.g. `30m`, `every 2h`, `0 9 * * *`). |
| `name` | no | Job name; default: filename without `.md`. |
| `deliver` | no | Passed to Hermes `--deliver`; omit for default. |
| `repeat` | no | Integer; omit or ≤0 → unlimited per Hermes rules. |
| `skills` | no | List or single string → multiple `--skill`. |
| `script` | no | Maps to `--script`. |
| `workdir` | no | Maps to `--workdir` (often absolute). |
| `suspend` | no | If true, apply then pause job to match (default false). |

Any other YAML keys are **ignored** (not forwarded to Hermes).

---

## Example spec file

```markdown
---
type: hermes-cron
schedule: "every 24h"
deliver: local
suspend: false
---

Example scheduled task for Hermes cron. Copy and edit as needed.

- Summarize open todos in three short sections.
- If anything is blocked, call it out in one line.

(No `skills` in this sample; add `skills: [your-skill]` in the YAML header if you need them.)
```

---

## Commands

| Command | Purpose |
|---------|---------|
| `apply PATHS…` | Create or update jobs from `.md` files and/or directories (non‑recursive `*.md` each). |
| `delete PATHS…` \| `delete --name NAME` | Remove a job by spec path(s) or by job name. |
| `status PATHS…` | Compare specs to `jobs.json` (sync / pending_apply / missing, etc.). |
| `get` | List jobs in `jobs.json` (optional `--name`, `--json`). |
| `new [TASK]` | Scaffold a spec: blank template (`--schedule`, default `every 24h`) or export from an existing job (`--from-job <id>`). Optional `TASK` with `--from-job` (defaults to job name). Also `--dir` / `-o/--output`, `--stdout`, `--force`. |

Common flags: `-p/--profile`, `--hermes-bin`, `-v/--verbose`; `apply` / `delete` also support `--accept-hooks`.

```bash
hermes jobctl apply ./examples/sample-cron-task.md
hermes jobctl status ./examples/
hermes jobctl delete ./examples/sample-cron-task.md
hermes jobctl delete --name my-job
hermes jobctl new my-task --schedule "every 24h"
hermes jobctl get -v
hermes jobctl new --from-job abc123
hermes jobctl new my-copy --from-job abc123 -o ./tasks/my-copy.md
```

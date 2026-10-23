# Starter assistant templates

Templates are starting configurations, not finished integrations or guarantees that a bot can complete every task. They create a bot with its own instructions, tools, policy rules and optional schedule. `hutch bot templates` and the web app show the same catalogue.

Templates contain task instructions, tool permissions and policy rules; they do not fabricate a model, run, transcript, result or schedule. Choose a configured local or hosted model route when creating the bot. Hutch refuses to start until a real route is selected and available.

Templates marked **needs a folder** expect files that you choose. Give the bot a working folder when you create it, or set one afterward. Without one, its private workspace starts empty. Review the template's input, outputs, schedule, tools and policy before connecting it to real data.

Templates that draft messages, replies or documents have no sending, posting or publishing tool. A person reviews and sends the result. The OpenCode assistant runtime may use its own tools after Hutch approval; those approved actions run with your OS authority, outside the built-in shell sandbox.

## The roster

| Template | Owns | Inputs | Deliverable | Tools |
|---|---|---|---|---|
| **personal-assistant** | Everyday requests, plans and review-ready drafts | The request and approved memory | A direct answer, plan or draft | files, memory |
| **day-planner** | Turning tasks and constraints into a realistic day | The request or a note | A prioritized plan with dependencies | files, memory |
| **inbox-followups** | Finding commitments and preparing replies | `inbox/*.md` or `inbox-notes.md` | `follow-ups.md` and `drafts/` | files, memory |
| **research-decisions** | A sourced decision brief | `question.md` or the request | `decision-brief.md` | web_fetch, files, memory |
| **project-coordinator** | Project status, blockers and next actions | Project notes and git history | `project-status.md` | shell (read-only rules), files, memory |
| **meeting-followthrough** | Owners, decisions and actions from meeting notes | `meetings/*.md` or `*.txt` | `actions.md` | files, memory |
| **document-workbench** | A finished document from notes and data | Source notes, CSV or existing documents | DOCX or Markdown plus a source note | files, documents, memory |
| **data-brief** | A checkable profile of a spreadsheet | CSV or Excel files | `data-brief.md` | shell (downloads/deletes denied), files, memory |

## Add a recurring task deliberately

No template starts with a schedule. After a successful task, add a schedule in the assistant's settings and choose the time zone explicitly. A schedule repeats the saved instructions; it does not grant new tools, accounts or destinations. Missed windows follow the assistant's catch-up policy.

## Create from the CLI

```bash
hutch bot create my-assistant --template personal-assistant --model opencode/anthropic/claude-haiku-5-5
hutch bot create project-status --template project-coordinator --workdir ~/code/my-project --model openai/gpt-5.4
hutch bot create inbox --template inbox-followups --workdir ~/Documents/inbox --model openrouter/anthropic/claude-sonnet-4.6
```

The model must be a real configured route. For an OpenCode assistant, use `opencode/<provider>/<model>` and connect the provider in Hutch's private OpenCode profile first.

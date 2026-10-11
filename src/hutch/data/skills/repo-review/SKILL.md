---
name: repo-review
description: Read-only review of a Git repository in the workspace. Use when the user asks what changed recently, wants a code review without edits, or asks for repository health before other work. Never commits, pushes or edits.
license: MIT
compatibility: Requires the shell tool and git. Read-only commands only; the workspace must be a Git repository.
metadata:
  hutch.version: "1.0"
  hutch.requires-tools: "shell, files"
---

# Read-only repository review

Inspect a Git repository and report what you find. This skill never mutates the repository: no
commits, no pushes, no resets, no file edits. If the user asks for a change, say that this skill
only reviews and let them request the change separately.

## Steps

1. Confirm the workspace is a Git repository: run `git rev-parse --show-toplevel`. If it fails,
   report that this folder is not a repository and stop.
2. Get the shape of the repository, in this order:
   - `git status --short --branch` for the current branch and working-tree state.
   - `git log --oneline -15` for recent history.
   - `git diff --stat` for uncommitted changes.
3. Read the changed files that matter with `read_file` before commenting on them. Quote exact
   file paths and line references where possible.
4. If a diff is large, sample it per file with `git diff -- <path>` and say which files you did
   not review in full.

## Output format

- **Repository**: path, branch, working-tree state (clean/dirty).
- **Recent work**: 3–6 bullets from history and diffs, newest first.
- **Findings**: correctness, safety or maintainability observations, each tied to a file and
  labelled `question`, `risk` or `nits`.
- **Suggestions**: at most three concrete follow-ups. Do not perform them.

## Boundaries

- Only read-only git commands: `status`, `log`, `diff`, `show`, `branch`, `rev-parse`.
- Never run commands that write: `commit`, `push`, `reset`, `checkout`, `clean`, `stash`, `add`.
- Do not modify any file, including the review notes: put the review in your reply only.

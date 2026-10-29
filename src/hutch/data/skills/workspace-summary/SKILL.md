---
name: workspace-summary
description: Summarize what is in a Bot's workspace folder. Use when the user asks what a folder contains, wants an inventory of files, or asks for a plain-language digest of a directory before another task.
license: MIT
compatibility: Requires the files tool (read_file, list_files). Reads only; no network access.
metadata:
  hutch.version: "1.0"
  hutch.requires-tools: "files"
---

# Workspace summary

Turn a working folder into a short, accurate digest a person can act on. This skill reads only.

## Steps

1. Use `list_files` to enumerate the workspace. Do not assume the folder is empty because the
   first listing looks short; check the path you were given.
2. Identify the kinds of files present (documents, spreadsheets, images, code, archives, other).
   When a name does not reveal the type, read the first part of the file with `read_file` instead
   of guessing.
3. Read the two or three files that look most important in full. Prefer recent, clearly named
   files over hidden or system files.
4. Write the digest with `write_file` to `summary.md` in the workspace, then reply with the same
   digest text.

## Output format

- **Folder**: one line with the path and total file count.
- **Contents**: 3–8 bullets grouped by kind, each naming concrete files.
- **Notable**: anything surprising, very large files, duplicates, files that look misplaced, or
  dates that are clearly stale.
- **Not read**: list files you deliberately skipped and why.

## Edge cases

- An empty workspace is a valid answer: say it is empty rather than inventing contents.
- If the workspace holds many near-identical files, summarize the pattern and give one example
  instead of listing every file.
- Never include file contents that look like credentials, keys or personal data in the summary;
  note that such a file exists and stop.

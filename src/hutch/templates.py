"""Starter bot templates: the gallery behind `hutch bot create --template`, the dashboard and the API.

Two products set the bar: Grok Team Bots ship role templates (sales, PM, marketing, data analytics) and Dots are pitched as
coworkers for everyday jobs. Hutch's templates are the same idea, built from what Hutch really has: a working folder of
yours, web fetch, memory, a policy-gated shell, and no way to send anything on its own. That last point is deliberate and is
stated on every template that touches people (sales, support): they *draft*, a person sends.

Templates describe a bot's task and tools. They do not choose or simulate a model: select a real configured route when
creating the bot. Templates that read files say so: a bot with no working folder starts with an empty workspace.

``TEMPLATES`` (name -> Bot) is what the rest of the code uses; ``TEMPLATE_INFO`` adds what a gallery needs to show.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import ApprovalMode, Bot, CommandRule, RiskTier, Schedule


@dataclass(frozen=True)
class TemplateInfo:
    key: str
    category: str
    tagline: str
    reads: str                    # what it expects to find (and where)
    produces: str                 # what it leaves behind
    safety: str                   # one honest line about what it can and cannot do
    needs_folder: bool            # reads files you provide: give it a working folder
    bot: Bot


def _rules(*pairs: tuple[str, str]) -> list[CommandRule]:
    return [CommandRule(verdict=v, match=m) for v, m in pairs]


_NO_MUTATION = _rules(("deny", "git push*"), ("deny", "git commit*"), ("deny", "git reset*"), ("deny", "rm *"),
                      ("deny", "mv *"))

_T: list[TemplateInfo] = []


def _add(key: str, category: str, tagline: str, reads: str, produces: str, safety: str, needs_folder: bool, **bot) -> None:
    bot.setdefault("model", "")
    bot.setdefault("description", tagline)
    _T.append(TemplateInfo(key, category, tagline, reads, produces, safety, needs_folder,
                           Bot(name=key, template=key, **bot)))


# ----------------------------------------------------------------------------- the original three

_add("research-briefing", "Research", "Weekly research briefing on topics you pick",
     "the topics written into its instructions; the public web", "report.md with 5-8 sourced bullets",
     "Reads public pages only. Cannot send anything; cannot run commands.", False,
     instructions=(
         "Search the public web for developments since the last briefing on the topics below, "
         "then write report.md: 5-8 bullets, each with a source URL. Save a memory note listing "
         "the URLs you already covered so the next briefing only adds what's new.\n"
         "Topics: replace this line with your topics."),
     tools=["web_fetch", "files", "memory"], schedule=Schedule(cron="0 9 * * 1", timezone="UTC"), preset="research")

_add("repo-sweeper", "Engineering", "Sweep a git repo for TODOs and stale code, on demand",
     "a copy of a git repository (set it as the working folder)", "findings.md with file:line references and a suggested fix each",
     "Reports only: commits, pushes, resets, deletes and moves are denied by rule.", True,
     instructions=(
         "You run inside a copy of a git repository. Find TODO/FIXME/HACK comments and obviously "
         "stale code paths; write findings.md with file:line references and a suggested fix for "
         "each. Do NOT modify source files - reports only."),
     tools=["shell", "files", "memory"], command_rules=_NO_MUTATION, preset="coding")

_add("tidy-downloads", "Personal", "Sort a messy folder into tidy ones, with approval before each move",
     "the folder you point it at, for example ~/Downloads", "the same folder, sorted into docs / images / installers / archives / other",
     "Every move asks first (that is intentional); nothing leaves the folder; deletes are never proposed.", True,
     instructions=(
         "List the files in the working folder, propose a simple folder structure (docs/images/installers/"
         "archives/other), and move files into it. Every move needs the operator's approval - "
         "that is intentional; batch your proposals so one approval covers a group. Never delete anything."),
     tools=["files", "shell", "memory"], approval_mode=ApprovalMode.ask, preset="router")

# ------------------------------------------------------------------------------------ role templates

_add("sales-prospector", "Sales", "Research each prospect on your list and write a one-page brief",
     "prospects.txt: one company or person per line, optionally followed by a note",
     "briefs/<name>.md per prospect, and prospects-summary.md ranking them",
     "Reads public pages only and has no way to email, message or post: it drafts the brief, you do the outreach.", True,
     instructions=(
         "You prepare sales research. Read prospects.txt in the working folder: one prospect per line, optionally followed by "
         "a note about why they matter.\n"
         "For each prospect that has no brief yet (check the memory and the briefs/ folder), fetch their public website and "
         "one or two recent news pages, then write briefs/<name>.md with: what they do in two sentences; size and growth "
         "signals; recent news with the URL of each item; two specific talking points tied to the user's note; and a "
         "'what I could not verify' list. Never state a fact you did not read on a page you fetched; cite the URL.\n"
         "Finish with prospects-summary.md: a table of every prospect, one line each, ranked by how promising the evidence is, "
         "and why. Remember which prospects are done. You cannot contact anyone and must not suggest that you did."),
     tools=["web_fetch", "files", "memory"], preset="research")

_add("pm-standup-digest", "Product", "A weekday digest of what shipped, what is in flight and what is blocked",
     "the git history of the working folder and any notes/*.md files", "digest-YYYY-MM-DD.md",
     "Read-only shell: commits, pushes, deletes and moves are denied by rule.", True,
     instructions=(
         "You write the team's daily stand-up digest. In the working folder, read `git log --since='1 day ago' --stat` (use "
         "'3 days ago' on Mondays) and any notes in notes/*.md that changed recently.\n"
         "Write digest-<today's date>.md with four sections: Done (merged or finished work, one line each, naming the author), "
         "In progress (branches and notes that show active work), Blocked (anything notes or commits describe as waiting, "
         "failing or stuck), and Asks (questions someone left for someone else). Quote commit subjects exactly; do not invent "
         "status. If there was no activity, say so in one line."),
     tools=["shell", "files", "memory"], command_rules=_NO_MUTATION,
     schedule=Schedule(cron="0 9 * * 1-5", timezone="UTC"), preset="extraction")

_add("competitor-watch", "Marketing", "Watch competitor pages and report what actually changed",
     "competitors.txt: one URL per line (pricing, features or changelog pages)", "changes-YYYY-MM-DD.md",
     "Reads public pages only; cannot send anything.", True,
     instructions=(
         "You monitor competitor pages. Read competitors.txt in the working folder: one URL per line.\n"
         "For each URL, fetch the page and compare it with what you remembered last time (the memory holds a short summary and "
         "the notable facts per URL: headline, prices, plan names, feature lists). Report only MEANINGFUL changes: a price or "
         "plan change, a new or removed feature, a changed headline or positioning claim, a new customer logo. Ignore dates, "
         "cookie banners, counters and layout noise.\n"
         "Write changes-<today's date>.md: for each change, the URL, what it said before, what it says now (quote both), and "
         "why it might matter. If nothing meaningful changed, write a single line saying so. Then update the memory with the "
         "current summary for each URL."),
     tools=["web_fetch", "files", "memory"], schedule=Schedule(cron="0 8 * * 1", timezone="UTC"), preset="research")

_add("data-reporter", "Analytics", "Profile a folder of CSV files and write a report you can check",
     "the CSV files in the working folder", "report.md with the commands used and the numbers they produced",
     "Runs only local commands; curl and wget are denied; other changes ask first.", True,
     instructions=(
         "You are a careful data analyst. In the working folder there are CSV files. For each one, use shell tools (head, wc, "
         "cut, sort, uniq, awk, python3) to find: row count, column names and likely types, how many values are empty per "
         "column, the most common values of text columns, min/max/mean of numeric columns, and anything that looks wrong "
         "(duplicate rows, impossible values, mixed formats).\n"
         "Write report.md with one section per file. Under every number put the exact command that produced it, so a reader "
         "can rerun it. Do not report a number you did not compute. End with 'questions to ask the data owner'. You may not "
         "download anything."),
     tools=["shell", "files", "memory"], command_rules=_rules(("deny", "curl*"), ("deny", "wget*"), ("deny", "rm *")), preset="coding")

_add("support-triage", "Support", "Sort incoming tickets by urgency and draft a reply for each",
     "tickets/*.txt: one ticket per file", "triage.md (sorted by urgency) and drafts/<ticket>.md",
     "Drafts only: it has no way to send a reply. A person reads and sends every one.", True,
     instructions=(
         "You triage customer support tickets. Each file in tickets/ is one ticket. For each ticket not yet in the memory:\n"
         "1. Classify it: category (bug, billing, how-to, feature request, account, other), urgency P1 (service down or money "
         "lost) / P2 (blocked, workaround exists) / P3 (question or request), and the customer's mood (calm, frustrated, angry).\n"
         "2. Write drafts/<ticket-file>.md: a reply in a warm, plain tone that answers what was asked, says what you do not "
         "know instead of guessing, and never promises refunds, dates or fixes.\n"
         "Then write triage.md: a table sorted P1 first with ticket, category, mood and a one-line summary, plus a short list "
         "of problems that appear in more than one ticket. Remember each ticket you handled. You cannot send anything."),
     tools=["files", "memory"], preset="extraction")

_add("meeting-actions", "Operations", "Turn meeting notes into owners, decisions and open questions",
     "meetings/*.md or *.txt: one file per meeting", "actions.md with a table of actions plus decisions and open questions",
     "Reads and writes files in its folder only; cannot send anything.", True,
     instructions=(
         "You turn meeting notes into follow-through. Read every file in meetings/ that is not yet in the memory.\n"
         "Write actions.md with three sections. Actions: a table of Owner, Action, Due and Source (file and the line it came "
         "from). Take only what the notes say; if an owner or date is implied rather than stated, write it and mark it "
         "'(inferred)'. Decisions: what was decided, one line each. Open questions: anything raised and not answered. If the "
         "notes do not say who owns something, write 'unassigned' rather than choosing someone. Remember each file handled."),
     tools=["files", "memory"], preset="extraction")

_add("page-change-monitor", "Monitoring", "Watch one page and tell you only when something that matters changes",
     "watch.txt: the URL on the first line, and on the next lines what counts as a change worth knowing",
     "changes.md (appended), and a one-line 'no change' answer otherwise",
     "Reads one public page; cannot send anything. Run it on a schedule to be told on the next run.", True,
     instructions=(
         "You watch a web page for the user. Read watch.txt in the working folder: the first line is the URL, the following "
         "lines say what counts as a change worth knowing about.\n"
         "Fetch the page. Compare it with the summary and key facts in the memory from the last run. If nothing the user "
         "cares about changed, do not write a file; answer in one line: 'No change since <date>'. If something changed, append "
         "an entry to changes.md with the date, what it said before, what it says now (quote both), and the URL. Always update "
         "the memory with the current summary. Never report a change you cannot quote from the page."),
     tools=["web_fetch", "files", "memory"], schedule=Schedule(cron="0 8 * * *", timezone="UTC"), preset="router")

_add("release-notes", "Engineering", "Draft release notes from the commits since the last tag",
     "the git history of the working folder", "RELEASE_NOTES.md draft grouped into Added, Fixed and Changed",
     "Read-only shell: it cannot commit, push, tag, delete or move anything.", True,
     instructions=(
         "You draft release notes. In the working folder find the latest tag (`git describe --tags --abbrev=0`; if there is "
         "none, use the whole history) and read `git log <tag>..HEAD --pretty=format:'%h %s'`.\n"
         "Write RELEASE_NOTES.md with sections Added, Fixed and Changed, plus Breaking if any commit says so. One line per "
         "user-visible change in plain language, with the short commit hash. Leave out merges, refactors and CI-only changes; "
         "say how many you left out. Do not invent changes the commits do not show."),
     tools=["shell", "files"], command_rules=_NO_MUTATION + _rules(("deny", "git tag*")), preset="coding")

_add("weekly-review", "Personal", "Look back over a week of your own files and write a short review",
     "the working folder: what was created or changed in the last 7 days", "weekly-review.md",
     "Reads and writes inside the folder only; cannot send anything.", True,
     instructions=(
         "You help the user review their week. In the working folder find what changed in the last 7 days (`find . -mtime -7 "
         "-type f`) and read the notes among them.\n"
         "Write weekly-review.md: what was worked on (grouped by theme, with file names), what was finished, what looks "
         "started but dropped, and three questions the user could ask themselves for next week. Stay grounded in the files; "
         "say 'not enough to tell' rather than guessing."),
     tools=["shell", "files", "memory"], command_rules=_rules(("deny", "rm *"), ("deny", "mv *")),
     risk_tier=RiskTier.supervised, schedule=Schedule(cron="0 17 * * 5", timezone="UTC"), preset="extraction")


#: name -> everything a gallery shows
TEMPLATE_INFO: dict[str, TemplateInfo] = {t.key: t for t in _T}

#: name -> a ready-to-copy Bot (what the CLI, API and dashboard create from)
TEMPLATES: dict[str, Bot] = {t.key: t.bot for t in _T}

CATEGORIES = ["Research", "Sales", "Product", "Marketing", "Analytics", "Support", "Operations", "Monitoring",
              "Engineering", "Personal"]


def gallery() -> list[tuple[str, list[TemplateInfo]]]:
    """Templates grouped by category, in a stable order."""
    out = []
    for cat in CATEGORIES:
        items = [t for t in _T if t.category == cat]
        if items:
            out.append((cat, items))
    return out

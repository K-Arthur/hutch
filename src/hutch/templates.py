"""Starter assistant templates: a small, practical roster for everyday work.

The catalogue follows the pattern the reference products recommend: a small
number of durable assistants that own a repeatable outcome, not a pile of
demo personas. Every template describes a real input, a real deliverable and
the tools it actually has. None chooses a model, starts a schedule, sends a
message, or fabricates a result.

Templates that read files require a working folder. A folderless template
starts with an empty private workspace and works from the conversation.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Bot, CommandRule


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


_NO_MUTATION = _rules(("deny", "git push*"), ("deny", "git commit*"), ("deny", "git reset*"),
                      ("deny", "rm *"), ("deny", "mv *"))


_T: list[TemplateInfo] = []


def _add(key: str, category: str, tagline: str, reads: str, produces: str, safety: str,
         needs_folder: bool, **bot) -> None:
    bot.setdefault("model", "")
    bot.setdefault("description", tagline)
    _T.append(TemplateInfo(key, category, tagline, reads, produces, safety, needs_folder,
                           Bot(name=key, template=key, **bot)))


# ------------------------------------------------------------------ everyday work

_add("personal-assistant", "Personal", "Keeps everyday requests moving and remembers what matters",
     "the request in chat; approved memory from earlier conversations",
     "a direct answer, a plan, or a review-ready draft",
     "Drafts only when a message or document is involved. It cannot send, post or contact anyone.",
     False,
     instructions=(
         "You are the person's everyday assistant. Start by identifying the outcome they want, then do the "
         "smallest useful piece of work that moves it forward. Ask one focused question only when a missing "
         "detail would change the answer. When the request involves a message, document, plan or decision, "
         "produce a review-ready draft and label assumptions and unknowns. Use approved memory when it is "
         "relevant, but never invent a fact, commitment or completed action. You cannot send, post, submit "
         "or contact anyone; say that the person must review and send anything outward."),
     tools=["files", "memory"], preset="router")

_add("day-planner", "Personal", "Turns a messy list into a realistic plan for the day",
     "the tasks, deadlines and constraints in the request or an attached note",
     "a prioritized plan with time blocks, dependencies and follow-ups",
     "No calendar writes. It plans from what you provide and never claims an event was created.",
     False,
     instructions=(
         "You build a realistic plan from the person's tasks, deadlines, energy and fixed commitments. "
         "First separate must-do work from optional work, then place the must-do items into a sequence that "
         "fits the available time. Name dependencies, estimate effort, and keep buffer time. If a deadline "
         "or duration is missing, state the assumption instead of inventing one. End with the three things "
         "that would make the plan fail and one question the person should answer. You cannot change a "
         "calendar or send the plan anywhere."),
     tools=["files", "memory"], preset="planner")

_add("inbox-followups", "Personal", "Finds commitments and prepares replies you can review",
     "inbox/*.md or inbox-notes.md in the working folder: one message or thread per file",
     "follow-ups.md with commitments, owners and dates, plus drafts/<thread>.md replies",
     "Drafts only. It has no mail, message or posting tool and cannot send anything.",
     True,
     instructions=(
         "You review exported messages in inbox/ or inbox-notes.md. For each thread, extract every promise, "
         "request and deadline with the person who owns it. Distinguish what the sender asked for from what "
         "the person already agreed to. Write follow-ups.md with columns: thread, commitment, owner, due date, "
         "source, and status. Then write drafts/<thread>.md with a concise reply the person can edit. Never "
         "invent a date, price, approval or attachment. If the export does not show something, write "
         "'not stated'. You cannot send, post or contact anyone; every draft requires the person to send it."),
     tools=["files", "memory"], preset="extraction")

# ------------------------------------------------------------------------ research

_add("research-decisions", "Research", "Researches a decision and separates evidence from opinion",
     "question.md in the working folder, or the decision and constraints in the request",
     "decision-brief.md with sourced options, tradeoffs, a recommendation and open questions",
     "Reads public pages only. It cannot buy, subscribe, contact a vendor or make the decision for you.",
     True,
     instructions=(
         "You prepare a decision brief. Read question.md or the request and restate the decision, the "
         "constraints and what would make an option unacceptable. Fetch public sources and record the URL, "
         "publication date and the exact claim each source supports. Compare at least two viable options in "
         "a table: cost, effort, risk, reversibility and evidence quality. Separate facts from your judgment. "
         "Recommend one option only when the evidence supports it; otherwise say what is still unknown. End "
         "with the smallest test that would resolve the biggest uncertainty. Never present a search snippet "
         "as if you read the page, and never contact anyone or buy anything."),
     tools=["web_fetch", "files", "memory"], preset="research")

# ---------------------------------------------------------------------- operations

_add("project-coordinator", "Operations", "Keeps a project's status, blockers and next actions current",
     "the working folder: project notes, decisions and git history",
     "project-status.md with done, in progress, blocked, owner and next action",
     "Read-only shell: commits, pushes, resets, deletes and moves are denied by rule.",
     True,
     instructions=(
         "You maintain a factual project status. Read the recent notes and `git log --since='7 days ago' "
         "--stat`, then write project-status.md with four sections: Done (what actually changed), In progress "
         "(active work and its owner), Blocked (what is waiting, on whom, and for how long), and Next actions "
         "(one owner and one next step each). Quote commit subjects and note lines exactly; do not infer "
         "progress from a branch name alone. If two sources disagree, record both and flag the conflict. "
         "You may inspect the repository but must not commit, push, reset, delete or move anything."),
     tools=["shell", "files", "memory"], command_rules=_NO_MUTATION, preset="coding")

_add("meeting-followthrough", "Operations", "Turns meeting notes into owners, decisions and actions",
     "meetings/*.md or *.txt: one file per meeting",
     "actions.md with an action table, decisions and unresolved questions",
     "Reads and writes files in its folder only; it cannot send anything.",
     True,
     instructions=(
         "You turn meeting notes into follow-through. Read each file in meetings/ that is not already in "
         "memory. Write actions.md with three sections. Actions: Owner, Action, Due and Source (file and line). "
         "Decisions: what was decided, one line each. Open questions: anything raised and not answered. Use "
         "only what the notes say; if an owner or date is implied, mark it '(inferred)'. If no owner is named, "
         "write 'unassigned' rather than choosing someone. Flag contradictions between notes. Remember each "
         "file handled. You cannot send, assign work in another system or change a calendar."),
     tools=["files", "memory"], preset="extraction")

# ----------------------------------------------------------------------- documents

_add("document-workbench", "Documents", "Turns notes and data into a finished document you can review",
     "source notes, CSV files or existing documents in the working folder",
     "a DOCX or Markdown deliverable plus a short source-and-assumptions note",
     "Writes only in its workspace. It cannot send, publish or upload the document.",
     True,
     instructions=(
         "You produce a finished document from the files in the working folder. First list the sources you "
         "actually read and the questions the document must answer. Build an outline, then write the document "
         "with clear headings, short paragraphs and tables where they help. Cite the source file for each "
         "material fact. Put unresolved questions and assumptions in a final section rather than hiding them. "
         "Use the document tools for DOCX output when the person asks for a document; otherwise write Markdown. "
         "You cannot send, publish or upload the result; the person must review and deliver it."),
     tools=["files", "documents", "memory"], preset="extraction")

_add("data-brief", "Analytics", "Profiles a spreadsheet and writes a checkable brief",
     "CSV or Excel files in the working folder",
     "data-brief.md with row counts, column profiles, anomalies, commands used and questions for the owner",
     "Runs local commands only; curl and wget are denied; deletes are denied.",
     True,
     instructions=(
         "You are a careful data analyst. For each CSV or Excel file in the working folder, compute row count, "
         "column names and types, empty values, common values for text columns, and min/max/mean for numeric "
         "columns. Look for duplicate rows, impossible values and mixed formats. Write data-brief.md with one "
         "section per file and put the exact command or tool call under every number so a reader can rerun it. "
         "Do not report a number you did not compute. End with questions for the data owner and a short list "
         "of what the data cannot answer. You may not download anything or delete files."),
     tools=["shell", "files", "memory"],
     command_rules=_rules(("deny", "curl*"), ("deny", "wget*"), ("deny", "rm *")), preset="coding")


#: name -> everything a gallery shows
TEMPLATE_INFO: dict[str, TemplateInfo] = {t.key: t for t in _T}

#: name -> a ready-to-copy Bot (what the CLI, API and dashboard create from)
TEMPLATES: dict[str, Bot] = {t.key: t.bot for t in _T}

CATEGORIES = ["Personal", "Research", "Operations", "Documents", "Analytics"]


def instantiate(key: str, name: str) -> Bot:
    """Create a fresh Bot from a template with its own identity.

    ``TEMPLATES`` entries are process-wide singletons; every copy must receive a new immutable
    Bot ID, or a second Bot created from the same template collides with the first.
    """
    from .models import new_id
    bot = TEMPLATES[key].model_copy(deep=True)
    bot.id = new_id("bot")
    bot.name, bot.template = name, key
    return bot


def gallery() -> list[tuple[str, list[TemplateInfo]]]:
    """Templates grouped by category, in a stable order."""
    out = []
    for cat in CATEGORIES:
        items = [t for t in _T if t.category == cat]
        if items:
            out.append((cat, items))
    return out

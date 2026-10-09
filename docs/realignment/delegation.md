# Bounded task delegation (experimental)

Hutch exposes one opt-in `delegate_task` tool for independent, text-only subtasks. It runs a child attempt under the same bot's
captured permissions. This is a narrow preview for Linux hosts; it is not a general multi-bot planner or shared-workspace system.

## Requirements and setup

Delegation requires the built-in runtime, a supported local inference route in **Strict Offline** mode, verified Linux bubblewrap
network/PID containment, the supervised process executor, and enough global run slots. The default global limit of two supports a
root plus one child. A nested child needs a third slot; deeper nesting is refused when the ancestry cannot fit under the configured
global limit. Strict Offline removes browser and public-page tools and requires contained shell when shell is enabled.

Enable it only for a bot whose local route and permissions are appropriate:

```sh
hutch bot update local-worker --inference-mode offline --sandbox strict --tools files,delegate_task
```

The Settings form exposes the same explicit tool opt-in. Enabling the tool does not start work. Every delegation request creates
an outward approval, even when the bot's normal approval mode is `auto`; a denial or expired request creates no child.

## What is shared

The child receives only the task string supplied to `delegate_task`. It does not receive prior user/assistant messages, parent
tool output, parent workspace files, browser state, or reference memory. Its credential-free capability snapshot is inherited
from the root run and cannot be widened by later bot edits. Browser and memory tools are removed. Each child gets a private
per-run workspace, and its process uses the same Strict Offline broker and shell containment requirements.

The child run is attached to the parent's conversation for operator visibility. Its transcript, approval prompts and verified
file snapshots stay attributed to the child run. The parent model receives only the child's final text result. Hutch does not copy
child files into the parent's workspace or prompt; the operator can inspect the child run's files in Studio. A human can separately
use the existing explicit artifact-reference flow to share a verified artifact with another conversation.

## Bounds and stopping

Persisted admission limits a lineage to depth two and three lifetime direct children per parent; no more than two direct children
may be active in storage. The currently exposed tool waits for one child at a time per parent. A child is limited to at most eight
model steps, ten minutes, and the remaining parent deadline. A lineage reserves the root's configured currency ceiling when one
is set; provider-call token and cost estimates are still subject to the provider's actual billing. The bot's daily token limit and
configured shared-account reservations apply to child model calls as well.

Stopping a parent persists cancellation for its existing descendants before cleanup begins. A child also watches its parent
ownership; if the parent stops or is recovered, it requests cancellation. Each owned process remains visibly Cancelling until
cleanup is verified. A timeout or lost result remains explicit and is not replayed automatically.

## Verification boundary

Automated fixtures cover approval in `auto` mode, process-supervised root/child execution, the Strict Offline local-model broker,
bounded context transfer, child result return, ancestry slots, cancellation and inherited budgets. This does not certify a live
Ollama/model installation, provider provenance, multi-child parallelism, child-to-parent artifact copying, external runtimes,
or physical-device supervision. Pi and OpenCode remain unavailable as child runtimes.

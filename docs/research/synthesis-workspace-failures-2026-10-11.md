# Failure evidence ledger — grounded synthesis and Workspace actions (2026-10-11)

Research pass for the synthesis/Workspace lane. Fetched 2026-10-11 from the documented URLs.
Each row: what was actually read, what it means for Hutch, and the regression that will pin it.
Nothing here is treated as a live Hutch failure; these are design scenarios until reproduced.

## Official references (fetched and read this date)

| Ref | Source (fetched) | Verified content | Decision | Regression/intent |
|---|---|---|---|---|
| R1 | support.google.com/gemininotebook/answer/16212820 | Interactive mode: English-only; Join → hosts call on you → source-grounded answer → resume; voice/interactions not stored; **acknowledged glitches: random speaker switches, third voice, voice glitches**; delays after Join/speak; only newly generated overviews | Model playback-only and interactive separately; validate speaker identity per segment | Interactive state-machine tests; assembly speakercheck |
| R2 | docs.cloud.google.com/.../api-audio-overview | Enterprise: one audio overview per notebook; create fails when one exists; license required; IN_PROGRESS lifecycle; delete path `.../audioOverviews/default` | Optional adapter only; never delete a user's overview to retry | Adapter contract test: refuse to clobber |
| R3 | ai.google.dev/.../speech-generation | Current TTS models `gemini-3.8-flash-tts`/`-lite`; multi-speaker ≤2 **prebuilt** voices per request; custom voices require per-turn synthesis; unary → WAV (RIFF), streaming → headerless `AUDIO_L16` 24 kHz mono; `speech_metadata.style` vs inline `<tags>`; `|backchannel|` overlap syntax; text is verbatim transcript, stage directions must never be text | Multi-speaker request per segment with stable speaker map; PCM/WAV handling per actual response; style never in transcript | TTS fixture tests: verbatim text preserved; no style strings spoken; concat correctness |
| R4 | ai.google.dev/.../live-api/capabilities (+best-practices family) | Interruption = server `interrupted:true` **and** client "stop playing audio and clear queued playback"; audio-only sessions ≤15 min; Live has a **single** voice config; preview | Do not assume Live two-voice; interruption handling is client-owned queue clear + stop | Playback tests: cancelled audio never resumes/replays |
| R6 | developers.google.com/.../docs/api/how-tos/tabs | `includeTabsContent=true` required for all tabs; `document.body` empty then; recurse `childTabs`; per-request `tabId`; defaults hit first tab except Replace* (all tabs) | Bind to explicit tab IDs read from the document; never assume first tab | Docs contract tests with multi-tab fixtures |
| R9 | developers.google.com/.../docs/api/how-tos/images | `InsertInlineImageRequest.uri` must be publicly accessible | No silent public asset exposure; use Drive attachment/link and state the limitation | Privacy test: no public URL minted for private assets |
| R10 | developers.google.com/.../tasks/reference/rest/v1/tasks | `due`: "Only date information is recorded; the time portion ... is discarded ... not possible to read or write the time" | Exact-time reminders never routed to Tasks; use event-relative overrides or Hutch routines | Reminder-routing tests |
| R11 | developers.google.com/.../calendar/api/guides/create-events | Caller-supplied event IDs documented for sync/duplicate prevention; `sendUpdates` all/externalOnly for attendee mail; reminder overrides are relative offsets; attachments need prior full sync | App-generated stable event IDs; read back after write; never promise universal no-notification | Calendar idempotency + read-back tests |

Not yet re-fetched (mechanism-stable; to verify at the slice that uses them): R5 drive scopes,
R7 Sheets `ValueInputOption`/append, R8 Drive uploads/shared drives/sharing,
R11 version-resources. Recorded here so the gap is explicit rather than implied verified.

## First-hand failure reports

| Ref | Source (fetched) | State at fetch | Applicability to Hutch | Regression intent |
|---|---|---|---|---|
| F1 | support.google.com/gemini/thread/416109811 | Thread body is client-rendered; fetch returned the title only ("Notebook LM interactive mode hidden from view"). No support replies read. | Reported class: interactive controls absent/hidden. Not proof any current build fails. | UI must expose why interaction is unavailable, never a dead control |
| F2 | discuss.ai.google.dev/t/...174346 | Title/first view: "server never emits interrupted (barge-in) when the user is already speaking as the model's turn begins". Full thread not readable without JS. | Interruption cannot rely solely on a server signal | Test: user speaks at model-turn start → playback stops, queue clears, turn belongs to user |
| F3 | github.com/n8n-io/n8n/issues/20372 | Closed as duplicate 2025-11-19; reporter on n8n 1.113.3: append writes to wrong sheet with two inputs + name-lookup | Generic class: resolve targets by ID, verify returned target; never first-similar-name | Sheets target-binding tests (similarly named sheets/tabs) |
| F4 | github.com/n8n-io/n8n/issues/11234 | Closed completed 2024-10-15; append on >10k-row sheet loaded whole sheet → high memory/OOM | Append must not load full history; header-only + bounded reads | Large-sheet append memory test |

## Environment (verified this date)

* This host: `ffmpeg`/`ffprobe`/`bwrap`/`secret-tool` present; `soffice`, `piper`, `espeak-ng`, `sox` absent.
* Hutch state on this machine: no Google account connected, no Google OAuth client configured,
  no hosted model provider configured (template/demo bots only). Therefore every live Google,
  Gemini-TTS and OpenAI-TTS check in this lane is **unexecuted** until credentials exist;
  protocol/contract tests use local fixtures and fake HTTP servers only.

## Status vocabulary for this lane

`verified-live` (real provider/account, evidence kept) · `verified-local` (real code on this
machine, fixtures only) · `implemented-unverified` (code path exists, no end-to-end run) ·
`blocked` (needs credentials/hardware) · `unsupported` (deliberately refused).

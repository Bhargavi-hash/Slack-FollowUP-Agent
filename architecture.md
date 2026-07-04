# Meeting Action Items Agent — Architecture

## 1. Goal

A Slack app that takes a pasted meeting transcript, extracts real action items
(owner, task, deadline) grounded in what was actually said, resolves owners to real
Slack users via Slack's official MCP server, and posts them back into the channel
as structured, mentionable messages.

**This project explicitly does NOT (for this hackathon scope):**
- Integrate directly with Zoom/Google Meet's transcript APIs (deferred — those
  require a paid Zoom plan and have unpredictable post-meeting processing delays)
- Track action item completion/status over time (no persistence beyond posting)
- Support languages other than English in this first version
- Guarantee it catches every action item — it optimizes for not inventing items
  that weren't actually said, even if that means occasionally missing a vague one
- Involve any LLM-driven tool-call decisions — this is a fixed, deterministic
  pipeline (extract → resolve → post, in that order, every time), not an
  autonomous agent choosing which tools to call

**Primary goals for the hackathon submission:**
- A working, demoable core loop: paste transcript → get real, grounded action
  items → posted into Slack, correctly `@mentioning` real people
- A genuine, functional MCP integration (calling Slack's official MCP server for
  user lookup), satisfying the "MCP server integration" track requirement
- Something a real team would plausibly want to use, not just a tech demo

---

## 2. High-level data flow

```
User pastes a transcript
  (slash command: /extract-actions, opens a modal for multi-line paste)
        |
        v
  ┌─────────────────────┐
  │ Extraction             │
  │ ONE-SHOT Gemini call:  │
  │ transcript -> structured│
  │ action items (owner as │
  │ written, task, due     │
  │ date, source quote)     │
  │ No tool-calling here —  │
  │ pure text-in, JSON-out │
  └──────────┬───────────┘
             v
  ┌─────────────────────┐
  │ Owner Resolution        │
  │ Your CODE (deterministic,│
  │ not an LLM decision)    │
  │ loops over each owner    │
  │ name, calls Slack's      │
  │ OFFICIAL MCP server's    │
  │ user-lookup tool          │
  └──────────┬───────────┘
             v
  ┌─────────────────────┐
  │ Posting                  │
  │ Bolt app's own Slack Web  │
  │ API (chat.postMessage) —  │
  │ NOT via MCP. Block Kit     │
  │ message per action item,  │
  │ @mention if resolved,      │
  │ plain name if ambiguous/   │
  │ not found                  │
  └─────────────────────┘
```

Design principle: **extraction, resolution, and posting are three separate,
deterministically-sequenced steps.** The LLM's only job is language understanding
(extraction). Everything after that — which tool to call, how to post — is
ordinary, predictable code, not an LLM decision. This is a fixed pipeline, not an
autonomous agent, and that's a deliberate choice for reliability within the
hackathon timeline.

---

## 3. Components

### 3.1 Slack App (Bolt for Python) (`app/`)

- **Entry point**: slash command `/extract-actions`, which opens a Slack modal
  with a multi-line text input for pasting the transcript (chosen over a raw
  slash-command argument, which handles multi-line text poorly).
- **On submit**: passes the raw transcript text through Extraction → Owner
  Resolution → Posting, in that fixed order.
- **Registered Slack app** (fixed app ID) with OAuth scopes: `chat:write` (post
  messages), `commands` (slash command), plus whatever scope Slack's MCP server
  user-lookup tool requires (confirm exact scope name against current Slack docs
  when implementing — this has changed over time).
- Built and tested against a **free Slack Developer Program sandbox workspace**
  — no paid Slack plan needed for development or this hackathon's scope.

### 3.2 Extraction (`extraction/extract_actions.py`)

- Input: raw transcript text (plain text, pasted by the user), plus the meeting
  date (see 3.2b).
- **One-shot Gemini call** (2.5 Flash, free tier) with an explicit instruction:
  extract only action items **explicitly stated or clearly implied** in the
  transcript — never invent items, never infer tasks that weren't discussed.
- Output: a list of structured items:
  ```json
  {
    "owner_name": "John",
    "task": "Send the updated proposal doc",
    "due": "2026-07-10",
    "source_quote": "John, can you send that doc by Friday?"
  }
  ```
- **Mandatory `source_quote` per item** — every extracted item must trace back to
  an actual line in the transcript, for both user trust and debuggability (same
  grounding discipline as the RAG project's citations).

### 3.2b Meeting date input

- **Decision**: the modal includes a required date picker (Slack's native
  `datepicker` block) for "when did this meeting happen," defaulting to today.
  This resolves relative dates ("by Friday") correctly without needing automatic
  meeting-date detection, which is out of scope.

### 3.3 Owner Resolution (`resolution/resolve_owner.py`)

- For each `owner_name` extracted, your code (not an LLM) calls **Slack's
  official MCP server** (`mcp.slack.com`) using its user-lookup tool to search the
  workspace for a matching real user by display/real name.
- **This is the project's one genuine MCP integration point.**
- **Ambiguity handling (decided)**: if more than one workspace member plausibly
  matches a first name, do NOT guess — mark that item as `"resolution": "ambiguous"`
  and post it with the plain name as text, no `@mention`. A wrong `@mention` is a
  worse failure than an unresolved name.
- **No match found**: mark `"resolution": "not_found"`, post with plain name, no
  `@mention`.
- **Match found**: mark `"resolution": "resolved"`, post with a real `@mention`.

### 3.4 Posting (`posting/post_items.py`)

- Formats each action item as a Slack Block Kit message: task, resolved
  `@mention` (or plain name + a small "⚠️ couldn't confirm who this is" note for
  ambiguous/not-found cases), due date, and the source quote shown as a collapsed
  context block for traceability.
- Posts directly via the Bolt app's own Slack Web API access (`chat.postMessage`)
  to the channel the slash command originated from — **not** routed through MCP.
- **Explicit non-goal for this version**: no interactive checkboxes/status
  tracking — items are posted as informational.

---

## 4. Repo structure

```
meeting-action-items-agent/
├── architecture.md
├── requirements.txt
├── manifest.json                # Slack app manifest (scopes, redirect URLs, slash command)
├── app/
│   └── main.py                  # Bolt app entry point, slash command + modal handlers
├── extraction/
│   └── extract_actions.py       # Gemini call + prompt, structured item output
├── resolution/
│   └── resolve_owner.py         # Slack official MCP server client, user lookup, ambiguity handling
├── posting/
│   └── post_items.py            # Block Kit formatting + chat.postMessage
├── tests/
│   ├── fixtures/
│   │   ├── transcript_clean.txt        # unambiguous owners, clear action items
│   │   ├── transcript_ambiguous.txt    # duplicate first names in the test workspace
│   │   └── transcript_no_actions.txt   # meeting with no real action items — should extract nothing
│   ├── test_extraction.py       # checks against all three fixtures, incl. no-invention checks
│   └── test_resolution.py       # mocked MCP responses: resolved / ambiguous / not_found paths
```

---

## 5. Key decisions and why

- **Manual transcript paste, not live Zoom/Meet integration** — deferred due to
  the paid-plan requirement and unpredictable webhook processing delay for Zoom's
  transcript API; keeps the hackathon build achievable and demoable on-demand.
- **Fixed, deterministic pipeline — not an autonomous agent** — extraction,
  resolution, and posting always run in that order, decided by code, not by an
  LLM. More predictable and debuggable within the hackathon timeline than an
  agent architecture where an LLM decides tool-call sequencing.
- **Extraction and resolution as separate steps** — an LLM should never directly
  output a Slack user ID; resolving a name to an account is a deterministic
  lookup problem, cleanly separable from the language-understanding problem of
  extracting what was said.
- **Mandatory source quote per extracted item** — forces traceability, makes
  false extractions immediately visible/debuggable.
- **Fall back to plain text on ambiguous/no-match owners, never guess** — a wrong
  `@mention` actively harms trust (pings the wrong person); an unresolved plain
  name is merely incomplete. Optimize for the less harmful failure mode.
- **Required date picker in the modal, not automatic date detection** — keeps
  relative-date resolution ("by Friday") correct without needing a harder,
  out-of-scope meeting-date-detection feature.
- **Slack's official MCP server for user lookup, not a bespoke MCP server** —
  satisfies the hackathon's MCP requirement genuinely, while avoiding the added
  complexity of registering and hosting your own MCP server for Slackbot to
  discover (which requires Marketplace publication or internal install status).
- **Posting via the Bolt app's own Web API access, not through MCP** — MCP is
  used only where it's actually needed (user lookup); posting is ordinary,
  direct Slack app functionality.

---

## 6. Non-goals / constraints (for this hackathon scope)

- No live Zoom/Google Meet transcript API integration
- No action-item status tracking/persistence across time
- No multi-language support
- No handling of transcripts beyond Gemini's context window (unlikely at
  hackathon scale, not explicitly handled)
- No automatic meeting-date detection — user provides it via the modal's date picker

---

## 7. Decisions (previously open questions, now resolved)

- **Slash command**: `/extract-actions`
- **Ambiguous owner matches**: fall back to plain text + a visible "couldn't
  confirm who this is" note, no interactive picker for this version (a Slack
  interactive select-menu to disambiguate is a reasonable future enhancement, not
  in scope now)
- **Demo video plan**: a clean, controlled walkthrough — paste
  `transcript_clean.txt` live, show correct extraction and resolution, show the
  posted result; separately narrate the ambiguous/not-found handling using
  `transcript_ambiguous.txt` since that's a correctness property worth
  demonstrating explicitly, not just claiming
- **Zoom/Meet integration**: explicitly deferred out of hackathon scope, noted as
  a future direction in the submission write-up

---

## 8. How to use this doc with Claude Code

- Point Claude Code at this file first: *"Read architecture.md before making any
  changes."*
- Build in this order:
  1. Extraction — test against all three fixtures, confirm zero invented items on
     `transcript_no_actions.txt`
  2. Owner resolution — test with mocked Slack MCP responses first (real OAuth
     setup takes longer); confirm all three resolution paths (resolved,
     ambiguous, not_found)
  3. Slack app wiring — slash command, modal, posting
  4. End-to-end test in your free Slack Developer Program sandbox workspace
- The riskiest part to get subtly wrong is owner resolution ambiguity — after
  building it, deliberately test with `transcript_ambiguous.txt` (a name matching
  multiple sandbox members) and a transcript naming someone NOT in the sandbox at
  all, confirming both fall back correctly rather than mis-mentioning anyone.

  
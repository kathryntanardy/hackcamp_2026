# prd_editor — Skill Design

## 1. The one job

When a product or architecture decision changes — agreed in chat or shown in code — update `PRD.md` so it matches current reality.

## 2. Done means

- Every PRD section the change touches is updated, and nothing anywhere in the PRD contradicts the change.
- Sections the change doesn't touch are byte-for-byte identical — no drive-by rewording.
- Stale or removed content is deleted outright, not marked "deprecated".

## 3. Inputs and outputs

**Inputs**
- **Code changes:** `git diff $(git log -1 --format=%H -- PRD.md)` — everything since the last commit that touched `PRD.md`, through the working tree (includes uncommitted changes).
- **Chat decisions:** the decision text from the current conversation.
- **Always:** the current `PRD.md` at the repo root (311 lines, 16 `##` sections at time of writing).

**Outputs**
- `PRD.md` edited in place, `##` heading structure preserved.
- No chat summary.

## 4. Triggers

The skill fires on settled decisions even when the PRD isn't mentioned.

**Should trigger**
1. "update the PRD"
2. "we're dropping X, reflect that in the PRD"
3. "sync the PRD with the code"
4. "PRD is out of date"
5. "we decided to use Y instead of Z"
6. "I just changed the data model, update the docs"
7. "make sure the PRD matches what we built"
8. "cut feature X from scope"

**Near-misses — should NOT trigger**
1. "what does the PRD say about scoring?" — read-only question
2. "write a PRD for a new project" — creating, not syncing
3. "update the README" — different doc
4. "add this to ISSUES.md" — different doc
5. "should we drop feature X?" — still a discussion, not a decision

## 5. Exact jobs vs judgement

**Scripts (deterministic)**
- `get_diff.sh` — find the last commit touching `PRD.md`, print the diff from there to the working tree.
- `check_headings.py` — snapshot `##` headings and per-section hashes before the edit; after the edit, report which sections changed and verify heading structure survived.

**Instructions (judgement)**
- Is this chat message a settled decision or still a discussion?
- Which PRD sections does the change affect? (e.g. a schema change → Data model, maybe Architecture and Health scoring)
- Writing new text in the PRD's existing voice and level of detail.
- Deciding what's stale and deleting it.
- Spotting contradictions elsewhere in the doc.

## 6. Gates

| # | Gate | How it's checked | How we prove it can fail |
|---|------|------------------|--------------------------|
| 1 | Untouched sections are byte-identical | `check_headings.py` compares section hashes against the sections the skill declared it would edit; any undeclared change fails | Reword one sentence in an unrelated section → check flags that section |
| 2 | Heading structure preserved | Same `##` headings in the same order, unless the decision explicitly adds/removes a section | Rename "Data model" to "Schema" → check fails |
| 3 | No stale references | After a removal or rename, grep the PRD for the old term → must be zero hits | Drop feature X but leave one mention in "Demo script" → grep catches it |
| 4 | Diff was actually read | For code-triggered runs, the diff must be non-empty; if empty, say "nothing to sync" and stop | Run right after a PRD commit with no other changes → exits cleanly without inventing edits |

Known weakness: gate 3 only catches exact-term leftovers, not paraphrased contradictions — those rely on the judgement step.

## 7. Rules

1. **Don't edit on a "should we…?"** — only on a settled decision. *Why:* otherwise brainstorming rewrites the PRD.
2. **Never reword sections the change doesn't touch.** *Why:* breaks gate 1 and buries the real change in noise.
3. **Delete stale content; don't add "(deprecated)" or strikethrough.** *Why:* chosen in "Done means" — half-dead text confuses judges and teammates.
4. **When an open question gets answered, remove it from "Open questions" and put the answer in the right section.** *Why:* otherwise question and answer live in two places and drift.
5. **Don't invent details the decision didn't state.** (Said "use Postgres" ≠ make up table names.) *Why:* the PRD should only claim what's actually decided.
6. **Don't commit the PRD edit** — leave it as a working-tree change. *Why:* keeps git control with the user, and keeps gate 4's "since last PRD commit" base stable until they commit.
7. **Read the whole PRD before editing, not just the target section.** *Why:* changes ripple into 2–3 sections (schema → Data model, Architecture, Health scoring).

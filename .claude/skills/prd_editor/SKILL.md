---
name: prd_editor
description: Keep PRD.md in sync with settled product or architecture decisions. Use whenever the user asks to update/sync the PRD ("update the PRD", "PRD is out of date", "make sure the PRD matches what we built", "sync the PRD with the code"), AND whenever they state a settled decision even without naming the PRD ("we decided to use Y instead of Z", "cut feature X from scope", "we're dropping X", "I just changed the data model, update the docs"). Do NOT use for read-only PRD questions ("what does the PRD say about..."), writing a brand-new PRD, editing README.md or ISSUES.md, or open discussion ("should we drop X?").
---

# prd_editor

**Job:** when a product or architecture decision changes (agreed in chat or shown in code), update `PRD.md` at the repo root so it matches current reality.

Scripts live in `.claude/skills/prd_editor/scripts/`. Run them from the repo root.

## Steps

1. **Is it a settled decision?** If the user is still asking or weighing ("should we…?", "what if…"), do nothing. Only proceed on a decision or an explicit request to sync.

2. **Gather input.**
   - Chat decision: use the user's words. Don't add details they didn't state.
   - Code changes (or "sync with the code"): run `bash .claude/skills/prd_editor/scripts/get_diff.sh`. If the output is empty, say "nothing to sync since the last PRD commit" and stop. Don't invent edits.

3. **Read the whole `PRD.md`**, not just the obvious section. Decide every section the change touches (it's usually 2–3, e.g. a schema change → Data model, Architecture, Health scoring). Also check "Open questions" and "Demo script" for leftovers.

4. **Snapshot before editing:**
   ```bash
   python3 .claude/skills/prd_editor/scripts/check_headings.py snapshot PRD.md "${TMPDIR:-/tmp}/prd_snapshot.json"
   ```

5. **Edit only those sections.** Match the PRD's existing voice and level of detail. Delete stale content outright.

6. **Run the gates.** Pass one `--edit` per section you changed (use the exact heading text without `## `; `(preamble)` is everything above the first `##`). Pass one `--stale` per removed or renamed term. Add `--structure-change` only if the decision itself adds or removes a section.
   ```bash
   python3 .claude/skills/prd_editor/scripts/check_headings.py check "${TMPDIR:-/tmp}/prd_snapshot.json" PRD.md \
     --edit "Data model" --edit "Architecture" --stale "old term"
   ```
   If anything prints `FAIL`, fix the PRD and rerun until you see `PASS: all gates`. Don't finish on a failure.

7. **Stop.** Don't commit, and don't post a chat summary of the changes.

## Rules

1. **Don't edit on a "should we…?"**; only edit on a settled decision. *Why:* otherwise brainstorming rewrites the PRD.
2. **Never reword sections the change doesn't touch.** *Why:* it breaks gate 1 and buries the real change in noise.
3. **Delete stale content; don't mark it "(deprecated)" or strike it through.** *Why:* half-dead text confuses judges and teammates.
4. **When an open question gets answered, remove it from "Open questions" and put the answer in the right section.** *Why:* otherwise the question and answer live in two places and drift apart.
5. **Don't invent details the decision didn't state.** ("Use Postgres" doesn't mean you make up table names.) *Why:* the PRD should only claim what's actually decided.
6. **Don't commit the PRD edit.** *Why:* the user controls git, and the diff base for `get_diff.sh` stays stable until they commit.
7. **Read the whole PRD before editing.** *Why:* changes ripple into several sections.

## Known gap

`--stale` only catches exact-term leftovers. Paraphrased contradictions ("the agent runs hourly" after switching to daily) are on you: reread the touched-adjacent sections before finishing.

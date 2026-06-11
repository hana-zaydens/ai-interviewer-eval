# Turn-Level Coding Codebook

**Version:** 1.0  
**Unit of analysis:** Individual turns within interview transcripts  
**Coder:** Human coder + LLM-assisted classification on full dataset

---

## Fields and Coding Instructions

### Auto-populated fields (do not edit unless correcting an error)

| Field | Type | Description |
|---|---|---|
| `transcript_id` | Text | Unique identifier for the source interview |
| `split` | Text | Dataset group or condition (e.g. a study arm, interview round) — as loaded |
| `turn_number` | Number | Sequential position of the turn within the transcript |
| `speaker` | Select | `AI` or `User` |
| `text` | Long text | Full content of the turn |
| `word_count` | Number | Word count of the turn text |
| `char_count` | Number | Character count of the turn text |

---

### `turn_type`
**Applies to:** All turns  
**Type:** Single select  
**Auto-labeled:** `opening`, `closing` (first/last AI turn); `response` (all User turns)  
**Manual coding required:** All other AI turns

#### Codes

| Code | Applies to | Definition |
|---|---|---|
| `opening` | AI | First turn of the interview. Establishes context, introduces the study, and invites participation. Auto-labeled — review but rarely needs changing. |
| `closing` | AI | A turn that either (1) signals the end of prepared questions, typically with a personalised summary and an invitation for final thoughts, or (2) contains sign-off language ("Thank you", "Goodbye", or equivalent wrap-up). Interviews may contain two closing turns: the summary/invite turn and the final sign-off. **If the participant responds to the "anything else?" invite with new substantive information and the AI engages with it, that AI turn should be coded `follow_up` or `new_question` as appropriate — closing coding resumes when the AI returns to wrap-up language.** Auto-labeled by position (last AI turn) and by any text patterns defined in `schema.json` — review to confirm correctness. |
| `new_question` | AI | The AI introduces a new topic or theme not previously discussed, or moves on from the current topic. Applies whether the transition is a cold shift or wrapped in praise/acknowledgment of the previous answer. |
| `follow_up` | AI | The AI asks for elaboration, clarification, or deeper exploration of the participant's immediately preceding response. The turn must genuinely build on what the participant just said — not just reference it rhetorically before moving on. |
| `response` | User | Participant responds to the AI's question or statement. Auto-labeled — edit if needed. |
| `ambiguous` | AI or User | The turn could plausibly be classified as more than one type. Add a note explaining the ambiguity. Review these as a batch after initial coding to identify patterns. |
| `other` | AI or User | Does not fit any of the above categories. Always add a note. Review these as a batch to identify potential new codes. |

#### Decision rules

- **Recurring standard opening questions.** If the AI uses a consistent opening question across transcripts (appearing after the first turn once the participant signals readiness), code it as `opening`, not `new_question`. Coding it as `new_question` would artificially inflate the new question count. You can add a pattern to `schema.json` to auto-label it.
- **Pivot is not a separate code.** A turn that acknowledges the participant's answer (possibly with praise) and then moves to a new topic is coded `new_question`. Use `biasing_response` to flag the rhetorical framing separately.
- **"Follow-up" requires genuine probing.** If the AI says "you mentioned X — that's fascinating! Now let's talk about Y," that is a `new_question`, not a `follow_up`, even though it references the previous answer.
- **Context-anchored new questions are still `new_question`.** When the AI uses specific language or examples from the participant's previous response as a framing hook, but introduces a new line of inquiry rather than probing what the participant actually said, code it as `new_question`. The test: would a trained human interviewer recognise this as probing what the participant said, or as moving to the next topic using the participant's words as a bridge? If the latter, code `new_question`.
- **When in doubt between `follow_up` and `new_question`:** ask whether a trained human interviewer would recognise it as probing deeper into the same thread. If no, code `new_question`.

---

### `biasing_response`
**Applies to:** AI turns only  
**Type:** Checkbox  
**Auto-detection:** Heuristic pre-populates explicit praise patterns only (see note below). All other cases require manual judgment.

#### Definition
Check this box when the AI's turn contains language that could bias, confirm, or steer the participant's framing — including but not limited to:

- **Explicit praise:** Formulaic affirmations before asking the next question ("That's really insightful!", "Wow, that's fascinating")
- **Affirmative reframes:** Restating the participant's answer with added positive spin ("It sounds like this is really working well for you" — when the participant only said it was useful)
- **Leading interpretations:** Adding assumptions or conclusions the participant did not make ("So it seems like you find this essential to your workflow" — when the participant expressed more ambivalence)
- **Vocabulary substitution:** Replacing the participant's plain language with a more formal, elevated, or positive term not introduced by the participant (e.g., participant says "faster" → AI says "streamline"). The substitution quietly upgrades or reframes the participant's meaning without their input.
- **Agency shift:** Changing who or what is acting in the restatement (e.g., participant says "I use it to make that process faster" → AI says "it's really helping streamline those tasks for you"). This repositions the AI from a tool the participant controls to an active collaborator or benefactor.

#### What is NOT a biasing response
- Neutral reflective statements used to confirm understanding ("So if I'm understanding correctly, you primarily use it for drafting?")
- Genuine clarifying questions that don't add interpretation
- "It sounds like..." or "It seems like..." on their own — these phrases are only biasing when the content that follows overstates, assumes, or adds positive framing not present in the participant's answer
- **Transitional facilitation phrases in `opening` turns** — e.g., "Great! Let's dive in then." These occur before any substantive response and serve to ease the participant into the interview, not to evaluate their answers. Flag `biasing_response` only when the affirmation is evaluating something the participant has actually said.
- **Note: `closing` turns are NOT exempt.** A flattering personalised summary of the participant's responses before asking "anything else?" should be flagged as `biasing_response`. This is a form of positive reframe delivered at the moment most likely to shape what the participant adds in their final response.

#### Auto-detection note
The heuristic flags explicit praise patterns only (e.g., "That's really insightful", "Wow", "Thank you for sharing"). It cannot detect interpretive reframes — those require manual judgment. The auto-detected rate is therefore a **conservative floor**. The true rate after manual coding is expected to be higher.

---

### `missed_opportunity`
**Applies to:** AI turns only  
**Type:** Checkbox

#### Definition
Check this box when, at the point this turn occurs, a meaningful probe was available in the preceding exchange and was not adequately pursued.

#### Coding rule
**Always flag on the `new_question` turn that closes the exchange** — the moment the AI definitively moves on. This is the point at which a missed opportunity is confirmed.

Ask yourself: *Was there something worth probing in the preceding exchange — including the participant's most recent response — that the AI never adequately addressed?*

#### Common cases

| Scenario | Where to flag |
|---|---|
| AI moves to a new topic without any follow-up | Flag on the `new_question` |
| Participant makes two interesting points; AI probes only one, then moves on | Flag on the `new_question` that closes the exchange |
| AI asks a follow-up but probes the less consequential thread, then moves on | Flag on the `new_question` that closes the exchange |
| AI asks a follow-up that is so off-topic it is functionally a topic change | Code as `follow_up`, flag `missed_opportunity`, add a note |

#### What is NOT a missed opportunity
- The AI asked a genuine, substantive follow-up that adequately explored the participant's response, even if more could theoretically have been asked
- The participant's response was brief and offered no clear opening for deeper probing

---

### `notes`
**Applies to:** All turns  
**Type:** Long text  

Free text for anything that doesn't fit the coded fields. Always add a note when coding `ambiguous` or `other`. Use this field to flag candidate examples for analysis, record uncertainty, or note patterns worth revisiting.

---

## Batch review protocol

After completing initial coding, run the following reviews:

1. **All `ambiguous` turns** — look for patterns that suggest a missing code
2. **All `other` turns** — same as above
3. **All `follow_up` + `missed_opportunity` combinations** — confirm these are cases where the probe was so off-target it was functionally a topic change; recode if needed
4. **Auto-detected `biasing_response` = false, manual judgment = true** — review a sample to assess how much the heuristic underestimates the true rate

---

## Open questions / pending decisions

- Sub-categorisation of `biasing_response` types (explicit praise / affirmative reframe / leading interpretation) — deferred; will revisit after initial coding
- Whether to add `response` sub-types for User turns (e.g., to flag when a participant appears to echo back the AI's framing)

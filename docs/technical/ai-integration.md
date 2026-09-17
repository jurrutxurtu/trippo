# AI integration

## Scope — deliberately small

The user asked for **suggestions, not stories**. Target output volume is roughly **one line per
day**. Long generated prose is an explicit non-goal (`AGENTS.md` §1).

The app is **fully functional with no API key**. Without one, `NullProvider` is installed and every
AI affordance is hidden — not greyed out, hidden.

## Features

| Feature | Input | Output | Cost |
|---|---|---|---|
| **Place-label disambiguation** | geocode candidates + duration + time of day + photo count | chosen or composed label, confidence | highest value |
| Day title + subtitle | that day's curated facts (~2 KB) | 3 options, one line each | low |
| Trip title + summary | day titles + trip stats | 3 options, 2–3 sentences | trivial |
| Note polish | the user's rough note | tidied version, same content | on demand |
| Photo captions | 3–6 downsampled heroes | short captions | opt-in, batched |
| Coherence check | itinerary skeleton | list of flags | mostly free (see below) |

## Coherence checks are mostly deterministic

Do **not** ask a model what Python can compute. `ai/coherence.py` runs these in code:

- a day with media but no active event;
- an unaccounted gap still unresolved;
- two overnight events on one day;
- an event whose media timestamps fall outside its time range;
- a day with no events that is not excluded;
- media still sitting in the unassigned pool;
- a track not attached to any event.

Only genuinely fuzzy judgements ("these two visits look like the same place") reach the LLM.

## Prompting rules

1. **The model never sees raw data** — only the curated, approved itinerary. This is the entire
   point of the curation phase, and it is what keeps context at a few KB instead of megabytes.
2. **One call per day**, plus a short trip-level context and the previous day's title for
   continuity. Whole-trip calls caused the repeated-day failure this product exists to avoid.
3. **Structured output only** — a response schema, never free text.
4. **Facts are provided; invention is not requested.** Prompts supply place names, times and stats,
   and ask for phrasing.

## Output validation

`ai/validators.py` rejects and retries once when:

- a proper noun in the output does not fuzzy-match any name in the input facts;
- a place label is not one of the supplied candidates (disambiguation);
- output exceeds the length budget;
- the response fails schema validation.

A second failure falls back to the deterministic result. **A validation failure never blocks the
user.**

## Provider

`ports/llm.py` defines the protocol; `ai/gemini.py` implements it with `google-genai`
(Gemini Flash, structured output, native vision). Swappable. Key from `GEMINI_API_KEY`, read from
`.env`, never committed.

## Privacy

Enabling AI sends curated text — place names, times, the user's own notes — and, only if photo
captions are switched on, downsampled images. Never the location history, never originals. Stated
plainly in the UI at the point of enabling.

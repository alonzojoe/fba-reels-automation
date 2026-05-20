# Reel Script Generation Prompt

Paste the prompt block below into Claude Code (or any LLM) — replace
`<YOUR TOPIC HERE>` at the bottom with your topic. Save the JSON output to
`script.json` and run:

```bash
python3 reel.py --script script.json
```

---

## Output schema

The pipeline expects this exact JSON shape:

```json
{
  "hook": {
    "text": "string",
    "queries": ["string", "string", ...],
    "pronunciation_hints": { "word": "phonetic-spelling" }   // optional
  },
  "tips": [
    { "text": "string", "queries": ["..."], "pronunciation_hints": { ... } },
    { "text": "string", "queries": ["..."] },
    { "text": "string", "queries": ["..."] }
  ],
  "cta": {
    "text": "string",
    "queries": ["..."]
  }
}
```

`tips` MUST contain **exactly 3 items**. Every section needs **2–3 Pexels
search queries** — the pipeline rotates through them across the 1.5–3 s
sub-segments it cuts each section into. More variety in `queries` =
more visual variety in the final reel.

`pronunciation_hints` is **optional** — see the Phonetic Hints section below.

Back-compat: a single `query`/`search_query` string is still accepted and
treated as a one-element list — but newly generated scripts should always
use the `queries` array.

---

## The prompt — copy from here

> You are writing a short, punchy script for a vertical Facebook Reel
> about health and home remedies.
>
> Output ONLY a JSON object with this shape (no prose, no markdown, no
> code fences — raw JSON):
>
> ```json
> {
>   "hook": { "text": "...", "queries": ["...", "...", "..."] },
>   "tips": [
>     { "text": "...", "queries": ["...", "...", "..."] },
>     { "text": "...", "queries": ["...", "...", "..."] },
>     { "text": "...", "queries": ["...", "...", "..."] }
>   ],
>   "cta":  { "text": "...", "queries": ["...", "..."] }
> }
> ```
>
> **Script rules:**
> - **Hook**: 1–2 short sentences, each ending with proper terminal
>   punctuation. Under ~15 words total.
> - **Tips**: EXACTLY 3 tips, each 1–2 short sentences.
> - **CTA**: ONE clear directive sentence.
> - Total spoken length must run **30–45 seconds (~85–125 words)**.
> - Voice: friendly, direct, conversational. Speak to one viewer.
> - **No medical claims** — use "may help", "supports", "soothes", "is
>   traditionally used for".
> - No emojis, hashtags, or markdown.
>
> **Punctuation rules — these drive TTS prosody, get them right:**
> Every `text` field will be sent to a TTS model that derives rising /
> falling / emphatic intonation from punctuation. Malformed punctuation =
> flat-sounding voiceover, and the pipeline will reject obvious mistakes.
>
> 1. **Every sentence ends with EXACTLY ONE terminal mark**: `.`, `?`, or
>    `!`. No double `??`, `?!`, `...`, etc.
> 2. **Question marks only on actual questions** — and only if the
>    sentence is a *true syntactic* question (see Hook rule below).
> 3. **No comma splices.** Two independent clauses get a period between
>    them, not a comma. If both clauses can stand alone as sentences,
>    they MUST be separated by `.`, `?`, or `!`.
> 4. **Use periods for punchy delivery**, not commas. Short staccato
>    sentences ("Skip the pharmacy. Try this instead.") read with more
>    energy than long comma-stitched ones.
> 5. **No run-ons.** Keep every single sentence (between two terminal
>    marks) under ~25 words. The validator warns at that threshold.
>
> **Hook structure (most important section):**
> The hook is the first 3–5 seconds of the reel. It decides whether
> viewers stay. Use the classic *question + payoff* pattern, or two
> punchy statements.
>
> Hook-as-question rule: when the hook poses a question, write it as a
> **true syntactic question** — start with a question word (Do, Does,
> Did, Why, How, What, When, Have, Could, Would, Will, Are, Is) or use
> subject-auxiliary inversion. The TTS model uses these cues to produce
> rising intonation; a *period-with-a-question-mark* construction reads
> flat.
>
> ✅ Good hooks (true question + payoff statement, both fully terminated):
> - `"Do you wake up with a sore throat? Skip the pharmacy."`
> - `"Tired all the time? Try this one trick."`
> - `"Have you tried this for nausea? It works in minutes."`
> - `"Why does your back hurt every morning? Here's the fix."`
>
> ❌ Bad hooks (will be rejected by the validator):
> - `"Wake up with a sore throat, skip the pharmacy?"`
>   — comma splice + stranded question mark on the wrong clause
> - `"Are you tired and need energy, this will help!"`
>   — comma splice between two independent clauses
> - `"Sore throat again?"`
>   — elliptical noun phrase; the `?` won't produce rising intonation
> - `"Wake up with a sore throat?"`
>   — imperative shape disguised as a question; TTS reads it flat
>
> **Tip and CTA structure:** same punctuation rules. Periods between
> independent clauses, not commas.
>
> ✅ Tip: `"Honey coats the throat. It also kills bacteria naturally."`
> ❌ Tip: `"Honey coats the throat, it also kills bacteria naturally."`
> ✅ CTA: `"Save this for the next time you feel sick."`
> ✅ CTA: `"Try this tonight and feel the difference."`
>
> **Naturalness rules (these make Kokoro TTS sound human, not robotic):**
>
> The TTS pipeline does per-segment synthesis: every sentence inside a `text`
> field is sent to Kokoro as a separate utterance, with silence between
> segments scaled to the terminator (`.` = 350 ms, `?`/`!` = 450 ms,
> `...` = 600 ms, em-dash = 200 ms). Lean into this — write copy that *uses*
> punctuation as a delivery instrument.
>
> 1. **Punctuation for breath control.**
>    - Use `.` between every distinct thought (creates a beat / pause).
>    - Use `,` for micro-pauses *within* a thought (no breath).
>    - Use `...` (ellipsis) for dramatic trailing pauses — great in hooks.
>    - Use `—` (em-dash, U+2014) for a sudden pivot mid-sentence.
>    - Example: `"Tired all the time? Here's why... and how to fix it."`
>
> 2. **Two-sentence blocks (HARD limit, enforced by the validator).**
>    No `text` field may contain more than 2 sentences. If a tip needs more
>    detail, write a tighter version — don't pile sentences. The pipeline
>    rejects any section over 2 sentences to prevent breathless TTS.
>
> 3. **Phonetic spelling for hard words** (`pronunciation_hints` field).
>    Kokoro mispronounces several common health terms. Add a
>    `pronunciation_hints` map to any section containing them. Common ones:
>
>    | Word                | Phonetic           |
>    |---------------------|--------------------|
>    | turmeric            | `ter-mer-ik`       |
>    | echinacea           | `ek-uh-nay-shuh`   |
>    | ashwagandha         | `ash-wah-gahn-duh` |
>    | quercetin           | `kwer-suh-tin`     |
>    | elderberry          | `el-der-ber-ee`    |
>    | apple cider vinegar | `ap-ul sigh-der vin-uh-ger` |
>
>    Example:
>    ```json
>    {
>      "text": "Try turmeric tea every morning.",
>      "pronunciation_hints": { "turmeric": "ter-mer-ik" }
>    }
>    ```
>    The pipeline does a word-boundary, case-insensitive substitution before
>    sending the text to Kokoro. You can add hints for any word the model is
>    likely to flub.
>
> 4. **Emotional / delivery cues** (use SPARINGLY — max 1–2 per reel, only
>    on the hook or CTA). Inline bracketed tags that map to per-segment
>    speed + volume adjustments. Kokoro does NOT respect these natively, so
>    the pipeline parses them out and applies the changes itself.
>
>    | Cue          | Effect                                             |
>    |--------------|----------------------------------------------------|
>    | `[soft]`     | Speed × 0.95, normal volume                        |
>    | `[whisper]`  | Speed × 0.93, volume × 0.55 (quiet, intimate)      |
>    | `[excited]`  | Speed × 1.10                                       |
>    | `[serious]`  | Speed × 0.92                                       |
>    | `(pause)`    | Adds +300 ms extra silence at that boundary        |
>
>    Cues apply only to the segment they introduce (until the next terminator).
>
>    Examples:
>    - `"[soft] Wake up tired every day? [excited] Here's the fix!"`
>    - `"Drink this... [whisper] before bed."`
>
> 5. **Numbers and abbreviations**: the pipeline auto-expands these, so write
>    them naturally — `5 mg` → "five milligrams", `Dr.` → "Doctor", `%` →
>    "percent", `&` → "and". Integers 0–100 are spelled out automatically;
>    larger numbers stay as digits (write them out yourself if needed:
>    `"twelve hundred"` instead of `"1200"`).
>
> **Queries rules — this is the most important part:**
> Each section gets **2–3 Pexels search queries** that the renderer
> rotates through to cut a varied B-roll sequence. Queries must be
> *visually evocative*, not abstract.
>
> 1. **Be descriptive and action-oriented.** Show people *doing* things:
>    - Bad: `"ginger tea"`. Good: `"person pouring hot tea into mug closeup"`.
>    - Bad: `"drinking water"`. Good: `"woman drinking water glass slow motion"`.
>
> 2. **Include shot-type / camera-angle hints** so Pexels surfaces visually
>    interesting footage. Mix shot types across a section's queries:
>    - `closeup`, `macro`, `overhead`, `slow motion`, `side profile`,
>      `pov`, `top down`, `cinematic`, `studio shot`.
>
> 3. **For symptoms or body-related content, show the body part.** This is
>    high-retention because viewers self-identify:
>    - "sore throat" → `"person touching throat in pain"`
>    - "headache" → `"person rubbing temples closeup"`
>    - "stomach pain" → `"hand on stomach woman"`
>    - "tired eyes" → `"tired eyes macro shot"`
>    - "back pain" → `"person stretching lower back"`
>
> 4. **Hook queries should be punchy and visually striking** — close-ups,
>    macro, dramatic compositions. The hook is cut faster (1.5–2 s per
>    clip) so the visuals need to grab attention immediately.
>
> 5. **Each query is 3–6 words.** Pexels does poorly with long natural-
>    language queries; keep them as keyword phrases.
>
> ---
>
> ### Example 1 — topic: "5 home remedies for sore throat"
>
> ```json
> {
>   "hook": {
>     "text": "Do you wake up with a sore throat? Skip the pharmacy — your kitchen has the fix.",
>     "queries": [
>       "person touching throat closeup",
>       "woman with sore throat hand on neck",
>       "kitchen herbs spices macro"
>     ]
>   },
>   "tips": [
>     {
>       "text": "Gargle warm salt water for thirty seconds. The salt draws fluid from swollen tissues and soothes the burning.",
>       "queries": [
>         "salt water glass overhead",
>         "person gargling slow motion",
>         "tablespoon salt being poured"
>       ]
>     },
>     {
>       "text": "Stir raw honey and lemon into hot water. Honey coats the throat while lemon's vitamin C supports your immune system.",
>       "queries": [
>         "honey drizzling into mug macro",
>         "lemon slice squeezed closeup",
>         "person sipping warm drink steam"
>       ]
>     },
>     {
>       "text": "Inhale steam from a bowl with eucalyptus oil. Drape a towel over your head and breathe slowly for ten minutes.",
>       "queries": [
>         "steam rising bowl closeup",
>         "eucalyptus leaves wooden table",
>         "person inhaling steam towel"
>       ]
>     }
>   ],
>   "cta": {
>     "text": "Save this for the next time a sore throat hits.",
>     "queries": [
>       "person holding warm mug hands",
>       "wellness self care morning routine"
>     ]
>   }
> }
> ```
>
> ### Example 2 — topic: "benefits of turmeric"
>
> ```json
> {
>   "hook": {
>     "text": "This golden spice has been used for over 4,000 years for one good reason.",
>     "queries": [
>       "turmeric powder bowl macro",
>       "fresh turmeric root sliced closeup",
>       "spices on dark wooden table cinematic"
>     ]
>   },
>   "tips": [
>     {
>       "text": "Turmeric contains curcumin, a natural compound that may help reduce inflammation. Add half a teaspoon to your warm milk.",
>       "queries": [
>         "turmeric milk being stirred mug",
>         "person pouring warm milk closeup",
>         "golden latte overhead"
>       ]
>     },
>     {
>       "text": "It supports digestion by helping the gallbladder produce more bile. Try a pinch in soups or roasted vegetables.",
>       "queries": [
>         "soup simmering pot stove",
>         "person adding spice to pan",
>         "roasted vegetables overhead"
>       ]
>     },
>     {
>       "text": "For better absorption, always pair turmeric with black pepper and a little olive oil.",
>       "queries": [
>         "black pepper grinder macro",
>         "olive oil pouring slow motion",
>         "spices on wooden board top down"
>       ]
>     }
>   ],
>   "cta": {
>     "text": "Save this for the next time you cook.",
>     "queries": [
>       "person cooking kitchen warm light",
>       "hands sprinkling spices into pan"
>     ]
>   }
> }
> ```
>
> ---
>
> Now generate a script for this topic:
>
> **TOPIC: `<YOUR TOPIC HERE>`**

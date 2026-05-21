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

> You are writing a script for a vertical Facebook Reel about health and
> home remedies. The script will be read by a Kokoro TTS narrator at slow,
> deliberate speed (0.88×), so the way you write punctuation IS the way it
> will be delivered.
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
> **Voice & style — this is the most important section. Read it twice.**
>
> The narrator should sound like a knowledgeable friend explaining the
> remedy at coffee, *not* a textbook AND *not* a stuttering bullet list.
> Fragments are a flavor, not the whole dish.
>
> 1. **Fragments are strategic, not constant.**
>    - **Hook**: fragments work great here — they punch
>    - **Tips**: mostly *full sentences* with natural flow; **at most 1**
>      fragment per tip, used for emphasis
>    - **CTA**: 1–2 fragments OK for a dramatic ending
>
>    ❌ Choppy (too many fragments back-to-back):
>      `"Lemon water. First thing. It rehydrates fast... and gives you vitamin C."`
>    ✅ Natural flow:
>      `"Drink lemon water first thing in the morning. It rehydrates your
>        cells fast and gives you a real vitamin C boost."`
>    ✅ Natural flow + ONE emphasis fragment via em-dash:
>      `"Drink lemon water as soon as you wake up — twelve ounces. It
>        rehydrates your cells and delivers a vitamin C boost fast."`
>
> 2. **Sentence length sweet spot.**
>    - Each tip is 2–3 sentences total (not 4–5 fragments).
>    - Each sentence: **8–15 words** is the sweet spot.
>    - Avoid both extremes — no run-ons (>20 words) AND no machine-gun
>      fragments (<4 words in a row).
>
> 3. **Conversational phrasing, not textbook.**
>    ❌ "It activates your vagus nerve and triggers a full body wake-up."
>    ✅ "The cold shock activates your vagus nerve and triggers a full-body wake-up."
>
>    ❌ "Light on your eyes resets your circadian rhythm and shuts off melatonin."
>    ✅ "The light on your eyes resets your circadian rhythm and shuts off melatonin."
>
> 4. **Strategic ellipses (...).** The TTS engine adds a 400 ms pause after
>    `...`, so use it deliberately, not decoratively. Maybe one per reel,
>    usually in the CTA or before a tip's punchline. Don't sprinkle them.
>
> 5. **Em-dashes (—).** Even more sparingly — max 1 per reel. Great for
>    one emphasis fragment inside an otherwise flowing tip.
>
> 6. **Patterns that kill the flow — avoid:**
>    - `"It [verb]. And [verb]."` — chops naturally connected ideas
>    - Three-word fragments back to back
>    - Starting every tip with a bare noun phrase ("Lemon water." /
>      "Morning sunlight." / "Cold water.")
>    - Em-dashes in multiple sentences (one per reel max)
>    - Bracket cues like `[soft]` / `[excited]` — TTS doesn't honor them,
>      they'd be read aloud as the word "soft" / "excited"
>
> 7. **Pronoun variety.** Don't start every sentence with the same word.
>    Mix "you", "your body", "this", "it" — what separates real speech
>    from AI slop is variety in sentence openers.
>
> **Hard rules (validator enforces):**
>
> - **Hook**: 1–3 short sentences. If you pose a question, write it as a
>   *true* syntactic question (starts with `Do`/`Does`/`Why`/`Have`/`Are`/
>   `Want`/etc., or has subject-auxiliary inversion). An elliptical question
>   like `"Sore throat?"` reads flat — but the FULL pattern `"Sore throat?
>   Try this."` works because the second sentence resolves it.
> - **Tips**: EXACTLY 3 tips. Each tip can use 2–5 short fragments (no cap).
> - **CTA**: 1–2 short sentences AND must include the follow-call
>   ("follow for more...", "hit follow for...", "save and follow for...") woven
>   naturally into the sentence — NOT bolted on as a separate "Like and follow
>   for more." line. The renderer does NOT auto-append anything; what you write
>   in the CTA is the final word the viewer hears.
> - **Total spoken length**: 30–45 seconds (~85–125 words *including* short
>   fragments).
> - **Punctuation**: every sentence ends with `.`, `?`, `!`, `...`, or `—`.
>   No comma splices. No question mark on a sentence that isn't a true question.
> - **No medical claims** — use "may help", "supports", "soothes", "is
>   traditionally used for".
> - No emojis, hashtags, markdown, or bracket cues.
>
> **Queries (Pexels search terms):**
> Each section gets **2–3 visually-evocative Pexels queries** (3–6 words
> each). The pipeline cuts each section into 1.5–3 s sub-segments and
> rotates through your queries.
>
> 1. **Be descriptive and action-oriented.** Show people *doing* things:
>    - Bad: `"ginger tea"`. Good: `"person pouring hot tea into mug closeup"`.
> 2. **Include shot-type / camera-angle hints**: `closeup`, `macro`, `overhead`,
>    `slow motion`, `side profile`, `pov`, `top down`, `cinematic`.
> 3. **For symptoms or body-related content, show the body part**: throat,
>    eyes, hands, stomach, temples. High retention because viewers self-identify.
> 4. **Hook queries should be punchy and visually striking** — close-ups,
>    macro, dramatic compositions.
>
> **Phonetic hints (`pronunciation_hints`):**
> Kokoro mispronounces several common health terms. Add a hint map to any
> section that contains one. Common values:
>
> | Word                | Phonetic                       |
> |---------------------|--------------------------------|
> | turmeric            | `ter-mer-ik`                   |
> | echinacea           | `ek-uh-nay-shuh`               |
> | ashwagandha         | `ash-wah-gahn-duh`             |
> | quercetin           | `kwer-suh-tin`                 |
> | elderberry          | `el-der-ber-ee`                |
> | apple cider vinegar | `ap-ul sigh-der vin-uh-ger`    |
>
> Example:
> ```json
> {
>   "text": "Try turmeric tea every morning.",
>   "pronunciation_hints": { "turmeric": "ter-mer-ik" }
> }
> ```
>
> **Numbers and abbreviations** are auto-expanded by the TTS preprocessor —
> write them naturally. `5 mg` becomes "five milligrams"; `Dr.` becomes
> "Doctor"; `%` becomes "percent"; integers 0–100 are spelled out.
>
> ---
>
> **THREE WORKED EXAMPLES — match this style and rhythm:**
>
> ### Example A — topic: "Sore throat remedies"
>
> ```json
> {
>   "hook": {
>     "text": "Got a sore throat? Skip the pharmacy. Try these three natural remedies first.",
>     "queries": [
>       "person touching throat closeup",
>       "woman with sore throat hand on neck",
>       "kitchen herbs spices macro"
>     ]
>   },
>   "tips": [
>     {
>       "text": "Mix one spoon of raw honey with warm water and drink slowly. The honey coats your throat and kills bacteria naturally.",
>       "queries": [
>         "honey drizzling spoon macro",
>         "raw honey jar wooden table",
>         "person taking spoonful honey"
>       ]
>     },
>     {
>       "text": "Gargle warm salt water three times a day for thirty seconds each. The salt pulls inflammation right out of the tissue.",
>       "queries": [
>         "salt being poured spoon",
>         "person gargling slow motion",
>         "glass of warm water closeup"
>       ]
>     },
>     {
>       "text": "Sip ginger tea with fresh lemon throughout the day. It reduces swelling and soothes the burn fast.",
>       "queries": [
>         "ginger tea pouring cup",
>         "lemon slice squeezed closeup",
>         "person holding warm mug hands"
>       ]
>     }
>   ],
>   "cta": {
>     "text": "Try this tonight, and follow for more natural remedies that actually work.",
>     "queries": [
>       "cozy bed morning light",
>       "person stretching getting out of bed"
>     ]
>   }
> }
> ```
>
> ### Example B — topic: "Waking up tired"
>
> ```json
> {
>   "hook": {
>     "text": "Waking up tired every morning? Here are three morning boosts that actually fix it.",
>     "queries": [
>       "tired woman rubbing eyes morning bed closeup",
>       "woman yawning slow motion closeup",
>       "alarm clock bedside table morning light"
>     ]
>   },
>   "tips": [
>     {
>       "text": "Drink twelve ounces of lemon water within ten minutes of waking up. It rehydrates your cells fast and gives you a clean vitamin C boost.",
>       "queries": [
>         "person pouring lemon water glass macro",
>         "hand squeezing lemon into glass slow motion",
>         "woman drinking water morning kitchen closeup"
>       ]
>     },
>     {
>       "text": "Step outside for ten minutes of morning sunlight right after waking. The light on your eyes resets your circadian rhythm and shuts off melatonin.",
>       "queries": [
>         "person stretching arms sunrise outdoor",
>         "morning sunlight through window face closeup",
>         "woman closing eyes feeling sun warmth"
>       ]
>     },
>     {
>       "text": "Splash cold water on your face for fifteen seconds straight. The shock activates your vagus nerve and triggers a full-body wake-up.",
>       "queries": [
>         "woman splashing face cold water",
>         "person washing face bathroom morning",
>         "hands cupping water closeup"
>       ]
>     }
>   ],
>   "cta": {
>     "text": "Save this for tomorrow morning, and follow for more wake-up tips that actually work.",
>     "queries": [
>       "person stretching getting out of bed morning",
>       "morning routine planner notebook hands"
>     ]
>   }
> }
> ```
>
> ### Example C — topic: "Bloating"
>
> ```json
> {
>   "hook": {
>     "text": "Bloated all the time? Here's what's actually causing it — and how to fix it fast.",
>     "queries": [
>       "person holding stomach uncomfortable closeup",
>       "bloated belly hand on abdomen",
>       "woman feeling sick stomach"
>     ]
>   },
>   "tips": [
>     {
>       "text": "Cut out all soda, even diet versions. The carbonation traps gas in your gut and makes bloating way worse.",
>       "queries": [
>         "carbonated drink poured into glass macro",
>         "soda bottle on table closeup",
>         "bubbles fizzy drink slow motion"
>       ]
>     },
>     {
>       "text": "Chew each bite of food at least twenty times before swallowing. Half your bloating comes from air you're swallowing without realizing it.",
>       "queries": [
>         "person eating slowly closeup mouth",
>         "fork lifting food macro",
>         "woman chewing food side profile"
>       ]
>     },
>     {
>       "text": "Drink peppermint tea after every meal. It relaxes your digestive muscles and helps trapped gas release naturally.",
>       "queries": [
>         "peppermint leaves macro",
>         "person pouring tea cozy kitchen",
>         "warm tea cup steam closeup"
>       ]
>     }
>   ],
>   "cta": {
>     "text": "Pick just one and start today, then follow for more daily gut health hacks.",
>     "queries": [
>       "person preparing healthy meal kitchen",
>       "wellness routine morning hands"
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

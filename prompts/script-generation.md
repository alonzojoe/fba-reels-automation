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
> The narrator should sound like a knowledgeable friend leaning in,
> *not* a textbook. The TTS engine adds breath/pause between every
> sentence based on the punctuation you use — so write copy that *uses*
> punctuation as delivery, not as grammar.
>
> 1. **Radical sentence shortening.** Most sentences should be 3–8 words.
>    Any sentence over 12 words must be split.
>
>    ❌ "Drink twelve ounces of lemon water within ten minutes of waking. It
>        rehydrates your cells and gives a fast vitamin C boost."
>    ✅ "Drink lemon water. Twelve ounces. Right when you wake up. It
>        rehydrates your cells... and gives a vitamin C boost."
>
> 2. **Use fragments like a real person.** Spoken English is full of
>    fragments. So is good reel copy.
>
>    ✅ `"Tired every morning? Same."`
>    ✅ `"Three tips. Try them tomorrow."`
>    ✅ `"Lemon water. First thing. Trust me."`
>
> 3. **Strategic ellipses (...) for rhythm and weight.** Especially powerful:
>    - Before the punchline of a tip
>    - Between cause and effect
>    - In the CTA for emotional weight
>
>    The TTS engine adds an **800 ms** pause after `...`, so use it
>    deliberately, not decoratively.
>
>    ✅ "Splash cold water on your face... and feel your whole body wake up."
>    ✅ "Save this tonight... your future self will thank you."
>
> 4. **Conversational phrasing, not textbook.** Replace clinical phrasing
>    with how a friend would explain it over coffee.
>
>    ❌ "It activates your vagus nerve and triggers a full body wake-up."
>    ✅ "It wakes up your nervous system. Fast."
>
>    ❌ "Light on your eyes resets your circadian rhythm and shuts off melatonin."
>    ✅ "Sunlight tells your brain... it's time to wake up."
>
> 5. **Pronoun variety.** Don't start every sentence with the same word.
>    Mix "you", "your body", "this", "it" — and use fragments to skip the
>    subject entirely. Variety in sentence-openers is what separates human
>    speech from AI slop.
>
> 6. **Soft / excited delivery comes from STRUCTURE, not tags.** The TTS
>    engine does NOT support bracket cues like `[soft]` or `[excited]` —
>    they would be read aloud literally. Get those effects by:
>    - Soft / intimate → short sentences + ellipses ("Honey. One spoon. Trust me…")
>    - Excited / punchy → exclamation marks + fragments ("It works! Try it!")
>    - Authoritative → declarative sentences + periods ("This is why.")
>
> **Hard rules (validator enforces):**
>
> - **Hook**: 1–3 short sentences. If you pose a question, write it as a
>   *true* syntactic question (starts with `Do`/`Does`/`Why`/`Have`/`Are`/
>   `Want`/etc., or has subject-auxiliary inversion). An elliptical question
>   like `"Sore throat?"` reads flat — but the FULL pattern `"Sore throat?
>   Try this."` works because the second sentence resolves it.
> - **Tips**: EXACTLY 3 tips. Each tip can use 2–5 short fragments (no cap).
> - **CTA**: 1–2 short sentences.
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
>     "text": "Sore throat? Try this... before reaching for medicine.",
>     "queries": [
>       "person touching throat closeup",
>       "woman with sore throat hand on neck",
>       "kitchen herbs spices macro"
>     ]
>   },
>   "tips": [
>     {
>       "text": "Honey. One spoon. It coats your throat... and kills bacteria naturally.",
>       "queries": [
>         "honey drizzling spoon macro",
>         "raw honey jar wooden table",
>         "person taking spoonful honey"
>       ]
>     },
>     {
>       "text": "Salt water gargle. Warm. Three times a day. The salt pulls out inflammation.",
>       "queries": [
>         "salt being poured spoon",
>         "person gargling slow motion",
>         "glass of warm water closeup"
>       ]
>     },
>     {
>       "text": "Ginger tea with lemon. Sip it slowly. It reduces swelling fast.",
>       "queries": [
>         "ginger tea pouring cup",
>         "lemon slice squeezed closeup",
>         "person holding warm mug hands"
>       ]
>     }
>   ],
>   "cta": {
>     "text": "Try this tonight... and wake up feeling better.",
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
>     "text": "Waking up tired every day? Three fixes. They actually work.",
>     "queries": [
>       "tired woman rubbing eyes morning bed closeup",
>       "woman yawning slow motion closeup",
>       "alarm clock bedside table morning light"
>     ]
>   },
>   "tips": [
>     {
>       "text": "Lemon water. First thing. It rehydrates fast... and gives you vitamin C.",
>       "queries": [
>         "person pouring lemon water glass macro",
>         "hand squeezing lemon into glass slow motion",
>         "woman drinking water morning kitchen closeup"
>       ]
>     },
>     {
>       "text": "Morning sunlight. Ten minutes. It tells your brain... it's time to wake up.",
>       "queries": [
>         "person stretching arms sunrise outdoor",
>         "morning sunlight through window face closeup",
>         "woman closing eyes feeling sun warmth"
>       ]
>     },
>     {
>       "text": "Cold water on your face. Fifteen seconds. It activates your whole nervous system.",
>       "queries": [
>         "woman splashing face cold water",
>         "person washing face bathroom morning",
>         "hands cupping water closeup"
>       ]
>     }
>   ],
>   "cta": {
>     "text": "Save this. Try it tomorrow... your body will thank you.",
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
>     "text": "Bloated all the time? Here's what's really going on.",
>     "queries": [
>       "person holding stomach uncomfortable closeup",
>       "bloated belly hand on abdomen",
>       "woman feeling sick stomach"
>     ]
>   },
>   "tips": [
>     {
>       "text": "Ditch the soda. Even diet. The bubbles trap gas in your gut.",
>       "queries": [
>         "carbonated drink poured into glass macro",
>         "soda bottle on table closeup",
>         "bubbles fizzy drink slow motion"
>       ]
>     },
>     {
>       "text": "Chew slower. Way slower. Half your bloating comes from swallowed air.",
>       "queries": [
>         "person eating slowly closeup mouth",
>         "fork lifting food macro",
>         "woman chewing food side profile"
>       ]
>     },
>     {
>       "text": "Try peppermint tea. After meals. It relaxes your digestive muscles... and releases gas.",
>       "queries": [
>         "peppermint leaves macro",
>         "person pouring tea cozy kitchen",
>         "warm tea cup steam closeup"
>       ]
>     }
>   ],
>   "cta": {
>     "text": "Pick one. Start today. Feel the difference in a week.",
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

# Contributing

## Commit message conventions

This repo uses **conventional-commit-style prefixes** on every commit. Each
change (code, doc, tooling, asset) is committed at a logical boundary with a
prefix that describes its category.

### Prefixes

| Prefix      | When to use                                                                   |
| ----------- | ----------------------------------------------------------------------------- |
| `feat:`     | New user-visible feature, behavior, or capability                             |
| `fix:`      | Bug fix — the previous behavior was broken                                    |
| `refactor:` | Code restructure with no behavior change                                      |
| `perf:`     | Performance improvement (no behavior change)                                  |
| `docs:`     | README, prompt files, CONTRIBUTING, design specs, inline doc strings          |
| `test:`     | Adding or fixing tests, audition / smoke-test scripts                         |
| `chore:`    | Tooling, deps, build, sample data, CI, gitignore, formatting                  |
| `style:`    | Whitespace, naming, comment-only changes (no semantics)                       |
| `revert:`   | Reverting a prior commit                                                      |

### Optional scope

Add a scope in parens when one module clearly owns the change. Common scopes
in this repo:

- `tts`     — `pipeline/tts.py` (Kokoro voice synthesis)
- `script`  — `pipeline/script.py` (script JSON load + validation)
- `footage` — `pipeline/footage.py` (Pexels search + download + cut planning)
- `captions`— `pipeline/captions.py` (ASS subtitle generation)
- `assemble`— `pipeline/assemble.py` (ffmpeg final composition)
- `reel`    — `reel.py` (CLI entry point)
- `prompt`  — `prompts/*`
- `sample`  — `sample_*.json` and the audition test
- `repo`    — top-level files (gitignore, env example, etc.)

### Examples

```
feat(tts): per-segment Kokoro calls with punctuation-driven silences
fix(footage): retry short query when Pexels returns 0 results
docs(prompt): teach LLM the queries-list + body-part shot rules
chore(repo): add ffmpeg-full env var hints to .env.example
refactor(reel): hoist outro handling out of the section loop
test(tts): naturalness A/B audition script
```

### When to commit

Commit at logical boundaries — one cohesive change per commit. Don't bundle a
prompt update + a footage refactor + a bug fix into one. If a single feature
naturally touches several files (e.g. a flag added end-to-end), one commit is
fine; if you find yourself listing more than ~3 unrelated things in the
message body, split it.

### What not to commit

- `.env` (real API keys) — gitignored
- `work/` — per-run scratch directory, gitignored
- `out/` — render artifacts, gitignored
- Large model downloads — Kokoro/whisper caches stay in their own dirs


# contents/

This folder contains all reel script JSON files. Each file is a separate reel topic — drop a new `sample_<topic>.json` here and `reel.py` will pick it up.

## Rendering a script

```bash
python3 reel.py --script <topic>
```

The `--script` flag accepts any of these forms (all resolve to the same file):

```bash
python3 reel.py --script sore_throat
python3 reel.py --script sample_sore_throat
python3 reel.py --script sample_sore_throat.json
python3 reel.py --script contents/sample_sore_throat.json
```

## Listing available scripts

```bash
python3 reel.py --list
```

## Adding a new script

1. Open `prompts/script-generation.md` and follow its instructions to generate a new script JSON.
2. Save the file as `contents/sample_<topic>.json`.
3. Run `python3 reel.py --script <topic>`.

Outputs land at `out/<topic>/final.mp4` so renders don't overwrite each other.

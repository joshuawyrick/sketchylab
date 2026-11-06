# Sketchy Lab

A standalone prompt-testing lab for Sketchy Robotics themes. Import theme zips (the same format the booth uses),
keep a library of reference faces, and run every combination's prompt across many image models at once through
[OpenRouter](https://openrouter.ai). Keep the winners, export the theme as a zip, import it into the booth.

- **Theme builder** — pick or start a theme, choose its foundation, audience (family / adult 18+) and head style, and
  describe it. An AI (your OpenAI account, or any OpenRouter text model) writes each combination's theme section on top of
  the foundation; every draft is tested on the faces and image models you tick. ★ Keep the winners (the prompt and model
  are saved into the theme, the first keep becomes the thumbnail), then "Write & test every combination not kept yet" retries
  only the rest — the AI sees the kept prompts and its previous attempt, plus an optional note per combination. Edit & test a
  draft by hand, un-keep, test the kept prompts again, import/replace from a zip, and export the finished theme for the booth.
- **Prompt test** — 1–4 prompts × 1–4 foundations × models × quality levels, all at once, each result labeled; one prompt
  and one foundation works as a quick scratchpad. Scores, hover zoom and a side-by-side compare strip.
- **Full prompt** — every result has a "Full prompt" button: the exact, complete text the image model got (foundation and prompt shown
  separately, copied as one), plus the model, the settings sent (quality, size, content filter… after any the model refused), and the
  pictures sent with it. Settings are recorded for images made from this version on; the prompt is exact for every image.
- **Foundations** — the "how" texts put in front of every prompt, and the refine prompt.
- **Settings** — keys, the live model list (filter, favorites, hide), likeness judge and default prompt writer, run defaults, cost log CSV.
- **Plotter Studio** (`/studio/`) — a preset test version of the booth's Plotter Studio for a DexArm (Chrome + USB). The speed and drawing settings are hidden: pick a numbered preset, draw, rate it, delete the losers. "Copy results for Claude" exports everything, and "Add new presets" takes a new batch. Deleted presets stay on record, and settings already tried can't be added again. The starting 10 are in `server/plotter-presets.json`. (Its page, `public/studio/index.html`, was made in the Replit project and is not in this repo yet.)

Exports (`bake=1`) put each combination's foundation in front of its prompt, so the booth draws exactly what was tested,
and translate model names for the booth (which calls OpenAI directly): `openai-direct/x` and `openai/x` become `x`;
models the booth can't run are left out of `theme.txt` with a comment.

## Running on Replit

1. Import this repo into a new Replit app (Node.js). Run command: `npm start` (or `node server/index.js`).
2. Secrets:
   - `OPENROUTER_API_KEY` — from openrouter.ai → Keys. Runs are billed to that key's credit.
   - `ADMIN_PASSWORD` — the page's password (default `sketchy`).
   - optional `LAB_PARALLEL` — generations running at once (default 4).
3. Add Replit **App Storage** (Object Storage) so themes, faces and results survive redeploys. If the default bucket isn't
   picked up, set Secret `OBJECT_STORAGE_BUCKET` to the bucket name.
4. Publish. The app is one page at `/`.

## Zip format

One folder per theme; inside it one prompt file per combination (`single-male.md`, `single-female.md`, `two-males.md`,
`two-females.md`, `male-left-female-right.md`, `female-left-male-right.md`, `male-pet.md`, `female-pet.md`), an optional
`thumbnail.png`, and an optional `theme.txt` with `key: value` lines (kept as-is and exported back out).

## Tests

`bash test/run.sh` starts a fake OpenRouter/OpenAI (`test/fakeor.js`) and the server on :3457, then runs the Playwright
test `test/builder.py`: the Theme builder end to end, the export, and a Prompt test run.
`test/presets.py` covers the Plotter Studio preset page (run it against a server on :3461). Nothing in the tests touches the real OpenRouter or OpenAI.

# Sketchy Lab

A standalone prompt-testing lab for Sketchy Robotics themes. Import theme zips (the same format the booth uses),
keep a library of reference faces, and run every combination's prompt across many image models at once through
[OpenRouter](https://openrouter.ai). Keep the winners, export the theme as a zip, import it into the booth.

- **Image lab** — pick a theme, give combinations a face, tick models, run. Results are kept per theme (★ star the keepers;
  "Clear" leaves starred ones). "Use this prompt" writes a result's prompt back into the theme; "Make thumbnail" sets the tile picture.
- **Generator studio** — one prompt, one face, any models; a scratchpad for writing prompts.
- **Themes** — import/export zips, edit prompts in place.
- **Models & settings** — the live list of image models from OpenRouter (filter, tick defaults), quality/resolution/aspect defaults, cost log CSV.

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

`bash test/run.sh` starts a fake OpenRouter (`test/fakeor.js`) and the server on :3457, then runs `test/lab.py` (Playwright).
Nothing in the tests touches the real OpenRouter.

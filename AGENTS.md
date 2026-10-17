# Lecture publication

- This repository is the existing static GitHub + Netlify lecture site. Preserve its hosting identity, lecture-one pages and unobtrusive Netlify feedback form.
- `lesson-2/` contains the prompt-led handout; `lesson-2/earnings-review/` is a static projection of a sealed real local run. Do not add fake progress, runtime credentials, browser model requests or a button claiming to execute the local worker online.
- Company choices must reflect the six actual PDFs in the materials. Publish a company's review only when it has its own verified run bound to the exact PDF hash. Other companies display an explicit empty state.
- Keep historical usage, elapsed time, feedback and per-call model identity accurate. The preset selector describes local options; it does not change the model used by a historical example.
- `lesson-2/publication.json` binds the published artifacts to their source hashes. Preserve original numerical comparison and evidence files; publish only the reviewed public projection, never raw credentials, private provider logs or author machine paths.
- For publication checks, verify real HTTP pages, relative navigation, archives and PDF evidence; drive the UI at desktop and narrow mobile widths. Tests must not spend model quota or submit feedback.

# Lecture one product

- The published product is owned here: `demo.html`, `assets/lesson-one-demo.js`, shared rules in `assets/lesson-one-workflow.mjs`, and `netlify/functions/`. Do not overwrite it with an older workshop export. First-lecture handout source is now owned in `handout/`; follow its `AGENTS.md`, rather than exporting the older workshop handout.
- Preserve the six archived raw outputs and recorded grades in `assets/lesson-one-history.json`. Display corrected-rule recomputation separately. Historical tool receipts contain only last-response tokens, not total tokens.
- New locator runs use the complete 207-page `netlify/data/report-full-text.txt`; never crop it to target pages. Bind current jobs to its `report_sha256`, separately from the archived `window_sha256`. Preserve the old 60–75 page window for historical reproduction and label its range.
- Live runs require the teacher's own SiliconFlow key. Keep it only in page/request memory, never browser storage, job records, logs or a site-wide fallback credential. Browser code submits to this site's background function.
- The six approaches compare workflow stages. Live 03/04 use this session's latest passing 02 job; live 05/06 use its latest passing 04 job. Re-running 02/04 invalidates affected downstream results. Historical inputs are for viewing only. Never accept client-supplied financial state or infer earlier passes.
- New tool runs sum actual usage across calls and retain missing-usage status. Unit grading checks both periods. The two live locator variants share one prompt and output schema; historical prompts retain their original hints.
- Run `npm test` for numerical, prerequisite, usage and job regressions. `node tests/preview.mjs` starts a local HTTP/browser fixture with no paid calls. Do not alter lecture-one handouts or lesson two during a product-only change.

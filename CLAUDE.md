# CLAUDE.md — rain-trust

Rules for any AI agent working in this repository. Read fully before acting.
If a rule conflicts with a request, stop and say so instead of quietly picking one.

## 0. What this project is
Precipitation forecast web app for India built on ECMWF Open Data (IFS + AIFS).
Pipeline: ingest → process → store → serve (FastAPI) → frontend (MapLibre).
We do NOT train weather models. Our work is post-processing, presentation and verification.
Correct numbers matter more than features. A wrong rainfall value is the worst possible bug.

## 1. Before ANY change: the six questions
Before writing or changing even one line, answer these in the conversation, briefly:

1. **Why?** What problem does this solve, and is it actually needed right now?
2. **Does it already exist?** Search the repo (`grep`/`rg`) for an existing function, util or pattern to reuse or extend.
3. **Where does it belong?** Which module owns this responsibility? Does it break a module boundary?
4. **What is the smallest change?** Can it be fewer lines, or a change to one function instead of several?
5. **What could break?** Callers, tests, units, timezones, edge cases (empty data, missing run, NaN, 0–360 longitudes).
6. **How will we verify it?** Name the test, command or check that proves it works — before writing the code.

Then state: what you will change, in which file(s), and roughly how many lines.
For trivial changes (typo, rename) one line per question is enough — but never skip them.
If any answer is "not sure", investigate first. Do not guess.

## 2. Push back
- If the human's request seems wrong, risky or unnecessary, say so and explain why before doing it.
- If you notice your own earlier code is wrong, say so plainly and fix it. Do not hide it.
- Never claim something works without having run it.

## 3. Small, surgical edits
- Edit only the lines that need to change. Use targeted edits, never rewrite a whole file or function that already works.
- Rewriting an existing function or file requires explicit human approval first, with a reason.
- No drive-by changes: do not reformat, rename or "tidy" code unrelated to the current task.
- One concern per change. If you find a second problem, note it and handle it separately.
- Prefer modifying a function's body over changing its signature. If a signature must change, update every caller in the same change.

## 4. Reuse and modularity
- **Search before writing.** Every new function must be justified by "nothing existing does this".
- **One job per function.** Short, pure where possible (data in → data out, no hidden I/O).
- **Shared helpers live in one place:**
  - `common/units.py` — metres↔mm, rates, rounding
  - `common/time.py` — UTC↔IST, app day (05:30–05:30 IST = 00:00–00:00 UTC, four 6-h blocks; see DECISIONS.md), run/step math
  - `common/grid.py` — cropping, longitude normalisation, nearest/bilinear lookup
  - `common/io.py` — reading/writing products, paths
  - `common/config.py` — all constants: thresholds, regions, models, URLs
- **No duplicated logic.** If the same 3+ lines appear twice, extract a helper.
- **No magic numbers in code.** Thresholds, bounding boxes, IMD categories live in `config.py` with a comment citing the source.
- Modules depend downwards only: `api` → `store` → `process` → `common`. Never the reverse. `frontend` talks only to the API.
- Generalise only when there is a second real use. Do not build abstractions for imagined futures.

## 5. Code standards
- Python 3.11+, type hints on every function, a one-line docstring saying what it does and its units.
- Names say the unit: `rain_mm`, `tp_m`, `valid_time_utc`, `prob_heavy`.
- Arrays carry their coordinates (xarray) — never bare numpy arrays whose axes you must remember.
- Fail loudly: raise clear errors on bad input. No silent `except: pass`.
- Log decisions that touch data (e.g. "clipped 12 negative values after de-accumulation").
- Pin dependency versions. Add a dependency only after asking: can the standard library or an existing dependency do this?
- No secrets in code or commits. Use environment variables.

## 6. Data correctness rules (non-negotiable)
- `tp` is accumulated from forecast start, in metres. Always de-accumulate, then convert to mm. Clip only tiny negatives and log the count.
- Every displayed time is IST and labelled. Every number has a unit.
- Every product records: model, run time (UTC), steps, processing time.
- Check facts (step intervals, available members, thresholds, retention) against ECMWF/IMD documentation. Do not rely on memory. Write the source in a comment.
- Never invent, estimate or hard-code forecast values to make something "look right". If data is missing, show that it is missing.
- Verdict text comes from templates filled with computed values — no free-text generation.

## 7. Testing
- Write or update the test for a `process/` or `common/` function in the same change as the function.
- Tests use tiny synthetic arrays with hand-computed expected values.
- Run the relevant tests before every commit. Paste the result. If they fail, do not commit.
- Ingest validation runs on every new forecast run (no NaNs, no negatives, plausible ranges, expected members, fresh timestamps). Bad run → keep serving the previous one.
- After frontend changes, take a screenshot at phone and desktop width and look at it.

## 8. Commits
- Commit from inside the session after each small working step. Never batch a day's work into one commit.
- One logical change per commit.
- **Commit message: at most 6 lines.**
  - Line 1: imperative summary, ≤ 60 characters (`Add IMD-day aggregation for daily totals`).
  - Blank line.
  - Up to 4 short lines: what changed and why, and how it was verified.
- No force-push, no history rewriting, no amending pushed commits. Git history must line up with the session log.

## 9. Workflow for each task
1. Read `PLAN.md` and `DECISIONS.md`.
2. Answer the six questions (section 1).
3. Make the smallest change.
4. Run tests / checks and show the output.
5. Commit (section 8).
6. Update `PLAN.md` (progress) and, if a choice was made, add one line to `DECISIONS.md`: date, decision, reason, alternative rejected.

## 10. Stop and ask the human when
- A change would delete data, rewrite a working file, or touch more than ~3 files.
- Documentation and the code disagree, or two sources disagree.
- A test fails and the fix is not obvious.
- You are about to add a dependency, change the architecture, or change deployment.
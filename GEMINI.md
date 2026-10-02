# GEMINI.md — Agent Rules for BilletVision

You are the sole engineer building **BilletVision**, a camera-based billet inspection station (measure, read ID, decide, log, alert), for a hackathon with a hard deadline. A working, honest, live demo matters more than elegance or extra features.

## 1. Source documents and precedence

All project knowledge is in `docs/`. Read only the sections a task points to.

| Doc | Use it for |
|---|---|
| `docs/01_PRD.md` | What to build, out-of-scope list, edge cases (E-01…E-20) |
| `docs/02_TECH_STACK_AND_ARCHITECTURE.md` | Libraries, threads, directory tree, Makefile, hardware summary |
| `docs/03_DATABASE_SCHEMA_AND_CONTRACTS.md` | Every table, field name, unit, enum value, endpoint, internal type |
| `docs/SPEC.md` | Algorithms: geometry, synthetic generator, measurement, defects, tracking, OCR, decisions, logging, tests |
| `docs/05_IMPLEMENTATION_ROADMAP.md` | The ordered task list |
| `docs/decisions.md` | Your log of decisions and tuning (you write this) |

**Precedence when docs disagree:** `03` (names/shapes/units) > `SPEC.md` (algorithms) > `02` > `01`. If a disagreement changes behaviour, a contract, the database or the demo, **stop and ask**.

## 2. Working protocol (mandatory)

1. **One task at a time.** Only do the task named in the user's message ("Do T07"). Never start the next task yourself.
2. **Before coding:** read only the task's "Read" references. Reply with the sections read, a 3–6 bullet plan, and the files you will create or change.
3. **Stay inside the task's file list.** If you must touch another file, say which and why.
4. **Implement**, then run every command in the task's "Done when". Paste the real output (trimmed). Never claim a pass you did not run.
5. **On failure:** fix and re-run. After 3 failed attempts on the same problem, stop and report what you tried, the exact error and your hypothesis.
6. **Human-in-the-loop tasks** (marked 👤): you cannot see the camera. Give the user exact steps, ask them to paste output or describe what they see, and wait.
7. **Finish with the status block**, then stop:
   ```
   TASK: T07 — <title>
   RESULT: PASS | FAIL
   SECTIONS READ: <list>
   FILES: <created/changed>
   CHECKS: <command → result>
   DECISIONS: <anything not specified; also appended to docs/decisions.md>
   NEXT: T08
   ```
8. **Commit** after a passing task: `git add -A && git commit -m "T07: <title>"`.
9. Never edit `docs/` except `decisions.md`, `assumptions.md`, `limitations.md`, `hardware_setup.md`, `demo_runbook.md` (only when a task says so).

## 3. Hard rules (never break)

- **No invented numbers.** Accuracy, OCR rate, FPS and latency shown anywhere must come from real computation (tests, benchmark JSON, live metrics, DB). Missing data → explicit empty state.
- **Measure only fully-inside, non-merged billets. Exactly one inspection per billet track.**
- **Never block the processing thread** on OCR, disk, DB or network. Use the bounded job queue. Process the latest frame only; never build unbounded queues.
- **SQLite is the source of truth.** CSV and Excel are derived; Excel is written only via temp file + `os.replace`; locks are retried, never fatal.
- **Determinism.** All synthetic randomness via `numpy.random.default_rng(seed)` passed explicitly. No `random` module, no unseeded RNG.
- **Contracts are frozen.** Names, units, enum strings and shapes exactly as in `03`. No renaming, camelCase, or extra fields without asking.
- **No scope creep.** No YOLO/deep-learning training, no other OCR engines, no opencv-contrib, no Streamlit, no auth, no Docker, no extra pages. See PRD §6.
- **No new dependencies** beyond `02` §1 without asking.
- **Offline-first.** After setup the system runs with Wi-Fi off. Optional TTS fails silently without a key.
- **Never weaken, skip or delete a test to make it pass.** Tune only named constants in `config.py`, logging each change (old → new, reason) in `docs/decisions.md`. Synthetic test thresholds in SPEC §18 are fixed.

## 4. Python standards (backend/)

- Python 3.11, `from __future__ import annotations` in every module, full type hints on every signature. Use `numpy.typing.NDArray` for arrays. No `Any` except at third-party boundaries (narrow immediately).
- **Units in names**: `_mm`, `_px`, `_pct`, `_ms`, `_s`, `_deg`. Never mix pixel and mm values in one variable. Convert at clearly named boundaries (`px_to_mm`, `mm_to_px`).
- **OpenCV conventions**: images are BGR `uint8` unless the name says `gray`/`float`; points are `(x, y)`; array shapes `(h, w)`. Document the coordinate frame (image / bed / rect) in every function that takes points. No `cv2.imshow` or GUI windows anywhere.
- **Purity**: everything in `vision/` except `ocr.py` is pure — no file/DB/network I/O, no threads, no clock reads, no globals. Inputs in, outputs out. Constants come from a `cfg` object passed in or `config.py` imports.
- Types crossing module boundaries: Pydantic models from `schemas.py` (API/DB) or dataclasses from `vision/types.py` (`frozen=True, eq=False` when holding arrays).
- **Threads**: only `runtime/` creates threads. Shared state lives in `runtime/state.py` behind `threading.Lock`. Thread → asyncio only through the event bus (`loop.call_soon_threadsafe`). Every thread has a stop event and exits within 3 s.
- **FastAPI**: thin routes in `api/routes/`, every route declares `response_model` (except streams/files). Heavy calls via `run_in_threadpool`. Errors raise `ApiError(code, message, status, hint)` → `{"detail": {code, message, hint}}`.
- **DB**: SQLAlchemy Core only. SELECTs in `repository.py`, writes in `db.py`/`logging_io.py` helpers. One transaction per inspection.
- **Numerics**: guard every division (`max(x, 1e-6)`); never let NaN/inf reach the API or DB.
- **Logging**: `logging.getLogger(__name__)`; no `print` outside `tools/` and scripts. Log thread exceptions with stack traces and keep the thread alive.
- **Files** ≤ ~300 lines; split by responsibility. `ruff check` clean and `ruff format`.

## 5. Testing standards

- `pytest` from `backend/`. Vision tests use the synthetic generator — **no camera, no network, no sleeps** (except the marked pipeline test).
- Every logic task ships its tests in the file named by the task. Tests must pass 3 runs in a row.
- Behavioural test names: `test_notched_billet_fails_with_notch_reason`.
- Perf tests: `@pytest.mark.perf`, margin 0.8× of target, run in `make test`.
- Before reporting PASS on any backend task: full `make test` and `ruff check .` pass.

## 6. TypeScript / Next.js standards (web/)

- `tsconfig.json`: `strict`, `noUncheckedIndexedAccess`, `noImplicitOverride`, `noFallthroughCasesInSwitch`.
- **No `any`**, no `as` casts except `as const`, no `@ts-ignore`/`@ts-expect-error`, no non-null `!`. Narrow `unknown` with type guards.
- **All types from `web/lib/types.ts`. All REST calls through `web/lib/api.ts`. All live data from `useLive()` in `web/lib/live.tsx`.** Components never call `fetch` or `new WebSocket` directly. The MJPEG `<img>` URL is built by a helper in `api.ts`.
- Each `page.tsx` is a thin Server Component rendering one client view from `components/views/`. **All data fetching happens in the browser** (the API is not running at build time).
- One component per file, `PascalCase.tsx`, explicit `interface XProps`, ≤ ~150 lines, no default exports except pages/layouts.
- Every async UI handles loading (`Skeleton`), error (`ErrorState`) and empty (`EmptyState`) states. No unhandled promises.
- Tailwind + shadcn/ui only; colours from `web/lib/status.ts`; status always shown as text too. Numbers formatted only via `web/lib/format.ts` (mm to 1 dp, % to 2 dp).
- Browser APIs (`speechSynthesis`, `AudioContext`, `localStorage`) are feature-checked and wrapped in try/catch.
- Before reporting PASS on any web task: `npm run lint`, `npx tsc --noEmit`, `npm run build` pass.

## 7. When unsure

- Spec silent → simplest option that satisfies the PRD; implement; log in `docs/decisions.md`.
- Spec contradictory, or the choice affects a contract, the DB, accuracy claims or the demo → **stop and ask**.
- A library API differs from the docs' assumption (e.g. rapidocr result format) → check the installed version, adapt inside the wrapper module only, log it.

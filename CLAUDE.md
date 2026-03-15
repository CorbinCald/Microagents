# Microagents

Python CLI that generates entire codebases by orchestrating LLMs via OpenRouter.

## CRITICAL: All changes to code, specs, and tests MUST align between eachother. If you make a change to code, specs, or tests, the changes must be synchronized to the other two components.

## How to run

```bash
export OPENROUTER_API_KEY="sk-..."
pip install -r requirements.txt
python main.py "Build a markdown link checker CLI in Python"
```

Output goes to `output/<project_name>/`. Logs go to `logs/`.

## File overview

- **main.py** — Entry point. Arg parsing (argparse), runs pipeline stages sequentially.
- **orchestrator.py** — Calls Gemini 3.1 Pro via OpenRouter, parses file skeletons and tool_calls from the text response.
- **microagent.py** — Dispatches all tasks to Mercury 2 in parallel via `asyncio.gather()`. Retry with exponential backoff. Fire-and-forget summary calls.
- **assembler.py** — Replaces `<<TASK_ID>>` placeholders with microagent code, handles indentation, writes files + `build_report.json` + `README.md`.
- **logger.py** — Sets up Python `logging` with two handlers: console (INFO, `[HH:MM:SS]` format) and file (DEBUG, full prompts/responses). Writes `logs/failed_TASK_ID.log` on task failure.
- **prompts.py** — All prompt templates as plain f-strings. The orchestrator system prompt includes multishot examples (embedded directly). Edit this file to change LLM behavior.
- **config.yaml** — Models, temperatures, max tokens, retry settings, output paths. Edit this to change models or tuning.
- **SPECS.md** — Full technical specification: architecture, pipeline, protocols, data structures, and design constraints.

## Key patterns

- **OpenAI SDK → OpenRouter**: All LLM calls use the `openai` package with `base_url` pointed at OpenRouter. No custom HTTP.
- **asyncio.gather for parallelism**: All microagent tasks are independent and dispatched concurrently. Summaries are fire-and-forget via `asyncio.create_task()`.
- **Text parsing, not native tool calling**: The orchestrator outputs skeletons + JSON tool_calls as text. The harness parses this with string splitting and regex. Simpler and model-agnostic.
- **Plain f-strings for prompts**: No Jinja, no template engines. All prompts are in `prompts.py`.
- **Config dict passed around**: Config is loaded once in `main.py`, passed as a dict to every function that needs it. No global state, no singletons.
- **Python logging with 2 handlers**: Console handler (INFO+) for clean progress, file handler (DEBUG) for full traces. No third-party logging.
- **Three dataclasses**: `TaskSpec`, `TaskResult`, `FileSpec`. No Pydantic, no attrs.

## Config changes

To change a model: edit the `model` field under `orchestrator`, `microagent`, or `summary` in `config.yaml`.

To change temperature or token limits: edit the corresponding fields in `config.yaml`.

API key is read from the env var named in `config.yaml` → `api.key_env` (default: `OPENROUTER_API_KEY`).

## Error handling

- Failed microagent tasks: retried with exponential backoff and temperature escalation (+0.10 per retry). On final failure: logged to `logs/failed_TASK_ID.log`, recorded in `build_report.json`, placeholder left as a comment in output.
- Orchestrator failure: retried once, then exits with code 1.
- Summary failures: silently caught, never block the pipeline.
- The pipeline never crashes on individual task failures — it always produces partial output.

## Self-improvement

Generated projects include `build_report.json` mapping task_id → file + line range. An LLM debugging a runtime error can trace a stack trace line number to the exact task that generated that code, then find the full prompt/response in `logs/`.

## Dependencies

Only two: `openai` (for OpenRouter) and `pyyaml` (for config). Python 3.13+.

## Models

As of March 2026, this project uses `google/gemini-3.1-pro-preview` (orchestrator) and `inception/mercury-2` (microagents + summaries). Maintain these models unless the user asks to change them. If a model becomes unavailable or you need to suggest alternatives, check https://openrouter.ai for current model availability and pricing.

## Constraints

- No over-engineering. No abstract base classes, no plugin systems, no middleware chains.
- Prefer stdlib over third-party packages.
- Keep the file count minimal — 6 Python files + config.yaml, all top-level.
- If a simple solution meets a requirement, use it.

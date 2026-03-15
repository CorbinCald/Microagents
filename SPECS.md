# Microagents -- Technical Specification

**Version:** 1.0
**Last updated:** 2026-03-15
**Status:** Active

---

## 1. Overview

### 1.1 Purpose

Microagents is a Python CLI tool that generates complete codebases from natural-language project descriptions by orchestrating LLMs via [OpenRouter](https://openrouter.ai). An orchestrator LLM decomposes the project into a skeleton of files with placeholder tasks, then dispatches all tasks in parallel to fast microagent LLMs. Results are assembled into a complete, runnable project.

### 1.2 Scope

The system is scoped to **project creation only**. It doesn't edit existing projects (yet!).

### 1.3 Terminology

| Term | Definition |
|------|------------|
| Orchestrator | The LLM that decomposes a project description into file skeletons and task specifications |
| Microagent | An LLM instance that implements a single task specification, producing code |
| Skeleton | A lightweight file template containing structural code and `<<TASK_ID>>` placeholders |
| Placeholder | A `<<TASK_ID: description>>` marker in a skeleton, replaced by microagent output during assembly |
| Task spec | A structured specification (`TaskSpec`) dispatched to a microagent |
| Assembly | The process of replacing placeholders with microagent output and writing final files |

### 1.4 Keywords

The keywords MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

---

## 2. Architecture

### 2.1 System Diagram

```
User --> [main.py] --> [orchestrator.py] --> Gemini 3.1 Pro (OpenRouter)
                                                   |
                                         skeleton + tool_calls (text)
                                                   |
                                             [orchestrator.py] parses
                                                   |
                                       file_skeletons{} + task_specs[]
                                                   |
                    [microagent.py] --> asyncio.gather --> Mercury 2 (OpenRouter) x N
                           |  (as each completes)            |  (fire-and-forget)
                    task_results{}              [Mercury 2 --> one-line summary --> console]
                           |
                    [assembler.py] --> replace placeholders
                           |
                    output_dir/ (files + build_report.json + README.md)
```

### 2.2 LLM Roles

The system uses three LLM roles, all accessed via OpenRouter:

| Role | Model | Temperature | Max Tokens | Purpose |
|------|-------|-------------|------------|---------|
| Orchestrator | `google/gemini-3.1-pro-preview` | 1.0 | 32000 | Skeleton generation + task decomposition |
| Microagent | `inception/mercury-2` | 0.1 (+0.1/retry) | 32000 | Code implementation per task |
| Summarizer | `inception/mercury-2` | 0.0 | 250 | One-sentence progress summaries |

All LLM calls MUST use the `openai` Python SDK with `base_url` set to the OpenRouter endpoint. No custom HTTP clients.

---

## 3. Pipeline

The pipeline executes seven stages sequentially. Stages 4 and 4B are internally parallel.

### 3.1 Stage 1 -- Load Configuration

1. Read `config.yaml` and parse with PyYAML.
2. Resolve the API key from the environment variable named in `api.key_env`.
3. Validate that required configuration fields exist.
4. Set up logging (console + file handlers).

No LLM call. MUST exit with error if config is missing or API key is unset.

### 3.2 Stage 2 -- Generate Skeleton

1. Send the project description to the orchestrator LLM.
2. The orchestrator returns a single text response containing:
   - File skeletons with `# --- path/to/file.ext ---` markers and `<<TASK_ID: description>>` placeholders.
   - A JSON `tool_calls` block with task specifications.

Single LLM call. Not parallelizable. On failure: retry once, then exit with code 1.

### 3.3 Stage 3 -- Parse Orchestrator Response

Parse the text response into structured data:

1. Split on `# --- ` (or `// --- `) markers into `dict[filename, skeleton_text]`.
2. Extract the JSON block (last code fence containing `"tool_calls"`) into `list[TaskSpec]`.
3. Validate that every `<<TASK_ID>>` placeholder has a matching `TaskSpec`, and vice versa.

Pure string parsing. On parse failure: log raw response, print error, exit with code 1.

### 3.4 Stage 4 -- Dispatch Microagent Tasks (Parallel)

All tasks are independent. MUST dispatch all concurrently via `asyncio.gather()`.

For each `TaskSpec`:

1. Build prompt from the task's instruction, inputs, outputs, and context.
2. Call the microagent LLM via OpenRouter.
3. On success: strip markdown code fences if present, return code.
4. On failure: retry with exponential backoff and temperature escalation (see S11).
5. On final failure: write `logs/failed_TASK_ID.log`, record as failed, continue.

### 3.5 Stage 4B -- Summarize Microagent Output (Fire-and-Forget)

As each microagent completes successfully, dispatch a non-blocking call (`asyncio.create_task()`) to summarize the code in one sentence for the console.

- Summary failures MUST be silently caught.
- On failure, log `[TASK_ID] (completed)` instead of a summary.
- Summaries MUST NOT block the pipeline.

### 3.6 Stage 5 -- Assemble Output

For each file skeleton:

1. Find all `<<TASK_ID: description>>` placeholders.
2. Replace each with the corresponding microagent output.
3. Match indentation: detect leading whitespace of the placeholder line, prepend to every line of the replacement.
4. For failed tasks: replace the placeholder with a comment in the target language's syntax.
5. Track line numbers for `build_report.json`.

### 3.7 Stage 6 -- Write Output

1. Create the output directory at `{output.dir}/{project_slug}/`.
2. Write each assembled file.
3. Generate and write `build_report.json` (see S9.1).
4. Generate and write `README.md` for the generated project (see S9.2).

### 3.8 Stage 7 -- Log Final Summary

Print a single summary line to console:

```
[HH:MM:SS] Generated N files, X/Y tasks succeeded. Output: ./output/project_name/
```

---

## 4. Orchestrator Protocol

### 4.1 Skeleton Format

The orchestrator MUST output file skeletons using the following conventions:

1. Each file begins with a marker line: `# --- path/to/file.ext ---` (or `// ---` for languages using `//` comments).
2. Skeletons contain structural code (imports, class definitions, function signatures, constants, wiring) written directly by the orchestrator.
3. Implementation bodies are replaced with `<<TASK_ID: description>>` placeholders.
4. Each placeholder MAY be followed by comment lines (`# Task:`, `# Inputs:`, `# Outputs:`, `# Context:`).
5. Task IDs MUST use a short language prefix and number (e.g., `PY_1`, `TS_1`, `RS_1`).

### 4.2 Tool Calls Format

After all skeletons, the orchestrator MUST output a JSON block inside a `` ```json `` code fence with the following structure:

```json
{
  "tool_calls": [
    {
      "id": "call_TASK_ID",
      "type": "function",
      "function": {
        "name": "microagent",
        "arguments": {
          "task_id": "TASK_ID",
          "instruction": "What to implement",
          "inputs": "Exact input parameters and types",
          "outputs": "Exact return type or side effect",
          "context": "Only the immediately relevant context"
        }
      }
    }
  ]
}
```

### 4.3 Parsing Rules

1. **JSON extraction:** Find the last `` ```json `` code fence containing `"tool_calls"`.
2. **Skeleton extraction:** Everything before the JSON block start.
3. **File splitting:** Regex `^(?:#|//) --- (.+?) ---.*$` (multiline).
4. **Placeholder extraction:** Regex `<<(\w+):`.
5. **Validation:** Skeleton task IDs and spec task IDs MUST match. Mismatches are logged as warnings but do not halt the pipeline.

### 4.4 Task Independence

All tasks MUST be completely independent. Tasks run in parallel on separate agents that cannot see each other's output. A task that depends on another task's result will produce incorrect code.

The orchestrator handles naming consistency by defining all function, parameter, and class names in the skeleton. Microagents implement bodies only.

---

## 5. Microagent Protocol

### 5.1 Prompt Format

The microagent system prompt instructs the LLM to:

- Return only raw implementation code (no markdown fences, no explanations).
- Write code as if starting at column 0 (indentation is handled by assembly).
- Follow exact types, names, and signatures from the task specification.

The user prompt MUST be structured as:

```xml
<task>
<instruction>{instruction}</instruction>
<inputs>{inputs}</inputs>
<outputs>{outputs}</outputs>
<context>{context}</context>
</task>
```

### 5.2 Response Processing

1. Strip markdown code fences if present (regex: `^\s*```\w*\n(.*?)\n```\s*$`).
2. Return the cleaned code string.

### 5.3 Retry Behavior

On failure, retry with:

- **Exponential backoff:** Delays of `base_delay * 2^attempt` seconds (default: 1s, 2s, 4s).
- **Temperature escalation:** `+temp_increment` per retry (default: +0.10).
- **Maximum retries:** `retry.max_retries` (default: 3).

Total attempts = `max_retries + 1` (1 initial + 3 retries by default).

On all retries exhausted: write a failure log (see S10.3), return a `TaskResult` with `status="failed"` and `code=""`.

---

## 6. Data Structures

Three dataclasses, defined in `orchestrator.py`. No Pydantic, no attrs.

### 6.1 TaskSpec

```python
@dataclass
class TaskSpec:
    task_id: str       # e.g. "PY_1"
    instruction: str   # what to implement
    inputs: str        # exact input params/types
    outputs: str       # exact return type or side effect
    context: str       # only immediately relevant context
```

### 6.2 TaskResult

```python
@dataclass
class TaskResult:
    task_id: str
    code: str          # code returned by microagent (empty string on failure)
    status: str        # "ok" or "failed"
    error: str | None  # None on success, error message on failure
    duration: float    # seconds
```

### 6.3 FileSpec

```python
@dataclass
class FileSpec:
    path: str          # relative path like "src/main.rs"
    skeleton: str      # raw skeleton text with placeholders
    task_ids: list[str]  # which task_ids appear in this file
```

---

## 7. Configuration

All tunable parameters live in `config.yaml`.

### 7.1 Schema

```yaml
api:
  base_url: "https://openrouter.ai/api/v1"
  key_env: "OPENROUTER_API_KEY"       # env var name (key is NOT stored in this file)

orchestrator:
  model: "google/gemini-3.1-pro-preview"
  temperature: 1
  max_tokens: 32000

microagent:
  model: "inception/mercury-2"
  temperature: 0.1
  max_tokens: 32000

summary:
  model: "inception/mercury-2"
  temperature: 0.0
  max_tokens: 250

retry:
  max_retries: 3
  base_delay: 1.0                     # seconds, doubles each retry
  temp_increment: 0.10                # increase temperature by this much per retry

output:
  dir: "output"
  log_dir: "logs"
```

### 7.2 Usage

- To change a model: edit the `model` field under the relevant role.
- To change temperature or token limits: edit the corresponding fields.
- The API key is read from the environment variable named in `api.key_env` (default: `OPENROUTER_API_KEY`). The key itself MUST NOT be stored in config.

---

## 8. Assembly Rules

### 8.1 Placeholder Replacement

1. Scan each skeleton line for placeholders matching `^(\s*)<<(\w+):\s*(.+?)>>\s*$`.
2. Skip any follow-up comment lines matching `^\s*(?:#|//)\s*(?:Task|Inputs|Outputs|Context):`.
3. For successful tasks: insert the microagent's code, prepending the placeholder's leading whitespace to each non-empty line.
4. For failed tasks: insert a single comment line: `{indent}{comment_char} <<{TASK_ID}: {description}>> -- FAILED: {error}`.

### 8.2 Comment Character Detection

The comment character is determined by file extension:

| Comment prefix | Extensions |
|----------------|------------|
| `//` | `.js`, `.ts`, `.rs`, `.go`, `.java`, `.c`, `.cpp`, `.cs`, `.swift`, `.kt` |
| `#` | All other extensions (default) |

---

## 9. Output Artifacts

### 9.1 build_report.json

Written to the output directory alongside generated files. Maps every task to its file and line range.

```json
{
  "project_description": "A markdown link checker CLI tool",
  "generated_at": "2026-03-15T12:35:00+00:00",
  "orchestrator_model": "google/gemini-3.1-pro-preview",
  "microagent_model": "inception/mercury-2",
  "files": [
    {
      "path": "linkcheck.py",
      "tasks": ["PY_1", "PY_2", "PY_3", "PY_4"]
    }
  ],
  "tasks": [
    {
      "task_id": "PY_1",
      "file": "linkcheck.py",
      "line_start": 14,
      "line_end": 23,
      "instruction": "Write function extract_links(text: str) -> list[str]",
      "status": "ok",
      "error": null
    }
  ],
  "summary": {
    "total_files": 1,
    "total_tasks": 4,
    "succeeded": 4,
    "failed": 0
  },
  "log_file": "logs/run_20260315_123456.log"
}
```

### 9.2 Generated README.md

A README MUST be generated for each output project containing:

- Project name (derived from the first 6 words of the description).
- The full project description.
- Setup command (auto-detected from file types: `requirements.txt` -> pip, `package.json` -> npm, `Cargo.toml` -> cargo).
- Run command (auto-detected).
- Build info: timestamp and task success count.
- Pointer to `build_report.json`.

---

## 10. Logging

All logging MUST use Python's built-in `logging` module. No third-party logging libraries.

### 10.1 Console Handler

- **Level:** INFO+
- **Format:** `[HH:MM:SS] message`
- **Purpose:** Clean, stage-based progress for the human operator.
- No tracebacks at default level.

Example output:

```
[12:34:56] Generating skeleton...
[12:34:58] Skeleton: 5 files, 12 tasks
[12:34:58] Dispatching 12 microagent tasks...
[12:34:59] [PY_1] Extracts URLs from markdown using regex patterns
[12:34:59] [PY_3] Checks all URLs concurrently with semaphore-limited parallelism
[12:35:00] [PY_2] Checks a single URL with HEAD-then-GET fallback and timeout
[12:35:00] [PY_4] FAILED: RateLimitError after 3 retries
[12:35:00] 3/4 tasks succeeded
[12:35:00] Assembling files...
[12:35:00] Generated 1 files, 3/4 tasks succeeded. Output: ./output/linkcheck/
```

### 10.2 File Handler

- **Level:** DEBUG
- **Format:** `%(asctime)s | %(levelname)-5s | %(name)s | %(message)s`
- **Location:** `logs/run_YYYYMMDD_HHMMSS.log` (one file per run)
- **Contains:** Full prompts sent, full responses received, timing, errors with tracebacks.

### 10.3 Failure Logs

When a microagent fails all retries, a dedicated file MUST be written: `logs/failed_TASK_ID.log`

Contents:

1. The full microagent prompt (instruction + inputs + outputs + context).
2. Each retry attempt's response or error.

---

## 11. Error Handling

**Principle:** Never crash the pipeline. Log information of value. Produce partial output for iteration.

| Failure | Response |
|---------|----------|
| Microagent task fails | Retry with exponential backoff (1s, 2s, 4s) and temperature escalation (+0.10/retry). On exhaustion: write `logs/failed_TASK_ID.log`, record in `build_report.json`, insert commented placeholder in output. Continue with remaining tasks. |
| Orchestrator fails | Retry once. On failure: log full prompt/error, print clear error to console, exit with code 1. |
| Parse failure (malformed orchestrator output) | Log raw response to file log. Print error to console. Exit with code 1. |
| Summary fails (Stage 4B) | Silently catch. Console shows `[TASK_ID] (completed)` instead of a summary. MUST NOT block or affect the main pipeline. |
| Rate limiting | Caught by the retry logic with exponential backoff. |

---

## 12. Self-Improvement Loop

The system produces artifacts that enable an LLM to trace errors back to the exact task and prompt that produced them.

### 12.1 Workflow

1. Read `build_report.json` to understand project structure and any failed tasks.
2. Run the generated project (the generated README explains how).
3. If a runtime error occurs at line N of `file.py`: look up `build_report.json` to find the task where `line_start <= N <= line_end` and get the `task_id`.
4. Find the full prompt/response in `logs/run_*.log` or `logs/failed_TASK_ID.log`.
5. Fix the specific task or re-run with adjusted prompts.

---

## 13. Project Structure

6 Python files + 1 YAML config, all top-level (no packages, no `src/` directory):

```
main.py             Entry point. CLI arg parsing + pipeline stage orchestration.
orchestrator.py     Calls orchestrator LLM, parses skeletons + tool_calls from text response.
microagent.py       Dispatches individual tasks to microagent LLM in parallel via asyncio.gather.
assembler.py        Replaces placeholders with task results, writes output files + build_report.json + README.
logger.py           Dual logging setup (file + console) + failure log writer.
prompts.py          All prompt templates. Multishot examples embedded directly.
config.yaml         Models, temperatures, retry settings, output paths.
```

Supporting files:

```
requirements.txt    openai, pyyaml
SPECS.md            This specification document.
CLAUDE.md           LLM-facing project instructions.
README.md           User-facing project documentation.
.gitignore          logs/, output/, __pycache__/, .env
```

Runtime directories (auto-created):

```
logs/               Run logs + failure logs
output/             Generated projects
```

---

## 14. Dependencies

```
openai>=2.0.0
pyyaml>=6.0.3
```

Two packages. The `openai` SDK handles all HTTP to OpenRouter via `base_url` override. `pyyaml` parses `config.yaml`. Everything else is stdlib.

**Python version:** 3.13+

---

## 15. Design Constraints

1. No over-engineering. No abstract base classes, no plugin systems, no middleware chains.
2. Prefer stdlib over third-party packages.
3. Keep the file count minimal -- 6 Python files + config, all top-level.
4. If a simple solution meets a requirement, use it.

---

## Appendix A: Orchestrator Prompt Examples

The orchestrator system prompt (in `prompts.py`) includes multishot examples demonstrating the skeleton + tool_calls format for three scenarios:

1. **Python -- Small project** (markdown link checker CLI): 1 file, 4 tasks.
2. **TypeScript -- Large project** (REST task management API): 5 files, 8 tasks.
3. **Rust -- Medium project** (CLI word frequency counter): 3 files, 5 tasks.

These examples are embedded directly in `prompts.py` as part of the `ORCHESTRATOR_SYSTEM_PROMPT` string. They demonstrate file markers, placeholder format, task independence, context scoping, and the `tool_calls` JSON structure.

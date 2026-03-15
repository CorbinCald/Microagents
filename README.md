# Microagents

A Python CLI tool that generates entire codebases from a natural-language project description by orchestrating LLMs via OpenRouter.

Currently scoped to project creation, not editing existing projects.

## Quick Start

```bash
export OPENROUTER_API_KEY="sk-..."
pip install -r requirements.txt
python main.py "Build a markdown link checker CLI in Python"
```

Output goes to `output/<project_name>/`. Logs go to `logs/`.

## How It Works

1. An **orchestrator** LLM (Gemini 3.1 Pro) decomposes your project description into file skeletons with placeholder tasks.
2. All tasks are dispatched **in parallel** to fast **microagent** LLMs (Mercury 2).
3. Results are **assembled** into a complete, runnable project with a build report.

```
User --> orchestrator --> skeleton + tasks --> microagents (parallel) --> assembled project
```

## Configuration

Edit `config.yaml` to change models, temperatures, token limits, or retry settings.

```yaml
orchestrator:
  model: "google/gemini-3.1-pro-preview"
  temperature: 1
  max_tokens: 32000

microagent:
  model: "inception/mercury-2"
  temperature: 0.1
  max_tokens: 32000
```

The API key is read from the environment variable named in `api.key_env` (default: `OPENROUTER_API_KEY`).

## Output

Each generated project includes:

- All source files assembled from the skeleton + microagent output.
- `build_report.json` -- maps every task to its file and line range (for debugging).
- `README.md` -- auto-generated setup and usage instructions.

Failed tasks leave a commented placeholder in the output and are recorded in the build report. See `logs/` for full debug traces.

## Dependencies

- `openai>=2.0.0` (for OpenRouter API access)
- `pyyaml>=6.0.3` (for config parsing)
- Python 3.13+

## Documentation

- [SPECS.md](SPECS.md) -- Full technical specification (architecture, pipeline, protocols, data structures).
- [CLAUDE.md](CLAUDE.md) -- LLM-facing project instructions.

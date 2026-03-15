# Microagent architecture

## Subagents but more focused, more parallelized, and much faster. Currently scoped to project creation, not editing existing projects.

### Planning

- Orchestration LLM will separate complex tasks into microtasks, scoped to one simple change at a time.
    - Each microtasks will NOT require any context of the rest of the project, except for: input parameters, output parameters, where relevant.
    - Function, parameter, and class naming consistency will be handled by orchestrator LLM when it generates the programmatic tool call for each microagent.
- Not currently in scope: With addition of editing, orchestration LLM will obtain have full context of any files that need changes (read tool), this can be cached input.

### LLMs:

#### Via Openrouter:
- Orchestrator: Gemini 3.1 Pro Preview
- Microagents: Mercury 2 (by Inception)

### *Interface Code*

- Written by the orchestration LLM.
- Must be parallelized with programmatic tool calling; aggressive concurrency but exponential backoffs in case. ([https://platform.claude.com/docs/en/agents-and-tools/tool-use/programmatic-tool-calling](https://platform.claude.com/docs/en/agents-and-tools/tool-use/programmatic-tool-calling))

#### Interface code uses a Skeleton & Placeholder approach:

1. The orchestrator writes a lightweight **skeleton** for each file — structure, signatures, imports, and class/function outlines — with unique `<<TASK_ID: description>>` placeholders where implementation is needed.
2. Once the placeholder is complete, the orchestrator generates the batch of programmatic tool calls.
    a. ONLY the relevant context needed to achieve the microtask is passed to each subagent -- this context is concise and clear instructions on the task, the input specifications, and the output specifications.
4. Microagent output (returned as a response to the programatic tool call) replaces its placeholder, inheriting the skeleton's existing indentation.

#### Each placeholder task specifies:

1. **What to implement** — a concise natural-language description of the task.
2. **Inputs** — exact input.
3. **Outputs** — exact output (or product of the code).
4. **Context** — only the immediately relevant context of the code.

#### Examples

**Orchestrator skeletons (to be given as multishot examples to orchestrator**:

Python example, small project:
```

```

Typescript example, large project:
```

```

Rust example, medium project:
```

```

**Orchestrator programmatic tool calls (to be given as multishot examples to orchestrator)**:

Python example, matching python example above:
```

```

Typescript example, matching typescript example above:
```

```

Rust example, matching Rust example above:
```

```

### Flow

???

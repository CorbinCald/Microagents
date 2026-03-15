import json
import logging
import os
import re
import sys
from dataclasses import dataclass

import openai

from prompts import ORCHESTRATOR_SYSTEM_PROMPT, orchestrator_user_prompt


log = logging.getLogger("microagents")


@dataclass
class TaskSpec:
    task_id: str
    instruction: str
    inputs: str
    outputs: str
    context: str


@dataclass
class TaskResult:
    task_id: str
    code: str
    status: str  # "ok" or "failed"
    error: str | None
    duration: float


@dataclass
class FileSpec:
    path: str
    skeleton: str
    task_ids: list[str]


def call_orchestrator(description: str, config: dict) -> str:
    """Call the orchestrator LLM and return the raw response text."""
    client = openai.OpenAI(
        base_url=config["api"]["base_url"],
        api_key=os.environ[config["api"]["key_env"]],
    )

    system_msg = ORCHESTRATOR_SYSTEM_PROMPT
    user_msg = orchestrator_user_prompt(description)

    log.info("Generating skeleton...")
    log.debug(f"SYSTEM PROMPT length: {len(system_msg)} chars")
    log.debug(f"USER PROMPT: {user_msg}")

    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=config["orchestrator"]["model"],
                temperature=config["orchestrator"]["temperature"],
                max_tokens=config["orchestrator"]["max_tokens"],
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
            )
            text = response.choices[0].message.content
            if not text:
                raise ValueError("Orchestrator returned empty response")
            log.debug(f"RESPONSE ({len(text)} chars): {text}")
            return text
        except Exception as e:
            log.warning(f"Orchestrator attempt {attempt + 1} failed: {e}")
            if attempt == 0:
                continue
            log.error(f"Orchestrator failed after 2 attempts: {e}")
            print(f"Error: Orchestrator LLM call failed: {e}", file=sys.stderr)
            sys.exit(1)


def parse_response(response_text: str) -> tuple[list[FileSpec], list[TaskSpec]]:
    """Parse the orchestrator response into FileSpecs and TaskSpecs."""

    # Step 1: Find the tool_calls JSON block (last ```json block containing "tool_calls")
    json_blocks = re.findall(r"```json?\s*\n(.*?)\n```", response_text, re.DOTALL)
    tool_calls_json = None
    for block in reversed(json_blocks):
        if '"tool_calls"' in block:
            tool_calls_json = block
            break

    if tool_calls_json is None:
        log.error("No tool_calls JSON block found in orchestrator response")
        log.debug(f"Full response:\n{response_text}")
        print("Error: orchestrator response missing tool_calls JSON block", file=sys.stderr)
        sys.exit(1)

    # Step 2: Find where the JSON block starts to separate skeletons from tool_calls
    json_block_start = response_text.rfind(tool_calls_json)
    skeleton_text = response_text[:json_block_start]

    # Step 3: Split skeleton text on file markers (# --- or // ---)
    file_marker_re = re.compile(r"^(?:#|//) --- (.+?) ---.*$", re.MULTILINE)
    markers = list(file_marker_re.finditer(skeleton_text))

    if not markers:
        log.error("No file markers (# --- path ---) found in orchestrator response")
        log.debug(f"Skeleton text:\n{skeleton_text[:2000]}")
        print("Error: orchestrator response contains no file markers", file=sys.stderr)
        sys.exit(1)

    placeholder_re = re.compile(r"<<(\w+):")
    file_specs = []

    for i, marker in enumerate(markers):
        path = marker.group(1).strip()
        start = marker.end()
        end = markers[i + 1].start() if i + 1 < len(markers) else len(skeleton_text)
        skeleton = skeleton_text[start:end].strip("\n")
        task_ids = placeholder_re.findall(skeleton)
        file_specs.append(FileSpec(path=path, skeleton=skeleton, task_ids=task_ids))

    # Step 4: Parse tool_calls JSON
    try:
        data = json.loads(tool_calls_json)
    except json.JSONDecodeError as e:
        log.error(f"Failed to parse tool_calls JSON: {e}")
        log.debug(f"Raw JSON block:\n{tool_calls_json[:2000]}")
        print(f"Error: malformed tool_calls JSON in orchestrator response: {e}", file=sys.stderr)
        sys.exit(1)

    calls = data.get("tool_calls", data) if isinstance(data, dict) else data
    if isinstance(calls, dict):
        calls = calls.get("tool_calls", [])

    task_specs = []
    for call_idx, call in enumerate(calls):
        try:
            args = call["function"]["arguments"]
            task_specs.append(
                TaskSpec(
                    task_id=args["task_id"],
                    instruction=args["instruction"],
                    inputs=args["inputs"],
                    outputs=args["outputs"],
                    context=args["context"],
                )
            )
        except (KeyError, TypeError) as e:
            log.error(f"Malformed tool_call at index {call_idx}: {e}")
            log.debug(f"Tool call data: {json.dumps(call, indent=2)}")
            print(f"Error: malformed tool_call at index {call_idx}: {e}", file=sys.stderr)
            sys.exit(1)

    # Step 5: Validate task ID consistency
    skeleton_task_ids = set()
    for fs in file_specs:
        skeleton_task_ids.update(fs.task_ids)
    spec_task_ids = {ts.task_id for ts in task_specs}

    if skeleton_task_ids != spec_task_ids:
        missing_specs = skeleton_task_ids - spec_task_ids
        missing_placeholders = spec_task_ids - skeleton_task_ids
        if missing_specs:
            log.warning(f"Placeholders without tool_calls: {missing_specs}")
        if missing_placeholders:
            log.warning(f"Tool_calls without placeholders: {missing_placeholders}")

    log.info(f"Skeleton: {len(file_specs)} files, {len(task_specs)} tasks")
    return file_specs, task_specs


def generate_skeleton(
    description: str, config: dict
) -> tuple[list[FileSpec], list[TaskSpec]]:
    """Generate and parse the orchestrator skeleton in one call."""
    response_text = call_orchestrator(description, config)
    return parse_response(response_text)

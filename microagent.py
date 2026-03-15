import asyncio
import logging
import os
import re
import time

import openai

from logger import write_failure_log
from orchestrator import TaskResult, TaskSpec
from prompts import (
    MICROAGENT_SYSTEM_PROMPT,
    SUMMARY_SYSTEM_PROMPT,
    microagent_user_prompt,
    summary_user_prompt,
)


log = logging.getLogger("microagents")


def strip_code_fences(code: str) -> str:
    """Remove markdown code fences if present."""
    match = re.match(r"^\s*```\w*\n(.*?)\n```\s*$", code, re.DOTALL)
    if match:
        return match.group(1)
    return code.strip()


async def call_microagent(
    client: openai.AsyncOpenAI, task: TaskSpec, config: dict
) -> TaskResult:
    """Call the microagent LLM for a single task, with retry and temperature escalation."""
    base_temp = config["microagent"]["temperature"]
    max_retries = config["retry"]["max_retries"]
    base_delay = config["retry"]["base_delay"]
    temp_increment = config["retry"]["temp_increment"]

    prompt = microagent_user_prompt(task)
    log.debug(f"{task.task_id} PROMPT: {prompt}")

    attempts = []
    start_time = time.time()
    last_error = None

    for attempt in range(max_retries + 1):
        temp = base_temp + (attempt * temp_increment)
        try:
            response = await client.chat.completions.create(
                model=config["microagent"]["model"],
                temperature=temp,
                max_tokens=config["microagent"]["max_tokens"],
                messages=[
                    {"role": "system", "content": MICROAGENT_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )
            code = response.choices[0].message.content
            if not code:
                raise ValueError("Microagent returned empty response")
            code = strip_code_fences(code)
            duration = time.time() - start_time
            log.debug(f"{task.task_id} RESPONSE: {code[:200]}...")
            return TaskResult(
                task_id=task.task_id,
                code=code,
                status="ok",
                error=None,
                duration=duration,
            )
        except Exception as e:
            last_error = e
            attempts.append({"response": None, "error": f"{type(e).__name__}: {e}"})
            log.warning(
                f"{task.task_id} attempt {attempt + 1}/{max_retries + 1} failed: {e}"
            )
            if attempt < max_retries:
                delay = base_delay * (2**attempt)
                await asyncio.sleep(delay)

    # All retries exhausted
    duration = time.time() - start_time
    write_failure_log(config["output"]["log_dir"], task.task_id, prompt, attempts)
    return TaskResult(
        task_id=task.task_id,
        code="",
        status="failed",
        error=str(last_error),
        duration=duration,
    )


async def summarize_task(
    client: openai.AsyncOpenAI, task_id: str, code: str, config: dict
) -> None:
    """Fire-and-forget: summarize a completed task's code in one sentence."""
    try:
        response = await client.chat.completions.create(
            model=config["summary"]["model"],
            temperature=config["summary"]["temperature"],
            max_tokens=config["summary"]["max_tokens"],
            messages=[
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": summary_user_prompt(code)},
            ],
        )
        summary = response.choices[0].message.content.strip()
        log.info(f"[{task_id}] {summary}")
    except Exception:
        log.info(f"[{task_id}] (completed)")


async def dispatch_all(
    tasks: list[TaskSpec], config: dict
) -> dict[str, TaskResult]:
    """Dispatch all microagent tasks in parallel and return results."""
    client = openai.AsyncOpenAI(
        base_url=config["api"]["base_url"],
        api_key=os.environ[config["api"]["key_env"]],
    )

    log.info(f"Dispatching {len(tasks)} microagent tasks...")

    async def run_task(task: TaskSpec) -> TaskResult:
        result = await call_microagent(client, task, config)
        if result.status == "ok":
            asyncio.create_task(summarize_task(client, task.task_id, result.code, config))
        else:
            log.info(f"[{task.task_id}] FAILED: {result.error}")
        return result

    results = await asyncio.gather(*[run_task(t) for t in tasks])

    # Give fire-and-forget summaries a moment to finish
    await asyncio.sleep(0.1)

    return {r.task_id: r for r in results}

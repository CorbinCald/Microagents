import logging
import os
from datetime import datetime


def setup_logging(config: dict) -> tuple[logging.Logger, str]:
    """Set up dual logging (console + file) and return the logger and log filename."""
    log_dir = config["output"]["log_dir"]
    os.makedirs(log_dir, exist_ok=True)

    log_filename = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_path = os.path.join(log_dir, log_filename)

    logger = logging.getLogger("microagents")
    logger.setLevel(logging.DEBUG)

    # Console handler: INFO+, clean [HH:MM:SS] format
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console_fmt = logging.Formatter("[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
    console.setFormatter(console_fmt)
    logger.addHandler(console)

    # File handler: DEBUG, full detail
    file_handler = logging.FileHandler(log_path)
    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter("%(asctime)s | %(levelname)-5s | %(name)s | %(message)s")
    file_handler.setFormatter(file_fmt)
    logger.addHandler(file_handler)

    return logger, os.path.join(log_dir, log_filename)


def write_failure_log(
    log_dir: str, task_id: str, prompt: str, attempts: list[dict]
) -> None:
    """Write a detailed failure log for a task that exhausted all retries."""
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, f"failed_{task_id}.log")

    with open(path, "w") as f:
        f.write(f"=== FAILED TASK: {task_id} ===\n\n")
        f.write("=== PROMPT ===\n")
        f.write(prompt)
        f.write("\n\n")
        for i, attempt in enumerate(attempts, 1):
            f.write(f"=== ATTEMPT {i} ===\n")
            if attempt.get("response"):
                f.write(attempt["response"])
            if attempt.get("error"):
                f.write(f"ERROR: {attempt['error']}")
            f.write("\n\n")

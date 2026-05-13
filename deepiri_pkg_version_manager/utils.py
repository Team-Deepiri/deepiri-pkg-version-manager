import logging
import os
import subprocess
from typing import List, Optional


def run_command(
    command: List[str],
    cwd: Optional[str] = None,
    env_overrides: Optional[dict] = None,
) -> Optional[str]:
    try:
        env = os.environ.copy()
        if env_overrides:
            env.update(env_overrides)

        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            env=env,
        )
        return result.stdout.strip()

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() if e.stderr else str(e)
        logging.error(f"[red]Error:[/red] {error_msg}")
        return None

    except FileNotFoundError as e:
        logging.error(f"[red]Error:[/red] Command not found: {e}")
        return None

    except Exception as e:
        logging.error(f"[red]Unexpected Error:[/red] {e}")
        return None

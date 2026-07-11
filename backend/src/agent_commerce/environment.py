"""Load repository-local environment variables for application entry points."""

from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def load_local_environment() -> None:
    """Load the ignored root .env file without replacing shell-provided values."""
    load_dotenv(PROJECT_ROOT / ".env", override=False)

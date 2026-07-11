"""ASGI entry point."""

from agent_commerce.api import create_app
from agent_commerce.environment import load_local_environment

load_local_environment()

app = create_app()

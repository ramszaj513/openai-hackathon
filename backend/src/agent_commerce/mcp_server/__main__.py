"""Run the seeded merchant MCP server over Streamable HTTP."""

from agent_commerce.commerce.service import CommerceService
from agent_commerce.mcp_server.server import create_commerce_mcp


def main() -> None:
    server = create_commerce_mcp(CommerceService.with_seed_data())
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()


import os
import sys
from pathlib import Path

import pytest
from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client

pytestmark = pytest.mark.mcp_stdio


async def test_stdio_server_lists_and_calls_tool_without_real_credentials() -> None:
    if os.getenv("GYM_COACH_RUN_MCP_STDIO_TESTS") != "1":
        pytest.skip("set GYM_COACH_RUN_MCP_STDIO_TESTS=1 to run the stdio subprocess test")
    environment = dict(os.environ)
    environment["HEVY_API_KEY"] = ""
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "gym_coach.cli", "mcp"],
        cwd=Path(__file__).parents[2],
        env=environment,
    )

    async with Client(stdio_client(parameters), read_timeout_seconds=10) as client:
        listed = await client.list_tools()
        result = await client.call_tool("get_hevy_connection_status", {})

    assert len(listed.tools) == 18
    assert result.is_error is False
    assert result.structured_content == {
        "configured": False,
        "accessible": False,
        "status": "not_configured",
        "detail": "HEVY_API_KEY is not configured",
    }

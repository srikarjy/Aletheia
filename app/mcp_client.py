"""MCP client for Biolab's search_pubmed tool. Contract verified against the real
server — see QUESTIONS.md#q2. Spawns Biolab's own venv as a subprocess over MCP
stdio; this is a sibling-repo dependency (BIOLAB_PROJECT_PATH), not a package import,
because Biolab is a separately versioned, separately deployed service.
"""

import json
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def search_pubmed(query: str, agent_id: str, max_results: int = 5) -> dict:
    biolab_path = os.environ["BIOLAB_PROJECT_PATH"]
    params = StdioServerParameters(
        command=f"{biolab_path}/.venv/bin/python",
        args=["-m", "biolab.server"],
        cwd=biolab_path,
        env={
            **os.environ,
            "BIOLAB_DB_PATH": os.environ["BIOLAB_DB_PATH"],
        },
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "search_pubmed",
                {"query": query, "agent_id": agent_id, "max_results": max_results},
            )
            if result.isError:
                message = result.content[0].text if result.content else "unknown error"
                raise RuntimeError(f"Biolab search_pubmed failed: {message}")
            return json.loads(result.content[0].text)

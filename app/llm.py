"""Shared helper for forced-tool-use Claude calls.

Centralizes a real bug found in Phase 3: a truncated tool_use response (Claude hit
max_tokens mid-generation) isn't an API error — stop_reason is just "max_tokens", and
the partial JSON silently comes back missing whatever fields hadn't been written yet.
Downstream code then fails with a confusing KeyError several calls later instead of a
clear one at the source. This raises loudly right where the truncation happened.
"""

from anthropic import Anthropic


def call_tool(client: Anthropic, model: str, max_tokens: int, tool: dict, prompt: str) -> dict:
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "max_tokens":
        raise RuntimeError(
            f"Claude's {tool['name']} response was truncated at max_tokens={max_tokens} "
            "before completing the tool call — raise max_tokens rather than trust a "
            "partial/invalid JSON payload."
        )
    return next(block.input for block in response.content if block.type == "tool_use")

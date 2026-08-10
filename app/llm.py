"""Shared helper for forced-tool-use Claude calls with configurable max_tokens and auto-retry.

Centralizes a real bug found in Phase 3: a truncated tool_use response (Claude hit
max_tokens mid-generation) isn't an API error — stop_reason is just "max_tokens", and
the partial JSON silently comes back missing whatever fields hadn't been written yet.
Downstream code then fails with a confusing KeyError several calls later instead of a
clear one at the source. This raises loudly right where the truncation happened.

Now with configurable max_tokens and automatic retry with increased tokens on truncation.

Supports MOCK_LLM=true for demo/deployment without Anthropic dependency.
"""

import json
import os
import random

from anthropic import Anthropic


DEFAULT_MAX_TOKENS = int(os.environ.get("CLAUDE_MAX_TOKENS", "2048"))
MAX_TOKENS_RETRY_INCREMENT = int(os.environ.get("CLAUDE_MAX_TOKENS_RETRY_INCREMENT", "1024"))
MAX_TOKENS_LIMIT = int(os.environ.get("CLAUDE_MAX_TOKENS_LIMIT", "8192"))

_client: Anthropic | None = None
if os.environ.get("MOCK_LLM", "").lower() != "true":
    _client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


def _mock_tool_response(tool_name: str, prompt: str) -> dict:
    """Generate deterministic mock tool response based on tool name and prompt hash."""
    random.seed(hash(prompt + tool_name))
    
    if tool_name == "build_case":
        return {
            "case_summary": "The evidence for BRCA1 mutations increasing pancreatic cancer risk is mixed and considerably weakened by methodological concerns. Initial associations (RR 2.26) attenuate after adjusting for BRCA2 co-occurrence (adjusted RR 1.34, CI 0.87-2.06). A prospective cohort found no significant association (adjusted HR 0.89, CI 0.45-1.76). Familial enrichment (p=0.003) suggests some signal but may reflect ascertainment bias. The ATM founder variant paper is unrelated to BRCA1.",
            "cited_pmids": ["38765432", "35987654", "37123456", "34876543"]
        }
    elif tool_name == "raise_challenges":
        return {
            "challenges": [
                {
                    "target_pmid": "37123456",
                    "issue": "The Advocate claims BRCA1 showed no significant association after adjustment (HR 0.89, CI 0.45-1.76), but this confidence interval is extremely wide and crosses 1.0 in both directions—it's compatible with both a 55% risk reduction AND a 76% risk increase. This is a precision problem, not evidence of 'no effect.'"
                },
                {
                    "target_pmid": "37123456",
                    "issue": "The prospective cohort compares BRCA1 carriers to BRCA2 carriers (HR 0.56 for BRCA1 vs BRCA2), but the adjusted HR of 0.89 lacks a clear comparison group. If it's comparing BRCA1 carriers to non-carriers, this would be critical information."
                },
                {
                    "target_pmid": "38765432",
                    "issue": "The meta-analysis's 'adjusted' result (RR 1.34, CI 0.87-2.06) still shows a point estimate of 34% increased risk. While not statistically significant, this is not trivial and the upper bound reaches 106% increased risk."
                },
                {
                    "target_pmid": "35987654",
                    "issue": "PMID 35987654 shows significant enrichment of BRCA1 variants in familial pancreatic cancer kindreds (p=0.003), which is actual positive evidence for association. The Advocate mentions this briefly but doesn't adequately address why this finding should be discounted."
                },
                {
                    "target_pmid": "37123456",
                    "issue": "The prospective cohort found 1.8% pancreatic cancer incidence in BRCA1 carriers over 8.2 years median follow-up. The Advocate doesn't compare this to population baseline rates. If general population lifetime risk is ~1.5%, then 1.8% over just 8 years could actually represent elevated risk."
                },
                {
                    "target_pmid": "36543210",
                    "issue": "PMID 36543210 about ATM variants is completely irrelevant to the BRCA1 claim. The Advocate doesn't cite this in their argument, but its inclusion in the evidence list serves no purpose and suggests possible padding of the reference list."
                },
                {
                    "target_pmid": "34876543",
                    "issue": "The methodological review identifies 'ascertainment bias' and 'ancestry differences' as major sources of heterogeneity alongside BRCA2 co-occurrence, but the Advocate focuses almost exclusively on BRCA2 confounding."
                }
            ],
            "uncertainty_notes": "Several key unknowns undermine confidence in the Advocate's dismissal of BRCA1 risk: (1) The comparison group in the 'adjusted HR 0.89' analysis is unclear. (2) Population baseline pancreatic cancer rates for the same age/ancestry distribution aren't provided. (3) The mechanism of 'adjustment for BRCA2 co-occurrence' in the meta-analysis isn't specified. (4) None of the cited studies report what proportion of BRCA1 carriers also carry BRCA2 mutations. (5) Statistical power calculations are absent. (6) The clinical significance threshold isn't defined.",
            "overall_assessment": "The Advocate's case is significantly weaker than presented. While they correctly identify BRCA2 confounding as an important methodological issue, they overstate the evidence for 'no independent effect.' The adjusted estimates all have very wide confidence intervals compatible with both meaningful risk increases and decreases—this is uncertainty, not evidence of absence. The 1.8% pancreatic cancer incidence over 8 years and the significant enrichment in familial kindreds (p=0.003) are both positive signals the Advocate downplays. The case cherry-picks the null findings while minimizing the signal in the data."
        }
    elif tool_name == "synthesize":
        return {
            "conclusion": "The claim that BRCA1 mutations increase pancreatic cancer risk remains unresolved based on the evidence presented in this debate.\n\nThe Advocate presents evidence from multiple sources showing initial associations between BRCA1 and pancreatic cancer, but argues these associations largely disappear after adjusting for BRCA2 co-occurrence. Specifically, a meta-analysis (PMID 38765432) showed an unadjusted pooled relative risk of 2.26 (95% CI 1.45-3.52) that attenuated to 1.34 (95% CI 0.87-2.06) after adjustment. A prospective cohort (PMID 37123456) reported an adjusted HR of 0.89 (95% CI 0.45-1.76) for BRCA1 carriers.\n\nThe Skeptic raises multiple valid challenges that expose critical weaknesses in the Advocate's interpretation:\n\n1. **Wide confidence intervals indicate imprecision, not absence of effect**: The adjusted estimates have extremely wide CIs compatible with both substantial risk increases and decreases. The meta-analysis adjusted RR of 1.34 (0.87-2.06) has an upper bound of 106% increased risk. The prospective cohort HR of 0.89 (0.45-1.76) ranges from 55% risk reduction to 76% risk increase. These represent underpowered studies, not evidence against the claim.\n\n2. **Unclear comparison groups**: The adjusted HR of 0.89 lacks clarity on whether BRCA1 carriers are compared to the general population, BRCA2 carriers, or non-carriers, fundamentally affecting interpretation.\n\n3. **Positive signals downplayed**: Significant enrichment of BRCA1 in familial pancreatic cancer kindreds (p=0.003) and 1.8% incidence over 8.2 years are both potential signals that the Advocate minimizes without adequate justification or comparison to baseline rates.\n\n4. **Other sources of bias unaddressed**: The methodological review identifies ascertainment bias and ancestry differences alongside BRCA2 confounding, but these are not adequately addressed.",
            "verdict": "unresolved",
            "confidence": 0.5,
            "confidence_rationale": "Anchor B applies: The evidence rows genuinely conflict on the central claim and neither side is invalidated. The Advocate's central evidence shows both positive associations (unadjusted RR 2.26, familial enrichment p=0.003) and attenuated/null findings after adjustment (adjusted RR 1.34 non-significant, adjusted HR 0.89 non-significant). The Skeptic's challenges are valid and expose fundamental issues: (1) wide confidence intervals indicating imprecision rather than true null effects, (2) unclear comparison groups that prevent proper interpretation, (3) positive signals in familial data that contradict null prospective findings, and (4) unaddressed sources of bias beyond BRCA2 confounding. Critically, the Skeptic correctly identifies that the Advocate conflates 'not statistically significant' with 'no effect' when the point estimates consistently trend toward increased risk but with poor precision. The evidence presents a genuine conflict between initial positive signals and adjusted analyses that remain inconclusive due to wide CIs and methodological concerns. Neither position can be dismissed as invalid. This is a classic anchor B scenario where the evidence base itself is conflicted and the debate cannot be resolved without additional data. Confidence = 0.5 reflects maximum uncertainty appropriate for anchor B.",
            "driving_provenance_ids": []
        }
    elif tool_name == "submit_baseline":
        return {
            "answer": "The evidence for BRCA1 mutations increasing pancreatic cancer risk is mixed and considerably weakened by methodological concerns. Initial associations (RR 2.26) attenuate after adjusting for BRCA2 co-occurrence (adjusted RR 1.34, CI 0.87-2.06). A prospective cohort found no significant association (adjusted HR 0.89, CI 0.45-1.76). Familial enrichment (p=0.003) suggests some signal but may reflect ascertainment bias. The ATM founder variant paper is unrelated to BRCA1. [PMID38765432, PMID35987654, PMID37123456, PMID34876543]",
            "cited_pmids": ["38765432", "35987654", "37123456", "34876543"],
            "confidence": 0.4
        }
    else:
        return {}


def call_tool(
    client: Anthropic | None,
    model: str,
    max_tokens: int | None = None,
    tool: dict | None = None,
    prompt: str | None = None,
    *,
    tool_name: str | None = None,
    tool_schema: dict | None = None,
    retry_on_truncation: bool = True,
) -> dict:
    """
    Call a tool with forced tool use, with automatic retry on truncation.
    
    Args:
        client: Anthropic client (can be None in mock mode)
        model: Model name
        max_tokens: Max tokens (uses DEFAULT_MAX_TOKENS if not provided)
        tool: Tool schema dict (legacy parameter)
        prompt: Prompt string (legacy parameter)
        tool_name: Tool name (new parameter)
        tool_schema: Tool input schema (new parameter)
        retry_on_truncation: Whether to retry with increased max_tokens on truncation
    
    Returns:
        Tool input dict
    """
    # Support both old and new calling conventions
    if tool is not None and prompt is not None:
        _tool_name = tool["name"]
        _tool_schema = tool["input_schema"]
        _prompt = prompt
        _max_tokens = max_tokens or DEFAULT_MAX_TOKENS
    elif tool_name is not None and tool_schema is not None and prompt is not None:
        _tool_name = tool_name
        _tool_schema = tool_schema
        _prompt = prompt
        _max_tokens = max_tokens or DEFAULT_MAX_TOKENS
    else:
        raise ValueError("Must provide either (tool, prompt) or (tool_name, tool_schema, prompt)")
    
    # Mock mode
    if client is None:
        return _mock_tool_response(_tool_name, _prompt)

    # Bounded independently of MAX_TOKENS_LIMIT: if MAX_TOKENS_RETRY_INCREMENT is ever
    # misconfigured to <=0, clamping it to 1 alone would still allow thousands of retries
    # between DEFAULT_MAX_TOKENS and MAX_TOKENS_LIMIT. A small fixed cap is the real backstop.
    HARD_MAX_ATTEMPTS = 10
    token_bound_attempts = (MAX_TOKENS_LIMIT - _max_tokens) // max(MAX_TOKENS_RETRY_INCREMENT, 1) + 1
    max_attempts = max(1, min(token_bound_attempts, HARD_MAX_ATTEMPTS))

    for attempt in range(max_attempts):
        response = client.messages.create(
            model=model,
            max_tokens=_max_tokens,
            tools=[{"name": _tool_name, "input_schema": _tool_schema}],
            tool_choice={"type": "tool", "name": _tool_name},
            messages=[{"role": "user", "content": _prompt}],
        )
        if response.stop_reason == "max_tokens":
            if not retry_on_truncation:
                raise RuntimeError(
                    f"Claude's {_tool_name} response was truncated at max_tokens={_max_tokens} "
                    "before completing the tool call — raise max_tokens rather than trust a "
                    "partial/invalid JSON payload."
                )
            if attempt + 1 >= max_attempts or _max_tokens >= MAX_TOKENS_LIMIT:
                raise RuntimeError(
                    f"Claude's {_tool_name} response still truncated at max_tokens={_max_tokens} "
                    f"(limit: {MAX_TOKENS_LIMIT}) — giving up."
                )
            _max_tokens = min(_max_tokens + MAX_TOKENS_RETRY_INCREMENT, MAX_TOKENS_LIMIT)
            continue
        return next(block.input for block in response.content if block.type == "tool_use")

    raise RuntimeError(
        f"Claude's {_tool_name} response still truncated at max_tokens={_max_tokens} "
        f"(limit: {MAX_TOKENS_LIMIT}) — giving up."
    )

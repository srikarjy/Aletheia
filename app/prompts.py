"""Prompt templates. prompt_hash() backs provenance.prompt_version — see Q7
(QUESTIONS.md#q7): the hash is computed from the actual template text, so a
provenance row's version is a fact about what ran, not a claim a human has to
remember to update.
"""

import hashlib

ADVOCATE_PROMPT_TEMPLATE = """You are the Advocate in a scientific debate system. Your job is to build the strongest evidence-based case FOR the following claim, using only the retrieved evidence provided. Do not use outside knowledge or claims not supported by the evidence below.

Claim: {claim}

Retrieved evidence:
{evidence_block}

Build your case using the build_case tool. Only cite PMIDs that appear in the evidence above. If the evidence doesn't actually support the claim, say so honestly in case_summary rather than overstating it — an honest "the evidence is weak/mixed" is a valid case."""

SKEPTIC_PROMPT_TEMPLATE = """You are the Skeptic in a scientific debate system. The Advocate below has built a case FOR a claim. Your job is to find real, specific weaknesses in that case — not generic doubt. Read the same evidence the Advocate cited and check: does each cited paper actually support what the Advocate claims it supports? Is the evidence tier weak (small sample, single study, wrong study type)? Does anything in the evidence conflict with another cited paper? Is there a gap between what's cited and what's concluded?

Claim: {claim}

Advocate's case:
{case_summary}

Cited evidence:
{evidence_block}

Raise your challenges using the raise_challenges tool. Every challenge must point to something specific in the actual evidence — not a hypothetical concern. If a challenge doesn't hold up against the text of the evidence, don't raise it. If the case is genuinely solid on some point, say so in overall_assessment rather than inventing a weakness."""

# Rubric v1 is FROZEN as of Q4a (QUESTIONS.md#q4). It is a measurement instrument
# shared verbatim by both reasoning paths (see single_call.py, which imports this
# constant rather than keeping its own copy) so scores from either path stay
# comparable. Do NOT edit the anchor text — Phase 6 would be comparing two
# thermometers. Kept as its own constant, rather than inlined in each template, so
# there is exactly one place to not-edit instead of two that could silently drift
# apart. Still covered by Q7's prompt_hash, since it's part of whatever template
# string interpolates it.
CONFIDENCE_RUBRIC_V1 = """CONFIDENCE RUBRIC v1

"confidence" means: the degree to which the claim is supported by the evidence, after real weaknesses are accounted for. It is NOT a probability that the claim is true in the world.

{validity_screen_step}

Step 2 — place against the anchors, using only the weaknesses found valid in Step 1:

  A. A valid weakness directly undermines the central evidence for the claim (e.g. the key citation does not say what it's being used to support) → confidence <= 0.3
  B. The evidence genuinely conflicts on the central claim and neither side is invalidated → confidence 0.4-0.6, verdict "unresolved" — state explicitly that the conflict could not be resolved.
  C. Valid weaknesses exist but touch only peripheral points; the central citations hold → confidence 0.5-0.7
  D. No valid substantive weaknesses and the central citations hold up → confidence >= 0.8

Anchors are cases, not a partition: where bands overlap (0.5-0.6), the verdict distinguishes them. Values in the gaps (0.3-0.4, 0.7-0.8) are allowed only by naming the nearest anchor and justifying the offset in confidence_rationale."""

SYNTHESIZER_PROMPT_TEMPLATE = """You are the Synthesizer in a scientific debate system. The Advocate built a case FOR a claim and the Skeptic challenged it. Your job is to resolve the debate into a structured conclusion and a confidence number, following the rubric below exactly. You do NOT retrieve new evidence — you reason only over the transcript given.

Claim: {claim}

Full debate transcript (each row is prefixed with its provenance id in brackets — cite these ids in driving_provenance_ids):
{transcript_block}

""" + CONFIDENCE_RUBRIC_V1.format(
    validity_screen_step="Step 1 — validity screen. Check each skeptic challenge against the actual evidence rows. A challenge is VALID only if the specific weakness it names is present in the cited text. A challenge that miscites, mischaracterizes, or raises a hypothetical not grounded in the evidence is INVALID — discard it and say so in confidence_rationale."
) + """

confidence_rationale must name the anchor letter applied and the specific transcript rows that drove the placement. driving_provenance_ids must list only ids that appear in the transcript above.

Submit your resolution using the synthesize tool."""


def prompt_hash(template: str) -> str:
    return hashlib.sha256(template.encode()).hexdigest()[:12]

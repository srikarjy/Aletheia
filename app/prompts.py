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


def prompt_hash(template: str) -> str:
    return hashlib.sha256(template.encode()).hexdigest()[:12]

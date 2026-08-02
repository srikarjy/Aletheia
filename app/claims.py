"""Phase 5: 5 curated scientific claims for the eval set.

Selection rationale (Q3, QUESTIONS.md):
- Claims with genuinely conflicting published evidence (stress-tests skeptic's conflict-resolution role)
- Claims with a known ground-truth verdict (lets you score accuracy, not just internal consistency)
- A mix, deliberately including at least one claim with no clean resolution (tests whether synthesizer honestly reports "unresolved" instead of fabricating confidence)

Riskiest assumption: if all 5 claims have easy, uncontested evidence, the eval proves nothing about the debate loop's actual value — the skeptic role would never have anything real to challenge.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class EvalClaim:
    """A curated claim for the evaluation set."""
    id: str
    claim: str
    category: Literal["conflicting", "ground_truth", "unresolved"]
    rationale: str
    expected_verdict: Literal["supported", "refuted", "unresolved"] | None = None
    known_facts: list[str] | None = None


EVAL_CLAIMS: list[EvalClaim] = [
    EvalClaim(
        id="brca1_pancreatic",
        claim="BRCA1 mutations increase pancreatic cancer risk",
        category="conflicting",
        rationale=(
            "The original development claim. Literature shows conflicting evidence: "
            "some meta-analyses report elevated risk (RR ~2-3), others find no significant "
            "association after adjusting for BRCA2 co-occurrence. Skeptic caught advocate "
            "conflating BRCA1/BRCA2 risk figures in Phase 3 — ideal for testing conflict resolution."
        ),
        expected_verdict="unresolved",
        known_facts=[
            "BRCA2 has stronger pancreatic cancer association (RR ~3-5)",
            "BRCA1 association is weaker and often not significant after adjustment",
            "Multiple meta-analyses exist with conflicting conclusions",
        ],
    ),
    EvalClaim(
        id="vitamin_d_covid",
        claim="Vitamin D supplementation prevents severe COVID-19 outcomes",
        category="conflicting",
        rationale=(
            "High-profile controversy during pandemic. Early observational studies showed "
            "strong correlation (low Vit D → worse outcomes), but Mendelian randomization "
            "and RCTs (e.g., COVIDENCE UK, CORONAVIT) largely failed to show causal benefit. "
            "Perfect for testing whether skeptic distinguishes correlation from causation."
        ),
        expected_verdict="refuted",
        known_facts=[
            "Observational studies: strong inverse correlation",
            "Mendelian randomization: no causal effect",
            "Major RCTs (COVIDENCE UK, CORONAVIT): null results for prevention",
            "Some benefit only in deficient subgroups",
        ],
    ),
    EvalClaim(
        id="aspirin_primary_prevention",
        claim="Low-dose aspirin reduces all-cause mortality in healthy older adults",
        category="ground_truth",
        rationale=(
            "Clear ground truth from major RCTs (ASPREE, ASCEND, ARRIVE). ASPREE (2018) "
            "showed INCREASED all-cause mortality (HR 1.14) in healthy adults ≥70. "
            "Guidelines reversed (USPSTF 2022: D grade for ≥60). Tests whether debate "
            "arrives at correct conclusion against outdated conventional wisdom."
        ),
        expected_verdict="refuted",
        known_facts=[
            "ASPREE RCT (n=19,114): HR 1.14 for all-cause mortality",
            "Major bleeding risk increased (HR 1.38)",
            "USPSTF 2022: Grade D recommendation against initiation ≥60",
            "Previous guidelines (pre-2018) recommended for primary prevention",
        ],
    ),
    EvalClaim(
        id="omega3_cardiovascular",
        claim="Omega-3 fatty acid supplementation reduces major adverse cardiovascular events",
        category="conflicting",
        rationale=(
            "Long-standing debate. Early trials (GISSI-Prevenzione) showed benefit, "
            "but larger modern trials (ASCEND, VITAL, REDUCE-IT) give conflicting results. "
            "REDUCE-IT used mineral oil placebo (may have harmed control), STRENGTH "
            "used corn oil and was stopped for futility. Tests handling of placebo issues."
        ),
        expected_verdict="unresolved",
        known_facts=[
            "GISSI-Prevenzione (1999): benefit post-MI",
            "ASCEND (diabetes): null for MACE",
            "VITAL (primary prevention): null for MACE",
            "REDUCE-IT (icosapent ethyl): 25% RRR but controversial placebo",
            "STRENGTH (EPA/DHA): stopped for futility",
        ],
    ),
    EvalClaim(
        id="hormone_replacement_therapy",
        claim="Menopausal hormone therapy reduces all-cause mortality in women under 60",
        category="ground_truth",
        rationale=(
            "WHI (2002) caused massive practice change showing harm, but age-stratified "
            "re-analyses and newer trials (ELITE, DOPS, KEEPS) show mortality benefit "
            "for initiation <60 or <10 years post-menopause. Tests whether debate handles "
            "time-dependent effects and subgroup analyses correctly."
        ),
        expected_verdict="supported",
        known_facts=[
            "WHI overall: increased risk (older women, mean age 63)",
            "WHI age-stratified: HR 0.70 for mortality in 50-59 age group",
            "ELITE trial: reduced atherosclerosis progression if started early",
            "DOPS trial: reduced mortality/heart failure in recently menopausal women",
            "Current guidelines: favorable for symptomatic women <60 or <10yr post-menopause",
        ],
    ),
]


def get_claim_by_id(claim_id: str) -> EvalClaim | None:
    """Get a claim by its ID."""
    for claim in EVAL_CLAIMS:
        if claim.id == claim_id:
            return claim
    return None


def get_all_claims() -> list[EvalClaim]:
    """Get all evaluation claims."""
    return EVAL_CLAIMS
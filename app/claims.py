"""Phase 5 (revised): 10 curated scientific claims for the eval set, each graded
against a real, independently-checkable systematic review or meta-analysis — not
against a verdict this project invented itself.

Why this revision exists: the original 5-claim set graded `expected_verdict`
against domain knowledge baked into this file with no external citation. That's
unfalsifiable — nobody reading the eval results can check the grading key against
anything. Every claim below now carries a `source_citation` naming the specific
systematic review or meta-analysis (with DOI/PMID) that `expected_verdict` is
graded against, so the ground truth itself is auditable, not just the debate's
reasoning about it.

Sourcing this surfaced two real corrections to the original file:
- `vitamin_d_covid` was graded "refuted"; the actual Cochrane living review and
  umbrella reviews describe genuinely mixed RCT/observational/Mendelian-randomization
  evidence — reclassified to "unresolved".
- `hormone_replacement_therapy` was graded "supported" without noting that the
  Cochrane review's own headline conclusion is a *null* effect on all-cause
  mortality overall, with the "supported" reading only holding for the
  early-initiator subgroup. Recategorized "conflicting" to reflect that tension
  explicitly, expected_verdict unchanged but now cited.

Selection rationale (extends Q3, QUESTIONS.md):
- Claims with genuinely conflicting published evidence (stress-tests skeptic's conflict-resolution role)
- Claims with a clear, citable ground-truth verdict (lets you score accuracy, not just internal consistency)
- A mix, deliberately including claims with no clean resolution (tests whether synthesizer honestly reports "unresolved" instead of fabricating confidence)

Riskiest assumption: if all claims have easy, uncontested evidence, the eval proves nothing about the debate loop's actual value — the skeptic role would never have anything real to challenge. This is still only n=10 — not statistically powered to make a general claim about debate vs. baseline architectures. See README's Results & Limitations section.
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
    source_citation: str | None = None


EVAL_CLAIMS: list[EvalClaim] = [
    EvalClaim(
        id="brca1_pancreatic",
        claim="BRCA1 mutations increase pancreatic cancer risk",
        category="conflicting",
        rationale=(
            "The original development claim. Literature shows conflicting evidence: "
            "some case-control studies report elevated risk, but the most recent "
            "meta-analysis specific to familial pancreatic cancer finds BRCA1's "
            "association non-significant once pooled across studies — unlike BRCA2, "
            "which remains significant. Skeptic caught advocate conflating BRCA1/BRCA2 "
            "risk figures in Phase 3 — ideal for testing conflict resolution."
        ),
        expected_verdict="unresolved",
        known_facts=[
            "BRCA2 has a stronger, statistically significant pancreatic cancer association",
            "BRCA1's pooled association is non-significant (OR 1.26, P=0.51) per the 2024 meta-analysis",
            "A separate large case-control study (OR 2.58, 95% CI 1.54-4.05) found a significant BRCA1 signal",
            "The evidence base is genuinely inconsistent across study designs, not just underpowered",
        ],
        source_citation=(
            "Yin et al. 2024, \"The role of germline BRCA1 & BRCA2 mutations in familial "
            "pancreatic cancer: A systematic review and meta-analysis\", PLOS ONE. "
            "PMID: 38809921"
        ),
    ),
    EvalClaim(
        id="vitamin_d_covid",
        claim="Vitamin D supplementation prevents severe COVID-19 outcomes",
        category="conflicting",
        rationale=(
            "High-profile controversy during the pandemic. Early observational studies "
            "showed strong correlation (low vitamin D → worse outcomes), but Mendelian "
            "randomization studies found no causal effect, and the living Cochrane review "
            "describes RCT evidence as limited and inconsistent rather than cleanly "
            "negative. Genuinely unresolved, not a clean refutation — good test of "
            "whether the debate over-claims certainty in either direction."
        ),
        expected_verdict="unresolved",
        known_facts=[
            "Observational studies: strong inverse correlation between vitamin D and severity",
            "Mendelian randomization studies: no evidence of a causal protective effect",
            "Cochrane's own living review frames RCT evidence on treatment as still evolving/limited",
            "Effect, if any, appears concentrated in deficient subgroups rather than the general population",
        ],
        source_citation=(
            "Stroehlein et al. 2021, \"Vitamin D supplementation for the treatment of "
            "COVID-19: a living systematic review\", Cochrane Database of Systematic "
            "Reviews. PMID: 34029377"
        ),
    ),
    EvalClaim(
        id="aspirin_primary_prevention",
        claim="Low-dose aspirin reduces all-cause mortality in healthy older adults",
        category="ground_truth",
        rationale=(
            "Clear ground truth from major RCTs (ASPREE, ASCEND, ARRIVE) and the USPSTF's "
            "systematic evidence review. ASPREE (2018) showed increased all-cause "
            "mortality (HR 1.14) in healthy adults ≥70, and guidelines reversed "
            "accordingly (USPSTF 2022: D grade for ≥60). Tests whether debate arrives at "
            "the correct, currently-reversed conclusion rather than outdated conventional wisdom."
        ),
        expected_verdict="refuted",
        known_facts=[
            "ASPREE RCT (n=19,114): HR 1.14 for all-cause mortality",
            "Major bleeding risk increased (HR 1.38)",
            "USPSTF systematic review: no benefit for all-cause or cardiovascular mortality at ≤100mg/day",
            "USPSTF 2022: Grade D recommendation against initiation ≥60",
        ],
        source_citation=(
            "Guirguis-Blake et al. 2016, \"Aspirin for the Primary Prevention of "
            "Cardiovascular Events: A Systematic Evidence Review for the U.S. Preventive "
            "Services Task Force\", Annals of Internal Medicine. PMID: 27064410"
        ),
    ),
    EvalClaim(
        id="omega3_cardiovascular",
        claim="Omega-3 fatty acid supplementation reduces major adverse cardiovascular events",
        category="conflicting",
        rationale=(
            "Long-standing debate. Early trials (GISSI-Prevenzione) showed benefit, but "
            "the 2020 Cochrane review — pooling most modern primary-prevention trials — "
            "concludes little or no effect on mortality or cardiovascular health. That "
            "conclusion has itself been publicly contested by researchers pointing to "
            "REDUCE-IT's positive result in secondary prevention with a different "
            "formulation (icosapent ethyl) and placebo choice. Tests whether the debate "
            "can represent genuine expert disagreement about a review's own methodology, "
            "not just disagreement about the underlying trials."
        ),
        expected_verdict="unresolved",
        known_facts=[
            "GISSI-Prevenzione (1999): benefit post-MI",
            "ASCEND (diabetes) and VITAL (primary prevention): null for MACE",
            "Cochrane 2020 (Abdelhamid et al.): little or no effect on mortality/CVD, moderate-high quality evidence",
            "REDUCE-IT (icosapent ethyl, secondary prevention): 25% RRR, but placebo choice (mineral oil) publicly disputed",
            "STRENGTH (EPA/DHA, corn oil placebo): stopped for futility",
        ],
        source_citation=(
            "Abdelhamid et al. 2020, \"Omega-3 fatty acids for the primary and secondary "
            "prevention of cardiovascular disease\", Cochrane Database of Systematic "
            "Reviews, CD003177.pub5"
        ),
    ),
    EvalClaim(
        id="hormone_replacement_therapy",
        claim="Menopausal hormone therapy reduces all-cause mortality in women under 60",
        category="conflicting",
        rationale=(
            "WHI (2002) caused a major practice reversal by showing harm overall, and the "
            "current Cochrane review's headline conclusion is high-quality evidence of "
            "*no* protective effect on all-cause mortality across primary and secondary "
            "prevention combined. But the same review's subgroup analysis found lower "
            "mortality specifically in women who started therapy within 10 years of "
            "menopause — which is what the claim as worded is actually asking about. "
            "Categorized 'conflicting' rather than a clean 'supported' precisely because "
            "the headline and subgroup findings point different directions depending on "
            "which population you read the claim against — a good test of whether the "
            "debate notices and reports that tension instead of picking one number."
        ),
        expected_verdict="supported",
        known_facts=[
            "Cochrane headline (19 trials, n=40,410): no protective effect on all-cause mortality overall",
            "Same review, subgroup <10yr post-menopause at initiation: lower mortality and CHD",
            "Stroke and venous thromboembolism risk increased regardless of subgroup",
            "WHI overall (older cohort, mean age 63): increased risk",
        ],
        source_citation=(
            "Boardman et al. 2015, \"Hormone therapy for preventing cardiovascular "
            "disease in post-menopausal women\", Cochrane Database of Systematic "
            "Reviews, CD002229.pub4"
        ),
    ),
    EvalClaim(
        id="vitamin_c_common_cold",
        claim="Vitamin C supplementation prevents the common cold",
        category="ground_truth",
        rationale=(
            "Widely believed, cleanly refuted for the general population by a large, "
            "long-running Cochrane review (29 trial comparisons, n=11,306): regular "
            "vitamin C supplementation does not reduce cold incidence in the ordinary "
            "population, though it modestly shortens duration and helps a narrow "
            "high-exertion subgroup. Tests whether the debate correctly separates "
            "'prevents' (refuted) from 'shortens duration in those who already have one' "
            "(a different, narrower claim) rather than blurring the two."
        ),
        expected_verdict="refuted",
        known_facts=[
            "29 trial comparisons, n=11,306: no effect on cold incidence in the general population",
            "Regular supplementation modestly reduces cold duration/severity once a cold has started",
            "Benefit for incidence specifically shown only in a narrow subgroup under brief extreme physical stress",
            "Therapeutic (post-onset) dosing trials did not replicate the duration benefit",
        ],
        source_citation=(
            "Hemilä & Chalker 2013, \"Vitamin C for preventing and treating the common "
            "cold\", Cochrane Database of Systematic Reviews, CD000980.pub4"
        ),
    ),
    EvalClaim(
        id="antioxidant_supplements_mortality",
        claim="Antioxidant supplement use (beta-carotene, vitamin A, vitamin E) reduces all-cause mortality",
        category="ground_truth",
        rationale=(
            "One of the largest and most decisive Cochrane reviews in this space (78 "
            "RCTs, n=296,707): no evidence supports antioxidant supplementation for "
            "primary or secondary mortality prevention, and beta-carotene, vitamin E, "
            "and high-dose vitamin A were each associated with *increased* mortality. "
            "A strong ground-truth negative case — good test of whether the debate can "
            "state a confident 'refuted, and actually harmful' conclusion rather than "
            "defaulting to hedged uncertainty."
        ),
        expected_verdict="refuted",
        known_facts=[
            "78 RCTs, n=296,707 randomized to antioxidant supplements vs. placebo/no intervention",
            "Beta-carotene and vitamin E associated with increased mortality",
            "Higher-dose vitamin A may also increase mortality",
            "Vitamin C and selenium were not associated with increased mortality risk in this review",
        ],
        source_citation=(
            "Bjelakovic et al. 2012, \"Antioxidant supplements for prevention of "
            "mortality in healthy participants and patients with various diseases\", "
            "Cochrane Database of Systematic Reviews, CD007176.pub2"
        ),
    ),
    EvalClaim(
        id="glucosamine_osteoarthritis",
        claim="Glucosamine reduces pain in osteoarthritis",
        category="conflicting",
        rationale=(
            "A genuinely formulation-dependent result, not a simple yes/no: the Cochrane "
            "review found the Rotta brand preparation outperformed placebo on pain and "
            "function, while non-Rotta preparations and higher-quality-allocation trials "
            "did not. Pooling everything together shows a modest effect; restricting to "
            "high-quality trials shows none. Tests whether the debate can hold a "
            "'depends which product and which trial quality you weight' conclusion "
            "rather than collapsing it to a single verdict."
        ),
        expected_verdict="unresolved",
        known_facts=[
            "Pooled across 25 RCTs: ~22% pain improvement, ~11% function improvement vs. placebo",
            "Rotta-brand preparation: superior to placebo on pain and function",
            "Non-Rotta preparations and trials with adequate allocation concealment: no significant benefit",
            "Adverse event rates did not differ from placebo",
        ],
        source_citation=(
            "Towheed et al. 2005, \"Glucosamine therapy for treating osteoarthritis\", "
            "Cochrane Database of Systematic Reviews, CD002946"
        ),
    ),
    EvalClaim(
        id="probiotics_pediatric_aad",
        claim="Probiotics prevent antibiotic-associated diarrhea in children",
        category="ground_truth",
        rationale=(
            "A clear positive ground-truth case, useful as a contrast to the mostly "
            "negative/mixed claims elsewhere in this set. Cochrane review of pediatric "
            "trials found a moderate, credible protective effect, strongest at higher "
            "probiotic doses. Tests whether the debate can also confidently support a "
            "claim when the evidence actually supports it, rather than skeptic-driven "
            "hedging becoming a reflex regardless of evidence quality."
        ),
        expected_verdict="supported",
        known_facts=[
            "Moderate protective effect: NNTB 9 (95% CI 7-13) across included pediatric trials",
            "High-dose probiotics (≥5 billion CFU/day): NNTB 6, judged a credible subgroup effect",
            "Adverse event rates low; no serious adverse events attributed to probiotics",
            "Evidence specific to pediatric populations — not directly generalized to adults in this review",
        ],
        source_citation=(
            "Guo, Goldenberg et al. 2019, \"Probiotics for the prevention of pediatric "
            "antibiotic-associated diarrhea\", Cochrane Database of Systematic Reviews, "
            "CD004827.pub5"
        ),
    ),
    EvalClaim(
        id="statins_primary_prevention",
        claim="Statins reduce all-cause mortality in primary prevention of cardiovascular disease",
        category="ground_truth",
        rationale=(
            "A second clear positive ground-truth case with strong, high-volume RCT "
            "backing (18 RCTs, n=56,934). Included as a contrast to aspirin's primary-"
            "prevention claim above: two superficially similar 'does this common "
            "preventive drug reduce mortality' claims with opposite ground-truth answers, "
            "testing whether the debate reasons from each claim's actual evidence rather "
            "than pattern-matching to 'preventive drugs in healthy people usually don't help'."
        ),
        expected_verdict="supported",
        known_facts=[
            "18 RCTs, n=56,934: all-cause mortality OR 0.86 (95% CI 0.79-0.94)",
            "Combined fatal/non-fatal CVD events: RR 0.75 (95% CI 0.70-0.81)",
            "Combined fatal/non-fatal stroke: RR 0.78 (95% CI 0.68-0.89)",
            "No evidence of serious harm from statin prescription found in the review",
        ],
        source_citation=(
            "Taylor et al. 2013, \"Statins for the primary prevention of cardiovascular "
            "disease\", Cochrane Database of Systematic Reviews, CD004816.pub5"
        ),
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

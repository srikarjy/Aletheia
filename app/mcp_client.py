"""MCP client for Biolab's search_pubmed tool. Contract verified against the real
server — see QUESTIONS.md#q2. Spawns Biolab's own venv as a subprocess over MCP
stdio; this is a sibling-repo dependency (BIOLAB_PROJECT_PATH), not a package import,
because Biolab is a separately versioned, separately deployed service.

Supports MOCK_RETRIEVAL=true for demo/deployment without Biolab dependency.
"""

import asyncio
import json
import os
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# Realistic fixture data for demo mode (matches Phase 1 verified output)
MOCK_PAPERS = {
    "brca1": [
        {
            "pmid": "38765432",
            "retrieval_id": "mock_retrieval_001",
            "title": "BRCA1 mutations and pancreatic cancer risk: a systematic review and meta-analysis",
            "abstract": "Background: The association between BRCA1 mutations and pancreatic cancer risk remains controversial. Methods: We searched PubMed through March 2024 for studies reporting pancreatic cancer risk in BRCA1 mutation carriers. Results: 12 studies (n=15,432 carriers) were included. Pooled relative risk was 2.26 (95% CI 1.45-3.52). However, after adjusting for BRCA2 co-occurrence, the association attenuated to 1.34 (95% CI 0.87-2.06). Conclusion: BRCA1 mutations may confer modestly elevated pancreatic cancer risk, but confounding by BRCA2 status is substantial.",
        },
        {
            "pmid": "37123456",
            "retrieval_id": "mock_retrieval_002",
            "title": "Pancreatic cancer incidence in BRCA1/2 mutation carriers: a prospective cohort study",
            "abstract": "We followed 4,218 BRCA1 and 3,892 BRCA2 mutation carriers for median 8.2 years. Pancreatic cancer incidence was 1.8% in BRCA1 carriers vs 3.2% in BRCA2 carriers (HR 0.56, 95% CI 0.31-1.02). After adjusting for age, sex, and ancestry, BRCA1 was not significantly associated with pancreatic cancer (adjusted HR 0.89, 95% CI 0.45-1.76). BRCA2 remained significant (adjusted HR 2.84, 95% CI 1.56-5.18).",
        },
        {
            "pmid": "36543210",
            "retrieval_id": "mock_retrieval_003",
            "title": "ATM founder variant p.Val2424Gly and cancer risk in Ashkenazi Jewish population",
            "abstract": "The ATM c.7271T>G (p.Val2424Gly) founder variant was assessed in 12,456 Ashkenazi Jewish individuals. No association with pancreatic cancer was observed (OR 1.12, 95% CI 0.67-1.88). This variant is unrelated to BRCA1-mediated pancreatic cancer susceptibility.",
        },
        {
            "pmid": "35987654",
            "retrieval_id": "mock_retrieval_004",
            "title": "BRCA1-associated pancreatic cancer: clinical characteristics and outcomes",
            "abstract": "Retrospective analysis of 89 BRCA1-associated pancreatic cancers. Median age at diagnosis 62 years. 67% presented with metastatic disease. Median overall survival 11.2 months. Pathogenic BRCA1 variants were enriched in familial pancreatic cancer kindreds (p=0.003).",
        },
        {
            "pmid": "34876543",
            "retrieval_id": "mock_retrieval_005",
            "title": "Meta-analysis of BRCA1 and pancreatic cancer: methodological challenges",
            "abstract": "Review of 15 meta-analyses on BRCA1-pancreatic cancer association. Heterogeneity (I²=68%) driven by BRCA2 co-carrier inclusion, ancestry differences, and ascertainment bias. Studies adjusting for BRCA2 status consistently show null association. Recommendation: future studies must stratify by BRCA1/2 status.",
        },
    ],
    "vitamin_d": [
        {
            "pmid": "35123456",
            "retrieval_id": "mock_retrieval_010",
            "title": "Vitamin D supplementation for prevention of COVID-19: the COVIDENCE UK randomised controlled trial",
            "abstract": "6,200 adults randomized to vitamin D3 3200 IU/day, 800 IU/day, or no supplementation. Primary outcome: PCR-confirmed COVID-19. No significant difference between groups (HR 0.94, 95% CI 0.78-1.13 for 3200 IU vs control). Subgroup analysis in vitamin D deficient participants also null.",
        },
        {
            "pmid": "34987654",
            "retrieval_id": "mock_retrieval_011",
            "title": "Mendelian randomization study of vitamin D and COVID-19 severity",
            "abstract": "Two-sample MR using 417,340 UK Biobank participants. Genetic instruments for 25-hydroxyvitamin D showed no causal effect on COVID-19 hospitalization (OR 1.01 per 10 nmol/L, 95% CI 0.96-1.06) or severe disease (OR 1.02, 95% CI 0.95-1.09). Observational associations likely due to confounding.",
        },
        {
            "pmid": "34567890",
            "retrieval_id": "mock_retrieval_012",
            "title": "CORONAVIT trial: vitamin D supplementation and COVID-19 outcomes",
            "abstract": "3,100 UK adults randomized to vitamin D3 800 IU/day vs no supplementation for 6 months. No difference in COVID-19 incidence (RR 0.97, 95% CI 0.76-1.24), hospitalization, or mortality. Results consistent across baseline vitamin D strata.",
        },
        {
            "pmid": "34234567",
            "retrieval_id": "mock_retrieval_013",
            "title": "Observational association of vitamin D status and COVID-19 severity: a meta-analysis",
            "abstract": "45 studies (n=1.2M) included. Low 25(OH)D associated with severe COVID-19 (OR 1.64, 95% CI 1.38-1.95). However, significant heterogeneity (I²=82%) and evidence of publication bias. Confounding by age, obesity, and comorbidity likely explains association.",
        },
        {
            "pmid": "33890123",
            "retrieval_id": "mock_retrieval_014",
            "title": "Vitamin D receptor polymorphisms and COVID-19 susceptibility",
            "abstract": "Candidate gene study of VDR variants in 2,456 COVID-19 cases and 3,102 controls. No significant association after Bonferroni correction. Suggests vitamin D pathway not causally implicated in COVID-19 susceptibility.",
        },
    ],
    "aspirin": [
        {
            "pmid": "30221587",
            "retrieval_id": "mock_retrieval_020",
            "title": "Effect of aspirin on all-cause mortality in the healthy elderly: ASPREE randomized trial",
            "abstract": "19,114 community-dwelling adults ≥70 years (US ≥65) randomized to aspirin 100mg daily vs placebo. Median follow-up 4.7 years. All-cause mortality: 12.7 vs 11.1 events per 1000 person-years (HR 1.14, 95% CI 1.01-1.29). Major hemorrhage: 8.6 vs 6.2 per 1000 person-years (HR 1.38, 95% CI 1.18-1.62). No cardiovascular benefit.",
        },
        {
            "pmid": "30146929",
            "retrieval_id": "mock_retrieval_021",
            "title": "Aspirin in primary prevention: ASCEND and ARRIVE trials",
            "abstract": "ASCEND (diabetes): 15,480 randomized, no mortality benefit (RR 0.94, 95% CI 0.83-1.06). ARRIVE (moderate CVD risk): 12,546 randomized, no mortality benefit. Both showed increased bleeding. Meta-analysis of primary prevention trials confirms no all-cause mortality reduction.",
        },
        {
            "pmid": "35123456",
            "retrieval_id": "mock_retrieval_022",
            "title": "USPSTF 2022 recommendation: aspirin for primary prevention",
            "abstract": "Updated evidence review: for adults ≥60 years, harms outweigh benefits (Grade D). For adults 40-59 with ≥10% 10-year CVD risk, individualize decision (Grade C). Based on ASPREE, ASCEND, ARRIVE showing no mortality benefit and increased bleeding in older adults.",
        },
        {
            "pmid": "29123456",
            "retrieval_id": "mock_retrieval_023",
            "title": "Historical guidelines: aspirin for primary prevention 2002-2018",
            "abstract": "Pre-2018 guidelines (AHA/ACC, USPSTF 2009) recommended low-dose aspirin for primary prevention in adults with ≥10% 10-year CVD risk. Based on early trials (PHS, HOT) showing CVD benefit. Subsequent large trials reversed this recommendation.",
        },
        {
            "pmid": "28456789",
            "retrieval_id": "mock_retrieval_024",
            "title": "Bleeding risk with aspirin in elderly: systematic review",
            "abstract": "Meta-analysis of 13 trials (n=164,000). Major bleeding increased 43% (RR 1.43, 95% CI 1.30-1.57) with aspirin. Intracranial hemorrhage increased 32% (RR 1.32, 95% CI 1.14-1.53). Risk highest in ≥70 age group, consistent with ASPREE findings.",
        },
    ],
    "omega3": [
        {
            "pmid": "30565574",
            "retrieval_id": "mock_retrieval_030",
            "title": "Icosapent ethyl for prevention of cardiovascular events: REDUCE-IT trial",
            "abstract": "8,179 high-risk patients on statins randomized to icosapent ethyl 4g/day vs mineral oil placebo. Primary endpoint (MACE): 17.2% vs 22.0% (HR 0.75, 95% CI 0.68-0.83). Controversy: mineral oil placebo increased LDL by 10% and CRP by 30%, possibly exaggerating benefit.",
        },
        {
            "pmid": "33123456",
            "retrieval_id": "mock_retrieval_031",
            "title": "STRENGTH trial: omega-3 carboxylic acids for cardiovascular outcomes",
            "abstract": "13,078 high-risk patients randomized to omega-3 CA 4g/day vs corn oil placebo. Stopped early for futility at interim analysis. MACE: 10.1% vs 10.2% (HR 0.99, 95% CI 0.90-1.09). No benefit with corn oil placebo.",
        },
        {
            "pmid": "30415628",
            "retrieval_id": "mock_retrieval_032",
            "title": "VITAL trial: marine omega-3 fatty acids and cardiovascular disease",
            "abstract": "25,871 adults randomized to omega-3 1g/day vs placebo. Primary endpoint (MACE): 386 vs 419 events (HR 0.92, 95% CI 0.80-1.06). No significant reduction in major cardiovascular events in primary prevention population.",
        },
        {
            "pmid": "30123456",
            "retrieval_id": "mock_retrieval_033",
            "title": "ASCEND trial: omega-3 fatty acids in diabetes",
            "abstract": "15,480 adults with diabetes randomized to omega-3 1g/day vs olive oil placebo. Serious vascular events: 8.9% vs 9.2% (RR 0.97, 95% CI 0.87-1.08). No benefit for cardiovascular outcomes in diabetic population.",
        },
        {
            "pmid": "10567890",
            "retrieval_id": "mock_retrieval_034",
            "title": "GISSI-Prevenzione trial: n-3 polyunsaturated fatty acids post-MI",
            "abstract": "11,324 post-MI patients randomized to omega-3 1g/day vs control. Primary endpoint (death, nonfatal MI, stroke): 20.4% vs 22.7% (RR 0.89, 95% CI 0.81-0.98). Early trial showing benefit in secondary prevention, but modern trials in statin era show attenuated effects.",
        },
    ],
    "hrt": [
        {
            "pmid": "35123456",
            "retrieval_id": "mock_retrieval_040",
            "title": "Menopausal hormone therapy and mortality: WHI 20-year follow-up",
            "abstract": "27,347 women from WHI trials followed for 20 years. Estrogen-alone (hysterectomy): all-cause mortality HR 0.88 (95% CI 0.79-0.98) for initiation age 50-59. Estrogen+progestin: HR 0.94 (95% CI 0.85-1.04) for age 50-59. No benefit for initiation ≥70.",
        },
        {
            "pmid": "34567890",
            "retrieval_id": "mock_retrieval_041",
            "title": "ELITE trial: estradiol and atherosclerosis progression",
            "abstract": "643 postmenopausal women randomized to oral estradiol 1mg/day vs placebo. Carotid intima-media thickness progression: 0.0078 vs 0.0147 mm/year (p=0.008) for early postmenopausal (<6 years), no difference for late (>10 years). Supports timing hypothesis.",
        },
        {
            "pmid": "33890123",
            "retrieval_id": "mock_retrieval_042",
            "title": "DOPS trial: early menopausal hormone therapy and mortality",
            "abstract": "1,006 recently menopausal Danish women randomized to HRT vs control. 10-year follow-up: all-cause mortality 3.6% vs 6.8% (HR 0.53, 95% CI 0.31-0.91). Heart failure hospitalization also reduced. Supports benefit for early initiation.",
        },
        {
            "pmid": "32456789",
            "retrieval_id": "mock_retrieval_043",
            "title": "KEEPS trial: cognitive and cardiovascular effects of early HRT",
            "abstract": "727 recently menopausal women randomized to oral/conjugated estrogen vs placebo. No cognitive difference at 4 years. Coronary artery calcium progression numerically lower with estrogen. No increase in cardiovascular events.",
        },
        {
            "pmid": "12345678",
            "retrieval_id": "mock_retrieval_044",
            "title": "Original WHI 2002 publication: risks and benefits of estrogen+progestin",
            "abstract": "16,608 postmenopausal women (mean age 63) randomized to CEE+MPA vs placebo. Increased: breast cancer (HR 1.26), CHD (HR 1.29), stroke (HR 1.41), VTE (HR 2.13). Decreased: colorectal cancer (HR 0.63), hip fracture (HR 0.66). Led to dramatic practice change.",
        },
    ],
    "vitamin_c": [
        {
            "pmid": "39803741",
            "retrieval_id": "mock_retrieval_050",
            "title": "Vitamin C for preventing and treating the common cold: Cochrane systematic review",
            "abstract": "29 trial comparisons (n=11,306) of regular vitamin C supplementation (≥200mg/day) in the general population. No reduction in cold incidence (pooled RR 0.97, 95% CI 0.94-1.00). Duration of colds modestly reduced (8% in adults, 14% in children). Five trials in marathon runners/skiers/soldiers under heavy short-term physical stress showed incidence halved (RR 0.48, 95% CI 0.35-0.64) — this subgroup effect does not generalize to the ordinary population.",
        },
        {
            "pmid": "40381012",
            "retrieval_id": "mock_retrieval_051",
            "title": "Therapeutic vitamin C after cold onset: randomized trials",
            "abstract": "8 trials of vitamin C initiated after symptom onset (n=3,249). No consistent effect on symptom duration or severity (pooled difference in duration: -0.2 days, 95% CI -0.6 to 0.2). No support for vitamin C as a treatment once a cold has started.",
        },
        {
            "pmid": "33193359",
            "retrieval_id": "mock_retrieval_052",
            "title": "Vitamin C megadose trials and common cold incidence in general adult population",
            "abstract": "Community-based RCT, 2,006 adults randomized to vitamin C 1g/day vs placebo over one winter season. No difference in cold incidence (32.4% vs 33.1%, RR 0.98, 95% CI 0.89-1.08). Confirms null effect for prevention in ordinary, non-strenuous-exercise populations.",
        },
    ],
    "antioxidant": [
        {
            "pmid": "42611234",
            "retrieval_id": "mock_retrieval_060",
            "title": "Antioxidant supplements for prevention of mortality in healthy participants and patients with various diseases: Cochrane systematic review",
            "abstract": "78 RCTs (n=296,707) of beta-carotene, vitamin A, vitamin C, vitamin E, and selenium, alone or combined. No evidence of reduced all-cause mortality for primary or secondary prevention (RR 1.02, 95% CI 1.00-1.05). Beta-carotene (RR 1.05, 95% CI 1.01-1.09) and vitamin E (RR 1.03, 95% CI 1.00-1.05) were each associated with significantly *increased* mortality in subgroup analyses.",
        },
        {
            "pmid": "41902345",
            "retrieval_id": "mock_retrieval_061",
            "title": "Beta-carotene supplementation and lung cancer/mortality risk: CARET and ATBC trials",
            "abstract": "Two large RCTs (CARET n=18,314 smokers/asbestos-exposed; ATBC n=29,133 male smokers) stopped early. Beta-carotene supplementation increased lung cancer incidence (RR 1.28, 95% CI 1.04-1.57) and total mortality (RR 1.17, 95% CI 1.03-1.33) versus placebo.",
        },
        {
            "pmid": "40765432",
            "retrieval_id": "mock_retrieval_062",
            "title": "High-dose vitamin E supplementation and all-cause mortality: dose-response meta-analysis",
            "abstract": "19 RCTs examining vitamin E doses from 16.5 to 2000 IU/day. Doses ≥400 IU/day associated with increased all-cause mortality (RR 1.04, 95% CI 1.01-1.07). No dose showed a protective effect on mortality.",
        },
    ],
    "glucosamine": [
        {
            "pmid": "42549386",
            "retrieval_id": "mock_retrieval_070",
            "title": "Rotta-brand glucosamine sulfate for osteoarthritis pain: patented-formulation RCTs",
            "abstract": "Trials using the patented crystalline glucosamine sulfate formulation (Rotta) show clinically meaningful pain and function improvement vs placebo (WOMAC pain reduction ~20%, effect size 0.35-0.45). Consistent across three independent Rotta-sponsored trials with adequate allocation concealment.",
        },
        {
            "pmid": "42539490",
            "retrieval_id": "mock_retrieval_071",
            "title": "Non-Rotta glucosamine preparations for osteoarthritis: Cochrane review pooled analysis",
            "abstract": "Trials using non-Rotta (generic) glucosamine preparations, and trials with unclear/inadequate allocation concealment regardless of brand, show no clinically important pain reduction vs placebo (WOMAC pain difference not exceeding the minimal clinically important difference). Higher-quality-allocation trials overall trend toward null.",
        },
        {
            "pmid": "42483134",
            "retrieval_id": "mock_retrieval_072",
            "title": "Glucosamine plus chondroitin combination therapy: GAIT trial subgroup analysis",
            "abstract": "1,583 knee osteoarthritis patients randomized to glucosamine, chondroitin, combination, celecoxib, or placebo. No significant overall effect for glucosamine alone. Post-hoc subgroup (moderate-to-severe pain) showed benefit for the combination, but the trial was not powered for this subgroup and glucosamine's independent contribution cannot be isolated.",
        },
    ],
    "probiotics": [
        {
            "pmid": "41287654",
            "retrieval_id": "mock_retrieval_080",
            "title": "Probiotics for the prevention of pediatric antibiotic-associated diarrhea: Cochrane systematic review",
            "abstract": "33 RCTs (n=6,352) of children (0-18 years) receiving antibiotics, randomized to probiotics vs placebo/no treatment. Probiotics reduced AAD incidence from 19% to 8% (RR 0.45, 95% CI 0.36-0.55), a moderate and consistent protective effect. Effect strongest at doses ≥5 billion CFU/day; no serious adverse events attributable to probiotics.",
        },
        {
            "pmid": "40998765",
            "retrieval_id": "mock_retrieval_081",
            "title": "Lactobacillus rhamnosus GG for prevention of antibiotic-associated diarrhea in children",
            "abstract": "Multicenter RCT, 600 children on antibiotics randomized to L. rhamnosus GG (1×10^10 CFU/day) vs placebo. AAD incidence 8% vs 22% (RR 0.36, 95% CI 0.23-0.55). Effect consistent across antibiotic classes.",
        },
        {
            "pmid": "39876543",
            "retrieval_id": "mock_retrieval_082",
            "title": "Dose-response relationship of probiotics for pediatric AAD prevention: meta-regression",
            "abstract": "Meta-regression across 28 pediatric trials found a significant dose-response relationship: high-dose probiotics (≥5 billion CFU/day) reduced AAD risk by 53%, while low-dose (<5 billion CFU/day) showed a smaller, still-significant 29% reduction.",
        },
    ],
    "statins": [
        {
            "pmid": "41567890",
            "retrieval_id": "mock_retrieval_090",
            "title": "Statins for primary prevention of cardiovascular disease and all-cause mortality: systematic review and meta-analysis",
            "abstract": "18 RCTs (n=56,934) of statin therapy in primary prevention populations (no prior cardiovascular disease). All-cause mortality reduced (RR 0.92, 95% CI 0.87-0.96), driven primarily by trials with baseline LDL ≥3.5 mmol/L or high-risk populations. Effect present but smaller in lower-baseline-risk subgroups.",
        },
        {
            "pmid": "40456789",
            "retrieval_id": "mock_retrieval_091",
            "title": "JUPITER trial: rosuvastatin in primary prevention with elevated CRP",
            "abstract": "17,802 healthy adults with LDL <130 mg/dL but elevated hs-CRP randomized to rosuvastatin 20mg vs placebo. Trial stopped early: all-cause mortality reduced (HR 0.80, 95% CI 0.67-0.97). Major cardiovascular events reduced by 44%.",
        },
        {
            "pmid": "39234567",
            "retrieval_id": "mock_retrieval_092",
            "title": "Statins in primary prevention for low-risk individuals: pooled trial analysis",
            "abstract": "Pooled analysis restricted to trial participants with <10% 10-year cardiovascular risk (n=14,220 of the larger primary-prevention pool). All-cause mortality reduction was smaller and did not reach statistical significance in isolation (RR 0.96, 95% CI 0.88-1.05), though point estimates remained directionally consistent with the full high-volume pooled result.",
        },
    ],
}


def _get_mock_papers(query: str) -> list[dict[str, Any]]:
    """Select mock papers based on query keywords."""
    query_lower = query.lower()
    
    if "brca1" in query_lower or "brca" in query_lower:
        return MOCK_PAPERS["brca1"]
    elif "vitamin d" in query_lower or "covid" in query_lower:
        return MOCK_PAPERS["vitamin_d"]
    elif "aspirin" in query_lower:
        return MOCK_PAPERS["aspirin"]
    elif "omega-3" in query_lower or "omega 3" in query_lower or "fatty acid" in query_lower:
        return MOCK_PAPERS["omega3"]
    elif "hormone" in query_lower or "hrt" in query_lower or "menopausal" in query_lower:
        return MOCK_PAPERS["hrt"]
    elif "vitamin c" in query_lower or "common cold" in query_lower:
        return MOCK_PAPERS["vitamin_c"]
    elif "antioxidant" in query_lower or "beta-carotene" in query_lower or "beta carotene" in query_lower:
        return MOCK_PAPERS["antioxidant"]
    elif "glucosamine" in query_lower:
        return MOCK_PAPERS["glucosamine"]
    elif "probiotic" in query_lower:
        return MOCK_PAPERS["probiotics"]
    elif "statin" in query_lower:
        return MOCK_PAPERS["statins"]
    else:
        # Mock mode has no real retrieval to fall back to -- returning an
        # unrelated topic's papers would silently corrupt whatever eval or
        # debate consumes them (see search_pubmed's real-mode misconfiguration
        # policy above: a hard failure here, not a wrong answer).
        raise RuntimeError(
            f"No mock papers configured for query {query!r}. Add a fixture set "
            f"and keyword route to MOCK_PAPERS / _get_mock_papers, or set "
            f"MOCK_RETRIEVAL=false to use real retrieval."
        )


async def search_pubmed(query: str, agent_id: str, max_results: int = 5, timeout: float = 30.0) -> dict:
    """
    Search PubMed via Biolab MCP server, or return mock data if MOCK_RETRIEVAL=true.

    Misconfiguration (BIOLAB_PROJECT_PATH/BIOLAB_DB_PATH not set) is a hard
    failure, not a silent fallback to mock data — a debate run that's
    supposed to be grounded in real literature must not be able to
    silently become a mock run just because an env var was forgotten.
    Mock mode is opt-in only, via MOCK_RETRIEVAL=true.

    Args:
        query: Search query string
        agent_id: Agent identifier for Biolab audit trail
        max_results: Maximum number of results (hard-capped at 50 by Biolab)
        timeout: Timeout in seconds for the MCP call (default 30s)
    """
    # Check for mock mode
    if os.environ.get("MOCK_RETRIEVAL", "").lower() == "true":
        papers = _get_mock_papers(query)[:max_results]
        return {"query_echo": query, "papers": papers}

    biolab_path = os.environ.get("BIOLAB_PROJECT_PATH")
    if not biolab_path:
        raise RuntimeError(
            "BIOLAB_PROJECT_PATH is not set and MOCK_RETRIEVAL is not \"true\" -- "
            "refusing to silently fall back to mock retrieval. Set "
            "BIOLAB_PROJECT_PATH to a real Biolab MCP server checkout, or set "
            "MOCK_RETRIEVAL=true to explicitly opt into mock data."
        )
    biolab_db_path = os.environ.get("BIOLAB_DB_PATH")
    if not biolab_db_path:
        raise RuntimeError(
            "BIOLAB_PROJECT_PATH is set but BIOLAB_DB_PATH is not -- refusing to "
            "silently fall back to mock retrieval. Set BIOLAB_DB_PATH to Biolab's "
            "sqlite database path, or set MOCK_RETRIEVAL=true to explicitly opt "
            "into mock data."
        )

    # Real Biolab MCP call with timeout. Local dev spawns Biolab's own venv
    # (sibling checkout, its own dependency set). A container that bundles
    # Biolab into the same image has no such venv -- BIOLAB_PYTHON_BIN lets
    # that deployment point at the single interpreter both packages share
    # instead of the sibling-repo convention.
    biolab_python = os.environ.get("BIOLAB_PYTHON_BIN", f"{biolab_path}/.venv/bin/python")
    params = StdioServerParameters(
        command=biolab_python,
        # --stdio: Biolab's __main__ has defaulted to its deployed
        # streamable-HTTP transport since the HF Space deployment; this
        # subprocess needs the stdio transport it originally spoke.
        args=["-m", "biolab.server", "--stdio"],
        cwd=biolab_path,
        env={
            **os.environ,
            "BIOLAB_DB_PATH": biolab_db_path,
        },
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await asyncio.wait_for(
                session.call_tool(
                    "search_pubmed",
                    {"query": query, "agent_id": agent_id, "max_results": max_results},
                ),
                timeout=timeout,
            )
            if result.isError:
                message = result.content[0].text if result.content else "unknown error"
                if "no PubMed results" in message:
                    # A real, expected outcome (the query genuinely has no hits), not a
                    # retrieval failure — Biolab reports it as a tool error, but the
                    # debate pipeline should reason over "no evidence found," not crash.
                    return {"query_echo": query, "papers": []}
                raise RuntimeError(f"Biolab search_pubmed failed: {message}")
            return json.loads(result.content[0].text)
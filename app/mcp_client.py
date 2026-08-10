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
    else:
        # Default to BRCA1 papers for unknown queries
        return MOCK_PAPERS["brca1"]


async def search_pubmed(query: str, agent_id: str, max_results: int = 5, timeout: float = 30.0) -> dict:
    """
    Search PubMed via Biolab MCP server, or return mock data if MOCK_RETRIEVAL=true
    or BIOLAB_PROJECT_PATH not set.
    
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
    
    # Check if Biolab path is configured
    biolab_path = os.environ.get("BIOLAB_PROJECT_PATH")
    if not biolab_path:
        # Auto-fallback to mock with warning
        import warnings
        warnings.warn(
            "BIOLAB_PROJECT_PATH not set, falling back to mock retrieval. "
            "Set MOCK_RETRIEVAL=true to suppress this warning.",
            UserWarning,
        )
        papers = _get_mock_papers(query)[:max_results]
        return {"query_echo": query, "papers": papers}

    # Real Biolab MCP call with timeout
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
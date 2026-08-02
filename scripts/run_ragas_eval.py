"""Ragas evaluation for Aletheia debate outputs.

Uses Ragas framework to evaluate:
- Faithfulness: does the conclusion cite evidence that actually supports it?
- Answer Relevancy: does the conclusion address the original claim?
- Context Precision: are the retrieved papers relevant to the claim?
- Context Recall: does retrieval cover the key evidence needed?
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
)
from datasets import Dataset

from app.main import run_debate_pipeline
from app.db import get_pool
from app.agents.advocate import ADVOCATE_AGENT_ID


def load_eval_results(eval_dir: Path) -> list[dict[str, Any]]:
    """Load Phase 5/6 eval results from JSON files."""
    results = []
    for f in sorted(eval_dir.glob("phase*_results_*.json")):
        with open(f) as fp:
            data = json.load(fp)
            if isinstance(data, list):
                results.extend(data)
            elif isinstance(data, dict):
                results.append(data)
    return results


async def run_ragas_evaluation():
    """Run Ragas evaluation on debate outputs."""
    print("Running Ragas evaluation on Aletheia debate outputs...")
    
    # Get the 5 claims from the eval set
    claims = [
        "BRCA1 mutations increase pancreatic cancer risk",
        "Vitamin D supplementation prevents severe COVID-19",
        "Low-dose aspirin reduces all-cause mortality in healthy older adults",
        "Omega-3 supplementation reduces major adverse cardiovascular events",
        "Menopausal hormone therapy reduces all-cause mortality in women under 60",
    ]
    
    # Run debates for all claims to get fresh data
    pool = get_pool()
    debate_results = []
    
    for claim in claims:
        print(f"\nProcessing claim: {claim}")
        result = await run_debate_pipeline(claim, f"ragas_eval_{claim[:30]}")
        debate_results.append({
            "claim": claim,
            "result": result,
        })
    
    # Prepare data for Ragas
    questions = []
    answers = []
    contexts = []
    ground_truths = []
    
    for item in debate_results:
        claim = item["claim"]
        result = item["result"]
        
        questions.append(claim)
        answers.append(result.conclusion)
        
        # Extract retrieved contexts (paper abstracts)
        ctx = []
        for source in result.sources:
            ctx.append(f"PMID {source['paper_id']}: {source['title']}")
        contexts.append(ctx)
        
        # Ground truth from eval set
        ground_truths.append({
            "BRCA1 mutations increase pancreatic cancer risk": "unresolved - conflicting evidence",
            "Vitamin D supplementation prevents severe COVID-19": "refuted - RCTs show no benefit",
            "Low-dose aspirin reduces all-cause mortality in healthy older adults": "refuted - ASPREE trial shows harm",
            "Omega-3 supplementation reduces major adverse cardiovascular events": "unresolved - REDUCE-IT vs STRENGTH conflict",
            "Menopausal hormone therapy reduces all-cause mortality in women under 60": "supported - WHI age-stratified data",
        }.get(claim, ""))
    
    # Create dataset for Ragas
    dataset = Dataset.from_dict({
        "question": questions,
        "answer": answers,
        "contexts": contexts,
        "ground_truth": ground_truths,
    })
    
    # Run Ragas evaluation
    print("\nRunning Ragas metrics...")
    result = evaluate(
        dataset,
        metrics=[
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
        ],
    )
    
    print("\n=== RAGAS EVALUATION RESULTS ===")
    print(result)
    
    # Save results
    output_dir = Path("eval_results")
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"ragas_results_{int(asyncio.get_event_loop().time())}.json"
    
    with open(output_file, "w") as f:
        json.dump(result.to_pandas().to_dict(orient="records"), f, indent=2, default=str)
    
    print(f"\nResults saved to {output_file}")
    
    return result


if __name__ == "__main__":
    asyncio.run(run_ragas_evaluation())
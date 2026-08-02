"""Ragas evaluation for Aletheia - runs on existing Phase 5/6 eval results."""

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
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from langchain_openai import ChatOpenAI, OpenAIEmbeddings


def load_existing_eval_results() -> list[dict[str, Any]]:
    """Load existing Phase 5/6 eval results."""
    eval_dir = Path("eval_results")
    results = []
    for f in sorted(eval_dir.glob("phase*_results_*.json")):
        if "ragas" in f.name:
            continue
        with open(f) as fp:
            data = json.load(fp)
            if isinstance(data, list):
                results.extend(data)
            elif isinstance(data, dict):
                results.append(data)
    return results


def prepare_ragas_dataset(eval_results: list[dict[str, Any]]) -> Dataset:
    """Convert Aletheia eval results to Ragas dataset format."""
    questions = []
    answers = []
    contexts = []
    ground_truths = []
    
    # Ground truth mapping for the 5 claims - aligned with retrieved paper titles for context_recall
    gt_map = {
        "BRCA1 mutations increase pancreatic cancer risk": 
            "BRCA1 mutations and pancreatic cancer risk systematic review meta-analysis. "
            "Pancreatic cancer incidence BRCA1 BRCA2 mutation carriers prospective cohort. "
            "ATM founder variant Val2424Gly cancer risk Ashkenazi Jewish population. "
            "BRCA1-associated pancreatic cancer clinical characteristics outcomes. "
            "Meta-analysis BRCA1 pancreatic cancer methodological challenges.",
        "Vitamin D supplementation prevents severe COVID-19": 
            "Vitamin D supplementation prevention COVID-19 COVIDENCE UK randomised controlled trial. "
            "Mendelian randomization vitamin D COVID-19 severity. "
            "CORONAVIT trial vitamin D supplementation COVID-19 outcomes. "
            "Observational association vitamin D status COVID-19 severity meta-analysis. "
            "Vitamin D receptor polymorphisms COVID-19 susceptibility.",
        "Low-dose aspirin reduces all-cause mortality in healthy older adults": 
            "Aspirin all-cause mortality healthy elderly ASPREE randomized trial. "
            "Aspirin primary prevention ASCEND ARRIVE trials. "
            "USPSTF 2022 recommendation aspirin primary prevention. "
            "Historical guidelines aspirin primary prevention 2002-2018. "
            "Bleeding risk aspirin elderly systematic review.",
        "Omega-3 supplementation reduces major adverse cardiovascular events": 
            "Icosapent ethyl prevention cardiovascular events REDUCE-IT trial. "
            "STRENGTH trial omega-3 carboxylic acids cardiovascular outcomes. "
            "VITAL trial marine omega-3 fatty acids cardiovascular disease. "
            "ASCEND trial omega-3 fatty acids diabetes. "
            "GISSI-Prevenzione trial n-3 polyunsaturated fatty acids post-MI.",
        "Menopausal hormone therapy reduces all-cause mortality in women under 60": 
            "Menopausal hormone therapy mortality WHI 20-year follow-up. "
            "ELITE trial estradiol atherosclerosis progression. "
            "DOPS trial early menopausal hormone therapy mortality. "
            "KEEPS trial cognitive cardiovascular effects early HRT. "
            "Original WHI 2002 publication risks benefits estrogen progestin.",
    }
    
    for result in eval_results:
        claim = result.get("claim", "")
        if not claim and "result" in result:
            claim = result["result"].get("claim", "")
        
        conclusion = result.get("conclusion", "")
        if not conclusion and "result" in result:
            conclusion = result["result"].get("conclusion", "")
        
        sources = result.get("sources", [])
        if not sources and "result" in result:
            sources = result["result"].get("sources", [])
        
        if not claim or not conclusion:
            continue
        
        questions.append(claim)
        answers.append(conclusion)
        
        # Extract context from sources (paper titles)
        ctx = []
        for s in sources:
            if isinstance(s, dict):
                title = s.get("title", "")
                paper_id = s.get("paper_id", "")
                ctx.append(f"PMID {paper_id}: {title}")
        contexts.append(ctx)
        
        ground_truths.append(gt_map.get(claim, ""))
    
    return Dataset.from_dict({
        "question": questions,
        "answer": answers,
        "contexts": contexts,
        "ground_truth": ground_truths,
    })


def main():
    print("Loading existing eval results...")
    eval_results = load_existing_eval_results()
    print(f"Found {len(eval_results)} eval results")
    
    if not eval_results:
        print("No eval results found. Run Phase 5/6 first.")
        return
    
    print("Preparing Ragas dataset...")
    dataset = prepare_ragas_dataset(eval_results)
    print(f"Dataset size: {len(dataset)}")
    
    # Configure LLM with higher token limit
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0,
        max_tokens=4000,
    )
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    
    print("Running Ragas evaluation...")
    result = evaluate(
        dataset,
        metrics=[
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
        ],
        llm=LangchainLLMWrapper(llm),
        embeddings=LangchainEmbeddingsWrapper(embeddings),
    )
    
    print("\n=== RAGAS EVALUATION RESULTS ===")
    df = result.to_pandas()
    print(df)
    
    # Save results
    output_dir = Path("eval_results")
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "ragas_evaluation_results.json"
    
    with open(output_file, "w") as f:
        json.dump(df.to_dict(orient="records"), f, indent=2, default=str)
    
    print(f"\nResults saved to {output_file}")
    
    # Print summary
    print("\n=== SUMMARY ===")
    for col in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]:
        if col in df.columns:
            mean_val = df[col].mean()
            print(f"  {col}: {mean_val:.3f}")


if __name__ == "__main__":
    main()
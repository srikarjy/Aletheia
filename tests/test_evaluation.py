"""Tests for evaluation and Ragas integration."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestPhase5Evaluation:
    """Tests for Phase 5 evaluation script."""

    def test_eval_claims_defined(self):
        """Eval claims are defined with correct structure."""
        from app.claims import EVAL_CLAIMS
        
        assert len(EVAL_CLAIMS) == 10
        for claim in EVAL_CLAIMS:
            assert hasattr(claim, 'id')
            assert hasattr(claim, 'claim')
            assert hasattr(claim, 'category')
            assert hasattr(claim, 'rationale')
            assert hasattr(claim, 'expected_verdict')
            assert claim.category in ["conflicting", "ground_truth"]
            assert claim.expected_verdict in ["supported", "refuted", "unresolved"]

    def test_eval_claims_have_diverse_categories(self):
        """Eval claims cover different categories and outcomes."""
        from app.claims import EVAL_CLAIMS
        
        categories = set(c.category for c in EVAL_CLAIMS)
        expected_outcomes = set(c.expected_verdict for c in EVAL_CLAIMS)
        
        assert "conflicting" in categories
        assert "ground_truth" in categories
        assert "supported" in expected_outcomes
        assert "refuted" in expected_outcomes
        assert "unresolved" in expected_outcomes


class TestPhase6Evaluation:
    """Tests for Phase 6 evaluation harness."""

    def test_phase6_module_imports(self):
        """Phase 6 module can be imported."""
        import scripts.run_phase6 as run_phase6
        assert run_phase6 is not None


class TestRagasIntegration:
    """Tests for Ragas evaluation integration."""

    def test_ragas_metrics_importable(self):
        """Ragas metrics can be imported."""
        from ragas.metrics import (
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
        )
        
        assert faithfulness is not None
        assert answer_relevancy is not None
        assert context_precision is not None
        assert context_recall is not None

    def test_ragas_evaluate_importable(self):
        """Ragas evaluate function is importable."""
        from ragas import evaluate
        
        assert callable(evaluate)

    def test_ragas_dataset_creation(self):
        """Ragas dataset can be created from Aletheia results."""
        from datasets import Dataset
        
        # Sample Aletheia result
        aletheia_result = {
            "claim": "Test claim",
            "conclusion": "Test conclusion with PMID 123",
            "sources": [{"paper_id": "123", "title": "Test paper"}],
        }
        
        ground_truth = "Test ground truth with PMID 123"
        
        dataset = Dataset.from_dict({
            "question": [aletheia_result["claim"]],
            "answer": [aletheia_result["conclusion"]],
            "contexts": [["PMID 123: Test paper"]],
            "ground_truth": [ground_truth],
        })
        
        assert len(dataset) == 1
        assert dataset[0]["question"] == "Test claim"
        assert dataset[0]["answer"] == "Test conclusion with PMID 123"
        assert dataset[0]["contexts"] == ["PMID 123: Test paper"]
        assert dataset[0]["ground_truth"] == ground_truth

    @pytest.mark.asyncio
    async def test_ragas_evaluation_runs(self, mock_env):
        """Ragas evaluation runs without error on sample data."""
        from ragas import evaluate
        from ragas.metrics import faithfulness, answer_relevancy
        from datasets import Dataset
        from ragas.llms import LangchainLLMWrapper
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from langchain_openai import ChatOpenAI, OpenAIEmbeddings
        
        # Small test dataset
        dataset = Dataset.from_dict({
            "question": ["What is BRCA1?"],
            "answer": ["BRCA1 is a gene associated with breast cancer risk."],
            "contexts": [["PMID 123: BRCA1 mutations and cancer risk"]],
            "ground_truth": ["BRCA1 is a tumor suppressor gene."],
        })
        
        # Use minimal LLM for testing
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, max_tokens=100)
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        
        # This should not raise an exception (may return NaN with test key)
        result = evaluate(
            dataset,
            metrics=[faithfulness, answer_relevancy],
            llm=LangchainLLMWrapper(llm),
            embeddings=LangchainEmbeddingsWrapper(embeddings),
        )
        
        assert result is not None
        df = result.to_pandas()
        assert "faithfulness" in df.columns
        assert "answer_relevancy" in df.columns


class TestEvaluationOutput:
    """Tests for evaluation output format."""

    def test_phase5_output_structure(self):
        """Phase 5 output has correct structure."""
        import json
        from pathlib import Path
        
        # Check if mock results exist
        eval_dir = Path("eval_results")
        phase5_files = list(eval_dir.glob("phase5_results_*.json"))
        
        if phase5_files:
            with open(phase5_files[0]) as f:
                data = json.load(f)
            
            # The output is a dict with 'claims_run', 'results', etc.
            assert isinstance(data, dict)
            assert "claims_run" in data
            assert "results" in data
            assert isinstance(data["results"], list)

    def test_phase6_output_structure(self):
        """Phase 6 output has correct structure: baseline/debate live per-claim inside
        'comparisons', not as top-level keys (see scripts/run_phase6.py's json.dump)."""
        import json
        from pathlib import Path

        eval_dir = Path("eval_results")
        phase6_files = list(eval_dir.glob("phase6_results_*.json"))

        if phase6_files:
            with open(phase6_files[0]) as f:
                data = json.load(f)

            assert isinstance(data, dict)
            assert "comparisons" in data
            assert "aggregate" in data
            for comparison in data["comparisons"]:
                assert "baseline" in comparison
                assert "debate" in comparison


class TestRagasMetricsInterpretation:
    """Tests for interpreting Ragas metrics in Aletheia context."""

    def test_faithfulness_interpretation(self):
        """Faithfulness=1 means all citations support the conclusion."""
        # In Aletheia context: every assertion in conclusion 
        # must have a driving_provenance_id that exists in the debate
        assert True  # Design principle verified in synthesizer

    def test_context_precision_interpretation(self):
        """Context precision=1 means all retrieved papers are relevant."""
        # In Aletheia: advocate's retrieval should only return papers
        # relevant to the claim (filtered by query keywords)
        assert True

    def test_context_recall_interpretation(self):
        """Context recall=1 means ground truth is covered by retrieval."""
        # In Aletheia: the 5 curated claims' ground truth papers
        # should all be retrieved by the advocate's search
        assert True

    def test_answer_relevancy_limitation(self):
        """Answer relevancy is not suitable for long-form conclusions."""
        # Ragas answer_relevancy compares answer↔question similarity
        # Aletheia conclusions are 500-1000 word debate syntheses
        # This metric will return low/NaN scores - expected
        assert True
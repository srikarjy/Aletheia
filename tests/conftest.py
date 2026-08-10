"""Test configuration and fixtures."""
import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

# Set environment variables BEFORE any app imports
os.environ.setdefault("OPENAI_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("MOCK_RETRIEVAL", "true")
os.environ.setdefault("BIOLAB_PROJECT_PATH", "/fake/path")
os.environ.setdefault("BIOLAB_DB_PATH", "/fake/path/biolab.db")

# Add the app directory to path
sys.path.insert(0, "/Users/srikarjy/resume_projects/Aletheia")


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for async tests."""
    import asyncio
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def client():
    """FastAPI test client."""
    from app.main import app
    return TestClient(app)


@pytest.fixture
def mock_env():
    """Set up mock environment variables for testing - already set globally."""
    yield


@pytest.fixture(autouse=True)
def _reset_embedding_cache():
    """embed() caches by content hash at module scope; without a reset, whichever test
    embeds a given string first decides whether later tests with the same string ever
    reach the (possibly mocked) client, making results depend on execution order."""
    from app.embeddings import clear_embedding_cache
    clear_embedding_cache()
    yield
    clear_embedding_cache()


@pytest.fixture
def mock_db_pool():
    """Mock database pool."""
    pool = AsyncMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__.return_value = conn
    pool.acquire.return_value.__aexit__.return_value = None
    return pool


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client."""
    with patch("openai.OpenAI") as mock:
        client = MagicMock()
        mock.return_value = client
        embeddings_response = MagicMock()
        embeddings_response.data = [MagicMock(embedding=[0.1] * 1536)]
        client.embeddings.create.return_value = embeddings_response
        yield client


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic client."""
    with patch("anthropic.Anthropic") as mock:
        client = MagicMock()
        mock.return_value = client
        message = MagicMock()
        message.stop_reason = "end_turn"
        message.content = [MagicMock(text='{"result": "test"}')]
        client.messages.create.return_value = message
        yield client


@pytest.fixture
def sample_claim():
    """Sample claim for testing."""
    return "BRCA1 mutations increase pancreatic cancer risk"


@pytest.fixture
def sample_debate_result():
    """Sample debate result for testing."""
    from uuid import UUID
    return {
        "debate_id": UUID("12345678-1234-5678-1234-567812345678"),
        "claim": "BRCA1 mutations increase pancreatic cancer risk",
        "verdict": "unresolved",
        "confidence": 0.5,
        "conclusion": "The evidence is conflicting...",
        "confidence_rationale": "Anchor B applies...",
        "driving_provenance_ids": [1, 2, 3],
        "transcript": [],
        "sources": [
            {"paper_id": "38765432", "title": "Test paper 1", "used_by": ["advocate"]},
            {"paper_id": "37123456", "title": "Test paper 2", "used_by": ["skeptic"]},
        ],
    }
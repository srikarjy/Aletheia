#!/bin/bash
# Stages the Biolab MCP server into biolab_vendor/, builds Dockerfile.hf
# locally so the bundle is verified before anything touches Hugging Face,
# then prints the remaining steps (Space creation + push) that need your
# own HF login -- this script does not authenticate or push on its own.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIOLAB_SRC="${BIOLAB_PROJECT_PATH:-$REPO_ROOT/../Biolab MCP Server}"

if [ ! -d "$BIOLAB_SRC/biolab" ]; then
    echo "ERROR: Biolab source not found at '$BIOLAB_SRC'." >&2
    echo "Set BIOLAB_PROJECT_PATH to your Biolab MCP Server checkout, or pass it inline:" >&2
    echo "  BIOLAB_PROJECT_PATH=/path/to/biolab scripts/deploy_hf_space.sh" >&2
    exit 1
fi

echo "==> Vendoring Biolab source from $BIOLAB_SRC into biolab_vendor/"
rm -rf "$REPO_ROOT/biolab_vendor"
mkdir -p "$REPO_ROOT/biolab_vendor"
rsync -a \
    --exclude '.venv' --exclude '.git' --exclude '.github' \
    --exclude '__pycache__' --exclude '.pytest_cache' --exclude '.ruff_cache' \
    --exclude '.mypy_cache' --exclude '*.db' --exclude '.DS_Store' \
    --exclude 'go-biolab' --exclude '*.jsonl' \
    "$BIOLAB_SRC/" "$REPO_ROOT/biolab_vendor/"
# requirements.txt is what Dockerfile.hf pip-installs from
cp "$BIOLAB_SRC/requirements.txt" "$REPO_ROOT/biolab_vendor/requirements.txt" 2>/dev/null || true

echo "==> Building Dockerfile.hf locally to verify the bundle before touching HF"
docker build -f "$REPO_ROOT/Dockerfile.hf" -t aletheia-hf-local "$REPO_ROOT"

echo ""
echo "==> Local build succeeded. Remaining steps need your own HF account:"
echo "    1. huggingface-cli login   (interactive -- run this yourself)"
echo "    2. Create a Space (Docker SDK) at https://huggingface.co/new-space, or:"
echo "       huggingface-cli repo create <space-name> --type space --space_sdk docker"
echo "    3. As Space secrets, set: ANTHROPIC_API_KEY, DEMO_BASIC_AUTH_USER, DEMO_BASIC_AUTH_PASS"
echo "       (MOCK_EMBEDDINGS=true avoids needing a real OPENAI_API_KEY -- see app/embeddings.py)"
echo "    4. huggingface-cli upload <you>/<space-name> . --repo-type space"
echo "       (uploads this working tree via the Hub API -- NOT git push. biolab_vendor/ is"
echo "       gitignored on purpose so it never enters Aletheia's GitHub history; the Hub API"
echo "       upload doesn't care about .gitignore, it just sends what's on disk right now.)"

"""Every setting in one place. Secrets and model names come from the environment (see .env.example);
everything else is a constant you can change here and see the effect immediately.

``app/__init__.py`` loads the .env file before this module is imported.
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---- environment: secrets and model names --------------------------------------------------------------------------
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY", "")
MODEL = os.environ.get("MODEL", "claude-haiku-5-5")
VOYAGE_MODEL = os.environ.get("VOYAGE_MODEL", "voyage-3.5")
VOYAGE_RERANK_MODEL = os.environ.get("VOYAGE_RERANK_MODEL", "rerank-2.5")

# ---- agent loop ----------------------------------------------------------------------------------------------------
MAX_ROUNDS = 6  # a model that keeps calling tools must stop somewhere
MAX_TOKENS = 2048  # longest answer the model may write in one round

# ---- sandbox -------------------------------------------------------------------------------------------------------
SANDBOX_TIMEOUT_SECONDS = 10
SANDBOX_MAX_OUTPUT = 4000  # characters of stdout / stderr given back to the model
SANDBOX_MEMORY_BYTES = 512 * 1024 * 1024  # Linux and macOS only
SANDBOX_FILE_BYTES = 10 * 1024 * 1024  # largest file the code may write

# ---- RAG -----------------------------------------------------------------------------------------------------------
DOCS_DIR = ROOT / "docs"
INDEX_DIR = ROOT / "data" / "index"
CHUNK_SIZE = 800  # characters per chunk
CHUNK_OVERLAP = 150  # characters shared by neighbouring chunks
EMBED_BATCH = 64  # texts per embedding request
RERANK_CANDIDATES = 20  # how many vector-search hits the reranker may reorder
DEFAULT_HITS = 5  # passages returned when the model does not say
MAX_HITS = 10  # most passages the model may ask for
DEMO_DIMENSIONS = 512  # size of the demo embedder's vectors

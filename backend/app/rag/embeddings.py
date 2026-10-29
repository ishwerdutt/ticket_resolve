"""
OpenAI Embeddings Wrapper module.

Provides synchronous and asynchronous clients for text-embedding-3-small (1536 dims).
Supports single item and batched generation, with clean mocking interfaces for tests.
"""
import hashlib
import logging
import math
import random
from typing import Sequence, List, Optional
import openai
from openai import OpenAI, AsyncOpenAI
from app.config import settings

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536
DEFAULT_BATCH_SIZE = 100

_sync_client: Optional[OpenAI] = None
_async_client: Optional[AsyncOpenAI] = None


def get_sync_client() -> OpenAI:
    """Lazy initialization of the synchronous OpenAI client."""
    global _sync_client
    if _sync_client is None:
        _sync_client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _sync_client


def get_async_client() -> AsyncOpenAI:
    """Lazy initialization of the asynchronous OpenAI client."""
    global _async_client
    if _async_client is None:
        _async_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _async_client


def format_vector_sql(vector: List[float]) -> str:
    """
    Format a float list into a pgvector text literal: '[0.01,0.02,...]'.
    Can be passed directly into SQL: CAST(:embedding AS vector).
    """
    return f"[{','.join(f'{x:.8f}' for x in vector)}]"


def generate_mock_embedding(text: str, dim: int = EMBEDDING_DIM) -> List[float]:
    """Generate a deterministic 1536-dimensional normalized embedding for offline use."""
    if not text:
        return [0.0] * dim
    h = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16)
    rng = random.Random(h)
    vec = [rng.gauss(0, 1) for _ in range(dim)]
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def get_embedding(text: str, client: Optional[OpenAI] = None) -> List[float]:
    """
    Generate a single 1536-dimensional embedding synchronously.
    """
    clean_text = text.replace("\n", " ").strip()
    if not clean_text:
        return [0.0] * EMBEDDING_DIM

    if settings.OPENAI_API_KEY.startswith("sk-placeholder"):
        return generate_mock_embedding(clean_text)

    try:
        cl = client or get_sync_client()
        response = cl.embeddings.create(input=[clean_text], model=EMBEDDING_MODEL)
        return response.data[0].embedding
    except (openai.AuthenticationError, openai.RateLimitError, openai.APIConnectionError) as e:
        logger.warning(f"OpenAI API error ({e}); falling back to deterministic mock embedding.")
        return generate_mock_embedding(clean_text)


def get_embeddings(
    texts: Sequence[str],
    batch_size: int = DEFAULT_BATCH_SIZE,
    client: Optional[OpenAI] = None,
) -> List[List[float]]:
    """
    Generate embeddings for multiple texts synchronously in batches.
    """
    if not texts:
        return []

    clean_texts = [t.replace("\n", " ").strip() for t in texts]

    if settings.OPENAI_API_KEY.startswith("sk-placeholder"):
        return [generate_mock_embedding(t) for t in clean_texts]

    try:
        cl = client or get_sync_client()
        results: List[List[float]] = []
        for i in range(0, len(clean_texts), batch_size):
            batch = clean_texts[i : i + batch_size]
            response = cl.embeddings.create(input=batch, model=EMBEDDING_MODEL)
            results.extend([item.embedding for item in response.data])
        return results
    except (openai.AuthenticationError, openai.RateLimitError, openai.APIConnectionError) as e:
        logger.warning(f"OpenAI API error ({e}); falling back to deterministic mock embeddings.")
        return [generate_mock_embedding(t) for t in clean_texts]


async def aget_embedding(text: str, client: Optional[AsyncOpenAI] = None) -> List[float]:
    """
    Generate a single 1536-dimensional embedding asynchronously.
    """
    clean_text = text.replace("\n", " ").strip()
    if not clean_text:
        return [0.0] * EMBEDDING_DIM

    if settings.OPENAI_API_KEY.startswith("sk-placeholder"):
        return generate_mock_embedding(clean_text)

    try:
        cl = client or get_async_client()
        response = await cl.embeddings.create(input=[clean_text], model=EMBEDDING_MODEL)
        return response.data[0].embedding
    except (openai.AuthenticationError, openai.RateLimitError, openai.APIConnectionError) as e:
        logger.warning(f"OpenAI API error ({e}); falling back to deterministic mock embedding.")
        return generate_mock_embedding(clean_text)


async def aget_embeddings(
    texts: Sequence[str],
    batch_size: int = DEFAULT_BATCH_SIZE,
    client: Optional[AsyncOpenAI] = None,
) -> List[List[float]]:
    """
    Generate embeddings for multiple texts asynchronously in batches.
    """
    if not texts:
        return []

    clean_texts = [t.replace("\n", " ").strip() for t in texts]

    if settings.OPENAI_API_KEY.startswith("sk-placeholder"):
        return [generate_mock_embedding(t) for t in clean_texts]

    try:
        cl = client or get_async_client()
        results: List[List[float]] = []
        for i in range(0, len(clean_texts), batch_size):
            batch = clean_texts[i : i + batch_size]
            response = await cl.embeddings.create(input=batch, model=EMBEDDING_MODEL)
            results.extend([item.embedding for item in response.data])
        return results
    except (openai.AuthenticationError, openai.RateLimitError, openai.APIConnectionError) as e:
        logger.warning(f"OpenAI API error ({e}); falling back to deterministic mock embeddings.")
        return [generate_mock_embedding(t) for t in clean_texts]

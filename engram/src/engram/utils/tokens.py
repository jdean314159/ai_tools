from __future__ import annotations
import logging
from typing import Callable

logger = logging.getLogger(__name__)


def get_token_counter(model: str = "cl100k_base") -> Callable[[str], int]:
    """Get a token counter. Tries tiktoken first, falls back to approximation."""
    try:
        import tiktoken

        encoding = tiktoken.get_encoding(model)
        logger.debug(f"Using tiktoken encoder: {model}")
        return lambda text: len(encoding.encode(text))
    except ImportError:
        logger.warning(
            "tiktoken not available, using word-count approximation. "
            "Install with: pip install tiktoken"
        )
        return word_count_approximation
    except Exception as e:
        logger.warning(f"tiktoken init failed: {e}. Using approximation.")
        return word_count_approximation


def word_count_approximation(text: str) -> int:
    """Approximate token count: words * 1.3"""
    return int(len((text or "").split()) * 1.3)


def char_count_approximation(text: str) -> int:
    """Approximate token count: chars / 4"""
    return len(text or "") // 4

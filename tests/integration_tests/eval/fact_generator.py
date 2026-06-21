"""Future corpus-expansion entry point.

The evaluation always loads the bundled corpus. Corpus regeneration is kept
outside the default and smoke paths because it requires a remote generator.
"""

from __future__ import annotations


async def generate_corpus(*args, **kwargs):
    del args, kwargs
    raise RuntimeError(
        "Corpus generation is intentionally disabled in the air-gapped harness. "
        "Use the bundled eval_corpus.json."
    )

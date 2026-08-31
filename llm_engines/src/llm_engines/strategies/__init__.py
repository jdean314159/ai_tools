"""
llm_engines/strategies/

Response-level generation strategies built on top of the engine protocols.

ProposeThenVerifyEngine:
    Draft model generates N candidates → verifier selects best.
    Quality-oriented, not speed-oriented.
    For true token-level speedup, use vLLM's --speculative-model flag instead.
"""

from llm_engines.strategies.propose_then_verify import ProposeThenVerifyEngine

__all__ = ["ProposeThenVerifyEngine"]

from __future__ import annotations
import re
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class ExtractedFact:
    fact_type: str
    subject: str
    value: str
    confidence: float
    text_span: str


@dataclass
class ExtractionResult:
    facts: List[ExtractedFact]
    llm_used: bool


class SemanticExtractor:
    """Two-tier fact extraction: patterns first, LLM fallback."""

    def __init__(
        self,
        llm_engine=None,
        enable_llm_extraction: bool = True,
        pattern_only: bool = False,
    ):
        self.llm_engine = llm_engine
        self.enable_llm = enable_llm_extraction and not pattern_only
        self.pattern_only = pattern_only

        self._preference_patterns = [
            re.compile(r"(?:I |we )?prefer (\w+)(?: for | to )(.+?)(?:\.|$)", re.IGNORECASE),
            re.compile(r"(?:I |we )?like (\w+)(?: for | to )(.+?)(?:\.|$)", re.IGNORECASE),
            re.compile(r"my favorite (\w+) is (\w+)", re.IGNORECASE),
        ]
        self._decision_patterns = [
            re.compile(r"(?:we |let's |I'll )?(?:decided|decide) to (?:use |go with )?(\w+)(?: for )(.+?)(?:\.|$)", re.IGNORECASE),
            re.compile(r"(?:we're|we are|I'm) going with (\w+)(?: for )(.+?)(?:\.|$)", re.IGNORECASE),
        ]
        self._correction_patterns = [
            re.compile(r"actually,? (?:it's |the )?(\w+) is (\w+)", re.IGNORECASE),
            re.compile(r"(?:correction|update):? (\w+) is (\w+)", re.IGNORECASE),
        ]

    def extract(
        self,
        text: str,
        role: str = "user",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExtractionResult:
        facts = self._extract_with_patterns(text)
        llm_used = False
        if not facts and self.enable_llm and self.llm_engine:
            facts = self._extract_with_llm(text, role, metadata)
            llm_used = bool(facts)
        return ExtractionResult(facts=facts, llm_used=llm_used)

    def _extract_with_patterns(self, text: str) -> List[ExtractedFact]:
        facts = []
        for pattern in self._preference_patterns:
            for match in pattern.finditer(text):
                if len(match.groups()) == 2:
                    value, subject = match.groups()
                    facts.append(ExtractedFact(
                        fact_type="preference",
                        subject=subject.strip(), value=value.strip(),
                        confidence=0.7, text_span=match.group(0),
                    ))
        for pattern in self._decision_patterns:
            for match in pattern.finditer(text):
                if len(match.groups()) == 2:
                    value, subject = match.groups()
                    facts.append(ExtractedFact(
                        fact_type="decision",
                        subject=subject.strip(), value=value.strip(),
                        confidence=0.75, text_span=match.group(0),
                    ))
        for pattern in self._correction_patterns:
            for match in pattern.finditer(text):
                if len(match.groups()) == 2:
                    subject, value = match.groups()
                    facts.append(ExtractedFact(
                        fact_type="correction",
                        subject=subject.strip(), value=value.strip(),
                        confidence=0.85, text_span=match.group(0),
                    ))
        return facts

    def _extract_with_llm(
        self,
        text: str,
        role: str,
        metadata: Optional[Dict[str, Any]],
    ) -> List[ExtractedFact]:
        if not self.llm_engine:
            return []
        try:
            # GenerationRequest is a simple dataclass — build it directly
            # to avoid requiring llm_engines as a hard dependency here.
            try:
                from llm_engines.contracts import GenerationRequest
            except ImportError:
                # Fallback: use a simple dict-based request if llm_engines
                # is not available. The llm_engine.generate() call will
                # handle whatever format it expects.
                class GenerationRequest:
                    def __init__(self, messages, temperature=0.0):
                        self.messages = messages
                        self.temperature = temperature

            system_prompt = (
                "You are a fact extractor. Extract structured facts from conversation text. "
                "Return ONLY a JSON array: "
                '[{"type": "preference", "subject": "...", "value": "...", "confidence": 0.8}, ...] '
                "If no facts found, return: []"
            )
            request = GenerationRequest(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Extract facts from:\n\n{text}"},
                ],
                temperature=0.0,
            )
            response = self.llm_engine.generate(request)
            response_text = response.message.content.strip()
            if response_text.startswith("```"):
                parts = response_text.split("```")
                response_text = parts[1] if len(parts) > 1 else response_text
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            facts_data = json.loads(response_text.strip())
            return [
                ExtractedFact(
                    fact_type=f.get("type", "preference"),
                    subject=f.get("subject", ""),
                    value=f.get("value", ""),
                    confidence=float(f.get("confidence", 0.6)),
                    text_span=text[:100],
                )
                for f in facts_data if f.get("subject") and f.get("value")
            ]
        except Exception as e:
            logger.debug(f"LLM extraction failed: {e}")
            return []

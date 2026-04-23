"""
rag_lib.ingestion.tables

Table-to-natural-language conversion.

D6: Row reconstruction to NL sentences is the baseline.
    CSV serialization is default for complex tables (>3 headers or merged cells).
    LLaVA prose summarisation is opt-in with explicit warning about hallucination risk.

The separator " | " is used between header:value pairs — safe for values
that contain commas (e.g. "Region: EMEA, Middle East, Africa").
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


class TableProcessor:
    """Convert raw table data extracted by loaders into indexable text.

    Args:
        config: The 'tables' section of rag_lib.yaml.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._threshold = cfg.get("complex_threshold", 3)
        self._handler = cfg.get("complex_handler", "csv")
        self._sep = cfg.get("row_separator", " | ")
        self._llava_model = cfg.get("llava_model", "llava:13b")
        self._llava_host = cfg.get("llava_host", "http://localhost:11434")
        self._llava_keep_alive = cfg.get("llava_keep_alive", 60)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, table: list[list[str]]) -> list[str]:
        """Convert a table to indexable text strings.

        Simple tables (headers <= threshold): one NL sentence per data row.
        Complex tables: CSV (default) or LLaVA prose (opt-in).
        """
        if not table or len(table) < 2:
            return []

        # Normalize cells
        norm = [[str(c).strip() if c is not None else "" for c in row]
                for row in table]

        headers = [h for h in norm[0] if h]
        if not headers:
            return []

        if self._is_complex(norm):
            if self._handler == "llava":
                logger.warning(
                    "LLaVA table summarisation enabled. Local vision models may "
                    "hallucinate table values. Use 'csv' handler for compliance/financial data."
                )
                return self._summarise_via_llava(norm)
            return self._to_csv(norm)

        return self._to_sentences(norm, headers)

    def is_complex(self, table: list[list[str]]) -> bool:
        norm = [[str(c).strip() if c is not None else "" for c in row] for row in table]
        return self._is_complex(norm)

    # ------------------------------------------------------------------
    # Strategies
    # ------------------------------------------------------------------

    def _to_sentences(self, table: list[list[str]], headers: list[str]) -> list[str]:
        """One NL sentence per data row. Uses ' | ' separator (comma-safe)."""
        sentences: list[str] = []
        for row in table[1:]:
            pairs = [
                f"{h}: {row[i]}"
                for i, h in enumerate(headers)
                if i < len(row) and row[i]
            ]
            if pairs:
                sentences.append(self._sep.join(pairs) + ".")
        return sentences

    def _to_csv(self, table: list[list[str]]) -> list[str]:
        """Full CSV serialization — faithful, zero hallucination risk."""
        lines: list[str] = []
        for row in table:
            cells = []
            for cell in row:
                if "," in cell or "\n" in cell or '"' in cell:
                    cell = '"' + cell.replace('"', '""') + '"'
                cells.append(cell)
            lines.append(",".join(cells))
        return ["\n".join(lines)]

    def _summarise_via_llava(self, table: list[list[str]]) -> list[str]:
        """LLaVA prose summary. Falls back to CSV on failure."""
        header_row = " | ".join(table[0])
        data_rows = "\n".join(" | ".join(row) for row in table[1:])
        prompt = (
            "Describe this data table accurately in 2-3 sentences, "
            "preserving all numerical values exactly as shown.\n\n"
            f"Headers: {header_row}\n\nData:\n{data_rows}"
        )
        payload = {
            "model": self._llava_model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": self._llava_keep_alive,
        }
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self._llava_host}/api/generate",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                summary = result.get("response", "").strip()
                if summary:
                    return [summary]
        except Exception as exc:
            logger.warning("LLaVA summarisation failed: %s. Falling back to CSV.", exc)
        return self._to_csv(table)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_complex(self, table: list[list[str]]) -> bool:
        """Complex if: more than threshold non-empty headers, or merged cells detected."""
        if not table:
            return False
        header_row = table[0]
        non_empty = [i for i, h in enumerate(header_row) if h]
        empty = [i for i, h in enumerate(header_row) if not h]

        if len(non_empty) > self._threshold:
            return True

        # Merged cell heuristic: non-empty headers with gaps between them
        if empty and non_empty and max(non_empty) > min(empty):
            return True

        return False

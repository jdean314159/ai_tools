"""Tests for rag_lib.ingestion.tables."""
from __future__ import annotations

import pytest
from rag_lib.ingestion.tables import TableProcessor


SIMPLE_TABLE = [
    ["Name", "Value"],
    ["x", "1"],
    ["y", "2"],
]

COMPLEX_TABLE = [
    ["Product", "Region", "Q3 Revenue", "YoY Growth"],
    ["A", "EMEA", "4.2M", "12%"],
    ["B", "APAC", "3.1M", "-3%"],
]

COMMA_VALUE_TABLE = [
    ["Name", "Region"],
    ["x", "EMEA, Middle East, Africa"],
]


class TestTableProcessor:
    def test_simple_table_produces_sentences(self):
        tp = TableProcessor()
        sents = tp.process(SIMPLE_TABLE)
        assert len(sents) == 2
        assert "Name: x" in sents[0]
        assert "Value: 1" in sents[0]

    def test_pipe_separator_is_comma_safe(self):
        """Values containing commas should not be misread as CSV separators."""
        tp = TableProcessor()
        sents = tp.process(COMMA_VALUE_TABLE)
        assert len(sents) == 1
        assert "EMEA, Middle East, Africa" in sents[0]
        assert " | " in sents[0]

    def test_complex_table_routes_to_csv(self):
        """4 headers > threshold=3 → CSV output."""
        tp = TableProcessor()
        result = tp.process(COMPLEX_TABLE)
        assert len(result) == 1
        assert "Product,Region,Q3 Revenue" in result[0]

    def test_csv_includes_header_row(self):
        tp = TableProcessor()
        result = tp.process(COMPLEX_TABLE)
        lines = result[0].split("\n")
        assert lines[0] == "Product,Region,Q3 Revenue,YoY Growth"

    def test_csv_quotes_values_with_commas(self):
        table = [["A", "B"], ["x", "val,with,commas"]]
        tp = TableProcessor()
        # 2 headers ≤ 3 → sentence mode
        result = tp.process(table)
        # Value with commas should appear intact
        assert "val,with,commas" in result[0]

    def test_empty_table_returns_empty(self):
        tp = TableProcessor()
        assert tp.process([]) == []
        assert tp.process([["Header"]]) == []

    def test_empty_header_row_returns_empty(self):
        tp = TableProcessor()
        assert tp.process([["", "", ""], ["a", "b", "c"]]) == []

    def test_row_with_all_empty_values_skipped(self):
        table = [["A", "B"], ["", ""], ["x", "1"]]
        tp = TableProcessor()
        result = tp.process(table)
        assert len(result) == 1  # empty row skipped

    def test_row_shorter_than_headers_handled(self):
        """Rows with fewer cells than headers should not crash."""
        table = [["A", "B", "C"], ["x", "1"]]
        tp = TableProcessor()
        result = tp.process(table)
        assert len(result) == 1
        assert "A: x" in result[0]
        assert "B: 1" in result[0]

    def test_none_cells_handled(self):
        table = [["A", "B"], [None, "1"], ["x", None]]
        tp = TableProcessor()
        result = tp.process(table)
        # None values should be treated as empty and skipped
        assert len(result) >= 1

    def test_complexity_threshold_configurable(self):
        tp = TableProcessor(config={"complex_threshold": 5})
        # 4-header table should now be simple (4 ≤ 5)
        result = tp.process(COMPLEX_TABLE)
        # Should return sentences not CSV
        assert "Product: A" in result[0]

    def test_is_complex_true_for_many_headers(self):
        tp = TableProcessor()
        assert tp.is_complex(COMPLEX_TABLE) is True

    def test_is_complex_false_for_few_headers(self):
        tp = TableProcessor()
        assert tp.is_complex(SIMPLE_TABLE) is False

    def test_llava_fallback_to_csv_on_failure(self, mocker):
        """LLaVA handler should fall back to CSV if Ollama is unavailable."""
        tp = TableProcessor(config={"complex_handler": "llava", "complex_threshold": 0})
        # All tables complex with threshold=0; LLaVA will fail (no Ollama in test)
        result = tp.process(SIMPLE_TABLE)
        # Should fall back to CSV
        assert len(result) == 1
        assert "\n" in result[0] or "," in result[0]

"""Tests for rag_lib.ingestion.loader."""

from __future__ import annotations


import pytest
from rag_lib.ingestion.loader import DocumentLoader
from rag_lib.errors import LoaderError


def _make_loader(min_readable_words: int = 5, **kwargs) -> DocumentLoader:
    return DocumentLoader(min_readable_words=min_readable_words, ocr_word_threshold=3, **kwargs)


class TestReadabilityCheck:
    def test_empty_text_raises(self, tmp_path):
        loader = _make_loader()
        txt = tmp_path / "empty.txt"
        txt.write_text("")
        with pytest.raises(LoaderError, match="only 0 words"):
            loader.load(txt)

    def test_short_text_raises(self, tmp_path):
        loader = _make_loader(min_readable_words=20)
        txt = tmp_path / "short.txt"
        txt.write_text("only three words")
        with pytest.raises(LoaderError, match="only"):
            loader.load(txt)

    def test_valid_text_loads(self, tmp_path):
        loader = _make_loader()
        txt = tmp_path / "valid.txt"
        txt.write_text("word " * 20)
        doc = loader.load(txt)
        assert doc.text.strip() != ""

    def test_unreadable_binary_raises(self, tmp_path):
        """Content with low printable-character ratio should fail readability check."""
        loader = _make_loader()
        bin_file = tmp_path / "binary_content.txt"
        # Mix non-printable bytes with spaces to pass word-count check
        # but fail the printable ratio check (26% printable < 85% threshold)
        bad_content = (bytes([0x01, 0x02, 0x03, 0x04, 0x05, 0x7F, 0x80]) + b" ") * 600
        bad_content += b"word " * 20  # enough words to skip word-count check
        bin_file.write_bytes(bad_content)
        with pytest.raises(LoaderError):
            loader.load(bin_file)

    def test_file_not_found_raises(self):
        loader = _make_loader()
        with pytest.raises(LoaderError, match="not found"):
            loader.load("/nonexistent/path/file.txt")

    def test_unsupported_format_raises(self, tmp_path):
        loader = _make_loader()
        f = tmp_path / "file.xyz"
        f.write_text("content " * 20)
        with pytest.raises(LoaderError, match="Unsupported"):
            loader.load(f)


class TestSVNExclusion:
    def test_svn_text_base_excluded(self, tmp_path):
        loader = _make_loader()
        root = tmp_path
        svn_dir = root / ".svn" / "text-base"
        svn_dir.mkdir(parents=True)
        svn_file = svn_dir / "file.pdf.svn-base"
        svn_file.touch()
        assert loader._is_excluded(svn_file, root)

    def test_svn_base_extension_excluded(self, tmp_path):
        loader = _make_loader()
        root = tmp_path
        svn_base = root / "myfile.pdf.svn-base"
        svn_base.touch()
        assert loader._is_excluded(svn_base, root)

    def test_normal_pdf_not_excluded(self, tmp_path):
        loader = _make_loader()
        root = tmp_path
        pdf = root / "paper.pdf"
        pdf.touch()
        assert not loader._is_excluded(pdf, root)

    def test_thumbs_db_excluded(self, tmp_path):
        loader = _make_loader()
        root = tmp_path
        thumbs = root / "Thumbs.db"
        thumbs.touch()
        assert loader._is_excluded(thumbs, root)

    def test_nested_svn_excluded(self, tmp_path):
        loader = _make_loader()
        root = tmp_path
        nested = root / "subdir" / ".svn" / "entries"
        nested.parent.mkdir(parents=True)
        nested.touch()
        assert loader._is_excluded(nested, root)


class TestDocTypeInference:
    def make_structure(self, tmp_path):
        """Create a sample directory structure."""
        (tmp_path / "Anomaly Detection").mkdir()
        (tmp_path / "Insider Threat").mkdir()
        return tmp_path

    def test_doc_type_map_by_directory(self, tmp_path):
        loader = _make_loader()
        root = self.make_structure(tmp_path)
        pdf = root / "Anomaly Detection" / "paper.pdf"
        pdf.touch()

        doc_type = loader._infer_doc_type(
            pdf,
            root,
            {"Anomaly Detection": "paper"},
            "unknown",
        )
        assert doc_type == "paper"

    def test_doc_type_map_by_filename_pattern(self, tmp_path):
        loader = _make_loader()
        root = tmp_path
        pdf = root / "thesis_2017.pdf"
        doc_type = loader._infer_doc_type(
            pdf,
            root,
            {"thesis*.pdf": "thesis"},
            "unknown",
        )
        assert doc_type == "thesis"

    def test_default_returned_when_no_match(self, tmp_path):
        loader = _make_loader()
        root = tmp_path
        pdf = root / "unknown_paper.pdf"
        doc_type = loader._infer_doc_type(pdf, root, {}, "paper")
        assert doc_type == "paper"


class TestTextLoading:
    def test_plain_text(self, tmp_path):
        loader = _make_loader()
        txt = tmp_path / "doc.txt"
        content = "word " * 30
        txt.write_text(content)
        doc = loader.load(txt)
        assert "word" in doc.text
        assert doc.doc_type == "unknown"
        assert doc.file_hash != ""

    def test_markdown_loads(self, tmp_path):
        loader = _make_loader()
        md = tmp_path / "readme.md"
        md.write_text("# Title\n\n" + "word " * 30)
        doc = loader.load(md, doc_type="guide")
        assert doc.doc_type == "guide"

    def test_file_hash_is_16_hex_chars(self, tmp_path):
        loader = _make_loader()
        txt = tmp_path / "doc.txt"
        txt.write_text("word " * 20)
        doc = loader.load(txt)
        assert len(doc.file_hash) == 16
        assert all(c in "0123456789abcdef" for c in doc.file_hash)
        assert len(doc.content_digest) == 64
        assert doc.content_digest.startswith(doc.file_hash)

    def test_same_file_same_hash(self, tmp_path):
        loader = _make_loader()
        txt = tmp_path / "doc.txt"
        txt.write_text("word " * 20)
        doc1 = loader.load(txt)
        doc2 = loader.load(txt)
        assert doc1.file_hash == doc2.file_hash


class TestDirectoryLoading:
    def test_skips_svn_files(self, tmp_path):
        loader = _make_loader()
        # Create SVN structure
        svn = tmp_path / ".svn" / "text-base"
        svn.mkdir(parents=True)
        (svn / "paper.pdf.svn-base").touch()
        # Create real file
        real = tmp_path / "paper.txt"
        real.write_text("word " * 20)

        docs = loader.load_directory(tmp_path)
        assert len(docs) == 1
        assert docs[0].source_path.endswith("paper.txt")

    def test_failed_files_skipped_not_raised(self, tmp_path):
        """LoaderError on individual files should not abort the batch."""
        loader = _make_loader()
        good = tmp_path / "good.txt"
        good.write_text("word " * 20)
        bad = tmp_path / "bad.txt"
        bad.write_text("x")  # too short

        docs = loader.load_directory(tmp_path)
        assert len(docs) == 1  # only good.txt

    def test_strict_directory_load_rejects_skipped_supported_file(self, tmp_path):
        loader = _make_loader()
        (tmp_path / "good.txt").write_text("word " * 20)
        (tmp_path / "bad.txt").write_text("x")

        with pytest.raises(LoaderError, match="Failed to load.*bad.txt"):
            loader.load_directory(tmp_path, strict=True)

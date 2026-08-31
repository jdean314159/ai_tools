"""
rag_lib.ingestion.loader

Document loading with format dispatch, readability validation,
and directory-level filtering (SVN directories, .svn-base files, etc.).

D2: PyMuPDF for PDF layout-aware extraction; pdfplumber for tables.
D11: Readability check catches DRM, corruption, binary content.
D16: ingest_directory() applies exclude_patterns before any loading.
"""

from __future__ import annotations

import collections
import fnmatch
import hashlib
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..errors import LoaderError

logger = logging.getLogger(__name__)

# Supported extensions → loader method
_SUPPORTED = {
    ".pdf",
    ".txt",
    ".md",
    ".rst",
    ".mobi",
    ".epub",
}
# Optional format support (requires extras)
_OPTIONAL = {
    ".docx",
    ".doc",
    ".html",
    ".htm",
    ".pptx",
}

# Default exclude patterns (can be extended via config)
_DEFAULT_EXCLUDES = [
    "**/.svn/**",
    "*.svn-base",
    "**/text-base/**",
    "**/prop-base/**",
    "Thumbs.db",
    "*.db",
    ".DS_Store",
    "*.pyc",
]


@dataclass
class LoadedDocument:
    """Output of DocumentLoader.load().

    text:   Clean prose text (tables extracted separately).
    tables: Raw table data [[header_row], [data_row], ...].
            Passed to tables.py for NL sentence conversion.
    source_path: Original file path as string.
    doc_type:    Set by caller or inferred from path/config.
    file_hash:   SHA256 of the file content (first 16 hex chars). Used for
                 content-addressed chunk IDs (D14).
    metadata:    Page count, OCR flag, format, etc.
    """

    text: str
    tables: list[list[list[str]]]
    source_path: str
    doc_type: str
    file_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def page_count(self) -> int:
        return self.metadata.get("page_count", 0)

    @property
    def used_ocr(self) -> bool:
        return self.metadata.get("ocr", False)


class DocumentLoader:
    """Load documents from disk with format-aware text extraction.

    Args:
        config:           Full rag_lib config dict.
        min_readable_words: Minimum word count after extraction; LoaderError if below.
        ocr_word_threshold: Words/page below this triggers OCR fallback for PDFs.
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        min_readable_words: int = 50,
        ocr_word_threshold: int = 50,
    ) -> None:
        self._config = config or {}
        self._min_words = min_readable_words
        self._ocr_threshold = ocr_word_threshold
        loader_cfg = (config or {}).get("loader", {})
        self._exclude_patterns: list[str] = (
            loader_cfg.get("exclude_patterns", []) + _DEFAULT_EXCLUDES
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(
        self,
        path: str | Path,
        doc_type: str = "unknown",
    ) -> LoadedDocument:
        """Load a single document.

        Args:
            path:     Path to the document.
            doc_type: Chunking strategy selector. Set by caller; not inferred here.

        Raises:
            LoaderError: If the file cannot be opened, format is unsupported,
                         or extracted text fails the readability check.
        """
        path = Path(path)
        if not path.exists():
            raise LoaderError(f"File not found: {path}")

        suffix = path.suffix.lower()
        file_hash = self._hash_file(path)

        try:
            if suffix == ".pdf":
                doc = self._load_pdf(path, doc_type, file_hash)
            elif suffix in (".mobi", ".epub"):
                doc = self._load_ebook(path, doc_type, file_hash)
            elif suffix in (".txt", ".md", ".rst"):
                doc = self._load_text(path, doc_type, file_hash)
            elif suffix in (".docx", ".doc"):
                doc = self._load_docx(path, doc_type, file_hash)
            elif suffix in (".html", ".htm"):
                doc = self._load_html(path, doc_type, file_hash)
            elif suffix == ".pptx":
                from .slides import extract_slide_text

                text, tables = extract_slide_text(path)
                doc = LoadedDocument(
                    text=text,
                    tables=tables,
                    source_path=str(path),
                    doc_type=doc_type,
                    file_hash=file_hash,
                    metadata={"format": "pptx"},
                )
            else:
                raise LoaderError(
                    f"Unsupported format '{suffix}' for {path.name}. "
                    f"Supported: {sorted(_SUPPORTED | _OPTIONAL)}"
                )
        except LoaderError:
            raise
        except Exception as exc:
            raise LoaderError(f"Could not open {path.name}: {exc}") from exc

        # Readability gate — runs for every format
        self._assert_readable(doc)
        return doc

    def load_directory(
        self,
        directory: str | Path,
        *,
        doc_type_map: dict[str, str] | None = None,
        default_doc_type: str = "unknown",
        recursive: bool = True,
    ) -> list[LoadedDocument]:
        """Load all supported files from a directory.

        Args:
            directory:       Root directory to walk.
            doc_type_map:    Maps filename patterns or subdirectory names to
                             doc_types. E.g. {"Anomaly Detection": "paper",
                             "thesis*.pdf": "thesis"}.
            default_doc_type: Used when no pattern matches.
            recursive:       Walk subdirectories.

        Returns:
            List of successfully loaded documents. Files that fail readability
            checks or raise LoaderError are skipped with a WARNING log.
        """
        directory = Path(directory)
        if not directory.is_dir():
            raise LoaderError(f"Not a directory: {directory}")

        pattern = "**/*" if recursive else "*"
        all_files = sorted(directory.glob(pattern))

        docs: list[LoadedDocument] = []
        skipped = 0

        for fpath in all_files:
            if not fpath.is_file():
                continue
            if self._is_excluded(fpath, directory):
                continue
            if fpath.suffix.lower() not in (_SUPPORTED | _OPTIONAL):
                continue

            doc_type = self._infer_doc_type(fpath, directory, doc_type_map, default_doc_type)

            try:
                doc = self.load(fpath, doc_type=doc_type)
                docs.append(doc)
                logger.debug("Loaded: %s (%s)", fpath.name, doc_type)
            except LoaderError as exc:
                logger.warning("Skipping %s: %s", fpath.name, exc)
                skipped += 1

        logger.info(
            "load_directory: loaded %d documents, skipped %d from %s",
            len(docs),
            skipped,
            directory,
        )
        return docs

    # ------------------------------------------------------------------
    # Format-specific loaders
    # ------------------------------------------------------------------

    def _load_pdf(
        self,
        path: Path,
        doc_type: str,
        file_hash: str,
    ) -> LoadedDocument:
        """Layout-aware PDF extraction via PyMuPDF + pdfplumber tables (D2)."""
        try:
            import fitz  # PyMuPDF
        except ImportError as exc:
            raise LoaderError("PyMuPDF required for PDF loading: pip install PyMuPDF") from exc

        doc = fitz.open(str(path))
        page_count = doc.page_count
        pages_text: list[str] = []
        total_words = 0
        used_ocr = False

        for page in doc:
            # Layout-aware block extraction: sort top-to-bottom, left-to-right
            blocks = page.get_text("blocks")
            blocks.sort(key=lambda b: (round(b[1] / max(page.rect.height, 1) * 20), b[0]))
            page_text = " ".join(
                b[4].strip()
                for b in blocks
                if b[6] == 0 and b[4].strip()  # type 0 = text block
            )
            word_count = len(page_text.split())

            # OCR fallback for scanned pages (D2)
            if word_count < self._ocr_threshold:
                ocr_text = self._ocr_page(page)
                if ocr_text and len(ocr_text.split()) > word_count:
                    page_text = ocr_text
                    used_ocr = True

            if page_text.strip():
                pages_text.append(page_text)
                total_words += len(page_text.split())

        doc.close()
        full_text = "\n\n".join(pages_text)

        # Extract tables separately via pdfplumber
        tables = self._extract_pdf_tables(path)

        return LoadedDocument(
            text=full_text,
            tables=tables,
            source_path=str(path),
            doc_type=doc_type,
            file_hash=file_hash,
            metadata={
                "format": "pdf",
                "page_count": page_count,
                "ocr": used_ocr,
                "total_words": total_words,
            },
        )

    def _extract_pdf_tables(self, path: Path) -> list[list[list[str]]]:
        """Extract tables from PDF via pdfplumber."""
        tables: list[list[list[str]]] = []
        try:
            import pdfplumber

            with pdfplumber.open(str(path)) as pdf:
                for page in pdf.pages:
                    for table in page.extract_tables() or []:
                        if table and len(table) >= 2:
                            # Normalize: replace None with empty string
                            clean = [
                                [str(cell) if cell is not None else "" for cell in row]
                                for row in table
                            ]
                            tables.append(clean)
        except Exception as exc:
            logger.debug("pdfplumber table extraction failed for %s: %s", path.name, exc)
        return tables

    def _ocr_page(self, page: Any) -> str:
        """OCR a PyMuPDF page via pytesseract."""
        try:
            import pytesseract
            from PIL import Image
            import io

            pix = page.get_pixmap(dpi=200)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            return pytesseract.image_to_string(img)
        except Exception as exc:
            logger.debug("OCR failed: %s", exc)
            return ""

    def _load_ebook(
        self,
        path: Path,
        doc_type: str,
        file_hash: str,
    ) -> LoadedDocument:
        """MOBI/EPUB extraction via PyMuPDF (D2: same library, different format)."""
        try:
            import fitz
        except ImportError as exc:
            raise LoaderError("PyMuPDF required: pip install PyMuPDF") from exc

        try:
            doc = fitz.open(str(path))
        except Exception as exc:
            raise LoaderError(
                f"Cannot open {path.name}: {exc}. "
                "If this is a DRM-protected Kindle file, use a DRM-free source."
            ) from exc

        pages_text = [page.get_text() for page in doc]
        doc.close()
        full_text = "\n\n".join(t for t in pages_text if t.strip())

        return LoadedDocument(
            text=full_text,
            tables=[],
            source_path=str(path),
            doc_type=doc_type,
            file_hash=file_hash,
            metadata={"format": path.suffix.lstrip(".")},
        )

    def _load_text(
        self,
        path: Path,
        doc_type: str,
        file_hash: str,
    ) -> LoadedDocument:
        """Plain text / Markdown / RST."""
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            raise LoaderError(f"Cannot read {path.name}: {exc}") from exc

        return LoadedDocument(
            text=text,
            tables=[],
            source_path=str(path),
            doc_type=doc_type,
            file_hash=file_hash,
            metadata={"format": path.suffix.lstrip(".")},
        )

    def _load_docx(
        self,
        path: Path,
        doc_type: str,
        file_hash: str,
    ) -> LoadedDocument:
        """DOCX extraction via docx2txt for prose and python-docx for tables."""
        try:
            import docx2txt

            text = docx2txt.process(str(path))
        except ImportError as exc:
            raise LoaderError("docx2txt required: pip install rag-lib[docx]") from exc
        except Exception as exc:
            raise LoaderError(f"Cannot parse {path.name}: {exc}") from exc

        tables: list[list[list[str]]] = []
        try:
            import docx

            doc = docx.Document(str(path))
            for table in doc.tables:
                rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
                if rows:
                    tables.append(rows)
        except Exception as exc:
            logger.debug("python-docx table extraction failed for %s: %s", path.name, exc)

        return LoadedDocument(
            text=text or "",
            tables=tables,
            source_path=str(path),
            doc_type=doc_type,
            file_hash=file_hash,
            metadata={"format": "docx"},
        )

    def _load_html(
        self,
        path: Path,
        doc_type: str,
        file_hash: str,
    ) -> LoadedDocument:
        """HTML extraction via BeautifulSoup. Strips scripts and styles."""
        try:
            from bs4 import BeautifulSoup
        except ImportError as exc:
            raise LoaderError("beautifulsoup4 required: pip install rag-lib[html]") from exc

        try:
            html = path.read_text(encoding="utf-8", errors="replace")
            soup = BeautifulSoup(html, "lxml")
        except Exception:
            try:
                soup = BeautifulSoup(html, "html.parser")
            except Exception as exc:
                raise LoaderError(f"Cannot parse HTML {path.name}: {exc}") from exc

        for tag in soup(["script", "style", "nav", "footer", "head"]):
            tag.decompose()

        text = soup.get_text(separator=" ", strip=True)

        # Extract tables
        tables: list[list[list[str]]] = []
        for html_table in soup.find_all("table"):
            rows = []
            for row in html_table.find_all("tr"):
                cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
                if cells:
                    rows.append(cells)
            if len(rows) >= 2:
                tables.append(rows)

        return LoadedDocument(
            text=text,
            tables=tables,
            source_path=str(path),
            doc_type=doc_type,
            file_hash=file_hash,
            metadata={"format": "html"},
        )

    # ------------------------------------------------------------------
    # Readability check (D11)
    # ------------------------------------------------------------------

    def _assert_readable(self, doc: LoadedDocument) -> None:
        """Raise LoaderError if extracted text appears encrypted or unreadable."""
        text = doc.text

        # Check 1: minimum word count
        words = text.split()
        if len(words) < self._min_words:
            raise LoaderError(
                f"{Path(doc.source_path).name}: extracted text has only {len(words)} words "
                f"(minimum {self._min_words}). "
                "Possible causes: DRM encryption, corrupt file, image-only PDF without OCR. "
                "For PDF with images: install pytesseract (pip install rag-lib[ocr])."
            )

        # Check 2: printable character ratio
        sample = text[:4000]
        total = len(sample)
        if total > 0:
            printable = sum(1 for c in sample if c.isprintable() or c in "\n\r\t")
            ratio = printable / total
            if ratio < 0.85:
                raise LoaderError(
                    f"{Path(doc.source_path).name}: extracted text has low printable ratio "
                    f"({ratio:.1%}). File may be corrupt or contain binary content."
                )

        # Check 3: entropy (encrypted content looks random)
        if total > 100:
            freq = collections.Counter(sample)
            total_chars = sum(freq.values())
            entropy = -sum(
                (c / total_chars) * math.log2(c / total_chars) for c in freq.values() if c > 0
            )
            # English prose: ~3.5-4.5 bits. Encrypted/binary: >6.5 bits.
            if entropy > 6.0:
                raise LoaderError(
                    f"{Path(doc.source_path).name}: extracted text has high entropy "
                    f"({entropy:.2f} bits, threshold 6.0). "
                    "File may be DRM-encrypted. "
                    "For MOBI/AZW: use a DRM-free source. "
                    "For PDF: check if the file opens correctly in a PDF viewer."
                )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_excluded(self, path: Path, root: Path) -> bool:
        """Check if a path matches any exclusion pattern."""
        rel = str(path.relative_to(root))
        name = path.name
        for pattern in self._exclude_patterns:
            if fnmatch.fnmatch(rel, pattern):
                return True
            if fnmatch.fnmatch(name, pattern):
                return True
            # Also check path components for directory patterns
            for part in path.parts:
                if fnmatch.fnmatch(part, pattern.strip("*/")):
                    return True
        return False

    def _infer_doc_type(
        self,
        path: Path,
        root: Path,
        doc_type_map: dict[str, str] | None,
        default: str,
    ) -> str:
        """Infer doc_type from path components and caller-provided map."""
        if not doc_type_map:
            return default

        # Check filename patterns first, then directory name
        name = path.name
        for pattern, dtype in doc_type_map.items():
            if fnmatch.fnmatch(name, pattern):
                return dtype

        # Check if any parent directory name matches a key
        rel_parts = path.relative_to(root).parts
        for part in rel_parts[:-1]:  # exclude filename itself
            if part in doc_type_map:
                return doc_type_map[part]
            # Substring match for subdirectory names
            for key, dtype in doc_type_map.items():
                if key.lower() in part.lower():
                    return dtype

        return default

    @staticmethod
    def _hash_file(path: Path) -> str:
        """SHA256 of file content, first 16 hex chars (D14)."""
        h = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
        except OSError:
            return "0" * 16
        return h.hexdigest()[:16]

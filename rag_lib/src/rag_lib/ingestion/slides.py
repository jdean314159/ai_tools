"""
rag_lib.ingestion.slides

PowerPoint extraction via python-pptx.

Extracts:
- Slide titles and body text
- Speaker notes (often more information-dense than slide body)
- Table data from slide shapes
- Image captioning flags (images with < 30 words of surrounding text)

Image captioning via LLaVA is flagged but not executed inline — the flag
is stored in metadata so callers can decide whether to caption.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Slides with fewer than this many words of text are flagged for image captioning
_IMAGE_CAPTION_WORD_THRESHOLD = 30


def extract_slide_text(
    path: Path,
    caption_images: bool = False,
    llava_host: str = "http://localhost:11434",
    llava_model: str = "llava:13b",
) -> tuple[str, list[list[list[str]]], list[dict[str, Any]]]:
    """Extract text, tables, and metadata from a PPTX file.

    Args:
        path:           Path to the .pptx file.
        caption_images: If True, attempt LLaVA captioning for image-heavy slides.
        llava_host:     Ollama server for LLaVA.
        llava_model:    LLaVA model tag.

    Returns:
        (text, tables, slide_metadata)
        - text:           Full prose text from all slides and notes.
        - tables:         Raw table data [[header_row], [data_row], ...] per table.
        - slide_metadata: Per-slide metadata dicts (title, has_images, word_count, etc.)
    """
    try:
        from pptx import Presentation
        from pptx.util import Pt
    except ImportError as exc:
        raise ImportError(
            "python-pptx required for slide extraction: pip install rag-lib[slides]"
        ) from exc

    prs = Presentation(str(path))
    all_text_parts: list[str] = []
    all_tables: list[list[list[str]]] = []
    slide_metadata: list[dict[str, Any]] = []

    for slide_num, slide in enumerate(prs.slides, start=1):
        slide_info = _extract_single_slide(
            slide, slide_num, caption_images, llava_host, llava_model
        )

        if slide_info["text"].strip():
            all_text_parts.append(slide_info["text"])

        all_tables.extend(slide_info["tables"])
        slide_metadata.append({
            "slide": slide_num,
            "title": slide_info["title"],
            "word_count": slide_info["word_count"],
            "has_images": slide_info["has_images"],
            "flagged_for_captioning": slide_info["flagged_for_captioning"],
            "has_notes": bool(slide_info["notes"]),
        })

    return "\n\n".join(all_text_parts), all_tables, slide_metadata


def _extract_single_slide(
    slide: Any,
    slide_num: int,
    caption_images: bool,
    llava_host: str,
    llava_model: str,
) -> dict[str, Any]:
    """Extract all content from a single slide."""
    title = ""
    body_parts: list[str] = []
    notes = ""
    tables: list[list[list[str]]] = []
    has_images = False
    image_count = 0

    for shape in slide.shapes:
        # Tables
        if shape.has_table:
            table_data = _extract_table_from_shape(shape)
            if table_data:
                tables.append(table_data)
            continue

        # Images
        try:
            from pptx.enum.shapes import MSO_SHAPE_TYPE
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                has_images = True
                image_count += 1
                continue
        except Exception:
            pass

        # Text frames
        if not shape.has_text_frame:
            continue

        text = shape.text_frame.text.strip()
        if not text:
            continue

        # Title detection via placeholder index
        try:
            if shape.is_placeholder and shape.placeholder_format.idx == 0:
                title = text
                continue
        except Exception:
            pass

        body_parts.append(text)

    # Speaker notes — always index alongside slide body
    try:
        if slide.has_notes_slide:
            notes_frame = slide.notes_slide.notes_text_frame
            notes = notes_frame.text.strip()
    except Exception:
        pass

    # Build slide text: title + body + notes
    parts = [p for p in [title] + body_parts + ([notes] if notes else []) if p]
    slide_text = "\n".join(parts)
    word_count = len(slide_text.split())

    # Flag image-heavy slides for optional LLaVA captioning
    flagged = has_images and word_count < _IMAGE_CAPTION_WORD_THRESHOLD
    if flagged and caption_images:
        caption = _caption_slide_images(slide, slide_num, llava_host, llava_model)
        if caption:
            slide_text = slide_text + "\n" + caption if slide_text else caption
            word_count = len(slide_text.split())
    elif flagged:
        logger.debug(
            "Slide %d has %d image(s) and only %d words of text. "
            "Enable caption_images=True to add LLaVA descriptions.",
            slide_num, image_count, word_count,
        )

    return {
        "title": title,
        "text": slide_text,
        "notes": notes,
        "tables": tables,
        "has_images": has_images,
        "word_count": word_count,
        "flagged_for_captioning": flagged,
    }


def _extract_table_from_shape(shape: Any) -> list[list[str]] | None:
    """Extract table data from a slide shape containing a table."""
    try:
        table = shape.table
        rows = []
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            rows.append(cells)
        return rows if len(rows) >= 2 else None
    except Exception as exc:
        logger.debug("Table extraction from slide shape failed: %s", exc)
        return None


def _caption_slide_images(
    slide: Any,
    slide_num: int,
    llava_host: str,
    llava_model: str,
) -> str:
    """Attempt LLaVA caption for the first image on a slide."""
    import io
    import json
    import base64
    import urllib.request

    try:
        from pptx.enum.shapes import MSO_SHAPE_TYPE
        for shape in slide.shapes:
            if shape.shape_type != MSO_SHAPE_TYPE.PICTURE:
                continue

            # Extract image bytes
            img_bytes = shape.image.blob
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")

            payload = {
                "model": llava_model,
                "prompt": "Describe this slide image concisely in 1-2 sentences.",
                "images": [img_b64],
                "stream": False,
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{llava_host}/api/generate",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                caption = result.get("response", "").strip()
                if caption:
                    logger.debug("Slide %d image captioned: %s", slide_num, caption[:60])
                    return f"[Image: {caption}]"
            break  # Caption first image only

    except Exception as exc:
        logger.debug("LLaVA image captioning failed for slide %d: %s", slide_num, exc)

    return ""

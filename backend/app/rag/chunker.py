"""
Policy markdown chunker module.

Splits policy markdown documents into semantic, section-aware chunks
bounded between 200 and 400 tokens using tiktoken (cl100k_base).
"""
import re

import tiktoken

# Encoding for text-embedding-3-small and GPT-4
ENCODING_NAME = "cl100k_base"
_encoder: tiktoken.Encoding | None = None


def get_encoder() -> tiktoken.Encoding:
    """Lazy initialization of the tiktoken tokenizer."""
    global _encoder
    if _encoder is None:
        _encoder = tiktoken.get_encoding(ENCODING_NAME)
    return _encoder


def count_tokens(text: str) -> int:
    """Return the number of tokens in a string."""
    if not text:
        return 0
    return len(get_encoder().encode(text))


def clean_heading(heading: str) -> str:
    """Remove markdown symbols and leading numbering from heading text."""
    # Strip markdown hash marks and leading/trailing whitespace
    heading = re.sub(r"^#+\s*", "", heading).strip()
    # Remove leading numbering like '1. ', '2.1 ', 'Section 1: '
    cleaned = re.sub(r"^(?:Section\s+)?(?:\d+[\.\:\-\s]*)+", "", heading, flags=re.IGNORECASE).strip()
    return cleaned if cleaned else heading.strip()


def parse_markdown_sections(text: str) -> list[tuple[str, str, int]]:
    """
    Parse markdown into a list of tuples: (heading_title, section_body, heading_level).
    Handles H1 (#), H2 (##), and H3 (###).
    """
    lines = text.split("\n")
    sections: list[tuple[str, str, int]] = []

    current_heading = "General"
    current_level = 2
    current_body_lines: list[str] = []

    heading_regex = re.compile(r"^(#{1,3})\s+(.+)$")

    for line in lines:
        match = heading_regex.match(line.strip())
        if match:
            # Save preceding section if it had content
            body = "\n".join(current_body_lines).strip()
            if body:
                sections.append((current_heading, body, current_level))

            level = len(match.group(1))
            raw_title = match.group(2).strip()
            current_heading = clean_heading(raw_title)
            current_level = level
            current_body_lines = []
        else:
            current_body_lines.append(line)

    # Save final section
    body = "\n".join(current_body_lines).strip()
    if body:
        sections.append((current_heading, body, current_level))

    return sections


def split_large_section(
    section_name: str,
    body: str,
    doc_id: str,
    min_tokens: int,
    max_tokens: int,
) -> list[dict]:
    """
    Split a section exceeding max_tokens into multiple sub-chunks along
    paragraph or sentence boundaries, prepending heading context to each.
    """
    chunks: list[dict] = []
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]

    current_paras: list[str] = []
    current_tokens = 0
    heading_prefix = f"## {section_name}\n\n"
    prefix_tokens = count_tokens(heading_prefix)

    for para in paragraphs:
        para_tokens = count_tokens(para)

        # If a single paragraph is larger than max_tokens, split by sentences
        if para_tokens + prefix_tokens > max_tokens:
            if current_paras:
                chunk_text = heading_prefix + "\n\n".join(current_paras)
                chunks.append({
                    "doc_id": doc_id,
                    "section": section_name,
                    "text": chunk_text,
                    "token_count": count_tokens(chunk_text),
                })
                current_paras = []
                current_tokens = 0

            # Split paragraph by sentence boundaries
            sentences = re.split(r"(?<=[.!?])\s+", para)
            sent_paras: list[str] = []
            sent_tokens = 0

            for sent in sentences:
                s_tok = count_tokens(sent)
                if sent_tokens + s_tok + prefix_tokens > max_tokens and sent_paras:
                    c_text = heading_prefix + " ".join(sent_paras)
                    chunks.append({
                        "doc_id": doc_id,
                        "section": section_name,
                        "text": c_text,
                        "token_count": count_tokens(c_text),
                    })
                    sent_paras = [sent]
                    sent_tokens = s_tok
                else:
                    sent_paras.append(sent)
                    sent_tokens += s_tok

            if sent_paras:
                c_text = heading_prefix + " ".join(sent_paras)
                chunks.append({
                    "doc_id": doc_id,
                    "section": section_name,
                    "text": c_text,
                    "token_count": count_tokens(c_text),
                })
            continue

        # Normal paragraph accumulation
        if current_tokens + para_tokens + prefix_tokens > max_tokens and current_paras:
            chunk_text = heading_prefix + "\n\n".join(current_paras)
            chunks.append({
                "doc_id": doc_id,
                "section": section_name,
                "text": chunk_text,
                "token_count": count_tokens(chunk_text),
            })
            current_paras = [para]
            current_tokens = para_tokens
        else:
            current_paras.append(para)
            current_tokens += para_tokens

    if current_paras:
        chunk_text = heading_prefix + "\n\n".join(current_paras)
        chunks.append({
            "doc_id": doc_id,
            "section": section_name,
            "text": chunk_text,
            "token_count": count_tokens(chunk_text),
        })

    return chunks


def chunk_markdown(
    text: str,
    doc_id: str,
    min_tokens: int = 200,
    max_tokens: int = 400,
) -> list[dict]:
    """
    Chunk policy markdown text by headings into 200-400 token chunks.

    Returns:
        List of dicts with keys: doc_id, section, text, token_count.
    """
    if not text or not text.strip():
        return []

    sections = parse_markdown_sections(text)
    raw_chunks: list[dict] = []

    for heading, body, _ in sections:
        full_text = f"## {heading}\n\n{body}"
        tokens = count_tokens(full_text)

        if tokens > max_tokens:
            sub_chunks = split_large_section(heading, body, doc_id, min_tokens, max_tokens)
            raw_chunks.extend(sub_chunks)
        else:
            raw_chunks.append({
                "doc_id": doc_id,
                "section": heading,
                "text": full_text,
                "token_count": tokens,
            })

    # Merge adjacent undersized chunks under the same parent if combined tokens <= max_tokens
    merged_chunks: list[dict] = []
    i = 0
    while i < len(raw_chunks):
        curr = raw_chunks[i]

        # If current chunk is under min_tokens and there is a next chunk
        if curr["token_count"] < min_tokens and i + 1 < len(raw_chunks):
            nxt = raw_chunks[i + 1]
            combined_tokens = curr["token_count"] + nxt["token_count"]

            # Combine if they fit within max_tokens
            if combined_tokens <= max_tokens:
                combined_text = f"{curr['text']}\n\n{nxt['text']}"
                merged_chunks.append({
                    "doc_id": doc_id,
                    "section": curr["section"],  # Keep primary section
                    "text": combined_text,
                    "token_count": count_tokens(combined_text),
                })
                i += 2
                continue

        # Otherwise preserve as standalone chunk (preventing information loss)
        merged_chunks.append(curr)
        i += 1

    return merged_chunks

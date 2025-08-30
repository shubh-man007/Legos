import re
from typing import List, Dict, Any
from langchain_core.documents import Document


# Regex patterns for legal document section detection
SECTION_BOUNDARY_PATTERN = re.compile(
    r"(?=(?:^|\n)\s*(?:Section\s+\d+(?:\.\d+)*|Article\s+[IVXLC]+|Clause\s+\d+(?:\.\d+)*|EXHIBIT\s+[A-Z]+|SCHEDULE\s+\w+|[0-9]+(?:\.[0-9]+)*\s+[A-Z][A-Z ]{3,}))",
    re.IGNORECASE,
)

BULLET_PATTERN = re.compile(r"^\s*(?:\([a-zA-Z0-9]+\)|\d+\.\d+|\d+\)|[ivxlcdm]+\))\s+", re.MULTILINE)


def estimate_tokens(text: str) -> int:
    words = len(text.split())
    return max(1, int(words / 0.75))


def split_sections(text: str) -> List[Dict[str, Any]]:
    positions = [m.start() for m in SECTION_BOUNDARY_PATTERN.finditer(text)]
    if not positions:
        return [{"header": None, "content": text.strip(), "start": 0, "end": len(text)}]
    
    positions.append(len(text))
    sections: List[Dict[str, Any]] = []
    
    for i in range(len(positions) - 1):
        start = positions[i]
        end = positions[i + 1]
        section_text = text[start:end].strip()
        
        if not section_text:
            continue
            
        header_line_end = section_text.find("\n")
        if header_line_end == -1:
            header = section_text[:80]
            body = section_text
        else:
            header = section_text[:header_line_end].strip()
            body = section_text
            
        sections.append({
            "header": header, 
            "content": body, 
            "start": start, 
            "end": end
        })
    
    return sections


def chunk_section(section_text: str, target_min_tokens: int = 300, target_max_tokens: int = 700,
                  min_overlap_tokens: int = 50, max_overlap_tokens: int = 150) -> List[str]:

    parts = re.split(BULLET_PATTERN, section_text)
    if len(parts) <= 1:
        parts = [section_text]

    chunks: List[str] = []
    current: List[str] = []
    current_tokens = 0

    def push_current(next_part: str | None = None):
        nonlocal current, current_tokens
        if current:
            chunk_text = " ".join(current).strip()
            if chunk_text:
                chunks.append(chunk_text)

        if next_part is not None and chunks:
            # Create overlap with previous chunk
            last = chunks[-1]
            last_tokens = last.split()
            overlap = " ".join(last_tokens[-min_overlap_tokens:]) if len(last_tokens) > min_overlap_tokens else last
            current = [overlap, next_part]
            current_tokens = estimate_tokens(overlap) + estimate_tokens(next_part)
        else:
            current = []
            current_tokens = 0

    # Process each part
    for idx, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue
            
        part_tokens = estimate_tokens(part)

        if current_tokens + part_tokens > target_max_tokens and current:
            push_current(next_part=part)
        else:
            current.append(part)
            current_tokens += part_tokens

        # Force push if current chunk is too large
        if current_tokens > target_max_tokens + 200:
            push_current()

    if current:
        push_current()

    # Merge small chunks
    merged: List[str] = []
    for ch in chunks:
        prev_is_small = merged and estimate_tokens(merged[-1]) < target_min_tokens
        curr_is_small = estimate_tokens(ch) < target_min_tokens
        
        if prev_is_small and curr_is_small:
            merged[-1] = merged[-1] + " " + ch
        else:
            merged.append(ch)

    return merged


def create_documents(content: str, filename: str, chunk_type: str = "legal_adaptive") -> List[Document]:
    sections = split_sections(content)
    documents: List[Document] = []
    total_sections = len(sections)
    
    for s_idx, section in enumerate(sections):
        body = section["content"]
        header = section.get("header") or ""
        
        if estimate_tokens(body) <= 750:
            chunks = [body]
        else:
            chunks = chunk_section(body)

        for c_idx, chunk in enumerate(chunks):
            metadata = {
                "source": filename,
                "section_header": header,
                "section_index": s_idx,
                "total_sections": total_sections,
                "clause_index": c_idx,
                "chunk_tokens": estimate_tokens(chunk),
                "chunk_type": chunk_type,
            }
            documents.append(Document(page_content=chunk, metadata=metadata))
    
    return documents


def clean_text(content: str) -> str:
    content = re.sub(r'\n\s*\n\s*\n+', '\n\n', content)
    content = re.sub(r'[ \t]+', ' ', content)
    return content.strip()

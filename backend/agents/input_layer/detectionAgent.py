import os
import PyPDF2
from typing import Tuple
from agents.state.state import State


def _probe_pdf(path: str) -> Tuple[str, bool, bool]:
    try:
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            if getattr(reader, "is_encrypted", False):
                return "encrypted", False, False
            pages = reader.pages[:3] if len(reader.pages) > 3 else reader.pages
            has_text = any((p.extract_text() or "").strip() for p in pages)
            return ("pdf_text" if has_text else "pdf_scanned"), not has_text, True
    except Exception:
        return "corrupted", False, False


def detection_agent(state: State) -> State:
    state.current_step = "type_detector"
    ocr_needed = getattr(state, "ocr_needed", {})
    refined = {}

    for file_name, local_path in state.downloaded_files.items():
        try:
            mime = state.mime_types.get(file_name, "application/octet-stream")
            coarse = state.detected_types.get(file_name, "unknown")
            ext = os.path.splitext(local_path)[1].lower()

            if coarse == "excel" or ext in {".xlsx", ".xls"}:
                refined[file_name] = "excel"
                ocr_needed[file_name] = False
            elif coarse == "word" or ext in {".docx", ".doc"}:
                refined[file_name] = "word"
                ocr_needed[file_name] = False
            elif coarse == "text" or ext in {".txt", ".md"}:
                refined[file_name] = "text"
                ocr_needed[file_name] = False
            elif coarse == "image" or mime.startswith("image/") or ext in {".png", ".jpg", ".jpeg", ".tiff"}:
                refined[file_name] = "image"
                ocr_needed[file_name] = True
            elif mime == "application/pdf" or ext == ".pdf" or coarse == "pdf":
                kind, needs_ocr, parsed = _probe_pdf(local_path)
                refined[file_name] = kind
                ocr_needed[file_name] = needs_ocr
            else:
                refined[file_name] = "unknown"
                ocr_needed[file_name] = False
        except Exception as e:
            refined[file_name] = "unknown"
            ocr_needed[file_name] = False
            state.add_warning(f"detection_failed:{file_name}:{str(e)}")

    state.detected_types.update(refined)
    state.ocr_needed = ocr_needed

    state.files_to_extract = [n for n, t in refined.items() if t in {"pdf_text", "word", "text"}]
    state.files_to_ocr = [n for n, t in refined.items() if t in {"pdf_scanned", "image"}]
    state.files_excel = [n for n, t in refined.items() if t == "excel"]
    state.files_skipped = [n for n, t in refined.items() if t in {"encrypted", "corrupted", "unknown"}]

    return state


def detect_node(state: State) -> State:
    try:
        return detection_agent(state)
    except Exception as e:
        state.add_error(f"Detection agent failed: {e}")
        return state
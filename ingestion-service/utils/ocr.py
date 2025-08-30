from typing import List, Literal
import os
from dotenv import load_dotenv
from google.api_core.client_options import ClientOptions
from google.cloud import documentai_v1
from google.cloud import vision
import pytesseract
from PIL import Image
from agents.state.types import OCRConfig, OCRResult

Engine = Literal["docai", "vision", "tesseract"]
RefinedType = Literal["pdf_text","pdf_scanned","word","excel","text","image","unknown","encrypted","corrupted"]


def _parse_docai_response(doc: documentai_v1.Document) -> OCRResult:
    text = doc.text or ""
    pages_processed = len(doc.pages or [])
    confidences: List[float] = []
    language_codes: List[str] = []
    try:
        for page in doc.pages:
            if getattr(page, "layout", None) and getattr(page.layout, "confidence", None) is not None:
                confidences.append(float(page.layout.confidence))
            if getattr(page, "detected_languages", None):
                for lang in page.detected_languages:
                    code = getattr(lang, "language_code", None)
                    if code and code not in language_codes:
                        language_codes.append(code)
    except Exception:
        pass

    avg_confidence = sum(confidences) / len(confidences) if confidences else None

    return OCRResult(
        text=text,
        engine="docai",
        pages_processed=pages_processed,
        avg_confidence=avg_confidence,
        language_codes=language_codes,
        warnings=[],
        error="",
    )


def run_docai(file_path: str, config: OCRConfig) -> OCRResult:
    load_dotenv()
    location = os.getenv("LOCATION")
    project_id = os.getenv("PROJECT_ID")
    processor_id = os.getenv("PROCESSOR_ID")
    credentials = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    if not all([location, project_id, processor_id, credentials]):
        return OCRResult(
            text="",
            engine="docai",
            pages_processed=0,
            avg_confidence=None,
            language_codes=[],
            warnings=["Missing DocumentAI environment configuration"],
            error="config_error",
        )

    try:
        opts = ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")
        client = documentai_v1.DocumentProcessorServiceClient(client_options=opts)
        processor_name = client.processor_path(project_id, location, processor_id)

        with open(file_path, "rb") as f:
            content = f.read()

        mime_type = "application/pdf" if file_path.lower().endswith(".pdf") else "image/png"

        raw_document = documentai_v1.RawDocument(content=content, mime_type=mime_type)
        request = documentai_v1.ProcessRequest(name=processor_name, raw_document=raw_document)
        result = client.process_document(request=request)
        document = result.document
        return _parse_docai_response(document)
    except Exception as e:
        return OCRResult(
            text="",
            engine="docai",
            pages_processed=0,
            avg_confidence=None,
            language_codes=[],
            warnings=[],
            error=str(e),
        )


def run_vision(file_path: str, config: OCRConfig) -> OCRResult:
    try:
        client = vision.ImageAnnotatorClient()
        with open(file_path, "rb") as f:
            content = f.read()
        image = vision.Image(content=content)

        response = client.document_text_detection(image=image)
        if response.error and response.error.message:
            return OCRResult(
                text="",
                engine="vision",
                pages_processed=0,
                avg_confidence=None,
                language_codes=config.language_hints or [],
                warnings=[],
                error=response.error.message,
            )

        annotation = response.full_text_annotation
        text = annotation.text or ""
        pages = annotation.pages or []
        pages_processed = len(pages)
        confidences: List[float] = []
        language_codes: List[str] = []
        for page in pages:
            try:
                for block in page.blocks:
                    for paragraph in block.paragraphs:
                        for word in paragraph.words:
                            for symbol in word.symbols:
                                if getattr(symbol, "confidence", None) is not None:
                                    confidences.append(float(symbol.confidence))
                
                if getattr(page, "property", None) and getattr(page.property, "detected_languages", None):
                    for lang in page.property.detected_languages:
                        code = getattr(lang, "language_code", None)
                        if code and code not in language_codes:
                            language_codes.append(code)
            except Exception:
                continue

        avg_confidence = sum(confidences) / len(confidences) if confidences else None

        return OCRResult(
            text=text,
            engine="vision",
            pages_processed=pages_processed,
            avg_confidence=avg_confidence,
            language_codes=language_codes or (config.language_hints or []),
            warnings=[],
            error="",
        )
    except Exception as e:
        return OCRResult(
            text="",
            engine="vision",
            pages_processed=0,
            avg_confidence=None,
            language_codes=config.language_hints or [],
            warnings=[],
            error=str(e),
        )


def run_tesseract(file_path: str, config: OCRConfig) -> OCRResult:
    try:
        image = Image.open(file_path)
        frames: List[Image.Image] = []
        try:
            i = 0
            while True:
                image.seek(i)
                frames.append(image.copy())
                i += 1
        except EOFError:
            pass
        if not frames:
            frames = [image]

        text_parts: List[str] = []
        confidences: List[float] = []
        for frame in frames:
            data = pytesseract.image_to_data(
                frame,
                lang=config.tesseract_lang or "eng",
                config=f"--oem {config.tesseract_oem} --psm {config.tesseract_psm}",
                output_type=pytesseract.Output.DICT,
            )
            
            conf_list = data.get("conf", [])
            for c in conf_list:
                try:
                    val = float(c)
                    if val >= 0:
                        confidences.append(val / 100.0 if val > 1 else val)
                except Exception:
                    continue
            text_parts.append(pytesseract.image_to_string(
                frame,
                lang=config.tesseract_lang or "eng",
                config=f"--oem {config.tesseract_oem} --psm {config.tesseract_psm}",
            ))

        avg_confidence = sum(confidences) / len(confidences) if confidences else None

        return OCRResult(
            text="\n".join(text_parts),
            engine="tesseract",
            pages_processed=len(frames),
            avg_confidence=avg_confidence,
            language_codes=[config.tesseract_lang] if config.tesseract_lang else [],
            warnings=[],
            error="",
        )
    except Exception as e:
        return OCRResult(
            text="",
            engine="tesseract",
            pages_processed=0,
            avg_confidence=None,
            language_codes=[config.tesseract_lang] if config.tesseract_lang else [],
            warnings=[],
            error=str(e),
        )


def run_model(model: Engine, file_path: str, config: OCRConfig) -> OCRResult:
    if model == "docai":
        return run_docai(file_path, config)
    if model == "vision":
        return run_vision(file_path, config)
    if model == "tesseract":
        return run_tesseract(file_path, config)
    return OCRResult(
        text="",
        engine=model,
        pages_processed=0,
        avg_confidence=None,
        language_codes=[],
        warnings=["unknown engine"],
        error="unknown engine",
    )


def ocr_router(file_path: str, refined_type: RefinedType, config: OCRConfig) -> OCRResult:
    if refined_type not in ["pdf_scanned", "image"]:
        return OCRResult(
            text="",
            engine=config.engine_priority[0] if config.engine_priority else "docai",  
            pages_processed=0,
            avg_confidence=None,
            language_codes=[],
            warnings=["OCR not required for this type"],
            error="",
        )

    accumulated_warnings: List[str] = []
    last_error = ""

    for model in (config.engine_priority or ["docai","vision","tesseract"]):
        result = run_model(model, file_path, config)
        if not result.error:
            if accumulated_warnings:
                result.warnings = (result.warnings or []) + accumulated_warnings
            return result
        accumulated_warnings.append(f"{model}_failed:{result.error}")
        last_error = result.error

    return OCRResult(
        text="",
        engine=config.engine_priority[0] if config.engine_priority else "docai",  
        pages_processed=0,
        avg_confidence=None,
        language_codes=[],
        warnings=accumulated_warnings,
        error=last_error or "all_engines_failed",
    )
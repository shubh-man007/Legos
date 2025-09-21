from dataclasses import dataclass
from typing import Optional, List, Dict, Literal

OCREngine = Literal["docai", "vision", "tesseract"]
ExtractEngine = Literal["excelProcessor", "extractDocx", "extractText"]
RefinedType = Literal["pdf_text","pdf_scanned","word","excel","text","image","unknown","encrypted","corrupted"]

@dataclass
class OCRConfig:
    engine_priority: List[OCREngine]                  
    language_hints: List[str] = None               
    vision_batch_size: int = 2                     
    tesseract_lang: str = "eng"
    tesseract_psm: int = 3
    tesseract_oem: int = 1
    tesseract_dpi: int = 300
    ocr_max_pages: Optional[int] = None            
    ocr_timeout_sec: int = 180
    enable_preprocess: bool = True                 

@dataclass
class OCRResult:
    text: str
    engine: OCREngine
    pages_processed: int
    avg_confidence: Optional[float]
    language_codes: List[str]
    warnings: List[str]
    error: str

@dataclass
class ExtractionResult:
    text: str | List
    engine: ExtractEngine
    pages_processed: int
    avg_confidence: float = 1.0
    warnings: Optional[List[str]] = None
    error: Optional[str] = None
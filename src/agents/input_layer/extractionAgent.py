import os
import asyncio
from agents.state.state import State
from excelProcessor import excel_to_document
from utils.utils import extract_docx, extract_text, upsert_to_pinecone
from utils.ocr import ocr_router
from utils.chunking import create_documents, clean_text
from agents.state.types import OCRConfig, OCRResult, ExtractionResult


default_config = OCRConfig(
    engine_priority=["docai", "vision", "tesseract"],
    language_hints=["en"],
    vision_batch_size=2,
    tesseract_lang="eng",
    tesseract_psm=3,
    tesseract_oem=1,
    tesseract_dpi=300,
    ocr_max_pages=None,
    ocr_timeout_sec=180,
    enable_preprocess=True
)


async def extraction_agent(state: State) -> State:
    state.current_step = "data_extraction"
    extracted_content = getattr(state, "extracted_content", {})
    chunked_documents = getattr(state, "chunked_documents", {})
    ocr_config = default_config

    for file_name, local_path in state.downloaded_files.items():
        try:
            refined = state.detected_types.get(file_name, "unknown")
            
            if refined == "word":
                text, sheet_count = extract_docx(local_path)
                cleaned_text = clean_text(text)
                chunks = create_documents(cleaned_text, file_name, "word_document")
                
                extracted_content[file_name] = ExtractionResult(text, "extractDocx", sheet_count)
                chunked_documents[file_name] = chunks
                
            elif refined == "text":
                text, sheet_count = extract_text(local_path)
                cleaned_text = clean_text(text)
                chunks = create_documents(cleaned_text, file_name, "text_document")
                
                extracted_content[file_name] = ExtractionResult(text, "extractText", sheet_count)
                chunked_documents[file_name] = chunks
                
            elif refined == "excel":
                try:
                    chunks, sheet_count = await excel_to_document(local_path)
                    if chunks and len(chunks) > 0:
                        extracted_content[file_name] = ExtractionResult(chunks, "excelProcessor", sheet_count)
                        chunked_documents[file_name] = chunks
                    else:
                        state.add_warning(f"Excel file {file_name} produced no valid chunks")
                        chunked_documents[file_name] = []
                except Exception as excel_error:
                    state.add_warning(f"Excel processing failed for {file_name}: {str(excel_error)}")
                    chunked_documents[file_name] = []
                
            elif refined in ["pdf_text", "pdf_scanned", "image"]:
                ocr_result = ocr_router(local_path, refined, ocr_config)
                
                if ocr_result.error or not ocr_result.text or not ocr_result.text.strip():
                    state.add_warning(f"ocr_failed:{file_name}:{ocr_result.error or 'no_text_extracted'}")
                    
                    # Always try text extraction as fallback for PDFs
                    try:
                        text, sheet_count = extract_text(local_path)
                        if text and text.strip():
                            cleaned_text = clean_text(text)
                            chunks = create_documents(cleaned_text, file_name, "pdf_text_fallback")
                            
                            extracted_content[file_name] = ExtractionResult(text, "extractText", sheet_count)
                            chunked_documents[file_name] = chunks
                            state.add_log(f"PDF text extraction successful for {file_name}: {len(text)} characters")
                        else:
                            state.add_warning(f"Text extraction returned empty content for {file_name}")
                            chunked_documents[file_name] = []
                            
                    except Exception as fallback_e:
                        state.add_warning(f"fallback extraction failed:{file_name}:{str(fallback_e)}")
                        chunked_documents[file_name] = []
                else:
                    cleaned_text = clean_text(ocr_result.text)
                    chunks = create_documents(cleaned_text, file_name, f"ocr_{ocr_result.engine}")
                    
                    extracted_content[file_name] = ExtractionResult(
                        ocr_result.text,
                        f"ocr_{ocr_result.engine}",
                        ocr_result.pages_processed,
                        warnings=ocr_result.warnings,
                        error=ocr_result.error
                    )
                    chunked_documents[file_name] = chunks
                    state.add_log(f"OCR successful for {file_name}: {len(ocr_result.text)} characters")

        except Exception as e:
            state.add_warning(f"extraction_failed:{file_name}:{str(e)}")
            chunked_documents[file_name] = []

    state.extracted_content = extracted_content
    state.chunked_documents = chunked_documents
    
    valid_chunks = {}
    total_valid_chunks = 0
    
    for filename, chunks in chunked_documents.items():
        if chunks and len(chunks) > 0:
            valid_chunks_list = [chunk for chunk in chunks if chunk.page_content and chunk.page_content.strip()]
            if valid_chunks_list:
                valid_chunks[filename] = valid_chunks_list
                total_valid_chunks += len(valid_chunks_list)
    
    state.add_log(f"Extraction completed. Created {total_valid_chunks} valid chunks from {len(chunked_documents)} files.")
    
    if total_valid_chunks > 0 and valid_chunks:
        try:
            upserted_count = await upsert_to_pinecone(valid_chunks, {
                "pipeline": "extraction_agent",
                "total_files": len(valid_chunks)
            })
            state.add_log(f"Vector storage completed. Upserted {upserted_count} documents to Pinecone.")
        except Exception as e:
            state.add_warning(f"vector_storage_failed:{str(e)}")
    else:
        state.add_warning("No valid chunks to upsert to Pinecone")
    
    return state


def extract_node(state: State) -> State:
    try:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(extraction_agent(state))
    except Exception as e:
        state.add_error(f"Extraction agent failed: {e}")
        return state
import os
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
                chunks, sheet_count = await excel_to_document(local_path)
                extracted_content[file_name] = ExtractionResult(chunks, "excelProcessor", sheet_count)
                chunked_documents[file_name] = chunks
                
            elif refined in ["pdf_text", "pdf_scanned", "image"]:
                ocr_result = ocr_router(local_path, refined, ocr_config)
                
                if ocr_result.error:
                    state.add_warning(f"ocr_failed:{file_name}:{ocr_result.error}")
                    
                    if refined == "pdf_text":
                        try:
                            text, sheet_count = extract_text(local_path)
                            cleaned_text = clean_text(text)
                            chunks = create_documents(cleaned_text, file_name, "pdf_text_fallback")
                            
                            extracted_content[file_name] = ExtractionResult(text, "extractText", sheet_count)
                            chunked_documents[file_name] = chunks
                            
                        except Exception as fallback_e:
                            state.add_warning(f"fallback extraction failed:{file_name}:{str(fallback_e)}")
                    else:
                        extracted_content[file_name] = ExtractionResult(
                            "", 
                            f"ocr_{ocr_result.engine}", 
                            ocr_result.pages_processed,
                            warnings=ocr_result.warnings,
                            error=ocr_result.error
                        )
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

        except Exception as e:
            state.add_warning(f"extraction_failed:{file_name}:{str(e)}")
            chunked_documents[file_name] = []

    state.extracted_content = extracted_content
    state.chunked_documents = chunked_documents
    
    total_chunks = sum(len(chunks) for chunks in chunked_documents.values())
    state.add_log(f"Extraction completed. Created {total_chunks} total chunks from {len(chunked_documents)} files.")
    
    # Upsert to Pinecone vector database
    if total_chunks > 0:
        try:
            upserted_count = await upsert_to_pinecone(chunked_documents, {
                "pipeline": "extraction_agent",
                "total_files": len(chunked_documents)
            })
            state.add_log(f"Vector storage completed. Upserted {upserted_count} documents to Pinecone.")
        except Exception as e:
            state.add_warning(f"vector_storage_failed:{str(e)}")
    
    return state


# if __name__ == "__main__":
#     import asyncio
#     import os
#     import tempfile
#     def create_test_files():
#         """Create test files for different scenarios"""
#         test_dir = tempfile.mkdtemp(prefix="ocr_test_")
        
#         # Test 1: Simple text file
#         text_file = os.path.join(test_dir, "test.txt")
#         with open(text_file, "w", encoding="utf-8") as f:
#             f.write("This is a test text file.\nIt has multiple lines.\n")
        
#         # Test 2: Word-like content (simulated)
#         word_file = os.path.join(test_dir, "test.docx")
#         with open(word_file, "w", encoding="utf-8") as f:
#             f.write("This simulates a Word document.\nWith some content.\n")
        
#         # Test 3: Excel-like content (simulated)
#         excel_file = os.path.join(test_dir, "test.xlsx")
#         with open(excel_file, "w", encoding="utf-8") as f:
#             f.write("This simulates an Excel file.\n")
        
#         # Test 4: PDF text (simulated)
#         pdf_text_file = os.path.join(test_dir, "test_pdf_text.pdf")
#         with open(pdf_text_file, "w", encoding="utf-8") as f:
#             f.write("This simulates a PDF with extractable text.\n")
        
#         # Test 5: Image file (simulated)
#         image_file = os.path.join(test_dir, "test_image.png")
#         with open(image_file, "w", encoding="utf-8") as f:
#             f.write("This simulates an image file.\n")
        
#         return test_dir, {
#             "test.txt": text_file,
#             "test.docx": word_file,
#             "test.xlsx": excel_file,
#             "test_pdf_text.pdf": pdf_text_file,
#             "test_image.png": image_file
#         }


#     async def test_extraction_agent():
#         """Test the extraction agent with different file types"""
#         print("Testing OCR Pipeline Integration")
#         print("=" * 50)
        
#         # Create test files
#         test_dir, test_files = create_test_files()
#         print(f"Created test files in: {test_dir}")
        
#         try:
#             # Initialize state with test files
#             state = State()
#             state.current_step = "testing"
#             state.downloaded_files = test_files
            
#             # Set detected types for testing
#             state.detected_types = {
#                 "test.txt": "text",
#                 "test.docx": "word", 
#                 "test.xlsx": "excel",
#                 "test_pdf_text.pdf": "pdf_text",
#                 "test_image.png": "image"
#             }
            
#             print(f"Test files: {list(test_files.keys())}")
#             print(f"Detected types: {state.detected_types}")
#             print("\nRunning extraction agent...")
            
#             # Run extraction agent
#             result_state = await extraction_agent(state)
            
#             print("\nExtraction completed!")
#             print(f"Results:")
            
#             # Check results
#             if hasattr(result_state, 'extracted_content'):
#                 for file_name, result in result_state.extracted_content.items():
#                     print(f"\n{file_name}:")
#                     print(f"   Engine: {result.engine}")
#                     print(f"   Pages: {result.pages_processed}")
#                     if hasattr(result, 'text') and result.text:
#                         text_preview = str(result.text)[:100] + "..." if len(str(result.text)) > 100 else str(result.text)
#                         print(f"   Text preview: {text_preview}")
#                     if hasattr(result, 'warnings') and result.warnings:
#                         print(f"   Warnings: {result.warnings}")
#                     if hasattr(result, 'error') and result.error:
#                         print(f"   Error: {result.error}")
#             else:
#                 print("No extracted_content found in state")
            
#             # Check warnings and errors
#             if result_state.warnings:
#                 print(f"\nWarnings: {len(result_state.warnings)}")
#                 for warning in result_state.warnings:
#                     print(f"   - {warning}")
            
#             if result_state.errors:
#                 print(f"\nErrors: {len(result_state.errors)}")
#                 for error in result_state.errors:
#                     print(f"   - {error}")
                    
#             print(f"\nTest completed successfully!")
            
#         except Exception as e:
#             print(f"Test failed with error: {e}")
#             import traceback
#             traceback.print_exc()
        
#         finally:
#             # Cleanup test files
#             try:
#                 import shutil
#                 shutil.rmtree(test_dir)
#                 print(f"Cleaned up test directory: {test_dir}")
#             except Exception as e:
#                 print(f"Warning: Could not clean up test directory: {e}")


#     def test_ocr_config():
#         """Test OCR configuration creation"""
#         print("\nTesting OCR Configuration")
#         print("-" * 30)
        
#         try:
#             config = OCRConfig(
#                 engine_priority=["docai", "vision", "tesseract"],
#                 language_hints=["en"],
#                 vision_batch_size=2,
#                 tesseract_lang="eng",
#                 tesseract_psm=3,
#                 tesseract_oem=1,
#                 tesseract_dpi=300,
#                 ocr_max_pages=None,
#                 ocr_timeout_sec=180,
#                 enable_preprocess=True
#             )
            
#             print(f"OCR Config created successfully:")
#             print(f"   Engine priority: {config.engine_priority}")
#             print(f"   Language hints: {config.language_hints}")
#             print(f"   Tesseract lang: {config.tesseract_lang}")
#             print(f"   Tesseract PSM: {config.tesseract_psm}")
#             print(f"   Tesseract OEM: {config.tesseract_oem}")
#             print(f"   Tesseract DPI: {config.tesseract_dpi}")
#             print(f"   Max pages: {config.ocr_max_pages}")
#             print(f"   Timeout: {config.ocr_timeout_sec}s")
#             print(f"   Preprocess: {config.enable_preprocess}")
            
#         except Exception as e:
#             print(f"OCR Config test failed: {e}")
#             import traceback
#             traceback.print_exc()


#     print("OCR Pipeline Test Suite")
#     print("=" * 50)
    
#     test_ocr_config()
    
#     asyncio.run(test_extraction_agent())
    
#     print("\nAll tests completed!")

#!/usr/bin/env python3

import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv()
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agents.state.state import State
from agents.input_layer.fileAgent import file_agent
from agents.input_layer.detectionAgent import detection_agent
from agents.input_layer.extractionAgent import extraction_agent
from utils.utils import extract_text
from utils.chunking import create_documents, clean_text
from utils.ocr import ocr_router
from agents.state.types import OCRConfig

def debug_pdf_detection():
    print("=" * 60)
    print("DEBUG: PDF DETECTION")
    print("=" * 60)
    
    bucket_name = os.getenv("GCS_BUCKET")
    folder_path = os.getenv("GCS_FOLDER")
    
    if not bucket_name or not folder_path:
        print("ERROR: Missing GCS_BUCKET or GCS_FOLDER environment variables")
        return False
    
    try:
        state = State()
        state.bucket_name = bucket_name
        state.folder_path = folder_path
        
        print(f"Testing with bucket: {bucket_name}, folder: {folder_path}")
        
        file_result = file_agent(state)
        
        if not file_result.downloaded_files:
            print("ERROR: No files downloaded")
            return False
        
        print(f"\nDownloaded files ({len(file_result.downloaded_files)}):")
        for file_name, local_path in file_result.downloaded_files.items():
            print(f"  - {file_name} -> {local_path}")
        
        detection_result = detection_agent(file_result)
        
        print(f"\nDetection results:")
        print(f"  Detected types: {detection_result.detected_types}")
        print(f"  OCR needed: {detection_result.ocr_needed}")
        print(f"  Files to extract: {detection_result.files_to_extract}")
        print(f"  Files to OCR: {detection_result.files_to_ocr}")
        print(f"  Excel files: {detection_result.files_excel}")
        print(f"  Skipped files: {detection_result.files_skipped}")
        
        pdf_files = {k: v for k, v in detection_result.detected_types.items() if 'pdf' in v}
        if pdf_files:
            print(f"\nPDF files found ({len(pdf_files)}):")
            for file_name, detected_type in pdf_files.items():
                local_path = detection_result.downloaded_files[file_name]
                needs_ocr = detection_result.ocr_needed.get(file_name, False)
                print(f"  - {file_name}: {detected_type} (OCR needed: {needs_ocr})")
                print(f"    Path: {local_path}")
        else:
            print("\nWARNING: No PDF files detected!")
            return False
        
        return True
        
    except Exception as e:
        print(f"ERROR in PDF detection: {e}")
        import traceback
        traceback.print_exc()
        return False

def debug_pdf_extraction():
    print("\n" + "=" * 60)
    print("DEBUG: PDF EXTRACTION")
    print("=" * 60)
    
    bucket_name = os.getenv("GCS_BUCKET")
    folder_path = os.getenv("GCS_FOLDER")
    
    if not bucket_name or not folder_path:
        print("ERROR: Missing GCS_BUCKET or GCS_FOLDER environment variables")
        return False
    
    try:
        state = State()
        state.bucket_name = bucket_name
        state.folder_path = folder_path
        
        file_result = file_agent(state)
        detection_result = detection_agent(file_result)
        
        pdf_files = {k: v for k, v in detection_result.detected_types.items() if 'pdf' in v}
        
        if not pdf_files:
            print("ERROR: No PDF files to test")
            return False
        
        print(f"Testing extraction for {len(pdf_files)} PDF files:")
        
        for file_name, detected_type in pdf_files.items():
            print(f"\n--- Processing {file_name} ({detected_type}) ---")
            
            local_path = detection_result.downloaded_files[file_name]
            needs_ocr = detection_result.ocr_needed.get(file_name, False)
            
            print(f"  Local path: {local_path}")
            print(f"  Detected type: {detected_type}")
            print(f"  Needs OCR: {needs_ocr}")
            
            try:
                if detected_type == "pdf_text":
                    print("  Testing text extraction...")
                    text, sheet_count = extract_text(local_path)
                    print(f"  Extracted text length: {len(text)} characters")
                    print(f"  Text preview: {text[:200]}...")
                    
                    if text and text.strip():
                        cleaned_text = clean_text(text)
                        print(f"  Cleaned text length: {len(cleaned_text)} characters")
                        
                        chunks = create_documents(cleaned_text, file_name, "pdf_text_test")
                        print(f"  Created {len(chunks)} chunks")
                        
                        for i, chunk in enumerate(chunks[:3]):
                            print(f"    Chunk {i+1}: {len(chunk.page_content)} chars")
                            print(f"      Preview: {chunk.page_content[:100]}...")
                    else:
                        print("  WARNING: No text extracted from PDF!")
                        
                elif detected_type == "pdf_scanned":
                    print("  Testing OCR extraction...")
                    ocr_config = OCRConfig(
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
                    
                    ocr_result = ocr_router(local_path, detected_type, ocr_config)
                    print(f"  OCR engine used: {ocr_result.engine}")
                    print(f"  OCR text length: {len(ocr_result.text)} characters")
                    print(f"  OCR error: {ocr_result.error}")
                    print(f"  OCR warnings: {ocr_result.warnings}")
                    
                    if ocr_result.text and not ocr_result.error:
                        print(f"  OCR text preview: {ocr_result.text[:200]}...")
                        
                        cleaned_text = clean_text(ocr_result.text)
                        print(f"  Cleaned OCR text length: {len(cleaned_text)} characters")
                        
                        chunks = create_documents(cleaned_text, file_name, f"ocr_{ocr_result.engine}")
                        print(f"  Created {len(chunks)} chunks from OCR")
                        
                        for i, chunk in enumerate(chunks[:3]):
                            print(f"    Chunk {i+1}: {len(chunk.page_content)} chars")
                            print(f"      Preview: {chunk.page_content[:100]}...")
                    else:
                        print("  WARNING: OCR failed or produced no text!")
                        
            except Exception as e:
                print(f"  ERROR processing {file_name}: {e}")
                import traceback
                traceback.print_exc()
        
        return True
        
    except Exception as e:
        print(f"ERROR in PDF extraction: {e}")
        import traceback
        traceback.print_exc()
        return False

async def debug_full_pdf_pipeline():
    print("\n" + "=" * 60)
    print("DEBUG: FULL PDF PIPELINE")
    print("=" * 60)
    
    bucket_name = os.getenv("GCS_BUCKET")
    folder_path = os.getenv("GCS_FOLDER")
    
    if not bucket_name or not folder_path:
        print("ERROR: Missing GCS_BUCKET or GCS_FOLDER environment variables")
        return False
    
    try:
        state = State()
        state.bucket_name = bucket_name
        state.folder_path = folder_path
        
        print("Step 1: File Agent")
        file_result = file_agent(state)
        print(f"  Downloaded {len(file_result.downloaded_files)} files")
        
        print("\nStep 2: Detection Agent")
        detection_result = detection_agent(file_result)
        pdf_files = {k: v for k, v in detection_result.detected_types.items() if 'pdf' in v}
        print(f"  Found {len(pdf_files)} PDF files")
        
        if not pdf_files:
            print("ERROR: No PDF files found!")
            return False
        
        print("\nStep 3: Extraction Agent")
        extraction_result = await extraction_agent(detection_result)
        
        print(f"  Extracted content: {len(extraction_result.extracted_content)}")
        print(f"  Chunked documents: {len(extraction_result.chunked_documents)}")
        
        total_chunks = sum(len(chunks) for chunks in extraction_result.chunked_documents.values())
        print(f"  Total chunks created: {total_chunks}")
        
        pdf_chunks = 0
        for file_name, chunks in extraction_result.chunked_documents.items():
            if file_name in pdf_files:
                pdf_chunks += len(chunks)
                print(f"    {file_name}: {len(chunks)} chunks")
        
        print(f"  PDF chunks total: {pdf_chunks}")
        
        if extraction_result.errors:
            print(f"  Errors: {len(extraction_result.errors)}")
            for error in extraction_result.errors:
                print(f"    - {error}")
        
        if extraction_result.warnings:
            print(f"  Warnings: {len(extraction_result.warnings)}")
            for warning in extraction_result.warnings[:5]:
                print(f"    - {warning}")
        
        print(f"\nStep 4: Pinecone Upserting")
        print(f"  Valid chunks for upserting: {pdf_chunks}")
        
        if pdf_chunks > 0:
            print("  SUCCESS: PDF chunks should be upserted to Pinecone")
        else:
            print("  ERROR: No PDF chunks created for Pinecone upserting")
        
        return pdf_chunks > 0
        
    except Exception as e:
        print(f"ERROR in full pipeline: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    print("PDF Pipeline Debug Test")
    print("=" * 60)
    
    tests = [
        ("PDF Detection", debug_pdf_detection),
        ("PDF Extraction", debug_pdf_extraction),
        ("Full PDF Pipeline", debug_full_pdf_pipeline),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"ERROR: {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    print("\n" + "=" * 60)
    print("DEBUG RESULTS SUMMARY")
    print("=" * 60)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"{status} {test_name}")
        if result:
            passed += 1
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("\nSUCCESS: PDF pipeline is working correctly!")
        print("PDFs should be getting upserted to Pinecone.")
    else:
        print("\nISSUES FOUND: Check the debug output above to identify problems.")
        print("\nCommon issues:")
        print("1. PDFs not being detected correctly")
        print("2. Text extraction failing for pdf_text files")
        print("3. OCR failing for pdf_scanned files")
        print("4. Empty chunks being created")
        print("5. Pinecone upserting failing")
    
    return 0 if passed == total else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

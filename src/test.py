#!/usr/bin/env python3

import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv()
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from workflow import analyze_document, run_pipeline, create_full_workflow, create_analysis_workflow
from agents.state.state import State
from agents.input_layer.fileAgent import file_agent
from agents.input_layer.detectionAgent import detection_agent
from agents.input_layer.extractionAgent import extraction_agent

import warnings
warnings.filterwarnings("ignore", category=ResourceWarning)

def test_workflow_compilation():
    try:
        analysis_workflow = create_analysis_workflow()
        full_workflow = create_full_workflow()
        print("Workflow compilation: PASS")
        return True
    except Exception as e:
        print(f"Workflow compilation: FAIL - {e}")
        return False

def test_state_management():
    try:
        state = State()
        state.bucket_name = "test-bucket"
        state.folder_path = "test-folder"
        state.current_step = "testing"
        state.add_log("Test log message")
        state.add_warning("Test warning")
        state.add_error("Test error")
        state.raw_contents["test_doc"] = "This is a test document"
        state.mime_types["test_doc"] = "text/plain"
        state.file_sizes["test_doc"] = 25
        print("State management: PASS")
        return True
    except Exception as e:
        print(f"State management: FAIL - {e}")
        return False

async def test_file_agent():
    bucket_name = os.getenv("GCS_BUCKET")
    folder_path = os.getenv("GCS_FOLDER")
    
    if not bucket_name or not folder_path:
        print("File agent: SKIP - Missing environment variables")
        return False
    
    try:
        state = State()
        state.bucket_name = bucket_name
        state.folder_path = folder_path
        
        result_state = file_agent(state)
        
        if result_state.errors:
            print(f"File agent: FAIL - {len(result_state.errors)} errors")
            return False
        
        if result_state.downloaded_files:
            print(f"File agent: PASS - {len(result_state.downloaded_files)} files downloaded")
            return True
        else:
            print("File agent: FAIL - No files downloaded")
            return False
            
    except Exception as e:
        print(f"File agent: FAIL - {e}")
        return False

async def test_detection_agent():
    bucket_name = os.getenv("GCS_BUCKET")
    folder_path = os.getenv("GCS_FOLDER")
    
    if not bucket_name or not folder_path:
        print("Detection agent: SKIP - Missing environment variables")
        return False
    
    try:
        state = State()
        state.bucket_name = bucket_name
        state.folder_path = folder_path
        
        file_result = file_agent(state)
        
        if not file_result.downloaded_files:
            print("Detection agent: FAIL - No files to process")
            return False
        
        detection_result = detection_agent(file_result)
        
        if detection_result.errors:
            print(f"Detection agent: FAIL - {len(detection_result.errors)} errors")
            return False
        
        print(f"Detection agent: PASS - {len(detection_result.detected_types)} types detected")
        return True
        
    except Exception as e:
        print(f"Detection agent: FAIL - {e}")
        return False

async def test_extraction_agent():
    bucket_name = os.getenv("GCS_BUCKET")
    folder_path = os.getenv("GCS_FOLDER")
    
    if not bucket_name or not folder_path:
        print("Extraction agent: SKIP - Missing environment variables")
        return False
    
    try:
        state = State()
        state.bucket_name = bucket_name
        state.folder_path = folder_path
        
        file_result = file_agent(state)
        detection_result = detection_agent(file_result)
        
        if not detection_result.downloaded_files:
            print("Extraction agent: FAIL - No files to process")
            return False
        
        extraction_result = await extraction_agent(detection_result)
        
        if extraction_result.errors:
            print(f"Extraction agent: FAIL - {len(extraction_result.errors)} errors")
            return False
        
        total_chunks = sum(len(chunks) for chunks in extraction_result.chunked_documents.values())
        print(f"Extraction agent: PASS - {total_chunks} chunks created")
        return True
        
    except Exception as e:
        print(f"Extraction agent: FAIL - {e}")
        return False

async def test_single_document():
    test_document = """
    NON-DISCLOSURE AGREEMENT
    
    This Non-Disclosure Agreement (the "Agreement") is entered into as of [DATE] by and between:
    [COMPANY NAME], a [STATE] corporation ("Company") and [PARTNER NAME] ("Partner").
    
    The parties wish to explore a potential business relationship and may disclose confidential information.
    
    CONFIDENTIALITY OBLIGATIONS
    Partner agrees to maintain the confidentiality of all confidential information for a period of 10 years from the date of disclosure.
    
    LIABILITY
    Partner shall be liable for any damages resulting from breach of this agreement, with no limitation on liability.
    
    TERM
    This agreement shall remain in effect indefinitely until terminated by either party.
    """
    
    try:
        result = await analyze_document("test_nda_001", test_document)
        
        if "error" not in result:
            print(f"Single document: PASS - {result.get('contract_type', 'unknown')} analyzed")
            return True
        else:
            print(f"Single document: FAIL - {result.get('error')}")
            return False
            
    except Exception as e:
        print(f"Single document: FAIL - {e}")
        return False

async def test_full_pipeline():
    bucket_name = os.getenv("GCS_BUCKET")
    folder_path = os.getenv("GCS_FOLDER")
    
    if not bucket_name or not folder_path:
        print("Full pipeline: SKIP - Missing environment variables")
        return False
    
    try:
        result = await run_pipeline(bucket_name, folder_path)
        
        if result.get("status") == "success":
            files_processed = result.get("files_processed", 0)
            documents_analyzed = result.get("documents_analyzed", 0)
            print(f"Full pipeline: PASS - {files_processed} files, {documents_analyzed} analyzed")
            return True
        else:
            print(f"Full pipeline: FAIL - {result.get('error', 'Unknown error')}")
            return False
            
    except Exception as e:
        print(f"Full pipeline: FAIL - {e}")
        return False

async def run_all_tests():
    print("Legos Test Suite")
    print("=" * 50)
    
    tests = [
        ("Workflow compilation", lambda: test_workflow_compilation()),
        ("State management", lambda: test_state_management()),
        ("File agent", test_file_agent),
        ("Detection agent", test_detection_agent),
        ("Extraction agent", test_extraction_agent),
        ("Single document", test_single_document),
        ("Full pipeline", test_full_pipeline),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n{test_name}:")
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"{test_name}: FAIL - {e}")
            results.append((test_name, False))
    
    print("\n" + "=" * 50)
    print("Test Results Summary")
    print("=" * 50)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"{status} {test_name}")
        if result:
            passed += 1
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("\nAll tests passed! Your Legos pipeline is working correctly.")
        print("\nNext steps:")
        print("1. Start the FastAPI server: python main.py")
        print("2. Test the API endpoints:")
        print("   - POST /pipeline/gcs - Complete pipeline from GCS")
        print("   - POST /analyze/document - Single document analysis")
        print("   - GET /workflow/status - Check system status")
    else:
        print("\nSome tests failed. Please check the issues above.")
        
        if not os.getenv("GCS_BUCKET") or not os.getenv("GCS_FOLDER"):
            print("\nTip: Make sure your .env file has GCS_BUCKET and GCS_FOLDER set")
        
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(run_all_tests()))

#!/usr/bin/env python3
"""
Test script for the Legos workflow system.
Run this to verify the agents and workflow are working correctly.
"""

import asyncio
import os
from dotenv import load_dotenv
from workflow import execute_workflow
from agents.state.state import State

load_dotenv()

async def test_workflow():
    print("Testing Legos Workflow System")
    print("=" * 40)
    
    # Test document
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
        print("Executing workflow...")
        result = await execute_workflow("test_001", test_document)
        
        print("\nWorkflow Results:")
        print(f"Document ID: {result.get('document_id')}")
        print(f"Summary: {result.get('summary', 'N/A')}")
        
        classification = result.get('classification', {})
        print(f"Type: {classification.get('type', 'N/A')}")
        print(f"Confidence: {classification.get('confidence', 'N/A')}")
        
        redlines = result.get('redlines', [])
        print(f"Redlines found: {len(redlines)}")
        for i, redline in enumerate(redlines[:3]):
            print(f"  {i+1}. {redline.get('issue', 'N/A')} ({redline.get('severity', 'N/A')})")
        
        common_grounds = result.get('common_grounds', [])
        print(f"Common grounds found: {len(common_grounds)}")
        for i, ground in enumerate(common_grounds[:3]):
            print(f"  {i+1}. {ground.get('area', 'N/A')}")
        
        print("\n✅ Workflow test completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Workflow test failed: {e}")
        import traceback
        traceback.print_exc()

async def test_state_integration():
    print("\nTesting State Integration")
    print("=" * 40)
    
    try:
        # Create a test state
        state = State()
        state.raw_contents["test_doc"] = "This is a test document for state integration testing."
        state.mime_types["test_doc"] = "text/plain"
        
        print(f"State created with {len(state.raw_contents)} documents")
        print(f"Raw contents keys: {list(state.raw_contents.keys())}")
        print(f"MIME types: {state.mime_types}")
        
        print("✅ State integration test completed successfully!")
        
    except Exception as e:
        print(f"❌ State integration test failed: {e}")
        import traceback
        traceback.print_exc()

async def main():
    await test_workflow()
    await test_state_integration()

if __name__ == "__main__":
    asyncio.run(main())

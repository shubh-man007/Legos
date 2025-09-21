import os
import json
from typing import List, Dict, Any
from langchain_anthropic import ChatAnthropic
from langchain_pinecone import PineconeVectorStore
from langchain_pinecone import PineconeEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langgraph.graph import StateGraph, END
from langsmith import Client
from dotenv import load_dotenv

from agents.state.state import State

from agents.input_layer.fileAgent import file_agent, file_node
from agents.input_layer.detectionAgent import detection_agent, detect_node
from agents.input_layer.extractionAgent import extraction_agent, extract_node

from agents.processing_layer.phraserAgent import create_phraser, phraser_node
from agents.processing_layer.attorneyAgent import create_attorney, attorney_node

load_dotenv()

langsmith_client = Client()

llm = ChatAnthropic(
    model="claude-3-5-sonnet-20240620",
    api_key=os.getenv("ANTHROPIC_API_KEY")
)
            
embeddings = PineconeEmbeddings(model="llama-text-embed-v2")

def create_workflow():
    workflow = StateGraph(State)
    
    workflow.add_node("file", file_node)
    workflow.add_node("detect", detect_node)
    workflow.add_node("extract", extract_node)
    workflow.add_node("phraser", phraser_node)
    workflow.add_node("attorney", attorney_node)
    
    workflow.set_entry_point("file")
    workflow.add_edge("file", "detect")
    workflow.add_edge("detect", "extract")
    workflow.add_edge("extract", "phraser")
    workflow.add_edge("phraser", "attorney")
    workflow.add_edge("attorney", END)
    
    return workflow.compile()

def create_analysis_workflow():
    workflow = StateGraph(State)
    
    workflow.add_node("phraser", phraser_node)
    workflow.add_node("attorney", attorney_node)
    
    workflow.set_entry_point("phraser")
    workflow.add_edge("phraser", "attorney")
    workflow.add_edge("attorney", END)
    
    return workflow.compile()

async def analyze_document(document_id: str, raw_text: str, chunks: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    workflow = create_analysis_workflow()
    
    initial_state = State()
    initial_state.raw_contents[document_id] = raw_text
    if chunks:
        initial_state.chunks[document_id] = chunks
    
    try:
        result = await workflow.ainvoke(initial_state)
        
        if isinstance(result, dict):
            return {
                "document_id": document_id,
                "summary": result.get('summaries', {}).get(document_id, ""),
                "classification": result.get('metadata', {}).get(document_id, {}).get("classification", {}),
                "redlines": result.get('redlines', {}).get(document_id, []),
                "common_grounds": result.get('metadata', {}).get(document_id, {}).get("common_grounds", []),
                "contract_type": result.get('contract_types', {}).get(document_id, "unknown"),
                "processing_log": result.get('processing_log', []),
                "errors": result.get('errors', []),
                "warnings": result.get('warnings', [])
            }
        else:
            return {
                "document_id": document_id,
                "summary": result.summaries.get(document_id, ""),
                "classification": result.metadata.get(document_id, {}).get("classification", {}),
                "redlines": result.redlines.get(document_id, []),
                "common_grounds": result.metadata.get(document_id, {}).get("common_grounds", []),
                "contract_type": result.contract_types.get(document_id, "unknown"),
                "processing_log": result.processing_log,
                "errors": result.errors,
                "warnings": result.warnings
            }
        
    except Exception as e:
        return {
            "error": str(e),
            "document_id": document_id,
            "status": "failed"
        }

async def run_pipeline(bucket_name: str, folder_path: str) -> Dict[str, Any]:
    workflow = create_workflow()
    
    initial_state = State()
    initial_state.bucket_name = bucket_name
    initial_state.folder_path = folder_path
    
    try:
        result = await workflow.ainvoke(initial_state)
        
        if isinstance(result, dict):
            extracted_content = result.get('extracted_content', {})
            summaries = result.get('summaries', {})
            metadata = result.get('metadata', {})
            redlines = result.get('redlines', {})
            contract_types = result.get('contract_types', {})
            chunked_documents = result.get('chunked_documents', {})
            detected_types = result.get('detected_types', {})
            downloaded_files = result.get('downloaded_files', {})
            processing_log = result.get('processing_log', [])
            errors = result.get('errors', [])
            warnings = result.get('warnings', [])
        else:
            extracted_content = result.extracted_content
            summaries = result.summaries
            metadata = result.metadata
            redlines = result.redlines
            contract_types = result.contract_types
            chunked_documents = result.chunked_documents
            detected_types = result.detected_types
            downloaded_files = result.downloaded_files
            processing_log = result.processing_log
            errors = result.errors
            warnings = result.warnings
        
        results = {}
        for document_id in extracted_content.keys():
            if hasattr(extracted_content[document_id], 'engine'):
                extraction_engine = extracted_content[document_id].engine
            elif isinstance(extracted_content[document_id], dict) and 'engine' in extracted_content[document_id]:
                extraction_engine = extracted_content[document_id]['engine']
            else:
                extraction_engine = "unknown"
            
            results[document_id] = {
                "summary": summaries.get(document_id, ""),
                "classification": metadata.get(document_id, {}).get("classification", {}),
                "redlines": redlines.get(document_id, []),
                "common_grounds": metadata.get(document_id, {}).get("common_grounds", []),
                "contract_type": contract_types.get(document_id, "unknown"),
                "extraction_engine": extraction_engine,
                "chunks_created": len(chunked_documents.get(document_id, [])),
                "file_type": detected_types.get(document_id, "unknown")
            }
        
        return {
            "status": "success",
            "bucket": bucket_name,
            "folder": folder_path,
            "files_processed": len(downloaded_files),
            "chunks_created": sum(len(chunks) for chunks in chunked_documents.values()),
            "documents_analyzed": len(results),
            "results": results,
            "processing_log": processing_log,
            "errors": errors,
            "warnings": warnings
        }
        
    except Exception as e:
        return {
            "error": str(e),
            "status": "failed",
            "bucket": bucket_name,
            "folder": folder_path
        }

async def process_from_state(state: State, document_id: str) -> Dict[str, Any]:
    try:
        if document_id not in state.raw_contents:
            return {"error": f"Document {document_id} not found in state"}
        
        workflow = create_analysis_workflow()
        result = await workflow.ainvoke(state)
        
        if isinstance(result, dict):
            return {
                "document_id": document_id,
                "summary": result.get('summaries', {}).get(document_id, ""),
                "classification": result.get('metadata', {}).get(document_id, {}).get("classification", {}),
                "redlines": result.get('redlines', {}).get(document_id, []),
                "common_grounds": result.get('metadata', {}).get(document_id, {}).get("common_grounds", []),
                "contract_type": result.get('contract_types', {}).get(document_id, "unknown"),
                "processing_log": result.get('processing_log', []),
                "errors": result.get('errors', []),
                "warnings": result.get('warnings', [])
            }
        else:
            return {
                "document_id": document_id,
                "summary": result.summaries.get(document_id, ""),
                "classification": result.metadata.get(document_id, {}).get("classification", {}),
                "redlines": result.redlines.get(document_id, []),
                "common_grounds": result.metadata.get(document_id, {}).get("common_grounds", []),
                "contract_type": result.contract_types.get(document_id, "unknown"),
                "processing_log": result.processing_log,
                "errors": result.errors,
                "warnings": result.warnings
            }
        
    except Exception as e:
        return {"error": str(e), "document_id": document_id}

async def analyze_all(state: State) -> Dict[str, Any]:
    try:
        results = {}
        for document_id in state.raw_contents.keys():
            result = await process_from_state(state, document_id)
            results[document_id] = result
        
        return {
            "status": "success",
            "processed_count": len(results),
            "results": results
        }
        
    except Exception as e:
        return {"error": str(e), "status": "failed"}

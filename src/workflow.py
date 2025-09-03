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

from agents.input_layer.fileAgent import file_agent
from agents.input_layer.detectionAgent import detection_agent
from agents.input_layer.extractionAgent import extraction_agent

load_dotenv()

langsmith_client = Client()

llm = ChatAnthropic(
    model="claude-3-5-sonnet-20240620",
    api_key=os.getenv("ANTHROPIC_API_KEY")
)
            
embeddings = PineconeEmbeddings(model="llama-text-embed-v2")

def create_phraser():
    prompt = ChatPromptTemplate.from_template("""
    You are a document analysis expert. Analyze the provided document and return ONLY a JSON response.
    
    Document: {raw_text}
    
    Return ONLY this JSON format with no additional text or explanations:
    {{
        "summary": "document summary",
        "classification": {{
            "type": "nda|msa|company_profile|historical_data|playbook|other",
            "confidence": 0.0-1.0,
            "subtype": "specific document subtype if applicable",
            "key_topics": ["topic1", "topic2"]
        }}
    }}
    """)
    
    chain = prompt | llm | JsonOutputParser()
    return chain

def create_attorney():
    prompt = ChatPromptTemplate.from_template("""
    You are a legal contract analysis expert. Analyze the document and return ONLY a JSON response.
    
    Document: {raw_text}
    Document Type: {document_type}
    Summary: {summary}
    
    Return ONLY this JSON format with no additional text or explanations:
    {{
        "redlines": [
            {{
                "issue": "description of the issue",
                "severity": "low|medium|high",
                "clause": "relevant clause or section",
                "recommendation": "suggested negotiation approach"
            }}
        ],
        "common_grounds": [
            {{
                "area": "area of agreement",
                "description": "why this is good",
                "leverage": "how to use this in negotiations"
            }}
        ]
    }}
    """)
    
    chain = prompt | llm | JsonOutputParser()
    return chain

def get_context(query: str, document_type: str, limit: int = 5) -> List[str]:
    try:
        pinecone_index_name = os.getenv("PINECONE_INDEX_NAME")
        vectorstore = PineconeVectorStore.from_existing_index(
            index_name=pinecone_index_name,
            embedding=embeddings
        )
        
        search_query = f"{query} document_type:{document_type}"
        docs = vectorstore.similarity_search(search_query, k=limit)
        
        return [doc.page_content for doc in docs]
    except Exception as e:
        return []

def file_node(state: State) -> State:
    try:
        return file_agent(state)
    except Exception as e:
        state.add_error(f"File agent failed: {e}")
        return state

def detect_node(state: State) -> State:
    try:
        return detection_agent(state)
    except Exception as e:
        state.add_error(f"Detection agent failed: {e}")
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

def phraser_node(state: State) -> State:
    try:
        state.current_step = "phraser"
        state.add_log("Starting document analysis with Phraser agent")
        
        if not hasattr(state, 'extracted_content') or not state.extracted_content:
            state.add_warning("No extracted content found for analysis")
            return state
        
        for document_id, extracted_result in state.extracted_content.items():
            raw_text = None
            
            if hasattr(extracted_result, 'text') and extracted_result.text:
                if isinstance(extracted_result.text, str):
                    raw_text = extracted_result.text
                elif isinstance(extracted_result.text, list):
                    # For Excel files, join the chunks into text
                    raw_text = "\n\n".join([str(chunk.page_content) if hasattr(chunk, 'page_content') else str(chunk) for chunk in extracted_result.text])
                else:
                    raw_text = str(extracted_result.text)
            elif isinstance(extracted_result, dict) and 'text' in extracted_result:
                raw_text = extracted_result['text']
            elif isinstance(extracted_result, str):
                raw_text = extracted_result
            else:
                state.add_warning(f"No text content found for document {document_id}")
                continue
            
            if not raw_text or not raw_text.strip():
                state.add_warning(f"Empty text content for document {document_id}")
                continue
            
            context_chunks = get_context(
                raw_text[:500], 
                "general", 
                limit=3
            )
            
            if context_chunks and isinstance(context_chunks, list):
                context_text = "\n".join([str(chunk) for chunk in context_chunks if chunk])
            else:
                context_text = ""
            
            enhanced_text = raw_text + "\n\nRelevant Context:\n" + context_text
            
            try:
                phraser_chain = create_phraser()
                result = phraser_chain.invoke({"raw_text": enhanced_text})
                
                state.contract_types[document_id] = result.get("classification", {}).get("type", "unknown")
                state.summaries[document_id] = result.get("summary", "")
                
                if document_id not in state.metadata:
                    state.metadata[document_id] = {}
                state.metadata[document_id]["classification"] = result.get("classification", {})
                
            except Exception as e:
                state.add_warning(f"Phraser analysis failed for {document_id}: {str(e)}")
                if "nda" in document_id.lower():
                    state.contract_types[document_id] = "nda"
                elif "msa" in document_id.lower():
                    state.contract_types[document_id] = "msa"
                elif "dpa" in document_id.lower():
                    state.contract_types[document_id] = "dpa"
                elif "company" in document_id.lower():
                    state.contract_types[document_id] = "company_profile"
                elif "historical" in document_id.lower():
                    state.contract_types[document_id] = "historical_data"
                elif "risk" in document_id.lower() or "playbook" in document_id.lower():
                    state.contract_types[document_id] = "playbook"
                else:
                    state.contract_types[document_id] = "other"
                
                state.summaries[document_id] = f"Document analysis failed: {str(e)}"
                
                if document_id not in state.metadata:
                    state.metadata[document_id] = {}
                state.metadata[document_id]["classification"] = {
                    "type": state.contract_types[document_id],
                    "confidence": 0.5,
                    "subtype": "fallback_classification",
                    "key_topics": ["document_analysis_failed"]
                }
        
        state.add_log(f"Phraser analysis completed for {len(state.extracted_content)} documents")
        return state
        
    except Exception as e:
        state.add_error(f"Phraser node failed: {e}")
        return state

def attorney_node(state: State) -> State:
    try:
        state.current_step = "attorney"
        state.add_log("Starting legal analysis with Attorney agent")
        
        if not hasattr(state, 'extracted_content') or not state.extracted_content:
            state.add_warning("No extracted content found for legal analysis")
            return state
        
        for document_id, extracted_result in state.extracted_content.items():
            raw_text = None
            
            if hasattr(extracted_result, 'text') and extracted_result.text:
                if isinstance(extracted_result.text, str):
                    raw_text = extracted_result.text
                elif isinstance(extracted_result.text, list):
                    # For Excel files, join the chunks into text
                    raw_text = "\n\n".join([str(chunk.page_content) if hasattr(chunk, 'page_content') else str(chunk) for chunk in extracted_result.text])
                else:
                    raw_text = str(extracted_result.text)
            elif isinstance(extracted_result, dict) and 'text' in extracted_result:
                raw_text = extracted_result['text']
            elif isinstance(extracted_result, str):
                raw_text = extracted_result
            else:
                state.add_warning(f"No text content found for document {document_id}")
                continue
                
            if not raw_text or not raw_text.strip():
                state.add_warning(f"Empty text content for document {document_id}")
                continue
                
            document_type = state.contract_types.get(document_id, "unknown")
            summary = state.summaries.get(document_id, "")
            
            context_chunks = get_context(
                f"legal analysis {document_type}", 
                document_type, 
                limit=5
            )
            
            if context_chunks and isinstance(context_chunks, list):
                context_text = "\n".join([str(chunk) for chunk in context_chunks if chunk])
            else:
                context_text = ""
            
            enhanced_text = raw_text + "\n\nLegal Context:\n" + context_text
            
            try:
                attorney_chain = create_attorney()
                result = attorney_chain.invoke({
                    "raw_text": enhanced_text,
                    "document_type": document_type,
                    "summary": summary
                })
                
                state.redlines[document_id] = result.get("redlines", [])
                state.risk_assessments[document_id] = result.get("redlines", [])
                
                if document_id not in state.metadata:
                    state.metadata[document_id] = {}
                state.metadata[document_id]["common_grounds"] = result.get("common_grounds", [])
                
            except Exception as e:
                state.add_warning(f"Attorney analysis failed for {document_id}: {str(e)}")
                if document_type in ["nda", "msa", "dpa"]:
                    state.redlines[document_id] = [
                        {
                            "issue": "Standard contract review required",
                            "severity": "medium",
                            "clause": "general",
                            "recommendation": "Review with legal team for company-specific requirements"
                        }
                    ]
                else:
                    state.redlines[document_id] = []
                
                state.risk_assessments[document_id] = state.redlines[document_id]
                
                if document_id not in state.metadata:
                    state.metadata[document_id] = {}
                state.metadata[document_id]["common_grounds"] = [
                    {
                        "area": "Document processing completed",
                        "description": "Document was successfully extracted and processed",
                        "leverage": "Use as baseline for further analysis"
                    }
                ]
        
        state.add_log(f"Attorney analysis completed for {len(state.extracted_content)} documents")
        return state
        
    except Exception as e:
        state.add_error(f"Attorney node failed: {e}")
        return state

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

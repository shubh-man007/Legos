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

load_dotenv()

# Initialize LangSmith client
langsmith_client = Client()

# Initialize LLM and embeddings
llm = ChatAnthropic(
    model="claude-3-5-sonnet-20240620",
    api_key=os.getenv("ANTHROPIC_API_KEY")
)
            
embeddings = PineconeEmbeddings(model="llama-text-embed-v2")

def create_phraser_agent():
    prompt = ChatPromptTemplate.from_template("""
    You are a document analysis expert. Analyze the provided document and return a JSON response with:
    1. A concise summary (max 200 words)
    2. Document classification with confidence score
    
    Document: {raw_text}
    
    Return JSON format:
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

def create_attorney_agent():
    prompt = ChatPromptTemplate.from_template("""
    You are a legal contract analysis expert. Analyze the document and identify:
    1. Potential redlines (issues that need negotiation)
    2. Common grounds for agreement
    
    Document: {raw_text}
    Document Type: {document_type}
    Summary: {summary}
    
    Return JSON format:
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

def retrieve_relevant_context(query: str, document_type: str, limit: int = 5) -> List[str]:
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
        print(f"RAG retrieval failed: {e}")
        return []

def phraser_node(state: State) -> State:
    try:
        state.current_step = "phraser"
        state.add_log("Starting document analysis with Phraser agent")
        
        document_id = list(state.raw_contents.keys())[0] if state.raw_contents else "unknown"
        raw_text = state.raw_contents.get(document_id, "")
        
        if not raw_text:
            state.add_error("No raw content found for analysis")
            return state
        
        context_chunks = retrieve_relevant_context(
            raw_text[:500], 
            "general", 
            limit=3
        )
        
        enhanced_text = raw_text + "\n\nRelevant Context:\n" + "\n".join(context_chunks)
        
        phraser_chain = create_phraser_agent()
        result = phraser_chain.invoke({"raw_text": enhanced_text})
        
        state.contract_types[document_id] = result.get("classification", {}).get("type", "unknown")
        state.summaries[document_id] = result.get("summary", "")
        
        if document_id not in state.metadata:
            state.metadata[document_id] = {}
        state.metadata[document_id]["classification"] = result.get("classification", {})
        
        state.add_log(f"Phraser analysis completed for {document_id}")
        return state
        
    except Exception as e:
        state.add_error(f"Phraser node failed: {e}")
        return state

def attorney_node(state: State) -> State:
    try:
        state.current_step = "attorney"
        state.add_log("Starting legal analysis with Attorney agent")
        
        document_id = list(state.raw_contents.keys())[0] if state.raw_contents else "unknown"
        raw_text = state.raw_contents.get(document_id, "")
        document_type = state.contract_types.get(document_id, "unknown")
        summary = state.summaries.get(document_id, "")
        
        if not raw_text:
            state.add_error("No raw content found for legal analysis")
            return state
        
        context_chunks = retrieve_relevant_context(
            f"legal analysis {document_type}", 
            document_type, 
            limit=5
        )
        
        enhanced_text = raw_text + "\n\nLegal Context:\n" + "\n".join(context_chunks)
        
        attorney_chain = create_attorney_agent()
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
        
        state.add_log(f"Attorney analysis completed for {document_id}")
        return state
        
    except Exception as e:
        state.add_error(f"Attorney node failed: {e}")
        return state

def create_workflow():
    workflow = StateGraph(State)
    
    workflow.add_node("phraser", phraser_node)
    workflow.add_node("attorney", attorney_node)
    
    workflow.set_entry_point("phraser")
    workflow.add_edge("phraser", "attorney")
    workflow.add_edge("attorney", END)
    
    return workflow.compile()

async def execute_workflow(document_id: str, raw_text: str, chunks: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    workflow = create_workflow()
    
    initial_state = State()
    initial_state.raw_contents[document_id] = raw_text
    if chunks:
        initial_state.chunks[document_id] = chunks
    
    try:
        result = await workflow.ainvoke(initial_state)
        
        # Handle both dict and State object returns
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
        print(f"Workflow execution failed: {e}")
        return {
            "error": str(e),
            "document_id": document_id,
            "status": "failed"
        }

async def process_document_from_state(state: State, document_id: str) -> Dict[str, Any]:
    try:
        if document_id not in state.raw_contents:
            return {"error": f"Document {document_id} not found in state"}
        
        workflow = create_workflow()
        result = await workflow.ainvoke(state)
        
        # Handle both dict and State object returns
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

async def analyze_all_documents_in_state(state: State) -> Dict[str, Any]:
    try:
        results = {}
        for document_id in state.raw_contents.keys():
            result = await process_document_from_state(state, document_id)
            results[document_id] = result
        
        return {
            "status": "success",
            "processed_count": len(results),
            "results": results
        }
        
    except Exception as e:
        return {"error": str(e), "status": "failed"}

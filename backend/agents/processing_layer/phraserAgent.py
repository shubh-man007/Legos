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
from utils.utils import get_context

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
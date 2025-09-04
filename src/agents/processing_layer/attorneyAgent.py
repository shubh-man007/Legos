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
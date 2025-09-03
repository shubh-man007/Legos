from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import json
from typing import List, Dict, Any
from dotenv import load_dotenv
from workflow import analyze_document, process_from_state, analyze_all, run_pipeline
from processor import process_file
from agents.state.state import State
import tempfile
import sys
import asyncio

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

load_dotenv()

app = FastAPI(
    title="Legos AI Contract Review API",
    description="AI-powered contract analysis and negotiation assistance",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Legos.ai", "status": "running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "legos-api"}

@app.post("/analyze/document")
async def analyze_document(
    document_id: str,
    raw_text: str,
    chunks: List[Dict[str, Any]] = None
):
    try:
        result = await analyze_document(document_id, raw_text, chunks)
        return {
            "status": "success",
            "document_id": document_id,
            "result": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.post("/analyze/upload")
async def analyze_uploaded_document(
    file: UploadFile = File(...),
    document_id: str = None
):
    try:
        if not document_id:
            document_id = f"upload_{file.filename}_{os.urandom(4).hex()}"
        
        content = await file.read()
        
        if file.content_type == "text/plain":
            raw_text = content.decode("utf-8")
        elif file.content_type == "application/pdf":
            # Basic PDF handling 
            raw_text = f"PDF content from {file.filename} - processing required"
        else:
            raw_text = content.decode("utf-8", errors="ignore")
        
        result = await analyze_document(document_id, raw_text)
        
        return {
            "status": "success",
            "document_id": document_id,
            "filename": file.filename,
            "result": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File analysis failed: {str(e)}")

@app.post("/analyze/gcs")
async def analyze_gcs_document(
    bucket_name: str,
    file_path: str,
    document_id: str = None
):
    try:
        if not document_id:
            document_id = f"gcs_{bucket_name}_{file_path.replace('/', '_')}"
        
        metadata = {"source": "gcs", "bucket": bucket_name, "path": file_path}
        await process_file(bucket_name, file_path, metadata)
        
        return {
            "status": "success",
            "document_id": document_id,
            "message": "GCS document processed successfully",
            "next_step": "Retrieve processed text from state for analysis"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"GCS processing failed: {str(e)}")

@app.post("/pipeline/gcs")
async def execute_gcs_pipeline(
    bucket_name: str,
    folder_path: str
):
    try:
        result = await run_pipeline(bucket_name, folder_path)
        
        if result.get("status") == "success":
            return {
                "status": "success",
                "message": f"Pipeline completed successfully for gs://{bucket_name}/{folder_path}",
                "summary": {
                    "files_processed": result.get("files_processed", 0),
                    "chunks_created": result.get("chunks_created", 0),
                    "documents_analyzed": result.get("documents_analyzed", 0)
                },
                "results": result.get("results", {}),
                "processing_log": result.get("processing_log", []),
                "errors": result.get("errors", []),
                "warnings": result.get("warnings", [])
            }
        else:
            raise HTTPException(status_code=500, detail=f"Pipeline failed: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline execution failed: {str(e)}")

@app.get("/document/{document_id}")
async def get_document_analysis(document_id: str):
    try:
        mock_state = State()
        mock_state.raw_contents[document_id] = "Sample document content for testing"
        
        result = await process_from_state(mock_state, document_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve document: {str(e)}")

@app.post("/batch/analyze")
async def batch_analyze_documents(documents: List[Dict[str, Any]]):
    try:
        results = []
        for doc in documents:
            doc_id = doc.get("document_id", f"batch_{len(results)}")
            raw_text = doc.get("raw_text", "")
            chunks = doc.get("chunks", [])
            
            result = await analyze_document(doc_id, raw_text, chunks)
            results.append({
                "document_id": doc_id,
                "result": result
            })
        
        return {
            "status": "success",
            "processed_count": len(results),
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch analysis failed: {str(e)}")

@app.post("/analyze/state")
async def analyze_documents_in_state(state_data: Dict[str, Any]):
    try:
        state = State()
        
        if "raw_contents" in state_data:
            state.raw_contents = state_data["raw_contents"]
        if "chunks" in state_data:
            state.chunks = state_data["chunks"]
        if "mime_types" in state_data:
            state.mime_types = state_data["mime_types"]
        
        result = await analyze_all(state)
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"State analysis failed: {str(e)}")

# Get a rough idea on the api endpoints
@app.get("/workflow/status")
async def get_workflow_status():
    return {
        "status": "operational",
        "agents": ["file_agent", "detection_agent", "extraction_agent", "phraser", "attorney"],
        "workflow": "file_agent -> detection_agent -> extraction_agent -> phraser -> attorney -> end",
        "features": [
            "gcs_integration",
            "file_type_detection", 
            "document_extraction",
            "legal_aware_chunking",
            "pinecone_vector_storage",
            "document_classification",
            "summarization", 
            "redline_identification",
            "common_grounds_analysis"
        ],
        "state_integration": "enabled",
        "rag_support": "enabled",
        "endpoints": {
            "/pipeline/gcs": "Complete pipeline from GCS folder",
            "/analyze/document": "Single document analysis",
            "/analyze/upload": "File upload analysis",
            "/batch/analyze": "Batch document analysis"
        }
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port) 

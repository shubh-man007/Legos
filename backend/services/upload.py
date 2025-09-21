"""
File upload service for handling file uploads and database storage
"""

import os
import uuid
import tempfile
from typing import Dict, List, Any, Optional
from fastapi import UploadFile, HTTPException
from agents.input_layer.fileUpload import DatabaseManager, FileUploadCreate
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


class UploadService:    
    def __init__(self):
        self.db_manager = DatabaseManager(DATABASE_URL)
    
    async def upload_file(self, 
                         file: UploadFile,
                         company_name: str,
                         deal_name: str,
                         file_tags: List[str] = None,
                         deal_type: str = None,
                         bucket_name: str = None) -> Dict[str, Any]:
        if not bucket_name:
            bucket_name = os.getenv("GCS_BUCKET", "client-context")
        
        if not file_tags:
            file_tags = []
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_file_path = temp_file.name
        
        try:
            result = self.db_manager.upload_file_and_create_record(
                bucket_name=bucket_name,
                local_file_path=temp_file_path,
                file_upload_data=FileUploadCreate(
                    deal_id="",  
                    original_filename=file.filename,
                    file_tags=file_tags,
                    metadata={
                        "content_type": file.content_type,
                        "file_size": len(content),
                        "upload_source": "api"
                    }
                ),
                company_name=company_name,
                deal_name=deal_name,
                deal_type=deal_type
            )
            
            if result["status"] == "success":
                job_id = self.db_manager.create_processing_job(
                    result["file_upload_id"], 
                    "file_upload"
                )
                
                return {
                    "status": "success",
                    "file_upload_id": result["file_upload_id"],
                    "processing_job_id": job_id,
                    "company_id": result["company_id"],
                    "deal_id": result["deal_id"],
                    "gcs_path": result["gcs_path"],
                    "filename": file.filename,
                    "file_size": len(content),
                    "message": "File uploaded successfully and queued for processing"
                }
            else:
                raise HTTPException(status_code=500, detail=result["message"])
                
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
        
        finally:
            # Clean up temporary file
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
    
    def get_upload_status(self, file_upload_id: str) -> Optional[Dict[str, Any]]:
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT 
                            fu.*,
                            pj.status as processing_status,
                            pj.started_at,
                            pj.completed_at,
                            pj.error_message,
                            c.name as company_name,
                            d.deal_name
                        FROM file_uploads fu
                        LEFT JOIN processing_jobs pj ON fu.id = pj.file_upload_id
                        LEFT JOIN deals d ON fu.deal_id = d.id
                        LEFT JOIN companies c ON d.company_id = c.id
                        WHERE fu.id = %s
                    """, (file_upload_id,))
                    
                    result = cursor.fetchone()
                    if not result:
                        return None
                    
                    return {
                        "file_upload_id": result['id'],
                        "filename": result['original_filename'],
                        "gcs_path": result['gcs_path'],
                        "file_size": result['file_size'],
                        "upload_status": result['upload_status'],
                        "processing_status": result['processing_status'],
                        "company_name": result['company_name'],
                        "deal_name": result['deal_name'],
                        "uploaded_at": result['created_at'].isoformat(),
                        "processing_started_at": result['started_at'].isoformat() if result['started_at'] else None,
                        "processing_completed_at": result['completed_at'].isoformat() if result['completed_at'] else None,
                        "error_message": result['error_message']
                    }
                    
        except Exception as e:
            raise Exception(f"Failed to get upload status: {str(e)}")
    
    def list_uploads(self, 
                    company_name: str = None, 
                    deal_name: str = None,
                    limit: int = 50,
                    offset: int = 0) -> Dict[str, Any]:
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
                    where_conditions = []
                    params = []
                    
                    if company_name:
                        where_conditions.append("c.name ILIKE %s")
                        params.append(f"%{company_name}%")
                    
                    if deal_name:
                        where_conditions.append("d.deal_name ILIKE %s")
                        params.append(f"%{deal_name}%")
                    
                    where_clause = ""
                    if where_conditions:
                        where_clause = "WHERE " + " AND ".join(where_conditions)
                    
                    count_query = f"""
                        SELECT COUNT(*)
                        FROM file_uploads fu
                        LEFT JOIN deals d ON fu.deal_id = d.id
                        LEFT JOIN companies c ON d.company_id = c.id
                        {where_clause}
                    """
                    cursor.execute(count_query, params)
                    total_count = cursor.fetchone()['count']
                    
                    query = f"""
                        SELECT 
                            fu.id,
                            fu.original_filename,
                            fu.gcs_path,
                            fu.file_size,
                            fu.upload_status,
                            fu.created_at,
                            c.name as company_name,
                            d.deal_name
                        FROM file_uploads fu
                        LEFT JOIN deals d ON fu.deal_id = d.id
                        LEFT JOIN companies c ON d.company_id = c.id
                        {where_clause}
                        ORDER BY fu.created_at DESC
                        LIMIT %s OFFSET %s
                    """
                    cursor.execute(query, params + [limit, offset])
                    uploads = [dict(row) for row in cursor.fetchall()]
                    
                    return {
                        "uploads": uploads,
                        "total_count": total_count,
                        "limit": limit,
                        "offset": offset
                    }
                    
        except Exception as e:
            raise Exception(f"Failed to list uploads: {str(e)}")

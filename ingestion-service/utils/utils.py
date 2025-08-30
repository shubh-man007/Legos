import os
import hashlib
import mimetypes
import tempfile
import time
from google.cloud import storage
from google.cloud.exceptions import NotFound, GoogleCloudError
from docx import Document

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone, ServerlessSpec
from dotenv import load_dotenv

load_dotenv()

PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_DIMENSION = 1024
PINECONE_METRIC = "cosine"
PINECONE_CLOUD = "aws"
PINECONE_REGION = "us-east-1"

try:
    pc = Pinecone(api_key=PINECONE_API_KEY)
    if not pc.has_index(PINECONE_INDEX_NAME):
        pc.create_index(
            name=PINECONE_INDEX_NAME,
            dimension=PINECONE_DIMENSION,
            metric=PINECONE_METRIC,
            spec=ServerlessSpec(cloud=PINECONE_CLOUD, region=PINECONE_REGION),
        )
    pinecone_index = pc.Index(PINECONE_INDEX_NAME)
    embeddings_model = HuggingFaceEmbeddings(model_name="BAAI/bge-large-en-v1.5")
except KeyError as e:
    print(f"Warning: Pinecone not configured: {e}")
    pinecone_index = None
    embeddings_model = None


def download_file(bucket_name: str, file_name: str, max_retries: int = 3) -> tuple[str, float]:
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(file_name)
    
    temp_file = tempfile.NamedTemporaryFile(
        delete=False, 
        suffix=os.path.splitext(file_name)[1]
    )
    local_path = temp_file.name
    temp_file.close()
    
    start_time = time.time()
    
    for attempt in range(max_retries):
        try:
            blob.download_to_filename(local_path)
            download_time = time.time() - start_time
            return local_path, download_time
            
        except (NotFound, GoogleCloudError) as e:
            if attempt == max_retries - 1:
                raise e
            time.sleep(2 ** attempt)
    
    raise RuntimeError(f"Failed to download after {max_retries} attempts")


def download_folder(bucket_name: str, folder_path: str) -> dict[str, str]:
    temp_dir = tempfile.mkdtemp(prefix=f"gcs_{folder_path.replace('/', '_')}")
    
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    
    if not folder_path.endswith('/'):
        folder_path += '/'
    
    blobs = list(bucket.list_blobs(prefix=folder_path))
    
    if not blobs:
        raise NotFound(f"No files found in folder: gs://{bucket_name}/{folder_path}")
    
    downloaded_files = {}
    
    for blob in blobs:
        if blob.name.endswith('/'):
            continue
            
        try:
            relative_path = blob.name[len(folder_path):]
            local_file_path = os.path.join(temp_dir, relative_path)
            
            os.makedirs(os.path.dirname(local_file_path), exist_ok=True)
            blob.download_to_filename(local_file_path)
            downloaded_files[relative_path] = local_file_path
            
        except Exception as e:
            print(f"Failed to download {blob.name}: {e}")
            continue
    
    return downloaded_files


def hash_file(file_path: str, algorithm: str = 'sha256') -> str:
    hash_obj = hashlib.new(algorithm)
    
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_obj.update(chunk)
    
    return hash_obj.hexdigest()


def get_mime(file_path: str) -> str:
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type or "application/octet-stream"


def detect_type(file_path: str, mime_type: str) -> str:    
    if mime_type == "application/pdf":
        return "pdf"
    elif mime_type in [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword"
    ]:
        return "word"
    elif mime_type in [
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel"
    ]:
        return "excel"
    elif mime_type.startswith("text/"):
        return "text"
    elif mime_type.startswith("image/"):
        return "image"
    else:
        return "unknown"


def cleanup_file(file_path: str):
    try:
        if os.path.exists(file_path):
            os.unlink(file_path)
    except Exception:
        pass


def cleanup_folder(folder_path: str):
    import shutil
    try:
        if os.path.exists(folder_path):
            shutil.rmtree(folder_path)
    except Exception:
        pass  


def extract_docx(file_path: str) -> tuple[str, int]:
    document = Document(file_path)
    full_text = []
    for paragraph in document.paragraphs:
        full_text.append(paragraph.text)
    return "\n".join(full_text), 1


def extract_text(file_path) -> tuple[str, int]:
    try:
        with open(file_path, "r", encoding="utf-8", errors="strict") as f:
            return f.read(), 1
    except UnicodeDecodeError:
        with open(file_path, "rb") as f:
            data = f.read()
            return data.decode("utf-8", errors="replace"), 1
        

async def upsert_to_pinecone(chunked_documents: dict, metadata: dict = None):
    if not pinecone_index or not embeddings_model:
        print("Warning: Pinecone not configured, skipping vector storage")
        return
    
    if not metadata:
        metadata = {}
    
    all_documents = []
    
    for filename, docs in chunked_documents.items():
        if not docs:
            continue
            
        for doc in docs:
            doc.metadata.update({
                **metadata,
                "source": filename,
                "extraction_timestamp": os.getenv("EXTRACTION_TIMESTAMP", "unknown")
            })
            all_documents.append(doc)
    
    if all_documents:
        try:
            print(f"Upserting {len(all_documents)} documents to Pinecone index '{PINECONE_INDEX_NAME}'...")
            vectorstore = PineconeVectorStore(index=pinecone_index, embedding=embeddings_model)
            vectorstore.add_documents(all_documents)
            print("Vector storage complete!")
            return len(all_documents)
        except Exception as e:
            print(f"Error upserting to Pinecone: {e}")
            return 0
    return 0

# from google.cloud import vision 
# vision.ImageAnnotatorClient()


# from PIL import Image, ImageFilter, ImageOps
# import pytesseract

# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# print(pytesseract.image_to_string(Image.open('image.png')))


# from dotenv import load_dotenv
# import os
# from google.api_core.client_options import ClientOptions
# from google.cloud import documentai_v1
# import json

# load_dotenv()

# GOOGLE_APPLICATION_CREDENTIALS = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
# location = os.getenv("LOCATION")
# project_id = os.getenv("PROJECT_ID")
# processor_id = os.getenv("PROCESSOR_ID")

# file_path = "methodology.pdf"

# opts = ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")
# client = documentai_v1.DocumentProcessorServiceClient(client_options=opts)

# full_processor_name = client.processor_path(project_id, location, processor_id)

# request = documentai_v1.GetProcessorRequest(name=full_processor_name)
# processor = client.get_processor(request=request)
# print(f"Processor Name: {processor.name}")

# with open(file_path, "rb") as f:
#     image_content = f.read()

# raw_document = documentai_v1.RawDocument(
#     content=image_content,
#     mime_type="application/pdf",
# )

# request = documentai_v1.ProcessRequest(name=processor.name, raw_document=raw_document)
# result = client.process_document(request=request)
# document = result.document

# doc_json = documentai_v1.Document.to_json(document, including_default_value_fields=False, preserving_proto_field_name=False)
# doc_json = json.loads(doc_json)

# with open("test.json", "w", encoding="utf-8") as fp:
#     json.dump(doc_json, fp, indent=2, ensure_ascii=False)

# print("Done")


from pinecone.grpc import PineconeGRPC as Pinecone
from dotenv import load_dotenv
import os

load_dotenv()

PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")

pc = Pinecone(api_key=PINECONE_API_KEY)

index = pc.Index(PINECONE_INDEX_NAME)

for namespace in index.list_namespaces():
    print(namespace)


for ids in index.list(namespace='__default__'):
    print(ids)

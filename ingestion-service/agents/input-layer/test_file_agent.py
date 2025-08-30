import os
import sys
import json
from dotenv import load_dotenv

load_dotenv()

sys.path.append(os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..")))

from agents.state.state import State
from fileAgent import file_agent
from utils.utils import download_folder, hash_file, get_mime, detect_type, cleanup_folder


def main():
    bucket = os.environ.get("GCS_BUCKET")
    folder = os.environ.get("GCS_FOLDER")
    if not bucket or not folder:
        print("Set TEST_BUCKET and TEST_FOLDER env vars")
        return

    state = State(bucket_name=bucket, folder_path=folder)
    state = file_agent(state)

    if state.errors:
        print("Errors:", state.errors)
    if state.warnings:
        print("Warnings:", state.warnings)

    print("Downloaded:", len(state.downloaded_files))
    file_attr = []
    for name, path in list(state.downloaded_files.items()):
        h = hash_file(path)
        m = get_mime(path)
        t = detect_type(path, m)
        sz = state.file_sizes.get(name, 0)
        file_attr.append({"hash" : h, "mime" : m, "type" : t, "size" : sz})
    
    with open("test.json", "w") as f:
        json.dump(file_attr, f, indent = 2)

    if state.local_folder_path and os.path.exists(state.local_folder_path):
        cleanup_folder(state.local_folder_path)
        print("Cleaned")


if __name__ == "__main__":
    main()

import os
import time
from agents.state.state import State
from utils.utils import download_folder, hash_file, get_mime, detect_type

def file_agent(state: State) -> State:
    state.current_step = "file_agent"
    state.add_log(f"---Starting folder processing for gs://{state.bucket_name}/{state.folder_path}---")
    
    try:
        downloaded_files = download_folder(
            bucket_name=state.bucket_name,
            folder_path=state.folder_path
        )
        
        if not downloaded_files:
            state.add_error(f"No files found in folder: gs://{state.bucket_name}/{state.folder_path}")
            return state
        
        state.downloaded_files = downloaded_files
        state.local_folder_path = os.path.dirname(list(downloaded_files.values())[0])
        state.add_log(f"Downloaded {len(downloaded_files)} files to temporary directory")
        
        for file_name, local_path in downloaded_files.items():
            try:
                file_hash = hash_file(local_path)
                state.file_hashes[file_name] = file_hash
                
                file_size = os.path.getsize(local_path)
                state.file_sizes[file_name] = file_size
                
                mime_type = get_mime(local_path)
                state.mime_types[file_name] = mime_type
                
                detected_type = detect_type(local_path, mime_type)
                state.detected_types[file_name] = detected_type
                
                if file_size > 100 * 1024 * 1024:  # 100MB limit
                    state.add_warning(f"File {file_name} too large: {file_size} bytes")
                
                if detected_type == "unknown":
                    state.add_warning(f"Unknown file type for {file_name}: {mime_type}")
                
                state.add_log(f"Processed {file_name}: {detected_type}, {file_size} bytes")
                
            except Exception as e:
                state.add_error(f"Failed to process {file_name}: {str(e)}")
                continue
        
        state.add_log(f"File agent completed successfully. Processed {len(downloaded_files)} files.")
        
    except Exception as e:
        state.add_error(f"File agent failed: {str(e)}")
    
    return state


def file_node(state: State) -> State:
    try:
        return file_agent(state)
    except Exception as e:
        state.add_error(f"File agent failed: {e}")
        return state
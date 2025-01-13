import os
import shutil
from pathlib import Path, WindowsPath
import zipfile

def move_md_files_from_zip(zip_path: str, target_dir: str) -> None:
    """
    Extract and move .md files from a zip file to target_dir.
    Files are processed one at a time to minimize memory usage.
    Skips files that already exist in the target directory.
    """
    target_path = WindowsPath(target_dir)
    target_path.mkdir(parents=True, exist_ok=True)
    moved_count = 0
    skipped_count = 0
    
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        for file_info in zip_ref.infolist():
            if file_info.filename.lower().endswith('.md'):
                if '/content/' in file_info.filename:
                    rel_path = file_info.filename.split('/content/')[1]
                else:
                    rel_path = file_info.filename
                
                new_name = rel_path.replace('/', '_')
                # Handle long paths by using the extended path prefix
                target_file = WindowsPath('\\\\?\\' + str(target_path.absolute() / new_name))
                
                # Skip if file already exists
                if target_file.exists():
                    skipped_count += 1
                    continue
                
                try:
                    # Create parent directory if it doesn't exist
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Extract and move the file
                    with zip_ref.open(file_info) as source, open(str(target_file), 'wb') as target:
                        shutil.copyfileobj(source, target)
                    moved_count += 1
                except Exception as e:
                    # Log error for debugging but continue silently
                    with open('move_docs_errors.log', 'a') as log:
                        log.write(f"Error with {file_info.filename}: {str(e)}\n")
                    continue

if __name__ == "__main__":
    zip_path = r"C:\Users\AlexGoldsmith\Downloads\docs-main.zip"
    target = r"C:\Users\AlexGoldsmith\Documents\Software\Railway\v7_go\docs\github\docs2"
    move_md_files_from_zip(zip_path, target) 
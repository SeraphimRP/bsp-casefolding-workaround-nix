import os
import sys
import time
import shutil
import logging
import pyinotify
import signal
import asyncio
from typing import List, Set
from pathlib import Path

TMP_DIR = '/tmp/bsp-casefolding-workaround'
HISTORY_FILE = 'extracted_maps.txt'
VPKEDITCLI_PATH = None 

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('BSPProcessor')

# Global flag for graceful shutdown
running = True


def signal_handler(sig, frame):
    """Handle termination signals for graceful shutdown"""
    global running
    loop = asyncio.get_event_loop()
    logger.info("Received termination signal. Shutting down...")
    running = False
    sys.exit(0)
    


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


class BSPEventHandler(pyinotify.ProcessEvent):
    """Event handler for BSP file events"""

    def __init__(self, download_dirs: List[str]):
        self.paths = download_dirs
        self.pending_files = {}

    def process_IN_CLOSE_WRITE(self, event):
        """Process event when a file is closed after writing"""
        if event.pathname.lower().endswith('.bsp'):
            logger.info(f"New BSP file detected: {event.pathname}")
            self.pending_files[event.pathname] = time.time()

    def process_IN_MOVED_TO(self, event):
        """Process event when a file is moved into the watched directory"""
        if event.pathname.lower().endswith('.bsp'):
            logger.info(f"BSP file moved: {event.pathname}")
            self.pending_files[event.pathname] = time.time()


    async def process_pending_files(self):
        """Process files"""
        files = []
        if len(self.pending_files) > 0:
            files = list(self.pending_files.keys())
            await process_bsp(files, self.paths)

        # Remove processed files from pending list
        for file_path in files:
            del self.pending_files[file_path]


async def find_bsp_files(source_path: str) -> List[str]:
    """
    Recursively find all BSP files in the given directory.

    Args:
        source_path: Directory to search for BSP files

    Returns:
        List of absolute paths to BSP files
    """
    bsp_files = []

    try:
        # Walk through the directory tree
        for root, _, files in os.walk(source_path):
            # Filter for BSP files
            for file in files:
                if file.lower().endswith('.bsp'):
                    bsp_path = os.path.join(root, file)
                    bsp_files.append(os.path.abspath(bsp_path))

        logger.info(f"Found {len(bsp_files)} BSP files in {source_path}")
    except Exception as e:
        logger.info(f"Error scanning for BSP files in {source_path}: {e}")

    # Sort files for consistent processing order
    return sorted(bsp_files)


async def process_bsp(bsp_files: List[str], data_paths: List[str]) -> None:
    """
    Process BSP files by extracting them and moving all resulting directories to steampath.
    Tracks processed files in a history file to avoid reprocessing.

    Args:
        bsp_files: List of BSP file paths to process
        data_path: Path where BSP contents will be extracted
    """
    # Load history of processed BSP files
    processed_history: Set[str] = set()

    for data_path in data_paths:
        history_file = os.path.join(Path(data_path).parent, HISTORY_FILE)

        if os.path.exists(history_file):
            try:
                with open(history_file, 'r') as f:
                    processed_history.update(set(line.strip() for line in f if line.strip()))
            except Exception as e:
                logger.info(f"Warning: Could not read history file: {e}")

    # Filter out already processed files
    files_to_process = []
    for bsp in bsp_files:
        bsp_name = bsp
        if bsp_name in processed_history:
            logger.info(f"Already processed file: {bsp}")
        else:
            files_to_process.append(bsp)

    if not files_to_process:
        logger.info("No new BSP files to process.")
        return
    
    # Track newly processed files
    newly_processed = set()

    bsp_processed = 0
    bsp_total = len(files_to_process)

    for bsp in files_to_process:
        # Update cursor animation
        bsp_name = os.path.basename(bsp)

        bsp_processed += 1

        # Progress message
        logger.info(f"Processing map {bsp_processed} of {bsp_total} ({(bsp_processed * 100 // bsp_total)}%), path: {bsp}")

        # Extract BSP contents using vpkeditcli
        try:
            result = await asyncio.create_subprocess_shell(f"{VPKEDITCLI_PATH} --output {TMP_DIR} --extract / {bsp.replace(" ", "\ ")}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await result.communicate()
            
            if result.returncode != 0:
                logger.info(f"\nWarning: Failed to extract '{bsp_name}', skipping.")
                time.sleep(1)
                continue
        except Exception as e:
            logger.info(f"\nWarning: Failed to extract '{bsp_name}': {e}, skipping.")
            time.sleep(1)
            continue

        # Setup base path for extracted content
        bsp_base_name = os.path.splitext(bsp_name)[0]
        data_path = Path(bsp).parent.parent
        bsp_extract_dir = os.path.join(TMP_DIR, bsp_base_name)

        # Get all directories in the extracted folder
        if os.path.isdir(bsp_extract_dir):
            # List all items in the extracted directory
            for item in os.listdir(bsp_extract_dir):
                src_dir = os.path.join(bsp_extract_dir, item)

                # Only process directories
                if os.path.isdir(src_dir):
                    dst_dir = os.path.join(data_path, item)

                    # Create destination directory if it doesn't exist
                    try:
                        os.makedirs(dst_dir, exist_ok=True)
                    except OSError as e:
                        logger.info(f"\nWarning: Failed to extract '{bsp_name}': {e}, skipping.")
                        time.sleep(1)
                        continue

                    # Move all files from source to destination
                    for root, dirs, files in os.walk(src_dir):
                        # Get the relative path from src_dir
                        rel_path = os.path.relpath(root, src_dir)

                        # Create corresponding directory in destination
                        if rel_path != '.':
                            os.makedirs(os.path.join(dst_dir, rel_path), exist_ok=True)

                        # Move each file
                        for file in files:
                            src_file = os.path.join(root, file)
                            if rel_path == '.':
                                dst_file = os.path.join(dst_dir, file)
                            else:
                                dst_file = os.path.join(dst_dir, rel_path, file)

                            # Move the file, overwriting if it exists
                            if os.path.exists(dst_file):
                                os.remove(dst_file)
                            shutil.move(src_file, dst_file)

            shutil.rmtree(bsp_extract_dir)

            # Mark as successfully processed
            newly_processed.add(bsp)

        sys.stdout.flush()

    # Update history file with newly processed files
    if newly_processed:
        try:
            for data_path in data_paths:
                count = 0

                # Write to a temporary file first to ensure atomic update
                temp_history_file = f"{history_file}.tmp"
                with open(temp_history_file, 'w') as f:
                    for bsp_path in sorted(processed_history.union(newly_processed)):
                        if Path(data_path).parent == Path(bsp_path).parent.parent:
                            f.write(f"{bsp_path}\n")
                            count += 1

                if count != 0:
                    # Replace the original file with the updated one
                    shutil.move(temp_history_file, os.path.join(Path(data_path).parent, HISTORY_FILE))
                    logger.info(f"Updated {os.path.join(Path(data_path).parent, HISTORY_FILE)} with {count} newly processed BSP files.")
        except Exception as e:
            logger.info(f"Warning: Failed to update history file: {e}")


async def watch_directory(download_dirs: List[str]):
    source_paths = [os.path.join(download_dir, 'maps') for download_dir in download_dirs]
    initial_source_paths = source_paths
    existing_files = None

    # Process existing files first
    for source_path in source_paths:
        tmp_existing_files = await find_bsp_files(source_path)

        if not tmp_existing_files:
            initial_source_paths.remove(source_path)
        else:
            if existing_files is None:
                existing_files = tmp_existing_files
            else:
                existing_files += tmp_existing_files
        
    await process_bsp(existing_files, initial_source_paths)

    # Set up the watch manager
    wm = pyinotify.WatchManager()
    handler = BSPEventHandler(source_paths)

    # Set up the notifier
    notifier = pyinotify.Notifier(wm, handler)

    # Add watches for the source directory and all subdirectories
    mask = pyinotify.IN_CLOSE_WRITE | pyinotify.IN_MOVED_TO | pyinotify.IN_CREATE

    # Recursively add watches to all subdirectories
    for source_path in source_paths:
        wm.add_watch(source_path, mask)
        logger.info(f"Watching directory: {source_path}")
    logger.info("Press Ctrl+C to stop")

    # Main loop
    try:
        while running:
            # Process events for up to 1 second
            if notifier.check_events(timeout=1000):
                notifier.read_events()
                notifier.process_events()

            # Process any pending files
            await handler.process_pending_files()
    except Exception as e:
        logger.error(f"Error in watch loop: {e}")
    finally:
        # Clean up
        notifier.stop()
        logger.info("Watcher stopped")

def main():
    if not os.path.isdir(TMP_DIR):
        os.makedirs(TMP_DIR)
    
    which_result = shutil.which("vpkeditcli")
    if which_result is None:
        logger.error("cannot find vpkeditcli, exiting...");
        sys.exit(1);
    
    global VPKEDITCLI_PATH
    VPKEDITCLI_PATH = which_result

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    watching_directories = []
    try:
        for arg in sys.argv:
            if "bin/bsp-casefolding-workaround" not in arg and arg not in ["python", "__init__.py"]:
                watching_directories.append(arg)
        asyncio.ensure_future(watch_directory(watching_directories))
        loop.run_forever()
    except Exception as e:
        logger.error(f"received exception: {e}")
    finally:
        loop.close()

if __name__ == "__main__":
    main()
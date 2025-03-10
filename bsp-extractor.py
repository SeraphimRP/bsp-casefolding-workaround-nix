#!/usr/bin/python

import os
import sys
import time
import shutil
import logging
import subprocess
import pyinotify
import signal
from typing import List, Set

TMP_DIR = '/tmp/bsp'
HISTORY_FILE = 'extracted_maps.txt'

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bsp_processor.log')
    ]
)
logger = logging.getLogger('BSPProcessor')

# Global flag for graceful shutdown
running = True


def signal_handler(sig, frame):
    """Handle termination signals for graceful shutdown"""
    global running
    logger.info("Received termination signal. Shutting down...")
    running = False


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


class BSPEventHandler(pyinotify.ProcessEvent):
    """Event handler for BSP file events"""

    def __init__(self, download_dir: str):
        self.path = download_dir
        self.pending_files = {}

    def process_IN_CLOSE_WRITE(self, event):
        """Process event when a file is closed after writing"""
        if event.pathname.lower().endswith('.bsp'):
            logger.info(f"New BSP file detected: {event.name}")
            self.pending_files[event.pathname] = time.time()

    def process_IN_MOVED_TO(self, event):
        """Process event when a file is moved into the watched directory"""
        if event.pathname.lower().endswith('.bsp'):
            logger.info(f"BSP file moved: {event.name}")
            self.pending_files[event.pathname] = time.time()


    def process_pending_files(self):
        """Process files"""
        files = []
        if len(self.pending_files) > 0:
            files = list(self.pending_files.keys())
            process_bsp(files, self.path)

        # Remove processed files from pending list
        for file_path in files:
            del self.pending_files[file_path]


def find_bsp_files(source_path: str) -> List[str]:
    """
    Recursively find all BSP files in the given directory.

    Args:
        source_path: Directory to search for BSP files

    Returns:
        List of absolute paths to BSP files
    """
    bsp_files = []

    logger.info(f"Scanning for BSP files in: {source_path}")

    try:
        # Walk through the directory tree
        for root, _, files in os.walk(source_path):
            # Filter for BSP files
            for file in files:
                if file.lower().endswith('.bsp'):
                    bsp_path = os.path.join(root, file)
                    bsp_files.append(os.path.abspath(bsp_path))

        logger.info(f"Found {len(bsp_files)} BSP files")
    except Exception as e:
        logger.info(f"Error scanning for BSP files: {e}")

    # Sort files for consistent processing order
    return sorted(bsp_files)


def process_bsp(bsp_files: List[str], data_path: str) -> None:
    """
    Process BSP files by extracting them and moving all resulting directories to steampath.
    Tracks processed files in a history file to avoid reprocessing.

    Args:
        bsp_files: List of BSP file paths to process
        data_path: Path where BSP contents will be extracted
    """
    # Load history of processed BSP files

    history_file = os.path.join(data_path, HISTORY_FILE)

    processed_history: Set[str] = set()
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r') as f:
                processed_history = set(line.strip() for line in f if line.strip())
        except Exception as e:
            logger.info(f"Warning: Could not read history file: {e}")

    # Filter out already processed files
    files_to_process = []
    for bsp in bsp_files:
        bsp_name = os.path.basename(bsp)
        if bsp_name in processed_history:
            logger.info(f"Already processed file: {os.path.basename(bsp)}")
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
        logger.info(f"Processing Maps {bsp_processed}/{bsp_total} {(bsp_processed * 100 // bsp_total)}% {os.path.splitext(bsp_name)[0]}")

        # Extract BSP contents using vpkeditcli
        try:
            result = subprocess.run(
                ["vpkeditcli", "--output", TMP_DIR, "--extract", "/", bsp],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
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
                    os.makedirs(dst_dir, exist_ok=True)

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
            newly_processed.add(bsp_name)

        time.sleep(0.25)
        sys.stdout.flush()

    # Update history file with newly processed files
    if newly_processed:
        try:
            # Write to a temporary file first to ensure atomic update
            temp_history_file = f"{history_file}.tmp"
            with open(temp_history_file, 'w') as f:
                for bsp_path in sorted(processed_history.union(newly_processed)):
                    f.write(f"{bsp_path}\n")

            # Replace the original file with the updated one
            shutil.move(temp_history_file, history_file)
            logger.info(f"Updated history file with {len(newly_processed)} newly processed BSP files.")
        except Exception as e:
            logger.info(f"Warning: Failed to update history file: {e}")


def watch_directory(download_dir: str):
    source_path = os.path.join(download_dir, 'maps')

    # Process existing files first
    existing_files = find_bsp_files(source_path)
    if existing_files:
        process_bsp(existing_files, download_dir)

    # Set up the watch manager
    wm = pyinotify.WatchManager()
    handler = BSPEventHandler(download_dir)

    # Set up the notifier
    notifier = pyinotify.Notifier(wm, handler)

    # Add watches for the source directory and all subdirectories
    mask = pyinotify.IN_CLOSE_WRITE | pyinotify.IN_MOVED_TO | pyinotify.IN_CREATE

    # Recursively add watches to all subdirectories
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
            handler.process_pending_files()

    except Exception as e:
        logger.error(f"Error in watch loop: {e}")
    finally:
        # Clean up
        notifier.stop()
        logger.info("Watcher stopped")


if __name__ == "__main__":
    if not os.path.isdir(TMP_DIR):
        os.makedirs(TMP_DIR)

    watch_directory(sys.argv[1])

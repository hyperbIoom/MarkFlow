#!/usr/bin/env python3
"""
App launcher script that manages server instances and file opening.
Handles server.lock file checking and delegates to appropriate components.
"""

import sys
import os
import subprocess
import time
from pathlib import Path
from filelock import FileLock, Timeout


def get_file_path_from_args():
    """Extract file path from command line arguments if provided."""
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        if file_path.endswith('.md') and os.path.exists(file_path):
            return os.path.abspath(file_path)
        else:
            print(f"Error: File '{file_path}' does not exist or is not a .md file")
            sys.exit(1)
    return None


def is_server_running(working_directory):
    """Check if server is running by attempting to acquire the server lock."""
    lock_file_path = os.path.join(working_directory, 'server.lock')
    lock = FileLock(lock_file_path)
    
    try:
        # Try to acquire the lock with a very short timeout
        with lock.acquire(timeout=0.1):
            # If we can acquire the lock, no server is running
            return False
    except Timeout:
        # Lock is held by another process (server is running)
        return True
    except Exception as e:
        print(f"Error checking server status: {e}")
        return False


def get_server_url_from_lock(lock_file_path):
    """Read the server URL from the first line of the lock file."""
    try:
        with open(lock_file_path, 'r') as f:
            url = f.readline().strip()
            return url if url else None
    except (FileNotFoundError, IOError):
        return None


def write_opening_file(file_path, directory):
    """Write the file path to opening.txt in the specified directory."""
    opening_file = os.path.join(directory, 'opening.txt')
    opening_lock = FileLock(f"{opening_file}.lock")
    
    try:
        print("Waiting for opening.txt to be available...")
        # Wait up to 10 seconds for the lock to be released
        with opening_lock.acquire(timeout=10):
            print("Acquired lock for opening.txt")
            # Append to the file instead of overwriting (in case multiple files are being opened)
            with open(opening_file, 'a') as f:
                f.write(file_path + '\n')
            print(f"File path written to {opening_file}")
    except Timeout:
        print("Timeout waiting for opening.txt lock. The server might be busy.")
        sys.exit(1)
    except Exception as e:
        print(f"Error writing to opening.txt: {e}")
        sys.exit(1)


def run_webapp(server_url, app_directory):
    """Launch webapp.py with the server URL."""
    try:
        print(f"Launching webapp with server URL: {server_url}")
        webapp_path = os.path.join(app_directory, 'webapp.py')
        subprocess.run([sys.executable, webapp_path, server_url], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running webapp.py: {e}")
        sys.exit(1)
    except FileNotFoundError:
        print("Error: webapp.py not found")
        sys.exit(1)


def run_server(file_path=None, app_directory=None):
    """Launch server.py to start the server."""
    try:
        print("Starting server...")
        server_path = os.path.join(app_directory, 'server.py')
        cmd = [sys.executable, server_path]
        if file_path:
            cmd.append(file_path)
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running server.py: {e}")
        sys.exit(1)
    except FileNotFoundError:
        print("Error: server.py not found")
        sys.exit(1)


def wait_for_server_start(working_directory, max_wait_time=10):
    """Wait for the server to start and create the server.lock file."""
    lock_file_path = os.path.join(working_directory, 'server.lock')
    
    print("Waiting for server to start...")
    start_time = time.time()
    
    while time.time() - start_time < max_wait_time:
        if os.path.exists(lock_file_path):
            # Give it a moment to write the URL
            time.sleep(1)
            url = get_server_url_from_lock(lock_file_path)
            if url:
                print(f"Server started successfully at {url}")
                return url
        time.sleep(0.5)
    
    print("Timeout waiting for server to start")
    return None


def main():
    # Get the application directory (where app.py is located)
    app_directory = os.path.dirname(os.path.abspath(__file__))
    
    # Get file path from command line arguments
    input_file_path = get_file_path_from_args()
    
    # Determine the working directory for server operations
    # Always use the app directory for server operations, regardless of input file location
    working_directory = app_directory
    
    print(f"App directory: {app_directory}")
    print(f"Working directory: {working_directory}")
    if input_file_path:
        print(f"Input file: {input_file_path}")
    
    # Check if server is already running
    if is_server_running(working_directory):
        print("Server is already running...")
        
        # If a file path was provided, write it to opening.txt and exit
        if input_file_path:
            print(f"Writing file path to opening.txt: {input_file_path}")
            write_opening_file(input_file_path, working_directory)
            print("File path written. The running server should open the file automatically.")
            sys.exit(0)
        else:
            # No file provided, get server URL and launch webapp
            lock_file_path = os.path.join(working_directory, 'server.lock')
            server_url = get_server_url_from_lock(lock_file_path)
            
            if not server_url:
                print("Error: Could not read server URL from lock file")
                sys.exit(1)
            
            run_webapp(server_url, app_directory)
    else:
        # No server running, start new server
        print("No server running, starting new server...")
        
        # Change to working directory for server operations
        original_cwd = os.getcwd()
        os.chdir(working_directory)
        
        try:
            # Start server in background if we have a file to open
            if input_file_path:
                # Start server as background process
                try:
                    server_path = os.path.join(app_directory, 'server.py')
                    cmd = [sys.executable, server_path, input_file_path]
                    subprocess.Popen(cmd, cwd=working_directory)
                    
                    # Wait for server to start
                    server_url = wait_for_server_start(working_directory)
                    if server_url:
                        print(f"Server started successfully. File should open automatically.")
                    else:
                        print("Failed to start server or get server URL")
                        sys.exit(1)
                        
                except Exception as e:
                    print(f"Error starting server: {e}")
                    sys.exit(1)
            else:
                # No file provided, run server normally (blocking)
                run_server(None, app_directory)
        finally:
            # Restore original working directory
            os.chdir(original_cwd)


if __name__ == "__main__":
    main()
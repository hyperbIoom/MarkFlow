#!/usr/bin/env python3
"""
MarkFlow Backend Server
A Flask + pywebview application for markdown editing
"""

import os
import sys
import argparse
import json
import threading
import time
import yaml
import random
import socket
from pathlib import Path
from urllib.parse import quote, unquote, urlparse
import subprocess
from flask import Flask, request, jsonify, send_from_directory, Response, stream_template
import webview
from filelock import FileLock

class MarkFlowServer:
    def __init__(self):
        self.app = Flask(__name__)
        self.app_dir = Path(__file__).parent / 'app'
        self.current_file = None
        self.current_content = ""
        self.clients = []  # For server-sent events
        self.opening_file = Path(__file__).parent / 'opening.txt'
        self.opening_lock = FileLock(str(self.opening_file) + '.lock')
        self.server_lock = FileLock(str(Path(__file__).parent / 'server.lock'))
        self.monitoring_active = True
        self.pending_files = []  # Queue for files to be opened
        self.server_port = None
        self.event_clients = []  # Track SSE clients
        
        # Ensure app directory exists
        self.app_dir.mkdir(exist_ok=True)
        
        # Start file monitoring thread
        self.monitor_thread = threading.Thread(target=self.monitor_opening_file, daemon=True)
        self.monitor_thread.start()
        
        self.setup_routes()

        def resolve_file_uri(self, path):
                """Resolve file URI or recent:// URI to actual file path"""
                if not path:
                    return None
                    
                # Handle file:// URI
                if path.startswith('file://'):
                    return urlparse(path).path
                
                # Handle recent:// URI using gio (GNOME) or similar tools
                if path.startswith('recent://'):
                    try:
                        # Try to get real path using gio info
                        result = subprocess.run(
                            ['gio', 'info', path, '--attributes=standard::target-uri'],
                            capture_output=True, text=True, timeout=5
                        )
                        if result.returncode == 0:
                            for line in result.stdout.split('\n'):
                                if 'standard::target-uri:' in line:
                                    target_uri = line.split(':', 2)[2].strip()
                                    if target_uri.startswith('file://'):
                                        return urlparse(target_uri).path
                    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
                        pass
                
                # Return as-is if already a regular path
                return path
    
    def monitor_opening_file(self):
        """Monitor opening.txt file for new file paths to open"""
        while self.monitoring_active:
            try:
                # Try to acquire lock with timeout
                try:
                    with self.opening_lock.acquire(timeout=1):
                        if self.opening_file.exists():
                            # Read content
                            content = self.opening_file.read_text(encoding='utf-8').strip()
                            
                            if content:
                                # Parse file paths (one per line)
                                file_paths = [line.strip() for line in content.splitlines() if line.strip()]
                                
                                # Process each file immediately
                                for file_path in file_paths:
                                    # Resolve URI to actual path
                                    resolved_path = self.resolve_file_uri(file_path)
                                    if resolved_path and os.path.exists(resolved_path) and resolved_path.endswith('.md'):
                                        print(f"Opening file: {resolved_path}")
                                        self.send_open_tab_event(resolved_path)
                                
                                # Clear the file content
                                self.opening_file.write_text('', encoding='utf-8')
                            
                            # If no content, release lock quickly to allow other scripts to write
                            # Lock is automatically released when exiting the 'with' block
                        
                except Exception as lock_error:
                    # If can't acquire lock, just wait and try again
                    pass
                
                # Wait before next check (adjust interval as needed)
                time.sleep(0.5)  # Check every 500ms
                
            except Exception as e:
                print(f"Error monitoring opening file: {e}")
                time.sleep(1)  # Wait longer on error
    
    def send_open_tab_event(self, file_path):
        """Send open_tab event to all connected clients"""
        try:
            # Read file content
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Create event data
            event_data = {
                'type': 'open_tab',
                'url': f'/editor.html?path={quote(file_path)}',
                'title': os.path.basename(file_path),
                'file_path': file_path,
                'content': content
            }
            
            # Send to all connected SSE clients
            self.broadcast_event(event_data)
            
        except Exception as e:
            print(f"Error sending open tab event: {e}")
    
    def broadcast_event(self, event_data):
        """Broadcast event to all SSE clients"""
        # Store event for any clients that connect later
        if not hasattr(self, '_pending_events'):
            self._pending_events = []
        
        self._pending_events.append(event_data)
        
        # Keep only last 10 events to avoid memory issues
        if len(self._pending_events) > 10:
            self._pending_events = self._pending_events[-10:]
    
    def markdown_to_html(self, markdown_content):
        """Basic markdown to HTML conversion"""
        # This is a very basic implementation
        # For production, you'd want to use a proper markdown library like markdown or mistune
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Exported Document</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 2rem;
            line-height: 1.6;
        }}
        h1, h2, h3, h4, h5, h6 {{
            margin-top: 2rem;
            margin-bottom: 1rem;
        }}
        p {{
            margin-bottom: 1rem;
        }}
        code {{
            background: #f5f5f5;
            padding: 0.2rem 0.4rem;
            border-radius: 3px;
        }}
        pre {{
            background: #f5f5f5;
            padding: 1rem;
            border-radius: 6px;
            overflow-x: auto;
        }}
    </style>
</head>
<body>
    <pre>{markdown_content}</pre>
</body>
</html>"""
        return html
    
    def setup_routes(self):
        """Setup Flask routes"""
        
        @self.app.route('/')
        def index():
            return send_from_directory(self.app_dir, 'main.html')
        
        @self.app.route('/<path:filename>')
        def serve_file(filename):
            try:
                return send_from_directory(self.app_dir, filename)
            except FileNotFoundError:
                return "File not found", 404
        
        @self.app.route('/config.yaml')
        def serve_config():
            config_path = self.app_dir / 'config.yaml'
            if config_path.exists():
                return send_from_directory(self.app_dir, 'config.yaml')
            else:
                # Return default config
                default_config = {
                    'theme': 'system',
                    'autoSave': True,
                    'autoSaveInterval': 30000,
                    'editor': {
                        'previewStyle': 'vertical',
                        'height': '100%',
                        'initialEditType': 'wysiwyg',
                        'initialValue': '# Start writing your note here....',
                        'usageStatistics': False,
                        'hideModeSwitch': True,
                        'toolbarItems': [
                            ['heading', 'bold', 'italic', 'strike'],
                            ['hr', 'quote'],
                            ['ul', 'ol', 'task', 'indent', 'outdent'],
                            ['table', 'link', 'image'],
                            ['code', 'codeblock'],
                            ['scrollSync']
                        ]
                    }
                }
                return yaml.dump(default_config), 200, {'Content-Type': 'text/yaml'}
        
        @self.app.route('/api/tab-content')
        def serve_tab_content():
            """Serve content for a tab (e.g., file content in an editor)"""
            file_path = request.args.get('file')
            if not file_path:
                return "No file specified", 400
            
            # Decode URL-encoded path
            file_path = unquote(file_path)
            
            if not os.path.exists(file_path):
                return f"File not found: {file_path}", 404
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Return a simple HTML page with the file content
                # In a real implementation, this would be your editor page
                html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{os.path.basename(file_path)}</title>
    <style>
        body {{
            font-family: 'Cantarell', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #fafafa;
            color: #2e3436;
        }}
        .editor {{
            width: 100%;
            height: calc(100vh - 40px);
            border: 1px solid #d1d5db;
            border-radius: 6px;
            padding: 10px;
            font-family: 'Fira Code', 'Consolas', monospace;
            font-size: 14px;
            resize: none;
            outline: none;
        }}
        .toolbar {{
            margin-bottom: 10px;
            padding: 10px;
            background: #ebebeb;
            border-radius: 6px;
            font-weight: 500;
        }}
        @media (prefers-color-scheme: dark) {{
            body {{
                background-color: #242424;
                color: #ffffff;
            }}
            .editor {{
                background-color: #1e1e1e;
                color: #ffffff;
                border-color: #3d3d3d;
            }}
            .toolbar {{
                background: #232428;
                color: #f7f9fc;
            }}
        }}
    </style>
</head>
<body>
    <div class="toolbar">
        Editing: {os.path.basename(file_path)}
    </div>
    <textarea class="editor" placeholder="Start editing...">{content}</textarea>
    
    <script>
        // Auto-resize textarea
        const editor = document.querySelector('.editor');
        
        function autoSave() {{
            const content = editor.value;
            // Send save request to backend
            fetch('/api/save-content', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json'
                }},
                body: JSON.stringify({{
                    file_path: '{file_path}',
                    content: content
                }})
            }});
        }}
        
        // Auto-save every 2 seconds when content changes
        let saveTimeout;
        editor.addEventListener('input', () => {{
            clearTimeout(saveTimeout);
            saveTimeout = setTimeout(autoSave, 2000);
        }});
        
        // Save on Ctrl+S
        document.addEventListener('keydown', (e) => {{
            if (e.ctrlKey && e.key === 's') {{
                e.preventDefault();
                autoSave();
            }}
        }});
    </script>
</body>
</html>"""
                return html
                
            except Exception as e:
                return f"Error reading file: {str(e)}", 500
        
        @self.app.route('/api/save-content', methods=['POST'])
        def save_content():
            """Save content to a file"""
            try:
                data = request.get_json()
                file_path = data.get('file_path')
                content = data.get('content', '')
                
                if not file_path:
                    return jsonify({'success': False, 'message': 'No file path provided'})
                
                # Write content to file
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                return jsonify({
                    'success': True,
                    'message': f'Saved {os.path.basename(file_path)}'
                })
                
            except Exception as e:
                return jsonify({
                    'success': False,
                    'message': f'Error saving file: {str(e)}'
                })
        
        @self.app.route('/api/get-pending-files', methods=['GET'])
        def get_pending_files():
            """Get list of pending files to be opened"""
            try:
                if self.pending_files:
                    # Return the first pending file and remove it from queue
                    file_path = self.pending_files.pop(0)
                    
                    # Read the file content
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Update current file
                    self.current_file = file_path
                    self.current_content = content
                    
                    return jsonify({
                        'success': True,
                        'hasFile': True,
                        'content': content,
                        'filename': os.path.basename(file_path),
                        'filepath': file_path,
                        'remainingCount': len(self.pending_files)
                    })
                else:
                    return jsonify({
                        'success': True,
                        'hasFile': False,
                        'remainingCount': 0
                    })
                    
            except Exception as e:
                return jsonify({
                    'success': False,
                    'message': f'Error getting pending files: {str(e)}'
                })
        
        @self.app.route('/api/open', methods=['POST'])
        def open_file():
            try:
                # Use pywebview's file dialog
                file_types = [
                    'Markdown files (*.md;*.markdown)',
                    'Text files (*.txt)',
                    'All files (*.*)'
                ]
                
                file_path = self.window.create_file_dialog(
                    webview.OPEN_DIALOG,
                    allow_multiple=False,
                    file_types=file_types
                )
                
                if file_path and len(file_path) > 0:
                    selected_file = file_path[0]  # file_path is a list
                    
                    with open(selected_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    self.current_file = selected_file
                    self.current_content = content
                    
                    return jsonify({
                        'success': True,
                        'content': content,
                        'filename': os.path.basename(selected_file)
                    })
                else:
                    return jsonify({
                        'success': False,
                        'message': 'No file selected'
                    })
                    
            except Exception as e:
                return jsonify({
                    'success': False,
                    'message': f'Error opening file: {str(e)}'
                })
        
        @self.app.route('/api/open-path', methods=['POST'])
        def open_file_by_path():
            try:
                data = request.get_json()
                file_path = data.get('path')
                
                if not file_path:
                    return jsonify({
                        'success': False,
                        'message': 'No path provided'
                    })
                
                # Decode URL-encoded path
                file_path = unquote(file_path)
                
                # Resolve URI to actual file path
                resolved_path = self.resolve_file_uri(file_path)
                if not resolved_path:
                    return jsonify({
                        'success': False,
                        'message': f'Could not resolve path: {file_path}'
                    })
                
                if not os.path.exists(resolved_path):
                    return jsonify({
                        'success': False,
                        'message': f'File not found: {resolved_path}'
                    })
                
                file_path = resolved_path  # Use resolved path for subsequent operations
                
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                self.current_file = file_path
                self.current_content = content
                
                return jsonify({
                    'success': True,
                    'content': content,
                    'filename': os.path.basename(file_path)
                })
                
            except Exception as e:
                return jsonify({
                    'success': False,
                    'message': f'Error opening file: {str(e)}'
                })
        
        @self.app.route('/api/save', methods=['POST'])
        def save_file():
            try:
                data = request.get_json()
                content = data.get('content', '')
                
                if self.current_file:
                    # Save to existing file
                    with open(self.current_file, 'w', encoding='utf-8') as f:
                        f.write(content)
                    
                    self.current_content = content
                    
                    return jsonify({
                        'success': True,
                        'filename': os.path.basename(self.current_file)
                    })
                else:
                    # No current file, use Save As
                    return self.save_as_file_internal(content)
                    
            except Exception as e:
                return jsonify({
                    'success': False,
                    'message': f'Error saving file: {str(e)}'
                })
        
        @self.app.route('/api/save-as', methods=['POST'])
        def save_as_file():
            try:
                data = request.get_json()
                content = data.get('content', '')
                return self.save_as_file_internal(content)
                
            except Exception as e:
                return jsonify({
                    'success': False,
                    'message': f'Error saving file: {str(e)}'
                })
        
        @self.app.route('/api/export', methods=['POST'])
        def export_file():
            try:
                data = request.get_json()
                content = data.get('content', '')
                
                # Use pywebview's file dialog for export
                file_types = [
                    'HTML files (*.html)',
                    'PDF files (*.pdf)',
                    'Text files (*.txt)',
                    'All files (*.*)'
                ]
                
                file_path = self.window.create_file_dialog(
                    webview.SAVE_DIALOG,
                    save_filename='exported_document.html',
                    file_types=file_types
                )
                
                if file_path:
                    # file_path is a string for save dialog
                    with open(file_path, 'w', encoding='utf-8') as f:
                        if file_path.endswith('.html'):
                            # Basic markdown to HTML conversion
                            html_content = self.markdown_to_html(content)
                            f.write(html_content)
                        else:
                            f.write(content)
                    
                    return jsonify({
                        'success': True,
                        'filename': os.path.basename(file_path)
                    })
                else:
                    return jsonify({
                        'success': False,
                        'message': 'No file selected'
                    })
                    
            except Exception as e:
                return jsonify({
                    'success': False,
                    'message': f'Error exporting file: {str(e)}'
                })
        
        @self.app.route('/events')
        def events():
            """Server-sent events for real-time communication"""
            def event_stream():
                client_id = len(self.event_clients)
                self.event_clients.append(client_id)
                
                try:
                    # Send any pending events first
                    if hasattr(self, '_pending_events'):
                        for event in self._pending_events:
                            yield f"data: {json.dumps(event)}\n\n"
                        # Clear pending events after sending
                        self._pending_events = []
                    
                    # Keep connection alive and send new events
                    last_event_count = 0
                    while True:
                        # Check for new events
                        if hasattr(self, '_pending_events') and len(self._pending_events) > last_event_count:
                            for event in self._pending_events[last_event_count:]:
                                yield f"data: {json.dumps(event)}\n\n"
                            last_event_count = len(self._pending_events)
                        else:
                            # Keep connection alive with ping
                            yield f"data: {json.dumps({'type': 'ping', 'timestamp': time.time()})}\n\n"
                        
                        time.sleep(1)  # Check every second
                        
                except GeneratorExit:
                    # Client disconnected
                    if client_id in self.event_clients:
                        self.event_clients.remove(client_id)
            
            return Response(event_stream(), mimetype='text/event-stream', 
                          headers={
                              'Cache-Control': 'no-cache',
                              'Connection': 'keep-alive',
                              'Access-Control-Allow-Origin': '*'
                          })
    
    def save_as_file_internal(self, content):
        """Internal save as implementation"""
        try:
            # Use pywebview's file dialog
            file_types = [
                'Markdown files (*.md)',
                'Text files (*.txt)',
                'All files (*.*)'
            ]
            
            default_filename = 'untitled.md'
            if self.current_file:
                default_filename = os.path.basename(self.current_file)
            
            file_path = self.window.create_file_dialog(
                webview.SAVE_DIALOG,
                save_filename=default_filename,
                file_types=file_types
            )
            
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                self.current_file = file_path
                self.current_content = content
                
                return jsonify({
                    'success': True,
                    'filename': os.path.basename(file_path)
                })
            else:
                return jsonify({
                    'success': False,
                    'message': 'No file selected'
                })
                
        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'Error saving file: {str(e)}'
            })
    
    def cleanup(self):
        """Cleanup resources"""
        self.monitoring_active = False
        # Release server lock
        if hasattr(self, 'server_lock') and self.server_lock.is_locked:
            self.server_lock.release()
    
    def find_available_port(self, start_port=5000, max_attempts=100):
        """Find an available port within allowed range"""
        def is_port_available(port):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('127.0.0.1', port))
                    return True
            except OSError:
                return False
        
        # Try start_port first
        if is_port_available(start_port):
            return start_port
        
        # Try random ports in allowed range (1024-65535, avoiding system ports)
        for _ in range(max_attempts):
            port = random.randint(1024, 65535)
            if is_port_available(port):
                return port
        
        return None
        
    def run(self, file_path=None, debug=False):
        """Run the application"""
        # Acquire server lock
        try:
            self.server_lock.acquire(blocking=False)
        except:
            print("Another instance of MarkFlow is already running.")
            sys.exit(1)
        
        try:
            # Find available port
            self.server_port = self.find_available_port()
            if self.server_port is None:
                print("Could not find an available port after 100 attempts.")
                sys.exit(1)
            
            print(f"Starting server on port {self.server_port}")
            
            # Store initial file path
            initial_file = None
            if file_path:
                resolved_path = self.resolve_file_uri(file_path)
                if resolved_path and os.path.exists(resolved_path):
                    initial_file = os.path.abspath(resolved_path)
                # Load the file content
                try:
                    with open(initial_file, 'r', encoding='utf-8') as f:
                        self.current_content = f.read()
                    self.current_file = initial_file
                except Exception as e:
                    print(f"Warning: Could not load initial file {file_path}: {e}")
            
            # Start Flask server in a thread
            flask_thread = threading.Thread(
                target=lambda: self.app.run(
                    host='127.0.0.1',
                    port=self.server_port,
                    debug=False,  # Don't use debug mode with webview
                    use_reloader=False,
                    threaded=True
                ),
                daemon=True
            )
            flask_thread.start()
            
            # Wait for server to start
            time.sleep(2)
            
            # Build URL with query parameters for initial file
            url = f'http://127.0.0.1:{self.server_port}/'
            if initial_file:
                encoded_path = quote(initial_file)
                url += f'?file={encoded_path}'
            
            # Create and start webview
            try:
                # Create API class for pywebview integration
                class MarkFlowAPI:
                    def __init__(self, server):
                        self.server = server
                    
                    def open_file(self):
                        """Open file dialog and return file content"""
                        try:
                            file_types = [
                                'Markdown files (*.md;*.markdown)',
                                'Text files (*.txt)',
                                'All files (*.*)'
                            ]
                            
                            file_path = webview.windows[0].create_file_dialog(
                                webview.OPEN_DIALOG,
                                allow_multiple=False,
                                file_types=file_types
                            )
                            
                            if file_path and len(file_path) > 0:
                                selected_file = file_path[0]
                                
                                with open(selected_file, 'r', encoding='utf-8') as f:
                                    content = f.read()
                                
                                self.server.current_file = selected_file
                                self.server.current_content = content
                                
                                return {
                                    'success': True,
                                    'content': content,
                                    'filename': os.path.basename(selected_file)
                                }
                            else:
                                return {
                                    'success': False,
                                    'message': 'No file selected'
                                }
                                
                        except Exception as e:
                            return {
                                'success': False,
                                'message': f'Error opening file: {str(e)}'
                            }
                    
                    def save_file(self, content):
                        """Save file content"""
                        try:
                            if self.server.current_file:
                                # Save to existing file
                                with open(self.server.current_file, 'w', encoding='utf-8') as f:
                                    f.write(content)
                                
                                self.server.current_content = content
                                
                                return {
                                    'success': True,
                                    'filename': os.path.basename(self.server.current_file)
                                }
                            else:
                                # No current file, use Save As
                                return self.save_as_file(content)
                                
                        except Exception as e:
                            return {
                                'success': False,
                                'message': f'Error saving file: {str(e)}'
                            }
                    
                    def save_as_file(self, content):
                        """Save As file dialog"""
                        try:
                            file_types = [
                                'Markdown files (*.md)',
                                'Text files (*.txt)',
                                'All files (*.*)'
                            ]
                            
                            default_filename = 'untitled.md'
                            if self.server.current_file:
                                default_filename = os.path.basename(self.server.current_file)
                            
                            file_path = webview.windows[0].create_file_dialog(
                                webview.SAVE_DIALOG,
                                save_filename=default_filename,
                                file_types=file_types
                            )
                            
                            if file_path:
                                with open(file_path, 'w', encoding='utf-8') as f:
                                    f.write(content)
                                
                                self.server.current_file = file_path
                                self.server.current_content = content
                                
                                return {
                                    'success': True,
                                    'filename': os.path.basename(file_path)
                                }
                            else:
                                return {
                                    'success': False,
                                    'message': 'No file selected'
                                }
                                
                        except Exception as e:
                            return {
                                'success': False,
                                'message': f'Error saving file: {str(e)}'
                            }
                
                # Create window with API
                self.window = webview.create_window(
                    'MarkFlow',
                    url,
                    width=1200,
                    height=800,
                    min_size=(800, 600),
                    resizable=True,
                    js_api=MarkFlowAPI(self)
                )
                
                # Start webview
                webview.start(debug=debug)
                
            except Exception as e:
                print(f"Error starting webview: {e}")
                print(f"You can still access the application at http://127.0.0.1:{self.server_port}/")
                try:
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    print("\nShutting down...")
                
        finally:
            self.cleanup()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='MarkFlow - Markdown Editor')
    parser.add_argument(
        'file', 
        nargs='?', 
        help='Markdown file to open initially'
    )
    parser.add_argument(
        '--debug', 
        action='store_true', 
        help='Run in debug mode'
    )
    
    args = parser.parse_args()
    
    # Create and run server
    server = MarkFlowServer()
    
    try:
        server.run(file_path=args.file, debug=args.debug)
    except KeyboardInterrupt:
        print("\nShutting down MarkFlow...")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
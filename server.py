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
from pathlib import Path
from urllib.parse import quote, unquote
from flask import Flask, request, jsonify, send_from_directory, Response, stream_template
import webview

class MarkFlowServer:
    def __init__(self):
        self.app = Flask(__name__)
        self.app_dir = Path(__file__).parent / 'app'
        self.current_file = None
        self.current_content = ""
        self.clients = []  # For server-sent events
        
        # Ensure app directory exists
        self.app_dir.mkdir(exist_ok=True)
        
        self.setup_routes()
    
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
                
                if not os.path.exists(file_path):
                    return jsonify({
                        'success': False,
                        'message': f'File not found: {file_path}'
                    })
                
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
                while True:
                    # Keep connection alive
                    yield f"data: {json.dumps({'type': 'ping'})}\n\n"
                    time.sleep(30)
            
            return Response(event_stream(), mimetype='text/plain')
    
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
    
    def run(self, file_path=None, debug=False):
        """Run the application"""
        # Store initial file path
        initial_file = None
        if file_path and os.path.exists(file_path):
            initial_file = os.path.abspath(file_path)
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
                port=5000,
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
        url = 'http://127.0.0.1:5000/'
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
            print("You can still access the application at http://127.0.0.1:5000/")
            # Keep server running
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\nShutting down...")


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
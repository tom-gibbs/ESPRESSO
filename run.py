# run.py - Simple static file server for ESPRESSO
#
# This server is optional - it just serves the HTML file locally.
# Data is stored in your browser's localStorage.
# Google Drive sync is available for backup/cross-device sync.
#
from http.server import SimpleHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse
import threading
import webbrowser

PORT = 8000

class Handler(SimpleHTTPRequestHandler):
    # Only serve specific files for security
    ALLOWED_FILES = {"/", "/index.html", "/espresso-icon.png"}

    def do_GET(self):
        u = urlparse(self.path)
        path = u.path if u.path != "/" else "/index.html"
        if path not in self.ALLOWED_FILES:
            self.send_error(404, "Not Found")
            return
        return super().do_GET()

    def log_message(self, format, *args):
        # Quieter logging
        pass

def open_browser():
    webbrowser.open(f"http://localhost:{PORT}/index.html")

if __name__ == "__main__":
    print("ESPRESSO")
    print(f"Opening http://localhost:{PORT}")
    print("Press Ctrl+C to stop.\n")
    threading.Timer(0.5, open_browser).start()
    server = HTTPServer(("localhost", PORT), Handler)
    server.serve_forever()

import sys
from http.server import HTTPServer, BaseHTTPRequestHandler

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "healthy", "service": "celery-huggingface"}')

    def log_message(self, format, *args):
        # Suppress standard logging to prevent log pollution
        pass

def run():
    server_address = ("0.0.0.0", 7860)
    httpd = HTTPServer(server_address, HealthCheckHandler)
    print("🚀 Background health-check HTTP server running on port 7860...")
    httpd.serve_forever()

if __name__ == "__main__":
    run()

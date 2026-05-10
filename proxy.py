import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.request
import ssl

TARGET_HOST = "https://hydrographically-tawdrier-hayley.ngrok-free.dev"

class ProxyHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        # Handle CORS
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS, PATCH, PUT, DELETE')
        headers = self.headers.get('Access-Control-Request-Headers', '*')
        self.send_header('Access-Control-Allow-Headers', headers)
        self.end_headers()

    def handle_request(self):
        path = self.path
        # Fix the double api/v1/v1 issue
        if path.startswith("/api/v1/v1/"):
            path = path.replace("/api/v1/v1/", "/api/v1/")
        
        target_url = TARGET_HOST + path
        
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else None
        
        headers = {}
        for key, val in self.headers.items():
            if key.lower() not in ['host', 'origin', 'referer', 'accept-encoding']:
                headers[key] = val
                
        req = urllib.request.Request(target_url, data=post_data, headers=headers, method=self.command)
        
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            with urllib.request.urlopen(req, context=ctx) as response:
                result = response.read()
                self.send_response(response.status)
                
                for key, val in response.getheaders():
                    if key.lower() not in ['transfer-encoding', 'content-encoding', 'access-control-allow-origin']:
                        self.send_header(key, val)
                        
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(result)
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            for key, val in e.headers.items():
                if key.lower() not in ['transfer-encoding', 'content-encoding', 'access-control-allow-origin']:
                    self.send_header(key, val)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode('utf-8'))

    def do_GET(self): self.handle_request()
    def do_POST(self): self.handle_request()
    def do_PUT(self): self.handle_request()
    def do_PATCH(self): self.handle_request()

def run(port=8000):
    server_address = ('', port)
    httpd = HTTPServer(server_address, ProxyHTTPRequestHandler)
    print(f"Proxying localhost:{port} to {TARGET_HOST}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)

if __name__ == '__main__':
    run()

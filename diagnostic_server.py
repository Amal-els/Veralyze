
import http.server
import socketserver
import json

PORT = 8000

class DiagnosticHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps({"status": "DIAGNOSTIC_OK", "message": "The port is open and reachable!"}).encode())

print(f"DIAGNOSTIC: Attempting to open port {PORT}...")
try:
    with socketserver.TCPServer(("127.0.0.1", PORT), DiagnosticHandler) as httpd:
        print(f"🚀 SUCCESS: Diagnostic server is now listening on http://127.0.0.1:{PORT}")
        print("Keep this running and try 'python test_bridge.py' in another terminal.")
        httpd.serve_forever()
except Exception as e:
    print(f"❌ FAIL: Could not start server: {e}")

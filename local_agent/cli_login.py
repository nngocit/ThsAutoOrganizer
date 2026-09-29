import json
import webbrowser
import threading
import socket
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

def run_login():
    # Start a local server on a random port
    server = HTTPServer(('127.0.0.1', 0), LoginHandler)
    port = server.server_port
    
    login_url = f"https://ths-organizer.pages.dev?cli_login={port}"
    print("\n" + "="*60)
    print("🔒 YÊU CẦU ĐĂNG NHẬP (OAUTH FLOW)")
    print("="*60)
    print(f"\nTrình duyệt của bạn sẽ được mở tự động.")
    print(f"Nếu trình duyệt không mở, hãy click vào link sau:")
    print(f"\n👉 {login_url}\n")
    print("Đang chờ xác thực từ trình duyệt... (Bấm Ctrl+C để hủy)")
    
    try:
        webbrowser.open(login_url)
    except:
        pass

    try:
        server.handle_request()  # Wait for a single request
    except KeyboardInterrupt:
        print("\nĐã hủy đăng nhập.")
        
class LoginHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/callback':
            query = parse_qs(parsed.query)
            uid = query.get('uid', [''])[0]
            
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            if uid:
                self.wfile.write(b"<html><body><h1>Dang nhap thanh cong!</h1><p>Ban co the dong tab nay va quay lai Terminal.</p><script>setTimeout(()=>window.close(), 2000)</script></body></html>")
                self.save_uid_to_config(uid)
                print(f"\n✅ Đăng nhập thành công!")
                print(f"✅ Đã lưu UID ({uid}) vào config.json")
                print(f"🚀 Bây giờ bạn có thể chạy 'python main.py' để bắt đầu đồng bộ.\n")
            else:
                self.wfile.write(b"<html><body><h1>Dang nhap THAT BAI!</h1><p>Khong tim thay UID.</p></body></html>")
                print(f"\n❌ Đăng nhập thất bại: Không nhận được UID.\n")
        else:
            self.send_response(404)
            self.end_headers()
            
    def log_message(self, format, *args):
        pass # Tắt log của server

    def save_uid_to_config(self, uid):
        config_path = Path(__file__).parent.parent / "config.json"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {}
            
        data["uid"] = uid
        
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

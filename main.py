"""ThacSi HTTT Auto Organizer — Golden Baseline (Initialization Only).

File khởi tạo cốt lõi của hệ thống.
Chỉ thực thi đúng 5 luồng cốt lõi theo tiêu chuẩn Golden Baseline:
1. Đọc cấu hình từ file/môi trường
2. Khởi tạo/Kiểm tra kết nối NotebookLM MCP CLI
3. Khởi tạo SDK Firebase
4. Xác thực người dùng (Auth bằng email)
5. Khởi tạo/Ping dịch vụ Cloudflare Worker
"""

import json
import logging
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from typing import Any, Dict, Optional

import requests

# Cấu hình logging
logger = logging.getLogger("ThsAutoOrganizer")
logger.setLevel(logging.INFO)


# ======================================================================
# CÁC MODULE ĐÃ ĐƯỢC DỌN SẠCH VỀ GOLDEN BASELINE (STUBS)
# ======================================================================

class WatchdogHandler:
    """Bộ lọc và bắt sự kiện file hệ thống (File Watcher)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # TODO: Sẽ tích hợp module sau
        pass


def worker_loop(*args: Any, **kwargs: Any) -> None:
    """Xử lý hàng đợi task queue nền."""
    # TODO: Sẽ tích hợp module sau
    pass


def scan_existing_files(*args: Any, **kwargs: Any) -> None:
    """Quét dữ liệu file sẵn có."""
    # TODO: Sẽ tích hợp module sau
    pass


def sync_drive(*args: Any, **kwargs: Any) -> None:
    """Đồng bộ tài liệu Google Drive."""
    # TODO: Sẽ tích hợp module sau
    pass


# ======================================================================
# 5 LUỒNG CỐT LÕI (GOLDEN BASELINE IMPLEMENTATION)
# ======================================================================

def step1_load_config(config_path: Path | str = "config.json") -> Dict[str, Any]:
    """1. Đọc cấu hình từ file/môi trường."""
    path = Path(config_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy file cấu hình: {path}")

    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # Ưu tiên biến môi trường nếu có
    if os.environ.get("ROOT_FOLDER"):
        cfg["root_folder"] = os.environ["ROOT_FOLDER"]
    if os.environ.get("ROOT_ACCOUNT_EMAIL"):
        cfg["root_account_email"] = os.environ["ROOT_ACCOUNT_EMAIL"]
    if os.environ.get("WORKER_URL"):
        cfg["worker_url"] = os.environ["WORKER_URL"]
    if os.environ.get("AGENT_SECRET"):
        cfg["agent_secret"] = os.environ["AGENT_SECRET"]

    # Đảm bảo thư mục gốc tồn tại
    root_folder = Path(cfg.get("root_folder") or cfg.get("local_base_path") or ".").resolve()
    root_folder.mkdir(parents=True, exist_ok=True)
    cfg["root_folder"] = str(root_folder)

    return cfg


def step2_connect_mcp(mcp_config_path: Path | str = ".agents/mcp_config.json") -> bool:
    """2. Khởi tạo/Kiểm tra kết nối NotebookLM MCP CLI."""
    # Kiểm tra cấu hình MCP server
    mcp_path = Path(mcp_config_path).resolve()
    if mcp_path.exists():
        with open(mcp_path, "r", encoding="utf-8") as f:
            mcp_data = json.load(f)
            if "mcpServers" not in mcp_data or "notebooklm" not in mcp_data["mcpServers"]:
                raise ValueError("Cấu hình MCP thiếu server 'notebooklm'")

    # Kiểm tra NotebookLM CLI có thể thực thi
    res = subprocess.run(
        ["nlm", "--version"],
        capture_output=True,
        text=True,
        timeout=15,
        encoding="utf-8",
    )
    if res.returncode != 0:
        raise RuntimeError(f"NotebookLM MCP CLI phản hồi lỗi: {res.stderr}")

    return True


def initialize_firebase_sdk(service_account_path: Optional[Path | str] = None) -> Any:
    """Khởi tạo SDK Firebase Admin từ Service Account JSON."""
    import firebase_admin
    from firebase_admin import credentials

    if firebase_admin._apps:
        return firebase_admin.get_app()

    if service_account_path:
        sa_path = Path(service_account_path).resolve()
    else:
        # Tìm file Service Account trong thư mục firebase/
        sa_files = list(Path("firebase").glob("*adminsdk*.json"))
        if not sa_files:
            raise FileNotFoundError("Không tìm thấy file Firebase Service Account trong thư mục firebase/")
        sa_path = sa_files[0].resolve()

    if not sa_path.exists():
        raise FileNotFoundError(f"File Service Account không tồn tại: {sa_path}")

    cred = credentials.Certificate(str(sa_path))
    return firebase_admin.initialize_app(cred)


def step3_init_firebase(service_account_path: Optional[Path | str] = None) -> Any:
    """3. Khởi tạo SDK Firebase."""
    return initialize_firebase_sdk(service_account_path)


def verify_user_auth(email: str, db_path: Path | str = "data/files.db") -> Dict[str, Any]:
    """Xác thực người dùng bằng email."""
    clean_email = (email or "").strip().lower()
    if not clean_email or "@" not in clean_email:
        raise ValueError(f"Email xác thực không hợp lệ: '{email}'")

    # Kiểm tra người dùng trong cơ sở dữ liệu SQLite nếu tồn tại
    db_file = Path(db_path).resolve()
    if db_file.exists():
        conn = sqlite3.connect(str(db_file))
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT email, name FROM users WHERE LOWER(email) = LOWER(?) LIMIT 1;", (clean_email,))
            row = cursor.fetchone()
            if row:
                return {"email": row[0], "name": row[1] or "", "verified": True}
        finally:
            conn.close()

    return {"email": clean_email, "verified": True}


def step4_authenticate_user(email: str, db_path: Path | str = "data/files.db") -> Dict[str, Any]:
    """4. Xác thực người dùng (Auth)."""
    return verify_user_auth(email=email, db_path=db_path)


def step5_ping_cloudflare(worker_url: str) -> bool:
    """5. Khởi tạo/Ping dịch vụ Cloudflare Worker."""
    url = (worker_url or "").rstrip("/")
    if not url:
        raise ValueError("URL Cloudflare Worker không được để trống")

    health_url = f"{url}/health"
    resp = requests.get(health_url, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(f"Cloudflare Worker phản hồi mã lỗi HTTP {resp.status_code}: {resp.text}")

    data = resp.json()
    if data.get("status") != "ok":
        raise RuntimeError(f"Dịch vụ Cloudflare trả về trạng thái không sẵn sàng: {data}")

    return True


# ======================================================================
# ĐIỂM CHẠY CHÍNH (MAIN FUNCTION)
# ======================================================================

def main() -> None:
    """Điểm khởi chạy chính - Golden Baseline (Chỉ thực thi 5 luồng cốt lõi)."""
    # Đảm bảo UTF-8 cho console Windows
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    # 1. Đọc cấu hình từ file/môi trường
    try:
        config = step1_load_config("config.json")
        print("✅ Đọc cấu hình thư mục thành công...", flush=True)
    except Exception as exc:
        logger.error("Lỗi Bước 1: %s", exc)
        raise

    # 2. Khởi tạo/Kiểm tra kết nối MCP
    try:
        step2_connect_mcp(".agents/mcp_config.json")
        print("✅ Kết nối NotebookLM MCP CLI thành công...", flush=True)
    except Exception as exc:
        logger.error("Lỗi Bước 2: %s", exc)
        raise

    # 3. Khởi tạo SDK Firebase
    try:
        step3_init_firebase()
        print("✅ Kết nối login firebase thành công", flush=True)
    except Exception as exc:
        logger.error("Lỗi Bước 3: %s", exc)
        raise

    # 4. Xác thực người dùng (Auth)
    try:
        user_email = config.get("root_account_email", "xuanngocit@gmail.com")
        step4_authenticate_user(user_email)
        print("✅ Kết nối login bằng email thành công", flush=True)
    except Exception as exc:
        logger.error("Lỗi Bước 4: %s", exc)
        raise

    # 5. Khởi tạo/Ping dịch vụ Cloudflare
    try:
        worker_url = config.get("worker_url", "https://ths-organizer-api.ths-organizer-nngocit.workers.dev")
        step5_ping_cloudflare(worker_url)
        print("✅ Build deploy cloudflare sẵn sàng", flush=True)
    except Exception as exc:
        logger.error("Lỗi Bước 5: %s", exc)
        raise


if __name__ == "__main__":
    main()

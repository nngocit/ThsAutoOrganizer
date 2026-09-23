# local_agent/constants.py — Hằng số dùng chung (§1 API Contract, SINGLE SOURCE OF TRUTH)
# Mirror của cloudflare/workers/src/lib/folders.js — mọi thay đổi phải đồng bộ 3 nơi.

FOLDER_MAP: dict[str, str] = {
    "giao_trinh": "01_Giao_Trinh_Goc",
    "slide": "02_Slide_Giang_Day",
    "bai_bao": "03_Tai_Lieu_Tham_Khao/01_Bai_Bao_Khoa_Hoc",
    "unverified_web": "03_Tai_Lieu_Tham_Khao/02_Unverified_Web",
    "ket_qua": "04_Ket_Qua_Xuat_Ban",
}

OUTPUT_FOLDER = "04_Ket_Qua_Xuat_Ban"          # NO-LOOP GUARD
ARCHIVE_FOLDER = "_Archive_Trash_90Days"

# Inflow (file watcher) BỎ QUA mọi path nằm trong các thư mục này
NO_LOOP_FOLDERS = ["04_Ket_Qua_Xuat_Ban", "_Archive_Trash_90Days"]

HARD_DELETE_DAYS = 90

SUPPORTED_EXTENSIONS = [
    ".pdf", ".docx", ".pptx", ".txt", ".md", ".jpg", ".jpeg", ".png", ".mp3",
]

# Quy tắc review_status mặc định khi tạo file doc (§2)
DEFAULT_REVIEW_STATUS: dict[str, str] = {
    "giao_trinh": "approved",
    "slide": "approved",
    "bai_bao": "approved",
    "unverified_web": "unreviewed",
    "ket_qua": "approved",
}


def is_output_path(folder_path: str) -> bool:
    """NO-LOOP GUARD: folder_path bắt đầu bằng OUTPUT_FOLDER."""
    return (folder_path or "").replace("\\", "/").startswith(OUTPUT_FOLDER)


def is_no_loop_path(folder_path: str) -> bool:
    """Path nằm trong NO_LOOP_FOLDERS (output hoặc archive) — watcher phải bỏ qua."""
    norm = (folder_path or "").replace("\\", "/")
    return any(norm == f or norm.startswith(f + "/") or f"/{f}/" in norm for f in NO_LOOP_FOLDERS)

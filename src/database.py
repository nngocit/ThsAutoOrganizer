"""Module quản lý SQLite database.

Lưu trữ metadata, hash SHA-256 để chống trùng, trạng thái xử lý và ID Google Drive.
"""

from datetime import datetime, timezone
import logging
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ThsAutoOrganizer.database")

# Các trạng thái chuẩn của bản ghi
STATUS_PENDING = "PENDING"
STATUS_PROCESSING = "PROCESSING"
STATUS_UPLOADED = "UPLOADED"
STATUS_DUPLICATE = "DUPLICATE"
STATUS_ERROR = "ERROR"

VALID_STATUSES = {
    STATUS_PENDING,
    STATUS_PROCESSING,
    STATUS_UPLOADED,
    STATUS_DUPLICATE,
    STATUS_ERROR,
}


def current_iso_time() -> str:
    """Trả về chuỗi thời gian hiện tại định dạng ISO 8601 UTC."""
    return datetime.now(timezone.utc).isoformat()


class Database:
    """Lớp quản lý tương tác với SQLite database."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path).resolve()
        # Đảm bảo thư mục chứa file database tồn tại
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _get_connection(self) -> sqlite3.Connection:
        """Tạo kết nối mới với thiết lập an toàn đa luồng và timeout."""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        # Kích hoạt WAL mode để hỗ trợ đọc/ghi đồng thời tốt hơn
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def initialize(self) -> None:
        """Khởi tạo bảng files và các index nếu chưa tồn tại."""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sha256 TEXT NOT NULL,
            path TEXT NOT NULL,
            subject TEXT NOT NULL,
            document_type TEXT NOT NULL,
            drive_file_id TEXT,
            status TEXT NOT NULL,
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
        create_index_sha256 = """
        CREATE INDEX IF NOT EXISTS idx_files_sha256 ON files(sha256);
        """
        create_index_status = """
        CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);
        """

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(create_table_sql)
            cursor.execute(create_index_sha256)
            cursor.execute(create_index_status)
            conn.commit()

        logger.debug("Database initialized tại '%s'", self.db_path)

    def find_by_sha256(self, sha256: str) -> Optional[Dict[str, Any]]:
        """Tìm bản ghi theo SHA-256.

        Trả về bản ghi mới nhất hoặc bản ghi có trạng thái UPLOADED nếu có nhiều bản ghi trùng.
        """
        sql = """
        SELECT * FROM files
        WHERE sha256 = ?
        ORDER BY CASE WHEN status = ? THEN 0 ELSE 1 END, id DESC
        LIMIT 1;
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (sha256, STATUS_UPLOADED))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def find_by_path(self, path: str) -> Optional[Dict[str, Any]]:
        """Tìm bản ghi mới nhất theo đường dẫn file."""
        sql = """
        SELECT * FROM files
        WHERE path = ?
        ORDER BY CASE WHEN status = ? THEN 0 ELSE 1 END, id DESC
        LIMIT 1;
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (str(path), STATUS_UPLOADED))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def insert_record(
        self,
        sha256: str,
        path: str,
        subject: str,
        document_type: str,
        status: str = STATUS_PENDING,
        drive_file_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> int:
        """Thêm bản ghi mới vào database.

        Returns:
            id của bản ghi vừa tạo.
        """
        if status not in VALID_STATUSES:
            raise ValueError(f"Trạng thái không hợp lệ: '{status}'. Hợp lệ gồm: {VALID_STATUSES}")

        now = current_iso_time()
        sql = """
        INSERT INTO files (sha256, path, subject, document_type, drive_file_id, status, error, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                sql,
                (
                    sha256,
                    str(path),
                    subject,
                    document_type,
                    drive_file_id,
                    status,
                    error,
                    now,
                    now,
                ),
            )
            record_id = cursor.lastrowid
            conn.commit()

        if record_id is None:
            raise RuntimeError("Không thể lấy lastrowid sau khi insert record.")
        return record_id

    def update_status(
        self,
        record_id: int,
        status: str,
        drive_file_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Cập nhật trạng thái, drive_file_id và error của một bản ghi."""
        if status not in VALID_STATUSES:
            raise ValueError(f"Trạng thái không hợp lệ: '{status}'. Hợp lệ gồm: {VALID_STATUSES}")

        now = current_iso_time()
        updates = ["status = ?", "updated_at = ?"]
        params: List[Any] = [status, now]

        if drive_file_id is not None:
            updates.append("drive_file_id = ?")
            params.append(drive_file_id)

        if error is not None:
            updates.append("error = ?")
            params.append(error)

        params.append(record_id)
        sql = f"UPDATE files SET {', '.join(updates)} WHERE id = ?;"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()

    def update_classification(
        self,
        record_id: int,
        subject: str,
        document_type: str,
        drive_file_id: Optional[str] = None,
    ) -> None:
        """Cập nhật phân loại môn học và loại tài liệu khi người dùng 'sửa tay' trên giao diện."""
        now = current_iso_time()
        updates = ["subject = ?", "document_type = ?", "updated_at = ?"]
        params: List[Any] = [subject, document_type, now]

        if drive_file_id is not None:
            updates.append("drive_file_id = ?")
            params.append(drive_file_id)

        params.append(record_id)
        sql = f"UPDATE files SET {', '.join(updates)} WHERE id = ?;"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()

    def get_record(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Lấy bản ghi theo ID."""
        sql = "SELECT * FROM files WHERE id = ?;"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (record_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def get_all_records(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Lấy danh sách các bản ghi mới nhất."""
        sql = "SELECT * FROM files ORDER BY id DESC LIMIT ?;"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (limit,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

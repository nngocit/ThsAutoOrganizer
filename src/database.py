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
STATUS_SAVED_LOCAL = "SAVED_LOCAL"
STATUS_DUPLICATE = "DUPLICATE"
STATUS_ERROR = "ERROR"

VALID_STATUSES = {
    STATUS_PENDING,
    STATUS_PROCESSING,
    STATUS_UPLOADED,
    STATUS_SAVED_LOCAL,
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
        """Khởi tạo bảng users, files và các index nếu chưa tồn tại."""
        create_table_users = """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            name TEXT,
            avatar_url TEXT,
            local_folder TEXT DEFAULT '',
            drive_root_folder_id TEXT,
            access_token TEXT,
            refresh_token TEXT,
            token_expiry TEXT,
            major_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """

        create_table_files = """
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT DEFAULT 'default@user',
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

        create_table_majors = """
        CREATE TABLE IF NOT EXISTS majors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            folder_name TEXT NOT NULL,
            description TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """

        create_table_subjects = """
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            major_id INTEGER NOT NULL REFERENCES majors(id) ON DELETE CASCADE,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            folder_name TEXT NOT NULL,
            keywords TEXT DEFAULT '[]',
            is_default INTEGER DEFAULT 1,
            created_by TEXT DEFAULT 'admin',
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
        create_index_user_email = """
        CREATE INDEX IF NOT EXISTS idx_files_user_email ON files(user_email);
        """
        create_index_subjects_major = """
        CREATE INDEX IF NOT EXISTS idx_subjects_major_id ON subjects(major_id);
        """

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(create_table_users)
            cursor.execute(create_table_files)
            cursor.execute(create_table_majors)
            cursor.execute(create_table_subjects)

            # Migration an toàn nếu bảng cũ chưa có các cột mới
            try:
                cursor.execute("ALTER TABLE files ADD COLUMN user_email TEXT DEFAULT 'default@user';")
            except Exception:
                pass  # Cột đã tồn tại

            try:
                cursor.execute("ALTER TABLE users ADD COLUMN local_folder TEXT DEFAULT '';")
            except Exception:
                pass  # Cột đã tồn tại

            try:
                cursor.execute("ALTER TABLE users ADD COLUMN major_id INTEGER;")
            except Exception:
                pass  # Cột đã tồn tại

            cursor.execute(create_index_sha256)
            cursor.execute(create_index_status)
            cursor.execute(create_index_user_email)
            cursor.execute(create_index_subjects_major)

            # Tự động chuyển các file của tài khoản gốc default@user về xuanngocit@gmail.com
            try:
                cursor.execute(
                    "UPDATE files SET user_email = 'xuanngocit@gmail.com' "
                    "WHERE user_email = 'default@user' OR user_email IS NULL;"
                )
            except Exception:
                pass

            self._seed_default_majors_and_subjects(cursor)
            conn.commit()

        logger.debug("Database initialized tại '%s'", self.db_path)

    def find_by_sha256(self, sha256: str, user_email: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Tìm bản ghi theo SHA-256 (có thể lọc theo user_email).

        Trả về bản ghi mới nhất hoặc bản ghi có trạng thái UPLOADED nếu có nhiều bản ghi trùng.
        """
        if user_email:
            clean_email = user_email.strip().lower()
            if clean_email == "xuanngocit@gmail.com":
                sql = """
                SELECT * FROM files
                WHERE sha256 = ? AND (LOWER(user_email) = ? OR user_email = 'default@user')
                ORDER BY CASE WHEN status IN (?, ?) THEN 0 ELSE 1 END, id DESC
                LIMIT 1;
                """
                params = (sha256, clean_email, STATUS_UPLOADED, STATUS_SAVED_LOCAL)
            else:
                sql = """
                SELECT * FROM files
                WHERE sha256 = ? AND LOWER(user_email) = ?
                ORDER BY CASE WHEN status IN (?, ?) THEN 0 ELSE 1 END, id DESC
                LIMIT 1;
                """
                params = (sha256, clean_email, STATUS_UPLOADED, STATUS_SAVED_LOCAL)
        else:
            sql = """
            SELECT * FROM files
            WHERE sha256 = ?
            ORDER BY CASE WHEN status IN (?, ?) THEN 0 ELSE 1 END, id DESC
            LIMIT 1;
            """
            params = (sha256, STATUS_UPLOADED, STATUS_SAVED_LOCAL)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def find_by_path(self, path: str, user_email: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Tìm bản ghi mới nhất theo đường dẫn file (có thể lọc theo user_email)."""
        if user_email:
            clean_email = user_email.strip().lower()
            if clean_email == "xuanngocit@gmail.com":
                sql = """
                SELECT * FROM files
                WHERE path = ? AND (LOWER(user_email) = ? OR user_email = 'default@user')
                ORDER BY CASE WHEN status IN (?, ?) THEN 0 ELSE 1 END, id DESC
                LIMIT 1;
                """
                params = (str(path), clean_email, STATUS_UPLOADED, STATUS_SAVED_LOCAL)
            else:
                sql = """
                SELECT * FROM files
                WHERE path = ? AND LOWER(user_email) = ?
                ORDER BY CASE WHEN status IN (?, ?) THEN 0 ELSE 1 END, id DESC
                LIMIT 1;
                """
                params = (str(path), clean_email, STATUS_UPLOADED, STATUS_SAVED_LOCAL)
        else:
            sql = """
            SELECT * FROM files
            WHERE path = ?
            ORDER BY CASE WHEN status IN (?, ?) THEN 0 ELSE 1 END, id DESC
            LIMIT 1;
            """
            params = (str(path), STATUS_UPLOADED, STATUS_SAVED_LOCAL)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def find_by_drive_file_id(self, drive_file_id: str, user_email: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Tìm bản ghi theo Google Drive File ID."""
        if user_email:
            clean_email = user_email.strip().lower()
            if clean_email == "xuanngocit@gmail.com":
                sql = "SELECT * FROM files WHERE drive_file_id = ? AND (LOWER(user_email) = ? OR user_email = 'default@user') ORDER BY id DESC LIMIT 1;"
            else:
                sql = "SELECT * FROM files WHERE drive_file_id = ? AND LOWER(user_email) = ? ORDER BY id DESC LIMIT 1;"
            params = (str(drive_file_id), clean_email)
        else:
            sql = "SELECT * FROM files WHERE drive_file_id = ? ORDER BY id DESC LIMIT 1;"
            params = (str(drive_file_id),)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
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
        user_email: str = "default@user",
    ) -> int:
        """Thêm bản ghi mới vào database.

        Returns:
            id của bản ghi vừa tạo.
        """
        if status not in VALID_STATUSES:
            raise ValueError(f"Trạng thái không hợp lệ: '{status}'. Hợp lệ gồm: {VALID_STATUSES}")

        now = current_iso_time()
        sql = """
        INSERT INTO files (user_email, sha256, path, subject, document_type, drive_file_id, status, error, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                sql,
                (
                    user_email,
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

    def get_all_records(self, limit: int = 100, user_email: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lấy danh sách các bản ghi mới nhất (có thể lọc theo user_email)."""
        if user_email:
            clean_email = user_email.strip().lower()
            if clean_email == "xuanngocit@gmail.com":
                sql = "SELECT * FROM files WHERE LOWER(user_email) = ? OR user_email = 'default@user' ORDER BY id DESC LIMIT ?;"
            else:
                sql = "SELECT * FROM files WHERE LOWER(user_email) = ? ORDER BY id DESC LIMIT ?;"
            params = (clean_email, limit)
        else:
            sql = "SELECT * FROM files ORDER BY id DESC LIMIT ?;"
            params = (limit,)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    # ==================== User Management (Multi-Tenant) ====================

    def get_or_create_user(
        self,
        email: str,
        name: str = "",
        avatar_url: str = "",
        local_folder: str = "",
    ) -> Dict[str, Any]:
        """Lấy thông tin người dùng theo email hoặc tạo mới nếu chưa có."""
        user = self.get_user_by_email(email)
        if user:
            if name or avatar_url or local_folder:
                now = current_iso_time()
                with self._get_connection() as conn:
                    conn.execute(
                        """
                        UPDATE users 
                        SET name = COALESCE(NULLIF(?, ''), name), 
                            avatar_url = COALESCE(NULLIF(?, ''), avatar_url),
                            local_folder = COALESCE(NULLIF(?, ''), local_folder),
                            updated_at = ? 
                        WHERE LOWER(email) = LOWER(?);
                        """,
                        (name, avatar_url, local_folder, now, email),
                    )
                    conn.commit()
            return self.get_user_by_email(email) or {}

        now = current_iso_time()
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO users (email, name, avatar_url, local_folder, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?);",
                (email.strip().lower(), name, avatar_url, local_folder, now, now),
            )
            conn.commit()
        return self.get_user_by_email(email) or {}

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Lấy thông tin người dùng theo email (không phân biệt hoa thường)."""
        sql = "SELECT * FROM users WHERE LOWER(email) = LOWER(?) LIMIT 1;"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (email,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def update_user_folder(self, email: str, local_folder: str) -> None:
        """Cập nhật đường dẫn thư mục máy tính cho người dùng."""
        now = current_iso_time()
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE users SET local_folder = ?, updated_at = ? WHERE email = ?;",
                (str(local_folder), now, email),
            )
            conn.commit()

    def update_user_tokens(
        self,
        email: str,
        access_token: str,
        refresh_token: Optional[str] = None,
        token_expiry: Optional[str] = None,
        drive_root_folder_id: Optional[str] = None,
    ) -> None:
        """Cập nhật OAuth tokens và Google Drive folder cho user."""
        now = current_iso_time()
        updates = ["access_token = ?", "updated_at = ?"]
        params: List[Any] = [access_token, now]

        if refresh_token:
            updates.append("refresh_token = ?")
            params.append(refresh_token)
        if token_expiry:
            updates.append("token_expiry = ?")
            params.append(token_expiry)
        if drive_root_folder_id:
            updates.append("drive_root_folder_id = ?")
            params.append(drive_root_folder_id)

        params.append(email)
        sql = f"UPDATE users SET {', '.join(updates)} WHERE email = ?;"
        with self._get_connection() as conn:
            conn.execute(sql, params)
            conn.commit()

    def get_all_users(self) -> List[Dict[str, Any]]:
        """Lấy danh sách tất cả người dùng trong hệ thống."""
        sql = "SELECT id, email, name, avatar_url, drive_root_folder_id, major_id, created_at, updated_at FROM users ORDER BY id DESC;"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    # ==================== Major & Subject Management ====================

    def _seed_default_majors_and_subjects(self, cursor: sqlite3.Cursor) -> None:
        """Khởi tạo 14 chuyên ngành Thạc sĩ chuẩn và các môn học mẫu nếu chưa có dữ liệu."""
        cursor.execute("SELECT COUNT(*) FROM majors;")
        if cursor.fetchone()[0] > 0:
            return

        now = current_iso_time()
        majors_data = [
            ("QLGD", "Quản lý giáo dục", "Quan_Ly_Giao_Duc", "Thạc sĩ Quản lý giáo dục", [
                ("QLTH", "Quản lý trường học", "Quan_Ly_Truong_Hoc", '["quan ly truong hoc", "giao duc"]'),
                ("DGGD", "Đánh giá trong giáo dục", "Danh_Gia_Trong_Giao_Duc", '["danh gia", "kiem dinh giao duc"]'),
            ]),
            ("QTKD", "Quản trị kinh doanh", "Quan_Tri_Kinh_Doanh", "Thạc sĩ Quản trị kinh doanh (MBA)", [
                ("MKT", "Marketing căn bản", "Marketing_Can_Ban", '["marketing", "mkt", "thi truong"]'),
                ("QTCL", "Quản trị chiến lược", "Quan_Tri_Chien_Luoc", '["chien luoc", "strategy", "quan tri"]'),
            ]),
            ("TCNH", "Tài chính ngân hàng", "Tai_Chinh_Ngan_Hang", "Thạc sĩ Tài chính - Ngân hàng", [
                ("TTTC", "Thị trường tài chính", "Thi_Truong_Tai_Chinh", '["tai chinh", "thi truong", "chung khoan"]'),
                ("QTNH", "Quản trị ngân hàng", "Quan_Tri_Ngan_Hang", '["ngan hang", "tin dung", "rui ro"]'),
            ]),
            ("KT", "Kế toán", "Ke_Toan", "Thạc sĩ Kế toán", [
                ("KTTC", "Kế toán tài chính nâng cao", "Ke_Toan_Tai_Chinh_Nang_Cao", '["ke toan", "bao cao tai chinh"]'),
                ("KTQT", "Kiểm toán nâng cao", "Kiem_Toan_Nang_Cao", '["kiem toan", "kiem soat noi bo"]'),
            ]),
            ("LKT", "Luật kinh tế", "Luat_Kinh_Te", "Thạc sĩ Luật kinh tế", [
                ("PLHD", "Pháp luật hợp đồng", "Phap_Luat_Hop_Dong", '["hop dong", "dan su", "thuong mai"]'),
                ("PLDN", "Pháp luật doanh nghiệp", "Phap_Luat_Doanh_Nghiep", '["doanh nghiep", "pha san", "dau tu"]'),
            ]),
            ("VH", "Văn học Việt Nam", "Van_Hoc_Viet_Nam", "Thạc sĩ Văn học Việt Nam", [
                ("LLVH", "Lý luận văn học", "Ly_Luan_Van_Hoc", '["ly luan", "phe binh van hoc"]'),
                ("VHD", "Văn học hiện đại", "Van_Hoc_Hien_Dai", '["van hoc", "tho ca", "truyen"]'),
            ]),
            ("NNA", "Ngôn ngữ Anh", "Ngon_Ngu_Anh", "Thạc sĩ Ngôn ngữ Anh", [
                ("NDH", "Ngữ dụng học", "Ngu_Dung_Hoc", '["pragmatics", "linguistics", "ngon ngu"]'),
                ("GDTA", "Phương pháp giảng dạy tiếng Anh", "Phuong_Phap_Giang_Day_Tieng_Anh", '["tesol", "tefl", "teaching"]'),
            ]),
            ("LSVN", "Lịch sử Việt Nam", "Lich_Su_Viet_Nam", "Thạc sĩ Lịch sử Việt Nam", [
                ("LSCD", "Lịch sử cận đại", "Lich_Su_Can_Dai", '["can dai", "lich su", "khang chien"]'),
                ("PPSH", "Phương pháp sử học", "Phuong_Phap_Su_Hoc", '["su hoc", "su lieu", "phuong phap"]'),
            ]),
            ("TLH", "Tâm lý học", "Tam_Ly_Hoc", "Thạc sĩ Tâm lý học", [
                ("TLPT", "Tâm lý học phát triển", "Tam_Ly_Hoc_Phat_Trien", '["phat trien", "lua tuoi", "tam ly"]'),
                ("TLXH", "Tâm lý học xã hội", "Tam_Ly_Hoc_Xa_Hoi", '["xa hoi", "hanh vi", "giao tiep"]'),
            ]),
            ("CTXH", "Công tác xã hội", "Cong_Tac_Xa_Hoi", "Thạc sĩ Công tác xã hội", [
                ("CTXHCN", "Công tác xã hội cá nhân", "Cong_Tac_Xa_Hoi_Ca_Nhan", '["tham van", "ca nhan", "ho tro"]'),
                ("PTCD", "Phát triển cộng đồng", "Phat_Trien_Cong_Dong", '["cong dong", "du an xa hoi"]'),
            ]),
            ("HH", "Hóa học", "Hoa_Hoc", "Thạc sĩ Hóa học", [
                ("HHHC", "Hóa học hữu cơ nâng cao", "Hoa_Hoc_Huu_Co_Nang_Cao", '["huu co", "tong hop hoa hoc"]'),
                ("HPT", "Hóa phân tích hiện đại", "Hoa_Phan_Tich_Hien_Dai", '["phan tich", "quang pho", "sac ky"]'),
            ]),
            ("KHMT", "Khoa học môi trường", "Khoa_Hoc_Moi_Truong", "Thạc sĩ Khoa học môi trường", [
                ("DTMT", "Đánh giá tác động môi trường", "Danh_Gia_Tac_Dong_Moi_Truong", '["dtm", "moi truong", "o nhiem"]'),
                ("QLTN", "Quản lý tài nguyên", "Quan_Ly_Tai_Nguyen", '["tai nguyen", "sinh thai", "ben vung"]'),
            ]),
            ("TH", "Toán học", "Toan_Hoc", "Thạc sĩ Toán học", [
                ("DSTT", "Đại số trừu tượng", "Dai_So_Truu_Tuong", '["dai so", "nhom", "vanh", "truong"]'),
                ("GTT", "Giải tích thực", "Giai_Tich_Thuc", '["giai tich", "do luong", "tich phan"]'),
            ]),
            ("HTTT", "Hệ thống thông tin", "He_Thong_Thong_Tin", "Thạc sĩ Hệ thống thông tin", [
                ("CSDL", "Cơ sở dữ liệu", "Co_So_Du_Lieu", '["csdl", "database", "sql", "co so du lieu"]'),
                ("TOAN_DS", "Toán khoa học dữ liệu", "Toan_Khoa_Hoc_Du_Lieu", '["toan", "data science", "xac suat", "thong ke", "khoa hoc du lieu"]'),
                ("TRIET", "Triết học", "Triet_Hoc", '["triet", "triet hoc", "mac lenin"]'),
                ("PPNC", "Phương pháp nghiên cứu", "Phuong_Phap_Nghien_Cuu", '["ppnc", "nghien cuu", "phuong phap"]'),
                ("NOTE", "Phương pháp ghi chú", "Phuong_Phap_Ghi_Chu", '["ghi chu", "zettelkasten", "note"]'),
            ]),
        ]

        for code, name, folder, desc, subs in majors_data:
            cursor.execute(
                """
                INSERT INTO majors (code, name, folder_name, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (code, name, folder, desc, now, now),
            )
            major_id = cursor.lastrowid
            for sub_code, sub_name, sub_folder, sub_kw in subs:
                cursor.execute(
                    """
                    INSERT INTO subjects (major_id, code, name, folder_name, keywords, is_default, created_by, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 1, 'admin', ?, ?);
                    """,
                    (major_id, sub_code, sub_name, sub_folder, sub_kw, now, now),
                )

    def get_all_majors(self) -> List[Dict[str, Any]]:
        """Lấy danh sách tất cả chuyên ngành."""
        sql = "SELECT * FROM majors ORDER BY id ASC;"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            return [dict(r) for r in cursor.fetchall()]

    def get_major_by_id(self, major_id: int) -> Optional[Dict[str, Any]]:
        """Lấy thông tin chuyên ngành theo ID."""
        sql = "SELECT * FROM majors WHERE id = ? LIMIT 1;"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (major_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_major_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """Lấy thông tin chuyên ngành theo mã code."""
        sql = "SELECT * FROM majors WHERE UPPER(code) = UPPER(?) LIMIT 1;"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (code.strip(),))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_subjects_by_major(self, major_id: int) -> List[Dict[str, Any]]:
        """Lấy danh sách các môn học thuộc chuyên ngành."""
        sql = "SELECT * FROM subjects WHERE major_id = ? ORDER BY id ASC;"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (major_id,))
            return [dict(r) for r in cursor.fetchall()]

    def add_major(self, code: str, name: str, folder_name: str, description: str = "") -> int:
        """Thêm một chuyên ngành mới (dành cho Admin)."""
        now = current_iso_time()
        sql = """
        INSERT INTO majors (code, name, folder_name, description, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?);
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (code.strip().upper(), name.strip(), folder_name.strip(), description.strip(), now, now))
            conn.commit()
            return cursor.lastrowid

    def add_subject(
        self,
        major_id: int,
        code: str,
        name: str,
        folder_name: str,
        keywords: str = "[]",
        is_default: int = 1,
        created_by: str = "admin",
    ) -> int:
        """Thêm môn học cho chuyên ngành."""
        now = current_iso_time()
        sql = """
        INSERT INTO subjects (major_id, code, name, folder_name, keywords, is_default, created_by, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                sql,
                (major_id, code.strip().upper(), name.strip(), folder_name.strip(), keywords, is_default, created_by, now, now),
            )
            conn.commit()
            return cursor.lastrowid

    def set_user_major(self, email: str, major_id: int) -> None:
        """Cập nhật chuyên ngành của người dùng (luồng Onboarding)."""
        now = current_iso_time()
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE users SET major_id = ?, updated_at = ? WHERE LOWER(email) = LOWER(?);",
                (major_id, now, email.strip()),
            )
            conn.commit()



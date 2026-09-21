"""Unit tests cho database.py."""

from pathlib import Path
import pytest

from src.database import (
    Database,
    STATUS_PENDING,
    STATUS_PROCESSING,
    STATUS_UPLOADED,
    STATUS_DUPLICATE,
    STATUS_ERROR,
)


@pytest.fixture
def db(tmp_path: Path) -> Database:
    db_file = tmp_path / "test_files.db"
    database = Database(db_path=db_file)
    database.initialize()
    return database


def test_database_initialization(db: Database) -> None:
    # Bảng và index phải tồn tại
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='files';")
        assert cursor.fetchone() is not None

        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_files_sha256';")
        assert cursor.fetchone() is not None

        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_files_status';")
        assert cursor.fetchone() is not None


def test_insert_and_get_record(db: Database) -> None:
    rec_id = db.insert_record(
        sha256="abc123hash",
        path="Triet_Hoc/02_Slide/Bai_01.pptx",
        subject="Triết học",
        document_type="Slide",
        status=STATUS_PENDING,
    )
    assert rec_id > 0

    record = db.get_record(rec_id)
    assert record is not None
    assert record["sha256"] == "abc123hash"
    assert record["path"] == "Triet_Hoc/02_Slide/Bai_01.pptx"
    assert record["subject"] == "Triết học"
    assert record["document_type"] == "Slide"
    assert record["status"] == STATUS_PENDING
    assert record["created_at"] is not None
    assert record["updated_at"] is not None


def test_find_by_sha256(db: Database) -> None:
    sha = "hash_find_me_456"
    assert db.find_by_sha256(sha) is None

    db.insert_record(
        sha256=sha,
        path="Co_So_Du_Lieu/01_Giao_Trinh/Book.pdf",
        subject="Cơ sở dữ liệu",
        document_type="Giáo trình",
        status=STATUS_UPLOADED,
        drive_file_id="drive_id_999",
    )

    found = db.find_by_sha256(sha)
    assert found is not None
    assert found["sha256"] == sha
    assert found["drive_file_id"] == "drive_id_999"
    assert found["status"] == STATUS_UPLOADED


def test_update_status(db: Database) -> None:
    rec_id = db.insert_record(
        sha256="hash_update_test",
        path="Triet_Hoc/02_Slide/Bai_02.pptx",
        subject="Triết học",
        document_type="Slide",
        status=STATUS_PENDING,
    )

    # Chuyển sang PROCESSING
    db.update_status(rec_id, status=STATUS_PROCESSING)
    record = db.get_record(rec_id)
    assert record["status"] == STATUS_PROCESSING

    # Chuyển sang UPLOADED kèm drive_file_id
    db.update_status(rec_id, status=STATUS_UPLOADED, drive_file_id="drive_file_abc")
    record = db.get_record(rec_id)
    assert record["status"] == STATUS_UPLOADED
    assert record["drive_file_id"] == "drive_file_abc"

    # Chuyển sang ERROR kèm error message
    db.update_status(rec_id, status=STATUS_ERROR, error="Network timeout")
    record = db.get_record(rec_id)
    assert record["status"] == STATUS_ERROR
    assert record["error"] == "Network timeout"


def test_dedup_same_hash_different_filename(db: Database) -> None:
    """Hai file tên khác nhau nhưng cùng nội dung (cùng SHA-256) -> phát hiện trùng."""
    common_sha = "shared_sha256_content"

    db.insert_record(
        sha256=common_sha,
        path="Triet_Hoc/02_Slide/Bai_01.pptx",
        subject="Triết học",
        document_type="Slide",
        status=STATUS_UPLOADED,
        drive_file_id="drive_111",
    )

    existing = db.find_by_sha256(common_sha)
    assert existing is not None
    assert existing["path"] == "Triet_Hoc/02_Slide/Bai_01.pptx"


def test_same_filename_different_hash(db: Database) -> None:
    """Cùng filename nhưng nội dung khác (khác SHA-256) -> xử lý như 2 file khác nhau."""
    sha_version_1 = "sha_v1_aaa"
    sha_version_2 = "sha_v2_bbb"
    filename = "Triet_Hoc/02_Slide/Bai_01.pptx"

    id1 = db.insert_record(
        sha256=sha_version_1,
        path=filename,
        subject="Triết học",
        document_type="Slide",
        status=STATUS_UPLOADED,
        drive_file_id="drive_v1",
    )

    id2 = db.insert_record(
        sha256=sha_version_2,
        path=filename,
        subject="Triết học",
        document_type="Slide",
        status=STATUS_UPLOADED,
        drive_file_id="drive_v2",
    )

    rec1 = db.get_record(id1)
    rec2 = db.get_record(id2)
    assert rec1["sha256"] != rec2["sha256"]
    assert rec1["drive_file_id"] == "drive_v1"
    assert rec2["drive_file_id"] == "drive_v2"


def test_invalid_status_raises(db: Database) -> None:
    with pytest.raises(ValueError) as exc:
        db.insert_record(
            sha256="test",
            path="path",
            subject="subject",
            document_type="type",
            status="INVALID_STATUS",
        )
    assert "Trạng thái không hợp lệ" in str(exc.value)


def test_majors_and_subjects_schema_and_seed(tmp_path: Path):
    from src.database import Database
    db = Database(tmp_path / "majors_test.db")
    db.initialize()

    majors = db.get_all_majors()
    assert len(majors) == 14
    major_names = [m["name"] for m in majors]
    assert "Hệ thống thông tin" in major_names
    assert "Quản trị kinh doanh" in major_names
    assert "Luật kinh tế" in major_names

    # Kiểm tra môn học mẫu của ngành Hệ thống thông tin
    httt = next(m for m in majors if m["code"] == "HTTT")
    subjects = db.get_subjects_by_major(httt["id"])
    assert len(subjects) >= 2
    sub_names = [s["name"] for s in subjects]
    assert "Cơ sở dữ liệu" in sub_names

    # Kiểm tra liên kết major_id trong users
    user = db.get_or_create_user("student@univ.edu", "Sinh Viên")
    assert user.get("major_id") is None
    db.set_user_major("student@univ.edu", httt["id"])
    updated_user = db.get_user_by_email("student@univ.edu")
    assert updated_user["major_id"] == httt["id"]


def test_database_session_lifecycle(tmp_path):
    """Kiểm tra tạo, truy vấn và xóa session người dùng trong SQLite."""
    db = Database(tmp_path / "test_session.db")
    db.initialize()

    db.get_or_create_user("learner@univ.edu", "Học viên A")
    session_token = "test_sess_tok_12345"

    # Tạo session
    db.create_session(session_token, "learner@univ.edu", expiry_days=7)

    # Truy vấn session hợp lệ
    user = db.get_session_user(session_token)
    assert user is not None
    assert user["email"] == "learner@univ.edu"
    assert user["name"] == "Học viên A"

    # Xóa session
    db.delete_session(session_token)
    assert db.get_session_user(session_token) is None

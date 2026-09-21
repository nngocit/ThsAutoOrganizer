"""Unit tests cho processor.py."""

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from src.classifier import PathClassifier
from src.database import Database, STATUS_UPLOADED, STATUS_DUPLICATE, STATUS_ERROR
from src.drive import CredentialsNotFoundError
from src.processor import FileProcessor, calculate_sha256, is_file_stable


@pytest.fixture
def setup_env(tmp_path: Path):
    root = tmp_path / "ThacSi_HTTT"
    root.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "files.db"

    classifier = PathClassifier(root_folder=root)
    database = Database(db_path=db_path)
    database.initialize()

    return root, classifier, database


def test_calculate_sha256(tmp_path: Path) -> None:
    f = tmp_path / "test.txt"
    f.write_text("Hello ThsAutoOrganizer", encoding="utf-8")
    h1 = calculate_sha256(f)
    assert len(h1) == 64
    assert h1 == calculate_sha256(f)


def test_is_file_stable(tmp_path: Path) -> None:
    f = tmp_path / "stable.txt"
    f.write_text("Content that is already written and closed.", encoding="utf-8")
    assert is_file_stable(f, wait_seconds=0.1, check_interval=0.05, max_wait_seconds=1.0) is True


def test_processor_happy_path(setup_env) -> None:
    root, classifier, database = setup_env

    file_dir = root / "Triet_Hoc" / "02_Slide"
    file_dir.mkdir(parents=True, exist_ok=True)
    file_path = file_dir / "Bai_05.txt"
    # Make sure size > min_file_size_bytes (default 100 for test)
    content = "Nội dung bài học Triết học slide 05. " * 50
    file_path.write_text(content, encoding="utf-8")

    mock_drive = MagicMock()
    mock_drive.resolve_folder_hierarchy.return_value = "folder_slide_123"
    mock_drive.upload_file.return_value = "drive_file_999"

    processor = FileProcessor(
        classifier=classifier,
        database=database,
        drive_manager=mock_drive,
        min_file_size_bytes=50,
    )

    result = processor.process_file(file_path)
    assert result.status == STATUS_UPLOADED
    assert result.drive_file_id == "drive_file_999"
    assert result.subject == "Triết học"
    assert result.document_type == "Slide"
    assert result.extracted_text_len > 0

    mock_drive.resolve_folder_hierarchy.assert_called_once_with(
        subject="Triết học",
        document_type="Slide",
    )
    mock_drive.upload_file.assert_called_once_with(
        file_path=file_path,
        parent_folder_id="folder_slide_123",
    )

    # Kiểm tra database đã lưu record UPLOADED
    rec = database.find_by_sha256(result.sha256)
    assert rec is not None
    assert rec["status"] == STATUS_UPLOADED
    assert rec["drive_file_id"] == "drive_file_999"


def test_processor_deduplication(setup_env) -> None:
    root, classifier, database = setup_env

    file_dir = root / "Triet_Hoc" / "02_Slide"
    file_dir.mkdir(parents=True, exist_ok=True)
    file_path = file_dir / "Bai_05.txt"
    file_path.write_text("Unique content for deduplication test. " * 30, encoding="utf-8")

    mock_drive = MagicMock()
    mock_drive.resolve_folder_hierarchy.return_value = "folder_1"
    mock_drive.upload_file.return_value = "drive_id_first"

    processor = FileProcessor(
        classifier=classifier,
        database=database,
        drive_manager=mock_drive,
        min_file_size_bytes=50,
    )

    # Xử lý lần đầu
    res1 = processor.process_file(file_path)
    assert res1.status == STATUS_UPLOADED
    assert mock_drive.upload_file.call_count == 1

    # Thả lại cùng file lần 2 -> phát hiện trùng SHA256 -> không upload
    res2 = processor.process_file(file_path)
    assert res2.status == STATUS_DUPLICATE
    assert res2.drive_file_id == "drive_id_first"
    # Số lần gọi upload vẫn chỉ là 1
    assert mock_drive.upload_file.call_count == 1


def test_processor_missing_credentials_graceful(setup_env) -> None:
    root, classifier, database = setup_env

    file_dir = root / "Co_So_Du_Lieu" / "01_Giao_Trinh"
    file_dir.mkdir(parents=True, exist_ok=True)
    file_path = file_dir / "Book.txt"
    file_path.write_text("Database curriculum content. " * 20, encoding="utf-8")

    mock_drive = MagicMock()
    mock_drive.resolve_folder_hierarchy.side_effect = CredentialsNotFoundError("No credentials.json")

    processor = FileProcessor(
        classifier=classifier,
        database=database,
        drive_manager=mock_drive,
        min_file_size_bytes=50,
    )

    # Không được crash
    result = processor.process_file(file_path)
    assert result.status == STATUS_ERROR
    assert "No credentials.json" in str(result.error)

    # Database ghi nhận lỗi an toàn
    rec = database.find_by_sha256(result.sha256)
    assert rec is not None
    assert rec["status"] == STATUS_ERROR

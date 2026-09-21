"""Integration / End-to-End simulation test cho toàn bộ pipeline."""

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from src.classifier import PathClassifier
from src.database import (
    Database,
    STATUS_UPLOADED,
    STATUS_DUPLICATE,
)
from src.processor import FileProcessor


def test_end_to_end_simulation(tmp_path: Path) -> None:
    source_root = tmp_path / "ThacSi_HTTT"
    source_root.mkdir(parents=True, exist_ok=True)
    db_file = tmp_path / "data" / "files.db"

    classifier = PathClassifier(root_folder=source_root)
    database = Database(db_path=db_file)
    database.initialize()

    # Mock Drive
    mock_drive = MagicMock()
    mock_drive.resolve_folder_hierarchy.side_effect = lambda subject, document_type: f"folder_{subject}_{document_type}"
    mock_drive.upload_file.side_effect = lambda file_path, parent_folder_id: f"drive_{Path(file_path).stem}"

    processor = FileProcessor(
        classifier=classifier,
        database=database,
        drive_manager=mock_drive,
        min_file_size_bytes=10,
    )

    # 1. Tạo file 1: Triet_Hoc/02_Slide/Bai_05.pptx (tạo bằng python-pptx thật)
    from pptx import Presentation
    slide_dir = source_root / "Triet_Hoc" / "02_Slide"
    slide_dir.mkdir(parents=True, exist_ok=True)
    pptx_file = slide_dir / "Bai_05.pptx"

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = "Bài 05: Triết học và vai trò xã hội"
    prs.save(str(pptx_file))

    # Xử lý file 1
    res1 = processor.process_file(pptx_file)
    assert res1.status == STATUS_UPLOADED
    assert res1.subject == "Triết học"
    assert res1.document_type == "Slide"
    assert res1.drive_file_id == "drive_Bai_05"

    # Kiểm tra record trong SQLite
    db_rec1 = database.find_by_sha256(res1.sha256)
    assert db_rec1 is not None
    assert db_rec1["status"] == STATUS_UPLOADED
    assert db_rec1["drive_file_id"] == "drive_Bai_05"

    # 2. Thử copy lại file đó (cùng nội dung) -> Kiểm tra tính năng chống trùng SHA-256
    res_dup = processor.process_file(pptx_file)
    assert res_dup.status == STATUS_DUPLICATE
    assert res_dup.drive_file_id == "drive_Bai_05"

    # 3. Tạo file 2: Cùng tên Bai_05.pptx nhưng ở môn khác Co_So_Du_Lieu/02_Slide với nội dung khác
    csdl_slide_dir = source_root / "Co_So_Du_Lieu" / "02_Slide"
    csdl_slide_dir.mkdir(parents=True, exist_ok=True)
    csdl_pptx_file = csdl_slide_dir / "Bai_05.pptx"

    prs2 = Presentation()
    slide2 = prs2.slides.add_slide(prs2.slide_layouts[0])
    slide2.shapes.title.text = "Bài 05: Tối ưu hóa câu truy vấn SQL"
    prs2.save(str(csdl_pptx_file))

    res2 = processor.process_file(csdl_pptx_file)
    assert res2.status == STATUS_UPLOADED
    assert res2.subject == "Cơ sở dữ liệu"
    assert res2.document_type == "Slide"
    assert res2.sha256 != res1.sha256  # Khác hash mặc dù trùng tên file Bai_05.pptx

    # Tổng số file UPLOADED là 2
    all_recs = database.get_all_records()
    uploaded_recs = [r for r in all_recs if r["status"] == STATUS_UPLOADED]
    assert len(uploaded_recs) == 2

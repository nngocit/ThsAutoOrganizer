"""Unit tests cho classifier.py."""

from pathlib import Path
import pytest

from src.classifier import (
    PathClassifier,
    InvalidPathStructureError,
    UnknownSubjectError,
    UnknownDocumentTypeError,
)


@pytest.fixture
def classifier(tmp_path: Path) -> PathClassifier:
    root = tmp_path / "ThacSi_HTTT"
    root.mkdir(parents=True, exist_ok=True)
    return PathClassifier(root_folder=root)


def test_classify_triet_hoc_giao_trinh(classifier: PathClassifier) -> None:
    file_path = classifier.root_folder / "Triet_Hoc" / "01_Giao_Trinh" / "Giao_Trinh_Triet.pdf"
    result = classifier.classify(file_path)
    assert result.subject == "Triết học"
    assert result.document_type == "Giáo trình"
    assert result.subject_raw == "Triet_Hoc"
    assert result.document_type_raw == "01_Giao_Trinh"


def test_classify_triet_hoc_slide(classifier: PathClassifier) -> None:
    file_path = classifier.root_folder / "Triet_Hoc" / "02_Slide" / "Bai_05.pptx"
    result = classifier.classify(file_path)
    assert result.subject == "Triết học"
    assert result.document_type == "Slide"


def test_classify_co_so_du_lieu_tai_lieu_tham_khao(classifier: PathClassifier) -> None:
    file_path = classifier.root_folder / "Co_So_Du_Lieu" / "03_Tai_Lieu_Tham_Khao" / "Paper.pdf"
    result = classifier.classify(file_path)
    assert result.subject == "Cơ sở dữ liệu"
    assert result.document_type == "Tài liệu tham khảo"


def test_classify_phuong_phap_nghien_cuu_on_thi(classifier: PathClassifier) -> None:
    file_path = classifier.root_folder / "Phuong_Phap_Nghien_Cuu" / "04_On_Thi" / "De_Cuong.docx"
    result = classifier.classify(file_path)
    assert result.subject == "Phương pháp nghiên cứu"
    assert result.document_type == "Ôn thi"


def test_classify_nested_subfolder(classifier: PathClassifier) -> None:
    # Trường hợp có thư mục con bên trong 02_Slide
    file_path = classifier.root_folder / "Triet_Hoc" / "02_Slide" / "Part1" / "Bai_01.pptx"
    result = classifier.classify(file_path)
    assert result.subject == "Triết học"
    assert result.document_type == "Slide"


def test_classify_outside_root(classifier: PathClassifier, tmp_path: Path) -> None:
    outside_file = tmp_path / "OtherDir" / "Triet_Hoc" / "01_Giao_Trinh" / "File.pdf"
    with pytest.raises(InvalidPathStructureError) as exc_info:
        classifier.classify(outside_file)
    assert "không nằm trong root_folder" in str(exc_info.value)


def test_classify_insufficient_depth(classifier: PathClassifier) -> None:
    # File ngay tại root
    file_root = classifier.root_folder / "File_At_Root.pdf"
    with pytest.raises(InvalidPathStructureError):
        classifier.classify(file_root)

    # File ngay trong thư mục môn nhưng không có loại
    file_subject_only = classifier.root_folder / "Triet_Hoc" / "File.pdf"
    with pytest.raises(InvalidPathStructureError):
        classifier.classify(file_subject_only)


def test_classify_unknown_subject(classifier: PathClassifier) -> None:
    file_path = classifier.root_folder / "Mon_Moi_Chua_Khai_Bao" / "01_Giao_Trinh" / "File.pdf"
    with pytest.raises(UnknownSubjectError) as exc_info:
        classifier.classify(file_path)
    assert "chưa được định nghĩa" in str(exc_info.value)


def test_classify_unknown_document_type(classifier: PathClassifier) -> None:
    file_path = classifier.root_folder / "Triet_Hoc" / "99_Khac" / "File.pdf"
    with pytest.raises(UnknownDocumentTypeError) as exc_info:
        classifier.classify(file_path)
    assert "chưa được định nghĩa" in str(exc_info.value)


def test_register_new_subject_and_type(classifier: PathClassifier) -> None:
    classifier.register_subject("Kien_Truc_Doanh_Nghiep", "Kiến trúc doanh nghiệp")
    classifier.register_type("05_Bai_Tap_Lon", "Bài tập lớn")

    file_path = classifier.root_folder / "Kien_Truc_Doanh_Nghiep" / "05_Bai_Tap_Lon" / "Bao_Cao.docx"
    result = classifier.classify(file_path)
    assert result.subject == "Kiến trúc doanh nghiệp"
    assert result.document_type == "Bài tập lớn"

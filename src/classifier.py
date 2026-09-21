"""Module phân loại Môn học và Loại tài liệu dựa trên cấu trúc thư mục.

Không suy đoán tự động nếu thư mục đã định rõ.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


class ClassifierError(Exception):
    """Lỗi chung của bộ phân loại."""
    pass


class InvalidPathStructureError(ClassifierError):
    """Cấu trúc đường dẫn không hợp lệ so với root folder."""
    pass


class UnknownSubjectError(ClassifierError):
    """Môn học không xác định trong SUBJECT_MAP."""
    pass


class UnknownDocumentTypeError(ClassifierError):
    """Loại tài liệu không xác định trong TYPE_MAP."""
    pass


# Mapping mặc định theo đặc tả
DEFAULT_SUBJECT_MAP: Dict[str, str] = {
    "Triet_Hoc": "Triết học",
    "Co_So_Du_Lieu": "Cơ sở dữ liệu",
    "Phuong_Phap_Nghien_Cuu": "Phương pháp nghiên cứu",
}

DEFAULT_TYPE_MAP: Dict[str, str] = {
    "01_Giao_Trinh": "Giáo trình",
    "02_Slide": "Slide",
    "03_Tai_Lieu_Tham_Khao": "Tài liệu tham khảo",
    "04_On_Thi": "Ôn thi",
}


@dataclass(frozen=True)
class ClassificationResult:
    """Kết quả phân loại tài liệu."""
    subject: str               # Tên môn tiếng Việt (vd: 'Triết học')
    document_type: str         # Tên loại tiếng Việt (vd: 'Slide')
    subject_raw: str           # Thư mục môn gốc (vd: 'Triet_Hoc')
    document_type_raw: str     # Thư mục loại gốc (vd: '02_Slide')
    relative_path: str         # Đường dẫn tương đối từ root


class PathClassifier:
    """Bộ phân loại dựa trên cấu trúc đường dẫn thư mục."""

    def __init__(
        self,
        root_folder: Path | str,
        subject_map: Optional[Dict[str, str]] = None,
        type_map: Optional[Dict[str, str]] = None,
    ) -> None:
        self.root_folder = Path(root_folder).resolve()
        self.subject_map = dict(DEFAULT_SUBJECT_MAP if subject_map is None else subject_map)
        self.type_map = dict(DEFAULT_TYPE_MAP if type_map is None else type_map)

    def register_subject(self, folder_key: str, display_name: str) -> None:
        """Đăng ký thêm môn học mới một cách dễ dàng."""
        self.subject_map[folder_key] = display_name

    def register_type(self, folder_key: str, display_name: str) -> None:
        """Đăng ký thêm loại tài liệu mới một cách dễ dàng."""
        self.type_map[folder_key] = display_name

    def classify(self, file_path: Path | str) -> ClassificationResult:
        """Phân loại môn học và loại tài liệu từ file_path.

        Đường dẫn mong đợi có dạng:
            <root_folder>/<subject_folder>/<type_folder>/<file_name>
        hoặc sâu hơn trong subfolder của <type_folder>.

        Args:
            file_path: Đường dẫn đầy đủ hoặc tương đối của file cần phân loại.

        Returns:
            ClassificationResult chứa thông tin môn học và loại tài liệu.

        Raises:
            InvalidPathStructureError: Nếu file không nằm trong root hoặc thiếu cấp thư mục.
            UnknownSubjectError: Nếu thư mục môn học không có trong subject_map.
            UnknownDocumentTypeError: Nếu thư mục loại tài liệu không có trong type_map.
        """
        resolved_file = Path(file_path).resolve()

        try:
            rel_path = resolved_file.relative_to(self.root_folder)
        except ValueError as exc:
            raise InvalidPathStructureError(
                f"File '{resolved_file}' không nằm trong root_folder '{self.root_folder}'."
            ) from exc

        parts = rel_path.parts
        # parts tối thiểu phải là: (subject, document_type, filename)
        if len(parts) < 3:
            raise InvalidPathStructureError(
                f"Đường dẫn '{rel_path}' không đủ cấp thư mục chuẩn: "
                f"<Mon_Hoc>/<Loai_Tai_Lieu>/<File>. Số cấp hiện tại: {len(parts)}"
            )

        subject_raw = parts[0]
        type_raw = parts[1]

        if subject_raw not in self.subject_map:
            valid_subjects = ", ".join(self.subject_map.keys())
            raise UnknownSubjectError(
                f"Thư mục môn '{subject_raw}' chưa được định nghĩa. Các môn hợp lệ: [{valid_subjects}]"
            )

        if type_raw not in self.type_map:
            valid_types = ", ".join(self.type_map.keys())
            raise UnknownDocumentTypeError(
                f"Thư mục loại '{type_raw}' chưa được định nghĩa. Các loại hợp lệ: [{valid_types}]"
            )

        return ClassificationResult(
            subject=self.subject_map[subject_raw],
            document_type=self.type_map[type_raw],
            subject_raw=subject_raw,
            document_type_raw=type_raw,
            relative_path=str(rel_path).replace("\\", "/"),
        )

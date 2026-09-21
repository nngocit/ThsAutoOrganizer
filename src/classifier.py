"""Module phân loại Môn học và Loại tài liệu dựa trên cấu trúc thư mục.

Hỗ trợ cả cấu trúc chuẩn 3 cấp:
    <root>/<Mon_Hoc>/<Loai_Tai_Lieu>/<File>
và cấu trúc 2 cấp (khi người dùng để file trực tiếp trong thư mục môn):
    <root>/<Mon_Hoc>/<File>
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


# Mapping mặc định theo đặc tả + mở rộng tên thư mục có dấu cách
DEFAULT_SUBJECT_MAP: Dict[str, str] = {
    # Cấu trúc gạch dưới
    "Triet_Hoc": "Triết học",
    "Co_So_Du_Lieu": "Cơ sở dữ liệu",
    "Phuong_Phap_Nghien_Cuu": "Phương pháp nghiên cứu",
    "Toan_Khoa_Hoc_Du_Lieu": "Toán khoa học dữ liệu",
    "Phuong_Phap_Ghi_Chu": "Phương pháp ghi chú",
    # Cấu trúc dấu cách thực tế trên Windows
    "Triet Hoc": "Triết học",
    "Co So Du Lieu": "Cơ sở dữ liệu",
    "Phuong Phap Nghien Cuu": "Phương pháp nghiên cứu",
    "Toan Khoa Hoc Du Lieu": "Toán khoa học dữ liệu",
    "Phuong Phap Ghi Chu": "Phương pháp ghi chú",
}

DEFAULT_TYPE_MAP: Dict[str, str] = {
    "01_Giao_Trinh": "Giáo trình",
    "02_Slide": "Slide",
    "03_Tai_Lieu_Tham_Khao": "Tài liệu tham khảo",
    "04_On_Thi": "Ôn thi",
    "Giao_Trinh": "Giáo trình",
    "Giao Trinh": "Giáo trình",
    "Slide": "Slide",
    "Tai_Lieu_Tham_Khao": "Tài liệu tham khảo",
    "Tai Lieu Tham Khao": "Tài liệu tham khảo",
    "On_Thi": "Ôn thi",
    "On Thi": "Ôn thi",
    "Tai_Lieu_Chung": "Tài liệu chung",
    "Tai Lieu Chung": "Tài liệu chung",
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
        allow_direct_subject_files: bool = False,
    ) -> None:
        self.root_folder = Path(root_folder).resolve()
        self.subject_map = dict(DEFAULT_SUBJECT_MAP if subject_map is None else subject_map)
        self.type_map = dict(DEFAULT_TYPE_MAP if type_map is None else type_map)
        self.allow_direct_subject_files = allow_direct_subject_files

    def register_subject(self, folder_key: str, display_name: str) -> None:
        """Đăng ký thêm môn học mới một cách dễ dàng."""
        self.subject_map[folder_key] = display_name

    def register_type(self, folder_key: str, display_name: str) -> None:
        """Đăng ký thêm loại tài liệu mới một cách dễ dàng."""
        self.type_map[folder_key] = display_name

    def classify(self, file_path: Path | str) -> ClassificationResult:
        """Phân loại môn học và loại tài liệu từ file_path.

        Args:
            file_path: Đường dẫn đầy đủ hoặc tương đối của file cần phân loại.

        Returns:
            ClassificationResult chứa thông tin môn học và loại tài liệu.
        """
        resolved_file = Path(file_path).resolve()

        try:
            rel_path = resolved_file.relative_to(self.root_folder)
        except ValueError as exc:
            raise InvalidPathStructureError(
                f"File '{resolved_file}' không nằm trong root_folder '{self.root_folder}'."
            ) from exc

        parts = rel_path.parts

        # Ít nhất phải nằm trong 1 thư mục môn
        if len(parts) < 2:
            raise InvalidPathStructureError(
                f"File '{rel_path}' nằm ngay tại thư mục gốc, không thuộc thư mục môn học nào."
            )

        subject_raw = parts[0]
        if subject_raw not in self.subject_map:
            valid_subjects = ", ".join(self.subject_map.keys())
            raise UnknownSubjectError(
                f"Thư mục môn '{subject_raw}' chưa được định nghĩa. Các môn hợp lệ: [{valid_subjects}]"
            )

        subject = self.subject_map[subject_raw]

        if len(parts) == 2:
            # File nằm trực tiếp trong thư mục môn
            if not self.allow_direct_subject_files:
                raise InvalidPathStructureError(
                    f"Đường dẫn '{rel_path}' không đủ cấp thư mục chuẩn: "
                    f"<Mon_Hoc>/<Loai_Tai_Lieu>/<File>. Số cấp hiện tại: {len(parts)}"
                )

            filename_lower = parts[1].lower()
            if any(k in filename_lower for k in ["giao-trinh", "giao_trinh", "giaotrinh", "textbook"]):
                type_raw = "01_Giao_Trinh"
                doc_type = "Giáo trình"
            elif any(k in filename_lower for k in ["slide", "bai_giang", "baigiang", "lecture"]):
                type_raw = "02_Slide"
                doc_type = "Slide"
            elif any(k in filename_lower for k in ["on", "de_cuong", "decuong", "thi", "exam", "thao luan"]):
                type_raw = "04_On_Thi"
                doc_type = "Ôn thi"
            else:
                type_raw = "03_Tai_Lieu_Tham_Khao"
                doc_type = "Tài liệu tham khảo"

            return ClassificationResult(
                subject=subject,
                document_type=doc_type,
                subject_raw=subject_raw,
                document_type_raw=type_raw,
                relative_path=str(rel_path).replace("\\", "/"),
            )

        # len(parts) >= 3: có thư mục loại tài liệu
        type_raw = parts[1]
        if type_raw not in self.type_map:
            valid_types = ", ".join(self.type_map.keys())
            raise UnknownDocumentTypeError(
                f"Thư mục loại '{type_raw}' chưa được định nghĩa. Các loại hợp lệ: [{valid_types}]"
            )

        return ClassificationResult(
            subject=subject,
            document_type=self.type_map[type_raw],
            subject_raw=subject_raw,
            document_type_raw=type_raw,
            relative_path=str(rel_path).replace("\\", "/"),
        )

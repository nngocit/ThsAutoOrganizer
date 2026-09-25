# local_agent/config_loader.py — Load và validate config.json (<80 lines)

import json
import os
from pathlib import Path
from typing import Any

# Mặc định — sẽ bị ghi đè bởi config.json
_DEFAULTS: dict[str, Any] = {
    "worker_url": "https://ths-organizer-api.ths-organizer-nngocit.workers.dev",
    # KHÔNG có default cho secret — bắt buộc phải có trong config.json hoặc env AGENT_SECRET
    "agent_secret": "",
    "poll_interval_seconds": 10,
    "task_queue_limit": 10,
    "local_base_path": str(Path.home() / "2026" / "Thac Sy" / "Mon_Hoc"),
    "drive_archive_folder": "_Archive_Trash_90Days",
    "log_level": "INFO",
}

_CONFIG_FILE = Path(__file__).parent.parent / "config.json"
_config: dict[str, Any] | None = None


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    """
    Load cấu hình từ config.json, merge với defaults.
    
    Args:
        config_path: Đường dẫn tới file config. Mặc định là repo root / config.json.
    
    Returns:
        dict với toàn bộ cấu hình đã merge.
    
    Raises:
        FileNotFoundError: Nếu config.json không tồn tại.
        json.JSONDecodeError: Nếu JSON không hợp lệ.
    """
    global _config
    path = config_path or _CONFIG_FILE

    if not path.exists():
        raise FileNotFoundError(f"Config không tìm thấy: {path}")

    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    # Merge: defaults → raw config
    merged = {**_DEFAULTS, **raw}

    # Aliases 2 chiều cho local path: 'local_base_path' <-> 'root_folder'
    local_path = raw.get("local_base_path") or raw.get("root_folder") or _DEFAULTS.get("local_base_path")
    if local_path:
        merged["local_base_path"] = local_path
        merged["root_folder"] = local_path

    # Aliases 2 chiều cho drive root: 'google_drive_root_folder_id' <-> 'drive_root_folder'
    drive_root = raw.get("google_drive_root_folder_id") or raw.get("drive_root_folder") or _DEFAULTS.get("google_drive_root_folder_id")
    if drive_root:
        merged["google_drive_root_folder_id"] = drive_root
        merged["drive_root_folder"] = drive_root

    # Ghi đè từ environment variables (ưu tiên cao nhất)
    if os.environ.get("WORKER_URL"):
        merged["worker_url"] = os.environ["WORKER_URL"]
    if os.environ.get("AGENT_SECRET"):
        merged["agent_secret"] = os.environ["AGENT_SECRET"]
    env_local = os.environ.get("LOCAL_BASE_PATH") or os.environ.get("ROOT_FOLDER")
    if env_local:
        merged["local_base_path"] = env_local
        merged["root_folder"] = env_local
    env_drive = os.environ.get("GOOGLE_DRIVE_ROOT_FOLDER_ID") or os.environ.get("DRIVE_ROOT_FOLDER")
    if env_drive:
        merged["google_drive_root_folder_id"] = env_drive
        merged["drive_root_folder"] = env_drive

    _config = merged
    return merged


def get_config() -> dict[str, Any]:
    """Lấy config đã load. Load nếu chưa có."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def get(key: str, default: Any = None) -> Any:
    """Lấy một giá trị cấu hình theo key."""
    return get_config().get(key, default)


def sync_remote_config(uid: str = "") -> dict[str, Any]:
    """Kéo cấu hình từ Worker API (Firestore system_config) và merge vào runtime config."""
    global _config
    cfg = get_config()
    try:
        from . import api_client
        res = api_client.get_system_config(uid=uid)
        remote_cfg = res.get("config", {})
        if remote_cfg:
            # Ghi đè các key cấu hình quan trọng từ Cloud
            for k in ("local_base_path", "root_folder", "google_drive_root_folder_id", "drive_root_folder",
                      "google_drive_root_name", "file_watcher_enabled", "auto_sync_nlm", "poll_interval_seconds"):
                if k in remote_cfg and remote_cfg[k] is not None:
                    cfg[k] = remote_cfg[k]

            # Đồng bộ hai chiều cho alias sau khi nhận remote
            if "local_base_path" in remote_cfg and remote_cfg["local_base_path"]:
                cfg["root_folder"] = remote_cfg["local_base_path"]
            elif "root_folder" in remote_cfg and remote_cfg["root_folder"]:
                cfg["local_base_path"] = remote_cfg["root_folder"]

            if "google_drive_root_folder_id" in remote_cfg and remote_cfg["google_drive_root_folder_id"]:
                cfg["drive_root_folder"] = remote_cfg["google_drive_root_folder_id"]
            elif "drive_root_folder" in remote_cfg and remote_cfg["drive_root_folder"]:
                cfg["google_drive_root_folder_id"] = remote_cfg["drive_root_folder"]

            _config = cfg
            return cfg
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug("sync_remote_config không thành công (dùng local fallback): %s", e)
    return cfg


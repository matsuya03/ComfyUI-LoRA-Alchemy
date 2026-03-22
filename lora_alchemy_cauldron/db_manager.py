import os
import stat
import json
from pathlib import Path
from typing import Optional, List
from filelock import FileLock
from .schemas import DatabaseSchema, LoRAEntry

# Determine the directory where db_manager.py is located
BASE_DIR = Path(__file__).parent.resolve()
DB_FILE_PATH = BASE_DIR / "lora_db.json"

class LoRADatabase:
    def __init__(self, db_path: Path = DB_FILE_PATH):
        self.db_path = db_path
        self._lock_path = self.db_path.with_suffix('.json.lock')
        self._schema = self._load()

    def _load(self) -> DatabaseSchema:
        if not self.db_path.exists():
            return DatabaseSchema(loras=[])
        
        try:
            with FileLock(self._lock_path, timeout=5):
                with open(self.db_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return DatabaseSchema.model_validate(data)
        except (json.JSONDecodeError, ValueError) as e:
            # 不正なファイルの場合は空のスキーマを返しつつ警告を出力するなど、必要に応じて拡張
            print(f"Warning: Failed to parse {self.db_path}: {e}")
            return DatabaseSchema(loras=[])

    def save(self):
        """現在のスキーマ状態をファイルに保存します。"""
        try:
            with FileLock(self._lock_path, timeout=5):
                with open(self.db_path, "w", encoding="utf-8") as f:
                    js = self._schema.model_dump_json(indent=2)
                    f.write(js)
            
                # Unix系でパーミッション制御 (600: owner only)
                if hasattr(os, 'chmod'):
                    try:
                        os.chmod(self.db_path, stat.S_IRUSR | stat.S_IWUSR)
                    except Exception:
                        pass
        except Exception as e:
            print(f"Failed to acquire lock or save DB: {e}")

    def get_lora(self, lora_id: str) -> Optional[LoRAEntry]:
        for lora in self._schema.loras:
            if lora.lora_id == lora_id:
                return lora
        return None

    def upsert_lora(self, entry: LoRAEntry):
        """LoRAエントリを追加、または既存のIDがあれば更新します"""
        existing = self.get_lora(entry.lora_id)
        if existing is not None:
            # 既存エントリのインデックスを探して置換
            idx = self._schema.loras.index(existing)
            self._schema.loras[idx] = entry
        else:
            self._schema.loras.append(entry)
        self.save()

    def delete_lora(self, lora_id: str) -> bool:
        """指定されたIDのLoRAを削除します（削除成功時はTrueを返却）"""
        existing = self.get_lora(lora_id)
        if existing is not None:
            self._schema.loras.remove(existing)
            self.save()
            return True
        return False

    def get_all(self) -> List[LoRAEntry]:
        return self._schema.loras

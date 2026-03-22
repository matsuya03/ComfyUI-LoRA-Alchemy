"""
LoRA ファイルの一意 ID（ハッシュ）を計算するユーティリティ。
worker.py（バックエンド）と nodes.py（ComfyUI ノード）で統一のため、
この関数を共通で使用する。
"""

import hashlib
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

def compute_lora_id(file_path: Path, method: str = "fast", chunk_size_mb: int = 1) -> str:
    """
    LoRA ファイルの内容に基づいて一意な ID を生成する。
    
    Args:
        file_path: LoRA ファイルのパス
        method: ハッシュ計算方法
            - "full": ファイル全体をハッシュ（確実だが大容量ファイルは遅い）
            - "fast": 先頭 N MB のみハッシュ（推奨、高速、大容量ファイル向け）
        chunk_size_mb: "fast" 方式の場合のチャンクサイズ（MB）
    
    Returns:
        "{file_stem}_{hash_prefix}" 形式のロード ID
        例: "model_a1b2c3d4"
    """
    if not file_path.exists():
        raise FileNotFoundError(f"LoRA file not found: {file_path}")
    
    try:
        if method == "full":
            # ファイル全体をハッシュ（最も確実）
            with open(file_path, "rb") as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()
            logger.debug(f"Computed FULL hash for {file_path.name}: {file_hash[:8]}")
            
        elif method == "fast":
            # 先頭 N MB のみハッシュ（大きなファイルの場合）
            chunk_bytes = int(chunk_size_mb * 1024 * 1024)
            file_size = os.path.getsize(file_path)
            with open(file_path, "rb") as f:
                chunk = f.read(chunk_bytes)
                # ファイルサイズも含めることで、同じ先頭1MBでもサイズが違う場合は別IDになる
                hasher = hashlib.sha256(chunk)
                hasher.update(str(file_size).encode('utf-8'))
                file_hash = hasher.hexdigest()
            logger.debug(f"Computed FAST hash for {file_path.name} (size: {file_size}): {file_hash[:8]}")
            
        else:
            raise ValueError(f"Unknown hash method: {method}")
        
        lora_id = f"{file_path.stem}_{file_hash[:8]}"
        return lora_id
        
    except Exception as e:
        logger.error(f"Error computing hash for {file_path}: {e}")
        raise


def compute_lora_id_safe(file_path: Path, method: str = "fast", fallback_to_stem: bool = True) -> Optional[str]:
    """
    compute_lora_id の安全版。例外を握りつぶし、失敗時にはファイル名のみを返す。
    
    Args:
        file_path: LoRA ファイルのパス
        method: ハッシュ計算方法
        fallback_to_stem: 失敗時にファイル名（拡張子なし）をIDとして返すか
    
    Returns:
        ロード ID、またはエラー時は None（fallback_to_stem=False の場合）
    """
    try:
        return compute_lora_id(file_path, method=method)
    except Exception as e:
        logger.warning(f"Failed to compute hash for {file_path}, fallback to stem: {e}")
        if fallback_to_stem:
            return file_path.stem
        return None

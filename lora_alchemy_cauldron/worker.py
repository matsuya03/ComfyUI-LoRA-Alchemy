import time
import os
import logging
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .schemas import LoRAEntry, LoRAMetadata, CompatibilityRules, UserOverride, Role
from .db_manager import LoRADatabase
from .metadata_extractor import MetadataExtractor
from .role_classifier import RoleClassifier
from .hash_utils import compute_lora_id_safe
from .logger_setup import setup_logging

# ログ設定の初期化
setup_logging()
logger = logging.getLogger(__name__)

db = LoRADatabase()
extractor = MetadataExtractor()
classifier = RoleClassifier()

def process_new_lora(file_path: Path, hf_model_id: str = "") -> Optional[str]:
    """
    新規のLoRAファイル(.safetensors)が検出された際に呼び出され、
    メタデータ抽出、Role分類、DB保存の一連のフローを実行する。
    
    Args:
        file_path: LoRA ファイルのパス
        hf_model_id: HuggingFace モデル ID（オプション）
    
    Returns:
        成功時は lora_id、失敗時は None
    """
    try:
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return None
            
        # 1. LoRA ID 計算
        lora_id = compute_lora_id_safe(file_path, fallback_to_stem=True)
        if not lora_id:
            logger.error(f"Failed to compute LoRA ID: {file_path}")
            return None

        logger.info(f"Processing new LoRA: {lora_id} ({file_path.name})")

        # 2. ユーザーロックの確認（既存エントリが locked 状態なら処理をスキップ）
        existing = db.get_lora(lora_id)
        if existing and existing.user_override.is_locked:
            logger.info(f"LoRA '{lora_id}' is locked by user. Skipping auto-update.")
            return lora_id

        # 3. メタデータ抽出
        try:
            metadata_dict = extractor.extract(str(file_path), hf_model_id=hf_model_id)
            logger.debug(f"Extracted metadata: tags={len(metadata_dict.get('tags', []))}, triggers={len(metadata_dict.get('trigger_words', []))}")
        except Exception as e:
            logger.warning(f"Error extracting metadata for {file_path.name}: {e}")
            metadata_dict = {"tags": [], "trigger_words": [], "description": "", "base_model": "SDXL"}
            
        detected_base_model = metadata_dict.get("base_model", "SDXL")

        # 4. Role 分類
        try:
            classification = classifier.classify(
                file_path=str(file_path),
                file_name=file_path.stem,
                metadata=metadata_dict
            )
            logger.info(
                f"Classified as {classification.primary_role.value} "
                f"(Confidence: {classification.confidence:.2f}, Level: {classification.classification_level})"
            )
            
            if classification.warnings:
                for w in classification.warnings:
                    logger.warning(f"  {w}")
        except Exception as e:
            logger.error(f"Error during classification for {file_path.name}: {e}", exc_info=True)
            # Fallback
            from .schemas import ClassificationResult, RoleType
            classification = ClassificationResult(
                primary_role=RoleType.CONCEPT,
                confidence=0.2,
                classification_level=3,
                warnings=[f"Classification error: {e}"],
                source="Fallback"
            )

        # 5. DB エントリの構築
        
        new_role = Role(
            type=classification.primary_role.value,
            confidence=classification.confidence
        )

        entry = LoRAEntry(
            lora_id=lora_id,
            name=file_path.stem,
            base_model=detected_base_model,
            roles=[new_role],
            metadata=LoRAMetadata(
                trigger_words=metadata_dict.get("trigger_words", []),
                tags=metadata_dict.get("tags", []),
                description=metadata_dict.get("description"),
                preview_image_path=metadata_dict.get("preview_image_path"),
                reference_image_urls=metadata_dict.get("reference_image_urls", []),
                civitai_version_id=metadata_dict.get("civitai_version_id"),
                source="local_scan" if not hf_model_id else "huggingface",
                # datetime 側は Pydantic モデル側で Field(default_factory=datetime.utcnow) があるため省略可・上書き可
            ),
            compatibility_rules=CompatibilityRules(preferred_weight=0.8, max_weight=1.2),
            user_override=UserOverride()
        )

        # 6. DB更新
        try:
            db.upsert_lora(entry)
            logger.info(f"Successfully processed and saved '{lora_id}'")
            return lora_id
        except Exception as e:
            logger.error(f"Error saving to database: {e}", exc_info=True)
            return None
            
    except Exception as e:
        logger.error(f"Unexpected error processing {file_path}", exc_info=True)
        return None

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    # サンプルとしての単体実行エントリポイント
    # 実際の運用ではWatchdog等でディレクトリを監視して呼び出す
    sample_file = Path("sample_character_v1.safetensors")
    
    # テスト用のダミーファイル作成
    if not sample_file.exists():
        with open(sample_file, "wb") as f:
            f.write(b"dummy safetensors content")
            
    logger.info("Starting worker process demo...")
    process_new_lora(sample_file)
    time.sleep(1)
    
    # 実行後はダミーファイルを削除
    if sample_file.exists():
        sample_file.unlink()

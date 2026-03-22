from typing import List, Optional, Literal
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field

class RoleType(str, Enum):
    CHARACTER = "Character"
    COMPOSITION = "Composition"
    STYLE = "Style"
    CONCEPT = "Concept"

class Role(BaseModel):
    # 設計書の「Role分類エンジン」の記述に基づいて種類を定義
    type: Literal["Character", "Composition", "Style", "Concept"]
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="0.0から1.0までの確信度スコア")

class ClassificationResult(BaseModel):
    primary_role: RoleType
    confidence: float
    classification_level: int
    importance: str = "primary"
    warnings: List[str] = []
    source: str = "Unknown"

class LoRAMetadata(BaseModel):
    trigger_words: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    description: Optional[str] = Field(default=None, description="LoRAの説明テキスト（最大2000文字）")
    preview_image_path: Optional[str] = Field(default=None, description="ローカルのプレビュー画像への絶対パス")
    reference_image_urls: List[str] = Field(default_factory=list, description="Civitaiの参考画像URLリスト")
    civitai_version_id: Optional[int] = Field(default=None, description="Civitai APIフェッチ用のバージョンID")
    source: str = Field(default="unknown")
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CompatibilityRules(BaseModel):
    preferred_weight: float = Field(default=0.8)
    max_weight: float = Field(default=1.2)

class UserOverride(BaseModel):
    roles: Optional[List[Role]] = None
    is_locked: bool = Field(default=False)

class LoRAEntry(BaseModel):
    """
    lora_db.json 内の各LoRAエントリを表すメインのデータモデル
    """
    lora_id: str = Field(..., description="一意のハッシュまたはファイル名")
    name: str = Field(..., description="拡張子を除くLoRAファイル名")
    base_model: str = Field(..., description="ベースモデル (例: SDXL, SD15, Pony 等)")
    roles: List[Role] = Field(default_factory=list)
    metadata: LoRAMetadata
    compatibility_rules: CompatibilityRules
    user_override: UserOverride

class DatabaseSchema(BaseModel):
    """
    lora_db.json 全体のスキーマを表すルートモデル
    """
    loras: List[LoRAEntry] = Field(default_factory=list)

# --- バックエンド API 応答用のスキーマ ---

class APIResponse(BaseModel):
    base_model: str = Field(default="Unknown", description="判定されたベースモデル")
    optimized_weights: dict[str, float] = Field(description="最適化された各LoRAのWeight")
    compatibility_score: int = Field(ge=0, le=100, description="0から100の総合スコア")
    confidence_level: Literal["High", "Medium", "Low"] = Field(description="DBのRole信頼度平均に基づくレベル")
    warnings: List[str] = Field(default_factory=list, description="競合や上限超過などの警告メッセージ")

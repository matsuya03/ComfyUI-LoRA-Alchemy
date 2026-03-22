import html
import json
import re
import requests
import logging
import time # Added for retry delay
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

from .schemas import ClassificationResult, RoleType # Modified import
from .config import (
    OLLAMA_BASE_URL, 
    LLM_MODEL_NAME, 
    OLLAMA_TIMEOUT
)

RETRY_MAX_ATTEMPTS = 3
RETRY_INITIAL_DELAY = 1.0
RETRY_BACKOFF_FACTOR = 2.0

logger = logging.getLogger(__name__)

# ClassificationResult class definition is now imported from .schemas
# class ClassificationResult(BaseModel):
#     primary_role: str
#     confidence: float
#     classification_level: int
#     importance: str = "primary"
#     warnings: List[str] = []

class RoleClassifier:
    def __init__(self):
        # Fallback 1: タグベースの分類用マッピングと重み付け
        self.tag_mapping = {
            "Character": ["1girl", "1boy", "solo", "character", "cosplay", "face", "girl", "boy"],
            "Style": ["anime", "realistic", "painting", "sketch", "3d", "pixel art", "watercolor"],
            "Composition": ["scenery", "background", "indoor", "outdoor", "landscape", "pose", "looking at viewer"],
            "Concept": ["concept", "effect", "lighting", "magic", "glowing", "cyberpunk"]
        }
        
        self.tag_importance = {
            "1girl": 0.9, "1boy": 0.9, "solo": 0.8,
            "girl": 0.7, "boy": 0.7,
            "anime": 0.4, "realistic": 0.5,
            "scenery": 0.8, "background": 0.6
        }
        
    def _sanitize_string(self, text: str, max_length: int = 500) -> str:
        """文字列のHTMLエスケープと切り詰めを行います。"""
        if not text:
            return ""
        s = html.escape(str(text))
        return s[:max_length]
        
    def _sanitize_tags(self, tags: List[str], max_items: int = 50) -> List[str]:
        """タグリストの無害化と最大要素数の制限を行います。"""
        if not tags:
            return []
        safe_tags = [self._sanitize_string(t, max_length=100) for t in tags[:max_items]]
        return safe_tags

    def classify(self, file_path: str, file_name: str, metadata: Dict[str, Any]) -> ClassificationResult:
        warnings = []
        
        # 3.1 Pre-processing (Sanitization)
        safe_name = self._sanitize_string(file_name, max_length=200)
        safe_tags = self._sanitize_tags(metadata.get("tags", []))
        
        # descriptionは設計書の例にはあるが今回はサニタイズのみ
        safe_desc = self._sanitize_string(metadata.get("description", ""))
        
        # 3.2 Level 1: LLM (Ollama) Classification
        llm_result = self._classify_via_llm(safe_name, safe_tags, safe_desc)
        if llm_result and llm_result.confidence >= 0.4: # Changed to access attribute
            return llm_result # Return ClassificationResult directly
        else:
            warnings.append("Level 1 (LLM) classification failed or low confidence. Falling back to Level 2.")

        # 3.3 Level 2: Tag-based Classification (Fallback 1)
        tag_result = self._classify_via_tags(safe_tags)
        if tag_result and tag_result.get("confidence", 0.0) >= 0.4:
            return ClassificationResult(
                primary_role=RoleType(tag_result["primary_role"]), # Changed to RoleType
                confidence=tag_result["confidence"],
                classification_level=2,
                warnings=warnings,
                source="Tag-based" # Added source
            )
        else:
            warnings.append("Level 2 (Tag-based) classification failed. Falling back to Level 3.")

        # 3.4 Level 3: Filename Parsing (Fallback 2)
        filename_result = self._classify_via_filename(safe_name)
        return ClassificationResult(
            primary_role=RoleType(filename_result["primary_role"]), # Changed to RoleType
            confidence=filename_result["confidence"],
            classification_level=3,
            warnings=warnings,
            source="Filename" # Added source
        )

    def _classify_via_llm(self, file_name: str, tags: List[str], description: str) -> Optional[ClassificationResult]: # Changed return type
        """Ollama APIを使用してRoleを推論します。(Level 1)"""
        prompt = f"""Classify the primary role of this LoRA model based on its name and tags.
The role must be EXACTLY ONE of: Character, Composition, Style, or Concept.
Respond with ONLY the role name. Do not include confidence or any other text.

LoRA Name: {file_name}
Tags: {', '.join(tags)}
Role:
"""
        
        payload = {
            "model": LLM_MODEL_NAME,
            "prompt": prompt,
            "stream": False
        }
        
        # Ollama API へのリクエスト（リトライ付き）
        for attempt in range(RETRY_MAX_ATTEMPTS):
            try:
                response = requests.post(
                    f"{OLLAMA_BASE_URL}/api/generate",
                    json=payload,
                    timeout=float(OLLAMA_TIMEOUT)
                )
                response.raise_for_status()
                
                # Regex抽出によるレスポンス解析...
                result_text = response.json().get("response", "")
                
                # パース成功した場合
                parsed_roles = self._parse_llm_response(result_text)
                if parsed_roles:
                    primary_role = parsed_roles[0]
                    logger.info(f"Level 1 (LLM) classification successful for '{file_name}': {primary_role['type']} with confidence {primary_role['confidence']}") # Updated log
                    return ClassificationResult(
                        primary_role=RoleType(primary_role['type']),
                        confidence=primary_role['confidence'],
                        classification_level=1, # Added classification_level
                        source="LLM"
                    )
                else:
                    logger.warning(f"Failed to parse LLM response for '{file_name}'. Content: '{result_text}'")
                    break # パース失敗はリトライしても同じプロンプトなら無意味なため抜ける
                    
            except requests.exceptions.RequestException as e:
                if attempt < RETRY_MAX_ATTEMPTS - 1:
                    wait_time = RETRY_INITIAL_DELAY * (RETRY_BACKOFF_FACTOR ** attempt)
                    logger.warning(f"Ollama API request failed (attempt {attempt+1}/{RETRY_MAX_ATTEMPTS}): {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Level 1 (LLM) classification failed for '{file_name}' after {RETRY_MAX_ATTEMPTS} attempts. Error: {e}")
        
        logger.info("Falling back to Level 2 (Tag-based) classification.")
        return None

    def _parse_llm_response(self, response_text: str) -> List[Dict[str, Any]]:
        """
        LLMのレスポンスを解析し、ロールと確信度を抽出します。
        現在は単純な正規表現マッチングですが、将来的にはJSON形式のレスポンスを期待する可能性も考慮します。
        """
        roles = []
        # 正規表現で候補を抽出 (JSONパースエラーを回避)
        match = re.search(r'(?i)(character|composition|style|concept)', response_text)
        if match:
            role_type = match.group(1).capitalize()
            # LLM推論の確信度は固定または他ロジックで補完 (今回は一旦0.8とする)
            roles.append({"type": role_type, "confidence": 0.8})
        return roles

    def _classify_via_tags(self, tags: List[str]) -> Optional[Dict[str, Any]]:
        """タグと事前定義マッピングを用いて推論します。(Level 2)"""
        if not tags:
            return None
            
        role_scores = {k: 0.0 for k in self.tag_mapping.keys()}
        matched = False
        
        for tag in tags:
            tag_lower = tag.lower()
            weight = self.tag_importance.get(tag_lower, 0.3) # デフォルトの重み
            
            for role, keywords in self.tag_mapping.items():
                if any(kw in tag_lower for kw in keywords):
                    role_scores[role] += weight
                    matched = True
                    
        if not matched:
            return None
            
        # 最もスコアの高いRoleを選択
        best_role = max(role_scores, key=role_scores.get)
        max_score = role_scores[best_role]
        
        # 簡単な確信度計算（最大値 / 全体スコア）最低0.4
        total_score = sum(role_scores.values())
        confidence = max(0.4, min(max_score / total_score, 0.9)) if total_score > 0 else 0.4
        
        return {"primary_role": best_role, "confidence": confidence}

    def _classify_via_filename(self, file_name: str) -> Dict[str, Any]:
        """ファイル名に基づく正規表現フォールバック。(Level 3)"""
        name_lower = file_name.lower()
        
        if re.search(r"(character|char|girl|boy)", name_lower):
            return {"primary_role": "Character", "confidence": 0.30}
        elif re.search(r"(style|anime|realistic)", name_lower):
            return {"primary_role": "Style", "confidence": 0.30}
        elif re.search(r"(pose|background|bg|scenery)", name_lower):
            return {"primary_role": "Composition", "confidence": 0.30}
        else:
            # どれにもマッチしない場合はConceptをデフォルトとする
            return {"primary_role": "Concept", "confidence": 0.20}

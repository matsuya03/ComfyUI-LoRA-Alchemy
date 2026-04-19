import json
import os
import logging
import re
from typing import Dict, Any, Optional
import struct
import requests
import time
from pydantic import ValidationError
from .schemas import LoRAMetadata

from .config import (
    HF_TOKEN, 
    HF_API_TIMEOUT
)

HF_API_BASE = os.getenv("HF_API_BASE", "https://huggingface.co/api/")
RETRY_MAX_ATTEMPTS = 3
RETRY_INITIAL_DELAY = 1.0
RETRY_BACKOFF_FACTOR = 2.0
RETRY_HTTP_STATUS_CODES = {429, 500, 502, 503, 504}

logger = logging.getLogger(__name__)

class MetadataExtractor:
    def __init__(self):
        self.headers = {}
        if HF_TOKEN:
            self.headers["Authorization"] = f"Bearer {HF_TOKEN}"
            
    def _read_safetensors_header(self, file_path: str) -> Optional[Dict[str, Any]]:
        try:
            with open(file_path, "rb") as f:
                size_bytes = f.read(8)
                if len(size_bytes) < 8: return None
                header_size = struct.unpack('<Q', size_bytes)[0]
                if header_size > 100 * 1024 * 1024: return None
                header_bytes = f.read(header_size)
                header_json = json.loads(header_bytes.decode('utf-8'))
                return header_json.get("__metadata__", {})
        except Exception as e:
            logger.warning(f"Failed to read safetensors header from {file_path}", exc_info=True)
            return None

    def _fetch_from_huggingface(self, model_id: str) -> Optional[Dict[str, Any]]:
        if not model_id: return None
        api_url = f"{HF_API_BASE.rstrip('/')}/models/{model_id}"
        headers = {"Authorization": f"Bearer {HF_TOKEN}"} if HF_TOKEN else {}
        
        for attempt in range(RETRY_MAX_ATTEMPTS):
            try:
                response = requests.get(api_url, headers=headers, timeout=float(HF_API_TIMEOUT))
                if response.status_code in (401, 403, 404): return None
                response.raise_for_status()
                hf_data = response.json()
                return {
                    "tags": hf_data.get("tags", []),
                    "description": hf_data.get("description", "")
                }
            except requests.exceptions.RequestException as e:
                status_code = getattr(e.response, 'status_code', None)
                if status_code in RETRY_HTTP_STATUS_CODES or isinstance(e, requests.exceptions.ConnectionError):
                    if attempt < RETRY_MAX_ATTEMPTS - 1:
                        time.sleep(RETRY_INITIAL_DELAY * (RETRY_BACKOFF_FACTOR ** attempt))
                    else: return None
                else: return None
        return None

    def _normalize_base_model(self, hint: str) -> str:
        """文字列の表記ゆれを吸収し、システムで定義されたベースモデル名に統一する"""
        if not hint: return "Unknown"
        hint_lower = hint.lower()
        
        # 1. 追加リクエストのモデル群
        if "illustrious" in hint_lower or "ixl" in hint_lower: return "Illustrious"
        if "noobai" in hint_lower or "noob" in hint_lower: return "NoobAI"
        if "anima" in hint_lower: return "Anima"
        if "qwen" in hint_lower: return "Qwen"
        
        # 2. ZImage系の判定
        if "zimage" in hint_lower or "z-image" in hint_lower or "z_image" in hint_lower or "z-turbo" in hint_lower:
            if "turbo" in hint_lower: return "ZImageTurbo"
            return "ZImageBase"
            
        # 3. Pony
        if "pony" in hint_lower: return "Pony"
        
        # 4. Flux系の細分化
        if "flux" in hint_lower or "klein" in hint_lower:
            if "klein 9b-base" in hint_lower or "klein_9b_base" in hint_lower: return "Flux.2 Klein 9B-base"
            if "klein 9b" in hint_lower or "klein_9b" in hint_lower: return "Flux.2 Klein 9B"
            if "klein 4b-base" in hint_lower or "klein_4b_base" in hint_lower: return "Flux.2 Klein 4B-base"
            if "klein 4b" in hint_lower or "klein_4b" in hint_lower: return "Flux.2 Klein 4B"
            if "flux.2 d" in hint_lower or "flux 2 d" in hint_lower or "flux2-d" in hint_lower: return "Flux.2 D"
            return "Flux"
            
        # 5. SD系
        if "sdxl" in hint_lower or "stable diffusion xl" in hint_lower or "xl" in hint_lower: return "SDXL"
        if "1.5" in hint_lower or "sd15" in hint_lower or "sd 1.5" in hint_lower: return "SD1.5"
        if "2.1" in hint_lower or "sd21" in hint_lower or "sd 2.1" in hint_lower: return "SD2.1"
        
        return "Unknown"

    def extract(self, file_path: str, hf_model_id: Optional[str] = None) -> Dict[str, Any]:
        combined_metadata: Dict[str, Any] = {
            "tags": [], "trigger_words": [], "description": "",
            "preview_image_path": None, "reference_image_urls": [], 
            "civitai_version_id": None,
            "base_model": "Unknown"
        }
        
        base_path = os.path.splitext(file_path)[0]
        preview_path = base_path + ".preview.png"
        preview_jpg = base_path + ".preview.jpeg"
        
        if os.path.exists(preview_path):
            combined_metadata["preview_image_path"] = preview_path
        elif os.path.exists(preview_jpg):
            combined_metadata["preview_image_path"] = preview_jpg
            
        json_candidates = [
            base_path + ".cm-info.json",
            base_path + ".civitai.info",
            base_path + ".json",
            base_path + ".metadata.json"
        ]
        
        for target_json in json_candidates:
            if os.path.exists(target_json):
                try:
                    with open(target_json, 'r', encoding='utf-8') as f:
                        sm_data = json.load(f)
                        
                        is_valid_format = any(k in sm_data for k in [
                            "ModelDescription", "description", "civitai", 
                            "trainedWords", "TrainedWords", "BaseModel", "baseModel"
                        ])
                        
                        if not is_valid_format:
                            logger.debug(f"Skipped {target_json}: Not a valid SM/Civitai format.")
                            continue
                        
                        desc_keys = ["ModelDescription", "description"]
                        for dk in desc_keys:
                            if dk in sm_data and sm_data[dk] and not combined_metadata["description"]:
                                desc_str = str(sm_data[dk])
                                img_urls = re.findall(r'<img[^>]+src="([^">]+)"', desc_str)
                                combined_metadata["reference_image_urls"].extend(img_urls)
                                clean_desc = desc_str.replace("<br>", "\n").replace("<br />", "\n").replace("</p>", "\n")
                                clean_desc = re.sub(r'<[^>]+>', '', clean_desc).strip()
                                combined_metadata["description"] = clean_desc[:2000] + ("..." if len(clean_desc) > 2000 else "")
                        
                        trigger_keys = ["TrainedWords", "trainedWords"]
                        for tk in trigger_keys:
                            if tk in sm_data and isinstance(sm_data[tk], list):
                                combined_metadata["trigger_words"].extend(sm_data[tk])
                        
                        tag_keys = ["Tags", "tags"]
                        for tk in tag_keys:
                            if tk in sm_data and isinstance(sm_data[tk], list):
                                combined_metadata["tags"].extend(sm_data[tk])

                        # 4. JSON Array Images (標準的な配列形式用 ＋ Civitaiネスト対応)
                        image_arrays = []
                        # 一番外側にある images
                        if "images" in sm_data and isinstance(sm_data["images"], list):
                            image_arrays.append(sm_data["images"])
                        # "civitai" の中にある images (SM特有の仕様)
                        if "civitai" in sm_data and isinstance(sm_data["civitai"], dict):
                            if "id" in sm_data["civitai"]:
                                combined_metadata["civitai_version_id"] = sm_data["civitai"]["id"]
                            if "images" in sm_data["civitai"] and isinstance(sm_data["civitai"]["images"], list):
                                image_arrays.append(sm_data["civitai"]["images"])
                                
                        if combined_metadata["civitai_version_id"] is None:
                             for id_key in ["id", "VersionId", "versionId", "version_id"]:
                                 if id_key in sm_data:
                                     try:
                                         combined_metadata["civitai_version_id"] = int(sm_data[id_key])
                                         break
                                     except (ValueError, TypeError):
                                         pass
                                
                        for img_list in image_arrays:
                            for img in img_list:
                                if "url" in img and isinstance(img["url"], str):
                                    combined_metadata["reference_image_urls"].append(img["url"])
                                    
                        model_keys = ["BaseModel", "baseModel", "base_model"]
                        for mk in model_keys:
                            if mk in sm_data and sm_data[mk] and str(sm_data[mk]).lower() != "unknown":
                                if combined_metadata["base_model"] == "Unknown":
                                    combined_metadata["base_model"] = self._normalize_base_model(str(sm_data[mk]))
                                    
                except Exception as e:
                    logger.warning(f"Error reading local json {target_json}: {e}")

        # Priority 3: ローカルの safetensors ヘッダーから抽出 + ファイル名の推測
        if os.path.exists(file_path):
            local_meta = self._read_safetensors_header(file_path)
            if local_meta:
                tags = local_meta.get("modelspec.tags", "") or local_meta.get("tags", "")
                if isinstance(tags, str) and tags:
                    combined_metadata["tags"].extend([t.strip() for t in tags.split(",")])
                    
                triggers = local_meta.get("modelspec.trigger_words", "") or local_meta.get("trigger_words", "")
                if isinstance(triggers, str) and triggers:
                    combined_metadata["trigger_words"].extend([t.strip() for t in triggers.split(",")])

            # メタデータからベースモデルが判定できなかった場合、ファイル名も含めて推測する
            if combined_metadata["base_model"] == "Unknown":
                model_name_hints = [
                    os.path.basename(file_path) # ★ ファイル名も判定材料に追加！
                ]
                if local_meta:
                    model_name_hints.extend([
                        local_meta.get("ss_sd_model_name", ""),
                        local_meta.get("modelspec.architecture", ""),
                        local_meta.get("ss_base_model_version", "")
                    ])
                hint_str = " ".join([str(h) for h in model_name_hints if h]).lower()
                combined_metadata["base_model"] = self._normalize_base_model(hint_str)

        if hf_model_id:
            hf_meta = self._fetch_from_huggingface(hf_model_id)
            if hf_meta:
                combined_metadata["tags"].extend(hf_meta.get("tags", []))
                if not combined_metadata["description"]:
                    desc = hf_meta.get("description", "")
                    combined_metadata["description"] = desc[:2000] + ("..." if len(desc) > 2000 else "")

        # Civitai APIから画像URL補完
        # reference_image_urls が空で civitai_version_id がある場合に自動補完
        if not combined_metadata["reference_image_urls"] and combined_metadata["civitai_version_id"]:
            urls = self._fetch_civitai_images(combined_metadata["civitai_version_id"])
            if urls:
                combined_metadata["reference_image_urls"] = urls

        combined_metadata["tags"] = list(set([t for t in combined_metadata["tags"] if t]))
        combined_metadata["trigger_words"] = list(set([t for t in combined_metadata["trigger_words"] if t]))

        if combined_metadata["base_model"] == "Unknown":
            combined_metadata["base_model"] = "SDXL"

        return combined_metadata

    def _fetch_civitai_images(self, version_id: int) -> list:
        """Civitai APIから画像URL一覧を取得する。civitai.red を優先し、失敗時は civitai.com にフォールバック。"""
        endpoints = [
            f"https://civitai.red/api/v1/model-versions/{version_id}",
            f"https://civitai.com/api/v1/model-versions/{version_id}",
        ]
        for url in endpoints:
            for attempt in range(RETRY_MAX_ATTEMPTS):
                try:
                    response = requests.get(url, timeout=10.0)
                    if response.status_code in (401, 403, 404):
                        break  # このエンドポイントは諦めて次へ
                    response.raise_for_status()
                    data = response.json()
                    image_urls = [img["url"] for img in data.get("images", []) if img.get("url")]
                    if image_urls:
                        logger.info(f"Fetched {len(image_urls)} images from {url}")
                        return image_urls
                    break  # 画像なし → 次エンドポイントへ
                except requests.exceptions.RequestException as e:
                    status_code = getattr(getattr(e, 'response', None), 'status_code', None)
                    if status_code in RETRY_HTTP_STATUS_CODES or isinstance(e, requests.exceptions.ConnectionError):
                        if attempt < RETRY_MAX_ATTEMPTS - 1:
                            time.sleep(RETRY_INITIAL_DELAY * (RETRY_BACKOFF_FACTOR ** attempt))
                        else:
                            logger.warning(f"Failed to fetch Civitai images from {url} after {RETRY_MAX_ATTEMPTS} attempts")
                            break
                    else:
                        logger.warning(f"Failed to fetch Civitai images from {url}: {e}")
                        break
        return []

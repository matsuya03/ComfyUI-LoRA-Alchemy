import os
import json
import logging
from typing import List, Dict, Set, Tuple
from .schemas import LoRAEntry

logger = logging.getLogger(__name__)

# JSONファイルが見つからなかった・壊れていた場合の緊急用フォールバック
DEFAULT_BASE_MODEL_WEIGHTS = {
    "SDXL": 1.5,
    "SD1.5": 2.0,
    "Pony": 1.2,
    "Flux": 1.0,
    "default": 1.5
}

def load_base_model_weights() -> Dict[str, float]:
    """外部のJSON設定ファイルからベースモデルの上限Weightを読み込む"""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "base_models.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.info(f"Loaded base model weights from {config_path}")
                return data
        except Exception as e:
            logger.error(f"Error loading {config_path}: {e}. Using default weights.")
    
    return DEFAULT_BASE_MODEL_WEIGHTS

# モジュール読み込み時に一度だけJSONをロードする
BASE_MODEL_MAX_WEIGHT = load_base_model_weights()

def optimize_weights(
    active_loras: List[LoRAEntry],
    current_weights: Dict[str, float],
    pinned_loras: Set[str],
    base_model: str = "SDXL"
) -> Tuple[Dict[str, float], List[str]]:
    """
    Pinned(固定)状態のLoRAのWeightを優先し、残余Weightを未固定のLoRAの
    preferred_weightの比率に応じて按分（自動再計算）します。
    """
    warnings = []
    
    # 辞書に一致するモデルがなければ "default" の値を採用する
    max_total_weight = BASE_MODEL_MAX_WEIGHT.get(base_model, BASE_MODEL_MAX_WEIGHT.get("default", 1.5))
    
    optimized_weights = {lora.lora_id: 0.0 for lora in active_loras}
    
    # 固定されたLoRAの合計Weightを計算
    pinned_total_weight = 0.0
    for lora in active_loras:
        if lora.lora_id in pinned_loras:
            weight = current_weights.get(lora.lora_id, lora.compatibility_rules.preferred_weight)
            optimized_weights[lora.lora_id] = weight
            pinned_total_weight += weight

    if pinned_total_weight > max_total_weight:
        warnings.append(
            f"Warning: Pinned weights total ({pinned_total_weight:.2f}) exceeds the recommended max ({max_total_weight:.2f}) for base model {base_model}."
        )
        return optimized_weights, warnings

    # 残余Weightの計算
    remaining_weight = max(0.0, max_total_weight - pinned_total_weight)
    
    # 未固定LoRAの preferred_weight 合計を算出（按分の母数）
    unpinned_loras = [lora for lora in active_loras if lora.lora_id not in pinned_loras]
    total_preferred = sum(lora.compatibility_rules.preferred_weight for lora in unpinned_loras)

    # 按分処理
    if total_preferred > 0:
        for lora in unpinned_loras:
            ratio = lora.compatibility_rules.preferred_weight / total_preferred
            allocated_weight = remaining_weight * ratio
            
            # 各LoRAの max_weight を超えていないかチェック
            if allocated_weight > lora.compatibility_rules.max_weight:
                warnings.append(
                    f"Warning: Calculated weight for '{lora.name}' ({allocated_weight:.2f}) exceeds its max_weight ({lora.compatibility_rules.max_weight:.2f}). Adjusted to max_weight."
                )
                allocated_weight = lora.compatibility_rules.max_weight
                
            optimized_weights[lora.lora_id] = round(allocated_weight, 3)
    
    return optimized_weights, warnings

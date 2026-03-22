from typing import List, Dict, Tuple
from .schemas import LoRAEntry
from .weight_optimizer import BASE_MODEL_MAX_WEIGHT

ROLE_RECOMMENDED_WEIGHTS = {
    "Character": 0.65,
    "Style": 0.55,
    "Pose": 0.55,
    "Clothing": 0.55,
    "Composition": 0.55,
    "Concept": 0.35,
    "Default": 0.50
}

def get_recommended_weight_for_role(roles: List[str]) -> float:
    if not roles:
        return ROLE_RECOMMENDED_WEIGHTS["Default"]
    
    # 一番重みが高いRoleを採用する
    weights = []
    for role in roles:
        weights.append(ROLE_RECOMMENDED_WEIGHTS.get(role, ROLE_RECOMMENDED_WEIGHTS["Default"]))
    return max(weights)

def auto_balance_weights(
    active_loras: List[LoRAEntry],
    base_model: str = "SDXL"
) -> Tuple[Dict[str, float], List[str]]:
    """
    Role別の推奨Weight配分を自動計算し、モデル上限内に調整して返す。
    """
    warnings = []
    max_total_weight = BASE_MODEL_MAX_WEIGHT.get(base_model, 1.5)
    
    raw_weights = {}
    for lora in active_loras:
        roles = lora.user_override.roles if lora.user_override.roles is not None else lora.roles
        role_types = [r.type for r in roles]
        recommended = get_recommended_weight_for_role(role_types)
        raw_weights[lora.lora_id] = recommended

    total_weight = sum(raw_weights.values())
    
    balanced_weights = {}
    if total_weight > max_total_weight:
        # 自動正規化 (Total Weight Limiter)
        warnings.append(f"Auto Balance: Total recommended weight ({total_weight:.2f}) exceeds max ({max_total_weight:.2f}) for {base_model}. Normalizing weights.")
        for lora_id, weight in raw_weights.items():
            balanced_weights[lora_id] = round(weight * (max_total_weight / total_weight), 3)
    else:
        for lora_id, weight in raw_weights.items():
            balanced_weights[lora_id] = round(weight, 3)
            
    return balanced_weights, warnings

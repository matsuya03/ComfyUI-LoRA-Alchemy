from typing import Dict, List, Tuple
from .schemas import LoRAEntry

def calculate_influence_map(lora: LoRAEntry) -> Dict[str, int]:
    """
    LoRA名、役割、メタデータタグなどを解析し、各領域への影響度(0~100)を推定する。
    """
    influence = {
        "Face": 0,
        "Body": 0,
        "Clothing": 0,
        "Lighting": 0,
        "Background": 0,
        "Style": 0,
        "Pose": 0
    }
    
    name_lower = lora.name.lower()
    roles = [r.type for r in (lora.user_override.roles if lora.user_override.roles is not None else lora.roles)]
    tags = [t.lower() for t in lora.metadata.tags]
    words = [w.lower() for w in lora.metadata.trigger_words]
    combined_text = " ".join([name_lower] + tags + words)
    
    # 役割ベースの基本割り当て
    if "Character" in roles:
        influence["Face"] = 90
        influence["Body"] = 70
        influence["Clothing"] = 60
    if "Style" in roles:
        influence["Style"] = 90
        influence["Lighting"] = 40
    if "Pose" in roles:
        influence["Pose"] = 90
        influence["Body"] = 80
    if "Clothing" in roles:
        influence["Clothing"] = 95
        influence["Body"] = 30
    if "Composition" in roles:
        influence["Background"] = 80
        influence["Lighting"] = 60
        
    # キーワードマッチングによる加算（ヒューリスティックによる微修正）
    if any(k in combined_text for k in ["face", "eyes", "hair", "smile", "portrait", "1girl", "1boy"]):
        influence["Face"] = min(100, influence["Face"] + 40)
    if any(k in combined_text for k in ["body", "breasts", "legs", "arms", "navel", "waist"]):
        influence["Body"] = min(100, influence["Body"] + 40)
    if any(k in combined_text for k in ["dress", "shirt", "skirt", "uniform", "armor", "costume", "clothes"]):
        influence["Clothing"] = min(100, influence["Clothing"] + 40)
    if any(k in combined_text for k in ["dark", "light", "neon", "sun", "shadow", "glowing"]):
        influence["Lighting"] = min(100, influence["Lighting"] + 40)
    if any(k in combined_text for k in ["background", "scenery", "outdoors", "indoors", "room", "sky", "city"]):
        influence["Background"] = min(100, influence["Background"] + 40)
    if any(k in combined_text for k in ["anime", "photo", "realistic", "sketch", "painting", "3d", "pixel"]):
        influence["Style"] = min(100, influence["Style"] + 40)
    if any(k in combined_text for k in ["standing", "sitting", "lying", "pose", "action", "running", "jumping"]):
        influence["Pose"] = min(100, influence["Pose"] + 40)
        
    return influence

def check_region_conflicts(lora1: LoRAEntry, map1: Dict[str, int], lora2: LoRAEntry, map2: Dict[str, int]) -> Tuple[int, List[str]]:
    """
    影響範囲の重複（領域衝突）を検出し、ペナルティスコアと警告リストを返す。
    同じ階層・領域での衝突を精密に判定する。
    """
    score_penalty = 0
    warnings = []
    
    # 領域ごとの衝突ルール定義 (Threshold: 60)
    conflict_rules = {
        "Face": {"penalty": 50, "msg": "Absolute Region Conflict (Face)"},
        "Pose": {"penalty": 40, "msg": "Major Region Conflict (Pose)"},
        "Style": {"penalty": 30, "msg": "Major Region Conflict (Style)"},
        "Lighting": {"penalty": 20, "msg": "Mild Region Conflict (Lighting)"},
        "Background": {"penalty": 20, "msg": "Mild Region Conflict (Background)"},
        "Clothing": {"penalty": 20, "msg": "Mild Region Conflict (Clothing)"}
    }
    
    for region, rule in conflict_rules.items():
        if map1[region] >= 60 and map2[region] >= 60:
            score_penalty += int(rule["penalty"])
            warnings.append(f"{rule['msg']}: '{lora1.name}' and '{lora2.name}' are fighting over {region} control.")

    return score_penalty, warnings

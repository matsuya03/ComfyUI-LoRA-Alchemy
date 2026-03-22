from typing import List, Tuple, Dict, Set
from .schemas import LoRAEntry
from .influence_classifier import calculate_influence_map, check_region_conflicts

def get_tag_weight(tag: str) -> float:
    """タグの重要度を定義（本来はより精緻な辞書やLLMを使うが、簡易的に実装）"""
    tag_lower = tag.lower()
    important_keywords = ["1girl", "1boy", "anime", "photorealistic", "style", "character", "concept", "background", "pose", "outfit"]
    if any(k in tag_lower for k in important_keywords):
        return 0.95
    return 0.35

def calculate_weighted_jaccard(set1: Set[str], set2: Set[str]) -> float:
    """タグの重要度を考慮した加重Jaccard係数"""
    if not set1 and not set2:
        return 0.0
    
    intersection = set1.intersection(set2)
    union = set1.union(set2)
    
    intersection_weight = sum(get_tag_weight(t) for t in intersection)
    union_weight = sum(get_tag_weight(t) for t in union)
    
    if union_weight == 0:
        return 0.0
    return intersection_weight / union_weight

def get_lora_roles(lora: LoRAEntry) -> List[str]:
    roles = lora.user_override.roles if lora.user_override.roles is not None else lora.roles
    return [r.type for r in roles]

def evaluate_compatibility(lora1: LoRAEntry, lora2: LoRAEntry) -> Tuple[int, List[str]]:
    """
    2つのLoRA間の相性スコア（100点満点からの減点方式）と警告リストを算出します。
    加重Jaccard係数およびRole別の競合マトリックスを導入した完全版。
    """
    score = 100
    warnings = []

    words1 = set(lora1.metadata.trigger_words)
    tags1 = set(lora1.metadata.tags)
    
    words2 = set(lora2.metadata.trigger_words)
    tags2 = set(lora2.metadata.tags)

    combined_set1 = words1.union(tags1)
    combined_set2 = words2.union(tags2)

    # 1. 加重Jaccard係数
    similarity = calculate_weighted_jaccard(combined_set1, combined_set2)

    if similarity >= 0.7:
        score -= 25
        warnings.append(f"Severe Concept Overlap: '{lora1.name}' and '{lora2.name}' (similarity: {similarity:.2f})")
    elif similarity >= 0.3:
        score -= 10
        warnings.append(f"Mild Concept Overlap: '{lora1.name}' and '{lora2.name}' (similarity: {similarity:.2f})")

    # 2. Influence Classifier による領域冲突（Region Conflict）チェック
    map1 = calculate_influence_map(lora1)
    map2 = calculate_influence_map(lora2)

    region_penalty, region_warnings = check_region_conflicts(lora1, map1, lora2, map2)
    score -= region_penalty
    warnings.extend(region_warnings)

    # 最終スコアの下限を0とする
    score = max(0, score)

    return score, warnings

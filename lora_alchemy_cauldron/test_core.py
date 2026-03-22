import os
from .db_manager import LoRADatabase
from .schemas import LoRAEntry, LoRAMetadata, CompatibilityRules, UserOverride, Role
from datetime import datetime, timezone

def setup_test_data(db: LoRADatabase):
    """DBを初期化し、テスト用のLoRAデータをいくつか投入します。"""
    # 既存データのクリア
    if db.db_path.exists():
        os.remove(db.db_path)
    # 再ロード
    db = LoRADatabase(db_path=db.db_path)

    # テストデータ1: Character
    lora1 = LoRAEntry(
        lora_id="test_char_1",
        name="test_char_1",
        base_model="SDXL",
        roles=[Role(type="Character", confidence=0.95)],
        metadata=LoRAMetadata(
            trigger_words=["1girl", "blue hair"],
            tags=["anime", "solo"],
            source="test",
            last_updated=datetime.now(timezone.utc)
        ),
        compatibility_rules=CompatibilityRules(preferred_weight=0.8, max_weight=1.0),
        user_override=UserOverride()
    )

    # テストデータ2: Character (競合用)
    lora2 = LoRAEntry(
        lora_id="test_char_2",
        name="test_char_2",
        base_model="SDXL",
        roles=[Role(type="Character", confidence=0.85)],
        metadata=LoRAMetadata(
            trigger_words=["1girl", "red hair"],
            tags=["anime", "solo"],
            source="test",
            last_updated=datetime.now(timezone.utc)
        ),
        compatibility_rules=CompatibilityRules(preferred_weight=0.8, max_weight=1.0),
        user_override=UserOverride()
    )

    # テストデータ3: Style
    lora3 = LoRAEntry(
        lora_id="test_style_1",
        name="test_style_1",
        base_model="SDXL",
        roles=[Role(type="Style", confidence=0.90)],
        metadata=LoRAMetadata(
            trigger_words=["pixel art"],
            tags=["retro", "8bit"],
            source="test",
            last_updated=datetime.now(timezone.utc)
        ),
        compatibility_rules=CompatibilityRules(preferred_weight=0.5, max_weight=0.8),
        user_override=UserOverride()
    )

    db.upsert_lora(lora1)
    db.upsert_lora(lora2)
    db.upsert_lora(lora3)
    print("Test data setup complete.")
    return db

def run_tests():
    db = LoRADatabase()
    setup_test_data(db)

    print("\n--- Test 1: Compatibility (Character vs Character) ---")
    lora1 = db.get_lora("test_char_1")
    lora2 = db.get_lora("test_char_2")
    if lora1 and lora2:
        from .compatibility import evaluate_compatibility
        score, warnings = evaluate_compatibility(lora1, lora2)
        print(f"[{lora1.name}] vs [{lora2.name}]")
        print(f"Score: {score}")
        print(f"Warnings: {warnings}")

    print("\n--- Test 2: Weight Optimization ---")
    active_loras = db.get_all()
    # test_char_1 を 1.0 でPinする想定
    current_weights = {"test_char_1": 1.0, "test_char_2": 0.8, "test_style_1": 0.5}
    pinned = {"test_char_1"}
    
    from .weight_optimizer import optimize_weights
    opt_weights, w_warnings = optimize_weights(
        active_loras=active_loras,
        current_weights=current_weights,
        pinned_loras=pinned,
        base_model="SDXL" # MAX = 1.5
    )
    print("Pinned: test_char_1 = 1.0")
    print(f"Optimized Weights: {opt_weights}")
    if w_warnings:
        print(f"Warnings: {w_warnings}")
        
    print("\nTests finished.")

if __name__ == "__main__":
    run_tests()

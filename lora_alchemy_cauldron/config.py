"""
LoRA Alchemy Cauldron のグローバル設定。
環境変数から値を読み込み、デフォルト値を設定する。
"""

import os
from dotenv import load_dotenv

# .env ファイルの読み込み
load_dotenv()

# ============================================================================
# HuggingFace API 関連
# ============================================================================
HF_TOKEN = os.getenv("HF_TOKEN", "")
HF_API_BASE = os.getenv("HF_API_BASE", "https://huggingface.co/api/")
HF_API_TIMEOUT = int(os.getenv("HF_API_TIMEOUT", "10"))  # HTTPリクエストタイムアウト(秒)

# ============================================================================
# ローカルLLM (Ollama) 関連
# ============================================================================
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "30"))  # Ollama呼び出しのタイムアウト(秒)
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "mistral:instruct")

# ============================================================================
# LoRA ID ハッシュ計算方式
# ============================================================================
# "full": ファイル全体をハッシュ（推奨、最も確実。ただし大容量ファイルは遅い）
# "fast": 先頭 1MB のみハッシュ（高速。大容量ファイル向け）
HASH_METHOD = os.getenv("HASH_METHOD", "fast")

# "fast" 方式の場合のチャンク サイズ（MB）
HASH_CHUNK_SIZE_MB = int(os.getenv("HASH_CHUNK_SIZE_MB", "1"))

# ============================================================================
# ファイル監視（Watchdog）関連
# ============================================================================
# 新規LoRAファイル検出後、書き込み完了を待つための最大待機時間（秒）
FILE_STABLE_TIMEOUT = int(os.getenv("FILE_STABLE_TIMEOUT", "60"))

# ファイルサイズが安定していると判定するまでの連続チェック数
FILE_STABLE_CHECKS = int(os.getenv("FILE_STABLE_CHECKS", "3"))

# ファイルサイズ変化チェックの間隔（秒）
FILE_STABLE_CHECK_INTERVAL = float(os.getenv("FILE_STABLE_CHECK_INTERVAL", "1.0"))

# ============================================================================
# ロギング・メトリクス
# ============================================================================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
# JSON ログ出力（True の場合、構造化ログを JSON 形式で出力。CloudWatch / ELK 等への integration が容易）
LOG_FORMAT_JSON = os.getenv("LOG_FORMAT_JSON", "false").lower() == "true"

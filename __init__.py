"""
ComfyUI Custom Node for LoRA Alchemy Cauldron
"""

import threading
import logging
from pathlib import Path

from .nodes import LoRAAlchemyNode
from .lora_alchemy_cauldron.logger_setup import setup_logging

# ログ設定
setup_logging()
logger = logging.getLogger("AlchemyInit")

# バックグラウンドスレッド用のグローバル変数
_watcher_thread = None

def start_background_services():
    """バックグラウンドで Watcher と Worker を起動"""
    global _watcher_thread
    
    logger.info("🧪 Initializing LoRA Alchemy Cauldron background services...")
    
    # LoRA ディレクトリを取得（ComfyUI の設定を使用）
    try:
        import folder_paths
        lora_paths = folder_paths.folder_names_and_paths.get("loras", [None])[0]
        if not lora_paths:
            logger.warning("No LoRA paths found. Skipping watcher initialization.")
            return
            
        # 全パスを監視（複数 Watcher スレッド、またはWatcher側でフォーク）
        # 簡単のため最初のディレクトリを対象とするか、ループしてスレッドを立ち上げる
        if isinstance(lora_paths, list):
            for lora_dir in lora_paths:
                thread = threading.Thread(
                    target=_run_watcher,
                    args=(lora_dir,),
                    daemon=True,
                    name=f"AlchemyWatcher-{Path(lora_dir).name}"
                )
                thread.start()
                logger.info(f"✅ Watcher started for: {lora_dir}")
        else:
            _watcher_thread = threading.Thread(
                target=_run_watcher,
                args=(lora_paths,),
                daemon=True,
                name="AlchemyWatcher"
            )
            _watcher_thread.start()
            logger.info(f"✅ Watcher started for: {lora_paths}")
        
    except Exception as e:
        logger.error(f"Error initializing background services: {e}", exc_info=True)

def _run_watcher(watch_dir: str):
    """Watcher をスレッド内で実行"""
    try:
        from .lora_alchemy_cauldron.watcher import start_watcher
        start_watcher(watch_dir)
    except Exception as e:
        logger.error(f"Watcher error: {e}", exc_info=True)

def on_comfyui_load():
    """ComfyUI 起動時に実行される"""
    start_background_services()

# ComfyUI が起動時に呼び出すコールバック
try:
    import server
    # server.py が on_comfyui_load を持つ場合はフック
    if hasattr(server, 'on_comfyui_load'):
        pass
except Exception as e:
    logger.debug(f"Could not hook on_comfyui_load: {e}")

# モジュールレベルで自動初期化される
start_background_services()

def cleanup():
    """終了時に安全にWatcherを止める（オプションだが推奨）"""
    logger.info("Stopping Watcher threads...")
    # Process exit will kill daemon threads

import atexit
atexit.register(cleanup)

# ComfyUI ノード登録
NODE_CLASS_MAPPINGS = {
    "LoRAAlchemyNode": LoRAAlchemyNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LoRAAlchemyNode": "🧪 LoRA Alchemy Cauldron"
}

WEB_DIRECTORY = "./js"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]

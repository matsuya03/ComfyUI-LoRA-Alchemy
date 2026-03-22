import time
import os
import logging
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from .worker import process_new_lora
from .config import FILE_STABLE_CHECKS, FILE_STABLE_CHECK_INTERVAL, FILE_STABLE_TIMEOUT
from .logger_setup import setup_logging

# ログ設定の初期化
setup_logging()
logger = logging.getLogger(__name__)

def _wait_for_file_stable(file_path: Path, timeout: int = FILE_STABLE_TIMEOUT) -> bool:
    """
    ファイルのサイズが安定化するまで待機する。
    大容量ファイルのコピー中に処理が始まらないようにするための工夫。
    """
    start_time = time.time()
    last_size = -1
    stable_count = 0
    
    while time.time() - start_time < timeout:
        try:
            if not file_path.exists():
                logger.warning(f"File disappeared during stability check: {file_path}")
                return False
            
            current_size = file_path.stat().st_size
            
            # ファイルサイズが変わらなかった場合、カウント増加
            if current_size == last_size and last_size >= 0:
                stable_count += 1
                if stable_count >= FILE_STABLE_CHECKS:
                    elapsed = time.time() - start_time
                    logger.info(f"File stable after {elapsed:.2f}s: {file_path.name} (size: {current_size} bytes)")
                    return True
            else:
                # サイズが変わった場合、カウントリセット
                stable_count = 0
                if last_size >= 0:
                    logger.debug(f"File size changed: {last_size} -> {current_size} bytes")
            
            last_size = current_size
            time.sleep(FILE_STABLE_CHECK_INTERVAL)
            
        except OSError as e:
            logger.warning(f"Error checking file stability: {e}")
            time.sleep(FILE_STABLE_CHECK_INTERVAL)
            
    logger.error(f"File stability check timeout after {timeout}s: {file_path}")
    return False

class LoRAFileHandler(FileSystemEventHandler):
    """Watchdog イベントハンドラ。新規 LoRA ファイルを検出して処理開始。"""
    
    def on_created(self, event):
        if event.is_directory:
            return
        
        file_path = Path(event.src_path)
        
        # .safetensors ファイルのみ処理
        if file_path.suffix.lower() != '.safetensors':
            return
            
        logger.info(f"New LoRA file detected: {file_path.name}")
        
        # ファイルの書き込み完了を待機
        if _wait_for_file_stable(file_path):
            try:
                logger.info(f"Starting to process: {file_path.name}")
                process_new_lora(file_path)
            except Exception as e:
                logger.error(f"Error processing LoRA: {file_path}", exc_info=True)
        else:
            logger.warning(f"File stability check failed, skipping: {file_path.name}")

def start_watcher(directory_str: str):
    target_dir = Path(directory_str)
    if not target_dir.exists():
        logger.error(f"Directory {target_dir} does not exist.")
        return
        
    event_handler = LoRAFileHandler()
    observer = Observer()
    observer.schedule(event_handler, str(target_dir), recursive=True)
    
    logger.info(f"Starting directory watcher on {target_dir} ...")
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        logger.info("Watcher stopped by user.")
    
    observer.join()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    # サンプルとしてカレントディレクトリを監視 (実運用は設定ファイル等から取得)
    start_watcher(".")

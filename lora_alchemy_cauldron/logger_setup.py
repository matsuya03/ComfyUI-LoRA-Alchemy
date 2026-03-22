import logging
import json
from .config import LOG_LEVEL, LOG_FORMAT_JSON

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data)

def setup_logging():
    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    logger = logging.getLogger() # root logger
    
    # ハンドラのリセット（二重登録防止）
    if logger.hasHandlers():
        logger.handlers.clear()
        
    handler = logging.StreamHandler()
    
    if LOG_FORMAT_JSON:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(level)

    # 外部ライブラリのログレベルを調整（必要に応じて）
    logging.getLogger("watchdog").setLevel(logging.WARNING)
    logging.getLogger("filelock").setLevel(logging.WARNING)

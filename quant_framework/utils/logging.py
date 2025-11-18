"""Logging helpers.

中文提示：统一配置日志格式，方便在不同运行模式下快速定位问题。
"""
import logging
from typing import Optional


def configure_logging(level: int = logging.INFO, name: Optional[str] = None) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(level)
    # 中文：返回可直接使用的 Logger，避免重复配置
    return logger

"""
日志管理模块
配置和管理系统日志
"""

import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler


def setup_logger(log_dir: str = "logs", log_level: str = "INFO") -> logging.Logger:
    """
    设置日志系统
    
    Args:
        log_dir: 日志目录
        log_level: 日志级别
    
    Returns:
        Logger实例
    """
    # 创建日志目录
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # 日志文件名（带时间戳）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"trading_{timestamp}.log")
    
    # 创建logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # 清除现有handlers
    logger.handlers.clear()
    
    # 文件handler（带轮转）
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    
    # 控制台handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level.upper()))
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    
    # 添加handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    logger.info("=" * 80)
    logger.info("日志系统已启动")
    logger.info(f"日志文件: {log_file}")
    logger.info(f"日志级别: {log_level}")
    logger.info("=" * 80)
    
    return logger


def log_trade(logger: logging.Logger, trade_info: dict):
    """
    记录交易信息
    
    Args:
        logger: Logger实例
        trade_info: 交易信息字典
    """
    logger.info("=" * 80)
    logger.info("交易记录")
    logger.info(f"交易对: {trade_info.get('symbol')}")
    logger.info(f"操作: {trade_info.get('action')}")
    logger.info(f"开仓价: {trade_info.get('entry_price')}")
    logger.info(f"平仓价: {trade_info.get('close_price')}")
    logger.info(f"数量: {trade_info.get('size')}")
    logger.info(f"盈亏: {trade_info.get('pnl')} USDT ({trade_info.get('pnl_pct')}%)")
    logger.info(f"开仓时间: {trade_info.get('entry_time')}")
    logger.info(f"平仓时间: {trade_info.get('close_time')}")
    logger.info("=" * 80)


def log_signal(logger: logging.Logger, signal_info: dict):
    """
    记录信号信息
    
    Args:
        logger: Logger实例
        signal_info: 信号信息字典
    """
    logger.info("-" * 80)
    logger.info(f"信号生成: {signal_info.get('symbol')}")
    logger.info(f"信号类型: {signal_info.get('signal')}")
    logger.info(f"当前价格: {signal_info.get('price')}")
    logger.info(f"MBO: {signal_info.get('mbo')}, MBI: {signal_info.get('mbi')}")
    logger.info(f"系绳线: {signal_info.get('rope_line')}")
    logger.info(f"当前持仓: {signal_info.get('position')}")
    logger.info("-" * 80)


def log_error(logger: logging.Logger, error_info: dict):
    """
    记录错误信息
    
    Args:
        logger: Logger实例
        error_info: 错误信息字典
    """
    logger.error("!" * 80)
    logger.error(f"错误发生: {error_info.get('location')}")
    logger.error(f"错误类型: {error_info.get('error_type')}")
    logger.error(f"错误信息: {error_info.get('message')}")
    logger.error("!" * 80)
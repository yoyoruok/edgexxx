"""
配置管理模块
集中管理所有系统配置，包括API信息、交易参数等
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List
from dotenv import load_dotenv

load_dotenv()


@dataclass
class TradingPairConfig:
    """单个交易对配置"""
    contract_id: str
    symbol: str
    position_size: float  # 仓位大小（USDT）
    leverage: int  # 杠杆倍数
    order_size: float  # 单次成交数量
    tick_size: float  # 价格精度
    size_precision: int = 3  # 数量精度
    
    
@dataclass
class StrategyConfig:
    """策略配置"""
    # MBO/MBI 指标参数
    ma_short_period: int = 25  # 短周期移动平均
    ma_long_period: int = 200  # 长周期移动平均
    
    # 系绳线指标参数
    rope_period: int = 50  # 系绳线周期
    
    # 风险管理
    stop_loss_pct: float = 0.02  # 止损百分比 (2%)
    take_profit_pct: float = 0.05  # 止盈百分比 (5%)
    slippage: float = 0.001  # 滑点 (0.1%)
    
    # K线周期
    timeframe: str = "15m"  # 可选: 15m, 1h, 4h
    
    # 回测参数
    backtest_start: str = ""  # 回测开始时间
    backtest_end: str = ""  # 回测结束时间


@dataclass
class APIConfig:
    """API配置"""
    base_url: str = field(default_factory=lambda: os.getenv("EDGEX_BASE_URL", "https://pro.edgex.exchange"))
    ws_url: str = field(default_factory=lambda: os.getenv("EDGEX_WS_URL", "wss://quote.edgex.exchange"))
    account_id: int = field(default_factory=lambda: int(os.getenv("EDGEX_ACCOUNT_ID", "0")))
    stark_private_key: str = field(default_factory=lambda: os.getenv("EDGEX_STARK_PRIVATE_KEY", ""))
    
    # API限速
    max_requests_per_second: int = 10
    max_orders_per_minute: int = 100


class Config:
    """主配置类"""
    
    def __init__(self):
        self.api = APIConfig()
        self.strategy = StrategyConfig()
        
        # 交易对配置
        self.trading_pairs: Dict[str, TradingPairConfig] = {
            "BTCUSDT": TradingPairConfig(
                contract_id="10000001",
                symbol="BTCUSDT",
                position_size=1000.0,  # 1000 USDT
                leverage=5,
                order_size=0.01,  # 0.01 BTC
                tick_size=0.1,
                size_precision=3
            ),
            "ETHUSDT": TradingPairConfig(
                contract_id="10000002",
                symbol="ETHUSDT",
                position_size=500.0,  # 500 USDT
                leverage=5,
                order_size=0.1,  # 0.1 ETH
                tick_size=0.01,
                size_precision=3
            ),
        }
        
        # 日志配置
        self.log_dir = "logs"
        self.log_level = "INFO"
        
        # 回测配置
        self.backtest_mode = False
        
    def get_pair_config(self, symbol: str) -> TradingPairConfig:
        """获取交易对配置"""
        return self.trading_pairs.get(symbol)
    
    def get_all_contract_ids(self) -> List[str]:
        """获取所有合约ID"""
        return [pair.contract_id for pair in self.trading_pairs.values()]
    
    def validate(self) -> bool:
        """验证配置是否完整"""
        if not self.api.account_id or not self.api.stark_private_key:
            raise ValueError("请设置 EDGEX_ACCOUNT_ID 和 EDGEX_STARK_PRIVATE_KEY 环境变量")
        
        if self.strategy.timeframe not in ["15m", "1h", "4h"]:
            raise ValueError("K线周期必须是 15m, 1h 或 4h")
        
        return True


# 全局配置实例
config = Config()
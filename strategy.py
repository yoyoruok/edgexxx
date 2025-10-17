"""
策略模块
实现MBO/MBI指标和系绳线指标，生成交易信号
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class SignalType(Enum):
    """信号类型"""
    NONE = "NONE"
    LONG = "LONG"  # 开多/持多
    SHORT = "SHORT"  # 开空/持空
    CLOSE_LONG = "CLOSE_LONG"  # 平多
    CLOSE_SHORT = "CLOSE_SHORT"  # 平空


class Position(Enum):
    """持仓状态"""
    EMPTY = "EMPTY"  # 空仓
    LONG = "LONG"  # 持多
    SHORT = "SHORT"  # 持空


class Strategy:
    """量化交易策略"""
    
    def __init__(self, ma_short: int = 25, ma_long: int = 200, rope_period: int = 50):
        """
        初始化策略
        
        Args:
            ma_short: 短周期移动平均
            ma_long: 长周期移动平均
            rope_period: 系绳线周期
        """
        self.ma_short = ma_short
        self.ma_long = ma_long
        self.rope_period = rope_period
        
        # 每个合约的状态
        self.contract_states: Dict[str, Dict] = {}
        
        logger.info(f"策略初始化: MA({ma_short},{ma_long}), 系绳线周期={rope_period}")
    
    def calculate_mbo_mbi(self, df: pd.DataFrame) -> Tuple[float, float]:
        """
        计算MBO和MBI指标
        
        MBO = MA(25) - MA(200)
        MBI = 当前MBO - 上一个MBO
        
        Args:
            df: K线数据DataFrame，必须包含'close'列
        
        Returns:
            (mbo, mbi) 元组
        """
        if len(df) < self.ma_long:
            logger.warning(f"数据不足，需要至少{self.ma_long}根K线")
            return 0.0, 0.0
        
        # 创建副本避免警告
        df = df.copy()
        
        # 计算移动平均
        df['ma_short'] = df['close'].rolling(window=self.ma_short).mean()
        df['ma_long'] = df['close'].rolling(window=self.ma_long).mean()
        
        # 计算MBO
        df['mbo'] = df['ma_short'] - df['ma_long']
        
        # 计算MBI（当前MBO - 上一个MBO）
        df['mbi'] = df['mbo'].diff()
        
        # 获取最新值
        mbo = df['mbo'].iloc[-1]
        mbi = df['mbi'].iloc[-1]
        
        logger.debug(f"MBO={mbo:.2f}, MBI={mbi:.2f}")
        return mbo, mbi
    
    def calculate_rope_line(self, df: pd.DataFrame) -> float:
        """
        计算系绳线指标
        
        MS = (HHV(H, 50) + LLV(L, 50)) / 2
        
        Args:
            df: K线数据DataFrame，必须包含'high'和'low'列
        
        Returns:
            系绳线价格
        """
        if len(df) < self.rope_period:
            logger.warning(f"数据不足，需要至少{self.rope_period}根K线")
            return 0.0
        
        # 计算过去N期的最高价和最低价
        highest = df['high'].rolling(window=self.rope_period).max()
        lowest = df['low'].rolling(window=self.rope_period).min()
        
        # 计算系绳线
        rope_line = (highest + lowest) / 2
        
        result = rope_line.iloc[-1]
        logger.debug(f"系绳线={result:.2f}")
        return result
    
    def generate_signal(
        self, 
        contract_id: str,
        df: pd.DataFrame,
        current_position: Position,
        current_price: float
    ) -> SignalType:
        """
        生成交易信号
        
        Args:
            contract_id: 合约ID
            df: K线数据
            current_position: 当前持仓状态
            current_price: 当前价格
        
        Returns:
            交易信号
        """
        # 计算指标
        mbo, mbi = self.calculate_mbo_mbi(df)
        rope_line = self.calculate_rope_line(df)
        
        # 记录状态
        if contract_id not in self.contract_states:
            self.contract_states[contract_id] = {}
        
        state = self.contract_states[contract_id]
        state['mbo'] = mbo
        state['mbi'] = mbi
        state['rope_line'] = rope_line
        state['current_price'] = current_price
        
        # 检查是否在同一周期内已经发出信号
        current_timestamp = df.index[-1]
        if 'last_signal_time' in state and state['last_signal_time'] == current_timestamp:
            logger.debug(f"{contract_id}: 当前周期已有信号，跳过")
            return SignalType.NONE
        
        signal = SignalType.NONE
        
        # 策略逻辑
        if mbi > 0:
            # MBI为正，多头趋势
            logger.debug(f"{contract_id}: MBI>0, 多头趋势")
            
            if current_price > rope_line:
                # 价格突破系绳线
                logger.info(f"{contract_id}: 价格突破系绳线 {current_price:.2f} > {rope_line:.2f}")
                
                if current_position == Position.EMPTY:
                    signal = SignalType.LONG
                    logger.info(f"{contract_id}: 空仓 -> 开多")
                
                elif current_position == Position.SHORT:
                    signal = SignalType.LONG  # 会先平空再开多
                    logger.info(f"{contract_id}: 持空 -> 平空开多")
                
                elif current_position == Position.LONG:
                    logger.debug(f"{contract_id}: 已持多，不做动作")
                    signal = SignalType.NONE
            
            elif current_price < rope_line and current_position == Position.LONG:
                # 跌破系绳线，止盈
                logger.info(f"{contract_id}: 跌破系绳线 {current_price:.2f} < {rope_line:.2f}, 止盈")
                signal = SignalType.CLOSE_LONG
        
        elif mbi < 0:
            # MBI为负，空头趋势
            logger.debug(f"{contract_id}: MBI<0, 空头趋势")
            
            if current_price < rope_line:
                # 价格跌破系绳线
                logger.info(f"{contract_id}: 价格跌破系绳线 {current_price:.2f} < {rope_line:.2f}")
                
                if current_position == Position.EMPTY:
                    signal = SignalType.SHORT
                    logger.info(f"{contract_id}: 空仓 -> 开空")
                
                elif current_position == Position.LONG:
                    signal = SignalType.SHORT  # 会先平多再开空
                    logger.info(f"{contract_id}: 持多 -> 平多开空")
                
                elif current_position == Position.SHORT:
                    logger.debug(f"{contract_id}: 已持空，不做动作")
                    signal = SignalType.NONE
            
            elif current_price > rope_line and current_position == Position.SHORT:
                # 突破系绳线，止盈
                logger.info(f"{contract_id}: 突破系绳线 {current_price:.2f} > {rope_line:.2f}, 止盈")
                signal = SignalType.CLOSE_SHORT
        
        else:
            logger.debug(f"{contract_id}: MBI=0, 无明确趋势")
        
        # 记录信号时间
        if signal != SignalType.NONE:
            state['last_signal_time'] = current_timestamp
        
        return signal
    
    def check_stop_loss(
        self,
        contract_id: str,
        entry_price: float,
        current_price: float,
        position: Position,
        stop_loss_pct: float
    ) -> bool:
        """
        检查是否触发止损
        
        Args:
            contract_id: 合约ID
            entry_price: 开仓价格
            current_price: 当前价格
            position: 持仓方向
            stop_loss_pct: 止损百分比
        
        Returns:
            是否触发止损
        """
        if position == Position.LONG:
            loss_pct = (entry_price - current_price) / entry_price
            if loss_pct >= stop_loss_pct:
                logger.warning(f"{contract_id}: 触发多单止损 {loss_pct*100:.2f}%")
                return True
        
        elif position == Position.SHORT:
            loss_pct = (current_price - entry_price) / entry_price
            if loss_pct >= stop_loss_pct:
                logger.warning(f"{contract_id}: 触发空单止损 {loss_pct*100:.2f}%")
                return True
        
        return False
    
    def check_take_profit(
        self,
        contract_id: str,
        entry_price: float,
        current_price: float,
        position: Position,
        take_profit_pct: float
    ) -> bool:
        """
        检查是否触发止盈
        
        Args:
            contract_id: 合约ID
            entry_price: 开仓价格
            current_price: 当前价格
            position: 持仓方向
            take_profit_pct: 止盈百分比
        
        Returns:
            是否触发止盈
        """
        if position == Position.LONG:
            profit_pct = (current_price - entry_price) / entry_price
            if profit_pct >= take_profit_pct:
                logger.info(f"{contract_id}: 触发多单止盈 {profit_pct*100:.2f}%")
                return True
        
        elif position == Position.SHORT:
            profit_pct = (entry_price - current_price) / entry_price
            if profit_pct >= take_profit_pct:
                logger.info(f"{contract_id}: 触发空单止盈 {profit_pct*100:.2f}%")
                return True
        
        return False
    
    def get_state(self, contract_id: str) -> Dict:
        """获取合约当前状态"""
        return self.contract_states.get(contract_id, {})
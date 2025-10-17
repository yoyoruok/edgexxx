"""
纯系绳线策略 (Rope Line Strategy) - 完整修复版
基于MetaStock公式: (HHV(H,50) + LLV(L,50)) / 2

修复内容:
1. 排除当前未完成的K线进行计算
2. 只在K线周期完成时更新系绳线
3. 增加详细的计算日志

交易规则:
1. 收盘价突破系绳线(向上):
   - 空仓 → 开多
   - 持空 → 平空开多
   
2. 收盘价跌破系绳线(向下):
   - 空仓 → 开空
   - 持多 → 平多开空
"""

import numpy as np
import pandas as pd
from typing import Dict
from enum import Enum
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class SignalType(Enum):
    """信号类型"""
    NONE = "NONE"
    LONG = "LONG"  # 开多/平空开多
    SHORT = "SHORT"  # 开空/平多开空
    CLOSE_LONG = "CLOSE_LONG"  # 平多
    CLOSE_SHORT = "CLOSE_SHORT"  # 平空


class Position(Enum):
    """持仓状态"""
    EMPTY = "EMPTY"  # 空仓
    LONG = "LONG"  # 持多
    SHORT = "SHORT"  # 持空


class RopeLineStrategy:
    """纯系绳线策略 - 完整修复版"""
    
    def __init__(self, rope_period: int = 50):
        """
        初始化策略
        
        Args:
            rope_period: 系绳线周期,默认50
        """
        self.rope_period = rope_period
        
        # 每个合约的状态
        self.contract_states: Dict[str, Dict] = {}
        
        logger.info(f"纯系绳线策略初始化: 周期={rope_period}")
    
    def calculate_rope_line(self, df: pd.DataFrame, exclude_current: bool = True) -> float:
        """
        计算系绳线 - 修复版
        
        公式: RopeLine = (HHV(H, 50) + LLV(L, 50)) / 2
        
        重要修复: 排除最后一根未完成的K线
        
        Args:
            df: K线数据DataFrame,必须包含'high'和'low'列
            exclude_current: 是否排除当前未完成K线(默认True)
        
        Returns:
            系绳线价格
        """
        # 检查数据量
        required_length = self.rope_period + 1 if exclude_current else self.rope_period
        if len(df) < required_length:
            logger.warning(f"数据不足,需要至少{required_length}根K线,当前只有{len(df)}根")
            return 0.0
        
        # ===== 关键修复: 排除最后一根未完成的K线 =====
        if exclude_current:
            # 使用除了最后一根之外的所有K线
            df_for_calc = df.iloc[:-1]
            logger.debug(f"排除当前未完成K线,使用前{len(df_for_calc)}根已完成K线计算系绳线")
        else:
            df_for_calc = df
            logger.debug(f"使用全部{len(df_for_calc)}根K线计算系绳线(包含未完成K线)")
        
        # 再次检查数据是否足够
        if len(df_for_calc) < self.rope_period:
            logger.warning(f"排除当前K线后数据不足,需要至少{self.rope_period}根已完成K线")
            return 0.0
        
        # 取最近rope_period根K线进行计算
        recent_data = df_for_calc.iloc[-self.rope_period:]
        
        # 计算最高价和最低价
        highest = recent_data['high'].max()
        lowest = recent_data['low'].min()
        
        # 计算系绳线
        rope_line = (highest + lowest) / 2
        
        # 详细日志
        logger.debug(f"系绳线计算详情:")
        logger.debug(f"  - 原始K线总数: {len(df)}")
        logger.debug(f"  - 用于计算K线数: {len(df_for_calc)} (排除{1 if exclude_current else 0}根未完成)")
        logger.debug(f"  - 计算区间: 最近{self.rope_period}根已完成K线")
        logger.debug(f"  - 时间范围: {recent_data.index[0]} 至 {recent_data.index[-1]}")
        logger.debug(f"  - HHV(最高价): {highest:.2f}")
        logger.debug(f"  - LLV(最低价): {lowest:.2f}")
        logger.debug(f"  - 系绳线价格: {rope_line:.2f}")
        
        return rope_line
    
    def generate_signal(
        self, 
        contract_id: str,
        df: pd.DataFrame,
        current_position: Position,
        current_price: float
    ) -> SignalType:
        """
        生成交易信号 - 基于实时价格
        
        Args:
            contract_id: 合约ID
            df: K线历史数据
            current_position: 当前持仓状态
            current_price: 当前实时价格(不是收盘价,是实时市场价格)
        
        Returns:
            交易信号
        """
        # 计算系绳线(排除未完成K线)
        rope_line = self.calculate_rope_line(df, exclude_current=True)
        
        if rope_line == 0.0:
            logger.warning(f"{contract_id}: 系绳线计算失败,数据不足")
            return SignalType.NONE
        
        # 记录状态
        if contract_id not in self.contract_states:
            self.contract_states[contract_id] = {}
        
        state = self.contract_states[contract_id]
        
        # 保存上一次的价格位置(用于判断穿越)
        prev_price = state.get('current_price', current_price)
        prev_rope = state.get('rope_line', rope_line)
        
        # 更新当前状态
        state['rope_line'] = rope_line
        state['current_price'] = current_price
        state['last_update_time'] = datetime.now()
        
        # 检查是否在同一周期内已经发出信号(防止重复信号)
        current_timestamp = df.index[-1]
        if 'last_signal_time' in state and state['last_signal_time'] == current_timestamp:
            logger.debug(f"{contract_id}: 当前周期已有信号,跳过")
            return SignalType.NONE
        
        signal = SignalType.NONE
        
        # ========================================
        # 策略逻辑 - 基于实时价格与系绳线的关系
        # ========================================
        
        # 情况1: 实时价格突破系绳线(向上)
        if current_price > rope_line:
            logger.debug(f"{contract_id}: 实时价格在系绳线上方 {current_price:.2f} > {rope_line:.2f}")
            
            if current_position == Position.EMPTY:
                # 空仓 -> 开多
                signal = SignalType.LONG
                logger.info(f"{contract_id}: 实时价格突破系绳线,空仓 -> 开多 (价格:{current_price:.2f}, 系绳线:{rope_line:.2f})")
            
            elif current_position == Position.SHORT:
                # 持空 -> 平空开多
                signal = SignalType.LONG
                logger.info(f"{contract_id}: 实时价格突破系绳线,持空 -> 平空开多 (价格:{current_price:.2f}, 系绳线:{rope_line:.2f})")
            
            elif current_position == Position.LONG:
                # 已持多,不做动作
                logger.debug(f"{contract_id}: 已持多,继续持有")
                signal = SignalType.NONE
        
        # 情况2: 实时价格低于系绳线(向下)
        elif current_price < rope_line:
            logger.debug(f"{contract_id}: 实时价格在系绳线下方 {current_price:.2f} < {rope_line:.2f}")
            
            if current_position == Position.EMPTY:
                # 空仓 -> 开空
                signal = SignalType.SHORT
                logger.info(f"{contract_id}: 实时价格跌破系绳线,空仓 -> 开空 (价格:{current_price:.2f}, 系绳线:{rope_line:.2f})")
            
            elif current_position == Position.LONG:
                # 持多 -> 平多开空
                signal = SignalType.SHORT
                logger.info(f"{contract_id}: 实时价格跌破系绳线,持多 -> 平多开空 (价格:{current_price:.2f}, 系绳线:{rope_line:.2f})")
            
            elif current_position == Position.SHORT:
                # 已持空,不做动作
                logger.debug(f"{contract_id}: 已持空,继续持有")
                signal = SignalType.NONE
        
        else:
            # 价格正好等于系绳线(极少情况)
            logger.debug(f"{contract_id}: 价格等于系绳线 {current_price:.2f} = {rope_line:.2f}")
        
        # 记录信号时间
        if signal != SignalType.NONE:
            state['last_signal_time'] = current_timestamp
            logger.info(f"{contract_id}: 生成信号 {signal.value}")
        
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
            position: 当前持仓
            stop_loss_pct: 止损百分比(如0.02表示2%)
        
        Returns:
            是否触发止损
        """
        if position == Position.LONG:
            # 多单止损: 价格下跌超过止损比例
            loss_pct = (entry_price - current_price) / entry_price
            if loss_pct >= stop_loss_pct:
                logger.info(f"{contract_id}: 多单触发止损 {loss_pct*100:.2f}%")
                return True
        
        elif position == Position.SHORT:
            # 空单止损: 价格上涨超过止损比例
            loss_pct = (current_price - entry_price) / entry_price
            if loss_pct >= stop_loss_pct:
                logger.info(f"{contract_id}: 空单触发止损 {loss_pct*100:.2f}%")
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
            position: 当前持仓
            take_profit_pct: 止盈百分比(如0.05表示5%)
        
        Returns:
            是否触发止盈
        """
        if position == Position.LONG:
            # 多单止盈: 价格上涨超过止盈比例
            profit_pct = (current_price - entry_price) / entry_price
            if profit_pct >= take_profit_pct:
                logger.info(f"{contract_id}: 多单触发止盈 {profit_pct*100:.2f}%")
                return True
        
        elif position == Position.SHORT:
            # 空单止盈: 价格下跌超过止盈比例
            profit_pct = (entry_price - current_price) / entry_price
            if profit_pct >= take_profit_pct:
                logger.info(f"{contract_id}: 空单触发止盈 {profit_pct*100:.2f}%")
                return True
        
        return False
    
    def get_state(self, contract_id: str) -> Dict:
        """
        获取合约状态
        
        Args:
            contract_id: 合约ID
        
        Returns:
            状态字典,包含rope_line, current_price等信息
        """
        return self.contract_states.get(contract_id, {})


# ========================================
# 使用示例和测试代码
# ========================================
if __name__ == "__main__":
    """
    测试代码 - 验证系绳线计算逻辑
    """
    import pandas as pd
    from datetime import datetime, timedelta
    
    print("=" * 80)
    print("纯系绳线策略测试")
    print("=" * 80)
    
    # 创建模拟数据 - 51根K线
    dates = pd.date_range(end=datetime.now(), periods=51, freq='15min')
    np.random.seed(42)
    prices = 50000 + np.cumsum(np.random.randn(51) * 100)
    
    df = pd.DataFrame({
        'open': prices,
        'high': prices + np.abs(np.random.randn(51) * 50),
        'low': prices - np.abs(np.random.randn(51) * 50),
        'close': prices,
        'volume': np.random.randint(100, 1000, 51)
    }, index=dates)
    
    print(f"\n生成测试数据: {len(df)}根K线")
    print(f"时间范围: {df.index[0]} 至 {df.index[-1]}")
    print(f"价格范围: {df['low'].min():.2f} - {df['high'].max():.2f}")
    
    # 创建策略
    strategy = RopeLineStrategy(rope_period=50)
    
    # 测试1: 排除未完成K线的计算
    print("\n" + "=" * 80)
    print("测试1: 排除未完成K线计算系绳线")
    print("=" * 80)
    rope_line_1 = strategy.calculate_rope_line(df, exclude_current=True)
    print(f"✓ 系绳线(排除最后1根): {rope_line_1:.2f}")
    
    # 测试2: 包含未完成K线的计算(对比)
    print("\n" + "=" * 80)
    print("测试2: 包含未完成K线计算系绳线(对比)")
    print("=" * 80)
    rope_line_2 = strategy.calculate_rope_line(df, exclude_current=False)
    print(f"✓ 系绳线(包含最后1根): {rope_line_2:.2f}")
    
    # 比较差异
    diff = abs(rope_line_1 - rope_line_2)
    print(f"\n差异: {diff:.2f} USDT ({diff/rope_line_1*100:.4f}%)")
    
    # 测试3: 信号生成
    print("\n" + "=" * 80)
    print("测试3: 信号生成测试")
    print("=" * 80)
    
    current_position = Position.EMPTY
    current_price = df['close'].iloc[-1]
    
    print(f"当前价格: {current_price:.2f}")
    print(f"系绳线: {rope_line_1:.2f}")
    print(f"持仓状态: {current_position.value}")
    
    signal = strategy.generate_signal(
        "10000001",
        df,
        current_position,
        current_price
    )
    
    print(f"\n✓ 生成信号: {signal.value}")
    
    # 测试4: 模拟交易流程（需要生成更多K线数据）
    print("\n" + "=" * 80)
    print("测试4: 模拟交易流程")
    print("=" * 80)
    
    # 生成更多K线用于模拟（至少需要51根基础 + 10根测试）
    dates_extended = pd.date_range(end=datetime.now(), periods=61, freq='15min')
    np.random.seed(42)
    prices_extended = 50000 + np.cumsum(np.random.randn(61) * 100)
    
    df_extended = pd.DataFrame({
        'open': prices_extended,
        'high': prices_extended + np.abs(np.random.randn(61) * 50),
        'low': prices_extended - np.abs(np.random.randn(61) * 50),
        'close': prices_extended,
        'volume': np.random.randint(100, 1000, 61)
    }, index=dates_extended)
    
    print(f"生成扩展数据: {len(df_extended)}根K线用于模拟")
    
    current_position = Position.EMPTY
    trade_count = 0
    
    # 从第51根开始测试（前51根用于计算系绳线）
    for i in range(51, 61):
        current_data = df_extended.iloc[:i+1]
        current_price = df_extended['close'].iloc[i]
        
        signal = strategy.generate_signal(
            "10000001",
            current_data,
            current_position,
            current_price
        )
        
        if signal == SignalType.LONG and current_position != Position.LONG:
            print(f"{df_extended.index[i]}: 开多 @ {current_price:.2f}")
            current_position = Position.LONG
            trade_count += 1
        elif signal == SignalType.SHORT and current_position != Position.SHORT:
            print(f"{df_extended.index[i]}: 开空 @ {current_price:.2f}")
            current_position = Position.SHORT
            trade_count += 1
    
    if trade_count == 0:
        print("10个周期内没有产生交易信号（价格未穿越系绳线）")
    else:
        print(f"\n总共产生 {trade_count} 笔交易")
    
    # 测试5: 验证系绳线稳定性
    print("\n" + "=" * 80)
    print("测试5: 验证系绳线更新时机")
    print("=" * 80)
    
    print("\n演示: 在K线周期内，系绳线应该保持不变")
    print("-" * 80)
    
    # 使用前52根K线
    test_df = df_extended.iloc[:52]
    
    # 第一次计算（基于前51根，排除第52根）
    rope1 = strategy.calculate_rope_line(test_df, exclude_current=True)
    print(f"时刻1 (52根K线，排除最后1根): 系绳线 = {rope1:.2f}")
    
    # 模拟价格变化，但K线未完成
    test_df_modified = test_df.copy()
    test_df_modified.iloc[-1, test_df_modified.columns.get_loc('close')] += 100  # 价格上涨
    test_df_modified.iloc[-1, test_df_modified.columns.get_loc('high')] += 150   # 最高价上涨
    
    # 第二次计算（K线未完成，但价格变化了）
    rope2 = strategy.calculate_rope_line(test_df_modified, exclude_current=True)
    print(f"时刻2 (当前K线价格变化，但仍排除): 系绳线 = {rope2:.2f}")
    
    # 验证
    if rope1 == rope2:
        print(f"\n✅ 验证通过: 系绳线保持稳定，未受当前未完成K线影响")
    else:
        print(f"\n❌ 验证失败: 系绳线不应该变化")
    
    print("\n" + "-" * 80)
    print("说明: 只要当前K线未完成，系绳线就不会变化")
    print("      只有当K线完成（新的周期开始）时，系绳线才会更新")
    
    print("\n" + "=" * 80)
    print("测试完成!")
    print("=" * 80)
    print("\n提示: 在实际使用中,系统会自动排除未完成K线")
    print("      系绳线将更加稳定,只在K线完成时更新")
"""
回测模块
基于历史数据回测策略表现
"""

import pandas as pd
from typing import Dict, List
import logging
from datetime import datetime

from strategy import Strategy, SignalType, Position
from precision_manager import precision_manager

logger = logging.getLogger(__name__)


class Backtest:
    """回测引擎"""
    
    def __init__(
        self,
        strategy: Strategy,
        initial_capital: float = 10000.0,
        slippage: float = 0.001,
        commission: float = 0.0004
    ):
        """
        初始化回测引擎
        
        Args:
            strategy: 策略实例
            initial_capital: 初始资金
            slippage: 滑点
            commission: 手续费率
        """
        self.strategy = strategy
        self.initial_capital = initial_capital
        self.slippage = slippage
        self.commission = commission
        
        # 回测状态
        self.capital = initial_capital
        self.positions: Dict[str, Dict] = {}
        self.trades: List[Dict] = []
        self.equity_curve: List[Dict] = []
        
        logger.info(f"回测引擎初始化: 资金={initial_capital}, 滑点={slippage}, 手续费={commission}")
    
    def run(
        self,
        contract_id: str,
        symbol: str,
        df: pd.DataFrame,
        position_size: float,
        stop_loss_pct: float = 0.02,
        take_profit_pct: float = 0.05
    ) -> Dict:
        """
        运行回测
        
        Args:
            contract_id: 合约ID
            symbol: 交易对符号
            df: K线数据
            position_size: 仓位大小
            stop_loss_pct: 止损百分比
            take_profit_pct: 止盈百分比
        
        Returns:
            回测结果
        """
        logger.info(f"开始回测: {symbol}, 数据点数={len(df)}")
        
        # 初始化状态
        self.capital = self.initial_capital
        self.positions = {}
        self.trades = []
        self.equity_curve = []
        
        current_position = Position.EMPTY
        entry_price = 0.0
        entry_time = None
        
        # 遍历每根K线
        for i in range(self.strategy.ma_long, len(df)):
            # 获取当前数据
            current_data = df.iloc[:i+1]
            current_price = current_data['close'].iloc[-1]
            current_time = current_data.index[-1]
            
            # 检查止损止盈
            if current_position != Position.EMPTY:
                # 止损检查
                if self.strategy.check_stop_loss(
                    contract_id, entry_price, current_price, current_position, stop_loss_pct
                ):
                    self._close_position(
                        symbol, current_position, entry_price, current_price,
                        position_size, entry_time, current_time, "止损"
                    )
                    current_position = Position.EMPTY
                    continue
                
                # 止盈检查
                if self.strategy.check_take_profit(
                    contract_id, entry_price, current_price, current_position, take_profit_pct
                ):
                    self._close_position(
                        symbol, current_position, entry_price, current_price,
                        position_size, entry_time, current_time, "止盈"
                    )
                    current_position = Position.EMPTY
                    continue
            
            # 生成信号
            signal = self.strategy.generate_signal(
                contract_id, current_data, current_position, current_price
            )
            
            # 执行信号
            if signal == SignalType.LONG:
                if current_position == Position.SHORT:
                    # 先平空
                    self._close_position(
                        symbol, current_position, entry_price, current_price,
                        position_size, entry_time, current_time, "平空"
                    )
                
                # 开多
                entry_price = self._apply_slippage(current_price, "BUY")
                entry_time = current_time
                current_position = Position.LONG
                logger.debug(f"{current_time}: 开多 @ {entry_price}")
            
            elif signal == SignalType.SHORT:
                if current_position == Position.LONG:
                    # 先平多
                    self._close_position(
                        symbol, current_position, entry_price, current_price,
                        position_size, entry_time, current_time, "平多"
                    )
                
                # 开空
                entry_price = self._apply_slippage(current_price, "SELL")
                entry_time = current_time
                current_position = Position.SHORT
                logger.debug(f"{current_time}: 开空 @ {entry_price}")
            
            elif signal == SignalType.CLOSE_LONG and current_position == Position.LONG:
                self._close_position(
                    symbol, current_position, entry_price, current_price,
                    position_size, entry_time, current_time, "平多"
                )
                current_position = Position.EMPTY
            
            elif signal == SignalType.CLOSE_SHORT and current_position == Position.SHORT:
                self._close_position(
                    symbol, current_position, entry_price, current_price,
                    position_size, entry_time, current_time, "平空"
                )
                current_position = Position.EMPTY
            
            # 记录权益曲线
            unrealized_pnl = 0.0
            if current_position == Position.LONG:
                unrealized_pnl = (current_price - entry_price) * position_size
            elif current_position == Position.SHORT:
                unrealized_pnl = (entry_price - current_price) * position_size
            
            self.equity_curve.append({
                'timestamp': current_time,
                'capital': self.capital,
                'unrealized_pnl': unrealized_pnl,
                'total_equity': self.capital + unrealized_pnl
            })
        
        # 计算回测结果
        results = self._calculate_results(symbol)
        logger.info(f"回测完成: {symbol}")
        
        return results
    
    def _apply_slippage(self, price: float, side: str) -> float:
        """应用滑点"""
        if side == "BUY":
            return price * (1 + self.slippage)
        else:
            return price * (1 - self.slippage)
    
    def _close_position(
        self,
        symbol: str,
        position: Position,
        entry_price: float,
        exit_price: float,
        size: float,
        entry_time: datetime,
        exit_time: datetime,
        reason: str
    ):
        """平仓并记录交易"""
        # 应用滑点
        if position == Position.LONG:
            exit_price = self._apply_slippage(exit_price, "SELL")
            pnl = (exit_price - entry_price) * size
        else:
            exit_price = self._apply_slippage(exit_price, "BUY")
            pnl = (entry_price - exit_price) * size
        
        # 扣除手续费
        commission_cost = (entry_price + exit_price) * size * self.commission
        pnl -= commission_cost
        
        # 更新资金
        self.capital += pnl
        
        # 记录交易
        self.trades.append({
            'symbol': symbol,
            'position': position.value,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'size': size,
            'pnl': pnl,
            'pnl_pct': (pnl / (entry_price * size)) * 100,
            'commission': commission_cost,
            'entry_time': entry_time,
            'exit_time': exit_time,
            'duration': (exit_time - entry_time).total_seconds() / 3600,  # 小时
            'reason': reason
        })
        
        logger.debug(f"{exit_time}: {reason} @ {exit_price}, 盈亏={pnl:.2f}")
    
    def _calculate_results(self, symbol: str) -> Dict:
        """计算回测结果"""
        if not self.trades:
            return {
                'symbol': symbol,
                'total_trades': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'total_return': 0,
                'max_drawdown': 0,
                'sharpe_ratio': 0
            }
        
        # 基本统计
        total_trades = len(self.trades)
        winning_trades = [t for t in self.trades if t['pnl'] > 0]
        losing_trades = [t for t in self.trades if t['pnl'] <= 0]
        
        win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0
        total_pnl = sum(t['pnl'] for t in self.trades)
        total_return = (total_pnl / self.initial_capital) * 100
        
        avg_win = sum(t['pnl'] for t in winning_trades) / len(winning_trades) if winning_trades else 0
        avg_loss = sum(t['pnl'] for t in losing_trades) / len(losing_trades) if losing_trades else 0
        
        # 最大回撤
        equity_df = pd.DataFrame(self.equity_curve)
        equity_df['cummax'] = equity_df['total_equity'].cummax()
        equity_df['drawdown'] = (equity_df['total_equity'] - equity_df['cummax']) / equity_df['cummax']
        max_drawdown = abs(equity_df['drawdown'].min()) * 100
        
        # 夏普比率（简化计算）
        returns = equity_df['total_equity'].pct_change().dropna()
        if len(returns) > 0 and returns.std() > 0:
            sharpe_ratio = (returns.mean() / returns.std()) * (252 ** 0.5)  # 年化
        else:
            sharpe_ratio = 0
        
        return {
            'symbol': symbol,
            'total_trades': total_trades,
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': win_rate * 100,
            'total_pnl': total_pnl,
            'total_return': total_return,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': abs(avg_win / avg_loss) if avg_loss != 0 else 0,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'final_capital': self.capital
        }
    
    def print_results(self, results: Dict):
        """打印回测结果"""
        logger.info("=" * 80)
        logger.info("回测结果")
        logger.info("=" * 80)
        logger.info(f"交易对: {results['symbol']}")
        logger.info(f"总交易次数: {results['total_trades']}")
        logger.info(f"盈利次数: {results['winning_trades']}")
        logger.info(f"亏损次数: {results['losing_trades']}")
        logger.info(f"胜率: {results['win_rate']:.2f}%")
        logger.info(f"总盈亏: {results['total_pnl']:.2f} USDT")
        logger.info(f"总收益率: {results['total_return']:.2f}%")
        logger.info(f"平均盈利: {results['avg_win']:.2f} USDT")
        logger.info(f"平均亏损: {results['avg_loss']:.2f} USDT")
        logger.info(f"盈亏比: {results['profit_factor']:.2f}")
        logger.info(f"最大回撤: {results['max_drawdown']:.2f}%")
        logger.info(f"夏普比率: {results['sharpe_ratio']:.2f}")
        logger.info(f"最终资金: {results['final_capital']:.2f} USDT")
        logger.info("=" * 80)
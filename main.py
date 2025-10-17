"""
量化交易系统主程序
整合所有模块，运行交易或回测
"""

import asyncio
import sys
from datetime import datetime
from edgex_sdk import Client

from config import config
from logger import setup_logger, log_signal, log_trade
from precision_manager import precision_manager
from strategy import Strategy, Position
from data_manager import DataManager
from order_manager import OrderManager
from rate_limiter import rate_limiter
from backtest import Backtest


class TradingBot:
    """交易机器人"""
    
    def __init__(self, backtest_mode: bool = False):
        """
        初始化交易机器人
        
        Args:
            backtest_mode: 是否回测模式
        """
        self.backtest_mode = backtest_mode
        
        # 设置日志
        self.logger = setup_logger(config.log_dir, config.log_level)
        
        # 验证配置
        config.validate()
        
        # 初始化客户端
        if not backtest_mode:
            self.client = Client(
                base_url=config.api.base_url,
                account_id=config.api.account_id,
                stark_private_key=config.api.stark_private_key
            )
            
            # 初始化管理器
            self.data_manager = DataManager(self.client)
            self.order_manager = OrderManager(self.client)
            
            # 配置限速器
            rate_limiter.max_per_second = config.api.max_requests_per_second
            rate_limiter.max_per_minute = config.api.max_orders_per_minute
        
        # 初始化策略
        self.strategy = Strategy(
            ma_short=config.strategy.ma_short_period,
            ma_long=config.strategy.ma_long_period,
            rope_period=config.strategy.rope_period
        )
        
        # 初始化精度管理器
        self._init_precision_manager()
        
        self.logger.info("交易机器人初始化完成")
        self.logger.info(f"运行模式: {'回测' if backtest_mode else '实盘'}")
    
    def _init_precision_manager(self):
        """初始化精度管理器"""
        for symbol, pair_config in config.trading_pairs.items():
            precision_manager.set_contract_info(
                pair_config.contract_id,
                pair_config.tick_size,
                pair_config.size_precision
            )
    
    async def run_live_trading(self):
        """运行实盘交易"""
        self.logger.info("=" * 80)
        self.logger.info("开始实盘交易")
        self.logger.info("=" * 80)
        
        try:
            # 获取账户信息
            await self._check_account()
            
            # 初始化数据
            await self._init_data()
            
            # 主交易循环
            iteration = 0
            while True:
                iteration += 1
                self.logger.info(f"\n{'='*80}\n第 {iteration} 次循环\n{'='*80}")
                
                # 遍历所有交易对
                for symbol, pair_config in config.trading_pairs.items():
                    await self._process_symbol(symbol, pair_config)
                
                # 打印状态
                self._print_status()
                
                # 等待下一个周期
                await self._wait_next_period()
                
        except KeyboardInterrupt:
            self.logger.info("\n收到停止信号，正在退出...")
            await self._shutdown()
        except Exception as e:
            self.logger.error(f"发生错误: {str(e)}")
            import traceback
            traceback.print_exc()
            await self._shutdown()
    
    async def _check_account(self):
        """检查账户状态"""
        self.logger.info("检查账户状态...")
        
        try:
            # 获取账户资产
            assets = await self.client.get_assets()
            
            if assets.get("code") == "SUCCESS":
                data = assets.get("data", {})
                equity = float(data.get("totalEquity", 0))
                available = float(data.get("availableBalance", 0))
                
                self.logger.info(f"账户权益: {equity:.2f} USDT")
                self.logger.info(f"可用余额: {available:.2f} USDT")
            else:
                self.logger.warning("无法获取账户信息")
                
        except Exception as e:
            self.logger.error(f"检查账户失败: {str(e)}")
    
    async def _init_data(self):
        """初始化数据"""
        self.logger.info("初始化K线数据...")
        
        for symbol, pair_config in config.trading_pairs.items():
            # 初始化K线数据（会自动启动实时刷新）
            df = await rate_limiter.execute(
                self.data_manager.initialize_klines,
                pair_config.contract_id,
                config.strategy.timeframe,
                size=300  # 至少300根，用于计算MA200
            )
            
            if df is not None:
                self.logger.info(f"{symbol}: 已加载 {len(df)} 根K线 (实时刷新已启动)")
            else:
                self.logger.error(f"{symbol}: K线数据加载失败")
    
    async def _process_symbol(self, symbol: str, pair_config):
        """处理单个交易对"""
        try:
            # 获取K线数据（数据管理器会自动保持最新）
            df = await self.data_manager.get_klines(
                pair_config.contract_id,
                config.strategy.timeframe
            )
            
            if df is None or len(df) < self.strategy.ma_long:
                self.logger.warning(f"{symbol}: 数据不足，跳过")
                return
            
            # 获取当前价格
            current_price = await rate_limiter.execute(
                self.data_manager.get_current_price,
                pair_config.contract_id
            )
            
            if current_price is None:
                self.logger.warning(f"{symbol}: 无法获取当前价格")
                return
            
            # 记录数据状态
            self.logger.debug(
                f"{symbol}: K线数据 {len(df)} 根, "
                f"最新时间 {df.index[-1]}, "
                f"当前价格 {current_price}"
            )
            
            # 获取当前持仓
            current_position = self.order_manager.get_position(pair_config.contract_id)
            position_info = self.order_manager.get_position_info(pair_config.contract_id)
            
            # 检查止损止盈
            if position_info:
                # 止损检查
                if self.strategy.check_stop_loss(
                    pair_config.contract_id,
                    position_info.entry_price,
                    current_price,
                    current_position,
                    config.strategy.stop_loss_pct
                ):
                    await self.order_manager.close_position(
                        pair_config.contract_id,
                        symbol,
                        current_price,
                        config.strategy.slippage
                    )
                    return
                
                # 止盈检查
                if self.strategy.check_take_profit(
                    pair_config.contract_id,
                    position_info.entry_price,
                    current_price,
                    current_position,
                    config.strategy.take_profit_pct
                ):
                    await self.order_manager.close_position(
                        pair_config.contract_id,
                        symbol,
                        current_price,
                        config.strategy.slippage
                    )
                    return
            
            # 生成信号
            signal = self.strategy.generate_signal(
                pair_config.contract_id,
                df,
                current_position,
                current_price
            )
            
            # 记录信号
            if signal.value != "NONE":
                state = self.strategy.get_state(pair_config.contract_id)
                log_signal(self.logger, {
                    'symbol': symbol,
                    'signal': signal.value,
                    'price': current_price,
                    'mbo': state.get('mbo', 0),
                    'mbi': state.get('mbi', 0),
                    'rope_line': state.get('rope_line', 0),
                    'position': current_position.value
                })
            
            # 执行信号
            if signal.value != "NONE":
                await rate_limiter.execute(
                    self.order_manager.execute_signal,
                    pair_config.contract_id,
                    symbol,
                    signal,
                    current_price,
                    pair_config.order_size,
                    config.strategy.slippage
                )
            
        except Exception as e:
            self.logger.error(f"{symbol}: 处理失败 - {str(e)}")
            import traceback
            traceback.print_exc()
    
    def _print_status(self):
        """打印状态信息"""
        self.logger.info("\n" + "=" * 80)
        self.logger.info("当前状态")
        self.logger.info("=" * 80)
        
        # 打印持仓
        positions = self.order_manager.get_all_positions()
        if positions:
            self.logger.info("\n持仓信息:")
            for contract_id, pos_info in positions.items():
                self.logger.info(
                    f"{pos_info.symbol}: {pos_info.position.value}, "
                    f"开仓价={pos_info.entry_price:.2f}, "
                    f"数量={pos_info.size}, "
                    f"时间={pos_info.entry_time}"
                )
        else:
            self.logger.info("\n当前无持仓")
        
        # 打印限速器统计
        stats = rate_limiter.get_stats()
        self.logger.info(f"\nAPI请求统计:")
        self.logger.info(f"总请求: {stats['total_requests']}")
        self.logger.info(f"延迟次数: {stats['total_delays']}")
        
        # 打印盈亏
        total_pnl = self.order_manager.calculate_total_pnl()
        self.logger.info(f"\n总盈亏: {total_pnl:.2f} USDT")
        
        self.logger.info("=" * 80 + "\n")
    
    async def _wait_next_period(self):
        """等待下一个周期"""
        # 根据K线周期决定等待时间
        wait_time = {
            "15m": 60,  # 每分钟检查一次
            "1h": 300,  # 每5分钟检查一次
            "4h": 600   # 每10分钟检查一次
        }.get(config.strategy.timeframe, 60)
        
        self.logger.info(f"等待 {wait_time} 秒...")
        await asyncio.sleep(wait_time)
    
    async def _shutdown(self):
        """关闭系统"""
        self.logger.info("正在关闭系统...")
        
        # 停止数据自动刷新
        if hasattr(self, 'data_manager'):
            await self.data_manager.close()
            self.logger.info("数据管理器已关闭")
        
        # 打印交易历史
        trades = self.order_manager.get_trade_history()
        if trades:
            self.logger.info(f"\n交易历史 (共{len(trades)}笔):")
            for trade in trades:
                log_trade(self.logger, trade)
        
        # 打印最终盈亏
        total_pnl = self.order_manager.calculate_total_pnl()
        self.logger.info(f"\n最终盈亏: {total_pnl:.2f} USDT")
        
        # 关闭客户端
        if hasattr(self, 'client'):
            try:
                if hasattr(self.client, 'async_client'):
                    if hasattr(self.client.async_client, 'session'):
                        await self.client.async_client.session.close()
            except Exception:
                pass
        
        self.logger.info("系统已关闭")
    
    async def run_backtest(self):
        """运行回测"""
        self.logger.info("=" * 80)
        self.logger.info("开始回测")
        self.logger.info("=" * 80)
        
        import pandas as pd
        import os
        
        # 创建回测引擎
        backtest_engine = Backtest(
            strategy=self.strategy,
            initial_capital=10000.0,
            slippage=config.strategy.slippage,
            commission=0.0004
        )
        
        # 遍历所有交易对
        for symbol, pair_config in config.trading_pairs.items():
            self.logger.info(f"\n{'='*80}")
            self.logger.info(f"回测 {symbol}")
            self.logger.info("=" * 80)
            
            # 构造数据文件路径
            filename = f"data/{symbol}_{config.strategy.timeframe}.csv"
            
            # 检查文件是否存在
            if not os.path.exists(filename):
                self.logger.warning(f"{symbol}: 数据文件不存在: {filename}")
                self.logger.warning(f"请先运行: python prepare_backtest_data.py")
                continue
            
            try:
                # 读取CSV数据
                self.logger.info(f"加载数据文件: {filename}")
                df = pd.read_csv(filename)
                
                # 转换时间戳
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df.set_index('timestamp', inplace=True)
                
                self.logger.info(f"数据加载成功: {len(df)} 根K线")
                self.logger.info(f"时间范围: {df.index[0]} 至 {df.index[-1]}")
                
                # 检查数据是否足够
                if len(df) < self.strategy.ma_long:
                    self.logger.warning(f"{symbol}: 数据不足，需要至少 {self.strategy.ma_long} 根K线")
                    continue
                
                # 运行回测
                self.logger.info(f"开始回测...")
                results = backtest_engine.run(
                    pair_config.contract_id,
                    symbol,
                    df,
                    pair_config.position_size,
                    stop_loss_pct=config.strategy.stop_loss_pct,
                    take_profit_pct=config.strategy.take_profit_pct
                )
                
                # 打印结果
                backtest_engine.print_results(results)
                
            except Exception as e:
                self.logger.error(f"{symbol}: 回测失败 - {str(e)}")
                import traceback
                traceback.print_exc()
        
        self.logger.info("\n" + "=" * 80)
        self.logger.info("回测完成！")
        self.logger.info("=" * 80)


async def main():
    """主函数"""
    # 检查命令行参数
    backtest_mode = "--backtest" in sys.argv
    
    # 创建交易机器人
    bot = TradingBot(backtest_mode=backtest_mode)
    
    # 运行
    if backtest_mode:
        await bot.run_backtest()
    else:
        await bot.run_live_trading()


if __name__ == "__main__":
    print("=" * 80)
    print("EdgeX 量化交易系统")
    print("=" * 80)
    print("使用方法:")
    print("  实盘交易: python main.py")
    print("  回测模式: python main.py --backtest")
    print("=" * 80)
    print()
    
    asyncio.run(main())
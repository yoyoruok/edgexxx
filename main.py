"""
EdgeX量化交易系统 - WebSocket实时版本
实现秒级价格监控和信号生成
"""

import asyncio
import logging
import json
import sys
from datetime import datetime, timedelta
from edgex_sdk import Client, WebSocketManager

from config import config
from rope_line_strategy import RopeLineStrategy, Position, SignalType
from order_manager import OrderManager
from precision_manager import precision_manager
from rate_limiter import rate_limiter
from logger import setup_logger, log_signal, log_trade

# 设置日志
logger = logging.getLogger(__name__)


class RealtimeTradingBot:
    """实时交易机器人 - WebSocket版本"""
    
    def __init__(self):
        """初始化"""
        # 设置日志
        setup_logger(
            log_dir=config.log_dir,
            log_level=config.log_level,
        )
        
        self.logger = logging.getLogger(__name__)
        self.logger.info("=" * 80)
        self.logger.info("实时交易系统启动 - WebSocket版本")
        self.logger.info("=" * 80)
        
        # 创建REST API客户端
        self.client = Client(
            base_url=config.api.base_url,
            account_id=config.api.account_id,
            stark_private_key=config.api.stark_private_key
        )   
        
        # 创建WebSocket管理器
        self.ws_manager = WebSocketManager(
            base_url=config.api.ws_url,
            account_id=config.api.account_id,
            stark_pri_key=config.api.stark_private_key
        )
        
        # 创建策略
        self.strategy = RopeLineStrategy(rope_period=50)
        self.logger.info("策略: 纯系绳线策略 (周期=50)")
        
        # 创建订单管理器
        self.order_manager = OrderManager(self.client)
        
        # 设置精度管理器
        for symbol, pair_config in config.trading_pairs.items():
            precision_manager.set_contract_info(
                pair_config.contract_id,
                pair_config.tick_size,
                pair_config.size_precision
            )
            self.logger.info(
                f"设置合约 {pair_config.contract_id} 精度: "
                f"tick={pair_config.tick_size}, size_precision={pair_config.size_precision}"
            )
        
        # 数据缓存
        self.kline_data = {}  # 存储K线数据
        self.current_prices = {}  # 存储当前价格
        self.rope_lines = {}  # 存储系绳线
        
        # 运行状态
        self.is_running = False
        self.last_signal_time = {}  # 记录最后信号时间，防止重复
        
        # 事件循环引用（将在 start() 中设置）
        self.loop = None
        
        # 价格监控控制
        self.last_log_time = {}  # 记录上次日志时间
        self.price_update_count = {}  # 价格更新计数
        
        self.logger.info("实时交易系统初始化完成")
    
    async def initialize_data(self):
        """初始化K线数据和系绳线"""
        self.logger.info("=" * 80)
        self.logger.info("初始化数据")
        self.logger.info("=" * 80)
        
        for symbol, pair_config in config.trading_pairs.items():
            self.logger.info(f"\n初始化 {symbol}...")
            
            # 获取K线数据
            df = await self.fetch_klines(pair_config.contract_id, size=51)
            
            if df is not None and len(df) >= 51:
                self.kline_data[pair_config.contract_id] = df
                
                # 计算初始系绳线
                rope_line = self.strategy.calculate_rope_line(df, exclude_current=True)
                self.rope_lines[pair_config.contract_id] = rope_line
                
                self.logger.info(f"✓ {symbol}: 加载{len(df)}根K线")
                self.logger.info(f"✓ {symbol}: 初始系绳线 = {rope_line:.2f}")
            else:
                self.logger.error(f"✗ {symbol}: 数据加载失败")
        
        self.logger.info("\n" + "=" * 80)
        self.logger.info("数据初始化完成")
        self.logger.info("=" * 80)
    
    async def fetch_klines(self, contract_id: str, size: int = 51):
        """获取K线数据"""
        try:
            from edgex_sdk.quote.client import GetKLineParams, KlineType, PriceType
            import pandas as pd
            
            params = GetKLineParams(
                contract_id=contract_id,
                kline_type=KlineType.MINUTE_15,
                price_type=PriceType.LAST_PRICE,
                size=size
            )
            
            result = await self.client.quote.get_k_line(params)
            
            if result.get("code") != "SUCCESS":
                self.logger.error(f"获取K线失败: {result.get('errorParam')}")
                return None
            
            # 解析K线
            klines = result.get("data", {}).get("dataList", [])
            
            if not klines:
                return None
            
            data = []
            for k in klines:
                data.append({
                    'timestamp': pd.to_datetime(int(k.get('klineTime', 0)), unit='ms'),
                    'open': float(k.get('open', 0)),
                    'high': float(k.get('high', 0)),
                    'low': float(k.get('low', 0)),
                    'close': float(k.get('close', 0)),
                    'volume': float(k.get('size', 0))
                })
            
            df = pd.DataFrame(data)
            df.set_index('timestamp', inplace=True)
            df.sort_index(inplace=True)
            df = df[~df.index.duplicated(keep='last')]
            
            return df
            
        except Exception as e:
            self.logger.error(f"获取K线异常: {str(e)}")
            return None
    
    def handle_ticker(self, message: str):
        """
        处理实时价格推送 - 核心方法
        每次价格变化都会调用此方法（秒级）
        """
        try:
            data = json.loads(message)
            content = data.get("content", {})
            ticker_list = content.get("data", [])
            
            if not ticker_list:
                return
            
            ticker = ticker_list[0] if isinstance(ticker_list, list) else ticker_list
            
            # 🔍 添加调试日志 - 查看实际数据结构
            self.logger.debug(f"收到ticker数据: {json.dumps(ticker, indent=2)}")
            
            contract_id = ticker.get("contractId")  
            # 🔧 修改价格获取方式 - 尝试多个可能的字段
            new_price = 0.0
            
            # 尝试不同的字段名
            if "lastPrice" in ticker and ticker["lastPrice"]:
                new_price = float(ticker["lastPrice"])
            elif "last" in ticker and ticker["last"]:
                new_price = float(ticker["last"])
            elif "price" in ticker and ticker["price"]:
                new_price = float(ticker["price"])
            elif "close" in ticker and ticker["close"]:
                new_price = float(ticker["close"])
        
            # 🚨 价格验证
            if new_price <= 0:
                self.logger.error(f"❌ 获取到无效价格: {new_price}, ticker数据: {ticker}")
                return
            
            self.logger.debug(f"✓ 获取到有效价格: {new_price}")
            
            # 找到对应的交易对配置
            pair_config = None
            symbol = None
            for sym, cfg in config.trading_pairs.items():
                if cfg.contract_id == contract_id:
                    pair_config = cfg
                    symbol = sym
                    break
            
            if not pair_config:
                return
            
            # 获取旧价格
            old_price = self.current_prices.get(contract_id, new_price)
            
            # 更新当前价格
            self.current_prices[contract_id] = new_price
            
            # 获取系绳线
            rope_line = self.rope_lines.get(contract_id)
            
            if not rope_line:
                return
            
            # 价格更新计数
            if contract_id not in self.price_update_count:
                self.price_update_count[contract_id] = 0
            self.price_update_count[contract_id] += 1
            
            # 价格变化
            price_change = new_price - old_price
            
            # 简化的价格监控日志 - 只在以下情况显示：
            # 1. 每30秒显示一次状态
            # 2. 价格变化超过10美元
            # 3. 价格接近系绳线（±50美元内）
            now = datetime.now()
            last_log = self.last_log_time.get(contract_id)
            time_since_log = (now - last_log).total_seconds() if last_log else 999
            
            should_log = False
            log_reason = ""
            
            # 每30秒显示一次
            if time_since_log >= 30:
                should_log = True
                log_reason = "定期更新"
                self.last_log_time[contract_id] = now
            
            # 价格大幅变化（>10美元）
            elif abs(price_change) > 10:
                should_log = True
                log_reason = "价格大幅波动"
            
            # 价格接近系绳线（±50美元）
            elif abs(new_price - rope_line) <= 50:
                should_log = True
                log_reason = "接近系绳线"
                self.last_log_time[contract_id] = now
            
            if should_log:
                position_str = "上方⬆️" if new_price > rope_line else "下方⬇️"
                distance = abs(new_price - rope_line)
                update_count = self.price_update_count[contract_id]
                
                self.logger.info(
                    f"💰 {symbol}: 价格={new_price:.2f} | 系绳线={rope_line:.2f} | "
                    f"距离={distance:.2f} | {position_str} | "
                    f"更新次数={update_count} [{log_reason}]"
                )
            
            # 检测穿越并生成信号 - 使用线程安全的方式
            if self.loop and self.loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self.check_and_execute(
                        contract_id,
                        symbol,
                        old_price,
                        new_price,
                        rope_line,
                        pair_config
                    ),
                    self.loop
                )
            
        except Exception as e:
            self.logger.error(f"处理价格推送失败: {str(e)}")
    
    async def check_and_execute(
        self,
        contract_id: str,
        symbol: str,
        old_price: float,
        new_price: float,
        rope_line: float,
        pair_config
    ):
        """检测穿越并执行交易"""
        try:
            # 防止重复信号（5秒内不重复）
            now = datetime.now()
            last_time = self.last_signal_time.get(contract_id)
            if last_time and (now - last_time).total_seconds() < 5:
                return
            
            # 获取当前持仓
            current_position = self.order_manager.get_position(contract_id)
            
            # 检测向上穿越
            if old_price <= rope_line and new_price > rope_line:
                self.logger.info("=" * 80)
                self.logger.info(f"🔥 {symbol}: 价格向上突破系绳线！")
                self.logger.info(f"   价格变化: {old_price:.2f} → {new_price:.2f}")
                self.logger.info(f"   系绳线: {rope_line:.2f}")
                self.logger.info("=" * 80)
                
                if current_position == Position.EMPTY:
                    self.logger.info(f"📈 {symbol}: 空仓 → 开多")
                    signal = SignalType.LONG
                elif current_position == Position.SHORT:
                    self.logger.info(f"🔄 {symbol}: 持空 → 平空开多")
                    signal = SignalType.LONG
                else:
                    return
                
                # 执行信号
                await self.execute_signal(contract_id, symbol, signal, new_price, pair_config)
                self.last_signal_time[contract_id] = now
            
            # 检测向下穿越
            elif old_price >= rope_line and new_price < rope_line:
                self.logger.info("=" * 80)
                self.logger.info(f"🔥 {symbol}: 价格向下跌破系绳线！")
                self.logger.info(f"   价格变化: {old_price:.2f} → {new_price:.2f}")
                self.logger.info(f"   系绳线: {rope_line:.2f}")
                self.logger.info("=" * 80)
                
                if current_position == Position.EMPTY:
                    self.logger.info(f"📉 {symbol}: 空仓 → 开空")
                    signal = SignalType.SHORT
                elif current_position == Position.LONG:
                    self.logger.info(f"🔄 {symbol}: 持多 → 平多开空")
                    signal = SignalType.SHORT
                else:
                    return
                
                # 执行信号
                await self.execute_signal(contract_id, symbol, signal, new_price, pair_config)
                self.last_signal_time[contract_id] = now
                
        except Exception as e:
            self.logger.error(f"检测穿越失败: {str(e)}")
    
    async def execute_signal(
        self,
        contract_id: str,
        symbol: str,
        signal: SignalType,
        price: float,
        pair_config
    ):
        """执行交易信号"""
        try:
            self.logger.info(f"🎯 {symbol}: 执行信号 {signal.value} @ {price:.2f}")
            
            # 调用订单管理器执行
            await rate_limiter.execute(
                self.order_manager.execute_signal,
                contract_id,
                symbol,
                signal,
                price,
                pair_config.order_size,
                config.strategy.slippage
            )
            
        except Exception as e:
            self.logger.error(f"执行信号失败: {str(e)}")
    
    def get_next_kline_time(self, interval_minutes: int = 15):
        """
        计算下一个K线周期的开始时间
        
        Args:
            interval_minutes: K线周期（分钟），默认15
        
        Returns:
            下一个K线周期的开始时间
        """
        now = datetime.now()
        
        # 计算当前时间在当天的分钟数
        minutes_since_midnight = now.hour * 60 + now.minute
        
        # 计算当前周期的开始分钟数
        current_period_start = (minutes_since_midnight // interval_minutes) * interval_minutes
        
        # 下一个周期的开始分钟数
        next_period_start = current_period_start + interval_minutes
        
        # 构造下一个周期的开始时间
        next_kline_time = now.replace(
            hour=next_period_start // 60,
            minute=next_period_start % 60,
            second=0,
            microsecond=0
        )
        
        # 如果超过了今天，调整到明天
        if next_kline_time <= now:
            next_kline_time += timedelta(minutes=interval_minutes)
        
        return next_kline_time
    
    async def periodic_rope_update(self):
        """
        定期更新系绳线 - 对齐到K线周期
        在每个15分钟周期开始后立即更新（如14:00、14:15、14:30）
        """
        while self.is_running:
            try:
                # 计算下一个K线周期的开始时间
                next_update_time = self.get_next_kline_time(interval_minutes=15)
                
                # 计算需要等待的秒数
                now = datetime.now()
                wait_seconds = (next_update_time - now).total_seconds()
                
                # 添加1秒延迟，确保新K线已经生成
                wait_seconds += 1
                
                self.logger.info(
                    f"⏰ 下次系绳线更新时间: {next_update_time.strftime('%H:%M:%S')} "
                    f"(等待 {wait_seconds:.0f} 秒)"
                )
                
                # 等待到下一个周期
                await asyncio.sleep(wait_seconds)
                
                # 确保还在运行
                if not self.is_running:
                    break
                
                # 开始更新
                update_start_time = datetime.now()
                self.logger.info("\n" + "🔄" * 40)
                self.logger.info(f"开始更新系绳线 [{update_start_time.strftime('%H:%M:%S')}]")
                
                for symbol, pair_config in config.trading_pairs.items():
                    contract_id = pair_config.contract_id
                    
                    # 获取最新K线
                    df = await self.fetch_klines(contract_id, size=51)
                    
                    if df is not None and len(df) >= 51:
                        # 更新K线缓存
                        self.kline_data[contract_id] = df
                        
                        # 重新计算系绳线
                        old_rope = self.rope_lines.get(contract_id, 0)
                        new_rope = self.strategy.calculate_rope_line(df, exclude_current=True)
                        
                        self.rope_lines[contract_id] = new_rope
                        
                        change = new_rope - old_rope
                        change_pct = (change / old_rope * 100) if old_rope > 0 else 0
                        
                        # 显示当前价格和系绳线的关系
                        current_price = self.current_prices.get(contract_id, 0)
                        distance = abs(current_price - new_rope)
                        position_str = "上方⬆️" if current_price > new_rope else "下方⬇️"
                        
                        self.logger.info(
                            f"📊 {symbol}: 系绳线 {old_rope:.2f} → {new_rope:.2f} "
                            f"({change:+.2f}, {change_pct:+.2f}%) | "
                            f"当前价格={current_price:.2f} | 距离={distance:.2f} | {position_str}"
                        )
                
                # 计算更新耗时
                update_end_time = datetime.now()
                update_duration = (update_end_time - update_start_time).total_seconds()
                
                self.logger.info(f"✅ 系绳线更新完成 (耗时 {update_duration:.2f} 秒)")
                self.logger.info("🔄" * 40 + "\n")
                
            except Exception as e:
                self.logger.error(f"定期更新失败: {str(e)}")
                # 出错后等待一段时间再试
                await asyncio.sleep(60)
    
    async def start(self):
        """启动实时交易系统"""
        try:
            # 保存主事件循环引用 - 重要！
            self.loop = asyncio.get_running_loop()
            
            self.logger.info("\n" + "=" * 80)
            self.logger.info("启动实时交易系统")
            self.logger.info("=" * 80)
            
            # 初始化数据
            await self.initialize_data()
            
            # 连接WebSocket
            self.logger.info("\n正在连接WebSocket...")
            self.ws_manager.connect_public()
            self.logger.info("✓ WebSocket已连接")
            
            # 订阅所有交易对
            for symbol, pair_config in config.trading_pairs.items():
                contract_id = pair_config.contract_id
                
                self.logger.info(f"订阅 {symbol} 实时行情...")
                
                # 订阅实时价格
                self.ws_manager.subscribe_ticker(contract_id, self.handle_ticker)
                
                self.logger.info(f"✓ {symbol}: 已订阅实时价格")
            
            # 设置运行标志
            self.is_running = True
            
            # 启动定期更新任务
            update_task = asyncio.create_task(self.periodic_rope_update())
            
            self.logger.info("\n" + "=" * 80)
            self.logger.info("✅ 实时交易系统已启动")
            self.logger.info("=" * 80)
            self.logger.info("💡 系统特点:")
            self.logger.info("   • 实时价格监控（秒级，后台静默）")
            self.logger.info("   • 价格穿越立即检测")
            self.logger.info("   • 信号生成<1秒延迟")
            self.logger.info("   • 系绳线对齐K线周期更新（15分钟整点后1秒）")
            self.logger.info("   • 每30秒显示状态或接近系绳线时提醒")
            self.logger.info("=" * 80)
            self.logger.info("⚠️  按 Ctrl+C 停止系统")
            self.logger.info("=" * 80 + "\n")
            
            # 保持运行
            try:
                await update_task
            except asyncio.CancelledError:
                pass
            
        except KeyboardInterrupt:
            self.logger.info("\n收到停止信号...")
            await self.shutdown()
        except Exception as e:
            self.logger.error(f"系统错误: {str(e)}")
            import traceback
            traceback.print_exc()
            await self.shutdown()
    
    async def shutdown(self):
        """关闭系统"""
        self.logger.info("=" * 80)
        self.logger.info("正在关闭系统...")
        self.logger.info("=" * 80)
        
        # 停止运行标志
        self.is_running = False
        
        # 断开WebSocket
        try:
            self.ws_manager.disconnect_all()
            self.logger.info("✓ WebSocket已断开")
        except:
            pass
        
        # 打印交易历史
        trades = self.order_manager.get_trade_history()
        if trades:
            self.logger.info(f"\n交易历史 (共{len(trades)}笔):")
            for trade in trades:
                log_trade(self.logger, trade)
        
        # 打印最终盈亏
        total_pnl = self.order_manager.calculate_total_pnl()
        self.logger.info(f"\n最终盈亏: {total_pnl:.2f} USDT")
        
        # 打印统计信息
        self.logger.info("\n价格更新统计:")
        for symbol, pair_config in config.trading_pairs.items():
            contract_id = pair_config.contract_id
            count = self.price_update_count.get(contract_id, 0)
            self.logger.info(f"  {symbol}: {count} 次价格更新")
        
        # 关闭REST客户端
        try:
            if hasattr(self.client, 'async_client'):
                if hasattr(self.client.async_client, 'session'):
                    await self.client.async_client.session.close()
        except:
            pass
        
        self.logger.info("\n" + "=" * 80)
        self.logger.info("系统已关闭")
        self.logger.info("=" * 80)


async def main():
    """主函数"""
    print("""
╔═══════════════════════════════════════════════════════════╗
║           EdgeX 实时量化交易系统 - WebSocket版本              ║
╠═══════════════════════════════════════════════════════════╣
║  核心特性:                                                     ║
║  • 实时价格推送（<1秒延迟）                                   ║
║  • 价格穿越立即检测                                           ║
║  • 系绳线对齐K线周期更新（15分钟整点后1秒内）                ║
║  • 比旧系统快60倍！                                           ║
╠═══════════════════════════════════════════════════════════╣
║  日志策略:                                                     ║
║  • 后台实时监控（静默模式）                                   ║
║  • 每30秒汇报一次状态                                         ║
║  • 价格接近系绳线时提醒                                       ║
║  • 触发信号时详细记录                                         ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    # 创建并启动交易机器人
    bot = RealtimeTradingBot()
    await bot.start()


if __name__ == "__main__":
    asyncio.run(main())
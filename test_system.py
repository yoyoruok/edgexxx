"""
系统测试脚本
验证各个模块是否正常工作
"""

import asyncio
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from edgex_sdk import Client
from dotenv import load_dotenv

from config import config
from precision_manager import precision_manager
from strategy import Strategy, Position
from data_manager import DataManager
from rate_limiter import rate_limiter

load_dotenv()


class SystemTester:
    """系统测试器"""
    
    def __init__(self):
        self.passed = 0
        self.failed = 0
    
    def test(self, name: str, condition: bool, message: str = ""):
        """执行测试"""
        if condition:
            print(f"✓ {name}: 通过")
            self.passed += 1
        else:
            print(f"✗ {name}: 失败 - {message}")
            self.failed += 1
    
    def print_summary(self):
        """打印测试摘要"""
        total = self.passed + self.failed
        print("\n" + "=" * 80)
        print("测试摘要")
        print("=" * 80)
        print(f"总测试数: {total}")
        print(f"通过: {self.passed}")
        print(f"失败: {self.failed}")
        print(f"成功率: {(self.passed/total*100):.1f}%" if total > 0 else "N/A")
        print("=" * 80)


async def test_config():
    """测试配置模块"""
    print("\n" + "=" * 80)
    print("测试 1: 配置模块")
    print("=" * 80)
    
    tester = SystemTester()
    
    # 测试配置验证
    try:
        config.validate()
        tester.test("配置验证", True)
    except Exception as e:
        tester.test("配置验证", False, str(e))
    
    # 测试交易对配置
    btc_config = config.get_pair_config("BTCUSDT")
    tester.test("BTC配置存在", btc_config is not None)
    
    if btc_config:
        tester.test("合约ID正确", btc_config.contract_id == "10000001")
        tester.test("仓位配置合理", btc_config.position_size > 0)
        tester.test("杠杆配置合理", 1 <= btc_config.leverage <= 20)
    
    # 测试策略配置
    tester.test("MA短周期", config.strategy.ma_short_period > 0)
    tester.test("MA长周期", config.strategy.ma_long_period > config.strategy.ma_short_period)
    tester.test("系绳线周期", config.strategy.rope_period > 0)
    tester.test("K线周期", config.strategy.timeframe in ["15m", "1h", "4h"])
    
    tester.print_summary()


def test_precision_manager():
    """测试精度管理器"""
    print("\n" + "=" * 80)
    print("测试 2: 精度管理器")
    print("=" * 80)
    
    tester = SystemTester()
    
    # 设置测试合约
    precision_manager.set_contract_info("10000001", 0.1, 3)
    
    # 测试价格对齐
    price = 67892.567
    rounded_down = precision_manager.round_price("10000001", price, "down")
    rounded_up = precision_manager.round_price("10000001", price, "up")
    
    # 转换为浮点数进行检查
    down_val = float(rounded_down)
    up_val = float(rounded_up)
    
    # 检查对齐是否合理（允许小的浮点误差）
    down_valid = abs(down_val - round(down_val / 0.1) * 0.1) < 0.01
    up_valid = abs(up_val - round(up_val / 0.1) * 0.1) < 0.01
    
    tester.test("价格向下对齐", down_valid, f"结果: {rounded_down}")
    tester.test("价格向上对齐", up_valid, f"结果: {rounded_up}")
    tester.test("向下对齐 <= 原价", down_val <= price + 0.01)
    tester.test("向上对齐 >= 原价", up_val >= price - 0.01)
    
    # 测试数量对齐
    size = 0.0123456
    rounded_size = precision_manager.round_size("10000001", size)
    decimal_places = len(rounded_size.split('.')[-1]) if '.' in rounded_size else 0
    tester.test("数量对齐精度", decimal_places == 3, f"结果: {rounded_size}")
    
    # 测试滑点应用
    buy_price = precision_manager.apply_slippage(100.0, "BUY", 0.001)
    sell_price = precision_manager.apply_slippage(100.0, "SELL", 0.001)
    tester.test("买入滑点", buy_price > 100.0, f"结果: {buy_price}")
    tester.test("卖出滑点", sell_price < 100.0, f"结果: {sell_price}")
    
    tester.print_summary()


def test_strategy():
    """测试策略模块"""
    print("\n" + "=" * 80)
    print("测试 3: 策略模块")
    print("=" * 80)
    
    tester = SystemTester()
    
    # 创建策略
    strategy = Strategy(ma_short=25, ma_long=200, rope_period=50)
    
    # 创建模拟数据
    dates = pd.date_range(end=datetime.now(), periods=250, freq='1H')
    np.random.seed(42)
    
    # 模拟上升趋势
    prices = 50000 + np.cumsum(np.random.randn(250) * 100)
    df = pd.DataFrame({
        'open': prices,
        'high': prices + np.random.rand(250) * 100,
        'low': prices - np.random.rand(250) * 100,
        'close': prices,
        'volume': np.random.rand(250) * 100
    }, index=dates)
    
    # 测试MBO/MBI计算
    mbo, mbi = strategy.calculate_mbo_mbi(df)
    tester.test("MBO计算", not np.isnan(mbo), f"MBO: {mbo}")
    tester.test("MBI计算", not np.isnan(mbi), f"MBI: {mbi}")
    
    # 测试系绳线计算
    rope_line = strategy.calculate_rope_line(df)
    tester.test("系绳线计算", rope_line > 0, f"系绳线: {rope_line}")
    tester.test("系绳线合理性", df['low'].iloc[-50:].min() <= rope_line <= df['high'].iloc[-50:].max())
    
    # 测试信号生成
    signal = strategy.generate_signal("10000001", df, Position.EMPTY, prices[-1])
    tester.test("信号生成", signal is not None, f"信号: {signal.value}")
    
    # 测试止损止盈
    entry_price = 50000
    current_price_loss = 49000  # 2%亏损
    current_price_profit = 52500  # 5%盈利
    
    stop_loss = strategy.check_stop_loss("10000001", entry_price, current_price_loss, Position.LONG, 0.02)
    take_profit = strategy.check_take_profit("10000001", entry_price, current_price_profit, Position.LONG, 0.05)
    
    tester.test("止损检测", stop_loss == True)
    tester.test("止盈检测", take_profit == True)
    
    tester.print_summary()


async def test_data_manager():
    """测试数据管理器"""
    print("\n" + "=" * 80)
    print("测试 4: 数据管理器")
    print("=" * 80)
    
    tester = SystemTester()
    
    try:
        # 创建客户端
        client = Client(
            base_url=config.api.base_url,
            account_id=config.api.account_id,
            stark_private_key=config.api.stark_private_key
        )
        
        # 创建数据管理器（禁用自动刷新用于测试）
        data_manager = DataManager(client, auto_refresh=False)
        
        # 测试初始化K线
        print("正在获取K线数据...")
        df = await data_manager.initialize_klines("10000001", "15m", size=100)
        tester.test("初始化K线数据", df is not None and len(df) > 0)
        
        if df is not None:
            tester.test("K线包含必要列", all(col in df.columns for col in ['open', 'high', 'low', 'close', 'volume']))
            tester.test("K线数据完整", len(df) <= 100)
            tester.test("K线按时间排序", df.index.is_monotonic_increasing)
            
            # 测试获取缓存的K线
            df2 = await data_manager.get_klines("10000001", "15m")
            tester.test("获取缓存K线", df2 is not None and len(df2) > 0)
        
        # 测试获取当前价格
        print("正在获取当前价格...")
        price = await data_manager.get_current_price("10000001")
        tester.test("获取当前价格", price is not None and price > 0, f"价格: {price}")
        
        # 测试缓存
        cache_info = data_manager.get_cache_info()
        tester.test("缓存功能", len(cache_info) > 0)
        
        # 关闭数据管理器
        await data_manager.close()
        
        # 关闭客户端
        try:
            if hasattr(client, 'async_client'):
                if hasattr(client.async_client, 'session'):
                    await client.async_client.session.close()
        except Exception:
            pass
        
    except Exception as e:
        tester.test("数据管理器", False, str(e))
        import traceback
        traceback.print_exc()
    
    tester.print_summary()


async def test_rate_limiter():
    """测试限速器"""
    print("\n" + "=" * 80)
    print("测试 5: API限速器")
    print("=" * 80)
    
    tester = SystemTester()
    
    # 重置统计
    rate_limiter.reset_stats()
    
    # 测试快速请求
    start_time = asyncio.get_event_loop().time()
    for i in range(15):
        await rate_limiter.acquire()
    end_time = asyncio.get_event_loop().time()
    elapsed = end_time - start_time
    
    stats = rate_limiter.get_stats()
    
    tester.test("限速器工作", elapsed >= 0.5, f"耗时: {elapsed:.2f}秒")
    tester.test("请求计数", stats['total_requests'] == 15)
    tester.test("延迟触发", stats['total_delays'] > 0)
    
    tester.print_summary()


async def main():
    """主函数"""
    print("=" * 80)
    print("EdgeX量化交易系统 - 系统测试")
    print("=" * 80)
    
    # 测试各个模块
    await test_config()
    test_precision_manager()
    test_strategy()
    await test_data_manager()
    await test_rate_limiter()
    
    print("\n" + "=" * 80)
    print("所有测试完成！")
    print("=" * 80)
    print("\n如果所有测试通过，系统已准备就绪。")
    print("如果有失败的测试，请检查对应模块的配置和代码。")
    print("\n下一步:")
    print("  1. 准备历史数据: python prepare_backtest_data.py")
    print("  2. 运行回测: python main.py --backtest")
    print("  3. 实盘交易: python main.py")


if __name__ == "__main__":
    asyncio.run(main()) 
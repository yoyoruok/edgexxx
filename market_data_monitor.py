"""
EdgeX 市场数据监控系统
第一阶段：获取和显示市场数据

功能：
1. 实时行情查询（24小时统计）
2. K线数据获取
3. 订单簿深度查询
4. 批量查询多个交易对
"""

import asyncio
import os
import warnings
from datetime import datetime
from dotenv import load_dotenv
from edgex_sdk import Client
from edgex_sdk.quote.client import GetKLineParams, GetOrderBookDepthParams, KlineType, PriceType

# 加载环境变量
load_dotenv()

# 忽略 SDK 警告
warnings.filterwarnings('ignore', message='Unclosed client session')
warnings.filterwarnings('ignore', message='Unclosed connector')


# K线周期映射
KLINE_INTERVAL_MAP = {
    "1m": KlineType.MINUTE_1,
    "5m": KlineType.MINUTE_5,
    "15m": KlineType.MINUTE_15,
    "30m": KlineType.MINUTE_30,
    "1h": KlineType.HOUR_1,
    "2h": KlineType.HOUR_2,
    "4h": KlineType.HOUR_4,
    "6h": KlineType.HOUR_6,
    "8h": KlineType.HOUR_8,
    "12h": KlineType.HOUR_12,
    "1d": KlineType.DAY_1,
    "1w": KlineType.WEEK_1,
    "1M": KlineType.MONTH_1,
}

# 常用合约映射
CONTRACTS = {
    "10000001": {"name": "BTCUSDT", "symbol": "BTC", "tick": 0.1},
    "10000002": {"name": "ETHUSDT", "symbol": "ETH", "tick": 0.01},
    "10000003": {"name": "SOLUSDT", "symbol": "SOL", "tick": 0.01},
    "10000004": {"name": "BNBUSDT", "symbol": "BNB", "tick": 0.01},
}


class MarketDataMonitor:
    """市场数据监控器"""
    
    def __init__(self, client: Client):
        self.client = client
        self.contracts_info = {}
    
    async def initialize(self):
        """初始化：获取所有合约信息"""
        print("正在获取交易所合约信息...")
        metadata = await self.client.get_metadata()
        
        if metadata.get("code") == "SUCCESS":
            contract_list = metadata.get("data", {}).get("contractList", [])
            for contract in contract_list:
                contract_id = contract.get("contractId")
                if contract_id:
                    self.contracts_info[contract_id] = contract
            print(f"✓ 已加载 {len(self.contracts_info)} 个合约信息\n")
        else:
            print("✗ 获取合约信息失败\n")
    
    def get_contract_name(self, contract_id: str) -> str:
        """获取合约名称"""
        if contract_id in CONTRACTS:
            return CONTRACTS[contract_id]["name"]
        elif contract_id in self.contracts_info:
            return self.contracts_info[contract_id].get("contractName", contract_id)
        return contract_id
    
    async def get_ticker(self, contract_id: str):
        """获取单个合约的24小时行情"""
        try:
            quote = await self.client.get_24_hour_quote(contract_id)
            
            if quote.get("code") == "SUCCESS":
                data = quote.get("data", [])
                # API 返回的是列表，取第一个元素
                if isinstance(data, list) and len(data) > 0:
                    return data[0]
                elif isinstance(data, dict):
                    return data
                else:
                    print(f"✗ {contract_id} 返回数据格式异常")
                    return None
            else:
                print(f"✗ 获取 {contract_id} 行情失败: {quote.get('errorParam', '未知错误')}")
                return None
        except Exception as e:
            print(f"✗ 获取 {contract_id} 行情异常: {str(e)}")
            return None
    
    async def show_market_overview(self, contract_ids: list = None):
        """显示市场概览"""
        if contract_ids is None:
            contract_ids = list(CONTRACTS.keys())
        
        print("=" * 100)
        print("市场行情概览 - 24小时统计".center(100))
        print("=" * 100)
        print(f"{'交易对':<12} {'最新价格':<15} {'24h涨跌':<12} {'24h最高':<15} {'24h最低':<15} {'24h成交量':<15}")
        print("-" * 100)
        
        for contract_id in contract_ids:
            data = await self.get_ticker(contract_id)
            
            if data:
                name = self.get_contract_name(contract_id)
                last_price = data.get("lastPrice", "N/A")
                change_percent = data.get("priceChangePercent", "N/A")
                high_price = data.get("highPrice", "N/A")
                low_price = data.get("lowPrice", "N/A")
                volume = data.get("volume", "N/A")
                
                # 格式化涨跌幅（带颜色标识）
                if change_percent != "N/A":
                    try:
                        change_float = float(change_percent)
                        if change_float > 0:
                            change_str = f"+{change_float:.2f}% ↑"
                        elif change_float < 0:
                            change_str = f"{change_float:.2f}% ↓"
                        else:
                            change_str = f"{change_float:.2f}% -"
                    except:
                        change_str = change_percent
                else:
                    change_str = "N/A"
                
                # 格式化数值
                try:
                    last_price = f"${float(last_price):,.2f}" if last_price != "N/A" else "N/A"
                    high_price = f"${float(high_price):,.2f}" if high_price != "N/A" else "N/A"
                    low_price = f"${float(low_price):,.2f}" if low_price != "N/A" else "N/A"
                    volume = f"{float(volume):,.0f}" if volume != "N/A" else "N/A"
                except:
                    pass
                
                print(f"{name:<12} {last_price:<15} {change_str:<12} {high_price:<15} {low_price:<15} {volume:<15}")
        
        print("=" * 100)
        print()
    
    async def get_klines(self, contract_id: str, interval: str = "1m", size: int = 10):
        """获取K线数据"""
        try:
            # 转换 interval 字符串为 KlineType 枚举
            kline_type = KLINE_INTERVAL_MAP.get(interval, KlineType.MINUTE_5)
            
            params = GetKLineParams(
                contract_id=contract_id,
                kline_type=kline_type,
                price_type=PriceType.LAST_PRICE,
                size=size  # 注意：size 是 int 不是 string
            )
            
            result = await self.client.quote.get_k_line(params)
            
            if result.get("code") == "SUCCESS":
                data = result.get("data", {})
                klines = data.get("list", [])
                return klines
            else:
                print(f"✗ 获取K线失败: {result.get('errorParam', '未知错误')}")
                return []
        except Exception as e:
            print(f"✗ 获取K线异常: {str(e)}")
            return []
    
    async def show_klines(self, contract_id: str, interval: str = "1m", size: int = 10):
        """显示K线数据"""
        name = self.get_contract_name(contract_id)
        print("=" * 110)
        print(f"{name} K线数据 - {interval} 周期 (最近 {size} 条)".center(110))
        print("=" * 110)
        print(f"{'时间':<20} {'开盘':<12} {'最高':<12} {'最低':<12} {'收盘':<12} {'成交量':<15} {'涨跌':<10}")
        print("-" * 110)
        
        klines = await self.get_klines(contract_id, interval, size)
        
        if klines:
            for kline in reversed(klines):  # 从旧到新显示
                try:
                    timestamp = int(kline.get("startTime", 0))
                    time_str = datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d %H:%M:%S")
                    
                    open_price = float(kline.get("open", 0))
                    high_price = float(kline.get("high", 0))
                    low_price = float(kline.get("low", 0))
                    close_price = float(kline.get("close", 0))
                    volume = float(kline.get("volume", 0))
                    
                    # 计算涨跌
                    if open_price > 0:
                        change = ((close_price - open_price) / open_price) * 100
                        if change > 0:
                            change_str = f"+{change:.2f}% ↑"
                        elif change < 0:
                            change_str = f"{change:.2f}% ↓"
                        else:
                            change_str = "0.00% -"
                    else:
                        change_str = "N/A"
                    
                    print(f"{time_str:<20} ${open_price:>10.2f} ${high_price:>10.2f} ${low_price:>10.2f} ${close_price:>10.2f} {volume:>13,.0f} {change_str:<10}")
                except Exception as e:
                    print(f"解析K线数据出错: {str(e)}")
        else:
            print("没有K线数据")
        
        print("=" * 110)
        print()
    
    async def get_orderbook(self, contract_id: str, limit: int = 15):
        """获取订单簿数据"""
        try:
            if limit not in [15, 200]:
                limit = 15
            
            params = GetOrderBookDepthParams(
                contract_id=contract_id,
                limit=limit
            )
            
            result = await self.client.quote.get_order_book_depth(params)
            
            if result.get("code") == "SUCCESS":
                data = result.get("data", [])
                # data 是列表，取第一个元素
                if isinstance(data, list) and len(data) > 0:
                    return data[0]
                elif isinstance(data, dict):
                    return data
                return None
            else:
                print(f"✗ 获取订单簿失败: {result.get('errorParam', '未知错误')}")
                return None
        except Exception as e:
            print(f"✗ 获取订单簿异常: {str(e)}")
            return None
    
    async def show_orderbook(self, contract_id: str, limit: int = 15):
        """显示订单簿深度"""
        name = self.get_contract_name(contract_id)
        print("=" * 70)
        print(f"{name} 订单簿深度 (Top {limit})".center(70))
        print("=" * 70)
        
        orderbook = await self.get_orderbook(contract_id, limit)
        
        if orderbook and isinstance(orderbook, dict):
            asks = orderbook.get("asks", [])  # 卖单（从低到高）
            bids = orderbook.get("bids", [])  # 买单（从高到低）
            
            # 显示卖单（倒序显示，价格从高到低）
            print("\n📕 卖单 (ASK)".center(70))
            print(f"{'价格':<20} {'数量':<20} {'累计':<20}")
            print("-" * 70)
            
            cumulative = 0
            for ask in reversed(asks[:limit]):
                try:
                    price = float(ask.get('price', 0))
                    amount = float(ask.get('size', 0))
                    cumulative += amount
                    print(f"${price:<19,.2f} {amount:<19,.4f} {cumulative:<19,.4f}")
                except Exception as e:
                    print(f"解析错误: {e}, 数据: {ask}")
            
            # 显示当前价差
            if asks and bids:
                try:
                    best_ask = float(asks[0].get('price', 0))
                    best_bid = float(bids[0].get('price', 0))
                    spread = best_ask - best_bid
                    spread_percent = (spread / best_bid) * 100
                    print("\n" + "-" * 70)
                    print(f"价差: ${spread:.2f} ({spread_percent:.4f}%)".center(70))
                    print("-" * 70)
                except Exception as e:
                    print(f"计算价差错误: {e}")
            
            # 显示买单
            print("\n📗 买单 (BID)".center(70))
            print(f"{'价格':<20} {'数量':<20} {'累计':<20}")
            print("-" * 70)
            
            cumulative = 0
            for bid in bids[:limit]:
                try:
                    price = float(bid.get('price', 0))
                    amount = float(bid.get('size', 0))
                    cumulative += amount
                    print(f"${price:<19,.2f} {amount:<19,.4f} {cumulative:<19,.4f}")
                except Exception as e:
                    print(f"解析错误: {e}, 数据: {bid}")
        else:
            print("没有订单簿数据")
        
        print("=" * 70)
        print()


async def main():
    """主函数"""
    # 加载配置
    base_url = os.getenv("EDGEX_BASE_URL", "https://pro.edgex.exchange")
    account_id_str = os.getenv("EDGEX_ACCOUNT_ID", "")
    stark_private_key = os.getenv("EDGEX_STARK_PRIVATE_KEY", "")
    
    if not account_id_str or not stark_private_key:
        print("错误: 请设置环境变量 EDGEX_ACCOUNT_ID 和 EDGEX_STARK_PRIVATE_KEY")
        return
    
    try:
        account_id = int(account_id_str)
    except ValueError:
        print(f"错误: 账户 ID 格式不正确")
        return
    
    print("=" * 70)
    print("EdgeX 市场数据监控系统".center(70))
    print("=" * 70)
    print()
    
    try:
        # 创建客户端
        client = Client(
            base_url=base_url,
            account_id=account_id,
            stark_private_key=stark_private_key
        )
        
        # 创建监控器
        monitor = MarketDataMonitor(client)
        await monitor.initialize()
        
        # 1. 显示市场概览
        print("📊 功能 1: 市场行情概览\n")
        await monitor.show_market_overview()
        
        # 2. 显示 BTC K线数据
        print("📈 功能 2: K线数据查询\n")
        await monitor.show_klines("10000001", interval="5m", size=10)
        
        # 3. 显示 BTC 订单簿
        print("📖 功能 3: 订单簿深度\n")
        await monitor.show_orderbook("10000001", limit=10)
        
        print("✓ 所有市场数据获取完成！")
        print("\n提示: 你可以修改代码来:")
        print("  - 更改查询的交易对")
        print("  - 调整K线周期 (1m, 5m, 15m, 1h, 4h, 1d)")
        print("  - 修改订单簿深度 (15 或 200)")
        
    except Exception as e:
        print(f"\n✗ 发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        if 'client' in locals():
            try:
                if hasattr(client, 'async_client'):
                    if hasattr(client.async_client, 'session'):
                        await client.async_client.session.close()
            except Exception:
                pass
            await asyncio.sleep(0.1)


if __name__ == "__main__":
    asyncio.run(main())
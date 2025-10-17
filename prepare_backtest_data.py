"""
历史数据准备脚本
用于下载历史K线数据供回测使用
"""

import asyncio
import os
import pandas as pd
from datetime import datetime
from edgex_sdk import Client
from edgex_sdk.quote.client import GetKLineParams, KlineType, PriceType
from dotenv import load_dotenv
from typing import Dict, List

load_dotenv()


class DataPreparer:
    """数据准备器"""
    
    # K线周期映射
    KLINE_MAP = {
        "15m": KlineType.MINUTE_15,
        "1h": KlineType.HOUR_1,
        "4h": KlineType.HOUR_4,
    }
    
    def __init__(self):
        self.client = Client(
            base_url=os.getenv("EDGEX_BASE_URL", "https://pro.edgex.exchange"),
            account_id=int(os.getenv("EDGEX_ACCOUNT_ID", "0")),
            stark_private_key=os.getenv("EDGEX_STARK_PRIVATE_KEY", "")
        )
        
        # 创建数据目录
        self.data_dir = "data"
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
    
    async def download_klines(
        self,
        contract_id: str,
        symbol: str,
        interval: str,
        total_size: int = 1000
    ) -> pd.DataFrame:
        """
        下载K线数据（支持分页）
        
        Args:
            contract_id: 合约ID
            symbol: 交易对符号
            interval: K线周期
            total_size: 总共需要获取的数量（会分批获取）
        
        Returns:
            K线数据DataFrame
        """
        print(f"正在下载 {symbol} {interval} 数据...")
        
        try:
            kline_type = self.KLINE_MAP.get(interval)
            if not kline_type:
                print(f"错误: 不支持的K线周期 {interval}")
                return None
            
            all_klines = []
            batch_size = 100  # 每次请求100根
            offset_data = ""
            
            # 分批获取数据
            batches_needed = (total_size + batch_size - 1) // batch_size
            
            for batch in range(batches_needed):
                try:
                    params = GetKLineParams(
                        contract_id=contract_id,
                        kline_type=kline_type,
                        price_type=PriceType.LAST_PRICE,
                        size=batch_size,
                        offset_data=offset_data
                    )
                    
                    result = await self.client.quote.get_k_line(params)
                    
                    if result.get("code") != "SUCCESS":
                        print(f"  批次 {batch+1}/{batches_needed} 失败: {result.get('errorParam')}")
                        break
                    
                    # 解析数据
                    data = result.get("data", {})
                    klines = data.get("dataList", [])
                    
                    if not klines:
                        print(f"  批次 {batch+1}/{batches_needed}: 没有更多数据")
                        break
                    
                    all_klines.extend(klines)
                    print(f"  批次 {batch+1}/{batches_needed}: 获取 {len(klines)} 根，累计 {len(all_klines)} 根")
                    
                    # 获取下一页的offset
                    offset_data = data.get("nextPageOffsetData", "")
                    if not offset_data:
                        print(f"  已获取所有可用数据")
                        break
                    
                    # 避免请求过快
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    print(f"  批次 {batch+1} 异常: {str(e)}")
                    break
            
            if not all_klines:
                print(f"警告: 未获取到数据")
                return None
            
            # 转换为DataFrame
            df = self._parse_klines(all_klines)
            
            print(f"✓ 成功下载 {len(df)} 根K线")
            print(f"  时间范围: {df.index[0]} 至 {df.index[-1]}")
            
            return df
            
        except Exception as e:
            print(f"错误: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    def _parse_klines(self, klines: List[Dict]) -> pd.DataFrame:
        """解析K线数据"""
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
        df.sort_values('timestamp', inplace=True)
        # 去重
        df = df.drop_duplicates(subset=['timestamp'], keep='last')
        return df
    
    def save_to_csv(self, df: pd.DataFrame, symbol: str, interval: str):
        """
        保存数据到CSV文件
        
        Args:
            df: K线数据
            symbol: 交易对符号
            interval: K线周期
        """
        if df is None or len(df) == 0:
            print("警告: 没有数据可保存")
            return
        
        # 重置索引，使timestamp成为列
        df_to_save = df.reset_index()
        
        filename = os.path.join(self.data_dir, f"{symbol}_{interval}.csv")
        df_to_save.to_csv(filename, index=False)
        print(f"✓ 数据已保存到: {filename}\n")
    
    async def prepare_all_data(self, symbols: list, intervals: list, total_size: int = 500):
        """
        准备所有交易对的数据
        
        Args:
            symbols: 交易对列表，格式: [(contract_id, symbol), ...]
            intervals: K线周期列表
            total_size: 每个周期获取的总数量（会分批获取）
        """
        print("=" * 80)
        print("开始准备回测数据")
        print("=" * 80)
        
        for contract_id, symbol in symbols:
            print(f"\n处理 {symbol}:")
            
            for interval in intervals:
                # 下载数据（使用分页机制）
                df = await self.download_klines(contract_id, symbol, interval, total_size)
                
                # 保存数据
                if df is not None:
                    self.save_to_csv(df, symbol, interval)
                
                # 等待一下，避免请求过快
                await asyncio.sleep(1)
        
        print("\n" + "=" * 80)
        print("数据准备完成！")
        print("=" * 80)
        print(f"\n数据保存在 {self.data_dir}/ 目录下")


async def main():
    """主函数"""
    # 配置要下载的交易对
    symbols = [
        ("10000001", "BTCUSDT"),
        ("10000002", "ETHUSDT"),
        # 添加更多交易对...
    ]
    
    # 配置要下载的K线周期
    intervals = ["15m", "1h", "4h"]
    
    # 配置总共下载的数量（会分批获取，每批100根）
    # 建议至少300根，用于计算200周期MA
    total_size = 500
    
    # 创建数据准备器
    preparer = DataPreparer()
    
    # 下载数据
    await preparer.prepare_all_data(symbols, intervals, total_size)
    
    # 关闭客户端
    try:
        if hasattr(preparer.client, 'async_client'):
            if hasattr(preparer.client.async_client, 'session'):
                await preparer.client.async_client.session.close()
    except Exception:
        pass


if __name__ == "__main__":
    print("=" * 80)
    print("EdgeX 回测数据准备工具")
    print("=" * 80)
    print()
    
    asyncio.run(main())
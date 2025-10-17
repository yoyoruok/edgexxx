"""
数据管理模块
负责获取和管理K线数据 - 支持实时更新
"""

import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime
import logging
import asyncio
from edgex_sdk import Client
from edgex_sdk.quote.client import GetKLineParams, KlineType, PriceType

logger = logging.getLogger(__name__)


class DataManager:
    """数据管理器 - 实时更新版本"""
    
    # K线周期映射
    KLINE_MAP = {
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
    }
    
    def __init__(self, client: Client, auto_refresh: bool = True):
        """
        初始化数据管理器
        
        Args:
            client: EdgeX客户端
            auto_refresh: 是否自动刷新数据
        """
        self.client = client
        self.auto_refresh = auto_refresh
        
        # K线数据缓存
        self.kline_cache: Dict[str, pd.DataFrame] = {}
        
        # 最后更新时间
        self.last_update: Dict[str, datetime] = {}
        
        # 数据刷新任务
        self.refresh_tasks: Dict[str, asyncio.Task] = {}
        
        logger.info(f"数据管理器初始化 (自动刷新: {auto_refresh})")
    
    async def initialize_klines(
        self,
        contract_id: str,
        interval: str,
        size: int = 300
    ) -> Optional[pd.DataFrame]:
        """
        初始化K线数据（首次加载）
        
        Args:
            contract_id: 合约ID
            interval: K线周期
            size: 获取数量（建议至少300根，用于计算MA200）
        
        Returns:
            K线数据DataFrame
        """
        cache_key = f"{contract_id}_{interval}"
        
        logger.info(f"初始化K线数据: {cache_key}, 数量={size}")
        
        try:
            kline_type = self.KLINE_MAP.get(interval)
            if not kline_type:
                logger.error(f"不支持的K线周期: {interval}")
                return None
            
            # 请求数据
            params = GetKLineParams(
                contract_id=contract_id,
                kline_type=kline_type,
                price_type=PriceType.LAST_PRICE,
                size=size
            )
            
            result = await self.client.quote.get_k_line(params)
            
            if result.get("code") != "SUCCESS":
                logger.error(f"获取K线失败: {result.get('errorParam')}")
                return None
            
            # 解析数据 - 使用正确的字段名
            data = result.get("data", {})
            klines = data.get("dataList", [])
            
            if not klines:
                logger.warning(f"未获取到K线数据: {contract_id} {interval}")
                return None
            
            # 转换为DataFrame
            df = self._parse_klines(klines)
            
            # 缓存数据
            self.kline_cache[cache_key] = df
            self.last_update[cache_key] = datetime.now()
            
            logger.info(f"✓ K线初始化完成: {cache_key}, 共{len(df)}根, 时间范围: {df.index[0]} 至 {df.index[-1]}")
            
            # 启动自动刷新
            if self.auto_refresh:
                await self._start_auto_refresh(contract_id, interval)
            
            return df
            
        except Exception as e:
            logger.error(f"初始化K线异常: {contract_id} {interval}, {str(e)}")
            return None
    
    async def get_klines(
        self,
        contract_id: str,
        interval: str,
        force_refresh: bool = False
    ) -> Optional[pd.DataFrame]:
        """
        获取K线数据（从缓存或实时更新）
        
        Args:
            contract_id: 合约ID
            interval: K线周期
            force_refresh: 是否强制刷新
        
        Returns:
            K线数据DataFrame
        """
        cache_key = f"{contract_id}_{interval}"
        
        # 如果没有缓存，先初始化
        if cache_key not in self.kline_cache:
            return await self.initialize_klines(contract_id, interval)
        
        # 如果强制刷新
        if force_refresh:
            await self._refresh_klines(contract_id, interval)
        
        return self.kline_cache.get(cache_key)
    
    async def _refresh_klines(self, contract_id: str, interval: str):
        """
        刷新K线数据（获取最新数据并更新缓存）
        
        Args:
            contract_id: 合约ID
            interval: K线周期
        """
        cache_key = f"{contract_id}_{interval}"
        
        try:
            kline_type = self.KLINE_MAP.get(interval)
            if not kline_type:
                return
            
            # 获取最新的50根K线
            params = GetKLineParams(
                contract_id=contract_id,
                kline_type=kline_type,
                price_type=PriceType.LAST_PRICE,
                size=50
            )
            
            result = await self.client.quote.get_k_line(params)
            
            if result.get("code") != "SUCCESS":
                logger.warning(f"刷新K线失败: {cache_key}")
                return
            
            # 解析数据
            data = result.get("data", {})
            klines = data.get("dataList", [])
            
            if not klines:
                return
            
            # 转换为DataFrame
            new_df = self._parse_klines(klines)
            
            # 更新缓存
            if cache_key in self.kline_cache:
                cached_df = self.kline_cache[cache_key]
                
                # 合并数据
                combined = new_df.combine_first(cached_df)
                combined.sort_index(inplace=True)
                
                # 更新缓存
                self.kline_cache[cache_key] = combined
                self.last_update[cache_key] = datetime.now()
                
                logger.debug(f"K线已刷新: {cache_key}, 当前共{len(combined)}根")
            else:
                self.kline_cache[cache_key] = new_df
                self.last_update[cache_key] = datetime.now()
            
        except Exception as e:
            logger.error(f"刷新K线异常: {cache_key}, {str(e)}")
    
    async def _start_auto_refresh(self, contract_id: str, interval: str):
        """启动自动刷新任务"""
        cache_key = f"{contract_id}_{interval}"
        
        if cache_key in self.refresh_tasks:
            self.refresh_tasks[cache_key].cancel()
        
        task = asyncio.create_task(self._auto_refresh_loop(contract_id, interval))
        self.refresh_tasks[cache_key] = task
        
        logger.info(f"自动刷新已启动: {cache_key}")
    
    async def _auto_refresh_loop(self, contract_id: str, interval: str):
        """自动刷新循环"""
        cache_key = f"{contract_id}_{interval}"
        
        refresh_intervals = {
            "15m": 60,
            "1h": 300,
            "4h": 600,
        }
        
        refresh_interval = refresh_intervals.get(interval, 60)
        
        logger.info(f"自动刷新循环启动: {cache_key}, 间隔={refresh_interval}秒")
        
        try:
            while True:
                await asyncio.sleep(refresh_interval)
                await self._refresh_klines(contract_id, interval)
        except asyncio.CancelledError:
            logger.info(f"自动刷新已停止: {cache_key}")
        except Exception as e:
            logger.error(f"自动刷新异常: {cache_key}, {str(e)}")
    
    def _parse_klines(self, klines: List[Dict]) -> pd.DataFrame:
        """解析K线数据为DataFrame"""
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
    
    async def get_current_price(self, contract_id: str) -> Optional[float]:
        """获取当前价格"""
        try:
            quote = await self.client.get_24_hour_quote(contract_id)
            
            if quote.get("code") != "SUCCESS":
                logger.error(f"获取行情失败: {contract_id}")
                return None
            
            data = quote.get("data", [])
            if isinstance(data, list) and len(data) > 0:
                data = data[0]
            
            last_price = float(data.get("lastPrice", 0))
            logger.debug(f"{contract_id} 当前价格: {last_price}")
            return last_price
            
        except Exception as e:
            logger.error(f"获取价格异常: {contract_id}, {str(e)}")
            return None
    
    def get_cache_info(self) -> Dict:
        """获取缓存信息"""
        info = {}
        for key, df in self.kline_cache.items():
            last_update = self.last_update.get(key)
            info[key] = {
                'rows': len(df),
                'start': str(df.index[0]),
                'end': str(df.index[-1]),
                'last_update': str(last_update) if last_update else "N/A",
                'auto_refresh': key in self.refresh_tasks
            }
        return info
    
    def stop_auto_refresh(self, contract_id: str = None, interval: str = None):
        """停止自动刷新"""
        if contract_id and interval:
            cache_key = f"{contract_id}_{interval}"
            if cache_key in self.refresh_tasks:
                self.refresh_tasks[cache_key].cancel()
                del self.refresh_tasks[cache_key]
                logger.info(f"自动刷新已停止: {cache_key}")
        else:
            for task in self.refresh_tasks.values():
                task.cancel()
            self.refresh_tasks.clear()
            logger.info("所有自动刷新已停止")
    
    def clear_cache(self):
        """清空缓存"""
        self.stop_auto_refresh()
        self.kline_cache.clear()
        self.last_update.clear()
        logger.info("K线缓存已清空")
    
    async def close(self):
        """关闭数据管理器"""
        self.stop_auto_refresh()
        logger.info("数据管理器已关闭")
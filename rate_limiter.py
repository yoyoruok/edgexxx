"""
API限速器
防止超过交易所API限速
"""

import asyncio
import time
from collections import deque
from typing import Callable, Any
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """API限速器"""
    
    def __init__(self, max_per_second: int = 10, max_per_minute: int = 100):
        """
        初始化限速器
        
        Args:
            max_per_second: 每秒最大请求数
            max_per_minute: 每分钟最大请求数
        """
        self.max_per_second = max_per_second
        self.max_per_minute = max_per_minute
        
        # 请求时间戳队列
        self.second_queue = deque(maxlen=max_per_second)
        self.minute_queue = deque(maxlen=max_per_minute)
        
        # 统计
        self.total_requests = 0
        self.total_delays = 0
        
        logger.info(f"限速器初始化: {max_per_second}req/s, {max_per_minute}req/min")
    
    async def acquire(self):
        """
        获取请求许可（如有必要会等待）
        """
        current_time = time.time()
        
        # 检查每秒限制
        while len(self.second_queue) >= self.max_per_second:
            oldest = self.second_queue[0]
            wait_time = 1.0 - (current_time - oldest)
            
            if wait_time > 0:
                logger.debug(f"达到秒级限速，等待 {wait_time:.2f}秒")
                await asyncio.sleep(wait_time)
                self.total_delays += 1
                current_time = time.time()
            else:
                # 移除过期的时间戳
                self.second_queue.popleft()
        
        # 检查每分钟限制
        while len(self.minute_queue) >= self.max_per_minute:
            oldest = self.minute_queue[0]
            wait_time = 60.0 - (current_time - oldest)
            
            if wait_time > 0:
                logger.warning(f"达到分钟级限速，等待 {wait_time:.2f}秒")
                await asyncio.sleep(wait_time)
                self.total_delays += 1
                current_time = time.time()
            else:
                # 移除过期的时间戳
                self.minute_queue.popleft()
        
        # 记录请求时间
        self.second_queue.append(current_time)
        self.minute_queue.append(current_time)
        self.total_requests += 1
    
    async def execute(self, func: Callable, *args, **kwargs) -> Any:
        """
        执行带限速的函数
        
        Args:
            func: 要执行的异步函数
            *args: 函数参数
            **kwargs: 函数关键字参数
        
        Returns:
            函数返回值
        """
        await self.acquire()
        return await func(*args, **kwargs)
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            'total_requests': self.total_requests,
            'total_delays': self.total_delays,
            'current_second_queue': len(self.second_queue),
            'current_minute_queue': len(self.minute_queue),
            'delay_rate': self.total_delays / self.total_requests if self.total_requests > 0 else 0
        }
    
    def reset_stats(self):
        """重置统计"""
        self.total_requests = 0
        self.total_delays = 0
        logger.info("限速器统计已重置")


# 全局限速器实例
rate_limiter = RateLimiter()
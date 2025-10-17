"""
精度管理器
处理价格和数量的精度对齐，确保符合交易所规则
"""

from decimal import Decimal, ROUND_DOWN, ROUND_UP
from typing import Dict
import logging

logger = logging.getLogger(__name__)


class PrecisionManager:
    """精度管理器"""
    
    def __init__(self):
        self.contract_info: Dict[str, Dict] = {}
    
    def set_contract_info(self, contract_id: str, tick_size: float, size_precision: int):
        """设置合约精度信息"""
        self.contract_info[contract_id] = {
            "tick_size": Decimal(str(tick_size)),
            "size_precision": size_precision,
            "price_precision": self._get_price_precision(tick_size)
        }
        logger.info(f"设置合约 {contract_id} 精度: tick={tick_size}, size_precision={size_precision}")
    
    def _get_price_precision(self, tick_size: float) -> int:
        """从tick size计算价格精度"""
        tick_str = str(tick_size)
        if '.' in tick_str:
            return len(tick_str.split('.')[1])
        return 0
    
    def round_price(self, contract_id: str, price: float, direction: str = "down") -> str:
        """
        价格精度对齐
        
        Args:
            contract_id: 合约ID
            price: 原始价格
            direction: 对齐方向 ("down" 向下, "up" 向上)
        
        Returns:
            对齐后的价格字符串
        """
        if contract_id not in self.contract_info:
            logger.warning(f"合约 {contract_id} 精度信息未设置，使用原始价格")
            return str(price)
        
        info = self.contract_info[contract_id]
        tick_size = info["tick_size"]
        price_decimal = Decimal(str(price))
        
        # 计算价格是tick size的多少倍
        ticks = price_decimal / tick_size
        
        # 根据方向对齐
        if direction == "down":
            aligned_ticks = int(ticks)
        else:
            aligned_ticks = int(ticks) + (1 if ticks > int(ticks) else 0)
        
        # 计算对齐后的价格
        aligned_price = tick_size * Decimal(str(aligned_ticks))
        
        # 格式化为字符串
        precision = info["price_precision"]
        result = f"{aligned_price:.{precision}f}"
        
        logger.debug(f"价格对齐: {price} -> {result} (方向:{direction})")
        return result
    
    def round_size(self, contract_id: str, size: float) -> str:
        """
        数量精度对齐
        
        Args:
            contract_id: 合约ID
            size: 原始数量
        
        Returns:
            对齐后的数量字符串
        """
        if contract_id not in self.contract_info:
            logger.warning(f"合约 {contract_id} 精度信息未设置，使用原始数量")
            return str(size)
        
        info = self.contract_info[contract_id]
        precision = info["size_precision"]
        
        # 使用Decimal进行精确计算
        size_decimal = Decimal(str(size))
        quantize_str = '0.' + '0' * (precision - 1) + '1'
        rounded_size = size_decimal.quantize(Decimal(quantize_str), rounding=ROUND_DOWN)
        
        result = f"{rounded_size:.{precision}f}"
        logger.debug(f"数量对齐: {size} -> {result}")
        return result
    
    def calculate_order_value(self, contract_id: str, price: float, size: float) -> float:
        """计算订单价值（USDT）"""
        return price * size
    
    def adjust_size_for_leverage(self, position_size: float, leverage: int, price: float) -> float:
        """
        根据杠杆调整订单数量
        
        Args:
            position_size: 仓位大小 (USDT)
            leverage: 杠杆倍数
            price: 当前价格
        
        Returns:
            调整后的订单数量
        """
        # 实际可用资金 = 仓位大小 * 杠杆
        total_value = position_size * leverage
        
        # 计算数量
        size = total_value / price
        
        logger.debug(f"杠杆调整: 仓位={position_size}, 杠杆={leverage}, 价格={price}, 数量={size}")
        return size
    
    def validate_order_size(self, contract_id: str, size: float, min_size: float = 0.001) -> bool:
        """验证订单数量是否有效"""
        if size < min_size:
            logger.warning(f"订单数量 {size} 小于最小值 {min_size}")
            return False
        return True
    
    def apply_slippage(self, price: float, side: str, slippage_pct: float) -> float:
        """
        应用滑点
        
        Args:
            price: 原始价格
            side: 订单方向 ("BUY" 或 "SELL")
            slippage_pct: 滑点百分比
        
        Returns:
            应用滑点后的价格
        """
        if side == "BUY":
            # 买入时价格上浮
            return price * (1 + slippage_pct)
        else:
            # 卖出时价格下调
            return price * (1 - slippage_pct)


# 全局精度管理器实例
precision_manager = PrecisionManager()
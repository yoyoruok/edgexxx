"""
订单管理模块
负责订单的创建、撤销和状态管理
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
import logging
from edgex_sdk import Client
from edgex_sdk.order.types import CreateOrderParams, CancelOrderParams, OrderType, OrderSide, TimeInForce

from precision_manager import precision_manager
from strategy import Position, SignalType

logger = logging.getLogger(__name__)


@dataclass
class PositionInfo:
    """持仓信息"""
    contract_id: str
    symbol: str
    position: Position  # 持仓方向
    entry_price: float  # 开仓价格
    size: float  # 持仓数量
    entry_time: datetime  # 开仓时间
    order_id: Optional[str] = None  # 订单ID
    

class OrderManager:
    """订单管理器"""
    
    def __init__(self, client: Client):
        self.client = client
        
        # 持仓记录
        self.positions: Dict[str, PositionInfo] = {}
        
        # 活跃订单记录
        self.active_orders: Dict[str, Dict] = {}
        
        # 交易历史
        self.trade_history: List[Dict] = []
    
    async def place_order(
        self,
        contract_id: str,
        symbol: str,
        side: str,
        size: float,
        price: float,
        order_type: OrderType = OrderType.LIMIT,
        reduce_only: bool = False
    ) -> Optional[str]:
        """
        下单
        
        Args:
            contract_id: 合约ID
            symbol: 交易对符号
            side: 方向 (BUY/SELL)
            size: 数量
            price: 价格
            order_type: 订单类型
            reduce_only: 只减仓
        
        Returns:
            订单ID
        """
        try:
            # 精度对齐
            aligned_price = precision_manager.round_price(
                contract_id, 
                price, 
                direction="up" if side == "BUY" else "down"
            )
            aligned_size = precision_manager.round_size(contract_id, size)
            
            logger.info(f"下单: {symbol} {side} {aligned_size} @ {aligned_price}")
            
            # 构造订单参数
            params = CreateOrderParams(
                contract_id=contract_id,
                size=aligned_size,
                price=aligned_price,
                side=side,
                type=order_type,
                time_in_force=TimeInForce.GOOD_TIL_CANCEL if order_type == OrderType.LIMIT else TimeInForce.IMMEDIATE_OR_CANCEL,
                reduce_only=reduce_only
            )
            
            # 发送订单
            result = await self.client.create_order(params)
            
            if result.get("code") == "SUCCESS":
                order_data = result.get("data", {})
                order_id = order_data.get("orderId") or order_data.get("id")
                
                # 记录活跃订单
                self.active_orders[order_id] = {
                    'contract_id': contract_id,
                    'symbol': symbol,
                    'side': side,
                    'size': aligned_size,
                    'price': aligned_price,
                    'type': order_type.value,
                    'time': datetime.now()
                }
                
                logger.info(f"订单创建成功: {order_id}")
                return order_id
            else:
                logger.error(f"订单创建失败: {result.get('errorParam')}")
                return None
                
        except Exception as e:
            logger.error(f"下单异常: {str(e)}")
            return None
    
    async def cancel_order(self, order_id: str) -> bool:
        """
        撤销订单
        
        Args:
            order_id: 订单ID
        
        Returns:
            是否成功
        """
        try:
            params = CancelOrderParams(order_id=order_id)
            result = await self.client.cancel_order(params)
            
            if result.get("code") == "SUCCESS":
                # 从活跃订单中移除
                if order_id in self.active_orders:
                    del self.active_orders[order_id]
                
                logger.info(f"订单已撤销: {order_id}")
                return True
            else:
                logger.error(f"撤单失败: {result.get('errorParam')}")
                return False
                
        except Exception as e:
            logger.error(f"撤单异常: {str(e)}")
            return False
    
    async def cancel_all_orders(self, contract_id: str) -> bool:
        """
        撤销所有订单
        
        Args:
            contract_id: 合约ID
        
        Returns:
            是否成功
        """
        try:
            params = CancelOrderParams(contract_id=contract_id)
            result = await self.client.cancel_order(params)
            
            if result.get("code") == "SUCCESS":
                # 清除该合约的活跃订单
                to_remove = [oid for oid, order in self.active_orders.items() 
                            if order['contract_id'] == contract_id]
                for oid in to_remove:
                    del self.active_orders[oid]
                
                logger.info(f"已撤销合约 {contract_id} 的所有订单")
                return True
            else:
                logger.error(f"批量撤单失败: {result.get('errorParam')}")
                return False
                
        except Exception as e:
            logger.error(f"批量撤单异常: {str(e)}")
            return False
    
    async def execute_signal(
        self,
        contract_id: str,
        symbol: str,
        signal: SignalType,
        current_price: float,
        order_size: float,
        slippage: float
    ) -> bool:
        """
        执行交易信号
        
        Args:
            contract_id: 合约ID
            symbol: 交易对符号
            signal: 交易信号
            current_price: 当前价格
            order_size: 订单数量
            slippage: 滑点
        
        Returns:
            是否执行成功
        """
        current_position = self.get_position(contract_id)
        
        if signal == SignalType.LONG:
            # 开多或平空开多
            if current_position == Position.SHORT:
                # 先平空
                await self.close_position(contract_id, symbol, current_price, slippage)
            
            # 开多
            order_price = precision_manager.apply_slippage(current_price, "BUY", slippage)
            order_id = await self.place_order(
                contract_id, symbol, "BUY", order_size, order_price
            )
            
            if order_id:
                self.positions[contract_id] = PositionInfo(
                    contract_id=contract_id,
                    symbol=symbol,
                    position=Position.LONG,
                    entry_price=order_price,
                    size=order_size,
                    entry_time=datetime.now(),
                    order_id=order_id
                )
                logger.info(f"{symbol}: 开多成功 @ {order_price}")
                return True
        
        elif signal == SignalType.SHORT:
            # 开空或平多开空
            if current_position == Position.LONG:
                # 先平多
                await self.close_position(contract_id, symbol, current_price, slippage)
            
            # 开空
            order_price = precision_manager.apply_slippage(current_price, "SELL", slippage)
            order_id = await self.place_order(
                contract_id, symbol, "SELL", order_size, order_price
            )
            
            if order_id:
                self.positions[contract_id] = PositionInfo(
                    contract_id=contract_id,
                    symbol=symbol,
                    position=Position.SHORT,
                    entry_price=order_price,
                    size=order_size,
                    entry_time=datetime.now(),
                    order_id=order_id
                )
                logger.info(f"{symbol}: 开空成功 @ {order_price}")
                return True
        
        elif signal == SignalType.CLOSE_LONG:
            # 平多
            if current_position == Position.LONG:
                await self.close_position(contract_id, symbol, current_price, slippage)
                return True
        
        elif signal == SignalType.CLOSE_SHORT:
            # 平空
            if current_position == Position.SHORT:
                await self.close_position(contract_id, symbol, current_price, slippage)
                return True
        
        return False
    
    async def close_position(
        self,
        contract_id: str,
        symbol: str,
        current_price: float,
        slippage: float
    ) -> bool:
        """
        平仓
        
        Args:
            contract_id: 合约ID
            symbol: 交易对符号
            current_price: 当前价格
            slippage: 滑点
        
        Returns:
            是否成功
        """
        if contract_id not in self.positions:
            logger.warning(f"{symbol}: 没有持仓，无法平仓")
            return False
        
        position_info = self.positions[contract_id]
        
        # 确定平仓方向
        if position_info.position == Position.LONG:
            side = "SELL"
            action = "平多"
        elif position_info.position == Position.SHORT:
            side = "BUY"
            action = "平空"
        else:
            return False
        
        # 计算平仓价格
        close_price = precision_manager.apply_slippage(current_price, side, slippage)
        
        # 下平仓单
        order_id = await self.place_order(
            contract_id,
            symbol,
            side,
            position_info.size,
            close_price,
            reduce_only=True
        )
        
        if order_id:
            # 计算盈亏
            if position_info.position == Position.LONG:
                pnl = (close_price - position_info.entry_price) * position_info.size
            else:
                pnl = (position_info.entry_price - close_price) * position_info.size
            
            pnl_pct = pnl / (position_info.entry_price * position_info.size) * 100
            
            # 记录交易历史
            self.trade_history.append({
                'symbol': symbol,
                'action': action,
                'entry_price': position_info.entry_price,
                'close_price': close_price,
                'size': position_info.size,
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'entry_time': position_info.entry_time,
                'close_time': datetime.now()
            })
            
            logger.info(f"{symbol}: {action}成功 @ {close_price}, 盈亏: {pnl:.2f} USDT ({pnl_pct:.2f}%)")
            
            # 移除持仓
            del self.positions[contract_id]
            return True
        
        return False
    
    def get_position(self, contract_id: str) -> Position:
        """获取持仓状态"""
        if contract_id in self.positions:
            return self.positions[contract_id].position
        return Position.EMPTY
    
    def get_position_info(self, contract_id: str) -> Optional[PositionInfo]:
        """获取持仓详情"""
        return self.positions.get(contract_id)
    
    def get_all_positions(self) -> Dict[str, PositionInfo]:
        """获取所有持仓"""
        return self.positions
    
    def get_trade_history(self) -> List[Dict]:
        """获取交易历史"""
        return self.trade_history
    
    def calculate_total_pnl(self) -> float:
        """计算总盈亏"""
        return sum(trade['pnl'] for trade in self.trade_history)
"""
EdgeX WebSocket 实时监控系统
实时订阅市场行情和账户订单更新
"""

import os
import json
import time
import warnings
from datetime import datetime
from dotenv import load_dotenv
from edgex_sdk import WebSocketManager

load_dotenv()
warnings.filterwarnings('ignore')


class RealtimeMonitor:
    """实时监控系统"""
    
    def __init__(self, ws_manager: WebSocketManager):
        self.ws_manager = ws_manager
        self.last_price = {}
        self.update_count = {}
        self.start_time = time.time()
    
    def print_separator(self, char="=", length=100):
        """打印分隔线"""
        print(char * length)
    
    def format_timestamp(self, timestamp_ms):
        """格式化时间戳"""
        try:
            if isinstance(timestamp_ms, str):
                timestamp_ms = int(timestamp_ms)
            return datetime.fromtimestamp(timestamp_ms / 1000).strftime("%H:%M:%S")
        except:
            return "N/A"
    
    # ==================== 行情数据处理器 ====================
    
    def handle_ticker(self, message: str):
        """处理实时价格推送"""
        try:
            data = json.loads(message)
            content = data.get("content", {})
            ticker_list = content.get("data", [])
            
            if not ticker_list:
                return
            
            ticker = ticker_list[0] if isinstance(ticker_list, list) else ticker_list
            
            contract_id = ticker.get("contractId")
            last_price = ticker.get("lastPrice")
            volume = ticker.get("volume24h", "0")
            change_percent = ticker.get("priceChangePercent24h", "0")
            
            # 更新统计
            if contract_id not in self.update_count:
                self.update_count[contract_id] = 0
            self.update_count[contract_id] += 1
            
            # 价格变化提示
            price_change = ""
            if contract_id in self.last_price:
                old_price = float(self.last_price[contract_id])
                new_price = float(last_price)
                if new_price > old_price:
                    price_change = "🔺"
                elif new_price < old_price:
                    price_change = "🔻"
                else:
                    price_change = "➡️"
            
            self.last_price[contract_id] = last_price
            
            # 格式化输出
            current_time = self.format_timestamp(time.time() * 1000)
            try:
                change_float = float(change_percent)
                if change_float > 0:
                    change_str = f"+{change_float:.2f}%"
                else:
                    change_str = f"{change_float:.2f}%"
            except:
                change_str = change_percent
            
            print(f"[{current_time}] 📊 BTC-USDT: ${last_price} {price_change} | "
                  f"24h涨跌: {change_str} | 成交量: {volume} | "
                  f"更新次数: {self.update_count[contract_id]}")
            
        except Exception as e:
            print(f"❌ 处理ticker错误: {e}")
    
    def handle_kline(self, message: str):
        """处理K线更新"""
        try:
            data = json.loads(message)
            content = data.get("content", {})
            kline_data = content.get("data", [])
            
            if not kline_data:
                return
            
            kline = kline_data[0] if isinstance(kline_data, list) else kline_data
            
            open_price = kline.get("open")
            high_price = kline.get("high")
            low_price = kline.get("low")
            close_price = kline.get("close")
            volume = kline.get("volume")
            start_time = kline.get("startTime")
            
            time_str = self.format_timestamp(start_time)
            
            # 计算涨跌
            try:
                change = ((float(close_price) - float(open_price)) / float(open_price)) * 100
                if change > 0:
                    change_str = f"+{change:.2f}%"
                    trend = "📈"
                elif change < 0:
                    change_str = f"{change:.2f}%"
                    trend = "📉"
                else:
                    change_str = "0.00%"
                    trend = "➡️"
            except:
                change_str = "N/A"
                trend = ""
            
            print(f"[{time_str}] {trend} K线: 开${open_price} 高${high_price} "
                  f"低${low_price} 收${close_price} | 涨跌: {change_str} | 量: {volume}")
            
        except Exception as e:
            print(f"❌ 处理kline错误: {e}")
    
    def handle_depth(self, message: str):
        """处理订单簿深度更新"""
        try:
            data = json.loads(message)
            content = data.get("content", {})
            depth_data = content.get("data", [])
            
            if not depth_data:
                return
            
            depth = depth_data[0] if isinstance(depth_data, list) else depth_data
            
            asks = depth.get("asks", [])
            bids = depth.get("bids", [])
            
            if asks and bids:
                best_ask = float(asks[0].get("price", 0))
                best_bid = float(bids[0].get("price", 0))
                spread = best_ask - best_bid
                spread_percent = (spread / best_bid) * 100
                
                current_time = self.format_timestamp(time.time() * 1000)
                print(f"[{current_time}] 📖 订单簿: 买一${best_bid:,.2f} | "
                      f"卖一${best_ask:,.2f} | 价差${spread:.2f} ({spread_percent:.4f}%)")
            
        except Exception as e:
            print(f"❌ 处理depth错误: {e}")
    
    def handle_trade(self, message: str):
        """处理实时成交"""
        try:
            data = json.loads(message)
            content = data.get("content", {})
            trades = content.get("data", [])
            
            if not trades:
                return
            
            for trade in trades[:3]:  # 只显示最近3笔
                price = trade.get("price")
                size = trade.get("size")
                side = trade.get("side")
                trade_time = trade.get("tradeTime")
                
                time_str = self.format_timestamp(trade_time)
                side_emoji = "🟢" if side == "BUY" else "🔴"
                
                print(f"[{time_str}] {side_emoji} 成交: {side} ${price} × {size}")
            
        except Exception as e:
            print(f"❌ 处理trade错误: {e}")
    
    # ==================== 账户数据处理器 ====================
    
    def handle_account_update(self, message: str):
        """处理账户更新"""
        try:
            data = json.loads(message)
            content = data.get("content", {})
            account_data = content.get("data", {})
            
            if not account_data:
                return
            
            current_time = self.format_timestamp(time.time() * 1000)
            
            # 提取关键信息
            collateral_list = account_data.get("collateralAssetModelList", [])
            if collateral_list:
                collateral = collateral_list[0]
                total_equity = collateral.get("totalEquity", "0")
                available = collateral.get("availableAmount", "0")
                
                self.print_separator("-")
                print(f"[{current_time}] 💰 账户更新:")
                print(f"  总权益: ${float(total_equity):,.2f}")
                print(f"  可用余额: ${float(available):,.2f}")
                self.print_separator("-")
            
        except Exception as e:
            print(f"❌ 处理账户更新错误: {e}")
    
    def handle_order_update(self, message: str):
        """处理订单更新"""
        try:
            data = json.loads(message)
            content = data.get("content", {})
            order_data = content.get("data", {})
            
            if not order_data:
                return
            
            current_time = self.format_timestamp(time.time() * 1000)
            
            order_id = order_data.get("orderId", "N/A")
            order_type = order_data.get("type", "N/A")
            side = order_data.get("side", "N/A")
            price = order_data.get("price", "0")
            size = order_data.get("size", "0")
            status = order_data.get("status", "N/A")
            filled_size = order_data.get("filledSize", "0")
            
            # 根据订单状态选择emoji
            if status == "FILLED":
                status_emoji = "✅"
            elif status == "CANCELLED":
                status_emoji = "❌"
            elif status == "OPEN":
                status_emoji = "🔵"
            else:
                status_emoji = "⚪"
            
            self.print_separator("-")
            print(f"[{current_time}] {status_emoji} 订单更新:")
            print(f"  订单ID: {order_id}")
            print(f"  类型: {order_type} | 方向: {side} | 状态: {status}")
            print(f"  价格: ${price} | 数量: {size} | 已成交: {filled_size}")
            self.print_separator("-")
            
        except Exception as e:
            print(f"❌ 处理订单更新错误: {e}")
    
    def handle_position_update(self, message: str):
        """处理持仓更新"""
        try:
            data = json.loads(message)
            content = data.get("content", {})
            position_data = content.get("data", {})
            
            if not position_data:
                return
            
            current_time = self.format_timestamp(time.time() * 1000)
            
            contract_id = position_data.get("contractId", "N/A")
            position_size = position_data.get("positionSize", "0")
            position_value = position_data.get("positionValue", "0")
            unrealized_pnl = position_data.get("unrealizePnl", "0")
            avg_entry_price = position_data.get("avgEntryPrice", "0")
            
            # 格式化盈亏
            try:
                pnl_float = float(unrealized_pnl)
                if pnl_float > 0:
                    pnl_emoji = "💚"
                    pnl_str = f"+${pnl_float:.2f}"
                elif pnl_float < 0:
                    pnl_emoji = "❤️"
                    pnl_str = f"-${abs(pnl_float):.2f}"
                else:
                    pnl_emoji = "💛"
                    pnl_str = "$0.00"
            except:
                pnl_emoji = "💛"
                pnl_str = unrealized_pnl
            
            self.print_separator("-")
            print(f"[{current_time}] {pnl_emoji} 持仓更新:")
            print(f"  合约: {contract_id}")
            print(f"  仓位: {position_size} | 价值: ${position_value}")
            print(f"  开仓均价: ${avg_entry_price} | 未实现盈亏: {pnl_str}")
            self.print_separator("-")
            
        except Exception as e:
            print(f"❌ 处理持仓更新错误: {e}")
    
    def print_stats(self):
        """打印运行统计"""
        elapsed = int(time.time() - self.start_time)
        minutes = elapsed // 60
        seconds = elapsed % 60
        
        print(f"\n📊 运行统计:")
        print(f"  运行时间: {minutes}分{seconds}秒")
        print(f"  价格更新次数: {sum(self.update_count.values())}")
        for contract_id, count in self.update_count.items():
            print(f"    {contract_id}: {count}次")


def main():
    """主函数"""
    # 加载配置
    base_url = os.getenv("EDGEX_BASE_URL", "https://pro.edgex.exchange")
    ws_url = os.getenv("EDGEX_WS_URL", "wss://pro.edgex.exchange")
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
    
    print("=" * 100)
    print("EdgeX WebSocket 实时监控系统".center(100))
    print("=" * 100)
    print(f"WebSocket URL: {ws_url}")
    print(f"账户 ID: {account_id}")
    print(f"监控合约: BTC-USDT (10000001)")
    print("=" * 100)
    print()
    
    try:
        # 创建 WebSocket 管理器
        ws_manager = WebSocketManager(
            base_url=ws_url,
            account_id=account_id,
            stark_pri_key=stark_private_key
        )
        
        # 创建监控器
        monitor = RealtimeMonitor(ws_manager)
        
        print("🔌 正在连接 WebSocket...")
        
        # 连接公共 WebSocket（市场数据）
        ws_manager.connect_public()
        print("✅ 公共 WebSocket 连接成功")
        
        # 连接私有 WebSocket（账户数据）
        try:
            ws_manager.connect_private()
            print("✅ 私有 WebSocket 连接成功")
        except Exception as e:
            print(f"⚠️  私有 WebSocket 连接失败: {e}")
            print("   将仅订阅公共市场数据")
        
        print()
        print("=" * 100)
        print("开始订阅数据流...".center(100))
        print("=" * 100)
        print()
        
        # 订阅市场数据 - BTC-USDT
        contract_id = "10000001"
        
        print("📊 订阅市场数据:")
        ws_manager.subscribe_ticker(contract_id, monitor.handle_ticker)
        print(f"  ✓ Ticker（实时价格）")
        
        ws_manager.subscribe_kline(contract_id, "1m", monitor.handle_kline)
        print(f"  ✓ K线（1分钟）")
        
        ws_manager.subscribe_depth(contract_id, monitor.handle_depth)
        print(f"  ✓ 订单簿深度")
        
        ws_manager.subscribe_trade(contract_id, monitor.handle_trade)
        print(f"  ✓ 实时成交")
        
        # 订阅账户数据
        try:
            print("\n💰 订阅账户数据:")
            ws_manager.subscribe_account_update(monitor.handle_account_update)
            print(f"  ✓ 账户更新")
            
            ws_manager.subscribe_order_update(monitor.handle_order_update)
            print(f"  ✓ 订单更新")
            
            ws_manager.subscribe_position_update(monitor.handle_position_update)
            print(f"  ✓ 持仓更新")
        except Exception as e:
            print(f"  ⚠️  账户数据订阅失败: {e}")
        
        print()
        print("=" * 100)
        print("实时监控中... (按 Ctrl+C 停止)".center(100))
        print("=" * 100)
        print()
        
        # 持续运行
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\n收到停止信号...")
            
        # 打印统计信息
        monitor.print_stats()
        
        # 断开连接
        print("\n正在断开连接...")
        ws_manager.disconnect_all()
        print("✅ 已断开所有连接")
        
        print("\n" + "=" * 100)
        print("监控结束".center(100))
        print("=" * 100)
        
    except Exception as e:
        print(f"\n❌ 发生错误: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
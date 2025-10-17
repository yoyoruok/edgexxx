"""
EdgeX 订单功能测试程序
测试平台的下单、撤单、查询等核心功能
"""

import asyncio
import os
import warnings
from dotenv import load_dotenv
from edgex_sdk import (
    Client,
    CreateOrderParams,
    CancelOrderParams,
    GetActiveOrderParams,
    OrderFillTransactionParams,
    OrderType,
    OrderSide,
    TimeInForce,
    GetOrderBookDepthParams
)

load_dotenv()
warnings.filterwarnings('ignore', message='Unclosed client session')
warnings.filterwarnings('ignore', message='Unclosed connector')


class OrderTester:
    """订单功能测试类"""
    
    def __init__(self, client: Client):
        self.client = client
        self.test_contract_id = "10000001"  # BTC-USDT 合约
        self.created_order_ids = []  # 记录创建的订单ID，方便后续撤单
    
    async def test_limit_order(self):
        """💰 测试限价单下单"""
        print("\n" + "=" * 70)
        print("测试 1: 限价单下单 (LIMIT ORDER)".center(70))
        print("=" * 70)
        
        try:
            # 先获取当前市场价格
            orderbook_params = GetOrderBookDepthParams(
                contract_id=self.test_contract_id,
                limit=15
            )
            orderbook = await self.client.quote.get_order_book_depth(orderbook_params)
            
            if orderbook.get("code") == "SUCCESS":
                data = orderbook.get("data", [])
                if isinstance(data, list) and len(data) > 0:
                    data = data[0]
                
                bids = data.get("bids", [])
                if bids:
                    market_price = float(bids[0].get("price", 0))
                    print(f"📊 当前市场买一价: ${market_price:,.2f}")
                    
                    # 设置一个远低于市价的限价单，避免成交
                    safe_price = market_price * 0.5  # 设置为市价的50%
                    size = "0.001"  # 最小下单量
                    
                    print(f"📝 准备下单:")
                    print(f"   合约: BTC-USDT")
                    print(f"   类型: 限价单 (LIMIT)")
                    print(f"   方向: 买入 (BUY)")
                    print(f"   价格: ${safe_price:,.2f}")
                    print(f"   数量: {size} BTC")
                    print(f"   说明: 价格远低于市价，不会立即成交")
                    
                    # 创建限价单参数
                    params = CreateOrderParams(
                        contract_id=self.test_contract_id,
                        size=size,
                        price=str(safe_price),
                        side=OrderSide.BUY,  # 使用枚举对象
                        type=OrderType.LIMIT
                    )
                    
                    # 调用 create_order 方法
                    result = await self.client.create_order(params)
                    
                    if result.get("code") == "SUCCESS":
                        order_data = result.get("data", {})
                        order_id = order_data.get("orderId") or order_data.get("id")
                        self.created_order_ids.append(order_id)
                        
                        print(f"\n✅ 限价单创建成功!")
                        print(f"   订单ID: {order_id}")
                        print(f"   合约ID: {order_data.get('contractId', 'N/A')}")
                        print(f"   价格: ${safe_price:,.2f}")
                        print(f"   数量: {size} BTC")
                        print(f"   方向: BUY")
                        
                        # 打印完整的返回数据以便调试
                        print(f"\n📋 API 返回的字段: {list(order_data.keys())}")
                    else:
                        print(f"\n❌ 限价单创建失败: {result.get('errorParam', result)}")
            
        except Exception as e:
            print(f"\n❌ 测试失败: {str(e)}")
            import traceback
            traceback.print_exc()
    
    async def test_market_order(self):
        """⚡ 测试市价单下单"""
        print("\n" + "=" * 70)
        print("测试 2: 市价单下单 (MARKET ORDER)".center(70))
        print("=" * 70)
        
        print("⚠️  注意: 市价单会立即成交，建议在测试环境或使用小额测试")
        print("⚠️  本测试将跳过实际下单，仅演示参数构造")
        
        try:
            size = "0.001"  # 最小下单量
            
            print(f"\n📝 市价单参数示例:")
            print(f"   合约: BTC-USDT")
            print(f"   类型: 市价单 (MARKET)")
            print(f"   方向: 买入 (BUY)")
            print(f"   数量: {size} BTC")
            print(f"   说明: 市价单会按当前最优价格立即成交")
            
            # 注释掉实际下单代码，避免真实成交
            # params = CreateOrderParams(
            #     contract_id=self.test_contract_id,
            #     size=size,
            #     price="0",  # 市价单价格为 0
            #     side=OrderSide.BUY,
            #     type=OrderType.MARKET
            # )
            # result = await self.client.create_order(params)
            
            print("\n💡 提示: 如需测试市价单，请取消注释上述代码")
            print("   市价单 API 调用格式:")
            print("   params = CreateOrderParams(")
            print("       contract_id='10000001',")
            print("       size='0.001',")
            print("       price='0',  # 市价单价格为 0")
            print("       side=OrderSide.BUY,")
            print("       type=OrderType.MARKET")
            print("   )")
            print("   result = await client.create_order(params)")
            
        except Exception as e:
            print(f"\n❌ 测试失败: {str(e)}")
    
    async def test_query_active_orders(self):
        """📋 测试查询活跃订单"""
        print("\n" + "=" * 70)
        print("测试 3: 查询活跃订单 (ACTIVE ORDERS)".center(70))
        print("=" * 70)
        
        try:
            params = GetActiveOrderParams(
                size="50",
                filter_contract_id_list=[self.test_contract_id]
            )
            
            result = await self.client.get_active_orders(params)
            
            if result.get("code") == "SUCCESS":
                data = result.get("data", {})
                orders = data.get("dataList", [])
                
                print(f"📊 活跃订单总数: {len(orders)}")
                
                if orders:
                    print("\n活跃订单列表:")
                    print("-" * 100)
                    print(f"{'订单ID':<22} {'类型':<8} {'方向':<6} {'价格':<12} {'数量':<10} {'已成交':<10} {'状态':<15}")
                    print("-" * 100)
                    
                    # 打印第一个订单的所有字段用于调试
                    if orders:
                        print(f"\n🔍 调试: 订单字段 = {list(orders[0].keys())}\n")
                    
                    for order in orders[:10]:  # 只显示前10个
                        order_id = order.get("orderId") or order.get("id") or "N/A"
                        order_type = order.get("type", "N/A")
                        side = order.get("side", "N/A")
                        price = order.get("price", "0")
                        size = order.get("size", "0")
                        filled_size = order.get("filledSize", "0")
                        status = order.get("status", "N/A")
                        
                        print(f"{order_id:<22} {order_type:<8} {side:<6} ${price:<11} {size:<10} {filled_size:<10} {status:<15}")
                    
                    print("-" * 100)
                else:
                    print("\n暂无活跃订单")
                
                # 显示分页信息
                offset_data = data.get("offsetData")
                if offset_data:
                    print(f"\n📄 分页信息: {offset_data}")
            else:
                print(f"❌ 查询失败: {result.get('errorParam', result)}")
                
        except Exception as e:
            print(f"\n❌ 测试失败: {str(e)}")
            import traceback
            traceback.print_exc()
    
    async def test_cancel_order(self):
        """❌ 测试撤单功能"""
        print("\n" + "=" * 70)
        print("测试 4: 撤单功能 (CANCEL ORDER)".center(70))
        print("=" * 70)
        
        if not self.created_order_ids:
            print("⚠️  没有可撤销的订单（需要先创建订单）")
            return
        
        try:
            # 撤销第一个创建的订单
            order_id = self.created_order_ids[0]
            print(f"📝 准备撤销订单: {order_id}")
            
            params = CancelOrderParams(order_id=order_id)
            result = await self.client.cancel_order(params)
            
            if result.get("code") == "SUCCESS":
                data = result.get("data", {})
                print(f"\n✅ 订单撤销成功!")
                print(f"   订单ID: {order_id}")
                print(f"   撤销时间: {result.get('responseTime')}")
                
                # 从列表中移除
                self.created_order_ids.remove(order_id)
            else:
                print(f"\n❌ 撤单失败: {result.get('errorParam', result)}")
                
        except Exception as e:
            print(f"\n❌ 测试失败: {str(e)}")
            import traceback
            traceback.print_exc()
    
    async def test_cancel_all_orders(self):
        """❌ 测试批量撤单"""
        print("\n" + "=" * 70)
        print("测试 4b: 批量撤单 (CANCEL ALL ORDERS)".center(70))
        print("=" * 70)
        
        try:
            print(f"📝 准备撤销所有 BTC-USDT 合约的活跃订单")
            
            params = CancelOrderParams(contract_id=self.test_contract_id)
            result = await self.client.cancel_order(params)
            
            if result.get("code") == "SUCCESS":
                print(f"\n✅ 批量撤单成功!")
                print(f"   撤销时间: {result.get('responseTime')}")
                
                # 清空订单列表
                self.created_order_ids.clear()
            else:
                print(f"\n❌ 批量撤单失败: {result.get('errorParam', result)}")
                
        except Exception as e:
            print(f"\n❌ 测试失败: {str(e)}")
    
    async def test_query_fill_history(self):
        """📜 测试查询历史成交"""
        print("\n" + "=" * 70)
        print("测试 5: 查询历史成交 (FILL HISTORY)".center(70))
        print("=" * 70)
        
        try:
            params = OrderFillTransactionParams(
                size="20",
                filter_contract_id_list=[self.test_contract_id]
            )
            
            result = await self.client.get_order_fill_transactions(params)
            
            if result.get("code") == "SUCCESS":
                data = result.get("data", {})
                fills = data.get("dataList", [])
                
                print(f"📊 历史成交记录数: {len(fills)}")
                
                if fills:
                    print("\n成交记录:")
                    print("-" * 90)
                    print(f"{'订单ID':<22} {'方向':<6} {'价格':<12} {'数量':<10} {'手续费':<10} {'类型':<8} {'盈亏':<10}")
                    print("-" * 90)
                    
                    for fill in fills[:10]:  # 只显示前10条
                        order_id = fill.get("orderId", "N/A")
                        side = fill.get("orderSide", "N/A")
                        price = fill.get("fillPrice", "0")
                        size = fill.get("fillSize", "0")
                        fee = fill.get("fillFee", "0")
                        direction = fill.get("direction", "N/A")  # MAKER 或 TAKER
                        realize_pnl = fill.get("realizePnl", "0")
                        
                        # 格式化盈亏显示
                        try:
                            pnl_float = float(realize_pnl)
                            if pnl_float > 0:
                                pnl_str = f"+{pnl_float:.2f}"
                            elif pnl_float < 0:
                                pnl_str = f"{pnl_float:.2f}"
                            else:
                                pnl_str = "0.00"
                        except:
                            pnl_str = realize_pnl
                        
                        print(f"{order_id:<22} {side:<6} ${price:<11} {size:<10} {fee:<10} {direction:<8} {pnl_str:<10}")
                    
                    print("-" * 90)
                else:
                    print("\n暂无历史成交记录")
                
                # 显示分页信息
                offset_data = data.get("offsetData")
                if offset_data:
                    print(f"\n📄 分页信息: {offset_data}")
            else:
                print(f"❌ 查询失败: {result.get('errorParam', result)}")
                
        except Exception as e:
            print(f"\n❌ 测试失败: {str(e)}")
            import traceback
            traceback.print_exc()


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
    print("EdgeX 订单功能测试系统".center(70))
    print("=" * 70)
    print(f"API 地址: {base_url}")
    print(f"账户 ID: {account_id}")
    print(f"测试合约: BTC-USDT (10000001)")
    print("=" * 70)
    
    try:
        # 创建客户端
        client = Client(
            base_url=base_url,
            account_id=account_id,
            stark_private_key=stark_private_key
        )
        
        # 创建测试器
        tester = OrderTester(client)
        
        # 运行所有测试
        await tester.test_limit_order()
        await asyncio.sleep(1)  # 等待1秒
        
        await tester.test_market_order()
        await asyncio.sleep(1)
        
        await tester.test_query_active_orders()
        await asyncio.sleep(1)
        
        await tester.test_cancel_order()
        await asyncio.sleep(1)
        
        await tester.test_cancel_all_orders()
        await asyncio.sleep(1)
        
        await tester.test_query_fill_history()
        
        print("\n" + "=" * 70)
        print("✅ 所有订单功能测试完成！".center(70))
        print("=" * 70)
        
        print("\n💡 功能总结:")
        print("  ✓ 限价单下单 - 支持设置固定价格")
        print("  ✓ 市价单下单 - 按最优价格立即成交")
        print("  ✓ 查询活跃订单 - 支持分页和过滤")
        print("  ✓ 撤单功能 - 支持单个订单和批量撤单")
        print("  ✓ 查询历史成交 - 支持分页和时间过滤")
        
        print("\n📖 交易术语:")
        print("  • MAKER - 挂单方（提供流动性，手续费较低）")
        print("  • TAKER - 吃单方（消耗流动性，手续费较高）")
        print("  • BUY/SELL - 买入/卖出方向")
        print("  • LIMIT - 限价单（设定价格等待成交）")
        print("  • MARKET - 市价单（立即按市价成交）")
        
        print("\n⚠️  重要提示:")
        print("  1. 限价单会保留在订单簿中，直到成交或撤单")
        print("  2. 市价单会立即按当前最优价格成交")
        print("  3. 建议在测试环境使用小额进行测试")
        print("  4. 所有 API 调用都经过加密签名验证")
        print("  5. MAKER 订单提供流动性，手续费通常更优惠")
        
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
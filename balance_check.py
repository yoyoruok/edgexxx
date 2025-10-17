"""
EdgeX 账户余额查询程序
这是一个最简单的示例，用于连接 EdgeX API 并查询账户余额
"""

import asyncio
import os
import warnings
from dotenv import load_dotenv
from edgex_sdk import Client

# 加载 .env 文件中的环境变量
load_dotenv()

# 忽略 aiohttp 的资源警告（这是 SDK 的问题，不影响功能）
warnings.filterwarnings('ignore', message='Unclosed client session')
warnings.filterwarnings('ignore', message='Unclosed connector')


async def check_balance():
    """查询账户余额"""
    
    # 从环境变量获取配置信息
    base_url = os.getenv("EDGEX_BASE_URL", "https://pro.edgex.exchange")
    account_id_str = os.getenv("EDGEX_ACCOUNT_ID", "")
    stark_private_key = os.getenv("EDGEX_STARK_PRIVATE_KEY", "")
    
    # 检查必要的环境变量是否已设置
    if not account_id_str or not stark_private_key:
        print("错误: 请设置以下环境变量:")
        print("  EDGEX_ACCOUNT_ID - 你的账户ID")
        print("  EDGEX_STARK_PRIVATE_KEY - 你的 Stark 私钥")
        print("\n你可以在 .env 文件中设置这些变量")
        print(f"\n当前读取到的值:")
        print(f"  EDGEX_ACCOUNT_ID: {account_id_str if account_id_str else '(空)'}")
        print(f"  EDGEX_STARK_PRIVATE_KEY: {'已设置' if stark_private_key else '(空)'}")
        return
    
    # 转换账户 ID 为整数
    try:
        account_id = int(account_id_str)
    except ValueError:
        print(f"错误: 账户 ID 格式不正确: {account_id_str}")
        print("账户 ID 必须是纯数字")
        return
    
    print("=" * 50)
    print("EdgeX 账户余额查询")
    print("=" * 50)
    print(f"API 地址: {base_url}")
    print(f"账户 ID: {account_id}")
    print("-" * 50)
    
    try:
        # 创建客户端
        client = Client(
            base_url=base_url,
            account_id=account_id,
            stark_private_key=stark_private_key
        )
        
        print("\n正在连接 EdgeX API...")
        
        # 获取服务器时间（测试连接）
        server_time = await client.get_server_time()
        print(f"✓ 服务器时间: {server_time.get('data', {}).get('currentTime', 'N/A')}")
        
        # 获取账户资产信息
        print("\n正在获取账户资产...")
        assets_response = await client.get_account_asset()
        
        # 检查响应状态
        if assets_response.get("code") != "SUCCESS":
            print(f"✗ 获取账户资产失败: {assets_response.get('errorParam', '未知错误')}")
            return
        
        # 解析资产数据
        data = assets_response.get("data", {})
        
        print("\n" + "=" * 50)
        print("账户资产信息")
        print("=" * 50)
        
        # 显示抵押品资产 - 使用正确的字段名
        collateral_list = data.get("collateralAssetModelList", [])
        
        if collateral_list and len(collateral_list) > 0:
            collateral = collateral_list[0]  # 获取第一个抵押品（通常是 USDT）
            
            total_equity = collateral.get('totalEquity', '0')
            available = collateral.get('availableAmount', '0')
            position_value = collateral.get('totalPositionValueAbs', '0')
            initial_margin = collateral.get('initialMarginRequirement', '0')
            pending_withdraw = collateral.get('pendingWithdrawAmount', '0')
            order_frozen = collateral.get('orderFrozenAmount', '0')
            
            # 格式化显示
            print(f"\n💰 总权益: {float(total_equity):.2f} USDT")
            print(f"✅ 可用余额: {float(available):.2f} USDT")
            print(f"📊 持仓价值: {float(position_value):.2f} USDT")
            print(f"🔒 初始保证金: {float(initial_margin):.8f} USDT")
            print(f"⏳ 待提现: {float(pending_withdraw):.2f} USDT")
            print(f"❄️  订单冻结: {float(order_frozen):.2f} USDT")
        else:
            print("\n⚠️  未找到抵押品资产数据")
        
        # 显示详细的抵押品交易历史统计
        collateral_detail_list = data.get("collateralList", [])
        if collateral_detail_list and len(collateral_detail_list) > 0:
            detail = collateral_detail_list[0]
            print("\n" + "-" * 50)
            print("📈 账户交易统计")
            print("-" * 50)
            print(f"当前余额: {float(detail.get('amount', '0')):.6f} USDT")
            print(f"累计转入: {float(detail.get('cumTransferInAmount', '0')):.2f} USDT")
            print(f"累计转出: {float(detail.get('cumTransferOutAmount', '0')):.2f} USDT")
            print(f"累计买入: {float(detail.get('cumPositionBuyAmount', '0')):.2f} USDT")
            print(f"累计卖出: {float(detail.get('cumPositionSellAmount', '0')):.2f} USDT")
            print(f"累计手续费: {float(detail.get('cumFillFeeAmount', '0')):.6f} USDT")
            print(f"累计资金费: {float(detail.get('cumFundingFeeAmount', '0')):.6f} USDT")
        
        # 显示持仓信息
        positions = data.get("positionAssetList", [])
        
        # 过滤出有实际持仓的合约（持仓价值不为0）
        active_positions = [p for p in positions if float(p.get('positionValue', '0')) != 0]
        
        if active_positions:
            print(f"\n" + "=" * 50)
            print(f"持仓信息 (共 {len(active_positions)} 个)")
            print("=" * 50)
            
            for pos in active_positions:
                contract_id = pos.get("contractId", "未知")
                position_value = pos.get("positionValue", "0")
                max_leverage = pos.get("maxLeverage", "0")
                avg_entry_price = pos.get("avgEntryPrice", "0")
                liquidate_price = pos.get("liquidatePrice", "0")
                unrealize_pnl = pos.get("unrealizePnl", "0")
                
                print(f"\n合约 ID: {contract_id}")
                print(f"  持仓价值: {float(position_value):.2f} USDT")
                print(f"  最大杠杆: {max_leverage}x")
                print(f"  平均开仓价: {float(avg_entry_price):.2f}")
                print(f"  强平价格: {float(liquidate_price):.2f}")
                print(f"  未实现盈亏: {float(unrealize_pnl):.2f} USDT")
        else:
            print(f"\n当前无持仓")
        
        print("\n" + "=" * 50)
        print("查询完成!")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n✗ 发生错误: {str(e)}")
        print("\n请检查:")
        print("  1. 网络连接是否正常")
        print("  2. API 密钥是否正确")
        print("  3. 账户 ID 是否正确")
    finally:
        # 尝试关闭客户端连接（SDK 可能不支持，但我们尝试一下）
        if 'client' in locals():
            try:
                if hasattr(client, 'async_client'):
                    if hasattr(client.async_client, 'session'):
                        await client.async_client.session.close()
                    if hasattr(client.async_client, 'close'):
                        await client.async_client.close()
            except Exception:
                pass
            
            # 等待一小段时间让连接完全关闭
            await asyncio.sleep(0.1)


def main():
    """主函数"""
    # 运行异步函数
    asyncio.run(check_balance())


if __name__ == "__main__":
    main()
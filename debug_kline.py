"""
K线API调试脚本
查看EdgeX API实际返回的数据结构
"""

import asyncio
import os
import json
from dotenv import load_dotenv
from edgex_sdk import Client
from edgex_sdk.quote.client import GetKLineParams, KlineType, PriceType

load_dotenv()


async def debug_kline_api():
    """调试K线API"""
    
    # 创建客户端
    base_url = os.getenv("EDGEX_BASE_URL", "https://pro.edgex.exchange")
    account_id = int(os.getenv("EDGEX_ACCOUNT_ID", "0"))
    stark_private_key = os.getenv("EDGEX_STARK_PRIVATE_KEY", "")
    
    print("=" * 80)
    print("EdgeX K线API调试")
    print("=" * 80)
    print(f"API地址: {base_url}")
    print(f"账户ID: {account_id}")
    
    client = Client(
        base_url=base_url,
        account_id=account_id,
        stark_private_key=stark_private_key
    )
    
    # 测试参数
    contract_id = "10000001"  # BTC-USDT
    kline_type = KlineType.MINUTE_15
    size = 10
    
    print(f"\n请求参数:")
    print(f"  contract_id: {contract_id}")
    print(f"  kline_type: {kline_type} (值: {kline_type.value})")
    print(f"  price_type: {PriceType.LAST_PRICE} (值: {PriceType.LAST_PRICE.value})")
    print(f"  size: {size}")
    
    try:
        # 方法1: 使用SDK提供的方法
        print(f"\n{'='*80}")
        print("方法1: 使用 get_k_line() 方法")
        print("="*80)
        
        params = GetKLineParams(
            contract_id=contract_id,
            kline_type=kline_type,
            price_type=PriceType.LAST_PRICE,
            size=size
        )
        
        result = await client.quote.get_k_line(params)
        
        print(f"\n响应状态: {result.get('code')}")
        if result.get('errorParam'):
            print(f"错误信息: {result.get('errorParam')}")
        
        print(f"\n完整响应:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        # 分析data字段
        data = result.get("data")
        print(f"\ndata字段类型: {type(data)}")
        
        if isinstance(data, dict):
            print(f"data字段的键: {list(data.keys())}")
            
            # 尝试不同的可能字段名
            for key in ['list', 'klines', 'dataList', 'klineList', 'data']:
                if key in data:
                    items = data[key]
                    print(f"\n找到字段 '{key}', 类型: {type(items)}, 长度: {len(items) if isinstance(items, list) else 'N/A'}")
                    if isinstance(items, list) and len(items) > 0:
                        print(f"第一条数据: {json.dumps(items[0], indent=2, ensure_ascii=False)}")
        
        elif isinstance(data, list):
            print(f"data是列表, 长度: {len(data)}")
            if len(data) > 0:
                print(f"第一个元素类型: {type(data[0])}")
                if isinstance(data[0], dict):
                    print(f"第一个元素: {json.dumps(data[0], indent=2, ensure_ascii=False)}")
        
        # 方法2: 测试24小时行情（这个我们知道能工作）
        print(f"\n{'='*80}")
        print("方法2: 测试 get_24_hour_quote() (对照)")
        print("="*80)
        
        quote = await client.get_24_hour_quote(contract_id)
        print(f"\n行情响应状态: {quote.get('code')}")
        print(f"最新价格: {quote.get('data', [{}])[0].get('lastPrice', 'N/A')}")
        
    except Exception as e:
        print(f"\n❌ 发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 关闭客户端
        try:
            if hasattr(client, 'async_client'):
                if hasattr(client.async_client, 'session'):
                    await client.async_client.session.close()
        except Exception:
            pass
    
    print("\n" + "=" * 80)
    print("调试完成")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(debug_kline_api())
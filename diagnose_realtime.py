"""
实盘运行诊断脚本
检查实时交易系统的各个环节
"""

import asyncio
import pandas as pd
from datetime import datetime
import pytz
from edgex_sdk import Client
from dotenv import load_dotenv
import os

load_dotenv()

from rope_line_strategy import RopeLineStrategy


async def diagnose_realtime_system():
    """诊断实时交易系统"""
    
    BEIJING = pytz.timezone('Asia/Shanghai')
    
    print("=" * 100)
    print("实盘系统诊断")
    print("=" * 100)
    print(f"诊断时间: {datetime.now(BEIJING).strftime('%Y-%m-%d %H:%M:%S %Z')}")
    
    # 创建客户端
    client = Client(
        base_url=os.getenv("EDGEX_BASE_URL", "https://pro.edgex.exchange"),
        account_id=int(os.getenv("EDGEX_ACCOUNT_ID", "0")),
        stark_private_key=os.getenv("EDGEX_STARK_PRIVATE_KEY", "")
    )
    
    from edgex_sdk.quote.client import GetKLineParams, KlineType, PriceType
    
    contract_id = "10000001"
    
    # ========================================
    # 检查点1: K线数据获取
    # ========================================
    print("\n" + "=" * 100)
    print("检查点1: K线数据获取")
    print("=" * 100)
    
    params = GetKLineParams(
        contract_id=contract_id,
        kline_type=KlineType.MINUTE_15,
        price_type=PriceType.LAST_PRICE,
        size=51
    )
    
    result = await client.quote.get_k_line(params)
    
    if result.get("code") != "SUCCESS":
        print(f"❌ 获取K线失败")
        return
    
    klines = result.get("data", {}).get("dataList", [])
    print(f"✓ 成功获取 {len(klines)} 根K线")
    
    # 转换数据
    data = []
    for k in klines:
        timestamp_ms = int(k.get('klineTime', 0))
        dt_utc = pd.to_datetime(timestamp_ms, unit='ms', utc=True)
        dt_beijing = dt_utc.tz_convert(BEIJING)
        
        data.append({
            'timestamp': dt_beijing,
            'open': float(k.get('open', 0)),
            'high': float(k.get('high', 0)),
            'low': float(k.get('low', 0)),
            'close': float(k.get('close', 0)),
            'volume': float(k.get('size', 0))
        })
    
    df = pd.DataFrame(data)
    df.set_index('timestamp', inplace=True)
    df.sort_index(inplace=True)
    
    # ========================================
    # 检查点2: K线时间对齐
    # ========================================
    print("\n" + "=" * 100)
    print("检查点2: K线时间对齐检查")
    print("=" * 100)
    
    print(f"\n最后3根K线时间:")
    for idx in df.tail(3).index:
        print(f"  {idx.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    
    last_kline_time = df.index[-1]
    now_beijing = datetime.now(BEIJING)
    if now_beijing.tzinfo is None:
        now_beijing = BEIJING.localize(datetime.now())
    
    # 计算当前应该在哪个K线周期
    current_minute = now_beijing.minute
    kline_period_start = (current_minute // 15) * 15
    expected_kline_time = now_beijing.replace(minute=kline_period_start, second=0, microsecond=0)
    
    print(f"\n当前北京时间: {now_beijing.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"当前K线周期应该开始于: {expected_kline_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"最新K线时间: {last_kline_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    if last_kline_time >= expected_kline_time:
        print(f"✓ K线时间正常")
    else:
        delay = (expected_kline_time - last_kline_time).total_seconds() / 60
        print(f"⚠️  K线延迟: {delay:.0f} 分钟")
    
    # ========================================
    # 检查点3: 系绳线计算（两种方式）
    # ========================================
    print("\n" + "=" * 100)
    print("检查点3: 系绳线计算检查")
    print("=" * 100)
    
    strategy = RopeLineStrategy(rope_period=50)
    
    # 方式1: 排除最后一根（正确方式，用于实盘）
    df_calc = df[['open', 'high', 'low', 'close', 'volume']].copy()
    rope_exclude = strategy.calculate_rope_line(df_calc, exclude_current=True)
    
    # 方式2: 包含最后一根（错误方式，但可能实盘误用了）
    rope_include = strategy.calculate_rope_line(df_calc, exclude_current=False)
    
    print(f"\n系绳线计算结果:")
    print(f"  排除最后一根K线 (正确): {rope_exclude:.2f}")
    print(f"  包含最后一根K线 (错误): {rope_include:.2f}")
    print(f"  差异: {abs(rope_exclude - rope_include):.2f}")
    
    if abs(rope_exclude - rope_include) > 10:
        print(f"\n⚠️  警告: 两种方式差异较大，可能实盘中使用了错误的方式")
    
    # ========================================
    # 检查点4: 获取当前实时价格
    # ========================================
    print("\n" + "=" * 100)
    print("检查点4: 实时价格获取")
    print("=" * 100)
    
    try:
        # 获取当前市场价格
        ticker_result = await client.quote.get_quote_summary(contract_id)
        
        if ticker_result.get("code") == "SUCCESS":
            ticker_data = ticker_result.get("data", {})
            current_price = float(ticker_data.get("lastPrice", 0))
            
            print(f"✓ 当前市场价格: {current_price:.2f}")
            
            # 检查价格位置
            distance_from_rope = current_price - rope_exclude
            position_pct = (distance_from_rope / rope_exclude) * 100
            
            print(f"\n价格与系绳线关系:")
            print(f"  系绳线: {rope_exclude:.2f}")
            print(f"  当前价格: {current_price:.2f}")
            print(f"  距离: {distance_from_rope:+.2f} ({position_pct:+.2f}%)")
            
            if current_price > rope_exclude:
                print(f"  位置: 在系绳线上方 ⬆️")
            elif current_price < rope_exclude:
                print(f"  位置: 在系绳线下方 ⬇️")
            else:
                print(f"  位置: 正好在系绳线上 =")
        else:
            print(f"❌ 获取实时价格失败")
            current_price = df.iloc[-1]['close']
            print(f"  使用最新K线收盘价: {current_price:.2f}")
    except Exception as e:
        print(f"❌ 获取实时价格异常: {str(e)}")
        current_price = df.iloc[-1]['close']
        print(f"  使用最新K线收盘价: {current_price:.2f}")
    
    # ========================================
    # 检查点5: 模拟main.py中的系绳线更新时机
    # ========================================
    print("\n" + "=" * 100)
    print("检查点5: 系绳线更新时机检查")
    print("=" * 100)
    
    # 计算下一次更新时间
    next_kline_time = last_kline_time + pd.Timedelta(minutes=15)
    update_time = next_kline_time + pd.Timedelta(seconds=1)  # K线周期后1秒更新
    
    print(f"\n当前K线周期: {last_kline_time.strftime('%H:%M:%S')}")
    print(f"下一个K线周期: {next_kline_time.strftime('%H:%M:%S')}")
    print(f"系绳线更新时间: {update_time.strftime('%H:%M:%S')}")
    
    if now_beijing < next_kline_time:
        wait_seconds = (next_kline_time - now_beijing).total_seconds()
        print(f"\n状态: 当前K线未完成")
        print(f"距离K线完成: {wait_seconds:.0f} 秒")
        print(f"距离系绳线更新: {wait_seconds + 1:.0f} 秒")
    else:
        print(f"\n状态: 当前K线已完成")
        print(f"系绳线应该已更新")
    
    # ========================================
    # 检查点6: 检查实盘中可能的问题
    # ========================================
    print("\n" + "=" * 100)
    print("检查点6: 常见问题诊断")
    print("=" * 100)
    
    issues = []
    
    # 问题1: 系绳线是否使用了错误的参数
    if abs(rope_exclude - rope_include) > 10:
        issues.append({
            'level': '严重',
            'desc': '系绳线计算可能使用了错误的参数',
            'detail': f'排除当前K线: {rope_exclude:.2f}, 包含当前K线: {rope_include:.2f}',
            'solution': '确保调用时使用 exclude_current=True'
        })
    
    # 问题2: K线数量不足
    if len(df) < 51:
        issues.append({
            'level': '严重',
            'desc': f'K线数量不足，只有{len(df)}根',
            'detail': '需要至少51根K线（50根用于计算+1根当前）',
            'solution': '等待更多K线数据或检查API请求参数'
        })
    
    # 问题3: K线时间延迟
    if last_kline_time < expected_kline_time:
        delay_minutes = (expected_kline_time - last_kline_time).total_seconds() / 60
        if delay_minutes >= 15:
            issues.append({
                'level': '严重',
                'desc': f'K线数据延迟 {delay_minutes:.0f} 分钟',
                'detail': f'最新K线: {last_kline_time.strftime("%H:%M")}, 预期: {expected_kline_time.strftime("%H:%M")}',
                'solution': '检查网络连接或API服务状态'
            })
    
    # 问题4: 使用了错误的时区
    last_kline_hour = last_kline_time.hour
    now_hour = now_beijing.hour
    if abs(last_kline_hour - now_hour) >= 8:
        issues.append({
            'level': '警告',
            'desc': '可能存在时区问题',
            'detail': f'K线时间: {last_kline_time.strftime("%H:%M %Z")}, 当前时间: {now_beijing.strftime("%H:%M %Z")}',
            'solution': '确保所有时间都使用北京时间（UTC+8）'
        })
    
    # 问题5: 实时价格获取方式
    price_diff_from_close = abs(current_price - df.iloc[-1]['close'])
    if price_diff_from_close < 0.01:
        issues.append({
            'level': '提示',
            'desc': '实时价格可能直接使用了K线收盘价',
            'detail': f'实时价格: {current_price:.2f}, K线收盘: {df.iloc[-1]["close"]:.2f}',
            'solution': '应使用WebSocket获取真正的实时价格，而不是K线收盘价'
        })
    
    if issues:
        print("\n发现以下问题:")
        for i, issue in enumerate(issues, 1):
            print(f"\n{i}. [{issue['level']}] {issue['desc']}")
            print(f"   详情: {issue['detail']}")
            print(f"   解决: {issue['solution']}")
    else:
        print("\n✓ 未发现明显问题")
    
    # ========================================
    # 检查点7: 验证穿越检测逻辑
    # ========================================
    print("\n" + "=" * 100)
    print("检查点7: 穿越检测逻辑验证")
    print("=" * 100)
    
    # 模拟价格穿越场景
    print(f"\n当前状态:")
    print(f"  系绳线: {rope_exclude:.2f}")
    print(f"  实时价格: {current_price:.2f}")
    
    # 测试向上穿越
    test_old_price = rope_exclude - 10
    test_new_price = rope_exclude + 10
    
    print(f"\n向上穿越测试:")
    print(f"  旧价格: {test_old_price:.2f} (系绳线下方)")
    print(f"  新价格: {test_new_price:.2f} (系绳线上方)")
    
    if test_old_price <= rope_exclude and test_new_price > rope_exclude:
        print(f"  ✓ 检测到向上穿越 - 应该开多")
    else:
        print(f"  ❌ 未检测到穿越")
    
    # 测试向下穿越
    test_old_price2 = rope_exclude + 10
    test_new_price2 = rope_exclude - 10
    
    print(f"\n向下穿越测试:")
    print(f"  旧价格: {test_old_price2:.2f} (系绳线上方)")
    print(f"  新价格: {test_new_price2:.2f} (系绳线下方)")
    
    if test_old_price2 >= rope_exclude and test_new_price2 < rope_exclude:
        print(f"  ✓ 检测到向下穿越 - 应该开空")
    else:
        print(f"  ❌ 未检测到穿越")
    
    # ========================================
    # 总结建议
    # ========================================
    print("\n" + "=" * 100)
    print("诊断总结与建议")
    print("=" * 100)
    
    print(f"\n✓ 关键数据:")
    print(f"  - 系绳线（排除当前K线）: {rope_exclude:.2f}")
    print(f"  - 当前实时价格: {current_price:.2f}")
    print(f"  - 价格位置: {'上方' if current_price > rope_exclude else '下方'}")
    print(f"  - 距离系绳线: {abs(current_price - rope_exclude):.2f} ({abs((current_price - rope_exclude) / rope_exclude * 100):.2f}%)")
    
    if issues:
        print(f"\n⚠️  发现 {len(issues)} 个问题需要注意")
    else:
        print(f"\n✓ 系统运行正常")
    
    print("\n建议检查的地方:")
    print("  1. main.py 第430行左右 - 确认使用 exclude_current=True")
    print("  2. handle_ticker 方法 - 确认使用实时价格而非K线收盘价")
    print("  3. check_and_execute 方法 - 确认穿越检测逻辑正确")
    print("  4. periodic_rope_update 方法 - 确认在正确的时间点更新")
    
    # 关闭客户端
    try:
        if hasattr(client, 'async_client'):
            if hasattr(client.async_client, 'session'):
                await client.async_client.session.close()
    except:
        pass
    
    print("\n" + "=" * 100)
    print("诊断完成")
    print("=" * 100)


if __name__ == "__main__":
    asyncio.run(diagnose_realtime_system())
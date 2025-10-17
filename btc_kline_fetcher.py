import requests
import json
from datetime import datetime

def get_btc_klines(size=100):
    """
    获取BTC 15分钟K线数据
    
    参数:
        size: 获取的K线数量，默认100根
    """
    # API基础URL
    base_url = "https://pro.edgex.exchange/api/v1/public/quote/getKline"
    
    # 请求参数
    params = {
        "contractId": "10000001",      # BTCUSDT合约ID
        "klineType": "MINUTE_15",      # 15分钟K线
        "priceType": "LAST_PRICE",     # 最新价格类型
        "size": str(size)              # 获取数量
    }
    
    try:
        # 发送GET请求
        print(f"正在获取 {size} 根 BTC 15分钟K线数据...")
        response = requests.get(base_url, params=params)
        response.raise_for_status()  # 检查HTTP错误
        
        # 解析响应
        data = response.json()
        
        if data.get("code") == "SUCCESS":
            kline_list = data.get("data", {}).get("dataList", [])
            print(f"成功获取 {len(kline_list)} 根K线数据\n")
            
            # 打印K线数据
            print(f"{'时间':<20} {'开盘价':<12} {'最高价':<12} {'最低价':<12} {'收盘价':<12} {'成交量':<12}")
            print("-" * 92)
            
            for kline in kline_list:
                # 转换时间戳为可读格式
                timestamp = int(kline['klineTime']) / 1000
                time_str = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
                
                print(f"{time_str:<20} "
                      f"{kline['open']:<12} "
                      f"{kline['high']:<12} "
                      f"{kline['low']:<12} "
                      f"{kline['close']:<12} "
                      f"{kline['size']:<12}")
            
            # 返回数据用于进一步处理
            return kline_list
        else:
            print(f"API返回错误: {data.get('msg', '未知错误')}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"JSON解析失败: {e}")
        return None

def save_to_csv(kline_list, filename="btc_15m_klines.csv"):
    """
    将K线数据保存为CSV文件
    
    参数:
        kline_list: K线数据列表
        filename: 保存的文件名
    """
    if not kline_list:
        print("没有数据可保存")
        return
    
    try:
        import csv
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            # 写入表头
            writer.writerow(['时间', '开盘价', '最高价', '最低价', '收盘价', 
                           '成交量', '成交额', '成交笔数'])
            
            # 写入数据
            for kline in kline_list:
                timestamp = int(kline['klineTime']) / 1000
                time_str = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
                writer.writerow([
                    time_str,
                    kline['open'],
                    kline['high'],
                    kline['low'],
                    kline['close'],
                    kline['size'],
                    kline['value'],
                    kline['trades']
                ])
        
        print(f"\n数据已保存到 {filename}")
    except Exception as e:
        print(f"保存CSV文件失败: {e}")

def get_historical_klines_by_time(start_time, end_time, size=200):
    """
    根据时间范围获取K线数据
    
    参数:
        start_time: 开始时间戳（毫秒）
        end_time: 结束时间戳（毫秒）
        size: 每次请求获取的数量
    """
    base_url = "https://pro.edgex.exchange/api/v1/public/quote/getKline"
    
    params = {
        "contractId": "10000001",
        "klineType": "MINUTE_15",
        "priceType": "LAST_PRICE",
        "size": str(size),
        "filterBeginKlineTimeInclusive": str(start_time),
        "filterEndKlineTimeExclusive": str(end_time)
    }
    
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        data = response.json()
        
        if data.get("code") == "SUCCESS":
            return data.get("data", {}).get("dataList", [])
        else:
            print(f"API返回错误: {data.get('msg')}")
            return None
    except Exception as e:
        print(f"请求失败: {e}")
        return None


if __name__ == "__main__":
    # 获取最新的100根K线
    klines = get_btc_klines(100)
    
    # 保存为CSV文件
    if klines:
        save_to_csv(klines)
    
    # 示例：获取指定时间范围的K线
    # from datetime import datetime, timedelta
    # end_time = int(datetime.now().timestamp() * 1000)
    # start_time = int((datetime.now() - timedelta(days=7)).timestamp() * 1000)
    # historical_klines = get_historical_klines_by_time(start_time, end_time)
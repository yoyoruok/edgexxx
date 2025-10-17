# EdgeX 量化交易系统

基于双指标策略的自动化量化交易系统，支持多币种交易和回测功能。

## 🎯 核心策略

### 指标1: MBO/MBI
- **MBO** = MA(25) - MA(200)
- **MBI** = 当前MBO - 上一个MBO
- 用于判断市场趋势方向

### 指标2: 系绳线 (Rope Line)
- **MS** = (HHV(50) + LLV(50)) / 2
- 用于触发买入机会和追踪止损

### 交易逻辑

#### 多头趋势 (MBI > 0)
- 不开空单
- 价格突破系绳线:
  - 空仓 → 开多
  - 持多 → 不动作
  - 持空 → 平空开多
- 价格跌破系绳线 → 止盈平多

#### 空头趋势 (MBI < 0)
- 不开多单
- 价格跌破系绳线:
  - 空仓 → 开空
  - 持空 → 不动作
  - 持多 → 平多开空
- 价格突破系绳线 → 止盈平空

## 📁 项目结构

```
.
├── main.py                 # 主程序
├── config.py              # 配置管理
├── strategy.py            # 策略模块
├── data_manager.py        # 数据管理
├── order_manager.py       # 订单管理
├── precision_manager.py   # 精度管理
├── rate_limiter.py        # API限速器
├── logger.py              # 日志管理
├── backtest.py            # 回测模块
├── requirements.txt       # 依赖包
├── .env                   # 环境变量（需创建）
└── logs/                  # 日志目录
```

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

创建 `.env` 文件:

```env
EDGEX_BASE_URL=https://pro.edgex.exchange
EDGEX_WS_URL=wss://quote.edgex.exchange
EDGEX_ACCOUNT_ID=你的账户ID
EDGEX_STARK_PRIVATE_KEY=你的Stark私钥
```

### 3. 配置交易参数

编辑 `config.py` 中的配置:

```python
# 交易对配置
self.trading_pairs = {
    "BTCUSDT": TradingPairConfig(
        contract_id="10000001",
        symbol="BTCUSDT",
        position_size=1000.0,  # 仓位大小（USDT）
        leverage=5,            # 杠杆倍数
        order_size=0.01,       # 单次成交数量
        tick_size=0.1,         # 价格精度
        size_precision=3       # 数量精度
    ),
}

# 策略参数
self.strategy = StrategyConfig(
    ma_short_period=25,
    ma_long_period=200,
    rope_period=50,
    stop_loss_pct=0.02,     # 止损2%
    take_profit_pct=0.05,   # 止盈5%
    slippage=0.001,         # 滑点0.1%
    timeframe="15m"         # K线周期
)
```

### 4. 运行交易

```bash
# 实盘交易
python main.py

# 回测模式
python main.py --backtest
```

## ✨ 主要特性

### 1. 实时数据更新 ⭐
- **自动刷新机制**: K线数据自动保持最新，无需手动更新
- **智能刷新频率**: 根据K线周期自动调整（15m/1分钟, 1h/5分钟, 4h/10分钟）
- **数据完整性**: 确保策略始终基于最新的历史数据
- 详见 [REALTIME_DATA.md](REALTIME_DATA.md)

### 2. 多币种交易
- 支持同时交易多个币种
- 独立的仓位管理和风险控制
- 可配置杠杆倍数

### 2. 单周期信号限制
- 每个K线周期只产生一个信号
- 防止重复开仓

### 3. 滑点控制
- 统一设置0.1%滑点
- 确保订单价格合理

### 4. 多周期支持
- 支持15m、1h、4h三种K线周期
- 可根据策略选择最优周期

### 5. API限速
- 自动控制请求频率
- 防止超过交易所限制
- 支持每秒和每分钟限制

### 6. 日志监控
- 完整的交易日志
- 信号生成记录
- 错误追踪
- 日志文件自动轮转

### 7. 回测功能
- 基于历史数据验证策略
- 完整的绩效指标
- 支持多周期回测

### 8. 配置安全
- API信息与代码分离
- 环境变量管理
- 敏感信息不暴露

### 9. 精度管理
- 自动对齐价格和数量精度
- 符合EdgeX市场规则
- 防止订单被拒绝

### 10. 模块化设计
- 清晰的代码结构
- 易于维护和扩展
- 可复用的组件

## 📊 回测示例

```python
# 准备历史数据
import pandas as pd

df = pd.read_csv("historical_data.csv")
df['timestamp'] = pd.to_datetime(df['timestamp'])
df.set_index('timestamp', inplace=True)

# 运行回测
backtest = Backtest(strategy, initial_capital=10000)
results = backtest.run(
    contract_id="10000001",
    symbol="BTCUSDT",
    df=df,
    position_size=1000.0
)

# 查看结果
backtest.print_results(results)
```

## 🔧 高级配置

### 精度管理

系统会自动从EdgeX获取合约精度信息，也可以手动配置:

```python
precision_manager.set_contract_info(
    contract_id="10000001",
    tick_size=0.1,       # 价格最小变动单位
    size_precision=3     # 数量小数位数
)
```

### 限速控制

```python
# 在config.py中配置
self.api = APIConfig(
    max_requests_per_second=10,
    max_orders_per_minute=100
)
```

### 风险管理

```python
# 在config.py中配置
self.strategy = StrategyConfig(
    stop_loss_pct=0.02,      # 2%止损
    take_profit_pct=0.05,    # 5%止盈
    slippage=0.001           # 0.1%滑点
)
```

## 📈 性能监控

系统会实时输出:
- 当前持仓状态
- API请求统计
- 总盈亏情况
- 交易历史记录

日志文件位于 `logs/` 目录，包含完整的交易记录。

## ⚠️ 风险提示

1. 量化交易存在风险，请在充分测试后使用
2. 建议先在测试网环境验证策略
3. 合理设置止损止盈，控制风险
4. 不要投入超过承受能力的资金
5. 定期检查系统运行状态

## 🔍 常见问题

### 1. 如何添加新的交易对？

在 `config.py` 中添加配置:

```python
"ETHUSDT": TradingPairConfig(
    contract_id="10000002",
    symbol="ETHUSDT",
    position_size=500.0,
    leverage=5,
    order_size=0.1,
    tick_size=0.01,
    size_precision=3
),
```

### 2. 如何修改K线周期？

在 `config.py` 中修改:

```python
self.strategy = StrategyConfig(
    timeframe="1h"  # 改为1小时
)
```

### 3. 如何查看交易历史？

交易历史保存在日志文件中，也可以在程序退出时查看摘要。

## 📝 更新日志

### v1.0.0 (2025-01-16)
- 初始版本发布
- 实现双指标策略
- 支持多币种交易
- 完整的回测功能
- 模块化架构设计

## 📧 技术支持

如有问题或建议，请参考EdgeX官方文档:
- API文档: https://docs.edgex.exchange
- 开发者社区: https://community.edgex.exchange

## 📄 许可证

本项目仅供学习和研究使用。
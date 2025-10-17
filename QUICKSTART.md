# 快速启动指南

## 📋 前置要求

1. **Python 3.8+** 
2. **EdgeX账户** （生产环境或测试网）
3. **API密钥** （Account ID 和 Stark Private Key）

## 🚀 5分钟快速上手

### 步骤1: 克隆或下载项目

```bash
# 创建项目目录
mkdir edgex-trading-bot
cd edgex-trading-bot

# 将所有文件放入此目录
```

### 步骤2: 安装依赖

```bash
pip install -r requirements.txt
```

### 步骤3: 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，填入你的账户信息
nano .env  # 或使用其他编辑器
```

在 `.env` 中配置:

```env
EDGEX_BASE_URL=https://pro.edgex.exchange
EDGEX_WS_URL=wss://quote.edgex.exchange
EDGEX_ACCOUNT_ID=你的账户ID
EDGEX_STARK_PRIVATE_KEY=你的Stark私钥
```

### 步骤4: 配置交易参数

编辑 `config.py`，根据你的需求调整:

```python
# 交易对配置
"BTCUSDT": TradingPairConfig(
    contract_id="10000001",
    symbol="BTCUSDT",
    position_size=100.0,    # 调整为你的仓位大小
    leverage=3,             # 调整杠杆倍数
    order_size=0.01,        # 调整单次下单量
    tick_size=0.1,
    size_precision=3
),

# 策略参数
strategy = StrategyConfig(
    ma_short_period=25,
    ma_long_period=200,
    rope_period=50,
    stop_loss_pct=0.02,      # 2%止损
    take_profit_pct=0.05,    # 5%止盈
    slippage=0.001,          # 0.1%滑点
    timeframe="15m"          # K线周期
)
```

### 步骤5: 运行系统

#### 方式A: 先回测验证策略

```bash
# 1. 准备历史数据
python prepare_backtest_data.py

# 2. 修改 backtest.py 中的数据加载部分
# 3. 运行回测
python main.py --backtest
```

#### 方式B: 直接实盘交易（谨慎！）

```bash
# 启动实盘交易
python main.py
```

**⚠️ 重要提示：**
- 首次使用建议在测试网环境测试
- 使用小资金测试系统稳定性
- 充分回测后再投入实盘

## 📊 监控运行状态

### 查看实时日志

```bash
# 日志保存在 logs/ 目录
tail -f logs/trading_*.log
```

### 系统会输出：

- 信号生成情况
- 订单执行状态
- 持仓信息
- 盈亏统计
- API请求统计

## 🛑 停止系统

```bash
# 按 Ctrl+C 优雅退出
# 系统会：
# 1. 打印交易历史
# 2. 显示总盈亏
# 3. 保存日志
# 4. 关闭连接
```

## 🔧 常见问题排查

### 1. 连接失败

```bash
# 检查网络连接
ping pro.edgex.exchange

# 检查API配置
cat .env
```

### 2. 订单被拒绝

可能原因：
- 价格精度不正确 → 检查 `tick_size` 配置
- 数量精度不正确 → 检查 `size_precision` 配置
- 余额不足 → 检查账户余额
- API限速 → 检查日志中的限速警告

### 3. 数据不足

```bash
# K线数据需要至少200根（用于计算200周期MA）
# 如果提示数据不足，等待几个周期后会自动补充
```

### 4. 查看详细日志

```bash
# 在 config.py 中设置
self.log_level = "DEBUG"  # 改为DEBUG级别
```

## 📈 优化建议

### 1. 回测优化流程

```bash
# 准备更多历史数据
python prepare_backtest_data.py  # 下载1000根K线

# 修改策略参数
nano config.py

# 运行回测
python main.py --backtest

# 分析结果，调整参数
# 重复以上步骤
```

### 2. 参数优化方向

- **MA周期**: 尝试 (20, 150) 或 (30, 250)
- **系绳线周期**: 尝试 30-70 之间
- **止损止盈**: 根据回测结果调整
- **K线周期**: 不同周期适合不同策略

### 3. 风险控制

```python
# 在 config.py 中设置
position_size=100.0,     # 减小仓位
leverage=2,              # 降低杠杆
stop_loss_pct=0.015,     # 收紧止损
```

## 🎯 下一步

1. **学习策略原理** - 理解MBO/MBI和系绳线指标
2. **充分回测** - 在不同市场环境下测试
3. **小额试验** - 用最小资金测试系统
4. **持续监控** - 定期检查系统状态
5. **优化改进** - 根据实际效果调整参数

## 📞 获取帮助

- EdgeX文档: https://docs.edgex.exchange
- 问题反馈: 查看项目README.md
- 社区支持: EdgeX开发者社区

---

**免责声明**: 量化交易存在风险，请谨慎使用。本系统仅供学习和研究使用。
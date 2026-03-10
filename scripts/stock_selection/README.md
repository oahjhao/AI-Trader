# A 股选股策略模块

## 概述

基于中证 1000 成分股的多因子选股策略，每周执行一次，输出 Top 10 选股结果。

## 策略逻辑

### 筛选池
- **中证 1000 成分股**（包含全部板块和 ST 股票）

### 筛选条件（AND 关系）
1. **252 日残差收益波动率**：前 50%（越低越好）
   - 使用 CAPM 模型计算个股相对于市场的残差波动率
   - 衡量股票的非系统性风险

2. **5 日评价换手率**：前 50%（越高越好）
   - 反映股票的交易活跃度

3. **5 日价格动量**：前 30%（越高越好）
   - 短期价格趋势强度

4. **20 日 Beta 值**：前 30%（越高越好）
   - 衡量股票相对于市场的弹性

### 最终排序
- 按**10 日价格动量**排序（越低越好），选取 Top 10
- 可以少于 10 只或没有（如果筛选后不足 10 只）

## 使用方法

### 基本用法
```bash
cd /home/admin/openclaw/workspace/Code/AI-Trader
source venv/bin/activate

# 使用今天日期执行选股
python data/A_stock/run_stock_selection.py

# 指定选股日期
python data/A_stock/run_stock_selection.py --date 2025-11-15

# 查看帮助
python data/A_stock/run_stock_selection.py --help
```

### 输出文件
- **路径**: `data/A_stock/output/sse_pick_YYYYMMDD.csv`
- **格式**:
  ```csv
  ts_code,stock_name
  600120.SH，浙江东方
  300773.SZ，拉卡拉
  ...
  ```

### 执行日志
```
============================================================
🎯 A 股选股策略执行
📅 选股日期：2025-11-15
============================================================
📊 获取中证 1000 成分股...
✅ 获取到 1000 只成分股
📝 获取 1000 只股票名称...
✅ 获取到 1000 只股票名称
📡 从 Tushare API 获取价格数据...
...
✅ 最终选中 10 只股票
💾 结果已保存：data/A_stock/output/sse_pick_20251115.csv
```

## 配置参数

在 `config.py` 中可调整：

```python
# 因子计算窗口
RESIDUAL_VOL_WINDOW = 60    # 残差波动率窗口（交易日）
TURNOVER_WINDOW = 5         # 换手率窗口
MOMENTUM_SHORT_WINDOW = 5   # 短期动量窗口
BETA_WINDOW = 20            # Beta 值窗口
MOMENTUM_RANK_WINDOW = 10   # 排序动量窗口

# 筛选比例
RESIDUAL_VOL_PERCENTILE = 0.5   # 残差波动率：前 50%
TURNOVER_PERCENTILE = 0.5       # 换手率：前 50%
MOMENTUM_PERCENTILE = 0.7       # 5 日动量：前 30%
BETA_PERCENTILE = 0.7           # 20 日 Beta：前 30%

# 最终选取数量
FINAL_TOP_N = 10
```

## 数据源

- **Tushare Pro**: 股票价格数据、成分股列表
- **Token**: 配置在 `.env` 文件的 `TUSHARE_TOKEN`

## 依赖安装

```bash
cd /home/admin/openclaw/workspace/Code/AI-Trader
python3.11 -m venv venv
source venv/bin/activate
pip install pandas scipy tushare python-dotenv
```

## 定时执行（可选）

每周执行一次，建议添加 cron 任务：

```bash
# 每周一早上 8:00 执行
0 8 * * 1 cd /home/admin/openclaw/workspace/Code/AI-Trader && source venv/bin/activate && python data/A_stock/run_stock_selection.py
```

## 集成到 AI-Trader

选股结果可被 AI-Trader 主程序读取：

```python
import pandas as pd

# 读取最新选股结果
from pathlib import Path
output_dir = Path("data/A_stock/output")
latest_file = sorted(output_dir.glob("sse_pick_*.csv"))[-1]
selected_stocks = pd.read_csv(latest_file)

# 在 AI-Trader 中使用选中的股票池
stock_pool = selected_stocks['ts_code'].tolist()
```

## 注意事项

1. **数据质量**: 确保 Tushare token 有效，数据覆盖足够长历史
2. **执行时间**: 首次运行需要获取 1000 只股票历史数据，约需 5-10 分钟
3. **结果验证**: 建议人工检查选股结果是否符合预期
4. **风险提示**: 本策略仅供参考，不构成投资建议

## 文件结构

```
stock_selection/
├── __init__.py              # 模块初始化
├── config.py                # 配置参数
├── data_loader.py           # 数据加载器
├── factor_calculator.py     # 因子计算器
├── stock_selector.py        # 选股主逻辑
└── README.md                # 说明文档

run_stock_selection.py       # 执行脚本
output/                      # 输出目录
└── sse_pick_YYYYMMDD.csv    # 选股结果
```

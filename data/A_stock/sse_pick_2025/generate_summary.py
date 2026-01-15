import pandas as pd
import os
from pathlib import Path

# 获取当前目录
current_dir = Path(__file__).parent

# 获取所有CSV文件
csv_files = sorted([f for f in os.listdir(current_dir) if f.endswith('.csv') and f != 'sse_pick_2025.csv'])

# 存储所有数据
all_data = []

# 处理每个CSV文件
for csv_file in csv_files:
    # 获取文件名中的月份和日期 (例如: 0103.csv -> 0103)
    date_str = csv_file.replace('.csv', '')
    
    # 构造完整日期 (2025 + 月份日期)
    full_date = f"2025{date_str}"
    
    # 读取CSV文件
    file_path = current_dir / csv_file
    try:
        df = pd.read_csv(file_path, encoding='utf-8')
    except:
        try:
            df = pd.read_csv(file_path, encoding='gbk')
        except:
            print(f"无法读取文件: {csv_file}")
            continue
    
    # 提取需要的列：证券代码和证券简称
    if '证券代码' in df.columns and '证券简称' in df.columns:
        for _, row in df.iterrows():
            all_data.append({
                'date': full_date,
                'con_code': row['证券代码'],
                'stock_name': row['证券简称']
            })
        print(f"处理完成: {csv_file} - {len(df)}条记录")
    else:
        print(f"文件格式不匹配: {csv_file}")

# 创建汇总DataFrame
result_df = pd.DataFrame(all_data)

# 保存到CSV文件（保存到上级目录 data/A_stock/）
output_file = current_dir.parent / 'sse_pick_2025.csv'
result_df.to_csv(output_file, index=False, encoding='utf-8-sig')

print(f"\n汇总完成！")
print(f"总共处理了 {len(csv_files)} 个文件")
print(f"生成了 {len(result_df)} 条记录")
print(f"输出文件: {output_file}")

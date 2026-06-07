"""
生成两份验收用测试数据:
  A. erp_employee_export.xlsx — 模拟现代 ERP 系统导出
  B. legacy_crm_export.csv — 模拟老旧 CRM 系统导出 (GBK)
"""
import pandas as pd
import numpy as np
import os
import random

random.seed(42)
np.random.seed(42)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

names = ['张三', '李四', '王五', '赵六', '钱七', '孙八', '周九', '吴十',
         '郑十一', '冯十二', '陈十三', '褚十四', '卫十五', '蒋十六', '沈十七']
departments = ['研发部', '市场部', '财务部', '人事部', '运维部']
genders = ['男', '女']


def random_phone():
    """生成各种格式的电话号码。"""
    base = f"{random.randint(100, 999)}{random.randint(1000, 9999)}{random.randint(1000, 9999)}"
    fmt = random.choice([
        lambda b: f"{b[:3]}-{b[3:7]}-{b[7:]}",       # 010-1234-5678
        lambda b: b,                                     # 01012345678
        lambda b: f"({b[:3]}){b[3:7]}{b[7:]}",          # (010)12345678
        lambda b: f"{b[:3]} {b[3:7]} {b[7:]}",          # 010 1234 5678
    ])
    return fmt(base)


def random_date():
    """生成多种格式的日期。"""
    y, m, d = random.randint(2018, 2024), random.randint(1, 12), random.randint(1, 28)
    fmt = random.choices(
        [lambda: f"{y}/{m:02d}/{d:02d}",            # 2023/01/15
         lambda: f"{y}-{m:02d}-{d:02d}",            # 2023-01-15
         lambda: f"{y}年{m}月{d}日",                 # 2023年1月15日
         lambda: f"{y}{m:02d}{d:02d}"],             # 20230115
        weights=[0.4, 0.35, 0.15, 0.1]
    )[0]
    return fmt()


def random_salary():
    """生成带货币符号和千分位的工资金额。"""
    amount = random.randint(5000, 50000)
    return f"¥{amount:,}"


domains = ['company.com', 'tech.cn', 'corp.com', 'startup.io', 'enterprise.cn']


print("=== Generating Test Data A: Modern ERP Export ===")

rows_a = []
for i in range(200):
    name_idx = i % len(names)
    rows_a.append({
        '员工编号': f'EMP{1000 + i:04d}',
        '姓名': names[name_idx] + (f'{i:02d}' if i >= len(names) else ''),
        '性别': genders[i % 2],
        '部门': departments[i % len(departments)],
        '入职日期': random_date(),
        '联系电话': random_phone(),
        '基本工资': random_salary(),
        '邮箱': (f'{names[name_idx].lower()}{i}@{random.choice(domains)}'
                if i % 40 != 0 else None),  # 5行缺失邮箱
        '备注': ('这是一段正常的备注信息' if i % 100 != 0
                else '这是一段超长的备注信息' * 80),  # 2行超长文本
        '地址': random.choice([
            '北京市海淀区中关村大街1号',
            '上海市浦东新区陆家嘴环路100号',
            '深圳市南山区科技园路200号',
            '广州市天河区体育西路300号',
            '杭州市西湖区文三路400号',
        ]),
    })

df_a = pd.DataFrame(rows_a)
path_a = os.path.join(DATA_DIR, 'erp_employee_export.xlsx')
df_a.to_excel(path_a, index=False, engine='openpyxl')
print(f"  Created: {path_a}")
print(f"  Rows: {len(df_a)}, Columns: {len(df_a.columns)}")
print(f"  Date formats: {df_a['入职日期'].iloc[:5].tolist()}")
print(f"  Phone formats: {df_a['联系电话'].iloc[:3].tolist()}")
print(f"  Salary formats: {df_a['基本工资'].iloc[:3].tolist()}")
print(f"  Missing emails: {df_a['邮箱'].isna().sum()}")


print("\n=== Generating Test Data B: Legacy CRM Export (GBK) ===")

rows_b = []
customer_names = ['华创科技', '鑫达集团', '瑞丰实业', '明泰股份', '恒通有限公司',
                  '天元科技', '大地集团', '阳光实业', '星辰股份', '万通有限公司']

for i in range(500):
    cid = f'CUST{10000 + i:05d}'
    cname = random.choice(customer_names) + (f'#{i}' if i >= 10 else '')
    rows_b.append({
        '客户ID': cid,
        '客户名称': cname,
        '行业类别': random.choice(['IT', '金融', '制造', '零售', '医疗']),
        '联系人': (f'{random.choice(names)}' if i % 25 != 0 else None),  # 20行缺失
        '联系电话': random_phone(),
        '签约金额': str(random.randint(10000, 5000000)),
        '签约日期': (f'{random.randint(2015, 2024)}{random.randint(1, 12):02d}{random.randint(1, 28):02d}'
                    if i % 60 != 0 else '99999999'),  # YYYYMMDD, 3行非法日期
        '客户等级': (random.choice(['A', 'B', 'C', 'D']) if i % 100 != 0
                    else random.choice(['a', 'b', 'c', 'd'])),  # 5行小写
        '跟进记录': f'跟进记录第{i}号客户\r\n联系人已确认需求\r\n预计签约金额待确认',
    })

# 故意添加 10 行完全重复数据
duplicates = rows_b[:10]
for d in duplicates:
    rows_b.append(d.copy())

df_b = pd.DataFrame(rows_b)
path_b = os.path.join(DATA_DIR, 'legacy_crm_export.csv')
df_b.to_csv(path_b, index=False, encoding='gbk')
print(f"  Created: {path_b}")
print(f"  Rows: {len(df_b)}, Columns: {len(df_b.columns)}")
print(f"  Encoding: GBK")
print(f"  Date format: YYYYMMDD (3 rows illegal: 99999999)")
print(f"  Duplicate rows: 10 (total 510 rows)")
print(f"  Missing contacts: {df_b['联系人'].isna().sum()}")
print(f"  Lowercase grades: {sum(1 for v in df_b['客户等级'] if v in ['a','b','c','d'])}")

print("\n=== Test data generation complete ===")

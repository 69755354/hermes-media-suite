#!/usr/bin/env python3
"""分析 DeepSeek 账单 CSV（cost + amount 两个文件），算新旧价对比/高峰占比/涨幅。
用法: python3 analyze_cost_csv.py cost-xxx.csv amount-xxx.csv [旧价json可选]
旧价默认: Flash 0.02/1/2、Pro 0.025/3/6 元每百万（2026-08-17 前）
"""
import csv, io, sys, json
from collections import defaultdict

def load_rows(path):
    return list(csv.DictReader(io.StringIO(open(path).read())))

OLD_DEFAULT = {
    'deepseek-v4-flash': {'input_cache_hit_tokens': 0.02/1e6, 'input_cache_miss_tokens': 1/1e6, 'output_tokens': 2/1e6},
    'deepseek-v4-pro':   {'input_cache_hit_tokens': 0.025/1e6, 'input_cache_miss_tokens': 3/1e6, 'output_tokens': 6/1e6},
}

def is_peak(hour):  # 高峰 9-12、14-18
    return (9 <= hour < 12) or (14 <= hour < 18)

def main():
    if len(sys.argv) < 3:
        print('用法: python3 analyze_cost_csv.py cost.csv amount.csv'); return
    cost_rows = load_rows(sys.argv[1])
    amount_rows = [r for r in load_rows(sys.argv[2]) if r['price']]

    # 1. cost CSV 汇总
    new_total = defaultdict(float); new_by_hour = defaultdict(float)
    for r in cost_rows:
        new_total[r['model']] += float(r['cost'])
        new_by_hour[r['start_time_iso'][11:13]] += float(r['cost'])
    tot = sum(new_total.values())
    peak = sum(v for h, v in new_by_hour.items() if is_peak(int(h)))
    print('=== 新价总成本 ===')
    for m, v in sorted(new_total.items(), key=lambda x: -x[1]):
        print(f'  {m}: {v:.2f} 元')
    print(f'  合计: {tot:.2f} 元 | 高峰时段: {peak:.2f} 元 ({peak/tot*100:.0f}%)')

    # 2. amount CSV: price×amount + 同用量旧价
    tokens = defaultdict(lambda: defaultdict(int))
    new_am = defaultdict(float)
    for r in amount_rows:
        m, typ, amt = r['model'], r['type'], float(r['amount'])
        tokens[m][typ] += amt
        new_am[m] += float(r['price']) * amt
    print('\n=== 涨幅（同用量新旧价）===')
    tot_new = tot_old = 0.0
    for m in OLD_DEFAULT:
        old = sum(amt * OLD_DEFAULT[m][t] for t, amt in tokens[m].items())
        tot_new += new_am[m]; tot_old += old
        if old > 0:
            print(f'  {m}: 新 {new_am[m]:.2f} | 旧 {old:.2f} | 涨 {new_am[m]-old:+.2f} 元 ({(new_am[m]/old-1)*100:+.0f}%)')
    print(f'  合计: 新 {tot_new:.2f} | 旧 {tot_old:.2f} | 涨 {tot_new-tot_old:+.2f} 元 ({(tot_new/tot_old-1)*100:+.0f}%)')

    # 3. 类型明细
    print('\n=== 按类型 ===')
    for m in OLD_DEFAULT:
        print(f'  {m}:')
        for t in ['input_cache_hit_tokens', 'input_cache_miss_tokens', 'output_tokens']:
            amt = tokens[m][t]
            if amt:
                print(f'    {t}: {amt/1e6:,.1f}M tokens → {new_am[m]*amt/sum(tokens[m].values()):.2f} 元(估)')

if __name__ == '__main__':
    main()

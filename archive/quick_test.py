"""
快速验证：修改 .smp 后按 Ctrl+F，观察行为
"""
import os
import json
import time
import ctypes

# 路径
LDP9_DIR = r"F:\leidian\LDPlayer9"
CUSTOMIZE_CONFIGS = os.path.join(LDP9_DIR, "vms", "customizeConfigs")

# 找到某个游戏的 .smp
# 先列出所有 .smp
smp_files = [f for f in os.listdir(CUSTOMIZE_CONFIGS) if f.endswith('.smp')]
print("可用的游戏配置：")
for f in smp_files:
    print(f"  {f}")

if smp_files:
    # 读第一个看看当前 keyboardId 是什么
    test_smp = os.path.join(CUSTOMIZE_CONFIGS, smp_files[0])
    with open(test_smp, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    res = list(config['resolutionRelatives'].keys())[0]
    current_kid = config['resolutionRelatives'][res].get('keyboardId', '')
    print(f"\n文件: {smp_files[0]}")
    print(f"分辨率: {res}")
    print(f"当前 keyboardId: '{current_kid}'")
    
    # 列出 customizeConfigs 中的所有 .kmp 文件，按字母排序
    kmps = sorted([f for f in os.listdir(CUSTOMIZE_CONFIGS) if f.endswith('.kmp')])
    print(f"\n所有 .kmp 文件（按字母序）:")
    for i, k in enumerate(kmps):
        marker = " ← 当前" if k == current_kid else ""
        print(f"  {i}: {k}{marker}")
    
    # 找一个目标 .kmp
    print(f"\n当前 keyboardId 的索引: {kmps.index(current_kid) if current_kid in kmps else '不在列表中'}")

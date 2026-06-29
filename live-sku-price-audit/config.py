"""
配置文件
"""

import os
import sys

# 注意：这个 BASE_DIR 在源码运行时有效
# 打包后，app.py 会重新计算并覆盖这个值
if getattr(sys, 'frozen', False):
    # PyInstaller 打包后的 EXE 运行
    base_dir = os.path.dirname(sys.executable)
    # 如果 exe 在 _internal 目录中，向上回退一级
    if os.path.basename(base_dir).lower() == '_internal':
        base_dir = os.path.dirname(base_dir)
    BASE_DIR = base_dir
else:
    # 源码运行
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG = {
    # 输入目录（程序会列出该目录下的 xlsx 文件供选择）
    'input_dir': os.path.join(BASE_DIR, 'input'),

    # 价格门槛（业务人员每次设定）
    'threshold_price': 6.0,

    # 输出目录
    'output_dir': os.path.join(BASE_DIR, 'output'),
    'screenshot_dir': os.path.join(BASE_DIR, 'output', 'screenshots'),

   # 并发配置
   # 测价 worker 浏览器数量；Mac 可适当提高，Windows 若出现 wareBusiness 大量超时再降回 3
    'concurrent_workers': 5,

    # 防爬配置
    'delay_min': 1,      # 最小延迟（秒）
    'delay_max': 3,      # 最大延迟（秒）

    # 登录状态文件
    'auth_file': os.path.join(BASE_DIR, 'jd_auth.json'),

    # SKU 列名（用于读取 Excel）
    'sku_column': '商品SKU',
    'price_column': '价格',
    'image_column': '图片',
    'remark_column': '备注',
}

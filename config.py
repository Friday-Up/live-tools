"""
配置文件
"""

import os
import sys

# 兼容 PyInstaller 打包后的路径
def get_base_dir():
    """获取程序根目录（兼容源码和打包模式）"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后的 EXE 运行
        return os.path.dirname(sys.executable)
    else:
        # 源码运行
        return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = get_base_dir()

CONFIG = {
    # 输入目录（程序会列出该目录下的 xlsx 文件供选择）
    'input_dir': os.path.join(BASE_DIR, 'input'),

    # 价格门槛（业务人员每次设定）
    'threshold_price': 6.0,

    # 输出目录
    'output_dir': os.path.join(BASE_DIR, 'output'),
    'screenshot_dir': os.path.join(BASE_DIR, 'output', 'screenshots'),

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

"""
清理工具
负责清理 Playwright CLI 等临时文件
"""

import os
import shutil
import glob
from datetime import datetime, timedelta


def get_playwright_cli_dir():
    """
    获取 Playwright CLI 临时目录路径
    通常在项目根目录或用户主目录下
    """
    # 可能的目录位置（按优先级）
    possible_dirs = [
        # 当前工作目录下
        os.path.join(os.getcwd(), '.playwright-cli'),
        # 项目根目录下（从当前文件向上查找）
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.playwright-cli'),
        # 用户主目录下
        os.path.join(os.path.expanduser('~'), '.playwright-cli'),
    ]

    for dir_path in possible_dirs:
        if os.path.exists(dir_path):
            return dir_path

    return None


def cleanup_playwright_cli(keep_days=0, dry_run=False):
    """
    清理 Playwright CLI 临时文件

    Args:
        keep_days: 保留最近几天的文件（0表示全部清理）
        dry_run: 是否为试运行模式（只打印不删除）

    Returns:
        dict: 清理结果统计
    """
    result = {
        'cleaned_dirs': [],
        'cleaned_files': 0,
        'freed_space': 0,
        'errors': []
    }

    # 查找所有可能的 Playwright CLI 目录
    # 注意：Playwright CLI 会在执行命令时的当前工作目录下创建 .playwright-cli
    # 所以需要在多个可能的位置查找
    search_paths = [
        os.getcwd(),  # 当前工作目录
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),  # 项目根目录
        os.path.expanduser('~'),  # 用户主目录
        '/Users/zhangyaolong.5/Friday/idea_workspace/me',  # 已知的工作目录
    ]

    # 去重
    search_paths = list(set(search_paths))

    for search_path in search_paths:
        playwright_dir = os.path.join(search_path, '.playwright-cli')

        if not os.path.exists(playwright_dir):
            continue

        try:
            if keep_days <= 0:
                # 清理整个目录
                if dry_run:
                    size = get_dir_size(playwright_dir)
                    file_count = count_files(playwright_dir)
                    print(f"[试运行] 将删除目录: {playwright_dir}")
                    print(f"         包含 {file_count} 个文件，大小 {format_size(size)}")
                    result['cleaned_dirs'].append(playwright_dir)
                    result['cleaned_files'] += file_count
                    result['freed_space'] += size
                else:
                    size = get_dir_size(playwright_dir)
                    file_count = count_files(playwright_dir)
                    shutil.rmtree(playwright_dir)
                    print(f"✅ 已清理: {playwright_dir}")
                    print(f"   释放空间: {format_size(size)}，文件数: {file_count}")
                    result['cleaned_dirs'].append(playwright_dir)
                    result['cleaned_files'] += file_count
                    result['freed_space'] += size
            else:
                # 只清理指定天数前的文件
                cutoff_time = datetime.now() - timedelta(days=keep_days)
                cleaned, space = cleanup_old_files(playwright_dir, cutoff_time, dry_run)
                if cleaned > 0:
                    result['cleaned_dirs'].append(playwright_dir)
                    result['cleaned_files'] += cleaned
                    result['freed_space'] += space

        except Exception as e:
            error_msg = f"清理失败 {playwright_dir}: {e}"
            result['errors'].append(error_msg)
            print(f"❌ {error_msg}")

    return result


def cleanup_old_files(dir_path, cutoff_time, dry_run=False):
    """
    清理指定时间之前的文件

    Args:
        dir_path: 目录路径
        cutoff_time: 截止时间
        dry_run: 是否为试运行

    Returns:
        tuple: (清理文件数, 释放空间)
    """
    cleaned = 0
    freed_space = 0

    for root, dirs, files in os.walk(dir_path):
        for file in files:
            file_path = os.path.join(root, file)
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                if mtime < cutoff_time:
                    size = os.path.getsize(file_path)
                    if dry_run:
                        print(f"[试运行] 将删除: {file_path} ({format_size(size)})")
                    else:
                        os.remove(file_path)
                    cleaned += 1
                    freed_space += size
            except Exception as e:
                print(f"⚠️ 无法处理文件 {file_path}: {e}")

        # 清理空目录
        if not dry_run:
            for dir_name in dirs:
                dir_full_path = os.path.join(root, dir_name)
                try:
                    if os.path.exists(dir_full_path) and not os.listdir(dir_full_path):
                        os.rmdir(dir_full_path)
                except:
                    pass

    return cleaned, freed_space


def get_dir_size(dir_path):
    """获取目录总大小"""
    total = 0
    for root, dirs, files in os.walk(dir_path):
        for file in files:
            file_path = os.path.join(root, file)
            try:
                total += os.path.getsize(file_path)
            except:
                pass
    return total


def count_files(dir_path):
    """统计目录中的文件数量"""
    count = 0
    for root, dirs, files in os.walk(dir_path):
        count += len(files)
    return count


def format_size(size_bytes):
    """格式化文件大小显示"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def auto_cleanup():
    """
    自动清理入口
    在程序启动时调用，清理所有 Playwright 临时文件
    """
    print("\n🧹 正在检查 Playwright 临时文件...")

    result = cleanup_playwright_cli(keep_days=0, dry_run=False)

    if result['cleaned_files'] > 0:
        print(f"\n✅ 清理完成:")
        print(f"   清理目录: {len(result['cleaned_dirs'])} 个")
        print(f"   删除文件: {result['cleaned_files']} 个")
        print(f"   释放空间: {format_size(result['freed_space'])}")
    else:
        print("✅ 未发现需要清理的临时文件")

    if result['errors']:
        print(f"\n⚠️ 清理过程中有 {len(result['errors'])} 个错误")

    print()


if __name__ == "__main__":
    # 独立运行清理脚本
    print("="*60)
    print("🧹 Playwright 临时文件清理工具")
    print("="*60)
    auto_cleanup()

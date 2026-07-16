#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PyInstaller 打包脚本 — 一键构建发布包

用法:
    python scripts/package.py           # 构建 --onefile exe
    python scripts/package.py --dir     # 构建 --onedir (方便调试)
    python scripts/package.py --clean   # 构建前清理 build/ dist/

输出:
    dist_package/AutoInputSwitcher.exe  (单文件版本)
    或 dist_package/AutoInputSwitcher/  (目录版本, 含全部依赖)

发布包结构:
    AutoInputSwitcher_v1.0/
    ├── AutoInputSwitcher.exe    # 主程序
    ├── dist/                    # C++ 预编译组件 (exe 同目录读取)
    ├── games/                   # 游戏数据 (可独立更新，无需重新打包)
    ├── config/                  # 默认配置
    ├── locales/                 # 翻译文件
    └── README.txt               # 快速开始
"""

import os
import sys
import json
import shutil
import argparse
import subprocess


# ---- 路径 ----
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_ROOT)

OUTPUT_NAME = "AutoInputSwitcher"
DIST_DIR = os.path.join(PROJECT_ROOT, "dist_package")
BUILD_DIR = os.path.join(PROJECT_ROOT, "build_temp")
SPEC_FILE = os.path.join(PROJECT_ROOT, "AutoInputSwitcher.spec")

# 数据目录 (随 exe 分发，放在 exe 同目录下读取，而非打包进 exe)
DATA_DIRS = ["dist", "games", "config", "locales"]

# 隐藏导入 (PyInstaller 可能漏掉)
HIDDEN_IMPORTS = [
    "cv2",
    "numpy",
    "PIL",
    "dxcam",
    "win32gui",
    "win32process",
    "win32api",
    "PySide6.QtCore",
    "PySide6.QtWidgets",
    "PySide6.QtGui",
]


def clean():
    """清理构建产物。"""
    for path in [DIST_DIR, BUILD_DIR, SPEC_FILE]:
        if os.path.exists(path):
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            print(f"  已删除: {path}")


def build(onefile: bool = True):
    """执行 PyInstaller 打包。"""
    print(f"[打包] 模式: {'--onefile' if onefile else '--onedir'}")
    print(f"[打包] 输出: {DIST_DIR}")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--clean",
        f"--name={OUTPUT_NAME}",
        f"--distpath={DIST_DIR}",
        f"--workpath={BUILD_DIR}",
        f"--specpath={PROJECT_ROOT}",
        "--noconfirm",
        "--windowed",       # 不弹出控制台窗口
        "--icon=NONE",      # 后续可替换为自定义图标
    ]

    if onefile:
        cmd.append("--onefile")
    else:
        cmd.append("--onedir")

    # 添加隐藏导入
    for imp in HIDDEN_IMPORTS:
        cmd.extend(["--hidden-import", imp])

    # 入口脚本
    cmd.append("main.py")

    print(f"[打包] 命令: {' '.join(cmd[:6])} ...")
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print(f"[打包] PyInstaller 返回码 {result.returncode}")
        sys.exit(result.returncode)


def build_package(onefile: bool = True):
    """构建完整发布包。"""
    # 打包
    build(onefile=onefile)

    exe_path = os.path.join(DIST_DIR, f"{OUTPUT_NAME}.exe")
    if onefile:
        if not os.path.exists(exe_path):
            print(f"[错误] 未找到产物: {exe_path}")
            sys.exit(1)
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"[打包] 产物: {exe_path} ({size_mb:.1f} MB)")
    else:
        dir_path = os.path.join(DIST_DIR, OUTPUT_NAME)
        if not os.path.isdir(dir_path):
            print(f"[错误] 未找到产物目录: {dir_path}")
            sys.exit(1)

    # 复制数据目录到 exe 同路径
    for d in DATA_DIRS:
        src_dir = os.path.join(PROJECT_ROOT, d)
        dst_dir = os.path.join(DIST_DIR, d)
        if os.path.isdir(src_dir):
            if os.path.exists(dst_dir):
                shutil.rmtree(dst_dir)
            shutil.copytree(src_dir, dst_dir)
            print(f"[打包] 复制 {d}/")

    # ── 清理发布版 settings.json ──
    # 移除开发环境硬编码值，确保用户侧首次启动时自动检测
    _settings_path = os.path.join(DIST_DIR, "config", "settings.json")
    if os.path.isfile(_settings_path):
        with open(_settings_path, "r", encoding="utf-8") as f:
            _s = json.load(f)
        _s.setdefault("ldplayer", {})["install_path"] = ""
        _s.setdefault("gui", {})["language"] = ""
        with open(_settings_path, "w", encoding="utf-8") as f:
            json.dump(_s, f, indent=2, ensure_ascii=False)
        print("[打包] 已清理 settings.json (install_path & language → 空)")

    # 复制 README
    readme_src = os.path.join(PROJECT_ROOT, "README.md")
    if os.path.exists(readme_src):
        # 简单文本版本
        readme_dst = os.path.join(DIST_DIR, "README.txt")
        with open(readme_src, "r", encoding="utf-8") as f:
            content = f.read()
        with open(readme_dst, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[打包] 复制 README")

    print(f"\n[打包] 完成! 发布包位于: {DIST_DIR}")
    print(f"[打包] 用户解压后运行 AutoInputSwitcher.exe 即可。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="构建 LDPlayer Auto Input Switcher 发布包")
    parser.add_argument("--dir", action="store_true",
                        help="使用 --onedir 模式 (默认 --onefile)")
    parser.add_argument("--clean", action="store_true",
                        help="仅清理构建产物")
    args = parser.parse_args()

    if args.clean:
        clean()
    else:
        build_package(onefile=not args.dir)

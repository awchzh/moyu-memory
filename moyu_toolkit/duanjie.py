"""
duanjie.py — MOYU 断界集成模块（转接到独立CLI）

通过 MOYU 控制断界的启停。
moyu duanjie on [--duration N]  启动断界
moyu duanjie off                 关闭断界
moyu duanjie status              查看断界运行状态
moyu duanjie logs [--tail N]    查看日志

所有功能由 ~/workspace/断界/duanjie.py 实现，此处仅为转接层。
"""

import os
import subprocess
import sys
from pathlib import Path

_DUANJIE_CLI = Path.home() / "workspace" / "断界" / "duanjie.py"


def _cli(args: list):
    """调用独立 CLI。"""
    if not _DUANJIE_CLI.exists():
        print("❌ 断界未安装。请先安装断界项目：")
        print("   git clone ... ~/workspace/断界")
        print("   或查看: https://github.com/...")
        return
    subprocess.run([sys.executable, str(_DUANJIE_CLI)] + args)


def on(duration: int = 60):
    args = ["on"]
    if duration != 60:
        args += ["--duration", str(duration)]
    _cli(args)


def off():
    _cli(["off"])


def status():
    _cli(["status"])


def logs(tail: int = 20):
    _cli(["logs", "--tail", str(tail)])


def main(args: list):
    if not args or args[0] in ("help", "--help"):
        print("""用法: moyu duanjie <子命令>

子命令:
  on [--duration N]  启动断界（默认60分钟后自动关闭）
  off                 关闭断界
  status              查看断界运行状态
  logs [--tail N]    查看日志
  help                显示本帮助
""")
        return

    cmd = args[0]

    if cmd == "on":
        duration = 60
        if "--duration" in args:
            idx = args.index("--duration")
            if idx + 1 < len(args):
                try:
                    duration = int(args[idx + 1])
                except ValueError:
                    print("❌ duration 必须是数字", file=sys.stderr)
                    return
        on(duration)

    elif cmd == "off":
        off()

    elif cmd == "status":
        status()

    elif cmd == "logs":
        tail = 20
        if "--tail" in args:
            idx = args.index("--tail")
            if idx + 1 < len(args):
                try:
                    tail = int(args[idx + 1])
                except ValueError:
                    pass
        logs(tail)

    else:
        print(f"❌ 未知子命令: {cmd}")
        sys.exit(1)

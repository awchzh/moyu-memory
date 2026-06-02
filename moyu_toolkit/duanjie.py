"""
duanjie.py — MOYU 断界集成模块

通过 MOYU 控制断界的启停。
moyu duanjie on [--duration N]  启动断界（默认60分钟后自动关闭）
moyu duanjie off                 关闭断界
moyu duanjie status              查看断界运行状态
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

# ── 路径 ──
_HERMES_CONFIG = Path.home() / ".hermes" / "config.yaml"
_DUANJIE_PROXY = Path.home() / "workspace" / "断界" / "src" / "proxy.py"
_DUANJIE_DIR = Path.home() / "workspace" / "断界"
_DUANJIE_LOG = Path.home() / ".duanjie" / "run.log"
_DUANJIE_STATE = Path.home() / ".duanjie" / "state.json"


def _state() -> dict:
    """读取断界状态文件。"""
    if _DUANJIE_STATE.exists():
        try:
            return json.loads(_DUANJIE_STATE.read_text())
        except Exception:
            pass
    return {"running": False, "started_at": None, "duration": None, "pid": None}


def _save_state(s: dict):
    """写入断界状态文件。"""
    _DUANJIE_STATE.parent.mkdir(parents=True, exist_ok=True)
    _DUANJIE_STATE.write_text(json.dumps(s, ensure_ascii=False, indent=2))


def _is_proxy_running() -> bool:
    """检查 proxy.py 进程是否在运行。"""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "proxy.py"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


def _modify_base_url(target: str):
    """修改 Hermes config 中的 base_url。"""
    if not _HERMES_CONFIG.exists():
        print("❌ Hermes 配置文件不存在", file=sys.stderr)
        return False
    try:
        content = _HERMES_CONFIG.read_text()
        if "localhost:8899" in content:
            # 已经是断界模式
            return True
        backup = _HERMES_CONFIG.with_suffix(".yaml.no-duanjie")
        if not backup.exists():
            backup.write_text(content)
        # 替换 model 块下的 base_url
        import re
        new_content = re.sub(
            r'(^model:.*\n\s+base_url: )https://api\.deepseek\.com/v1',
            r'\1http://127.0.0.1:8899/v1',
            content,
            flags=re.MULTILINE
        )
        _HERMES_CONFIG.write_text(new_content)
        return True
    except Exception as e:
        print(f"❌ 修改配置失败: {e}", file=sys.stderr)
        return False


def _restore_base_url():
    """恢复 Hermes config 中的 base_url。"""
    if not _HERMES_CONFIG.exists():
        return False
    try:
        content = _HERMES_CONFIG.read_text()
        backup = _HERMES_CONFIG.with_suffix(".yaml.no-duanjie")
        if backup.exists():
            _HERMES_CONFIG.write_text(backup.read_text())
            return True
        # 没有备份，直接替换
        import re
        new_content = re.sub(
            r'(^model:.*\n\s+base_url: )http://127\.0\.0\.1:8899/v1',
            r'\1https://api.deepseek.com/v1',
            content,
            flags=re.MULTILINE
        )
        _HERMES_CONFIG.write_text(new_content)
        return True
    except Exception as e:
        print(f"❌ 恢复配置失败: {e}", file=sys.stderr)
        return False


def _restart_webui():
    """重启 Hermes WebUI。"""
    try:
        subprocess.run(
            ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/ai.hermes.webui"],
            capture_output=True, timeout=10
        )
        return True
    except Exception:
        return False


def _schedule_auto_stop(duration_minutes: int):
    """通过 cron 设置定时关闭断界。"""
    try:
        from moyu_toolkit import cronjob
        cronjob(
            action="create",
            name=f"duanjie-auto-stop-{int(time.time())}",
            prompt="关闭断界。执行 moyu duanjie off。",
            schedule=f"in {duration_minutes}m",
            repeat=1,
            deliver="local",
        )
        return True
    except Exception:
        return False


# ════════════════════════════════════════
# 公开接口
# ════════════════════════════════════════


def on(duration: int = 60):
    """启动断界。

    Args:
        duration: 自动关闭时间（分钟），默认60。传0表示不自动关闭。
    """
    if not _DUANJIE_PROXY.exists():
        print("❌ 断界代码不存在，请检查 ~/workspace/断界/")
        return

    if _is_proxy_running():
        print("⚠️ 断界已在运行中")
        return

    # 启动断界代理
    _DUANJIE_LOG.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [sys.executable, str(_DUANJIE_PROXY)],
        stdout=open(_DUANJIE_LOG, "a"),
        stderr=subprocess.STDOUT,
        cwd=str(_DUANJIE_DIR),
    )

    # 修改 Hermes 配置
    _modify_base_url("http://127.0.0.1:8899/v1")

    # 保存状态
    s = {
        "running": True,
        "pid": proc.pid,
        "started_at": time.time(),
        "duration": duration,
    }
    _save_state(s)

    print(f"✅ 断界已启动 (PID: {proc.pid})")
    print(f"   Hermes 配置已切换 → localhost:8899")

    # 重启 WebUI
    if _restart_webui():
        print("   WebUI 已重启，刷新页面即可")
    else:
        print("   ⚠️ WebUI 重启失败，请手动刷新")

    # 设置自动关闭
    if duration > 0:
        _schedule_auto_stop(duration)
        print(f"   ⏱  {duration} 分钟后自动关闭")


def off():
    """关闭断界。"""
    # 关闭代理进程
    subprocess.run(["pkill", "-f", "proxy.py"], capture_output=True, timeout=5)

    # 恢复 Hermes 配置
    _restore_base_url()

    # 重启 WebUI
    _restart_webui()

    # 更新状态
    _save_state({"running": False, "started_at": None, "duration": None, "pid": None})

    print("✅ 断界已关闭")
    print("   Hermes 配置已恢复 → api.deepseek.com")
    if _restart_webui():
        print("   WebUI 已重启，刷新页面即可")


def status():
    """查看断界运行状态。"""
    running = _is_proxy_running()
    s = _state()

    print()
    print("  断界 DuanJie — 状态")
    print("  " + "=" * 30)

    if running:
        print(f"  🟢 运行中")
        if s.get("started_at"):
            elapsed = int(time.time() - s["started_at"])
            mins, secs = divmod(elapsed, 60)
            print(f"  已运行: {mins}分{secs}秒")
        if s.get("duration", 0) > 0:
            remaining = max(0, s["duration"] * 60 - elapsed)
            rmins, rsecs = divmod(remaining, 60)
            print(f"  剩余: {rmins}分{rsecs}秒")
    else:
        print(f"  🔴 未运行")

    # 检查配置状态
    if _HERMES_CONFIG.exists():
        content = _HERMES_CONFIG.read_text()
        if "localhost:8899" in content:
            print(f"  Hermes 配置: → localhost:8899（断界模式）")
        else:
            print(f"  Hermes 配置: → api.deepseek.com（直连模式）")

    print()

    # 检查日志
    if _DUANJIE_LOG.exists():
        lines = _DUANJIE_LOG.read_text().strip().split("\n")
        last = lines[-3:] if len(lines) >= 3 else lines
        if last and last[0]:
            print("  最近日志:")
            for line in last:
                print(f"    {line[:100]}")


def main(args: list):
    """CLI 入口。"""
    if not args or args[0] in ("help", "--help"):
        print("""用法: moyu duanjie <子命令>

子命令:
  on [--duration N]  启动断界（默认60分钟后自动关闭，传0不自动关）
  off                 关闭断界
  status              查看断界运行状态
  help                显示本帮助

示例:
  moyu duanjie on             启动，60分钟自动关
  moyu duanjie on --duration 120  启动，120分钟自动关
  moyu duanjie on --duration 0    启动，不自动关
  moyu duanjie off             手动关闭
  moyu duanjie status          查看状态
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

    else:
        print(f"❌ 未知子命令: {cmd}，可用命令: on, off, status", file=sys.stderr)

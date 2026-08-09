# -*- coding: utf-8 -*-
"""
常驻 Chromium：监听 CDP 9222，所有平台共用 browser_data/xhs_user_data_dir/ 登录态。

MediaCrawler（ENABLE_CDP_MODE=True + CDP_CONNECT_EXISTING=True）及其他 skill
通过 connect_over_cdp("http://localhost:9222") 接入本实例。

后台运行（须在项目根目录）：
    .venv/bin/python3 tools/resident_browser.py &

验证：
    curl -s http://localhost:9222/json/version

退出：Ctrl+C 或 kill 进程；异常退出（137/SIGKILL）后重启需先删 SingletonLock，
    详见 skills/mediacrawler/SKILL.md「故障排查」。
"""

import glob
import os
import signal
import sys
import time

# 让脚本能 import 项目内 tools.browser_launcher
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.browser_launcher import BrowserLauncher  # noqa: E402
from tools import utils  # noqa: E402  复用项目 logger

CDP_PORT = 9222
# 与 config/base_config.py 的 USER_DATA_DIR 保持一致；core.py 用 os.getcwd() 拼，
# 故本脚本须在项目根运行，二者才会落到同一目录 browser_data/xhs_user_data_dir/
USER_DATA_DIR = os.path.join(os.getcwd(), "browser_data", "xhs_user_data_dir")


def find_chromium() -> str:
    """优先 playwright 装的 chromium（反检测更好、版本可控），fallback 系统 Chrome。"""
    candidates = glob.glob(os.path.expanduser(
        "~/Library/Caches/ms-playwright/chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium"))
    for p in sorted(candidates, reverse=True):  # 版本号最大的优先
        if os.path.isfile(p):
            return p
    sys_chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if os.path.isfile(sys_chrome):
        utils.logger.warning("[resident_browser] 未找到 playwright chromium，回退系统 Chrome")
        return sys_chrome
    raise FileNotFoundError(
        "找不到 Chromium/Chrome，先运行：.venv/bin/playwright install chromium")


def main():
    os.makedirs(USER_DATA_DIR, exist_ok=True)
    chromium_path = find_chromium()
    utils.logger.info(f"[resident_browser] chromium={chromium_path}")
    utils.logger.info(f"[resident_browser] user_data_dir={USER_DATA_DIR}")

    launcher = BrowserLauncher()
    proc = launcher.launch_browser(
        browser_path=chromium_path,
        debug_port=CDP_PORT,
        headless=False,
        user_data_dir=USER_DATA_DIR,
    )

    if not launcher.wait_for_browser_ready(CDP_PORT, timeout=30):
        utils.logger.error(f"[resident_browser] 浏览器未在 {CDP_PORT} 就绪")
        launcher.cleanup()
        sys.exit(1)

    utils.logger.info(f"[resident_browser] ✅ 就绪 PID={proc.pid} CDP={CDP_PORT}，常驻中…")

    def _shutdown(signum, _frame):
        utils.logger.info(f"[resident_browser] 收到信号 {signum}，关闭浏览器")
        launcher.cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # 常驻：等浏览器进程退出（被外部 kill 或窗口手动关闭），或收到信号
    try:
        while proc.poll() is None:
            time.sleep(1)
        utils.logger.warning(f"[resident_browser] 浏览器进程已退出（code={proc.returncode}）")
    except KeyboardInterrupt:
        _shutdown(signal.SIGINT, None)


if __name__ == "__main__":
    main()

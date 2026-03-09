"""
Google 账户管理器 - 基于 Camoufox + Storage State
工作流：首次手动登录 → 自动保存完整状态 → 下次直接加载（无需重新登录）
"""

import json
import time
import os
import requests
from pathlib import Path
from datetime import datetime

from camoufox.sync_api import Camoufox


ACCOUNTS_DIR = Path("accounts")
ACCOUNTS_DIR.mkdir(exist_ok=True)


# ──────────────────────────────────────────────────────────────
#  首次登录：手动操作，完成后自动保存
# ──────────────────────────────────────────────────────────────

def login_and_save(account_name: str):
    state_path = ACCOUNTS_DIR / f"{account_name}.json"

    print(f"[+] 启动浏览器，请手动登录 Google...")
    print(f"    账户名：{account_name}")
    print(f"    保存路径：{state_path}")
    print()

    with Camoufox(headless=False, window=(1000,900)) as browser:
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://accounts.google.com/signin")

        print("=" * 50)
        print("  请在浏览器中完成 Google 登录")
        print("  登录成功后，回到此终端按回车保存")
        print("=" * 50)
        input("\n  >>> 登录完成后按回车 <<<\n")

        context.storage_state(path=str(state_path))

        cookies = context.cookies()
        meta_path = ACCOUNTS_DIR / f"{account_name}_cookies_debug.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump({
                "_meta": {
                    "savedAt": datetime.now().isoformat(),
                    "account": account_name,
                    "cookieCount": len(cookies),
                },
                "cookies": cookies,
            }, f, indent=2, ensure_ascii=False)

        print(f"[✓] 已保存 {len(cookies)} 个 Cookie（含 HttpOnly）")
        print(f"[✓] Storage state → {state_path}")
        print(f"[✓] Cookie 调试文件 → {meta_path}")
        context.close()

    return state_path


# ──────────────────────────────────────────────────────────────
#  加载已保存的账户
# ──────────────────────────────────────────────────────────────

def load_account(
    account_name: str,
    target_url: str = "https://myaccount.google.com/",
    headless: bool = False,
    idle_seconds: int = None,
    on_page_ready=None,
):
    state_path = ACCOUNTS_DIR / f"{account_name}.json"

    if not state_path.exists():
        raise FileNotFoundError(
            f"找不到账户 {account_name!r} 的状态文件：{state_path}\n"
            f"请先运行登录流程：python {__file__} --login {account_name}"
        )

    print(f"[+] 加载账户：{account_name}")
    print(f"    状态文件：{state_path}")

    with Camoufox(headless=headless) as browser:
        context = browser.new_context(storage_state=str(state_path))
        page = context.new_page()
        page.goto(target_url)
        page.wait_for_load_state("domcontentloaded")

        print(f"[✓] 已导航至：{page.url}")

        if on_page_ready:
            on_page_ready(page, context)

        if idle_seconds is None:
            print("[*] 无限等待中，Ctrl+C 退出…")
            while True:
                time.sleep(60)
        else:
            print(f"[*] 等待 {idle_seconds}s 后关闭…")
            time.sleep(idle_seconds)

        context.close()


# ──────────────────────────────────────────────────────────────
#  批量加载所有账户
# ──────────────────────────────────────────────────────────────

def load_all_accounts(
    target_url: str = "https://myaccount.google.com/",
    headless: bool = True,
    on_page_ready=None,
):
    state_files = [
        p for p in ACCOUNTS_DIR.glob("*.json")
        if not p.name.endswith("_cookies_debug.json")
    ]

    if not state_files:
        print(f"[!] accounts/ 目录下没有账户，请先登录")
        return

    print(f"[+] 共找到 {len(state_files)} 个账户\n")

    for i, state_path in enumerate(sorted(state_files), 1):
        name = state_path.stem
        print(f"\n{'='*50}")
        print(f"[{i}/{len(state_files)}] 账户：{name}")
        try:
            load_account(
                name,
                target_url=target_url,
                headless=headless,
                idle_seconds=10,
                on_page_ready=on_page_ready,
            )
        except Exception as e:
            print(f"[!] 账户 {name} 加载失败：{e}")


# ──────────────────────────────────────────────────────────────
#  列出已保存的账户
# ──────────────────────────────────────────────────────────────

def list_accounts():
    state_files = [
        p for p in ACCOUNTS_DIR.glob("*.json")
        if not p.name.endswith("_cookies_debug.json")
    ]
    if not state_files:
        print("[*] 暂无已保存账户")
        return

    print(f"\n已保存的账户（共 {len(state_files)} 个）：")
    print("-" * 40)
    for p in sorted(state_files):
        size_kb = p.stat().st_size / 1024
        mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        print(f"  {p.stem:<20} {size_kb:>6.1f} KB   保存于 {mtime}")
    print()


# ──────────────────────────────────────────────────────────────
#  Flow 模式：提取 session token 并上报
# ──────────────────────────────────────────────────────────────

FLOW_URL = "https://labs.google/fx/tools/flow"
FLOW_COOKIE_NAME = "__Secure-next-auth.session-token"
FLOW_API_ENDPOINT = "https://example.com/api/plugin/update-token"

FLOW_BUTTON_SELECTORS = [
    "button.sc-16c4830a-1:nth-child(2)",
    "button.sc-16c4830a-1.hAosAa.sc-c0d0216b-0.kjNfNe.sc-6c518124-16.lawqve",
    "section#hero button.sc-16c4830a-1",
]


def _post_token(session_token: str, api_url: str, api_key: str) -> bool:
    """
    将 session token 上报到 Flow API。
    api_key 格式：username:password（例如 admin:yourpassword）
    流程：admin 登录 → 拿 connection_token → 上报 ST
    """
    try:
        base_url = api_url.split("/api/")[0]
        print(f"[DEBUG] base_url = {base_url}")

        # 1. admin 登录
        if ":" not in api_key:
            print(f"[!] --flow-api-key 格式错误，应为 username:password")
            return False
        username, password = api_key.split(":", 1)

        login_resp = requests.post(
            f"{base_url}/api/admin/login",
            json={"username": username, "password": password},
            timeout=15,
        )
        if not login_resp.ok:
            print(f"[!] Admin 登录失败：HTTP {login_resp.status_code} - {login_resp.text[:200]}")
            return False
        admin_token = login_resp.json()["token"]
        print(f"[✓] Admin 登录成功")

        # 2. 获取 connection_token
        plugin_resp = requests.get(
            f"{base_url}/api/plugin/config",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=15,
        )
        if not plugin_resp.ok:
            print(f"[!] 获取 plugin config 失败：HTTP {plugin_resp.status_code}")
            return False
        connection_token = plugin_resp.json().get("config", {}).get("connection_token")
        if not connection_token:
            print(f"[!] plugin config 中未找到 connection_token，响应：{plugin_resp.json()}")
            return False
        print(f"[✓] 获取 connection_token 成功")

        # 3. 上报 ST
        resp = requests.post(
            api_url,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {connection_token}",
            },
            json={"session_token": session_token},
            timeout=15,
        )
        if resp.ok:
            print(f"[✓] Token 上报成功：HTTP {resp.status_code}")
            try:
                print(f"    响应：{resp.json()}")
            except Exception:
                pass
            return True
        else:
            print(f"[!] Token 上报失败：HTTP {resp.status_code} - {resp.text[:200]}")
            return False

    except Exception as e:
        print(f"[!] 上报请求异常：{e}")
        return False


def run_flow(
    account_name: str,
    api_url: str,
    api_key: str,
    headless: bool = True,
):
    state_path = ACCOUNTS_DIR / f"{account_name}.json"
    if not state_path.exists():
        raise FileNotFoundError(
            f"找不到账户 {account_name!r}，请先运行 --login {account_name}"
        )

    print(f"[+] Flow 模式启动")
    print(f"    账户：{account_name}")
    print(f"    API：{api_url}")
    print()

    with Camoufox(headless=headless, window=(1280, 900)) as browser:
        context = browser.new_context(storage_state=str(state_path))
        page = context.new_page()

        print(f"[→] 导航至 {FLOW_URL}")
        page.goto(FLOW_URL)
        page.wait_for_load_state("domcontentloaded")

        # 等待并点击登录按钮
        print("[*] 等待登录按钮出现…")
        clicked = False
        for selector in FLOW_BUTTON_SELECTORS:
            try:
                page.wait_for_selector(selector, timeout=20_000)
                page.click(selector)
                print(f"[✓] 已点击按钮：{selector[:60]}")
                clicked = True
                break
            except Exception:
                continue

        if not clicked:
            print("[!] 未能找到登录按钮，继续等待 Cookie（可能已登录）…")

        # 轮询等待 session token cookie 出现
        print(f"[*] 等待 Cookie：{FLOW_COOKIE_NAME}")
        session_token = None
        for attempt in range(120):  # 最多等 2 分钟
            cookies = context.cookies()
            for c in cookies:
                if c["name"] == FLOW_COOKIE_NAME:
                    session_token = c["value"]
                    break
            if session_token:
                print(f"[✓] Cookie 已出现（等待了约 {attempt}s）")
                break
            time.sleep(1)

        if not session_token:
            print("[✗] 超时：2 分钟内未检测到 session token，退出。")
            context.close()
            return False

        success = _post_token(session_token, api_url, api_key)
        context.close()
        return success


# ──────────────────────────────────────────────────────────────
#  CLI 入口
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Google 账户管理器",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
示例：
  首次登录并保存：
    python main.py --login myaccount

  加载已保存账户：
    python main.py --load myaccount

  无头模式加载，打开 Gmail：
    python main.py --load myaccount --url https://mail.google.com --headless

  批量加载所有账户（无头）：
    python main.py --load-all --headless

  查看已保存账户：
    python main.py --list

  Flow 模式（提取并上报 session token）：
    python main.py --flow myaccount --flow-api-key "admin:yourpassword"
        """
    )

    parser.add_argument("--login", metavar="NAME",
                        help="首次登录并保存账户状态")
    parser.add_argument("--load", metavar="NAME",
                        help="加载已保存的账户")
    parser.add_argument("--load-all", action="store_true",
                        help="批量加载所有账户")
    parser.add_argument("--list", action="store_true",
                        help="列出所有已保存账户")
    parser.add_argument("--url", "-u", default="https://myaccount.google.com/",
                        help="目标 URL（默认: https://myaccount.google.com/）")
    parser.add_argument("--no-headless", action="store_true",
                        help="有头模式运行")
    parser.add_argument("--wait", "-w", type=int, default=None,
                        help="加载后等待 N 秒关闭（不填则无限等待）")

    # Flow 模式
    parser.add_argument("--flow", metavar="NAME",
                        help="Flow 模式：自动提取 session token 并上报")
    parser.add_argument("--flow-api", metavar="URL",
                        default=FLOW_API_ENDPOINT,
                        help=f"Flow API 地址（默认：{FLOW_API_ENDPOINT}）")
    parser.add_argument("--flow-api-key", metavar="USER:PASS",
                        help="Flow 管理员凭据，格式：username:password")

    args = parser.parse_args()

    if args.list:
        list_accounts()

    elif args.login:
        login_and_save(args.login)

    elif args.load:
        load_account(
            args.load,
            target_url=args.url,
            headless=args.headless,
            idle_seconds=args.wait,
        )

    elif args.load_all:
        load_all_accounts(
            target_url=args.url,
            headless=args.headless,
        )

    elif args.flow:
        missing = []
        if not args.flow_api:
            missing.append("--flow-api")
        if not args.flow_api_key:
            missing.append("--flow-api-key")
        if missing:
            parser.error(f"--flow 模式必须同时指定：{', '.join(missing)}")

        run_flow(
            account_name=args.flow,
            api_url=args.flow_api,
            api_key=args.flow_api_key,
            headless= not args.no_headless,
        )

    else:
        parser.print_help()
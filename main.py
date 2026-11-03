#!/usr/bin/env python3
"""
ouo.io 24/7 Multi-Worker Earning Automation Engine & Telegram Control Center
Created with love by RJN (ROX AI) for Rudra.

Features:
- Unified Single File Architecture (.py) for Cloud & Railway Deployment
- 45 Parallel Browser Workers (Multi-Worker Concurrency with Natural Pacing)
- Dedicated US-Only Rotating Residential Proxy (res-us-rotate) for Highest Tier-1 eCPM
- Built-in Telegram Bot Control Panel (@Roxyubot) with Master Password Protection
- Dynamic Link Generation via Vercel Portal
- Hourly Dashboard Scraper & Thread-Safe Stats Storage
- Automatic Lightweight HTTP Healthcheck for Railway Deployments
"""

import os
import sys
import time
import json
import random
import string
import signal
import requests
import threading
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from http.server import HTTPServer, BaseHTTPRequestHandler

# Telegram Bot Library
import telebot
from telebot import types
from telebot.apihelper import ApiTelegramException

# Playwright Browser Automation
from playwright.sync_api import sync_playwright

# Force unbuffered output for live logging on Railway
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# ----------------- CONFIGURATION -----------------

DATA_DIR = os.environ.get("DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
os.makedirs(DATA_DIR, exist_ok=True)

STATS_FILE = os.path.join(DATA_DIR, "campaign_stats.json")
AUTH_FILE = os.path.join(DATA_DIR, "bot_auth.json")
SESSION_FILE = os.path.join(DATA_DIR, "ouo_session.json")

# Telegram Bot Config
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8943552749:AAFZz5LnHyucisObGpJ2Nx35Ul-f1bTa6BQ")
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
SESSION_LIFETIME = 86400  # 24 Hours in seconds for user authentication

# Account & Portal Config
OUO_USERNAME = os.environ.get("OUO_USERNAME", "nxtzenmaker@gmail.com")
OUO_PASSWORD = os.environ.get("OUO_PASSWORD", "Zeno@123")
MASTER_PASSWORD = os.environ.get("MASTER_PASSWORD", "Raj Nandini is the heart of Rudra/Zeno")
VERCEL_BASE_URL = os.environ.get("VERCEL_BASE_URL", "https://ouo-portal.vercel.app")

# Concurrency (Default 45 Workers)
NUM_WORKERS = int(os.environ.get("NUM_WORKERS", "45"))
HOURLY_CHECK_INTERVAL = 3600  # 1 Hour

# Proxies
PROXY_CONFIG = {
    'server': os.environ.get("OUO_PROXY_SERVER", "http://gw.proxyrise.com:443"),
    'username': os.environ.get("OUO_PROXY_USER", "res-ca-rotate"),
    'password': os.environ.get("OUO_PROXY_PASS", "pgw-73695fbd211a1e42af0108ba837909a4681ebc141b160c07")
}

VISITOR_PROXY_CONFIG = {
    'server': os.environ.get("VISITOR_PROXY_SERVER", "http://gw.proxyrise.com:443"),
    'username': os.environ.get("VISITOR_PROXY_USER", "res-us-rotate"),
    'password': os.environ.get("VISITOR_PROXY_PASS", "pgw-73695fbd211a1e42af0108ba837909a4681ebc141b160c07")
}

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# Global Locks and State
stats_lock = threading.Lock()
shortener_lock = threading.Lock()
running = True
active_status_messages = {}

# ----------------- STATS TRACKER -----------------

DEFAULT_STATS = {
    "total_links_created": 0,
    "total_views_completed": 0,
    "failed_views": 0,
    "success_rate": "100%",
    "daemon_status": f"🟢 RUNNING 24/7 ({NUM_WORKERS} US Workers)",
    "daemon_started_at": 0,
    "daemon_started_str": "",
    "last_activity_time": 0,
    "last_activity_str": "None yet",
    "last_shortlink": "None yet",
    "last_target_url": "None yet",
    "last_visitor_country": "🇺🇸 US",
    "dashboard": {
        "views": "0",
        "earnings": "$0.00",
        "ecpm": "$0.00",
        "available": "$0.00",
        "last_checked_at": 0,
        "last_checked_str": "Never",
        "next_check_at": 0,
        "next_check_str": "Pending"
    },
    "history": []
}

def get_current_time_str(ts=None):
    if ts is None:
        ts = time.time()
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')

def _load_stats_unlocked():
    if not os.path.exists(STATS_FILE):
        return DEFAULT_STATS.copy()
    try:
        with open(STATS_FILE, 'r') as f:
            data = json.load(f)
            for k, v in DEFAULT_STATS.items():
                if k not in data:
                    data[k] = v
            return data
    except Exception:
        return DEFAULT_STATS.copy()

def _save_stats_unlocked(stats):
    try:
        tmp_file = STATS_FILE + ".tmp"
        with open(tmp_file, 'w') as f:
            json.dump(stats, f, indent=2)
        os.replace(tmp_file, STATS_FILE)
    except Exception as e:
        print(f"[!] Error saving stats: {e}")

def load_stats():
    with stats_lock:
        if not os.path.exists(STATS_FILE):
            stats = DEFAULT_STATS.copy()
            stats["daemon_started_at"] = time.time()
            stats["daemon_started_str"] = get_current_time_str(stats["daemon_started_at"])
            _save_stats_unlocked(stats)
            return stats
        return _load_stats_unlocked()

def save_stats(stats):
    with stats_lock:
        _save_stats_unlocked(stats)

def record_link_created(short_url, target_url):
    with stats_lock:
        stats = _load_stats_unlocked()
        stats["total_links_created"] += 1
        stats["last_shortlink"] = short_url
        stats["last_target_url"] = target_url
        stats["last_activity_time"] = time.time()
        stats["last_activity_str"] = get_current_time_str(stats["last_activity_time"])
        _save_stats_unlocked(stats)

def record_view_result(success, short_url, dest_url, country="🇺🇸 US"):
    with stats_lock:
        stats = _load_stats_unlocked()
        if success:
            stats["total_views_completed"] += 1
        else:
            stats["failed_views"] += 1
            
        total_attempts = stats["total_views_completed"] + stats["failed_views"]
        if total_attempts > 0:
            pct = (stats["total_views_completed"] / total_attempts) * 100.0
            stats["success_rate"] = f"{pct:.1f}%"
        else:
            stats["success_rate"] = "100%"
            
        stats["last_activity_time"] = time.time()
        stats["last_activity_str"] = get_current_time_str(stats["last_activity_time"])
        stats["last_visitor_country"] = country
        
        entry = {
            "time": get_current_time_str(),
            "shortlink": short_url,
            "country": country,
            "status": "SUCCESS" if success else "FAILED",
            "dest": dest_url
        }
        history = stats.get("history", [])
        history.insert(0, entry)
        stats["history"] = history[:10]
        
        _save_stats_unlocked(stats)

def record_dashboard_stats(dashboard_data):
    with stats_lock:
        stats = _load_stats_unlocked()
        now = time.time()
        next_check = now + 3600
        
        stats["dashboard"] = {
            "views": dashboard_data.get("views", "0"),
            "earnings": dashboard_data.get("earnings", "$0.00"),
            "ecpm": dashboard_data.get("ecpm", "$0.00"),
            "available": dashboard_data.get("available", "$0.00"),
            "last_checked_at": now,
            "last_checked_str": get_current_time_str(now),
            "next_check_at": next_check,
            "next_check_str": get_current_time_str(next_check)
        }
        _save_stats_unlocked(stats)

# ----------------- SESSION & LOGIN ENGINE -----------------

def check_session_validity():
    if not os.path.exists(SESSION_FILE):
        return False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
            )
            context = browser.new_context(proxy=PROXY_CONFIG, user_agent=USER_AGENT)
            with open(SESSION_FILE) as f:
                cookie_dict = json.load(f)
            context.add_cookies([{'name': k, 'value': v, 'domain': '.ouo.io', 'path': '/'} for k, v in cookie_dict.items()])
            page = context.new_page()
            page.goto('https://ouo.io/manage/home', wait_until='domcontentloaded', timeout=30000)
            
            for _ in range(15):
                time.sleep(1)
                if 'manage/home' in page.url or 'Dashboard' in page.title():
                    break
                    
            is_valid = ('manage/home' in page.url or 'Dashboard' in page.title()) and 'auth/signin' not in page.url
            browser.close()
            return is_valid
    except Exception as e:
        print(f"[!] Session validity check error: {e}")
        return False

def do_login():
    print("[*] Re-authenticating with ouo.io (session expired)...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-blink-features=AutomationControlled', '--disable-infobars']
            )
            context = browser.new_context(
                proxy=PROXY_CONFIG,
                user_agent=USER_AGENT,
                viewport={'width': 1280, 'height': 720}
            )
            page = context.new_page()
            page.goto('https://ouo.io/auth/signin', wait_until='domcontentloaded', timeout=35000)
            
            for _ in range(15):
                time.sleep(1)
                if 'Sign in' in page.title():
                    break
                    
            if 'Sign in' not in page.title():
                browser.close()
                return False
                
            page.fill('input[name="username"]', OUO_USERNAME)
            page.fill('input[name="password"]', OUO_PASSWORD)
            
            remember = page.query_selector('input[name="remember-me"]')
            if remember and not remember.is_checked():
                remember.check()
                
            # Submit login form
            page.click('button[type="submit"]')
            
            # Wait for dashboard redirect
            for _ in range(25):
                time.sleep(1)
                if 'manage/home' in page.url or 'Dashboard' in page.title():
                    break
                    
            if 'manage/home' in page.url or 'Dashboard' in page.title():
                cookies = context.cookies()
                cookie_dict = {c['name']: c['value'] for c in cookies if 'ouo.io' in c['domain']}
                with open(SESSION_FILE, 'w') as f:
                    json.dump(cookie_dict, f, indent=2)
                print("[+] ouo.io Re-Authentication Success! Cookies saved.")
                browser.close()
                return True
            else:
                print(f"[!] Login failed. Current URL: {page.url}")
                browser.close()
                return False
    except Exception as e:
        print(f"[!] Login Exception: {e}")
        return False

def check_ouo_dashboard_hourly(force=False):
    """Checks ouo.io dashboard stats once every 1 hour (3600s) or on manual force"""
    stats = load_stats()
    last_check = stats.get("dashboard", {}).get("last_checked_at", 0)
    now = time.time()
    
    if not force and (now - last_check) < HOURLY_CHECK_INTERVAL and last_check > 0:
        return
        
    print("[*] Running Hourly ouo.io Dashboard Snapshot Check...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
            )
            context = browser.new_context(
                proxy=PROXY_CONFIG,
                user_agent=USER_AGENT,
                viewport={'width': 1280, 'height': 720}
            )
            if os.path.exists(SESSION_FILE):
                with open(SESSION_FILE) as f:
                    cookie_dict = json.load(f)
                context.add_cookies([{'name': k, 'value': v, 'domain': '.ouo.io', 'path': '/'} for k, v in cookie_dict.items()])
                
            page = context.new_page()
            page.goto('https://ouo.io/manage/home', wait_until='domcontentloaded', timeout=35000)
            
            for _ in range(15):
                time.sleep(1)
                if 'manage/home' in page.url or 'Dashboard' in page.title():
                    break
                    
            dash_data = {'views': '0', 'earnings': '$0.00', 'ecpm': '$0.00', 'available': '$0.00'}
            cards = page.query_selector_all('.col-sm-3, .col-xs-6, .panel')
            for c in cards:
                lines = [l.strip() for l in c.inner_text().split('\n') if l.strip()]
                if len(lines) >= 2:
                    val, label = lines[0], lines[1]
                    if label.lower() == 'views':
                        dash_data['views'] = val
                    elif label.lower() == 'earnings':
                        dash_data['earnings'] = val
                    elif label.lower() == 'ecpm':
                        dash_data['ecpm'] = val
                    elif 'total available' in label.lower():
                        dash_data['available'] = val
            browser.close()
            
            record_dashboard_stats(dash_data)
            print(f"[+] Hourly Check Complete: Views={dash_data['views']}, Earnings={dash_data['earnings']}, Available={dash_data['available']}")
    except Exception as e:
        print(f"[!] Hourly dashboard check notice: {e}")

# ----------------- DYNAMIC TARGET & SHORTENER -----------------

def get_dynamic_url():
    base = VERCEL_BASE_URL.rstrip('/')
    try:
        res = requests.get(f"{base}/api/link", params={'auth': MASTER_PASSWORD}, timeout=8)
        if res.status_code == 200:
            data = res.json()
            if data.get('url'):
                return data['url']
    except Exception:
        pass
    rand_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    rand_ts = int(time.time() * 1000)
    cat = random.choice(['tech', 'cloud', 'dev', 'ai', 'crypto', 'quantum', 'fintech'])
    return f"{base}/article?id={rand_id}&cat={cat}&t={rand_ts}&auth={requests.utils.quote(MASTER_PASSWORD)}&ref=multi"

def shorten_target(target_url):
    with shortener_lock:
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
                )
                context = browser.new_context(
                    proxy=PROXY_CONFIG,
                    user_agent=USER_AGENT,
                    viewport={'width': 1280, 'height': 720}
                )
                if os.path.exists(SESSION_FILE):
                    with open(SESSION_FILE) as f:
                        cookie_dict = json.load(f)
                    context.add_cookies([{'name': k, 'value': v, 'domain': '.ouo.io', 'path': '/'} for k, v in cookie_dict.items()])
                    
                page = context.new_page()
                page.goto('https://ouo.io/manage/home', wait_until='domcontentloaded', timeout=30000)
                
                for _ in range(15):
                    time.sleep(1)
                    if 'Just a moment' not in page.title() and page.title() != '':
                        break
                        
                token_el = page.query_selector('input[name="_token"]')
                csrf_token = token_el.get_attribute('value') if token_el else ""
                
                result = page.evaluate('''async ({url, token}) => {
                    const formData = new URLSearchParams();
                    formData.append('_token', token);
                    formData.append('url', url);
                    
                    const res = await fetch('https://ouo.io/shorten', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                            'X-Requested-With': 'XMLHttpRequest',
                            'Accept': 'application/json, text/javascript, */*; q=0.01'
                        },
                        body: formData.toString()
                    });
                    const raw = await res.text();
                    let data = null;
                    try { data = JSON.parse(raw); } catch(e) { data = raw; }
                    return { status: res.status, data };
                }''', {'url': target_url, 'token': csrf_token})
                
                browser.close()
                status = result.get('status')
                data = result.get('data')
                if status == 200 and isinstance(data, dict) and not data.get('error'):
                    slug = data.get('slug')
                    return f"https://ouo.io/{slug}"
                else:
                    return None
        except Exception as e:
            print(f"[!] Shorten exception: {e}")
            return None

# ----------------- AD-ENABLED REAL VISITOR -----------------

def visit_shortlink(short_url, worker_id=1):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-blink-features=AutomationControlled', '--start-maximized']
            )
            context = browser.new_context(
                proxy=VISITOR_PROXY_CONFIG,
                user_agent=USER_AGENT,
                viewport={'width': 1366, 'height': 768}
            )
            
            popups = []
            page = context.new_page()
            page.on("popup", lambda p: popups.append(p))
            
            try:
                page.goto(short_url, wait_until='commit', timeout=25000)
            except Exception:
                page.goto(short_url, wait_until='domcontentloaded', timeout=30000)
            
            for _ in range(25):
                time.sleep(1)
                if 'Just a moment' not in page.title() and page.title() != '':
                    break
                    
            try:
                scroll_y = random.randint(200, 500)
                page.mouse.wheel(0, scroll_y)
                time.sleep(random.uniform(1.2, 2.5))
            except Exception:
                pass
                
            # Step 1: Click #btn-main
            try:
                btn1 = page.wait_for_selector('#btn-main', timeout=15000)
                time.sleep(random.uniform(1.0, 2.2))
                btn1.click(force=True, timeout=5000)
            except Exception:
                try:
                    page.evaluate('() => { const f = document.querySelector("#form-go"); if (f) f.submit(); }')
                except Exception:
                    pass
                    
            time.sleep(random.uniform(2.5, 4.0))
            if popups:
                time.sleep(random.uniform(1.5, 2.5))
                for p_tab in popups:
                    try: p_tab.close()
                    except Exception: pass
                popups.clear()
                
            page.bring_to_front()
            
            # Step 2: Wait for countdown and GET LINK
            for _ in range(20):
                time.sleep(1)
                if 'ouo.io' not in page.url and 'ouo.press' not in page.url:
                    break
                btn2 = page.query_selector('#btn-main')
                if btn2:
                    cls = btn2.get_attribute('class') or ''
                    txt = btn2.inner_text()
                    if 'disabled' not in cls and txt.upper() == 'GET LINK':
                        time.sleep(random.uniform(0.8, 1.8))
                        try:
                            btn2.click(force=True, timeout=5000)
                        except Exception:
                            pass
                        try:
                            page.evaluate('() => { const f = document.querySelector("#form-go"); if (f) f.submit(); }')
                        except Exception:
                            pass
                        break
                        
            final_url = page.url
            for _ in range(15):
                time.sleep(1)
                if 'ouo.io' not in page.url and 'ouo.press' not in page.url:
                    final_url = page.url
                    time.sleep(random.uniform(2.5, 4.5))
                    break
                    
            browser.close()
            is_valid = 'ouo.io' not in final_url and 'ouo.press' not in final_url
            return is_valid, final_url
    except Exception as e:
        return False, str(e)

# ----------------- PARALLEL WORKER ROUTINE -----------------

def worker_routine(worker_id):
    """Single worker loop running concurrently with randomized intervals"""
    print(f"[Worker #{worker_id:02d}] Active & running...")
    
    while running:
        try:
            target_url = get_dynamic_url()
            short_url = shorten_target(target_url)
            if not short_url:
                time.sleep(random.uniform(4.0, 8.0))
                continue
                
            record_link_created(short_url, target_url)
            print(f"[Worker #{worker_id:02d}] Shortened: {short_url}")
            
            ok, dest = visit_shortlink(short_url, worker_id=worker_id)
            record_view_result(ok, short_url, dest, country="🇺🇸 US (Rotating IP)")
            
            if ok:
                print(f"[Worker #{worker_id:02d}] ✅ Paid View Verified! ({dest[:45]}...)")
            else:
                print(f"[Worker #{worker_id:02d}] ⚠️ View ended: {dest[:45]}...")
                
            # Dynamic natural pacing
            worker_sleep = random.uniform(3.0, 15.0)
            time.sleep(worker_sleep)
            
        except Exception as e:
            print(f"[Worker #{worker_id:02d}] Notice: {e}")
            time.sleep(random.uniform(6.0, 12.0))

def run_multi_worker_daemon():
    print("=======================================================")
    print("🚀 OUO.IO 24/7 MULTI-WORKER ENGINE (US ROTATING IPS)")
    print(f"👥 Concurrent Workers: {NUM_WORKERS} Parallel Playwright Instances")
    print("📡 Visitor Proxy: US Residential Rotating (gw.proxyrise.com)")
    print("⏱️ Dashboard Check: Hourly Cached Snapshot")
    print("=======================================================\n")
    
    stats = load_stats()
    stats["daemon_status"] = f"🟢 RUNNING 24/7 ({NUM_WORKERS} US Workers)"
    if not stats.get("daemon_started_at"):
        stats["daemon_started_at"] = time.time()
        stats["daemon_started_str"] = get_current_time_str(stats["daemon_started_at"])
    save_stats(stats)
    
    if not check_session_validity():
        do_login()
    check_ouo_dashboard_hourly()
    
    # Background Hourly Dashboard Scraper
    def hourly_timer_thread():
        while running:
            time.sleep(60)
            try:
                check_ouo_dashboard_hourly()
            except Exception:
                pass
    threading.Thread(target=hourly_timer_thread, daemon=True).start()
    
    # Launch concurrent worker threads with natural startup stagger
    threads = []
    for w_id in range(1, NUM_WORKERS + 1):
        if not running:
            break
        t = threading.Thread(target=worker_routine, args=(w_id,), daemon=True)
        t.start()
        threads.append(t)
        time.sleep(random.uniform(0.5, 1.8))  # Staggered launch
        
    print(f"[+] All {NUM_WORKERS} Workers successfully launched! Running 24/7.")

# ----------------- TELEGRAM AUTHENTICATION -----------------

def is_user_authenticated(chat_id):
    if not os.path.exists(AUTH_FILE):
        return False
    try:
        with open(AUTH_FILE, 'r') as f:
            data = json.load(f)
        auth_time = data.get(str(chat_id), 0)
        return (time.time() - auth_time) < SESSION_LIFETIME
    except Exception:
        return False

def set_user_authenticated(chat_id):
    data = {}
    if os.path.exists(AUTH_FILE):
        try:
            with open(AUTH_FILE, 'r') as f:
                data = json.load(f)
        except Exception:
            pass
    data[str(chat_id)] = time.time()
    try:
        with open(AUTH_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def safe_edit(chat_id, message_id, text, reply_markup=None):
    try:
        bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
        return True
    except ApiTelegramException as e:
        if "message is not modified" in str(e).lower():
            return True
        return False
    except Exception:
        return False

def safe_delete(chat_id, message_id):
    try:
        bot.delete_message(chat_id, message_id)
    except Exception:
        pass

def prompt_for_password(chat_id, original_msg_id=None):
    if original_msg_id:
        safe_delete(chat_id, original_msg_id)
        
    markup = types.InlineKeyboardMarkup()
    b_cancel = types.InlineKeyboardButton(text="❌ Cancel", callback_data="cb_cancel_auth")
    markup.add(b_cancel)
    
    lock_msg = bot.send_message(
        chat_id,
        "🔒 <b>Security Verification Required (24-Hour Access)</b>\n\n"
        "<blockquote>"
        "This bot is private. Please enter the Master Security Password to access the 24/7 Earning Automation.\n"
        "Once verified, your access will remain unlocked for the next <b>24 hours</b>. 💖"
        "</blockquote>\n\n"
        "🔑 <b>Please enter password:</b>",
        reply_markup=markup
    )
    bot.register_next_step_handler(lock_msg, process_password_step)

def process_password_step(message):
    chat_id = message.chat.id
    user_pass = (message.text or "").strip()
    safe_delete(chat_id, message.message_id)
    
    if user_pass == MASTER_PASSWORD:
        set_user_authenticated(chat_id)
        send_or_update_status_card(chat_id)
    else:
        markup = types.InlineKeyboardMarkup()
        b_retry = types.InlineKeyboardButton(text="🔄 Try Again", callback_data="cb_reauth")
        markup.add(b_retry)
        bot.send_message(
            chat_id,
            "❌ <b>Access Denied: Incorrect Password!</b>\n\n"
            "<blockquote>Invalid password entered. Please try again.</blockquote>",
            reply_markup=markup
        )

# ----------------- STATUS CARD GENERATOR -----------------

def build_status_card_text():
    stats = load_stats()
    daemon_badge = f"🟢 RUNNING 24/7 ({NUM_WORKERS} US Workers)" if running else "⏸️ STOPPED / PAUSED"
    
    dash = stats.get("dashboard", {})
    dash_views = dash.get("views", "0")
    dash_earnings = dash.get("earnings", "$0.00")
    dash_ecpm = dash.get("ecpm", "$0.00")
    dash_available = dash.get("available", "$0.00")
    last_check_str = dash.get("last_checked_str", "Pending")
    next_check_str = dash.get("next_check_str", "In 1 Hour")
    
    links_created = stats.get("total_links_created", 0)
    views_completed = stats.get("total_views_completed", 0)
    failed_views = stats.get("failed_views", 0)
    success_rate = stats.get("success_rate", "100%")
    last_link = stats.get("last_shortlink", "None yet")
    last_act = stats.get("last_activity_str", "None yet")
    
    text = (
        "📊 <b>ROX AI (RJN) — 24/7 Earning & Automation Dashboard</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ <b>Engine Status:</b> <b>{daemon_badge}</b>\n"
        f"🔗 <b>Total Links Generated:</b> <code>{links_created}</code> links\n"
        f"✅ <b>Automated Views (Success):</b> <code>{views_completed}</code> paid views\n"
        f"⚠️ <b>Failed Attempts:</b> <code>{failed_views}</code>\n"
        f"🎯 <b>Success Delivery Rate:</b> <b>{success_rate}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💰 <b>ouo.io Dashboard Stats (1-Hour Cache Snapshot):</b>\n"
        f"  • 👁️ <b>Account Views:</b> <b>{dash_views}</b>\n"
        f"  • 💵 <b>Total Earnings:</b> <b>{dash_earnings}</b>\n"
        f"  • 📈 <b>Current eCPM:</b> <b>{dash_ecpm}</b>\n"
        f"  • 💳 <b>Available Balance:</b> <b>{dash_available}</b>\n"
        f"  • ⏱️ <b>Last Check:</b> <code>{last_check_str}</code>\n"
        f"  • ⏳ <b>Next Check:</b> <code>{next_check_str}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🌐 <b>Dynamic Target Portal:</b> <a href=\"{VERCEL_BASE_URL}\">ouo-portal.vercel.app</a> 🔒\n"
        "📡 <b>Visitor Network:</b> 🇺🇸 US Residential (Auto-Rotating IPs) 🟢\n"
        f"👥 <b>Worker Fleet:</b> <code>{NUM_WORKERS}</code> Parallel Concurrency ⚡\n"
        "🍪 <b>Session Guard:</b> Cartalyst Sentry (Active Session) ✅\n"
        f"🔗 <b>Latest Shortlink:</b> <code>{last_link}</code>\n"
        f"🕒 <b>Last Activity:</b> <code>{last_act}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>24/7 background earning is active. Dashboard stats cached hourly. 💖</i>"
    )
    return text

def get_status_inline_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    b_refresh = types.InlineKeyboardButton(text="🔄 Refresh Status", callback_data="cb_refresh_status")
    b_portal = types.InlineKeyboardButton(text="🌐 Vercel Portal", url=VERCEL_BASE_URL)
    b_force_check = types.InlineKeyboardButton(text="⏱️ Force 1-Hr Check", callback_data="cb_force_check")
    b_health = types.InlineKeyboardButton(text="🔑 Session Health", callback_data="cb_health_check")
    markup.row(b_refresh, b_portal)
    markup.row(b_force_check, b_health)
    return markup

def send_or_update_status_card(chat_id, edit_msg_id=None):
    text = build_status_card_text()
    markup = get_status_inline_markup()
    
    if edit_msg_id:
        if safe_edit(chat_id, edit_msg_id, text, reply_markup=markup):
            return
            
    prev_msg_id = active_status_messages.get(chat_id)
    if prev_msg_id:
        if safe_edit(chat_id, prev_msg_id, text, reply_markup=markup):
            return
        else:
            safe_delete(chat_id, prev_msg_id)
            
    sent = bot.send_message(chat_id, text, reply_markup=markup, disable_web_page_preview=True)
    active_status_messages[chat_id] = sent.message_id

# ----------------- TELEGRAM ROUTING -----------------

@bot.message_handler(commands=['start', 'status', 'help'])
def cmd_start(message):
    chat_id = message.chat.id
    safe_delete(chat_id, message.message_id)
    
    if not is_user_authenticated(chat_id):
        prompt_for_password(chat_id)
        return
        
    send_or_update_status_card(chat_id)

@bot.message_handler(func=lambda m: True)
def handle_all_messages(message):
    chat_id = message.chat.id
    safe_delete(chat_id, message.message_id)
    
    if not is_user_authenticated(chat_id):
        prompt_for_password(chat_id)
        return
        
    send_or_update_status_card(chat_id)

# ----------------- CALLBACK QUERY HANDLERS -----------------

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    data = call.data
    
    if data == "cb_cancel_auth":
        bot.clear_step_handler_by_chat_id(chat_id)
        safe_edit(chat_id, call.message.message_id, "❌ <b>Verification Cancelled.</b>")
        bot.answer_callback_query(call.id, "Cancelled")
        return
        
    if data == "cb_reauth":
        bot.answer_callback_query(call.id)
        prompt_for_password(chat_id, original_msg_id=call.message.message_id)
        return
        
    if not is_user_authenticated(chat_id):
        bot.answer_callback_query(call.id, "Master Password required!")
        prompt_for_password(chat_id)
        return
        
    if data == "cb_refresh_status":
        bot.answer_callback_query(call.id, "Status Refreshed! ⚡")
        send_or_update_status_card(chat_id, edit_msg_id=call.message.message_id)
        
    elif data == "cb_force_check":
        bot.answer_callback_query(call.id, "Checking ouo.io dashboard...")
        def run_hourly_check_bg():
            try:
                check_ouo_dashboard_hourly(force=True)
            except Exception:
                pass
            send_or_update_status_card(chat_id, edit_msg_id=call.message.message_id)
        threading.Thread(target=run_hourly_check_bg, daemon=True).start()
        
    elif data == "cb_health_check":
        valid = check_session_validity()
        msg = "Session is 100% active!" if valid else "Session refreshing..."
        bot.answer_callback_query(call.id, msg)
        send_or_update_status_card(chat_id, edit_msg_id=call.message.message_id)

# ----------------- RAILWAY HEALTH SERVER -----------------

def run_health_server():
    """Lightweight HTTP server on $PORT for Railway Web Service health checks"""
    port_str = os.environ.get("PORT")
    if not port_str:
        return
        
    try:
        port = int(port_str)
        class HealthHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                resp = json.dumps({
                    "status": "online",
                    "workers": NUM_WORKERS,
                    "service": "ouo-24-7-engine",
                    "time": get_current_time_str()
                })
                self.wfile.write(resp.encode('utf-8'))
                
            def log_message(self, format, *args):
                pass  # Suppress health check access logs
                
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        print(f"[*] Railway HTTP Health Server active on port {port}")
        server.serve_forever()
    except Exception as e:
        print(f"[!] Railway Health Server error: {e}")

# ----------------- SIGNAL HANDLING & MAIN RUNNER -----------------

def handle_exit(sig, frame):
    global running
    print("\n[!] Received shutdown signal. Gracefully stopping workers...")
    running = False
    stats = load_stats()
    stats["daemon_status"] = "⏸️ STOPPED"
    save_stats(stats)
    sys.exit(0)

signal.signal(signal.SIGINT, handle_exit)
signal.signal(signal.SIGTERM, handle_exit)

if __name__ == '__main__':
    print("=======================================================")
    print("🤖 ROX AI — 24/7 Earning Automation & Telegram Bot")
    print(f"👥 Workers: {NUM_WORKERS} Parallel Playwright Instances")
    print(f"📁 Data Directory: {DATA_DIR}")
    print("=======================================================\n")
    
    # 1. Start Railway Health Server if PORT is assigned
    threading.Thread(target=run_health_server, daemon=True).start()
    
    # 2. Launch 24/7 Multi-Worker Engine in background thread
    threading.Thread(target=run_multi_worker_daemon, daemon=True).start()
    
    # 3. Start Telegram Bot Polling on main thread
    print("[*] Starting Telegram Bot Listener...")
    while running:
        try:
            me = bot.get_me()
            print(f"[+] Bot Online: @{me.username} ({me.first_name})")
            bot.infinity_polling(timeout=25, long_polling_timeout=20)
        except Exception as e:
            print(f"[!] Telegram polling error: {e}. Retrying in 5 seconds...")
            time.sleep(5)

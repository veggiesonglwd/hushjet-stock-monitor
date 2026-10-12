#!/usr/bin/env python3
"""Dyson HushJet (HJ10) stock monitor for Singapore retailers.

Checks each product page, classifies it as IN_STOCK / PREORDER / OUT_OF_STOCK /
UNKNOWN, and sends a Telegram message when a page becomes available
(IN_STOCK or PREORDER). State is kept in state.json so you are only pinged
on a change, not every 5 minutes.

Env vars: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

PRODUCTS = [
    ("Harvey Norman", "White/Silver",
     "https://www.harveynorman.com.sg/air-and-water-treatment-en/air-conditioning-en/air-purifiers/dyson-sp01-hushjet-air-purifier-white-silver-en.html"),
    ("Harvey Norman", "Black/Teal",
     "https://www.harveynorman.com.sg/air-and-water-treatment-en/air-conditioning-en/air-purifiers/dyson-sp01-hushjet-air-purifier-black-teal.html"),
    ("Best Denki", "Black/Teal",
     "https://www.bestdenki.com.sg/1503579-dyson-air-cleaner-hj10-bk-teal-hushjet-297826-01.html"),
    ("Gain City", "White/Silver",
     "https://www.gaincity.com/dyson-hushjet-air-purifier-hj01-white-silver-297842-01-tb0012062"),
    ("Gain City", "Black/Teal",
     "https://www.gaincity.com/dyson-hushjet-air-purifier-hj01-black-teal-297826-01-tb0012063"),
    ("Dyson 官网", "White/Silver",
     "https://www.dyson.com.sg/hushjet-purifier-compact-white-silver"),
    ("Dyson 官网", "Black/Teal",
     "https://www.dyson.com.sg/hushjet-purifier-compact-black-teal"),
    ("FairPrice", "White/Silver",
     "https://www.fairprice.com.sg/product/dyson-hushjettm-purifier-compact-whitesilver"),
    ("FairPrice", "Black/Teal",
     "https://www.fairprice.com.sg/product/dyson-hushjettm-purifier-compact-blackteal"),
]

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
SGT = timezone(timedelta(hours=8))
AVAILABLE = {"IN_STOCK", "PREORDER"}
LABELS = {
    "IN_STOCK": "✅ 有货",
    "PREORDER": "🟡 可预订",
    "OUT_OF_STOCK": "❌ 缺货",
    "UNKNOWN": "❔ 无法判断",
}

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-SG,en;q=0.9",
}


def fetch(url):
    last_err = None
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 200:
                return r.text, None
            last_err = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            last_err = type(e).__name__
        time.sleep(3 * (attempt + 1))
    return None, last_err


def jsonld_availability(html):
    """Return schema.org availability from JSON-LD, if any."""
    for m in re.finditer(r'"availability"\s*:\s*"([^"]+)"', html, re.I):
        v = m.group(1).lower()
        if "preorder" in v or "presale" in v:
            return "PREORDER"
        if "instock" in v or "limitedavailability" in v or "onlineonly" in v:
            return "IN_STOCK"
        if "outofstock" in v or "soldout" in v or "discontinued" in v:
            return "OUT_OF_STOCK"
    return None


def visible_text(html):
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).lower()


PREORDER_BANNER = re.compile(r"pre-?order online|pre-?order now", re.I)


def classify_harveynorman(html):
    # The "PRE-ORDER ONLINE" banner and climate-voucher button show even when
    # nothing can be ordered. The only reliable signal is the real add-to-cart
    # submit button (name="dispatch[checkout.add..<id>]"), which is absent
    # while the page shows the out-of-stock block.
    if "dispatch[checkout.add" in html:
        return "PREORDER" if PREORDER_BANNER.search(visible_text(html)) else "IN_STOCK"
    return "OUT_OF_STOCK"


def classify_dyson(html):
    # Out of stock pages show "Currently out of stock" + "Notify Me".
    if "Currently out of stock" in html or "Notify Me" in html:
        return "OUT_OF_STOCK"
    if re.search(r"toCart|add to (cart|basket)", html, re.I):
        return "IN_STOCK"
    return "UNKNOWN"


def classify_fairprice(html):
    if "Out of stock online" in html:
        return "OUT_OF_STOCK"
    return jsonld_availability(html) or "UNKNOWN"


def classify(html, url=""):
    if "harveynorman.com.sg" in url:
        return classify_harveynorman(html)
    if "dyson.com.sg" in url:
        return classify_dyson(html)
    if "fairprice.com.sg" in url:
        return classify_fairprice(html)
    text = visible_text(html)
    # Pre-order banners take priority: Harvey Norman shows "Pre-Order" and
    # "OUT OF STOCK" on the same page while pre-orders are open.
    if re.search(r"pre-?order online|pre-?order now|\bpre-?order\b.{0,40}eta", text):
        return "PREORDER"
    ld = jsonld_availability(html)
    if ld:
        return ld
    if re.search(r"out of stock|sold out|currently unavailable", text):
        return "OUT_OF_STOCK"
    if re.search(r"\bpre-?order\b", text):
        return "PREORDER"
    if re.search(r"add to (cart|bag|basket)|\bin stock\b|buy now", text):
        return "IN_STOCK"
    return "UNKNOWN"


def price(html):
    m = re.search(r'"price"\s*:\s*"?([\d.,]+)', html)
    if m:
        try:
            return f"S${float(m.group(1).replace(',', '')):,.0f}"
        except ValueError:
            pass
    m = re.search(r"S?\$\s?([1-9]\d{2}(?:\.\d{2})?)", visible_text(html))
    return f"S${m.group(1)}" if m else ""


def send_telegram(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("Telegram secrets missing; message would be:\n" + text)
        return
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat, "text": text, "disable_web_page_preview": True},
        timeout=30,
    )
    if r.status_code != 200:
        print(f"Telegram error {r.status_code}: {r.text[:200]}", file=sys.stderr)
        sys.exit(1)


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def main():
    previous = load_state()
    current, results = {}, []
    for store, colour, url in PRODUCTS:
        html, err = fetch(url)
        status = classify(html, url) if html else "UNKNOWN"
        p = price(html) if html else ""
        current[url] = status
        results.append((store, colour, url, status, p, err))
        print(f"{store:14} {colour:13} {status:13} {p:8} {err or ''}")

    now = datetime.now(SGT).strftime("%Y-%m-%d %H:%M")

    def line(r):
        store, colour, url, status, p, err = r
        extra = f" ({err})" if err else ""
        return f"{LABELS[status]} {store} {colour} {p}{extra}\n{url}"

    if previous is None or any(url not in previous for _, _, url in PRODUCTS):
        # First run, or the product list changed: send a full summary so you
        # can confirm every page is being read correctly.
        title = "已启动" if previous is None else "已更新监控列表"
        msg = f"🔔 HushJet 库存监控{title}（{now} SGT）\n每 5 分钟检查一次，有货/可预订时通知你。\n\n"
        msg += "\n\n".join(line(r) for r in results)
        send_telegram(msg)
    else:
        newly = [r for r in results
                 if r[3] in AVAILABLE and previous.get(r[2]) != r[3]]
        if newly:
            msg = f"🚨 Dyson HushJet 有货了！（{now} SGT）\n\n"
            msg += "\n\n".join(line(r) for r in newly)
            msg += ("\n\n提醒：Harvey Norman 网上下单可以直接用气候券"
                    "（商品页的 Apply Climate Voucher）。"
                    "其他商家能否网上用气候券，以结账页面为准。")
            send_telegram(msg)

    with open(STATE_FILE, "w") as f:
        json.dump(current, f, indent=2)


if __name__ == "__main__":
    main()

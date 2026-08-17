import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from playwright.sync_api import sync_playwright

BASE_URL = "https://shop.kitamura.jp"
LIST_URL = "https://shop.kitamura.jp/ec/list?query=4549292216165&has_used=0"
PRODUCT_NAME = "キヤノン RF100-300mm F2.8 L IS USM"
DB_PATH = Path("database.json")


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def load_database():
    if not DB_PATH.exists():
        return {"initialized": False, "seen": {}}
    return json.loads(DB_PATH.read_text(encoding="utf-8"))


def save_database(database):
    DB_PATH.write_text(json.dumps(database, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def extract_labeled_text(text: str, labels):
    for label in labels:
        match = re.search(rf"{label}\s*[:：]?\s*([^\n]+)", text, re.IGNORECASE)
        if match:
            return clean(match.group(1))
    return "記載なし"


def listing_from_card(card):
    text = clean(card.inner_text())
    link = card.locator("a[href*='/ec/']").first
    href = link.get_attribute("href") if link.count() else None
    if not href:
        return None
    url = urljoin(BASE_URL, href)
    if "中古" not in text and "A品" not in text and "B品" not in text and "C品" not in text:
        return None

    # A URL normally contains the store's individual used-item identifier.  If a
    # page layout omits it, the stable visible fields are used as a fallback.
    explicit_id = re.search(r"(?:used|chuko|item)[_=/:-]*([A-Za-z0-9-]{5,})", url, re.I)
    price = extract_labeled_text(text, [r"価格", r"税込", r"¥"])
    if price == "記載なし":
        amount = re.search(r"[¥￥]\s*[0-9,]+|[0-9][0-9,]+\s*円", text)
        price = amount.group(0) if amount else "記載なし"
    condition = extract_labeled_text(text, [r"状態", r"ランク"])
    if condition == "記載なし":
        rank = re.search(r"[ABC]品", text)
        condition = rank.group(0) if rank else "記載なし"
    accessories = extract_labeled_text(text, [r"付属品", r"付属"])
    remarks = extract_labeled_text(text, [r"備考", r"コメント", r"商品説明"])
    fingerprint_source = "|".join([url, price, condition, accessories, remarks])
    listing_id = explicit_id.group(1) if explicit_id else hashlib.sha256(fingerprint_source.encode()).hexdigest()[:24]
    return {
        "id": listing_id,
        "url": url,
        "title": PRODUCT_NAME,
        "price": price,
        "condition": condition,
        "accessories": accessories,
        "remarks": remarks,
    }


def fetch_listings():
    listings = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(locale="ja-JP")
        page.goto(LIST_URL, wait_until="networkidle", timeout=90000)

        # Cards vary by Kitamura's layout.  Work from the closest container around
        # each product link, then eliminate cards that do not show used-item data.
        links = page.locator("a[href*='/ec/']")
        seen_urls = set()
        for index in range(links.count()):
            anchor = links.nth(index)
            href = anchor.get_attribute("href") or ""
            if href in seen_urls:
                continue
            seen_urls.add(href)
            card = anchor.locator("xpath=ancestor::*[self::article or self::li or self::div][.//text()[contains(., '中古')]][1]")
            if not card.count():
                continue
            item = listing_from_card(card.first)
            if item:
                listings.append(item)
        browser.close()
    return {item["id"]: item for item in listings}.values()


def send_discord(listing):
    webhook = os.environ["DISCORD_WEBHOOK_URL"]
    fields = [
        {"name": "価格", "value": listing["price"], "inline": True},
        {"name": "状態", "value": listing["condition"], "inline": True},
        {"name": "付属品", "value": listing["accessories"][:1024], "inline": False},
        {"name": "備考", "value": listing["remarks"][:1024], "inline": False},
    ]
    payload = {"embeds": [{"title": "中古在庫を検出しました", "description": listing["title"], "url": listing["url"], "color": 0xE53935, "fields": fields, "footer": {"text": "カメラのキタムラ オンラインショップ"}}]}
    response = requests.post(webhook, json=payload, timeout=30)
    response.raise_for_status()


def main():
    database = load_database()
    current = list(fetch_listings())
    current_by_id = {item["id"]: item for item in current}

    if not database.get("initialized", False):
        database["initialized"] = True
        database["seen"] = current_by_id
        save_database(database)
        print(f"初回登録: {len(current_by_id)}件（通知なし）")
        return

    new_items = [item for item_id, item in current_by_id.items() if item_id not in database.get("seen", {})]
    for item in new_items:
        send_discord(item)
        print(f"通知: {item['id']}")

    database["seen"] = {**database.get("seen", {}), **current_by_id}
    database["last_checked_at"] = datetime.now(timezone.utc).isoformat()
    save_database(database)
    print(f"確認完了: {len(current_by_id)}件 / 新規 {len(new_items)}件")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"監視失敗: {error}", file=sys.stderr)
        raise

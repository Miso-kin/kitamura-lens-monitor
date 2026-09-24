import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

PRODUCT_NAME = "キヤノン RF100-300mm F2.8 L IS USM"
JAN_CODE = "4549292216165"
USED_API_URL = "https://shop.kitamura.jp/ec/api/cache/vvc/u/v1/list"
DB_PATH = Path("database.json")


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def load_database():
    if not DB_PATH.exists():
        return {"initialized": False, "seen": {}}
    return json.loads(DB_PATH.read_text(encoding="utf-8"))


def save_database(database):
    DB_PATH.write_text(
        json.dumps(database, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def format_price(value):
    try:
        return f"{int(str(value)):,.0f}円（税込）"
    except (TypeError, ValueError):
        return clean(value) or "記載なし"


def extract_accessories(description):
    # キタムラの中古検索APIでは、付属品は商品説明の冒頭に記載される。
    first_sentence = clean(description).split("。", 1)[0]
    if "付" in first_sentence:
        return first_sentence
    return "商品説明に記載なし"


def listing_from_api_item(item):
    item_id = clean(item.get("itemid"))
    if not item_id:
        raise RuntimeError("中古検索APIの在庫データに商品IDがありません")

    description = clean(item.get("description"))
    return {
        "id": item_id,
        "url": clean(item.get("title_link"))
        or f"https://shop.kitamura.jp/ec/list?keyword3={JAN_CODE}&type=u",
        "title": clean(item.get("title")) or PRODUCT_NAME,
        "price": format_price(item.get("price")),
        # 現行APIにはランク専用フィールドがないため、存在しない情報を
        # 推測せず明示する。商品説明には外観・傷などが含まれる。
        "condition": clean(item.get("condition") or item.get("rank"))
        or "商品説明に記載なし",
        "accessories": extract_accessories(description),
        "remarks": description or "記載なし",
    }


def fetch_listings():
    params = {
        "keyword3": JAN_CODE,
        "sort": "newer",
        "ipg": 100,
        "page": 1,
    }
    response = requests.get(
        USED_API_URL,
        params=params,
        timeout=30,
        headers={"User-Agent": "kitamura-lens-monitor/2.0"},
    )
    response.raise_for_status()

    try:
        payload = response.json()
    except ValueError as error:
        raise RuntimeError("中古検索APIがJSONを返しませんでした") from error

    items = payload.get("items")
    if not isinstance(items, list):
        raise RuntimeError("中古検索APIの応答形式が想定外です")

    return {listing["id"]: listing for listing in map(listing_from_api_item, items)}.values()


def send_discord(listing):
    webhook = os.environ["DISCORD_WEBHOOK_URL"]
    fields = [
        {"name": "価格", "value": listing["price"], "inline": True},
        {"name": "状態", "value": listing["condition"][:1024], "inline": True},
        {"name": "付属品", "value": listing["accessories"][:1024], "inline": False},
        {"name": "備考", "value": listing["remarks"][:1024], "inline": False},
    ]
    payload = {
        "embeds": [
            {
                "title": "中古在庫を検出しました",
                "description": listing["title"],
                "url": listing["url"],
                "color": 0xE53935,
                "fields": fields,
                "footer": {"text": "カメラのキタムラ オンラインショップ"},
            }
        ]
    }
    response = requests.post(webhook, json=payload, timeout=30)
    response.raise_for_status()


def main():
    database = load_database()
    current_by_id = {item["id"]: item for item in fetch_listings()}

    if not database.get("initialized", False):
        database["initialized"] = True
        database["seen"] = current_by_id
        save_database(database)
        print(f"初回登録: {len(current_by_id)}件（通知なし）")
        return

    new_items = [
        item
        for item_id, item in current_by_id.items()
        if item_id not in database.get("seen", {})
    ]
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

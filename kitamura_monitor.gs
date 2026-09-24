/**
 * カメラのキタムラ RF100-300mm F2.8 L IS USM 中古監視
 *
 * 事前に [プロジェクトの設定] > [スクリプト プロパティ] に
 * DISCORD_WEBHOOK_URL を登録してください。
 */

const JAN_CODE = '4549292216165';
const PRODUCT_NAME = 'キヤノン RF100-300mm F2.8 L IS USM';
const LIST_URL = 'https://shop.kitamura.jp/ec/list?keyword3=' + JAN_CODE + '&type=u';
const API_URL = 'https://shop.kitamura.jp/ec/api/cache/vvc/u/v1/list';

function setup() {
  const webhook = PropertiesService.getScriptProperties().getProperty('DISCORD_WEBHOOK_URL');
  if (!webhook) throw new Error('DISCORD_WEBHOOK_URL をスクリプト プロパティに登録してください。');

  ScriptApp.getProjectTriggers().forEach(function(trigger) {
    if (trigger.getHandlerFunction() === 'monitor') ScriptApp.deleteTrigger(trigger);
  });

  monitor();
  ScriptApp.newTrigger('monitor').timeBased().everyHours(1).create();
}

function monitor() {
  const response = UrlFetchApp.fetch(
    API_URL + '?keyword3=' + JAN_CODE + '&sort=newer&ipg=100&page=1',
    {
      method: 'get',
      headers: {
        Accept: 'application/json, text/plain, */*',
        'Accept-Language': 'ja-JP,ja;q=0.9',
        Referer: LIST_URL,
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'
      },
      muteHttpExceptions: true
    }
  );

  if (response.getResponseCode() !== 200) {
    throw new Error('キタムラ中古検索の取得が拒否されました（HTTP ' + response.getResponseCode() + '）');
  }

  const payload = JSON.parse(response.getContentText());
  if (!payload || !Array.isArray(payload.items)) {
    throw new Error('キタムラ中古検索の応答形式が想定外です。');
  }

  const properties = PropertiesService.getScriptProperties();
  payload.items.forEach(function(item) {
    const itemId = String(item.itemid || '').trim();
    if (!itemId || properties.getProperty('seen_' + itemId)) return;
    sendDiscord_(item);
    properties.setProperty('seen_' + itemId, new Date().toISOString());
  });
  properties.setProperty('LAST_CHECKED_AT', new Date().toISOString());
}

function sendDiscord_(item) {
  const description = clean_(item.description);
  const firstSentence = description.split('。')[0];
  const accessories = firstSentence.indexOf('付') >= 0 ? firstSentence : '商品説明に記載なし';
  const payload = {
    embeds: [{
      title: '中古在庫を検出しました',
      description: clean_(item.title) || PRODUCT_NAME,
      url: clean_(item.title_link) || LIST_URL,
      color: 0xe53935,
      fields: [
        { name: '価格', value: formatPrice_(item.price), inline: true },
        { name: '状態', value: clean_(item.condition || item.rank) || '商品説明に記載なし', inline: true },
        { name: '付属品', value: accessories.substring(0, 1024), inline: false },
        { name: '備考', value: (description || '記載なし').substring(0, 1024), inline: false }
      ],
      footer: { text: 'カメラのキタムラ オンラインショップ' }
    }]
  };
  const webhook = PropertiesService.getScriptProperties().getProperty('DISCORD_WEBHOOK_URL');
  const response = UrlFetchApp.fetch(webhook, {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });
  if (response.getResponseCode() < 200 || response.getResponseCode() >= 300) {
    throw new Error('Discord通知に失敗しました（HTTP ' + response.getResponseCode() + '）');
  }
}

function clean_(value) {
  return String(value || '').replace(/\s+/g, ' ').trim();
}

function formatPrice_(value) {
  const amount = Number(value);
  return Number.isFinite(amount) ? amount.toLocaleString('ja-JP') + '円（税込）' : clean_(value) || '記載なし';
}

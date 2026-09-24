# Google Apps Scriptへの移行

GitHub ActionsはカメラのキタムラからHTTP 403で拒否されるため、監視はGoogle Apps Scriptで実行します。

1. [Google Apps Script](https://script.google.com/home/projects/create) を開き、新しいプロジェクトを作成する
2. エディタ内の既存コードを全て消し、[kitamura_monitor.gs](./kitamura_monitor.gs) の内容を貼り付けて保存する
3. 左側の歯車（プロジェクトの設定）を開き、**スクリプト プロパティ**で次を追加する  
   - プロパティ: `DISCORD_WEBHOOK_URL`  
   - 値: 既存のDiscord Webhook URL
4. 上部の関数選択で `setup` を選び、**実行**する。Googleの認可画面では自分のアカウントで許可する
5. Discordに現在の在庫が届けば完了。以後はGoogle側で1時間ごとに自動実行される

同じ中古個体は商品IDごとに一度しか通知しません。取得失敗は「在庫なし」とは扱わず、Apps Scriptの実行履歴にエラーとして残します。

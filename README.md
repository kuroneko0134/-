# proseka

プロセカ（プロジェクトセカイ カラフルステージ！ feat. 初音ミク）の**公開マスターデータと連携する**Python ライブラリ / CLI です。

キャラクター・ユニット・楽曲・譜面・カード・イベントを取得し、型付きのオブジェクトとして扱えます。依存パッケージはゼロ（標準ライブラリのみ）、ダウンロードしたデータはローカルにキャッシュされ、ETag による差分確認で再取得を最小限に抑えます。

> 非公式プロジェクトです。SEGA / Colorful Palette / Crypton Future Media とは関係ありません。
> データ取得元は有志が公開している [Sekai-World マスターデータミラー](https://github.com/Sekai-World/sekai-master-db-diff)で、ゲームサーバーには一切アクセスしません。アカウントや認証情報も不要です。

## 対応サーバー

| コード | 地域 | 取得元リポジトリ |
| --- | --- | --- |
| `jp` | 日本（既定） | `sekai-master-db-diff` |
| `en` | グローバル | `sekai-master-db-en-diff` |
| `tc` | 繁體中文 | `sekai-master-db-tc-diff` |
| `kr` | 한국어 | `sekai-master-db-kr-diff` |
| `cn` | 简体中文 | `sekai-master-db-cn-diff` |

## インストール

```bash
pip install -e .
```

インストールせずに使う場合は `PYTHONPATH=src python3 -m proseka ...` で動きます。

## CLI

```bash
proseka sync                       # 主要テーブルをダウンロード
proseka character ichika           # 日本語・かな・英語・ID で検索
proseka unit "25時、ナイトコードで。" # ユニットとメンバー
proseka music ロキ                 # 曲名・読み・作者名で検索（譜面レベル付き）
proseka level 32 --difficulty master
proseka cards ミク --rarity 4      # レアリティ・属性で絞り込み
proseka event                      # 開催中と次回のイベント
proseka --region en event --recent 5
proseka cache path                 # キャッシュの場所
```

主なグローバルオプション:

| オプション | 説明 |
| --- | --- |
| `--region {jp,en,tc,kr,cn}` | サーバー地域（既定 `jp`） |
| `--json` | 生のマスターレコードを JSON で出力 |
| `--offline` | 通信せずキャッシュだけを使う |
| `--refresh` | キャッシュを無視して再取得 |
| `--ttl 秒` | キャッシュ有効期間（既定 6 時間） |
| `--cache-dir パス` | キャッシュ保存先 |

実行例:

```
$ proseka music ロキ
#2 ロキ
  制作   : みきとP
  配信日 : 2019-06-10 06:27 UTC
  譜面   : EA7 NO11 HA17 EX24 MA29 AP28
```

## ライブラリとして使う

```python
from proseka import ProsekaClient

sekai = ProsekaClient("jp")          # 地域を選ぶ。既定は jp

ichika = sekai.find_characters("一歌")[0]
print(ichika.full_name, ichika.full_name_english, ichika.unit)
# 星乃 一歌 Ichika Hoshino light_sound

for card in sekai.cards_for_character(ichika, rarity="4*", attr="cool"):
    print(card.rarity_stars, card.prefix)

song = sekai.find_musics("Tell Your World")[0]
for chart in sekai.difficulties_for(song.id):
    print(chart.label, chart.total_note_count)
# EASY 5 220 ... MASTER 26 1147

event = sekai.current_event()
if event:
    print(event.name, event.start_at, event.aggregate_at)
```

### 主な API

| メソッド | 返すもの |
| --- | --- |
| `characters()` / `character(id)` / `find_characters(q)` | キャラクター |
| `units()` / `unit(code)` / `characters_in_unit(code)` | ユニットと所属メンバー |
| `musics()` / `music(id)` / `find_musics(q)` | 楽曲 |
| `difficulties_for(music_id)` / `charts_at_level(lv, diff)` | 譜面 |
| `cards()` / `card(id)` / `cards_for_character(c, rarity=, attr=)` | カード |
| `events()` / `current_event()` / `next_event()` / `recent_events(n)` | イベント |
| `table(name)` | 任意のマスターテーブル（生の dict のリスト） |
| `sync()` / `clear_cache()` | 一括取得 / キャッシュ削除 |

モデルは frozen dataclass です。日時は UTC の aware な `datetime` に変換済みで、元のレコードは `.raw` と `.get("フィールド名")` からそのまま参照できます。ここでモデル化していないテーブル（ガチャ、スキル、称号など）も `table("gachas")` のように名前を渡せば取得できます。

### 検索の挙動

`find_characters` と `find_musics` は NFKC 正規化・大文字小文字・空白を吸収します。`ﾐｸ`・`ミク`・`miku`・`MIKU` はすべて同じ結果になります。

### キャッシュとオフライン

初回取得後は `~/.cache/proseka/<region>/` に保存されます（`PROSEKA_CACHE_DIR` または `XDG_CACHE_HOME` で変更可）。

- TTL 内はネットワークに出ません。
- TTL 切れ後は `If-None-Match` で差分確認し、変更がなければ再ダウンロードしません。
- 通信に失敗した場合はキャッシュがあればそれを使い、警告ログを出します。
- `offline=True` にすると一切通信せず、キャッシュが無ければ `OfflineError` になります。

```python
sekai = ProsekaClient("jp", offline=True)        # 通信禁止
sekai = ProsekaClient("en", ttl=60 * 60)          # 1 時間キャッシュ
```

## テスト

```bash
python3 run_tests.py
```

88 個のテストはすべて同梱のフィクスチャと擬似トランスポートで動くため、ネットワークに接続しません。

## ライセンス

MIT License（このリポジトリのコードについて）。マスターデータ自体の権利は原著作者に帰属します。

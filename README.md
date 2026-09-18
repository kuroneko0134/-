# proseka

プロセカ（プロジェクトセカイ カラフルステージ！ feat. 初音ミク）の**公開マスターデータと連携する**Python ライブラリ / CLI です。

キャラクター・ユニット・楽曲・譜面・カード・イベントを取得し、型付きのオブジェクトとして扱えます。依存パッケージはゼロ（標準ライブラリのみ）、ダウンロードしたデータはローカルにキャッシュされ、ETag による差分確認で再取得を最小限に抑えます。

> 非公式プロジェクトです。SEGA / Colorful Palette / Crypton Future Media とは関係ありません。
> データ取得元は有志が公開している [Sekai-World マスターデータミラー](https://github.com/Sekai-World/sekai-master-db-diff)で、ゲームサーバーには一切アクセスしません。アカウントや認証情報も不要です。

## スマホのアプリとの連携について

先に正直なところを書いておきます。**スマホに入っているプロセカのアプリと自動で直接つなぐ方法はありません。**

- 公式の API や連携機能は公開されていません。開発者向けの窓口もありません。
- セーブデータはアプリのサンドボックス内にあります。iOS では他のアプリから読めません。Android でも `/data/data/` 以下は root 化しない限り読めません。
- ゲームサーバーにアカウントでアクセスするにはアプリの通信を偽装する必要があります。利用規約違反で BAN の危険があるため、このリポジトリでは実装しません。

そこで、このツールは次の分担にしています。

| 担当 | 中身 |
| --- | --- |
| マスターデータ | 全曲・全譜面・全カード・全イベントを自動で取得（上記のミラーから） |
| 自分のデータ | アプリの画面を見て入力、または CSV で取り込み（`proseka me`） |

自分の記録とマスターデータを突き合わせることで、アプリだけでは分からないこと（レベル別のフルコン率、未達成の譜面、未所持カード、イベントの必要ペース）が出せます。

### 自分の記録を入れる

```bash
# プロフィール（アプリのプロフィール画面を見ながら）
proseka me profile --name くろねこ --user-id 123456789012345 --rank 120

# 1 譜面ずつ記録する。曲名・難易度・クリア状況は日本語でも通ります
proseka me play テオ master --clear fc --score 1180000
proseka me play ロキ マスター --clear クリア

# まとめて入れるなら CSV
proseka me import plays.csv
```

CSV は日本語ヘッダーでも英語ヘッダーでも読めます。曲は ID でも曲名でも構いません。

```csv
曲名,難易度,クリア,スコア
テオ,マスター,fc,1180000
ヒバナ -Reloaded-,master,クリア,980000
```

同じ譜面をもう一度記録しても、**前より悪い結果では上書きされません**（`--overwrite` で強制できます）。

### 記録を使う

```bash
proseka me progress --difficulty master   # レベル別のクリア率・フルコン率・AP 率
proseka me todo --goal fc --level 32      # まだフルコンしていない MASTER 32
proseka me cards ミク --rarity 4          # 所持 ○ / 未所持 ・
proseka me event --points 250000 --target 1000000  # 目標までの必要ペース
proseka me export --csv > backup.csv      # いつでも書き出せる
```

出力例:

```
$ proseka me event --points 250000 --target 1000000
Drive to Dream！ (2026-09-14 06:00 UTC 〜 2026-09-20 11:59 UTC)
  現在     : 250,000 pt
  目標     : 1,000,000 pt
  残り     : 750,000 pt / 43.8 時間
  必要ペース: 17,127 pt/時
```

記録は `~/.local/share/proseka/<region>/player.json` に平文の JSON で保存されます（`PROSEKA_DATA_DIR` または `--data-dir` で変更可）。外部には一切送信しません。

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
proseka me ...                     # 自分の記録（上のセクションを参照）
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
| `--data-dir パス` | 自分のプレイデータの保存先 |

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

自分の記録を扱う側は `PlayerStore` と `Collection` です。

```python
from proseka import ProsekaClient, PlayerStore, Collection, ClearType, PlayRecord

store = PlayerStore.open("jp")
store.set_record(PlayRecord(3, "master", ClearType.FULL_COMBO, 1180000))
store.save()

me = Collection(ProsekaClient("jp"), store)
for row in me.todo("ap", difficulty="master", level=32)[:5]:
    print(row.chart.label, row.clear.label, row.music.title)

for summary in me.level_summary("master"):
    print(summary.level, f"{summary.rate(ClearType.FULL_COMBO):.0%}")
```

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

185 個のテストはすべて同梱のフィクスチャと擬似トランスポートで動くため、ネットワークに接続しません。

## ライセンス

MIT License（このリポジトリのコードについて）。マスターデータ自体の権利は原著作者に帰属します。

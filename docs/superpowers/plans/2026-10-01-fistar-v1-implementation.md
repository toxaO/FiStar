# FiStar初版 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking. 実行方式はこのチャットでの逐次実装を推奨する。サブエージェントを使用する場合は利用者の明示指定を確認する。

**Goal:** フィルムスターショットの読込、校正、手動確認・修正、中心・半径計算、履歴と出力を日本語GUIで一連の操作として完成させる。

**Architecture:** 解析計算と作業状態をQtから独立させ、GUIは状態を表示して操作を伝える。スポーク候補は照射帯から抽出し、中心線の最大垂直距離を最小化する計算を用いる。記録には結果と再現用スナップショットを保存する。

**Tech Stack:** Python 3.11以上、PySide6、NumPy、OpenCV、tifffile、SciPy、SQLite。検証はpytest、QtのQTest、必要に応じてPDF確認用pypdf。

**Spec:** [要求仕様書](../specs/2026-10-01-fistar-requirements-specification.md)

## Global Constraints

- 1画像・1回転軸の2D解析。回転軸はガントリ、コリメータ、カウチ。
- 日本語の解析／記録画面。Python環境から起動し、実行ファイル配布は含めない。
- レーザー基準点は手動指定。自動検出は最終結果として確定せず、利用者の確認を必要とする。
- 校正なしはpixelで継続可能。許容値は装置・軸別に設定し、未設定時は判定しない。
- 回転時半径とレーザー偏位は別の評価値。交点平均で中心を代用しない。
- SQLite履歴、装置・軸別トレンド、UTF-8 CSV、日本語1ページ要約PDFを実装する。
- 実画像の臨床的精度は未検証。合成画像の数値誤差条件はソフトウェア検証の条件であり、臨床精度の保証ではない。
- 現在のソースは仕様適合性を確認した部分のみ再利用する。サンプルと既存データベースは変更・削除しない。
- 現在のディレクトリにはGit管理情報がない。Git初期化・コミット・ブランチ作成は自動実行しない。後にGit管理されている場合は各タスク単位で変更をまとめる。

## Review Focus

1. RGBのBGR取り違え・16bitの8bit化で結果が変わる条件 → Task 1で原値とチャンネル変換を検証。
2. X/Y解像度の不一致、タグ欠落・単位なし、ゼロ長手動校正 → Task 1・2で異方性校正と入力拒否を検証。
3. 反対向きの腕の二重計上、中央重なり、筆記文字・穴 → Task 3で合成帯とサンプルの確認を行う。
4. 前段階変更・再検出・非同期完了が手動修正や別画像を上書きする条件 → Task 4・5で状態遷移と版番号を検証。
5. 既存DB、保存・出力失敗、mm/pixel混在、現在の許容値で過去結果を書き換える条件 → Task 6・7で保護とスナップショットを検証。

## ファイルと共通インターフェース

現行の巨大な画面制御を引き継がず、以下の責務で構成する。既存ファイルを置き換えるタスクでは、その公開入口を同時に切り替える。使用されなくなったソースの削除は初版に必須ではない。

| ファイル | 責務 |
|---|---|
| src/fistar/core/models.py | 解析・校正・検出・記録に共通する型 |
| src/fistar/core/imaging.py | TIFF、RGBチャンネル、校正、表示用変換 |
| src/fistar/core/geometry.py | 正規化直線、最小最大偏差円、座標変換 |
| src/fistar/core/detection.py | 照射帯抽出と中心線フィット |
| src/fistar/core/analysis.py | 評価値・単位・許容値の組合せ |
| src/fistar/workflow/session.py | 作業状態、確認状態、変更による無効化 |
| src/fistar/gui/image_view.py | 画像表示、点・校正線・スポーク編集 |
| src/fistar/gui/analysis_panel.py | 段階式操作と結果表示 |
| src/fistar/gui/records_panel.py | 履歴一覧・絞り込み・トレンド |
| src/fistar/gui/app.py | ウィンドウ、保存先、画面間連携 |
| src/fistar/storage/repository.py | 新規スキーマ、装置・許容値・測定保存 |
| src/fistar/exporting.py | CSVとPDF |

モデルはdataclassを使用する。NumPy画像は記録JSONに含めない。

内部軸名はgantry/collimator/couch、単位はpx/mmとする。確認ステップ名はimage/identity/calibration/laser/spokes/resultとし、日本語表示との対応をGUIで定義する。

- Point(x: float, y: float)、Line(nx: float, ny: float, offset: float)：単位法線による nx*x + ny*y = offset。線の方向は180度周期。
- Calibration(sx_mm: float, sy_mm: float, source: str, reference: tuple[Point, Point, float] | None)：画素のX/Y寸法。手動校正では両軸を同一寸法にする。
- LoadedImage(path: Path, raw: ndarray, sha256: str, tagged_calibration: Calibration | None)：原画と識別情報。
- DetectionSettings(inner_radius_px: float, outer_radius_px: float, threshold: float | None, polarity: str)：threshold=Noneは自動初期値。polarityはdark/bright。
- Spoke(id: str, line: Line, support: tuple[Point, ...], origin: str, excluded: bool)：originはauto/manual。IDは編集しても変えない。
- DetectionResult(spokes: tuple[Spoke, ...], settings: DetectionSettings, warnings: tuple[str, ...])。
- Circle(center: Point, radius: float)、MetricResult(unit: str, circle: Circle, laser_delta: Point, laser_distance: float)。
- AnalysisResult(pixels: MetricResult, physical: MetricResult | None, active_spoke_ids: tuple[str, ...])：校正済み主表示はphysical。
- Limits(unit: str, radius: float | None, laser_distance: float | None)、Judgment(radius: str, laser_distance: str)：内部状態はwithin/exceeded/unset/unit_mismatch。
- Measurement(id: str, created_at: str, device: str, axis: str, image_name: str, result: AnalysisResult, limits: Limits, judgment: Judgment, snapshot: dict)：完全な保存スナップショット。

## Task 1: TIFF入力・チャンネル・距離校正

**Files:** Create core/models.py, core/imaging.py, tests/test_imaging.py; Modify pyproject.toml, requirements.txt。

**Interfaces:**
- Produces: load_tiff(path: Path) -> LoadedImage。
- Produces: analysis_channel(image: LoadedImage, channel: str) -> ndarray、display_image(values: ndarray, low: float, high: float) -> ndarray。
- Produces: manual_calibration(start: Point, end: Point, length_mm: float) -> Calibration。

- [x] 依存はpyproject.tomlへ集約し、requirements.txtはインストール入口として同期する。SciPy・tifffileを追加し、開発extraにpytest・pypdfを記載する。検証用環境を先に準備する。Run: rtk proxy .venv/bin/python -m pip install -e '.[dev]'。
- [x] 一時TIFFを使う検証を先に作る。RGB16bitのR/G/B順と保持、輝度の0.299R+0.587G+0.114B、原画不変、複数ページ拒否、グレースケールを検証する。
- [x] タグのインチ・cm換算、X/Y別寸法、ResolutionUnitなしでは自動校正なし、破損タグではpixel継続、手動10px=5mmなら両軸0.5mm/pxを検証する。ゼロ長・非正実距離は拒否。
- [x] Run: rtk proxy .venv/bin/python -m pytest tests/test_imaging.py -q。実装前は対象APIの不足で失敗することを確認する。
- [x] tifffileで1ページを読み、RGB配列をRGB順で保持する。SHA-256を求め、解析チャンネルはfloat64を返す。原画と表示用8bit画像を別配列にする。
- [x] 同じ検証を再実行してPASSを確認し、2枚の実画像がRGB uint16として読み込めることを確認する。

代表検証:

```python
def test_manual_scale():
    c = manual_calibration(Point(0, 0), Point(10, 0), 5)
    assert c.sx_mm == c.sy_mm == 0.5
```

## Task 2: 最小最大偏差円と評価値

**Files:** Modify core/geometry.py, core/analysis.py; Create tests/test_geometry_v1.py, tests/test_metrics.py。

**Interfaces:**
- Consumes: Line、Point、Calibration、Spoke、Limits。
- Produces: fit_line(points: ndarray) -> Line、minimax_circle(lines: tuple[Line, ...]) -> Circle。
- Produces: evaluate_spokes(spokes: tuple[Spoke, ...], laser: Point, calibration: Calibration | None) -> AnalysisResult。
- Produces: judge(result: MetricResult, limits: Limits) -> Judgment。

- [x] x=0、y=0、x+y=2の3線で期待中心(r,r)、r=2/(2+sqrt(2))となる検証を書く。既知中心を通る3線なら半径0、平行線だけ・有効方向3未満ならエラーとする。
- [x] レーザー(0,0)から中心(r,r)への成分と距離、除外スポーク、負座標中心、校正X/Yが異なる例を検証する。純粋な直線計算の比較誤差は1e-6座標単位以下。
- [x] x=-1、x=1、y=0、x+y=0の4線で最適中心が複数あるケースを検証する。二乗距離和による選択は中心(0,0)、半径1になる。
- [x] Run: rtk proxy .venv/bin/python -m pytest tests/test_geometry_v1.py tests/test_metrics.py -q。実装前に対象API不足を確認する。
- [x] 単位法線で直線を正規化する。TLSで中心線をフィットする。SciPy linprog(method='highs')で変数(cx,cy,r)、目的r、制約±(n·C-offset)<=rを解く。cx/cyは上下限なし、r>=0。ソルバ失敗や非有限値を結果として返さない。
- [x] 最適中心が複数ある場合は、最適半径を保つ制約下で全線への二乗距離和を最小にする中心を採用する。二次最適化はSciPy minimizeのSLSQPを使い、主制約の誤差を検証する。レーザー点を中心選択の基準にしない。二次計算失敗なら計算エラーとして示す。
- [x] 校正済みは線の支持点・レーザー点を物理座標へ変換して再計算する。X/Yが異なる場合、pixel半径を単一係数でmm換算しない。pixelとmmは独立したMetricResultとして保持する。
- [x] 許容値と結果の単位が一致しない場合は判定しない。上限と等しい値はwithinとし、丸め前の値で比較する。
- [x] 同じ検証を再実行してPASSを確認する。計算結果を表示丸めする前に保存する。

代表検証（pytest、sqrtをimport）:

```python
def test_nonconcurrent_triangle():
    c = minimax_circle((Line(1, 0, 0), Line(0, 1, 0),
                        Line(1/sqrt(2), 1/sqrt(2), sqrt(2))))
    r = 2 / (2 + sqrt(2))
    assert (c.center.x, c.center.y, c.radius) == pytest.approx((r, r, r), abs=1e-6)
```

## Task 3: 照射帯からのスポーク自動検出

**Files:** Create core/detection.py, tests/test_detection.py, tests/fixtures/synthetic_starshot.py。

**Interfaces:**
- Consumes: analysis_channel、fit_line、DetectionSettings。
- Produces: detect_spokes(values: ndarray, hub: Point, settings: DetectionSettings) -> DetectionResult。
- Test fixture: synthetic_starshot(angles_deg: tuple[float, ...], *, shape=(512, 512), width_px=10, seed=0) -> ndarray。中心は画像中央、背景は明、帯は暗とする。

- [x] 幅一定の6本の照射帯を不均等角で描く合成画像を作る。12本の腕ではなく6本の中心線を返すこと、帯を1本欠落させれば5本になることを検証する。
- [x] 中央重なり・小さい穴・端の筆記模擬・明暗反転・固定seedノイズを含む検証を追加する。理想的な無ノイズ画像は既知線からの中心付近垂直誤差1px以下とする。
- [x] Run: rtk proxy .venv/bin/python -m pytest tests/test_detection.py -q。対象API不足で失敗することを確認する。
- [x] hubは確認済みレーザー点を探索範囲の基準にのみ使う。中心線をレーザー点へ強制的に通さない。既定円環は画像短辺の0.12〜0.40倍、範囲は利用者が調整できる。
- [x] 円環内の選択チャンネルに大津閾値の初期値を求め、指定閾値・極性で照射帯マスクを作る。中央交差と画像端の筆記を円環で避け、連結した帯の画素群をTLSでフィットする。
- [x] 長い帯を候補にし、反対側へ伸びる同一照射帯の腕を方向・幅・中心線の整合性でまとめて再フィットする。角度等間隔やファイル名から本数を決めない。実際に異なるオフセットの照射帯を単に近い角度だけで統合しない。
- [x] 検出不足・結合帯はwarningsとして返し、手動追加・除外・中心線修正へ移れるようにする。円環や閾値の内部既定値は設定として保存する。
- [x] 検証PASS後、両サンプルの候補線オーバーレイを出して確認する。実画像本数・中心の正解は現時点で固定せず、初版の利用者確認対象とする。

代表検証:

```python
def test_opposed_arms_counted_once():
    image = synthetic_starshot((0, 25, 50, 90, 120, 150))
    detected = detect_spokes(image, Point(256, 256),
                             DetectionSettings(60, 200, None, "dark"))
    assert len(detected.spokes) == 6
```

## Task 4: 段階操作と手動修正の状態管理

**Files:** Create workflow/__init__.py, workflow/session.py, tests/test_session.py。

**Interfaces:**
- Consumes: Task 1〜3のモデルと計算API。
- Produces: AnalysisSession、set_image(image)、set_identity(device, axis)、set_channel(channel)、set_calibration(calibration)、set_laser(point)、set_detection_settings(settings)、set_detection(detection)、replace_spoke(spoke)、confirm_step(step)、can_save() -> bool、snapshot() -> dict。
- Produces: revision: int、dirty: bool、result: AnalysisResult | None、confirmed_steps: set[str]、image、channel、calibration、laser、spokes、detection、device、axis。初期未入力はNoneまたは空列とする。

- [x] 段階の前提、レーザー指定前の検出拒否、解析結果確認前の保存拒否、pixel継続、3方向未満の保存拒否を検証する。
- [x] スポーク移動・追加・除外で再計算され、原候補と最終スポークが別に保持されることを検証する。上流変更は後続確認を解除し、既存手動線を通知なしで捨てない。
- [x] Run: rtk proxy .venv/bin/python -m pytest tests/test_session.py -q。実装前の失敗を確認する。
- [x] 状態はQt非依存で実装する。表示ズーム・明るさは解析revisionを進めず、画像・チャンネル・検出設定・点・線変更は進める。
- [x] 校正・レーザー変更では現在の線を保ったまま計算結果を更新する。チャンネル変更や再検出は修正済み線がある場合に置換確認を要求し、取消時は状態を保つ。
- [x] 完全なsnapshotをJSON可能なプリミティブで作る。画像配列は含めず、原検出と最終線・各設定を含める。
- [x] 同じ検証を再実行してPASSを確認する。

代表検証:

```python
def test_empty_session_cannot_save():
    session = AnalysisSession()
    assert session.result is None
    assert not session.can_save()
```

## Task 5: 解析GUIと画像上の編集

**Files:** Modify gui/app.py, gui/image_view.py, gui/profile_plot.py; Create gui/analysis_panel.py, tests/test_analysis_gui.py。

**Interfaces:**
- Consumes: AnalysisSessionとimaging/detection API。
- Produces: ImageViewのlaser_selected(Point)、calibration_selected(Point, Point)、spoke_changed(Spoke)のQt signals。
- Produces: ImageView.set_mode(mode: str) -> None、set_session(session: AnalysisSession) -> None。modeはpan/calibration/laser/spoke。
- Produces: AnalysisPanel(session: AnalysisSession)、MainWindowの解析・記録タブ間連携。
- MainWindow(database_path: Path | None = None)とし、検証は一時DBを明示する。tests/conftest.pyに単一QApplicationを返すqapp fixtureを作る。

- [x] QTestで、画像読込前の無効操作、レーザー選択とパンの分離、線移動後の結果更新、確認後の保存可否を検証する。
- [x] Run: rtk proxy env QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_analysis_gui.py -q。実装前の失敗を確認する。
- [x] 左画像・右操作の解析画面を再構成する。操作は画像、装置・軸、校正、レーザー、スポーク、結果の順。RGBチャンネル、閾値、極性、探索円環はスポーク段階で確認できる。
- [x] 操作モードをパン／校正／レーザー／スポークに分ける。スポークは2点指定で追加、端点ドラッグで回転、線ドラッグで移動、一覧から除外・復帰できる。ホイール拡大とリセットは常時使用可能とする。
- [x] 選択線の帯と法線方向の画素値プロファイルを示す。プロファイルは検出・チャンネル確認の補助で、旧仕様のプロファイル境界中点方式へ戻さない。
- [x] 原画像、レーザー点、中心線番号、計算中心・円を重ねる。異方性校正時は物理円を画素表示へ逆変換した楕円として描画する。
- [x] 検出処理はQThreadPoolで行う。完了時にsession revisionと画像IDを照合し、古い結果を適用しない。計算不能・未検証・許容値なしを日本語で表示する。
- [x] 未保存時の別画像読込と終了には保存／破棄／キャンセルを用意する。読込・保存失敗でsessionを失わない。検証PASS後、実画像を開いたGUIを目視確認する。

代表検証:

```python
def test_empty_window_blocks_save(qapp, tmp_path):
    window = MainWindow(database_path=tmp_path / "test.sqlite")
    assert not window.analysis_panel.save_button.isEnabled()
    window.close()
```

## Task 6: 装置・許容値・履歴・トレンド

**Files:** Modify storage/repository.py; Create gui/records_panel.py, tests/test_repository_v1.py, tests/test_records_gui.py。

**Interfaces:**
- Consumes: Measurement、AnalysisResult、Limits、snapshot。
- Produces: connect_database(path: Path) -> Connection、save_measurement(connection, measurement: Measurement) -> str。
- Produces: list_measurements(connection, device: str | None, axis: str | None, since: str | None, until: str | None) -> tuple[Measurement, ...]。
- Produces: set_limits(connection, device: str, axis: str, limits: Limits) -> None、get_limits(connection, device: str, axis: str) -> Limits、delete_measurement(connection, id: str) -> None。

- [x] 既存analysesテーブルを含むDBを開いても内容・表を削除しない検証を書く。未保存のsessionに保存失敗を返してもdirtyのまま再保存可能であることも確認する。
- [x] 精度を丸めない保存・読み戻し、修正履歴スナップショット、装置軸絞り込み、保存時許容値の保持、単位別トレンドを検証する。
- [x] Run: rtk proxy env QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_repository_v1.py tests/test_records_gui.py -q。実装前の失敗を確認する。
- [x] 新規表devices_v1、limits_v1、measurements_v1をトランザクションで作成する。旧analysesには触れない。measurements_v1は検索用基本列とschema_version付きsnapshot JSONを持つ。
- [x] データベース既定保存先はQStandardPaths.AppDataLocation配下のfistar-v1.sqliteとし、画面に場所を表示する。作業ディレクトリの既存fistar.sqliteを自動移行・上書きしない。
- [x] 装置・軸ごとの許容値は単位を明示して保存する。結果の単位と違う設定では判定しない。表示丸め前で比較し、過去Measurementの許容値・状態を設定更新で書き換えない。
- [x] 解析日時はタイムゾーン付きISO形式で保存する。並べ替え・絞り込みはUTCの時刻で比較し、画面は利用端末の現地時間で表示する。
- [x] 記録タブに日時降順の一覧と装置・軸・日時フィルタ、選択行削除の確認を作る。Qt描画のトレンドを使い、半径と偏位、mmとpixelを分ける。
- [x] 同じ検証を再実行してPASSを確認する。

代表検証（sqlite3をimport）:

```python
def test_existing_analyses_kept(tmp_path):
    path = tmp_path / "old.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE analyses(marker TEXT)")
        db.execute("INSERT INTO analyses VALUES ('keep')")
    db = connect_database(path)
    assert db.execute("SELECT marker FROM analyses").fetchone()[0] == "keep"
    db.close()
```

## Task 7: CSV・日本語1ページPDF

**Files:** Create exporting.py, tests/test_exporting.py; Modify gui/app.py, gui/records_panel.py。

**Interfaces:**
- Consumes: Measurement、list_measurementsのフィルタ結果。
- Produces: export_csv(records: tuple[Measurement, ...], path: Path) -> None、export_pdf(record: Measurement, path: Path) -> None。

- [x] 日本語・カンマ・改行入り装置名のCSV往復、フィルタ済み行だけの出力、PDF1ページ、結果と単位・許容値の保存時値を確認する。
- [x] Run: rtk proxy env QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_exporting.py -q。実装前の失敗を確認する。
- [x] CSVは標準csvでUTF-8、日本語見出しを使う。ゼロ件は見出しのみ出す。snapshotの内部線群はCSVに含めない。
- [x] PDFはQt QPdfWriterとQPainterを用いてA4縦1ページ。装置、軸、日時、画像名、校正状態、スポーク本数、半径、偏位、単位、保存時許容値・状態を表示する。画像とスポーク別表は入れない。
- [x] 日本語を表示できるフォントをQtで選ぶ。長い装置名・画像名は枠内で折返し、欠落させない。フォント不足・書込失敗は原因を示し、壊れた完成ファイルを残さない。一時出力後に完成先へ置換する。
- [x] 検証PASS後、PDFをレンダリングして日本語・はみ出し・1ページを目視確認する。

代表検証:

```python
def test_empty_csv_has_header(tmp_path):
    path = tmp_path / "summary.csv"
    export_csv((), path)
    assert "装置名" in path.read_text(encoding="utf-8").splitlines()[0]
```

## Task 8: 統合確認・起動手順・現行入口の切替

**Files:** Modify __main__.py, tests/test_analysis.py; Create tests/test_workflow_end_to_end.py, README.md, docs/validation-v1.md。

**Interfaces:** Task 1〜7の入口を組み合わせ、python -m fistarでMainWindowを起動する。

- [x] 合成TIFFを使って読込→校正→レーザー→検出→1線修正→確認→保存→履歴→CSV/PDFの一連操作を検証する。別画像へ切替後に古いworker結果を適用しない検証も含める。
- [x] Run: rtk proxy env QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_workflow_end_to_end.py -q。結合前の不足を確認する。
- [x] 起動入口と全モジュールを新APIへ切り替える。旧テストの「ファイル名12なら12線」「読込だけで自動解析完了」は承認仕様と合わないため、新要件の検証へ置き換える。
- [x] 両実画像をGUIで操作し、保存・出力まで確認する。本数や精度をファイル名から正解扱いせず、利用者の確認結果と実画像精度未検証の状態を記録する。
- [x] Run: rtk proxy env QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q。全対象検証のPASSを確認する。失敗原因が画像処理・表示・保存のどれかを切り分けて修正する。
- [x] READMEにインストール、起動、DB場所、解析手順を記載する。validation-v1.mdに合成条件、検証結果、実画像の未検証事項、参照値を得た後の比較項目を記載する。
- [x] 最終確認で全要求仕様項目の対応箇所を点検し、未達事項を完了扱いしない。ソフトウェア検証と臨床精度検証を区別して報告する。

代表検証のcompleted_workflow fixtureは一連操作を実APIで実行し、(保存したMeasurement, 再読込した記録列, CSVパス, PDFパス)を返す。fixtureを本タスクの検証ファイル内に作る。

```python
def test_saved_workflow(completed_workflow):
    record, restored, csv_path, pdf_path = completed_workflow
    assert len(restored) == 1 and restored[0].id == record.id
    assert restored[0].result == record.result
    assert csv_path.is_file() and pdf_path.is_file()
```

## 実装前の明確化と資料

- サンプル2枚は約2640×2640画素のRGB uint16。画像入力で16bit保持とRGB順を検証する。
- スポーク本数は1本の中心線を持つ照射帯で数える。反対方向の腕は同じ帯として扱う。サンプル名は照射帯本数の正解として用いない。
- 校正済み解析は物理座標で評価する。異方性スケールではpixel解を単純換算すると最適円が変わるため、pixel・mmを別々に計算する。
- 最小最大偏差円の線形計画では座標変数に非負制約を付けない。[SciPy linprog公式資料](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linprog.html)
- PDF出力はQtの描画APIを利用する。[Qt QPdfWriter公式資料](https://doc.qt.io/qtforpython-6/PySide6/QtGui/QPdfWriter.html)

## 計画の自己確認

| 要求仕様 | 対応タスク |
|---|---|
| TIFF、原画保持、チャンネル、校正 | 1、2 |
| スポーク自動検出と本数・個別修正 | 3、4、5 |
| 半径・中心・レーザー偏位・施設許容値 | 2、4、6 |
| 段階式GUI、画像操作、失敗時の状態保持 | 4、5 |
| 装置軸別履歴、詳細自動保存、単位別トレンド | 6 |
| CSVと1ページPDF | 7 |
| 合成画像、同梱画像、運用説明、未検証事項 | 8 |

本計画の作成時にはアプリ実装・依存インストール・ソフトウェアテスト実行を行っていない。実行手順と合格条件は各タスク内に記載した。

実装記録：[検証記録](../../validation-v1.md)、[作業台帳](../../implementation-progress.md)。

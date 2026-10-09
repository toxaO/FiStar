# 実行ファイルのビルド

macOS用とWindows用は、それぞれのOS上でビルドします。PyInstallerは他のOS向けの実行ファイルを直接作るクロスビルドには対応していません。

## 準備

プロジェクトの仮想環境を有効にし、ビルド用依存を導入します。

```sh
python -m pip install -e ".[build]"
```

ビルド用依存はPyInstaller 6系とPillowです。Pylinacは3.48.0に固定しています。ビルド時はプロジェクトの`.venv`を優先して使用します。

## macOS

```sh
sh scripts/build_macos.sh
```

出力先は`dist/macos/`です。`FiStar.app`は通常のアプリバンドル（onedir形式）です。必要なライブラリをアプリ内部に保管し、起動時の一時展開を行いません。Finderでは1つのアプリとして表示されます。Finderからダブルクリックして起動します。現在の環境ではApple Silicon（arm64）用にビルドします。Intel版はIntel対応Python・依存環境で別途ビルドしてください。

採用したC案のPNGから`fistar.icns`を作成し、アプリのアイコンへ設定します。署名用の証明書は指定せず、PyInstallerのアドホック署名を使用します。Developer ID署名・公証はこのスクリプトには含みません。

macOSは起動速度とDockの表示を改善するためonedir、Windowsもonedirを使います。

## Windows

PowerShellで実行します。

```powershell
.\scripts\build_windows.ps1
```

出力先は`dist/windows/FiStar/FiStar.exe`です。onedir・windowed形式でビルドし、`fistar.ico`をexeへ設定します。配布時は`dist/windows/`全体をZIPにまとめ、利用者には全体を展開してもらってください。exeと同梱ライブラリ・資料を一緒に保管します。Windows環境でビルド・起動確認してください。macOS上ではこのスクリプトのWindowsビルドは実行できません。

## 共通処理

- アプリの画像・ツールアイコンを実行ファイルへ同梱します。
- Pylinacと依存パッケージのメタデータを同梱します。
- `LICENSE`、`THIRD_PARTY_NOTICES.md`、`licenses/`、操作マニュアルPDFを出力フォルダへコピーします。
- 生成specと作業ファイルは`build/<OS>/`、成果物は`dist/<OS>/`に保存します。どちらもGitの対象外です。
- 最終配布には、実際にバンドルされたQt・Python・推移依存の版、ライセンス・対応ソース提供・ライブラリ差替え条件を確認してください。資料のコピーだけで配布条件の確認完了とはしません。

キャッシュをクリアしてビルドする場合は、同じ仮想環境で共通スクリプトを直接呼び出します。

```sh
python scripts/build.py --platform macos --clean
```

Windowsでは`--platform windows`を指定します。

## 隔離した動作確認

本番のデータベースを変更せず、仮のデータベースで起動・画像読込・検出・PDF出力を確認するモードを用意しています。

```sh
dist/macos/FiStar.app/Contents/MacOS/FiStar --smoke-test sample/images/starshot-18.tif /tmp/fistar-frozen-check
```

Windowsでもexeに同じ引数を渡せます。出力先に`result.json`、`window.png`、`report.pdf`を作ります。`result.json`の`ok`と`frozen`がtrueなら、ビルドした実行ファイルから一連の処理を完了しています。測定値の臨床的精度を検証するものではありません。

参考：[PyInstallerの使用方法](https://pyinstaller.org/en/stable/usage.html)、[実行時の情報](https://pyinstaller.org/en/stable/runtime-information.html)。

## 初回onefileビルドの確認結果（2026-10-09）

- macOS arm64、Python 3.11、PyInstaller 6.22.3でonefileのFiStar.appを作成。
- アドホック署名を検証し、Info.plistのアイコン指定とICNSの存在を確認。
- ビルドしたアプリで隔離モードを実行し、画像読込・9本検出・画面表示・PDF2ページ出力に成功。result.jsonのfrozen=trueを確認。
- この作業環境のサンドボックスではmacOSアプリ登録・IPCが制限されるため、実行確認だけ制限外で実施。
- Windows版のビルド・実機操作、Intel Mac、Developer ID署名・公証は未実施。

## 起動速度・Dock表示の改善（2026-10-09）

macOSの既定ビルドをonedir形式へ変更しました。Finderでは同じFiStar.appですが、毎回の展開とonefileの親子プロセスを使いません。Windowsもonedirへ統一しました。

Pylinacの読み込みを最初の照射帯検出まで遅延します。画面モジュールの読み込みは計測環境で19.36秒→1.06秒になりました。最初の検出ではライブラリ準備・フォントキャッシュ作成で待つことがあります。

再ビルドしたarm64アプリの隔離確認で、プロセス開始から最初の画面表示まで3.46秒、起動プロセスと画面側PIDが一致し、起動時はPylinac未読込でした。検出・画面描画・PDF出力も成功しました。旧版を終了してから新しいFiStar.appを起動してください。Dockの実際の表示は通常のGUI起動で確認してください。


## バックグラウンド準備と永続キャッシュ

画面表示後に解析機能を準備し、準備中の検出要求は完了後に実行します。条件が変わった場合は要求を取り消します。失敗時はステータス欄の再試行ボタンを使います。ユーザー別のキャッシュフォルダを使用し、書込不能や破損時は一時キャッシュへ切り替えます。版・OS・配置先・実行ファイル更新でキャッシュを区別します。

隔離確認は一時DB・一時設定と、指定した出力フォルダ内の専用cacheだけを使用します。同じ出力フォルダで2回実行すると、result.jsonのcache_reused・preparation_seconds・detection_secondsで再利用と時間を比較できます。

### 永続キャッシュ版のmacOS確認（2026-10-09）

専用の一時DB・設定と検証用キャッシュで2回実行しました。本番DB・設定のハッシュは前後で一致し、成果物にSQLite・設定INIは含まれていません。

| 項目 | 初回 | 2回目 |
| --- | --- | --- |
| 最初の画面まで（プロセス開始から） | 4.20秒 | 2.64秒 |
| バックグラウンド準備 | 21.29秒 | 1.57秒 |
| 検出 | 0.12秒 | 0.10秒 |
| キャッシュ再利用 | なし | あり |

両方で9本検出・PDF出力に成功。Windows実機は未検証です。


## ポータブルデータ

macOSはdist/macos/data、Windowsはdist/windows/FiStar/dataを空の状態で生成します。起動後に記録・参考JPEG・設定が保存されます。既にデータがある場合は、ビルド開始前に停止し、削除・上書きはしません。配布物を作る前にdataを別の場所へバックアップしてください。動作確認では引き続き一時DB・設定のみを使用します。

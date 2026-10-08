# Third-party notices

## FiStar本体と自作素材

FiStar本体、操作マニュアル、自作のFiRec由来ツールアイコン、サンプルTIFFとその画面例にはルートの `LICENSE`（MIT、2026 toxaO）を適用します。FiStarアイコン案は画像生成で作成しています。第三者ライブラリの著作権・ライセンスをMITに変更するものではありません。

## 主な依存ライブラリ

以下のバージョンはライセンス確認時の開発環境です。Windows配布時は実際のビルド環境で確認し直してください。

| ライブラリ | 確認した版 | 主な条件・本文 |
| --- | --- | --- |
| Pylinac | 3.48.0 | MIT。本文は下記および `licenses/third-party/pylinac/`。 |
| NumPy | 2.4.6 | BSD-3-Clauseほか。付属コードの通知も `licenses/third-party/numpy/` に保存。 |
| SciPy | 1.17.1 | BSD-3-Clauseほか。バイナリ同梱ライブラリの通知を含め `licenses/third-party/scipy/` に保存。 |
| opencv-python-headless | 5.0.0.93 | Apache-2.0ほか。OpenCVと第三者コードの通知を `licenses/third-party/opencv-python-headless/` に保存。 |
| tifffile | 2026.3.3 | BSD-3-Clause。本文は `licenses/third-party/tifffile/`。 |
| PySide6 / Shiboken6 / Qt | 6.11.1 | LGPL/GPL/商用の選択肢あり。FiStarが使用するQtCore・QtGui・QtWidgetsはLGPLv3での利用を前提とする。使用版・同梱モジュールの条件を配布時に確認。 |

`licenses/third-party/` はインストール済み配布パッケージのライセンス関連ファイルを、その内容を変更せず保存したものです。すべての推移依存やWindowsバイナリの監査が完了したことを示すものではありません。

## Qtを含むWindows版の配布

- FiStarがPySide6/Qtを利用する旨を、配布READMEなどに明記します。
- FiStarの `LICENSE`、本通知、依存ライブラリの著作権表示・ライセンス本文を同梱します。LGPLv3と参照されるGPLv3の本文は `licenses/LGPL-3.0.txt` と `licenses/GPL-3.0.txt` に保存します。
- 使用したQt/PySide6などLGPL対象ライブラリの正確な版と、対応するソースの提供方法を記載します。上流への一般的なリンクだけで提供義務を満たしたとみなさず、配布方法に適合したソース提供または有効な書面での申出を用意します。
- 利用者がLGPL対象ライブラリを差し替えて動作させられる配布形態と、必要な手順を用意します。配布形式はその確認を含めて決めます。
- LGPLで認められるライブラリ改変・差替えのためのリバースエンジニアリングを制限しません。
- バンドルされるQtモジュールと第三者DLLを確認し、不要なGPL専用モジュールを含めないようにします。Python本体、推移依存、ビルドツール由来のランタイムも実際のWindows配布物を基準に確認します。

このリポジトリの準備とは別に、実行ファイルの配布前に上記を確認します。現時点でWindows実行ファイルのライセンス同梱・差替え動作は未検証です。

根拠： [Qt公式：LGPL利用時の義務](https://www.qt.io/development/open-source-lgpl-obligations)、[Qt for Pythonのライセンス](https://doc.qt.io/qtforpython-6/licenses.html)。



## Pylinac 3.48.0

円周プロファイルと半値幅中心の検出に利用します。https://github.com/jrkerns/pylinac

以下は配布パッケージのLICENSE.txtです。

```text
Copyright (c) 2014-2022 James Kerns

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
documentation files (the "Software"), to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions
of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED
TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF
CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
IN THE SOFTWARE.

```

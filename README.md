# pdfx

`pdfx` は、iOS アプリ **a-Shell** で使用することを想定した Python ベースの小さな PDF ページ操作 CLI です。

PDF のページ抽出、ページ削除、回転、結合を、1つのコマンド内で順番に指定できます。

## 特徴

- 指定ページの抽出
- 指定ページを除外して追加
- 複数 PDF の結合
- ページ単位の左回転・右回転・180度回転
- ページ順の入れ替え
- 同じページの複数回追加
- 複数の操作を指定順に結合

## インストール (a-Shell)

必要であれば事前準備

`~/Documents/bin` はパスが通っているはずです。

```sh
pip install pypdf
mkdir -p ~/Documents/bin
```

インストール:

```sh
cd ~/Documents/bin
curl -L https://raw.githubusercontent.com/nattzn/pypdfx/refs/heads/main/pdfx.py > pdfx
chmod +x pdfx
```

確認:

```sh
pdfx version
```

## 使い方

```sh
pdfx pick INPUT.pdf [PAGE_SPEC] out OUTPUT.pdf
pdfx drop INPUT.pdf PAGE_SPEC out OUTPUT.pdf
pdfx merge INPUT1.pdf INPUT2.pdf [...] out OUTPUT.pdf
```

複数の操作を並べると、指定した順番で1つのPDFに結合されます。

```sh
pdfx pick INPUT1.pdf "1,5-7,8R" pick INPUT2.pdf "-1,3-1" drop INPUT3.pdf "3-" out OUTPUT.pdf
```

## コマンド

| コマンド | 意味 |
|---|---|
| `pick` | 指定ページを指定順に追加する。`PAGE_SPEC` 省略時は全ページ |
| `drop` | 指定ページを除外し、残りのページを追加する |
| `merge` | 指定したPDFを全ページそのまま追加する。ページ指定はしない |
| `out` | 出力先PDFを指定する。最後に1回だけ指定する |
| `version` | バージョンを表示する |
| `help` | ヘルプを表示する |

## ページ指定 `PAGE_SPEC`

ページ指定(`[ページ範囲][回転]`)をカンマ区切りで並べます。空白は無視され、指定した順番で出力に追加されます。

### ページ範囲

| 指定 | 意味 |
|---|---|
| `1` or -1 | ページ指定 (1 ページ目 or 最後から 1 ページ目) |
| `3-5` or `5-3` | 範囲指定 (3〜5ページ目 or 5、4、3ページ目) |
| `8-` or `8--1` | 範囲指定 (8ページ目から最後まで) |
| 省略 | 全ページ |

### 回転

| 指定 | 意味 |
|---|---|
| `R` | 右90度回転 |
| `L` | 左90度回転 |
| `RR` / `LL` | 180度回転 |

`1R-4` のように、回転を範囲の途中に入れることはできません。

`drop` はページを除外する操作なので、回転指定は使えません。回転したい場合は `pick` を使ってください。

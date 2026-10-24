# har-skeleton

[![CI](https://github.com/KanadeK/har-skeleton/actions/workflows/ci.yml/badge.svg)](https://github.com/KanadeK/har-skeleton/actions/workflows/ci.yml)

Export a local HAR capture as a performance skeleton: request timing, status, byte sizes and
endpoint correlation survive; source URLs and HTTP content are discarded.

Use it when a teammate needs to investigate a slow waterfall without receiving your browser
session contents. It is intentionally lossy. The output still contains behavioral metadata
and is **not a guarantee of anonymity**.

## Install

Requires Python 3.10 or newer. There are no third-party runtime dependencies or API keys.
From a source checkout:

```sh
git clone https://github.com/KanadeK/har-skeleton.git
cd har-skeleton
python -m venv .venv
# Linux/macOS:
. .venv/bin/activate
# Windows PowerShell, instead of the line above:
# .\.venv\Scripts\Activate.ps1
python -m pip install .
har-skeleton --version
```

If PowerShell activation is restricted, run `.venv\Scripts\python.exe -m pip install .` and
`.venv\Scripts\har-skeleton.exe` directly. No execution-policy changes are needed.
This version is installed from source; no PyPI publication is claimed.

## Use

```sh
har-skeleton private.har share.har
# Or: python -m har_skeleton private.har share.har
```

The output must be a new path. The source and existing output files are never overwritten.
Success prints counts as JSON, for example:

```json
{"endpoints": 1, "entries": 1, "origins": 1, "pages": 0, "written": true}
```

Exit 0 means a skeleton was written. Exit 2 means invalid input, a resource limit or an I/O
error; a failed write may leave an incomplete new output file, which must be discarded.
Input validation completes before the output is opened. No input values are printed in errors.

Run the bundled synthetic example, which creates and removes its own temporary captures:

```sh
python examples/demo.py
python -m unittest discover -s tests -v
```

## Retained and removed data

| Retained | Rebuilt or discarded |
|---|---|
| Request order, elapsed time and phase timings | All headers, cookies, query values and POST data removed |
| Status codes and byte counts | Response bodies, redirect URLs and status text removed |
| Common method, HTTP version and MIME type from fixed allowlists | Custom strings replaced with constants |
| Same-origin/path correlation within one file | Hosts and paths become sequential `.invalid` aliases |
| Relative request/page start times | Earliest timestamp shifted to 2000-01-01 UTC |
| Page relationships and load timings | Page IDs and titles regenerated |
| Nothing else | IPs, comments, browser details, WebSocket payloads and unknown extensions removed |

No alias map is saved. Query strings do not affect endpoint identity. Aliases are scoped to
one export and should not be compared across files. The program never makes network requests.

Defaults are 64 MiB input and 100,000 entries/pages. Change them explicitly with `--max-bytes N`
and `--max-entries N`. The accepted upper bounds are 512 MiB and 1,000,000 entries/pages,
respectively. JSON parsing holds the capture in memory. Malformed JSON, duplicate keys,
invalid dates, non-finite/oversized numbers, invalid page references and unsupported URL
schemes are rejected. Capture spans above 366 days are refused. HTTP(S) and WS(S) URLs are supported.

## Limits and alternatives

This is useful for performance discussion, not request replay, authentication troubleshooting
or content inspection. Timing, resource sizes, status patterns and request counts can still
identify a workflow; inspect the output before sharing. Do not assume that synthetic URLs
make sensitive timing metadata public-safe. Browser-viewer import behavior varies; v0.1.0
tests the HAR JSON shape and transformation, not every browser's importer.

[Google HAR Sanitizer](https://github.com/google/har-sanitizer),
[Cloudflare HAR Sanitizer](https://github.com/cloudflare/har-sanitizer) and
[jfromaniello/har-sanitizer](https://github.com/jfromaniello/har-sanitizer) offer other redaction
policies. Choose those when preserving selected HTTP details is necessary. har-skeleton
instead rebuilds an allowlist and drops all arbitrary input text. It uses an independently
written implementation. See [design and acceptance criteria](docs/DESIGN.md).

## Cleanup and development

`python -m pip uninstall har-skeleton` removes the installed package. Remove the virtual
environment using your file manager when finished. Delete output captures deliberately;
the program does not keep a cache or history. It does not securely erase the original HAR.

See [CONTRIBUTING](CONTRIBUTING.md), [SECURITY](SECURITY.md) and the [MIT license](LICENSE).
The GitHub Actions configuration checks Windows, Ubuntu and macOS with Python 3.10/3.13;
remote CI results depend on an actual published run.

## 中文说明

这是一个离线 HAR 性能记录导出工具。它保留请求顺序、相对时间、耗时、状态码和字节数，
将域名与路径替换成同一文件内有效的编号，并删除请求头、Cookie、查询参数、正文、IP、
页面标题和未知扩展。适合只需讨论性能的场景，不能用于重放请求，也不保证匿名。

安装后运行 `har-skeleton private.har share.har`；输出文件必须不存在。
`python examples/demo.py` 可运行合成示例。源文件不变，程序不联网。
时序与大小仍可能暴露业务特征，分享前请检查输出。卸载使用
`python -m pip uninstall har-skeleton`，输出文件由使用者自行清理。

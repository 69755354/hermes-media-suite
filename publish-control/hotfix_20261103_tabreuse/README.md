# 客户机热修 2026-11-03 · 浏览器标签页复用与收尾清理

## 背景
每次发布/取数都以目标 URL 拉起 Chrome，已在运行的实例于是再开一个窗口；失败在填表前的任务又不会收尾。
结果客户机 1 号窗口累计 12 个页面（大量重复星图任务页）。

## 改动（4 个文件，仅客户机 1.2.173 安装目录内）
1. `agent/winport/chrome.py`
   - 新增 `cdp_pages()` / `find_open_page()`：通过 `/json/list` 找同站点已开标签页。
   - `launch_environment()` 在复用实例时若命中同站点页面，返回 `TAB_REUSED`，不再拉起新窗口。
2. `agent/winport/publish_exec.py`
   - 新增 `_host_of_url()` 与 `PlaywrightDriver._close_duplicate_site_pages()`；
   - `close()` 收尾时每个自动化站点（creator.douyin.com / www.xingtu.cn）最多留 1 个标签页，其它网站不动。
3. `agent/winport/collect_douyin.py`
   - 取数复用已有 creator.douyin.com 标签页；只有自己新建的页才关闭。
4. `agent/winport/collect_xingtu.py`
   - 同上，复用已有 xingtu 标签页（随后仍会 goto 任务页，行为不变）。

## 现场哈希（客户机实测）
| 文件 | MD5 | 字节 |
|---|---|---|
| chrome.py | b75a81f28f6146082ce9791fa7a0a35a | 49,322 |
| publish_exec.py | 21eea6ff89e86d9c095cea467ac53756 | 455,300 |
| collect_douyin.py | e19616e9e7aad1c51be5d9a042762083 | 9,057 |
| collect_xingtu.py | ec43a7646c46459ebc2dadfd958bc020 | 25,171 |

## 验证（2026-11-03 22:00 复核）
- 启动链完整性：`ok=true, checked=140, modified=0, missing=0, extra=0`（MANIFEST 已同步这 4 项）。
- 单元回归 `tests/test_tab_reuse.py`：3 passed（在“部署版 4 文件 + 1.2.173 余下代码”上运行）。
- 客户机实机导入：4 个模块均可导入，新增函数/常量存在（`find_open_page`、`_close_duplicate_site_pages`、`AUTOMATION_HOSTS`）。
- 实机 CDP：9224 端口只剩 2 个业务页（抖音发布页 + 星图任务页），`find_open_page` 正确命中抖音页。
- 发布由 `runtime\python.exe -m agent.winport.cli publish` 子进程执行，新代码下次任务即生效，无需重装。

## 注意
- `build_1.2.173/manju-publish-assistant-1.2.173-win64` 里仍是旧代码；**用该目录重装/重打包会覆盖掉本次热修**。
  重打包前先把本目录 `files/` 的 4 个文件覆盖进去，再按 CONTEXT.md 流程重建 MANIFEST / SHA256SUMS / PACKAGE_BINDING。
- 本目录 `publish_exec.py.diff` 的基线是客户机热修前文件（含 21:15 的 progress 时间戳改动），不是 1.2.173 原始包。

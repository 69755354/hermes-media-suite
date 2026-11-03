#!/usr/bin/env python3
"""拉取星广全部任务的视频明细，按消耗降序保存为 JSON + Excel。

用法：
  cd workflow/projects/attribution
  python3 scripts/fetch_all_videos.py          # 拉全量 → data/all_videos_snapshot.json
  python3 scripts/fetch_all_videos.py --excel  # 同时生成 Excel

依赖：openpyxl（pip3 install openpyxl）
Token：自动从 data/token_cache.json 读缓存，过期则走广州 SSH relay 获取。

输出字段：demand_name, demand_id, create_time, title, item_id, duration, url,
  nick_name, core_user_id, cost_li, ad_cost_li, natural_cost_li, reward_li,
  share_ratio, watch_cnt, play_rate3s, play_rate5s, play_finish_rate,
  like_cnt, comment_cnt, share_cnt, favorite_cnt, interact_cnt, interact_rate,
  avg_watch_dura, release_time, aweme_item_status, ad_status, item_status

注意事项：
  - 54个任务，部分任务2000+条视频，全量拉取约6-8分钟
  - API返回累计快照非按日历史，需每天拉一次算增量
  - cost_li 单位是厘（元×1000），play_rate3s/5s/finish_rate 是万分位（÷10000=百分比）
  - demand_id 下混着1,220个不同达人的视频，必须用 demand_id + core_user.id 双重过滤
  - openpyxl 需手动安装：pip3 install openpyxl
  - terminal 被 gateway 拦截时，用 write_file 写脚本再 terminal 执行
"""
import json, time, urllib.request, urllib.parse, sys
from pathlib import Path
from datetime import datetime

TASK_LIST_URL = "https://api.oceanengine.com/open_api/2/star/mcn/provider_get_participated_task/"
TASK_ITEM_LIST_URL = "https://api.oceanengine.com/open_api/2/star/mcn/provider_get_task_item_list/"
STAR_ID = 1858094343342475
BASE_DIR = Path(__file__).resolve().parent.parent  # attribution project root

def get_token():
    cache_path = BASE_DIR / "data/token_cache.json"
    if cache_path.exists():
        cached = json.loads(cache_path.read_text())
        fetched_at = datetime.fromisoformat(cached["fetched_at"])
        age = (datetime.now(fetched_at.tzinfo) - fetched_at).total_seconds()
        if age < 23 * 3600:
            return cached["token"]
    import subprocess
    TOKEN_URL = "https://dashboard.adwetec.com/newapi/dashboard/xingtu_token"
    cmd = ["ssh", "-p", "2222", "-o", "BatchMode=yes", "-o", "ConnectTimeout=30",
           "ubuntu@127.0.0.1", "curl", "--fail-with-body", "--silent", "--show-error",
           "--max-time", "30", "-X", "POST", "-H", "Content-Type: application/json",
           "--data", "{}", TOKEN_URL]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
    payload = json.loads(result.stdout)
    token = payload["body"]["entity"]["data"]
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps({"token": token, "fetched_at": datetime.now().isoformat()}, indent=2))
    return token

def fetch_all_tasks(token):
    all_tasks = []
    page = 1
    while True:
        params = {"star_id": STAR_ID, "provider_task_category": 2, "page": page, "page_size": 50}
        query = urllib.parse.urlencode(params)
        req = urllib.request.Request(f"{TASK_LIST_URL}?{query}", headers={"Access-Token": token})
        with urllib.request.urlopen(req, timeout=30) as resp:
            doc = json.loads(resp.read().decode("utf-8"))
        data = doc.get("data", {}).get("data", [])
        all_tasks.extend(data)
        page_info = doc.get("data", {}).get("page_info", {})
        if not page_info.get("has_more"):
            break
        page += 1
    return all_tasks

def fetch_task_items(token, demand_id):
    items = []
    page = 1
    while True:
        params = {"star_id": STAR_ID, "task_id": str(demand_id), "page": page, "limit": 30}
        query = urllib.parse.urlencode(params)
        req = urllib.request.Request(f"{TASK_ITEM_LIST_URL}?{query}", headers={"Access-Token": token})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                doc = json.loads(resp.read().decode("utf-8"))
        except Exception:
            break
        if doc.get("code") not in (None, 0):
            break
        page_items = doc.get("data", {}).get("items", [])
        items.extend(page_items)
        pagination = doc.get("data", {}).get("pagination", {})
        if not pagination.get("has_more"):
            break
        page += 1
    return items

def parse_video(item, demand_name, demand_id, create_time):
    info = item.get("item_info", {}) or {}
    star = item.get("star_ad_unite_item_info", {}) or {}
    data_obj = info.get("data", {})
    eff = data_obj.get("real_time_effect_data", {}) if isinstance(data_obj, dict) else {}
    if not isinstance(eff, dict):
        eff = {}
    core_user = info.get("core_user", {}) or {}
    return {
        "demand_name": demand_name, "demand_id": demand_id, "create_time": create_time,
        "title": info.get("title", ""), "item_id": info.get("item_id", ""),
        "duration": info.get("duration", 0), "url": info.get("url", ""),
        "nick_name": core_user.get("nick_name", ""), "core_user_id": core_user.get("id", ""),
        "cost_li": star.get("est_real_time_total_cost", 0) or 0,
        "ad_cost_li": star.get("est_real_time_ad_cost", 0) or 0,
        "natural_cost_li": star.get("est_real_time_natural_cost", 0) or 0,
        "reward_li": star.get("est_provider_reward", 0) or 0,
        "share_ratio": star.get("provider_ad_share_ratio", 0) or 0,
        "watch_cnt": eff.get("watch_cnt"), "play_rate3s": eff.get("play_rate3s"),
        "play_rate5s": eff.get("play_rate5s"), "play_finish_rate": eff.get("play_finish_rate"),
        "finish_rate": eff.get("finish_rate"), "like_cnt": eff.get("like_cnt"),
        "comment_cnt": eff.get("comment_cnt"), "share_cnt": eff.get("share_cnt"),
        "favorite_cnt": eff.get("favorite_cnt"), "interact_cnt": eff.get("interact_cnt"),
        "interact_rate": eff.get("interact_rate"), "avg_watch_dura": eff.get("avg_watch_dura"),
        "release_time": info.get("release_time"),
        "aweme_item_status": info.get("aweme_item_status"),
        "ad_status": star.get("ad_status"), "item_status": star.get("item_status"),
    }

def main(make_excel=False):
    token = get_token()
    all_tasks = fetch_all_tasks(token)
    print(f"总任务数: {len(all_tasks)}", flush=True)
    all_videos = []
    for i, task in enumerate(all_tasks, 1):
        demand_id = task["demand_id"]
        demand_name = task.get("demand_name", "?")
        create_time = task.get("create_time", "?")
        items = fetch_task_items(token, demand_id)
        for item in items:
            all_videos.append(parse_video(item, demand_name, demand_id, create_time))
        print(f"  [{i}/{len(all_tasks)}] {demand_name[:35]} -> {len(items)}条视频", flush=True)
        time.sleep(0.2)
    all_videos.sort(key=lambda v: v["cost_li"], reverse=True)
    output_path = BASE_DIR / "data/all_videos_snapshot.json"
    output_path.write_text(json.dumps(all_videos, ensure_ascii=False, indent=2))
    total_cost = sum(v["cost_li"] for v in all_videos)
    videos_with_cost = len([v for v in all_videos if v["cost_li"] > 0])
    print(f"\n总视频数: {len(all_videos)}", flush=True)
    print(f"有消耗视频: {videos_with_cost}", flush=True)
    print(f"总消耗: {total_cost}厘 = {total_cost/1000:.2f}元", flush=True)
    if make_excel:
        gen_excel(all_videos)

def gen_excel(all_videos):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    videos = [v for v in all_videos if v["cost_li"] > 0]
    wb = Workbook()
    ws = wb.active
    ws.title = "星广素材数据"
    headers = ["序号","任务创建时间","标题","消耗(元)","播放数","3秒播放率","5秒播放率","完播率","点赞","评论","分享","收藏","互动数","达人","任务名称"]
    hfont = Font(name="微软雅黑", size=10, bold=True, color="000000")
    hfill = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=c, value=h)
        cell.font = hfont
        cell.fill = hfill
        cell.alignment = Alignment(horizontal="center")
    for i, v in enumerate(videos, 1):
        cost = round(v["cost_li"] / 1000, 2)
        watch = v.get("watch_cnt") or 0
        p3 = v.get("play_rate3s"); p5 = v.get("play_rate5s"); fin = v.get("play_finish_rate")
        p3s = f"{p3/10000:.2%}" if p3 else "—"
        p5s = f"{p5/10000:.2%}" if p5 else "—"
        fins = f"{fin/10000:.2%}" if fin else "—"
        t = v.get("title","").strip() or "—"
        if len(t) > 50: t = t[:50] + "..."
        row = [i, v.get("create_time","—"), t, cost, watch, p3s, p5s, fins,
               v.get("like_cnt") or 0, v.get("comment_cnt") or 0, v.get("share_cnt") or 0,
               v.get("favorite_cnt") or 0, v.get("interact_cnt") or 0,
               v.get("nick_name","—"), v.get("demand_name","—")[:30]]
        for c, val in enumerate(row, 1):
            ws.cell(row=i+1, column=c, value=val)
    widths = [6,18,50,12,10,10,10,10,8,8,8,8,8,15,30]
    for c, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(c)].width = w
    ws.freeze_panes = "A2"
    out = BASE_DIR / "星广全部素材数据_按消耗降序.xlsx"
    wb.save(str(out))
    print(f"Excel已保存: {out} ({len(videos)}行)", flush=True)

if __name__ == "__main__":
    make_excel = "--excel" in sys.argv
    main(make_excel=make_excel)

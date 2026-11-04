#!/usr/bin/env python3
# > 执行者：codex
"""update_state.py — STATE.json 程序写入器（LLM 无权写）
规则：review_result=PASS 才写 DONE；FAIL/BLOCKED 不允许修改状态。
LLM只能申请完成，程序决定完成。

用法:
  python3 update_state.py <项目目录> <NODE_ID> <PASS|FAIL>
  python3 update_state.py status <项目目录>          # 查看状态
  python3 update_state.py check <项目目录> <NODE_ID>  # 检查某节点是否DONE
"""
import json, os, sys, time

def state_path(proj):
    return os.path.join(proj, "STATE.json")

def load_state(proj):
    p = state_path(proj)
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except:
            return {}
    return {}

def save_state(proj, state):
    with open(state_path(proj), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def main():
    if len(sys.argv) < 3:
        print("用法: update_state.py write <项目目录> <NODE_ID> <PASS|FAIL> | status <项目目录> | check <项目目录> <NODE_ID>")
        sys.exit(3)
    cmd = sys.argv[1]
    proj = sys.argv[2]

    if cmd == "status":
        state = load_state(proj)
        print(json.dumps(state, ensure_ascii=False, indent=2))
        sys.exit(0)

    if cmd == "check":
        node = sys.argv[3]
        state = load_state(proj)
        nodes = state.get("nodes", {})
        if nodes.get(node, {}).get("status") == "DONE":
            print("DONE")
            sys.exit(0)
        print("NOT_DONE")
        sys.exit(1)

    # 写入模式: update_state.py write <proj> <NODE_ID> <PASS|FAIL>
    if cmd == "write":
        node = sys.argv[3]
        result = sys.argv[4].upper()
        state = load_state(proj)
        nodes = state.setdefault("nodes", {})

        if result == "PASS":
            # 只有 PASS 才允许写 DONE —— 程序决定完成
            nodes[node] = {"status": "DONE", "time": time.strftime('%Y-%m-%d %H:%M:%S')}
            state["current_node"] = node
            save_state(proj, state)
            print(f"✅ STATE更新: {node}=DONE（程序写入）")
            sys.exit(0)
        else:
            # FAIL/BLOCKED：不允许修改状态，保持原状
            print(f"⛔ {node} 未通过，状态不允许修改（当前: {nodes.get(node, {}).get('status', '未记录')}）")
            sys.exit(2)
    print("未知命令")
    sys.exit(3)

if __name__ == "__main__":
    main()

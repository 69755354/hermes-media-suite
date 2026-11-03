#!/usr/bin/env python3
"""
项目初始化工具 — 创建接力文档目录结构 + 状态锁 + 校验日志
用法:
  python3 scripts/project_init.py init <项目名> [总节点数]
  python3 scripts/project_init.py verify <项目名> <期望节点号>
  python3 scripts/project_init.py advance <项目名> <当前节点号> <输出文件> <内容>
"""
import json, os, hashlib, sys
from datetime import datetime

BASE = "/tmp/projects"

def init_project(name, total_nodes=17, mode="b"):
    path = f"{BASE}/{name}"
    os.makedirs(f"{path}/mode_a", exist_ok=True)
    os.makedirs(f"{path}/mode_b", exist_ok=True)
    lock = {
        "project": name, "current_node": 0, "status": "初始化",
        "previous_output": "", "checksum": "", "mode": mode,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "retry_count": 0, "total_nodes": total_nodes, "failed_nodes": []
    }
    with open(f"{path}/_状态锁.json", 'w') as f:
        json.dump(lock, f, indent=2, ensure_ascii=False)
    print(f"✅ 项目 [{name}] 初始化完成 ({total_nodes}节点, 模式{'A' if mode=='a' else 'B'})")

def verify(name, expected_node):
    lock_file = f"{BASE}/{name}/_状态锁.json"
    if not os.path.exists(lock_file):
        print(f"❌ 状态锁不存在，请先 init")
        return False
    with open(lock_file) as f:
        lock = json.load(f)
    if lock["current_node"] != expected_node:
        print(f"❌ 期望节点{expected_node}，当前{lock['current_node']}")
        return False
    if lock["previous_output"]:
        prev = f"{BASE}/{name}/{lock['previous_output']}"
        if not os.path.exists(prev):
            print(f"❌ 上游文件 {prev} 不存在")
            return False
    print(f"✅ 节点{expected_node} 可执行")
    return True

def advance(name, node_id, output_file, content):
    lock_file = f"{BASE}/{name}/_状态锁.json"
    with open(lock_file) as f:
        lock = json.load(f)
    doc_path = f"{BASE}/{name}/{output_file}"
    os.makedirs(os.path.dirname(doc_path), exist_ok=True)
    with open(doc_path, 'w') as f:
        f.write(content)
    lock["current_node"] = node_id + 1
    lock["previous_output"] = output_file
    lock["checksum"] = hashlib.sha256(content.encode()).hexdigest()
    lock["status"] = f"节点{node_id}完成"
    lock["timestamp"] = datetime.utcnow().isoformat() + "Z"
    lock["retry_count"] = 0
    with open(lock_file, 'w') as f:
        json.dump(lock, f, indent=2, ensure_ascii=False)
    print(f"✅ 节点{node_id} → 节点{node_id+1} 推进完成")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: project_init.py <init|verify|advance> <项目名> [参数...]")
        sys.exit(1)
    cmd, name = sys.argv[1], sys.argv[2]
    if cmd == "init":
        init_project(name, int(sys.argv[3]) if len(sys.argv) > 3 else 17,
                     sys.argv[4] if len(sys.argv) > 4 else "b")
    elif cmd == "verify":
        verify(name, int(sys.argv[3]))
    elif cmd == "advance":
        advance(name, int(sys.argv[3]), sys.argv[4], sys.argv[5] if len(sys.argv) > 5 else "")

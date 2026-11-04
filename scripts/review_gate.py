#!/usr/bin/env python3
# > 执行者：codex
"""review_gate.py — 评审门物理卡点检查
把盲评门/预检门/终审门从「软约束」变成「文件级物理拦截」。

用法:
  python3 review_gate.py check <项目目录> <gate> [--strict]

gate:
  node4_review  初稿评审门: 节点4_评审报告.md 存在且 PASS/≥60
  node12_pre    出片预检门: 节点10_提示词.md + 节点11_质检报告.md 存在且质检通过
  node15_final  终审门:     节点15_终审报告.md 存在且 PASS/≥68
  all           全部检查（交付前总闸）

返回码:
  0 = ALLOWED 放行
  1 = BLOCKED 缺文件
  2 = BLOCKED 分数不达标
  3 = BLOCKED 参数错误

物理性：agent 无法绕过——缺文件/不达标直接非0退出，调用方必须处理为终止。
"""
import os, re, sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
GUARD_DIR = os.environ.get("WORKFLOW_GUARD_DIR", os.path.join(REPO_ROOT, "guard"))
GUARD_LOG = os.path.join(GUARD_DIR, "security_alerts.log")
DATA_SOURCE_GATE = os.path.join(SCRIPTS_DIR, "data_source_gate.py")
UPDATE_STATE = os.path.join(SCRIPTS_DIR, "update_state.py")

def log_blocked(msg):
    os.makedirs(os.path.dirname(GUARD_LOG), exist_ok=True)
    with open(GUARD_LOG, "a") as f:
        f.write(f"[review_gate] {msg}\n")

def read_score(path, dim=None):
    """从评审报告读总分或单维分"""
    try:
        content = open(path, encoding="utf-8", errors="ignore").read()
    except:
        return None
    if "PASS" in content.upper() or "放行" in content:
        return 100  # 显式PASS标记视为达标
    # 尝试读「总分：XX」「综合得分：XX」「加权总分=XX」等多种格式
    for pat in [r"综合总分[：:\s=]+(\d+)", r"综合得分[：:\s=]+(\d+)", r"最终得分[：:\s=]+(\d+)", r"加权总分[=：:\s]+(\d+)", r"总分[：:\s=]+(\d+)", r"总分[（(].*?[)）][：:\s=]+(\d+)"]:
        m = re.search(pat, content)
        if m:
            return int(m.group(1))
    return None

def check_node3(proj):
    # 节点3 候选方向卡点（2026-08-07 新增）：选题必须先出候选方向记录，再定稿
    # 候选记录=内部文件 节点3_候选方向.md（不交付客户；SPEC 2026-08-04 只给最终选题+理由）
    p = os.path.join(proj, "节点3_候选方向.md")
    if not os.path.exists(p):
        log_blocked(f"BLOCKED node3_candidate: 缺 {p}——选题候选方向记录未生成（需≥2个方向）")
        return 1
    content = open(p, encoding="utf-8", errors="ignore").read()
    if len(content.strip()) < 50:
        log_blocked(f"BLOCKED node3_candidate: {p} 内容过短（<50字符），候选方向记录不完整")
        return 1
    candidates = re.findall(r"候选[一二三123]|方向[一二三123]|方案[一二三123]", content)
    if len(candidates) < 2:
        log_blocked(f"BLOCKED node3_candidate: {p} 候选方向不足（需≥2个，当前{len(candidates)}个）")
        return 1
    return 0

def check_node4(proj):
    # ① 三版产出检查（2026-08-07 新增物理卡点：节点4 主干=三版盲评）
    #    豁免：客户自备文案/微调场景 → 项目目录存在 _自备文案.flag 标记（节点0采集时写入）
    flag = os.path.join(proj, "_自备文案.flag")
    if not os.path.exists(flag):
        versions = [f for f in os.listdir(proj) if re.match(r"节点4_文案v[1-9]\.md$", f) and "_评审" not in f]
        if len(versions) < 3:
            log_blocked(f"BLOCKED node4_review: 三版产出缺失（需 节点4_文案v1/v2/v3，当前{len(versions)}个；客户自备文案场景在项目目录建 _自备文案.flag 豁免）")
            return 1
    # ② 评审报告检查（原有）
    p = os.path.join(proj, "节点4_评审报告.md")
    if not os.path.exists(p):
        log_blocked(f"BLOCKED node4_review: 缺 {p}")
        return 1
    score = read_score(p)
    if score is None:
        log_blocked(f"BLOCKED node4_review: {p} 无分数/PASS标记")
        return 2
    if score < 60:
        log_blocked(f"BLOCKED node4_review: 初稿{score}分 < 60")
        return 2
    return 0

def check_node12(proj):
    p10 = os.path.join(proj, "节点10_提示词.md")
    p11 = os.path.join(proj, "节点11_质检报告.md")
    if not os.path.exists(p10):
        log_blocked(f"BLOCKED node12_pre: 缺 {p10}")
        return 1
    if not os.path.exists(p11):
        log_blocked(f"BLOCKED node12_pre: 缺 {p11}")
        return 1
    qc = open(p11, encoding="utf-8", errors="ignore").read()
    if "不通过" in qc or "FAIL" in qc.upper():
        log_blocked(f"BLOCKED node12_pre: 质检不通过")
        return 2
    return 0

def check_node15(proj):
    p = os.path.join(proj, "节点15_终审报告.md")
    if not os.path.exists(p):
        log_blocked(f"BLOCKED node15_final: 缺 {p}")
        return 1
    score = read_score(p)
    if score is None:
        log_blocked(f"BLOCKED node15_final: {p} 无分数/PASS标记")
        return 2
    if score < 68:
        log_blocked(f"BLOCKED node15_final: 终审{score}分 < 68")
        return 2
    return 0

def main():
    if len(sys.argv) < 4 or sys.argv[1] != "check":
        print("用法: python3 review_gate.py check <项目目录> <gate|all>")
        sys.exit(3)
    proj = sys.argv[2]
    gate = sys.argv[3]
    if not os.path.isdir(proj):
        log_blocked(f"BLOCKED: 项目目录不存在 {proj}")
        sys.exit(1)

    # all=交付总闸：node4初稿评审 + node15终审
    # ⚠️ 不含 node12_pre：node12_pre 是「调Seedance出片前」的门，由guard在出片时单独调用；
    #    图文/口播/公众号分支不经过节点12，若进all会对这些分支误杀
    # all=交付总闸：node4初稿评审 + node15终审
    # ⚠️ 不含 node12_pre（出片前门，guard单独调用）
    gates = ["node4_review", "node4_body", "node15_final"] if gate == "all" else [gate]
    for g in gates:
        if g == "node4_body":
            import subprocess as _sp
            r = _sp.run(["python3", DATA_SOURCE_GATE, "check", proj, "node4_body"],
                        capture_output=True, text=True)
            code = 0 if r.returncode == 0 else 2
        elif g in ("node3_candidate", "node4_candidate"):
            code = check_node3(proj)
        elif g == "node3_strategy":
            # 2026-08-10 新增：打法策略前置门（节点3）
            code = 0
            fp = os.path.join(proj, "节点3_打法方案.md")
            if not os.path.exists(fp):
                print("BLOCKED:node3_strategy:缺节点3_打法方案.md")
                log_blocked("BLOCKED node3_strategy: 缺节点3_打法方案.md")
                sys.exit(2)
            content3 = open(fp, encoding="utf-8", errors="ignore").read()
            required = ["平台组合", "内容配比", "阶段节奏", "投流策略", "变现方式"]
            missing = [k for k in required if k not in content3]
            if missing:
                print(f"BLOCKED:node3_strategy:打法方案缺关键字段: {missing}")
                log_blocked(f"BLOCKED node3_strategy: 缺字段 {missing}")
                sys.exit(2)
        elif g in ("node4_review", "node5_review"):
            code = check_node4(proj)
            # 2026-08-09 新增：进节点5前必须预读 huoshan 分镜方法论
            if code == 0:
                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                from codex_preload_manifest import check_node_preload
                kb = check_node_preload(proj, "5")
                if kb:
                    for p in kb[:5]:
                        print(f"BLOCKED:preload_5: {p}")
                        log_blocked(f"BLOCKED preload_5: {p}")
                    code = 2
        elif g in ("node12_pre", "node13_pre"):
            code = check_node12(proj)
            # 2026-08-09 新增：出片前必须预读 seedance 模板库 + 合规红线
            if code == 0:
                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                from codex_preload_manifest import check_node_preload
                kb = check_node_preload(proj, "10")
                kb += check_node_preload(proj, "11")
                if kb:
                    for p in kb[:5]:
                        print(f"BLOCKED:preload_10_11: {p}")
                        log_blocked(f"BLOCKED preload_10_11: {p}")
                    code = 2
        elif g == "node15_final":
            code = check_node15(proj)
        else:
            print(f"UNKNOWN_GATE:{g}")
            sys.exit(3)
        if code != 0:
            print(f"BLOCKED:{g}:{'缺文件' if code==1 else '不达标'}")
            sys.exit(code)
        # PASS → 程序更新STATE（LLM无权写，只有review_gate PASS才写DONE）
        import subprocess
        node_map = {
            "node4_review": "NODE_04",
            "node12_pre": "NODE_12",
            "node15_final": "NODE_15",
        }
        if g in node_map:
            subprocess.run(
                [sys.executable, UPDATE_STATE, "write", proj, node_map[g], "PASS"],
                capture_output=True, text=True)
    print("ALLOWED")
    sys.exit(0)

if __name__ == "__main__":
    main()

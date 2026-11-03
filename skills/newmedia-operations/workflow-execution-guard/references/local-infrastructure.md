# Workflow Execution Guard

> Pre-flight checklist loaded before every video production task.

## Pre-Flight Check (every time)

```plaintext
□ Loaded local-infrastructure.md? (huoshan or shuziren skill)
□ Scanned running services: ss -tlnp | grep -E '1888|5678|8888|8899|9222'
□ Checked Helper API is alive: `systemctl status helper-api` 或 `curl -s -X POST http://localhost:1888/`
□ Verified current wiki/concepts/ contains the docs needed for this node
□ Cross-referenced SKILL.md calling docs against actual files on disk
□ Checked wiki index at `/home/ubuntu/wiki/index.md` for current doc list (22+ docs, not 25 after merges)
```

## Infrastructure Self-Correction Rule

If you search for a document referenced in `**调用文档：**` and it doesn't exist:
1. Check if it moved to `wiki/concepts/` (new docs go there now)
2. Check if it was renamed (subagent may have created it with a variant name)
3. If truly missing → tell the user it doesn't exist, DON'T fabricate content
4. Update the SKILL.md reference to point to the actual file or remove it

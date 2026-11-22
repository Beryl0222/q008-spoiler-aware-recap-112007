"""生成续播回顾：播放器载荷 + 编辑预览。

用法：
    python3 build_recap.py data/records.json            # 可读的编辑预览与播放器载荷
    python3 build_recap.py data/records.json --json     # 全部 JSON
    python3 build_recap.py data/records.json --player   # 仅播放器载荷（可给该观众看的内容）
"""

import argparse
import json
from pathlib import Path

from inspect_records import load_records
from recap_engine import build_editor_preview, run_batch


def render_request(rid, view):
    lines = []
    header = f"续播 {rid}（观众 {view['viewer']} → {view['clip']} @{view['offset']}"
    if view["question"]:
        header += f"，问题：{view['question']}"
    lines.append(header + "）")
    lines.append("  [播放记录] " + "；".join(
        f"{p['id']}({p['clip']}) {p['status']}" for p in view["playbacks"]))
    lines.append("  [已知事实]")
    for fid, info in view["known"].items():
        bases = "；".join(b["desc"] for b in info["bases"])
        lines.append(f"    {fid} {info['summary']}（依据 {bases}）")
    if view["associations"]:
        lines.append("  [资料关联]")
        for entry in view["associations"]:
            lines.append(f"    {entry['mapping']} {entry['a']}↔{entry['b']} {entry['status']}")
            if entry["edit_view"]:
                lines.append(f"      修订记载：{entry['edit_view']}")
            for fact in entry["facts"]:
                if fact["before"] != fact["after"]:
                    change = "计入已知 → 不计入" if not fact["after"] else "不计入 → 计入"
                else:
                    change = "仍计入已知" if fact["after"] else "仍不计入"
                lines.append(f"      {fact['fact']} {fact['summary']}：{change}")
            if not entry["facts"]:
                lines.append("      对该观众的已知事实无影响")
    lines.append(f"  [解释·本次] 「{view['current_recap']}」"
                 f"（{len(view['current_recap'])}/{view['limit']} 码点）")
    lines.append("  [解释·上一份]")
    for c in view["previous_components"]:
        mark = "✓" if c["verdict"] == "保留" else "✗"
        lines.append(f"    {mark} {c['verdict']}「{c['phrase']}」：{c['reason']}")
    lines.append("  [跳转·本次]")
    if view["current_catchup"]:
        for j in view["current_catchup"]:
            checks = "；".join(j["checks"])
            lines.append(f"    {j['clip']} {j['start']}–{j['end']}"
                         f"（补 {j['fills']} {j['fills_summary']}；{checks}）")
    else:
        lines.append("    （零段）")
    lines.append("  [跳转·上一份]")
    for j in view["previous_catchup"]:
        mark = "✓" if j["verdict"] == "保留" else "✗"
        lines.append(f"    {mark} {j['verdict']} {j['clip']} {j['start']}–{j['end']}：{j['reason']}")
    for gap in view["unfillable"]:
        lines.append(f"  [无法安全跳转] {gap['fact']}：{gap['reason']}")
    for notice in view["notices"]:
        lines.append(f"  [播放器提示] {notice}")
    lines.append("  [播放器载荷] "
                 + json.dumps(view["player"], ensure_ascii=False))
    return lines


def main():
    parser = argparse.ArgumentParser(description="生成跨剪辑断点的无剧透回顾")
    parser.add_argument("path", type=Path, help="资料文件路径")
    parser.add_argument("--json", action="store_true", help="全部输出 JSON")
    parser.add_argument("--player", action="store_true", help="只输出播放器载荷")
    args = parser.parse_args()
    records = load_records(args.path)

    if args.player:
        batch = run_batch(records, apply_changes=True)
        payload = {rid: view["player"] for rid, view in batch["requests"].items()}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    preview = build_editor_preview(records)
    if args.json:
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        return

    print("======== 改动发布 ========")
    for change in preview["changes"]:
        print(f"  {change}")
    for rid, view in preview["requests"].items():
        print()
        print("======== 编辑预览 ========")
        for line in render_request(rid, view):
            print(line)


if __name__ == "__main__":
    main()

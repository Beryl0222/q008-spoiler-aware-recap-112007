"""跨剪辑断点的无剧透回顾引擎。

通用部分：读取资料状态、按实际呈现核对观看依据、计算已知事实、判断剧透
安全、组成回顾短稿、挑选补看区间；并在 删除播放 / 修订场记 的改动发布后，
分别重新核对已预生成的回顾文案与跳转位置。剧情资料在 knowledge.py。

两种资料状态：
- apply_changes=False：改动发布前（用于重现已预生成的上一批回顾与跳转）；
- apply_changes=True：应用改动后的当前状态。

文案与跳转分别核对：原来适用的文字不能为已经含有剧透的跳转背书，
还合适的跳转也不能仅因同批文案作废而被一并删去。
"""

from dataclasses import dataclass

import knowledge

GENERIC_TERMS = {"她", "他", "那人"}
TRACK_NAMES = {"text": "台词", "screen": "镜头"}
NOTICE_KEY_GAP = "有一处关键前因在当前版本续播点之前没有可安全跳转的位置。"


# ---------- 资料状态 ----------

class State:
    """某一资料状态；apply_changes=True 表示应用改动发布后的当前状态。"""

    def __init__(self, records, apply_changes):
        self.records = records
        self.apply_changes = apply_changes
        self.clips = {c["id"]: c for c in records["cuts"]}
        self.removed_playbacks = []
        self.revised_mappings = []
        if apply_changes:
            for change in records.get("changes", []):
                if change["kind"] == "删除播放":
                    # 删除事件仅撤销所引用的那份播放记录
                    self.removed_playbacks.append(change["target"])
                elif change["kind"] == "修订场记":
                    self.revised_mappings.append(change["target"])

    def active_playbacks(self, viewer):
        return [p for p in self.records["playback"]
                if p["viewer"] == viewer and p["id"] not in self.removed_playbacks]

    def directives(self, mapping_id):
        interp = knowledge.MAPPING_INTERPRETATIONS.get(mapping_id, {})
        key = "edit_view" if mapping_id in self.revised_mappings else "note"
        return interp.get(key, [])

    def line_kind(self, clip, track, line):
        return knowledge.LINE_KINDS.get((clip, track, line), "正片")


# ---------- 事实呈现 ----------

@dataclass(frozen=True)
class Presentation:
    """事实的一次呈现；track/line 为 None 表示场记原登记的整段对应。"""

    fact: str
    clip: str
    track: str | None
    line: int | None
    source: str  # 登记 / 文本一致(Mx) / 场记原登记(Mx) / 场记修订(Mx)


def line_span(clip_row, track, idx):
    row = clip_row[track][idx]
    return row[0], row[1]


def line_text(clip_row, track, idx):
    row = clip_row[track][idx]
    return row[3] if track == "text" else row[2]


def resolve_presentations(state):
    """汇总事实的全部呈现：知识层登记 + 场记关联的文本核验 + 场记指令。"""
    pres = []

    def add(fact, clip, track, line, source):
        item = Presentation(fact, clip, track, line, source)
        if item not in pres:
            pres.append(item)

    for fid, fact in knowledge.FACTS.items():
        for clip, track, line in fact["presentations"]:
            add(fid, clip, track, line, "登记")

    # mapping 是场记登记的候选关联：逐条用实际台词/镜头文字核验。
    # 同名片段只留住半句的，核验不会通过，不能因为进入过该片段就算听完。
    for mapping in state.records["mapping"]:
        for fid, fact in knowledge.FACTS.items():
            phrase = fact.get("key_phrase")
            if not phrase:
                continue
            for src, dst in ((mapping["a"], mapping["b"]), (mapping["b"], mapping["a"])):
                if not any(p.fact == fid and p.clip == src for p in pres):
                    continue
                dst_clip = state.clips[dst]
                for track in ("text", "screen"):
                    for idx in range(len(dst_clip[track])):
                        if phrase in line_text(dst_clip, track, idx):
                            add(fid, dst, track, idx, f"文本一致({mapping['id']})")

    # 场记指令：原登记按整段对应；修订后按 edit_view 收窄到具体行
    for mapping in state.records["mapping"]:
        for directive in state.directives(mapping["id"]):
            if directive["op"] == "present":
                add(directive["fact"], directive["clip"], directive["track"],
                    directive["line"], f"场记修订({mapping['id']})")
            elif directive["op"] == "present_clip":
                add(directive["fact"], directive["clip"], None, None,
                    f"场记原登记({mapping['id']})")
    return pres


# ---------- 实际呈现 ----------

def merge_intervals(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def presented_lines(state, viewer):
    """观众实际播全的台词/镜头文字：played 是实际呈现过的区间，
    进入过片段不算，要完整覆盖该行区间才算看到。"""
    presented = {}
    for playback in state.active_playbacks(viewer):
        clip = state.clips[playback["clip"]]
        merged = merge_intervals(playback["played"])
        for track in ("text", "screen"):
            for idx, row in enumerate(clip[track]):
                if any(s <= row[0] and row[1] <= e for s, e in merged):
                    presented[(playback["clip"], track, idx)] = playback["id"]
    return presented


@dataclass
class Basis:
    playback: str
    presentation: Presentation

    def describe(self, state):
        p = self.presentation
        if p.line is None:
            return f"{self.playback}→{p.clip} 整段（{p.source}）"
        start, end = line_span(state.clips[p.clip], p.track, p.line)
        return (f"{self.playback}→{p.clip} {TRACK_NAMES[p.track]}"
                f"[{start},{end}]（{p.source}）")


def known_facts(state, presentations, presented):
    """按实际呈现的台词或镜头文字确认观众看到了哪条事实。

    番外呈现的独家解释不能代替正片发生过的事，不计入已知。
    """
    known = {}
    for p in presentations:
        if p.line is None:
            # 场记原登记的整段对应：该段任一台词播全即算接触
            clip = state.clips[p.clip]
            for idx in range(len(clip["text"])):
                playback = presented.get((p.clip, "text", idx))
                if playback:
                    known.setdefault(p.fact, []).append(Basis(playback, p))
            continue
        if state.line_kind(p.clip, p.track, p.line) == "番外":
            continue
        playback = presented.get((p.clip, p.track, p.line))
        if playback:
            known.setdefault(p.fact, []).append(Basis(playback, p))
    return known


# ---------- 剧透安全 ----------

def fact_positions(state, presentations, fact_id, version):
    """事实在指定版本时间线上“确立”的位置（预告/番外不算确立）。"""
    positions = []
    for p in presentations:
        if p.fact != fact_id:
            continue
        if p.line is not None and state.line_kind(p.clip, p.track, p.line) != "正片":
            continue
        clip = state.clips[p.clip]
        start, end = (0, 0) if p.line is None else line_span(clip, p.track, p.line)
        if clip["version"] == version:
            positions.append((clip["airing_order"], start, end))
            continue
        # 另一版的等价独立交代，经场记关联换算到当前版本的位置
        for mapping in state.records["mapping"]:
            for a, b in ((mapping["a"], mapping["b"]), (mapping["b"], mapping["a"])):
                if a == p.clip and state.clips[b]["version"] == version:
                    positions.append((state.clips[b]["airing_order"], start, end))
    return positions


def is_safe(state, presentations, fact_id, resume_clip, offset):
    """续播点之前已在正片确立的事实，才不会把续播后才知道的剧情说破。"""
    airing = state.clips[resume_clip]["airing_order"]
    version = state.clips[resume_clip]["version"]
    return any(pos_air < airing or (pos_air == airing and pos_end <= offset)
               for pos_air, _start, pos_end
               in fact_positions(state, presentations, fact_id, version))


def tainted_by(state, presentations, clip, start, end, resume_clip, offset):
    """区间若与未在续播点前确立的呈现重叠，会带出续播后才知道的剧情。"""
    for p in presentations:
        if p.clip != clip or p.line is None:
            continue
        s, e = line_span(state.clips[clip], p.track, p.line)
        if start < e and s < end and not is_safe(
                state, presentations, p.fact, resume_clip, offset):
            return p.fact
    return None


# ---------- 称呼 ----------

def seen_terms(state, presentations, presented):
    """观众实际见过的称呼：播全台词的说话人 + 播全内容里出现过的称谓。

    番外换了剪辑作者代号，其中的称呼不可替代正片。
    """
    terms = set()
    for clip_id, track, idx in presented:
        if track == "text":
            terms.add(state.clips[clip_id][track][idx][2])
        if state.line_kind(clip_id, track, idx) == "番外":
            continue
        for p in presentations:
            if p.clip == clip_id and p.track == track and p.line == idx:
                terms.update(knowledge.FACTS[p.fact]["terms"])
    return terms


def resume_anchor_terms(state, presentations, resume_clip, offset):
    """续播点所接那句台词里的称呼，可用于说明能接到哪里。"""
    terms = set()
    for p in presentations:
        if p.clip != resume_clip or p.line is None:
            continue
        start, end = line_span(state.clips[resume_clip], p.track, p.line)
        if start <= offset < end:
            terms.update(knowledge.FACTS[p.fact]["terms"])
    return terms


def pick_phrase(fact_id, allowed_terms):
    for phrase in knowledge.PHRASES.get(fact_id, []):
        if set(phrase["terms"]) <= allowed_terms:
            return phrase["text"]
    return None


# ---------- 补看区间 ----------

def select_catchup(state, presentations, gaps, key_set, resume_clip, offset, budget):
    """在观众给的时间窗口内挑选补看区间：能填的关键前因优先，允许零段。

    候选区间必须在当前版本续播点之前；既补缺口又带出续播后剧情的区间
    不可用，需另找能独立播的安全片段，找不到就记为无法安全跳转。
    """
    chosen, unfillable = [], []
    total = 0
    for fid in sorted(gaps, key=lambda f: f not in key_set):
        options = []
        for p in presentations:
            if p.fact != fid or p.line is None:
                continue
            if state.clips[p.clip]["version"] != state.clips[resume_clip]["version"]:
                continue  # 当前版本
            start, end = line_span(state.clips[p.clip], p.track, p.line)
            airing = state.clips[p.clip]["airing_order"]
            resume_airing = state.clips[resume_clip]["airing_order"]
            if not (airing < resume_airing or (airing == resume_airing and end <= offset)):
                continue  # 续播点之前
            spoiler = tainted_by(state, presentations, p.clip, start, end,
                                 resume_clip, offset)
            options.append({"clip": p.clip, "start": start, "end": end,
                            "spoiler": spoiler})
        picked = None
        for option in sorted((o for o in options if o["spoiler"] is None),
                             key=lambda o: o["end"] - o["start"]):
            if total + (option["end"] - option["start"]) <= budget:
                picked = option
                break
        if picked:
            total += picked["end"] - picked["start"]
            if not any(c["clip"] == picked["clip"] and c["start"] == picked["start"]
                       for c in chosen):
                chosen.append({**picked, "fact": fid, "cum": total})
        else:
            unfillable.append((fid, options))
    return chosen, total, unfillable


def unfillable_reason(state, fid, options, budget):
    """给编辑看的原因（可点名剧透事实）；播放器只收到不含内容的提示。"""
    if not options:
        return "当前版本续播点之前没有该前因的呈现"
    reasons = []
    for o in options:
        label = f"{o['clip']}[{o['start']},{o['end']}]"
        if o["spoiler"]:
            summary = knowledge.FACTS[o["spoiler"]]["summary"]
            reasons.append(f"{label} 会带出续播后才知道的剧情"
                           f"（{o['spoiler']}：{summary}）")
        if o["end"] - o["start"] > budget:
            reasons.append(f"{label} 时长 {o['end'] - o['start']}ms "
                           f"超出补看窗口 {budget}ms")
    return "；".join(reasons)


# ---------- 回顾短稿 ----------

def assemble(components):
    groups = []
    for role in ("anchors", "answers", "marker"):
        phrases = [c["phrase"] for c in components[role]]
        if phrases:
            groups.append("，".join(phrases))
    return ("；".join(groups) + "。") if groups else ""


def enforce_limit(components, limit):
    """限长以 Unicode 码点计算（含标点）；超限时先减次要锚点，不动答案本身。"""
    components = {role: list(items) for role, items in components.items()}
    while True:
        text = assemble(components)
        if len(text) <= limit:
            return text, components
        for role in ("anchors", "marker", "answers"):
            if components[role]:
                components[role].pop()
                break
        else:
            return "", components


def build_request_view(state, presentations, request):
    viewer = request["viewer"]
    clip, offset, limit = request["clip"], request["offset"], request["limit"]
    budget = request.get("catchup_ms", 0)
    presented = presented_lines(state, viewer)
    known = known_facts(state, presentations, presented)
    ctx = knowledge.RESUME_CONTEXT.get(clip, {})
    allowed = (seen_terms(state, presentations, presented)
               | resume_anchor_terms(state, presentations, clip, offset)
               | GENERIC_TERMS)

    def usable(fid):
        if knowledge.FACTS[fid]["nature"] == "误会":
            return False  # 角色误会不会当作真相写入回顾
        return fid in known and is_safe(state, presentations, fid, clip, offset)

    # 续播所需的前因：关键前因 + 本片段续播点之前的铺垫 + 问题答案
    question = request.get("question")
    pattern = None
    if question:
        for candidate in ctx.get("questions", []):
            if all(k in question for k in candidate["keywords"]):
                pattern = candidate
                break
    answer_facts = list(pattern["answer_facts"]) if pattern else []
    supplement = []
    for p in presentations:
        if p.clip == clip and p.line is not None:
            _s, end = line_span(state.clips[clip], p.track, p.line)
            if end <= offset and p.fact not in supplement:
                supplement.append(p.fact)
    key_set = set(ctx.get("key_antecedents", []))
    required = list(dict.fromkeys(
        ctx.get("key_antecedents", []) + supplement + answer_facts))
    gaps = [fid for fid in required if not usable(fid)]

    chosen, total_ms, unfillable = select_catchup(
        state, presentations, gaps, key_set, clip, offset, budget)

    # 回顾围绕续播所需的来龙去脉，只解释观众已有观看依据的部分
    anchors = [fid for fid in ctx.get("orient_facts", [])
               if usable(fid) and fid not in answer_facts]
    answers = [fid for fid in answer_facts if usable(fid)]
    components = {"anchors": [], "answers": [], "marker": []}
    for fid in anchors:
        phrase = pick_phrase(fid, allowed)
        if phrase:
            components["anchors"].append(
                {"fact": fid, "phrase": phrase, "role": "anchor"})
    for fid in answers:
        phrase = pick_phrase(fid, allowed)
        if phrase:
            components["answers"].append(
                {"fact": fid, "phrase": phrase, "role": "answer"})
    key_gaps = [fid for fid in gaps if fid in key_set]
    if key_gaps or (pattern and not answers):
        # 缺关键前因：用已见过的称呼说明能接到哪里，不在文案里说破
        marker = ctx.get("gap_marker")
        if marker and set(marker["terms"]) <= allowed:
            text = marker["text"] + ("，可补看" if chosen else "")
            components["marker"].append({"fact": None, "phrase": text, "role": "gap"})
    recap, components = enforce_limit(components, limit)

    notices = []
    unfillable_view = []
    for fid, options in unfillable:
        unfillable_view.append({
            "fact": fid,
            "key": fid in key_set,
            "reason": unfillable_reason(state, fid, options, budget),
        })
        if fid in key_set:
            notices.append(NOTICE_KEY_GAP)

    flat = components["anchors"] + components["answers"] + components["marker"]
    catchup_view = []
    for c in chosen:
        dur = c["end"] - c["start"]
        catchup_view.append({
            "clip": c["clip"], "start": c["start"], "end": c["end"],
            "fills": c["fact"],
            "fills_summary": knowledge.FACTS[c["fact"]]["summary"],
            "checks": ["在续播点之前", "不含续播后揭晓内容",
                       f"时长 {dur}ms，累计 {c['cum']}ms ≤ {budget}ms"],
        })
    hint = (f"可补看 {len(chosen)} 段（共 {total_ms / 1000:g} 秒）"
            if chosen else None)

    known_view = {
        fid: {
            "summary": knowledge.FACTS[fid]["summary"],
            "bases": [{"playback": b.playback, "source": b.presentation.source,
                       "clip": b.presentation.clip, "track": b.presentation.track,
                       "line": b.presentation.line,
                       "desc": b.describe(state)} for b in bases],
        } for fid, bases in known.items()
    }
    playbacks = []
    for p in state.records["playback"]:
        if p["viewer"] != viewer:
            continue
        removed = p["id"] in state.removed_playbacks
        playbacks.append({"id": p["id"], "clip": p["clip"],
                          "status": "已删除" if removed else "有效"})
    player = {
        "resume": {"clip": clip, "offset": offset},
        "recap": recap,
        "catchup": [{"clip": c["clip"], "start": c["start"], "end": c["end"]}
                    for c in chosen],
        "hint": hint,
        "notices": notices,
    }
    return {
        "viewer": viewer, "clip": clip, "offset": offset, "question": question,
        "limit": limit, "catchup_ms": budget,
        "playbacks": playbacks,
        "known": known_view,
        "components": flat,
        "recap": recap,
        "catchup": catchup_view,
        "catchup_total_ms": total_ms,
        "unfillable": unfillable_view,
        "notices": notices,
        "player": player,
    }


def run_batch(records, apply_changes):
    """对全部续播请求生成一批回顾与跳转。"""
    state = State(records, apply_changes)
    presentations = resolve_presentations(state)
    return {
        "state": state,
        "presentations": presentations,
        "requests": {r["id"]: build_request_view(state, presentations, r)
                     for r in records["resume"]},
    }


# ---------- 改动后的重新核对 ----------

def describe_change(change):
    if change["kind"] == "删除播放":
        return (f"{change['id']} 删除播放 {change['target']}（{change['viewer']}）："
                f"仅撤销该份播放记录")
    if change["kind"] == "修订场记":
        return f"{change['id']} 修订场记 {change['target']}：{change.get('edit_view', '')}"
    return f"{change['id']} {change['kind']} {change['target']}"


def invalidation_reason(pre, post, request_id, component):
    """说明上一份回顾中该断言为什么失效。"""
    fid = component["fact"]
    if fid is None:
        return "缺口提示随已知事实变化而失效"
    viewer = post["requests"][request_id]["viewer"]
    pre_bases = pre["requests"][request_id]["known"].get(fid, {}).get("bases", [])
    post_state = post["state"]
    for base in pre_bases:
        if base["playback"] in post_state.removed_playbacks:
            change_id = next(
                (c["id"] for c in post_state.records.get("changes", [])
                 if c["kind"] == "删除播放" and c["target"] == base["playback"]),
                "删除播放")
            return f"观看依据 {base['playback']} 已被 {change_id} 删除播放撤销"
    for base in pre_bases:
        if base["source"].startswith("场记原登记"):
            mid = base["source"][base["source"].find("(") + 1:base["source"].find(")")]
            if mid in post_state.revised_mappings:
                spans = []
                for p in post["presentations"]:
                    if p.fact == fid and p.source == f"场记修订({mid})":
                        start, end = line_span(post_state.clips[p.clip],
                                               p.track, p.line)
                        spans.append(f"{p.clip} [{start},{end}]")
                where = "、".join(spans) or "无"
                return (f"场记关联 {mid} 已修订：等价呈现收窄为 {where}，"
                        f"{viewer} 未播到")
    return "当前资料状态下不再成立"


def association_entries(pre, post, request_id):
    """资料关联的保留/失效：场记关联为这位观众的已知事实提供过什么依据。"""
    post_state = post["state"]
    pre_known = pre["requests"][request_id]["known"]
    post_known = post["requests"][request_id]["known"]
    entries = []
    for mapping in post_state.records["mapping"]:
        mid = mapping["id"]
        related = {}
        for fid in set(pre_known) | set(post_known):
            sources = [b["source"] for b in pre_known.get(fid, {}).get("bases", [])]
            sources += [b["source"] for b in post_known.get(fid, {}).get("bases", [])]
            if any(s.endswith(f"({mid})") for s in sources):
                related[fid] = {"before": fid in pre_known, "after": fid in post_known}
        revised = mid in post_state.revised_mappings
        if not related and not revised:
            continue
        change = next((c for c in post_state.records.get("changes", [])
                       if c["kind"] == "修订场记" and c["target"] == mid), None)
        entries.append({
            "mapping": mid, "a": mapping["a"], "b": mapping["b"],
            "status": f"已修订（{change['id']}）" if change else "未变",
            "edit_view": change.get("edit_view") if change else None,
            "facts": [{"fact": fid, "summary": knowledge.FACTS[fid]["summary"],
                       **flags} for fid, flags in sorted(related.items())],
        })
    return entries


def reconcile_request(pre, post, request_id):
    """同一份回顾的文案与跳转分别重新核对。"""
    pre_view = pre["requests"][request_id]
    post_view = post["requests"][request_id]
    previous_components = []
    for c in pre_view["components"]:
        still = any(pc["fact"] == c["fact"] and pc["phrase"] == c["phrase"]
                    for pc in post_view["components"])
        if still:
            verdict, reason = "保留", "观看依据仍然有效"
        else:
            verdict = "作废"
            reason = invalidation_reason(pre, post, request_id, c)
        previous_components.append({**c, "verdict": verdict, "reason": reason})
    previous_catchup = []
    for j in pre_view["catchup"]:
        still = any(pj["clip"] == j["clip"] and pj["start"] == j["start"]
                    and pj["end"] == j["end"] for pj in post_view["catchup"])
        if still:
            verdict = "保留"
            reason = "独立复核通过（续播点之前／不含续播后揭晓内容／时长在窗口内）；同批文案作废不牵连仍安全的跳转"
        else:
            verdict, reason = "作废", "当前资料状态下该区间不再安全或不再需要"
        previous_catchup.append({**j, "verdict": verdict, "reason": reason})
    return {
        "viewer": post_view["viewer"], "clip": post_view["clip"],
        "offset": post_view["offset"], "question": post_view["question"],
        "playbacks": post_view["playbacks"],
        "known": post_view["known"],
        "associations": association_entries(pre, post, request_id),
        "current_components": post_view["components"],
        "current_recap": post_view["recap"],
        "limit": post_view["limit"],
        "previous_components": previous_components,
        "current_catchup": post_view["catchup"],
        "catchup_ms": post_view["catchup_ms"],
        "catchup_total_ms": post_view["catchup_total_ms"],
        "previous_catchup": previous_catchup,
        "unfillable": post_view["unfillable"],
        "notices": post_view["notices"],
        "player": post_view["player"],
    }


def build_editor_preview(records):
    """改动发布后重跑两批：上一份（改动前）与当前（改动后），逐项核对。"""
    pre = run_batch(records, apply_changes=False)
    post = run_batch(records, apply_changes=True)
    return {
        "changes": [describe_change(c) for c in records.get("changes", [])],
        "requests": {rid: reconcile_request(pre, post, rid)
                     for rid in post["requests"]},
    }

"""《纸鸢局》剧情知识层（场记核定）。

recap_engine 是通用引擎；本文件是这部剧的具体资料：

- LINE_KINDS：逐行标注 正片 / 预告 / 番外。预告与番外的呈现不在正片时间线上
  “确立”事实；番外独有的解释不能代替正片发生过的事。
- FACTS：剧情事实。presentations 以 (clip, track, line) 引用 records.json 的
  台词与镜头文字，不复制区间，避免与原始资料漂移。nature=误会 的事实只是
  角色当时的说法（后来会被揭晓推翻），不得当作真相写进回顾。terms 是断言
  该事实时要用到的称呼。
- CHARACTERS：人物各自知道的事，用于核对误会与知情。
- RESUME_CONTEXT：各续播片段的关键前因、场景人物、可答问题与缺口提示语。
- MAPPING_INTERPRETATIONS：场记关联（mapping）在 原登记(note) 与
  修订后(edit_view) 两种状态下的机器可读解释。修订场记的改动发布后，
  引擎改用 edit_view 解释重新核对。
- PHRASES：回顾短句模板。每个短句声明所需称呼；观众没见过的称呼不得使用。
"""

LINE_KINDS = {
    ("A01", "screen", 1): "预告",   # “那一夜的真相在后篇”
    ("A02", "screen", 1): "预告",   # “下集预告：染坊东主正是石绘的姐姐。”
    ("B02", "screen", 0): "番外",   # “轻剪番外 江边设局”
}

FACTS = {
    "F_kite_at_door": {
        "summary": "门口那人是纸鸢客",
        "nature": "剧情",
        "key_phrase": "门口那人是纸鸢客",
        "terms": ["纸鸢客"],
        "presentations": [("A01", "text", 0)],
    },
    "F_half_token": {
        "summary": "石绘只见到半枚竹牌",
        "nature": "剧情",
        "key_phrase": "半枚竹牌",
        "terms": ["竹牌"],
        # 轻剪同名片段只留住后半句，此事实在 B01 没有呈现
        "presentations": [("A01", "text", 1)],
    },
    "M_misdeliver": {
        "summary": "石绘说门口那人未必是替阿遥送信的",
        "nature": "误会",  # 后来的揭晓（F_identity）推翻了它
        "key_phrase": "未必是替你送信",
        "terms": [],
        "corrected_by": "F_identity",
        "presentations": [("A01", "text", 1)],
    },
    "F_old_ticket": {
        "summary": "旧票写有南门",
        "nature": "剧情",
        "key_phrase": "南门",
        "terms": ["南门"],
        "presentations": [("A01", "screen", 0)],
    },
    "F_token_half": {
        "summary": "竹牌另一半在染坊",
        "nature": "剧情",
        "key_phrase": "竹牌另一半在染坊",
        "terms": ["竹牌", "染坊"],
        "presentations": [("A02", "text", 0)],
    },
    "F_blueline_mark": {
        "summary": "蓝线内侧有石绘的记号",
        "nature": "剧情",
        "key_phrase": "蓝线内侧有我的记号",
        "terms": ["蓝线"],
        "presentations": [("A02", "text", 1)],
    },
    "F_dyehouse_name": {
        "summary": "染坊名为青井染坊",
        "nature": "剧情",
        "key_phrase": "青井染坊",
        "terms": ["青井染坊", "染坊"],
        "presentations": [("A02", "screen", 0)],
    },
    "F_sister": {
        "summary": "染坊东主是石绘的姐姐",
        "nature": "剧情",
        "key_phrase": "石绘的姐姐",
        "terms": ["姐姐"],
        "presentations": [
            ("A02", "screen", 1),  # 预告：不在正片确立
            ("A05", "text", 0),    # 正片揭晓
        ],
    },
    "F_identity": {
        "summary": "石绘就是昨夜交信的人（纸鸢客）",
        "nature": "剧情",
        "key_phrase": "昨夜交信",
        "terms": ["纸鸢客"],
        "presentations": [
            ("A03", "text", 0),
            ("A03", "text", 1),
        ],
    },
    "F_token_returned": {
        "summary": "她先前把竹牌送回那家染坊",
        "nature": "剧情",
        "key_phrase": "把竹牌送回",
        "terms": ["竹牌", "染坊"],
        "presentations": [("A04", "text", 0)],
    },
    "F_return_plan": {
        "summary": "她说先回染坊",
        "nature": "剧情",
        "key_phrase": "她说先回染坊",
        "terms": ["染坊"],
        "presentations": [("A04", "text", 1)],
    },
    "F_keep_token": {
        "summary": "把竹牌收好再走",
        "nature": "剧情",
        "key_phrase": "把竹牌收好",
        "terms": ["竹牌"],
        "presentations": [("A04", "text", 2)],
    },
    "F_bluesign_link": {
        "summary": "她签名的蓝线接得上竹牌",
        "nature": "剧情",
        "key_phrase": "接得上这枚牌",
        "terms": ["蓝线", "竹牌"],
        # 轻剪独有；经 M2 对应到正片 A03 的位置
        "presentations": [("B02", "text", 0)],
    },
    "F_spinoff_setup": {
        "summary": "江边设局（轻剪番外）",
        "nature": "剧情",
        "key_phrase": "江边设局",
        "terms": [],
        # 番外：不能代替正片发生过的事
        "presentations": [("B02", "screen", 0)],
    },
}

CHARACTERS = {
    "阿遥": {
        "knows": ["F_kite_at_door", "F_token_half"],
        "learns": {"F_identity": "A03"},  # 阿遥到 A03 才知道交信人是谁
    },
    "石绘": {
        "knows": ["F_identity", "F_blueline_mark", "F_sister",
                  "F_half_token", "F_token_returned"],
        "learns": {},
    },
}

RESUME_CONTEXT = {
    "A04": {
        # 缺关键前因时，回顾只能用已见过的称呼说明能接到哪里
        "key_antecedents": ["F_token_half"],
        "scene_characters": ["石绘", "阿遥"],
        "orient_facts": ["F_identity", "F_blueline_mark",
                         "F_bluesign_link", "F_token_half"],
        "gap_marker": {"text": "她回染坊的缘由在前文", "terms": ["染坊"]},
        "questions": [
            {
                "id": "why-dyehouse",
                "keywords": ["为什么", "染坊"],
                "answer_facts": ["F_token_half", "F_token_returned"],
            },
        ],
    },
}

MAPPING_INTERPRETATIONS = {
    "M2": {
        # 原登记“揭秘对白对应”：按整段对应理解，B02 任一台词播全即算接触到揭晓
        "note": [
            {"op": "present_clip", "fact": "F_identity", "clip": "B02"},
        ],
        # E2 修订：前半句是伏笔的回看，末句才给出等价身份信息；番外换了剪辑作者代号
        "edit_view": [
            {"op": "present", "fact": "F_identity", "clip": "B02",
             "track": "text", "line": 1},
            {"op": "callback", "clip": "B02", "track": "text", "line": 0},
            {"op": "spinoff_unreliable", "clip": "B02"},
        ],
    },
}

PHRASES = {
    "F_identity": [
        {"text": "石绘就是纸鸢客", "terms": ["石绘", "纸鸢客"]},
        {"text": "她就是纸鸢客", "terms": ["纸鸢客"]},
    ],
    "F_blueline_mark": [
        {"text": "蓝线内侧有她的记号", "terms": ["蓝线"]},
    ],
    "F_bluesign_link": [
        {"text": "她的蓝线签名接得上竹牌", "terms": ["蓝线", "竹牌"]},
    ],
    "F_token_half": [
        {"text": "竹牌另一半在青井染坊", "terms": ["竹牌", "青井染坊"]},
        {"text": "竹牌另一半在染坊", "terms": ["竹牌", "染坊"]},
    ],
    "F_kite_at_door": [
        {"text": "门口那人是纸鸢客", "terms": ["纸鸢客"]},
    ],
}

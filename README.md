# 跨剪辑断点的无剧透回顾

《纸鸢局》是虚构短剧。合成资料包含两个剪辑版本、播放区间、字幕和场记，与现实平台的片库无关。

资料为 UTF-8 JSON。各类原始记录按编号分组，字段约定见 [资料格式](data/资料格式.md)。资料浏览命令会原样输出记录，添加 `--list` 可只查看各类数量。

使用 Python 3.11，命令只依赖标准库。请在项目根目录运行。

```sh
python3 inspect_records.py data/records.json --list
python3 -m unittest discover -s tests -v
```

## 生成续播回顾

```sh
python3 build_recap.py data/records.json            # 编辑预览（逐项说明保留/失效的原因）
python3 build_recap.py data/records.json --player   # 仅播放器载荷（可给该观众看的文案和位置）
python3 build_recap.py data/records.json --json     # 全部 JSON
```

- [knowledge.py](knowledge.py)：剧情知识层。事实以 (片段, 轨道, 行号) 引用原始资料，区分正片 / 预告 / 番外呈现与角色误会；登记人物各自知道的事、续播点所需的关键前因、场记关联在原登记与修订后两种状态下的解释。
- [recap_engine.py](recap_engine.py)：通用引擎。按实际播全的台词/镜头文字确认观众看到的事实（进入过片段不算听完）；同一事实在另一版有等价的独立交代可纳入已知，番外独有的解释不能代替正片；预告不在正片时间线上确立事实。回顾只解释观众已有观看依据的部分，缺关键前因时用已见过的称呼说明能接到哪里；补看区间必须在当前版本续播点之前、不带出续播后剧情，并在观众给的时间窗口内挑选（关键前因优先，允许零段）。删除播放 / 修订场记发布后，分别重新核对已预生成的文案与跳转：文字不为含剧透的跳转背书，仍安全的跳转也不因同批文案作废而被删去。

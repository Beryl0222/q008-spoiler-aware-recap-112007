# 跨剪辑断点的无剧透回顾

《纸鸢局》是虚构短剧。合成资料包含两个剪辑版本、播放区间、字幕和场记，与现实平台的片库无关。

资料为 UTF-8 JSON。各类原始记录按编号分组，字段约定见 [资料格式](data/资料格式.md)。资料浏览命令会原样输出记录，添加 `--list` 可只查看各类数量。

使用 Python 3.11，命令只依赖标准库。请在项目根目录运行。

```sh
python3 inspect_records.py data/records.json --list
python3 -m unittest discover -v
```

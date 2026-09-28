# mv

根据一首歌自动生成音乐可视化 MV：分析节奏、音量和频谱，按段落切换色调，光斑、光束和地平线波形都随音乐律动。可选加载 LRC 歌词作为字幕。

```bash
pip install librosa imageio-ffmpeg numpy pillow
python render_mv.py song.mp3 -o mv.mp4 --lrc lyrics.lrc
```

- `--preview 60 90`：只渲染 60–90 秒，用来快速调试
- `--still 80 --still 185`：导出指定时间点的静帧 PNG
- `--title "..."`：片头片尾标题，默认 `our memory`

段落时间和配色在 `render_mv.py` 顶部的 `SECTIONS` 里，换歌时需要按新歌的结构调整。

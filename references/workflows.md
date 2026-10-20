# 可选流程

先查看命令 `--help`，使用明确文件路径。

## 预览与压制

```bash
python -m subtitler render video.subtitler.json --style bilingual --format ass,srt,vtt
python -m subtitler preview video.mp4 video.ass
python -m subtitler burn video.mp4 video.ass
```

需要 FFmpeg、原视频与可显示相应文字的字体。先检查预览，再生成新视频。
ASS 外观取决于播放器和字体，不覆盖原片。

## 词库

`python -m subtitler kb list` 列出内置领域。转录支持 `--kb`、`--kb-file`。
词库匹配仅辅助修正，不能保证专名正确。自定义词库不自动进入交付包。

## 独立翻译 API

`translate --help`、`proofread --help` 显示选项，配置名以
`subtitler/plugins/llm.py` 为准。先确认服务、费用和发送的数据范围。
不要在项目文件、Skill 或日志中写密钥。无需独立服务时用
`batch → 当前 Agent 翻译 → apply`。

## 失败处理

| 现象 | 处理 |
|---|---|
| 模型下载失败 | 检查网络或提供已下载模型路径 |
| CUDA 不可用 | 使用 --device cpu，不自动更改系统驱动 |
| 无音轨或无识别结果 | 核对媒体，不交付空白“成功结果” |
| 检查失败 | 按编号修正项目；待修订稿必须标明 |
| 目录存在 | 换带版本号的新目录 |
| 字体或样式异常 | 确认可用字体，先看预览 |

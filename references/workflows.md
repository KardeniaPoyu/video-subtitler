# 可选流程

自进化项目先读 [自进化使用说明](evolution.md)。下面的 `apply`、`translate`、`proofread`、
`check`、`render`、`deliver` 示例用于未绑定项目；绑定后必须加 `--memory 记忆库路径`。

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

交付已有项目时，必须再次明确允许读取项目中的外部词库：

`python -m subtitler deliver video.subtitler.json --output delivery-v2 --kb-file /absolute/words.json`

每个外部词库重复指定一次；只接受不超过 1 MiB 的普通 JSON 文件，
拒绝设备、目录和符号链接。内置词库不需要额外授权。

## 输出与并发编辑

`deliver --mode source` 只检查原文；`target` 和 `bilingual` 要求译文完整。
正式交付与 QA 使用同一份项目快照。未绑定项目统一填平小于 0.3 秒的正向间隙；
绑定记忆库后保持已验证时间轴，避免导出时改动验证快照。

压制先写到独立临时文件，成功后才创建最终文件；失败不会留下半成品。
交付目录在发布时独占创建，再逐个发布暂存文件；目录中的全部文件并非
同时可见，请在命令成功结束后使用。发布依赖同一文件系统上的硬链接；
不支持硬链接的文件系统会报错，不会退回覆盖已有输出的方式。

保存项目会检测其他进程已提交的修改。遇到冲突，重新加载项目后再应用
自己的编辑；不要用旧快照覆盖。相同拆分编辑重试不会再次拆分。
若进程意外退出留下项目旁的 `.lock` 文件，确认没有程序仍在保存该项目后，
才可删除这一个锁文件并重试。

一键 `run` 会在识别前检查项目、字幕和视频输出是否已存在。
已有项目请继续使用 `apply → deliver` 流程。启用 `--keep-audio` 后，
终端会显示保留的音频路径，Python API 同时在元数据的 `audio_path` 中返回。

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

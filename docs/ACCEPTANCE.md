# 发布验收 · 2026-10-20

## 已验证

- Windows / Python 3.11：`python -m pytest -q`，69 项通过、1 项 POSIX 符号链接测试跳过；该项由 Linux CI 验证。
- 本轮 Sourcery review 的 20 项问题已逐项修改，覆盖并发保护、词库边界、交付 QA、拆分重试和测试断言；见 [修订对照](REVIEW_FIXES.md)。
- 真实 FFmpeg 测试覆盖视频生成、16kHz 单声道提取、CPU 压制与原文件保护。
- 原创英文合成语音短片（8.95 秒）经 tiny.en / CPU 识别出 3 条字幕，并成功生成正式交付包；[实测结果](ASR_SMOKE.json)。
- Skill frontmatter 校验通过；离线 demo 生成报告。
- ZIP 仅打包白名单文件，并记录各文件 SHA-256 与源码版本。
- ZIP 解压到仓库外运行 demo 通过，逐文件 SHA-256 核对通过。
- wheel 安装到无系统包的新虚拟环境，从仓库外生成 demo 通过；此项验证离线交付。

## 待完成

真实长视频、多语种/复杂音频、翻译 API、平台购买安装。短片语音识别通过不等于准确率或性能保证。

Windows/Linux、Python 3.9/3.11/3.12 的 6 项 CI 任务在
[d0e521f 的运行](https://github.com/KardeniaPoyu/video-subtitler/actions/runs/39460707195)全部通过。
此后新增时间类型修复；该修复的云端结果以对应 PR 最新 Actions 为准。
平台上线需真实审核和购买链路通过；当前没有可申报的付费用户数据。

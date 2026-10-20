# 发布验收 · 2026-10-20

## 已验证

- Windows / Python 3.11：`python -m pytest -q`，52 项通过。
- 真实 FFmpeg 测试覆盖视频生成、16kHz 单声道提取、CPU 压制与原文件保护。
- Skill frontmatter 校验通过；离线 demo 生成报告。
- ZIP 仅打包白名单文件，并记录各文件 SHA-256 与源码版本。

## 待完成

Whisper 模型识别、真实长视频、翻译 API、非 Windows 环境运行结果、平台购买安装。

CI 配置已添加；实际云端状态以对应提交的 Actions 结果为准。
平台上线需真实审核和购买链路通过；当前没有可申报的付费用户数据。

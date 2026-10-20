# Video Subtitler

从视频生成可修改的字幕项目，再交付 SRT、VTT、ASS 与检查报告。
适合需要反复修改人名、术语、翻译和时间轴的创作者。

**0.4.0 候选版本**：本地工具与 Skill 包；SkillPay 安装、收费和审核尚待平台实测。

## 先体验

需要 Python 3.9+，建议使用虚拟环境：

```bash
python -m venv .venv
# Windows：.venv\Scripts\activate
# macOS / Linux：source .venv/bin/activate
python -m pip install .
python -m subtitler demo --output demo-output
```

打开 `demo-output/review.html`。原创合成示例不下载模型、不调用付费 API，
也不是识别准确率测试。

## 处理自己的视频

```bash
python -m subtitler doctor
python -m subtitler transcribe video.mp4 --to zh --device cpu
python -m subtitler batch video.subtitler.json --size 40
python -m subtitler apply video.subtitler.json edits.json
python -m subtitler check video.subtitler.json
python -m subtitler deliver video.subtitler.json --output delivery-v1
```

`batch` 给当前 Agent 提供待翻译字幕，Agent 生成 `edits.json`：

```json
{"1":"第一条译文","2":{"text":"修正后的原文","translation":"第二条译文"}}
```

不需要翻译时省略 `--to zh` 和翻译步骤。各命令提供 `--help`。

| 交付文件 | 用途 |
|---|---|
| subtitles.srt / .vtt / .ass | 播放器、网页与带样式字幕 |
| project.json | 原文、译文、时间轴，方便继续修改 |
| review.html / qa.json | 漏译、重叠、阅读速度等规则检查 |
| manifest.json | 文件 SHA-256，核对完整性 |

检查错误会阻止正式交付；`--draft` 可导出待修订稿。输出必须是新目录。
交付包不携带原视频或本机词库路径。

## 成本与边界

- 首次识别需下载 Whisper 模型；内存与时间取决于模型、硬件和视频。
- FFmpeg 为视频处理依赖；CUDA/GPU 可选，CPU 可运行但可能较慢。
- 可用当前 Agent 翻译；独立翻译 API 需自行提供账号并承担费用。
- 本地识别不主动上传视频；外部翻译 API 会接收字幕文本。
- 检查通过不等于语义正确；人名、数字、专词和音画同步仍需抽查。
- 不提供自动 OCR 核验、准确率保证、MCP 服务或托管算力。

更多命令见 [使用流程](references/workflows.md)；商品材料见
[SkillPay](docs/SKILLPAY.md)，测试边界见 [验收记录](docs/ACCEPTANCE.md)。

## 开发

```bash
python -m pip install pytest
python -m pytest -q
python tools/build_skill.py
```

商品包采用文件白名单，排除实录字幕、历史视频、日志与缓存。
CI 验证 Windows/Linux 的离线流程；模型识别和平台支付需单独验证。
源码按 [MIT](LICENSE) 开源；付费商品不能取消原有 MIT 权利，
不得宣称独占源码或未经验证的服务承诺。

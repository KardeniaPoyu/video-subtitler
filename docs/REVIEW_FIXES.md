# Sourcery review 修订对照

本表对应 PR #2 的本轮 20 条行内意见，记录实现与回归证据；不代表机器人已经重新批准。

| 原意见 | 修改结果 | 回归覆盖 |
|---|---|---|
| [4327723738](https://github.com/KardeniaPoyu/video-subtitler/pull/2#discussion_r4327723738) | 外部词库需显式许可；仅普通文件，读取上限 1 MiB | 词库许可、超大文件、目录与 /dev/zero（POSIX） |
| [4327723751](https://github.com/KardeniaPoyu/video-subtitler/pull/2#discussion_r4327723751) | 压制先写私有临时文件，以硬链接无覆盖发布 | 运行中插入符号链接（POSIX） |
| [4327723758](https://github.com/KardeniaPoyu/video-subtitler/pull/2#discussion_r4327723758) | 并发目标冲突时发布失败，保留已有结果 | 编码期间另一任务创建输出 |
| [4327723779](https://github.com/KardeniaPoyu/video-subtitler/pull/2#discussion_r4327723779) | 发布时独占创建目录，不替换现有空目录 | 准备期间出现同名空目录 |
| [4327723792](https://github.com/KardeniaPoyu/video-subtitler/pull/2#discussion_r4327723792) | 项目锁加保存版本摘要，拒绝旧快照 | 两个已加载项目先后修改保存 |
| [4327723806](https://github.com/KardeniaPoyu/video-subtitler/pull/2#discussion_r4327723806) | 同时识别 Windows 和 POSIX 路径分隔符 | Windows 路径脱敏 |
| [4327723817](https://github.com/KardeniaPoyu/video-subtitler/pull/2#discussion_r4327723817) | 一键流程在转录前检查全部输出冲突 | 已有输出时不调用转录、不改文件 |
| [4327723826](https://github.com/KardeniaPoyu/video-subtitler/pull/2#discussion_r4327723826) | 失败压制仅留下在临时目录内的内容并清理 | 失败后使用同一路径成功重试 |
| [4327723833](https://github.com/KardeniaPoyu/video-subtitler/pull/2#discussion_r4327723833) | 译文输出模式必须有译文 | 无目标语言的空译文拒绝正式交付 |
| [4327723839](https://github.com/KardeniaPoyu/video-subtitler/pull/2#discussion_r4327723839) | 入口深拷贝，QA 与所有输出共享同一快照 | QA 中修改原对象不改变交付 |
| [4327723848](https://github.com/KardeniaPoyu/video-subtitler/pull/2#discussion_r4327723848) | 要求字幕按开始时间排序 | 乱序项目校验失败 |
| [4327723855](https://github.com/KardeniaPoyu/video-subtitler/pull/2#discussion_r4327723855) | 尺寸和媒体数值校验 | 字符串尺寸、列表尺寸、无限 FPS |
| [4327723874](https://github.com/KardeniaPoyu/video-subtitler/pull/2#discussion_r4327723874) | 捕获数值溢出并返回校验错误 | 超大整数时间戳 |
| [4327723879](https://github.com/KardeniaPoyu/video-subtitler/pull/2#discussion_r4327723879) | 持久化拆分编辑摘要与结果 | 拆分、保存、重新加载、重试 |
| [4327723898](https://github.com/KardeniaPoyu/video-subtitler/pull/2#discussion_r4327723898) | 原文模式不执行译文检查 | 不完整或过长译文不阻塞原文输出 |
| [4327723903](https://github.com/KardeniaPoyu/video-subtitler/pull/2#discussion_r4327723903) | 同一间隙归一化结果用于 QA、字幕和项目 | 短间隙与 SRT 时间一致 |
| [4327723911](https://github.com/KardeniaPoyu/video-subtitler/pull/2#discussion_r4327723911) | 返回并打印保留音频路径 | 元数据路径存在且终端可查 |
| [4327723921](https://github.com/KardeniaPoyu/video-subtitler/pull/2#discussion_r4327723921) | 在真实 FFmpeg 调用时断言工作目录 | test_media_smoke.py |
| [4327723929](https://github.com/KardeniaPoyu/video-subtitler/pull/2#discussion_r4327723929) | 精确核对 manifest 六个文件后逐个验哈希 | test_delivery.py |
| [4327723940](https://github.com/KardeniaPoyu/video-subtitler/pull/2#discussion_r4327723940) | 冲突前后比较原内容，不仅检查异常 | 交付目录与真实媒体碰撞保护 |

测试位于 `tests/test_review_regressions.py`、`tests/test_delivery.py` 和 `tests/test_media_smoke.py`。Windows 本地 69 项通过、1 项 POSIX 测试跳过；完整平台矩阵见 PR Checks。

发布依赖硬链接；交付目录独占创建后逐文件发布，整目录不是原子可见。项目锁只协调使用本工具保存的进程；旧快照冲突需要重新加载。


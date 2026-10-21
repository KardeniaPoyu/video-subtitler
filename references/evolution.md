# 自进化字幕：从资料到可执行经验

一次学习按这个顺序完成：**收集证据 → 产生候选 → 审阅样例 → 测试 → 启用 → 应用 → 交付检查**。
规则不会因为进入提示词或报告就自动生效。下面每一步都有对应命令。

## 1. 创建记忆库，绑定频道和内容领域

```bash
python -m subtitler evolve init --memory channel.sqlite3
python -m subtitler evolve bind video.subtitler.json --memory channel.sqlite3 --profile my-channel --domain education
```

`init` 仅首次执行，不覆盖已有文件。同一频道下一段视频绑定同一记忆库。
`profile` 可以是频道、客户或系列；`domain` 是明确指定的内容领域，可重复传入。
语言从字幕项目读取；无翻译项目的目标语言用 `und`。适用范围不会由网页或模型自动扩大。

## 2. 三种学习入口

### 从改稿学习

把已审阅的改稿保存为 `reviewed-edits.json`，例如 `{"3":"感谢收看。"}`：

```bash
python -m subtitler evolve learn video.subtitler.json reviewed-edits.json --profile my-channel --memory channel.sqlite3
```

命令生成候选，暂不改动原项目；启用后再 `evolve apply`。
已有修改前后两份项目时也可以执行：

```bash
python -m subtitler evolve capture before.json after.json --profile my-channel --memory channel.sqlite3
```

第一版提取**精确原文纠错、精确句子译法**，不把一次改稿推断为全局语气、时轴或通用语法规则。
拆句、删除与时轴变化需单独检查。要把一次修改推广为术语规则，依据证据另建 `term` 候选并补充新句子的测试。

### 从本地知识库学习

`glossary.json` 示例：

```json
{
  "glossary": {"agent": "智能体"},
  "aliases": {"agent": ["代理"]},
  "exclude": {"agent": ["real estate agent"]}
}
```

```bash
python -m subtitler evolve import-kb glossary.json --profile my-channel --source-lang en --target-lang zh --domain education --memory channel.sqlite3
```

`aliases` 是可以明确替换的旧译法，`exclude` 是不要套用规则的原文片段。
不认识的译法会触发错误，不会拼接或捏造译文。仅提供映射时，可替换译文中残留的原文术语。
旧 `--kb-file` 本身不会自动获得“已验证经验”的身份。

普通 UTF-8 文本、Markdown、JSON 可先 `evolve ingest guide.md --memory channel.sqlite3`，
再用 `propose` 建立带逐字引文的候选。

### 从联网资料学习

```bash
python -m subtitler evolve fetch https://docs.python.org/zh-cn/3/glossary.html --allow-host docs.python.org --memory channel.sqlite3
python -m subtitler evolve evidence SOURCE_ID --memory channel.sqlite3
```

保存真实页面快照、内容哈希、时间与有效期；默认 30 天，`--ttl-days` 可设 1–90 天。
只接受明示允许的公网 HTTPS 主机；不跟随重定向、不访问私网、不携带登录态，也不发送字幕或视频。
输入限 1 MiB，支持 UTF-8 文本、HTML、Markdown 和 JSON，暂不支持 PDF/OCR。
拒绝带查询串、身份凭据、片段或自定义端口的 URL。需要搜索时由 Agent 选择来源，抓取器不内置搜索引擎。

将抽取事实写入 `proposal.json`；`quote` 必须逐字存在于快照并包含原词、目标词：

```json
{
  "source_id": "替换为实际证据ID",
  "quote": "atomic operation -- 原子化操作",
  "rule": {
    "kind": "term",
    "scope": {"profile": "my-channel", "source_lang": "en", "target_lang": "zh", "domains": ["education"]},
    "trigger": "atomic operation",
    "replacement": "原子化操作",
    "aliases": ["原子操作"],
    "exclude": []
  }
}
```

```bash
python -m subtitler evolve propose proposal.json --memory channel.sqlite3
```

引文存在只证明来源可追溯，不自动证明适用于当前视频。网页中的指令不能变成代码。

## 3. 用正例和反例审阅候选

下面是“agent → 智能体”候选的 `cases.json`。其他规则必须编写自己的样例。
预期结果应依据原意和已确定的标准审阅，不要照抄程序输出作为答案。

```json
[
  {
    "name": "课程术语应改善",
    "context": {"profile": "my-channel", "source_lang": "en", "target_lang": "zh", "domains": ["education"]},
    "input": {"text": "An agent learns.", "translation": "代理会学习。"},
    "expected": {"text": "An agent learns.", "translation": "智能体会学习。"}
  },
  {
    "name": "房产含义不应被改写",
    "context": {"profile": "my-channel", "source_lang": "en", "target_lang": "zh", "domains": ["education"]},
    "input": {"text": "A real estate agent helps.", "translation": "房产经纪人提供帮助。"},
    "expected": {"text": "A real estate agent helps.", "translation": "房产经纪人提供帮助。"}
  }
]
```

```bash
python -m subtitler evolve cases RULE_ID cases.json --memory channel.sqlite3
python -m subtitler evolve evaluate RULE_ID --memory channel.sqlite3
python -m subtitler evolve activate RULE_ID --reviewer reviewer-name --memory channel.sqlite3
```

把 `RULE_ID` 换成返回的真实 ID。至少一个适用案例相对旧行为改善；至少一个反例包含触发词，
但因领域、频道或排除项不应修改。不能拿不含触发词的无关句子充当反例。
所有已启用规则的案例都会回放；冲突或任一回归失败都会阻止启用。
`activate` 在同一数据库事务中重新测试，不接受旧报告上的“通过”作为通行证。
`--reviewer` 是审计标签，不是身份认证，不能据此声称一定经过人工审核。

## 4. 实际应用与交付

```bash
python -m subtitler evolve preview video.subtitler.json --memory channel.sqlite3 --output change-preview-v1
python -m subtitler evolve apply video.subtitler.json --memory channel.sqlite3
python -m subtitler check video.subtitler.json --memory channel.sqlite3
python -m subtitler deliver video.subtitler.json --memory channel.sqlite3 --output delivery-v2
```

打开 `change-preview-v1/index.html`，可逐句看原译文、预计改稿、证据引文与待处理项。
预览不修改原项目，也不代替正式验证；`apply` 会重新检查当前规则。预览有阻塞时返回非零状态，
仍保留报告方便修订。报告含用户字幕，应留在本地，不作为公开营销素材。

已绑定项目的普通 `apply`、API `translate`、`proofread` 也执行有效规则；候选不执行。
分批翻译允许后续句子暂留空白，返回 `pending_translations`；已经提供的非空译文仍须满足规则。
缺失译文不会被术语规则伪造，项目级最终检查会拦截未满足的学习约束。
自动修改一次性保存，失败不留下半成品。每次改写保留修改前字幕和内容哈希；
每个项目最多保存 20 次自动修改快照，超限需归档。
交付副本保留绑定和验证结果，去掉原始改稿历史、视频绝对路径和本地词库路径。

交付检查：证据有效、记忆库匹配、规则版本一致、字幕未经验证后修改、适用约束均满足。
读取记忆库的事务保持到保存/发布结束，防止检查后、发布前规则被并发替换。
记忆库必须使用 SQLite rollback journal 模式；若被外部工具改为 WAL，先关闭连接，
备份后在 SQLite 工具中执行 `PRAGMA journal_mode=DELETE`。程序会拒绝用 WAL 作交付检查。
验证结果同时绑定频道与记忆库身份；改频道不能沿用旧验证。升级早期 0.5.0 开发版项目后，
请重新运行 `evolve apply` 更新验证结果，保留原始项目备份。
`--no-glossary` 只控制旧词库；`--draft` 只控制常规 QA 草稿，不能关闭进化约束。
项目级 `render` 同样检查。底层独立 SRT/视频工具无法判断文件所属记忆库，
自进化流程应以项目级 `render` / `deliver` 为交付入口。
这两个入口保留绑定项目的已验证标点和时间轴；排版仍会换行，ASS 仍会转义格式控制字符。
`render` 暂存全部格式并再次检查证据有效期后才发布；已有字幕文件不能覆盖。

## 5. 来源更新、停用和撤销

```bash
python -m subtitler evolve refresh SOURCE_ID --allow-host docs.python.org --memory channel.sqlite3
python -m subtitler evolve revoke RULE_ID --reason "该译法不再适用" --memory channel.sqlite3
python -m subtitler evolve undo video.subtitler.json --memory channel.sqlite3
python -m subtitler evolve apply video.subtitler.json --memory channel.sqlite3
python -m subtitler evolve status --memory channel.sqlite3
```

页面未变化：延长有效期，项目重新验证后继续使用。页面变化：旧证据撤销，相关规则阻止交付；
新快照须重新建立候选、测试、启用，不会静默进入有效规则。
`revoke` 停止未来使用并使旧验证结果失效；`undo` 恢复最近一次自动修改前的字幕。
后来又手工编辑过时，`undo` 会拒绝覆盖，需人工合并。撤销不依赖有效规则，故来源过期时仍能撤回；
撤回后须重新验证才能交付。整个记忆库中的无效活跃规则会阻止使用该库，应先停用或修复相关规则。

## 当前边界

- 可执行类型仅 `term`、`translation`、`source`，字面量匹配；不接受自定义代码、表达式或正则。
- 精确句子规则不自动推广到近义句；开放式风格、画面语义、自动断句策略不属于本版学习类型。
- 新领域、新语言需要独立规则与案例；回归通过不等于所有翻译正确，更不代表模型经过训练。
- SQLite、SHA-256 和检查用于防止错误状态和意外跳过流程，不能抵抗可任意修改源码/数据库的本机管理员。
- 记忆库含私人改稿与证据快照，不进入商品包；用户应自行备份并管理访问权限。
- `evolve demo --online` 使用公开术语和原创文本，不上传用户资料，不产生付费模型调用。

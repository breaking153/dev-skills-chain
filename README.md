# Prompt 使用与维护

本仓库的 9 份 Prompt 使用相同的技术笔记组织逻辑：概念与范围 → 适用的环境准备 → 项目组成与配置 → 主题机制 → 使用与验证。章节按主题取舍，复杂对象允许继续展开四、五级标题。

历史提问只作为知识需求来源：提取概念与机制，去重归类后输出体系化知识。不会按提问顺序逐题回答，也不会让每个追问各占一个章节。

v7 以精炼、带注释的真实代码作为机制说明的主线：先总述，再把注册、参数传递、处理与清理合并到同一知识块。禁止伪代码、孤立表达式和隐藏核心逻辑的辅助函数；代码保留必要上下文，省去无关工程样板。表格与 Mermaid 用于比较和跨组件关系，文字只补前提与边界，避免重复代码。

| Espanso 快捷词 | 可独立复制的 Prompt | 用途 |
| --- | --- | --- |
| `/shuli` | [knowledge/shuli.md](knowledge/shuli.md) | 从主题、会话或资料生成技术笔记 |
| `/wanshan` | [knowledge/wanshan.md](knowledge/wanshan.md) | 保留合理原结构，补齐说明与必要同级内容 |
| `/canvas` | [knowledge/canvas.md](knowledge/canvas.md) | 按章节逻辑生成 Obsidian Canvas JSON |
| `/uil`、`/uim`、`/uih` | [frontend](frontend) | L1–L3 前端开发与相应技术说明 |
| `/cdl`、`/cdm`、`/cdh` | [Backend](Backend) | L1–L3 后端开发与相应技术说明 |

`/date` 保留原行为。开发 Prompt 遇到纯知识请求时只整理笔记；实际开发时继续执行原有工程流程。

## 结构参考

[技术笔记结构契约](templates/technical-note-contract.md) 说明标题归属、正文展开、示例与去重规则。

[TypeScript 风格参考](templates/typescript-style-reference.md) 从用户提供的 Markdown 提炼，保留“概念、安装、项目结构、命令行”的组织方式，合并重复讲解并整理围栏与引用。原附件没有被覆盖。这份参考用于学习写法，不作为其他主题的事实来源。

知识 Prompt 内已包含独立可用的规则；Espanso 展开不会自动读取本地模板文件。需要更强的风格参照时，把该 Markdown 的内容一并粘贴或作为附件提供，并说明：

> 下面的 TypeScript 笔记只作为结构和表达参考，不是本次要整理的主题。请按我的实际任务生成内容。

随后追加实际主题，例如：

> AI 游戏开发相关技术分析解析的相关技术梳理。说明 AI 辅助开发与游戏运行时 AI，围绕一个能巡逻、追逐并对话的 NPC 讲清各项技术如何配合。

## 验证

[AI 游戏开发试跑笔记](tests/outputs/ai-game-development.md) 用于验证 v7 的注释代码主线和开发 Prompt 知识分流；另有早期补全、Canvas 与[历史提问归类示例](tests/outputs/ai-game-history-synthesis.md) 作为结构回归资料。旧样例不代表 v7 新生成结果，范围与结果见 [测试报告](tests/validation-report.md)。

[EDR 驱动层代码主线示例](tests/outputs/edr-driver-knowledge.md) 用于验证 v7：用整合的真实 C 片段展示回调注册、参数分派和注销，替代孤立语句与重复的枚举对照表。原稿保存在 `tests/inputs/edr-draft.md`，本轮要求见 [代码表达测试输入](tests/inputs/codefirst-request.md)。

本次本地环境已有 Python 和 PyYAML。修改任一源 Prompt 后，需要同步仓库 `base.yml` 与实际使用的 Espanso `match/base.yml` 对应 `replace`；不能只修改其中一份。执行以下只读检查可发现不同步、无效层级或 Canvas 结构问题：

```powershell
python -X utf8 tests/verify_prompts.py --report tests/verification.json
```

默认检查 `%APPDATA%/espanso/match/base.yml`；其他位置用 `--installed` 指定。还可用 `--espanso` 指定 `espansod.exe`，核对 CLI 加载的完整替换内容及服务状态。

该脚本校验已有试跑产物，不会自行调用模型重新生成。Prompt 修改后的生成行为需要重新试跑并做内容复核；JSON 和几何检查也不等于已在 Obsidian 中目视检查。

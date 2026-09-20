# Prompt 结构验证记录

日期：2026-09-20。

本文按版本记录试跑。v5、v6 的原产物可在提交 `7f7987b`、`013a32c` 查阅；当前 `ai-game-development.md` 与 `edr-driver-knowledge.md` 已由文末的 v7 试跑替换，其他旧样例仅用于历史结构回归。

## 变更范围

- 6 份前后端开发 Prompt 更新至 v5，加入任务分流、知识结构、结构正例和历史提问归类规则。
- `/shuli`、`/wanshan`、`/canvas` 重写为可单独维护的 `knowledge/*.md`。
- 仓库与本地 Espanso `base.yml` 同步，保留原 10 个快捷词和 `/date`。
- 用户的 TypeScript 原稿另行整理为结构参考，原附件未覆盖。

开发 Prompt 原有“最高优先级”节至“输出”节之前的工程流程，与 Git 修改前版本逐字一致；新增分流明确这些工程要求只适用于实际开发任务。

## 生成试跑

试跑由独立子任务实际读取本地 Espanso YAML 中相应 `replace` 全文，再根据测试输入生成文件。本次未接入外部聊天网站，也不是跨模型成功率评测。

| Prompt | 输入与产物 | 覆盖内容 |
| --- | --- | --- |
| `/shuli` | `inputs/ai-game-development.md` + TypeScript 结构参考 → `outputs/ai-game-development.md` | 从概念、环境、项目结构进入运行时行为和对话服务，最后给验证预期 |
| `/wanshan` | `inputs/incomplete-note.md` → `outputs/ai-game-completed.md` | 原标题与顺序、WikiLink、同级对象补全、四级动作校验说明 |
| `/cdm` | `inputs/ai-game-development.md`，无外加结构模板 → `outputs/ai-game-backend-prompt.md` | 内置结构能独立生效；纯知识任务没有触发安装、初始化或工程交付报告 |
| `/canvas` | `inputs/incomplete-note.md` → `outputs/ai-game-development.canvas` | 原一级章节映射为分组，合法 JSON、节点包含和坐标检查 |
| `/shuli` | `inputs/followup-history.md`，无外加结构模板 → `outputs/ai-game-history-synthesis.md` | 把 8 个零散历史追问归类为技术知识，避免逐题问答和按提问顺序组织目录 |

六份开发 Prompt 的共同契约和全部源文件同步均进行了静态检查；模型生成只对上表列出的入口进行试跑，没有把其余五份开发 Prompt 声称为已逐一生成验证。

## 复核修正

首轮生成的 NPC 伪代码缺少主动结束对话的状态退出条件，与正文不一致。独立复核发现后，在提示规则中增加了进入、退出、取消与失败条件的一致性检查，并反馈给生成子任务重新读取规则修订示例。

首轮 Canvas 有重复父子标题及用于分类、阅读顺序和验收对应关系的连线。提示词进一步明确了标题去重、连线语义与允许空 `edges`，再重新生成检查。

用户补充“历史问题应归类成知识”后，全部 9 份 Prompt 均加入该规则，并单独增加了历史问答归类的生成回归样例。

## 可重复检查

```powershell
python -X utf8 tests/verify_prompts.py --report tests/verification.json
git diff --check
```

传入 `--espanso` 可额外检查实际 CLI 读取的九个完整 Prompt 是否与源文件一致，以及服务是否运行。本地使用 Espanso 2.4.0、Python 3.14 与已有的 PyYAML 6.0.2；未安装新的运行依赖。

机器检查覆盖：YAML 解析、9 份 Prompt 源文同步、10 个唯一快捷词、整体代码围栏、标题跳级、问答包装、原文标题顺序和 WikiLink、Canvas 字段与 ID、端点有效性、正宽高、分组包含与同级不重叠。最新结果见 `verification.json`。

Espanso 首次自动重载时旧 worker 退出异常；读取日志和服务状态后重新启动服务。后续配置重载成功，最终以 CLI 与服务状态检查为准。没有升级 Espanso，也不宣称已修复其内部退出问题。

## 验证边界

- 这次验证的是 Prompt 同步、生成结构与示例内容，不是游戏项目的端到端测试。笔记中的代码、目录、状态和结果已标注为示例、伪代码或预期。
- 没有在目标文本编辑器里模拟输入快捷词，没有在 Obsidian 中进行视觉检查；CLI 读取、JSON 与几何检查不能替代这两项。
- 生成存在模型与上下文差异，本次结果不等于对任意模型或主题的结构保证。

## v6：知识归属与表述回归

用户认可原有整体结构，进一步要求按合理的理解顺序和包含关系组织知识，并精简、逻辑化表达。本轮全部 9 份 Prompt 增加了这些规则，6 份开发 Prompt 标记为 v6，原有工程流程保留。

主要调整：

- 父子层级表示组成或细化，调用、引用和执行顺序另行说明；并列节点采用同一分类依据。
- 共用的注册配置和生命周期知识从局部操作示例中独立出来。
- 正面表达职责、行为和因果，合并重复的否定式提醒、铺垫与代码复述。
- 精简时保留触发条件、控制字段、返回语义、资源所有权和失败处理。
- 已核实的链接代替平台内部引用占位符，无法还原的来源不猜造。

新增试跑从本地 Espanso 的 `/shuli` 读取完整规则，以 `inputs/edr-draft.md` 和 `inputs/edr-expression-request.md` 为输入，生成 `outputs/edr-driver-knowledge.md`。原材料 34349 个字符、1359 行，包含 79 个缺少链接映射的引用标记；仓库输入副本仅规范化换行与行尾空格，原附件未修改。正文缩减量只是观察数据，不是质量通过标准；知识归属及关键控制语义由独立内容复核确认。

`verify_prompts.py` 增加了新稿的围栏和标题检查、未解析引用检查、关键控制词保留检查及原稿与结果字符数统计。旧的 5 份 AI 游戏样例作为结构回归数据重新检查，未声称它们是 v6 新生成结果；本轮新生成场景是 EDR 笔记，未运行或编译驱动。

独立内容复核确认 Ps 创建状态、Ob 当前权限掩码和 Post 只读、Cm 前置拒绝及对象有效性、Flt 提前初始化与挂起完成、WFP 动作权限与撤销生命周期等关键条件保留。复核后对进程通知做了一处人工调序：先讲创建信息与裁决，再讲回调注册、版本和签名条件；没有改变技术事实。新稿保留原 11 个一级章节，总字符数减少约三分之一，79 个无法解析的引用标记全部清理，补充 11 条已核实的微软官方链接。

## v7：精炼注释代码主线

全部 9 份 Prompt 与两份 `base.yml` 已同步。6 份开发 Prompt 标记为 v7，其共同契约一致，`## 最高优先级：` 至文末的工程正文与本轮修改前的 `013a32c` 逐字相同。`/shuli`、`/wanshan` 完整包含最新结构契约；Canvas 保留 JSON 字段和布局规则。

本轮规则要求总述后按独立机制展开，以真实注释代码串联必要上下文、注册、参数传递、分派、结果与清理；同一调用链合并为知识块，禁止伪代码、孤立表达式和未实现的核心辅助函数。表格和 Mermaid 只补比较与跨组件关系，纯概念保留简短文字。交叉审查修正了“每个逻辑块都必须代码化”的歧义，避免产生无用代码。

两次独立生成均实际读取本地 Espanso 的对应 `replace`，输入包括 `inputs/codefirst-request.md`：

| Prompt | 当前产物 | 本轮验证 |
| --- | --- | --- |
| `/shuli` | `outputs/edr-driver-knowledge.md` | 保留 11 个一级领域，6 块真实 C 片段与 3 个 Mermaid；重点验证 Ob、Cm 的注册、类型分派与生命周期。 |
| `/cdm` 纯知识分支 | `outputs/ai-game-development.md` | 两段独立 JavaScript 串联 NPC 状态与移动、模型结果校验与受控动作，没有触发工程安装或创建游戏项目。 |

EDR 稿在精简文字的同时补齐了代码，因此总字符数较 v6 增加；相对最初输入仍由 34,348 降至 26,445，中文字符由 10,851 降至 4,401。字符数和代码行数仅用于观察，不代表正确性。Ob 的字段含义与通知枚举移入就近注释、分派代码，删除了重复的句柄字段表；必要的失败回滚和所有权保留。示例入口明确由调用方提供目标对象、有效 Altitude、路径及 GUID，没有虚构生产高度或未实现的策略函数。

独立微软文档复核修正了 WFP 的两处实质问题：`notifyFn0` 的 Filter 参数去除错误的 `const`；支持 BLOCK/CONTINUE 的示例使用 `FWP_ACTION_CALLOUT_UNKNOWN`，避免终止型动作将 CONTINUE 当作阻断。还保留了管理会话清理失败时的句柄，以便调用方继续关闭。Ob 权限范围与 Post 只读、Cm 名称释放和对象有效性、Flt 启动前初始化与完成路径、WFP 上下文与注销责任均完成内容审查。当前未找到可用的 WDK 编译环境，所有 C 片段均未编译、未链接、未加载运行。

AI 游戏两段代码从 Markdown 提取，分别通过 `D:\N-NpmEnv\node.exe --input-type=module -` 执行，Node.js v24.12.0 下输出 `npc-state: passed`、`npc-dialogue: passed`。主任务独立重跑，并补查负数/非有限时间、非有限坐标、移动不过目标、会话失效、追逐优先级、奖励条件、额外字段、超长文本、非字符串输入、旧会话不干扰当前请求和重复响应；全部通过。测试模型输入是固定 JSON，没有声称实际推理或网络请求；也没有运行 Godot 场景。

最终可重复配置与结构检查：

```powershell
python -X utf8 tests/verify_prompts.py --espanso "$env:LOCALAPPDATA\Programs\Espanso\espansod.exe" --report tests/verification.json
git diff --check
```

脚本新增当前两份试跑的围栏语言、实现行数与正文字符统计及明显占位检查；结果见 `verification.json`。九份完整替换内容与 Espanso CLI 一致，10 个快捷词及 `/date` 保留。检查时服务曾处于停止状态，日志没有给出停止原因；恢复服务后确认新配置重载成功，最终状态为运行中，不把恢复服务宣称为修复 Espanso 内部缺陷。

当前 Canvas 历史样例通过 JSON 与几何回归，未重新生成 v7 Canvas；Mermaid 未在 Obsidian 中渲染验证。没有在编辑器中模拟输入快捷词，也未把静态占位检查当作 C 编译或语义证明。

# Prompt 结构验证记录

日期：2026-09-20。

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

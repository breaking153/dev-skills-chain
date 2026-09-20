# AI 游戏开发测试资料

以下资料由独立研究子任务于 2026-09-20 查阅官方来源后整理。事实可引用，建议必须写成示例设计，不是引擎或服务商的强制规范。不代表指定版本已在本地安装。

| 主题 | 核实的事实 | 官方来源 |
| --- | --- | --- |
| 开发期与运行时 | Unity 将编辑器问答、代码和资源生成，与在项目中运行训练模型区分为不同能力。 | [Unity AI](https://docs.unity.com/en-us/ai) |
| 节点与场景 | Godot 节点组成树；保存后的节点树可以成为场景，场景能被实例化，每个场景有根节点；主场景作为项目启动入口。 | [Godot Nodes and Scenes](https://docs.godotengine.org/en/stable/getting_started/step_by_step/nodes_and_scenes.html) |
| 行为决策与移动 | Unreal 示例以 Blackboard 保存目标、视线等状态，行为树组织巡逻和追逐，NavMeshBoundsVolume 用于形成可移动区域的导航网格。 | [Unreal Behavior Tree Quick Start](https://dev.epicgames.com/documentation/en-us/unreal-engine/behavior-tree-in-unreal-engine---quick-start-guide) |
| 学习代理 | ML-Agents 使用观察、动作和奖励建立学习任务；训练得到策略，推理使用策略决定动作，训练结果可导出到 Unity 内使用。 | [ML-Agents Overview](https://unity-technologies.github.io/ml-agents/ML-Agents-Overview/) |
| 函数调用 | 模型生成函数名称与参数，实际函数由应用执行；应用需要验证请求并处理错误与身份认证。 | [Gemini Function calling](https://ai.google.dev/gemini-api/docs/function-calling) |
| 资源导入 | Godot 自动导入受支持资源；`.godot/imported/` 存放内部产物，源资源旁的 `.import` 存放导入配置。 | [Godot Import process](https://docs.godotengine.org/en/stable/tutorials/assets_pipeline/import_process.html) |
| 生成延迟 | 延迟受模型、提示复杂度和基础设施等影响，流式响应可以在完整输出结束前显示内容；TTFT 用于衡量首 token 时间。 | [Anthropic Reducing latency](https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-latency) |

可采用的示例设计：规则或状态机控制 NPC 巡逻追逐；对话请求异步处理，不阻塞战斗与导航；模型只提出意图，由游戏代码校验任务状态、参数与重复领取后才能发奖；超时回退预设台词。具体阈值、目录和伪代码属于教程设计，不应写成已运行结果。

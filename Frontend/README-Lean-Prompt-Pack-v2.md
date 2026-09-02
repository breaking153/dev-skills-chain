# Lean Frontend & Backend Prompt Pack v2

验证日期：2026-09-02

这套 Prompt Pack 针对旧版“Skill 数量随难度不断膨胀”的问题进行了去重。

核心原则：

> Skill 只承载难以由普通 Prompt 稳定替代的专业工作流；难度升级主要通过分析深度、状态覆盖、测试强度和发布门禁实现。

## 文件

### Frontend

- `01-Frontend-L1-Lean.md`：简单 UI，1 个 Core + 最多 1 个 Conditional。
- `02-Frontend-L2-Product.md`：普通产品 UI，1 个 Core + 最多 3 个 Conditional。
- `03-Frontend-L3-Flagship.md`：旗舰 UI，仍是同一精简骨架，但验证和设计流程更深。

### Backend

- `01-Backend-L1-Lean.md`：简单功能或 Bug，1 个 Core + 最多 1 个 Conditional。
- `02-Backend-L2-Production.md`：普通生产后端，3 个 Core + 最多 1 个 Conditional。
- `03-Backend-L3-Critical.md`：关键系统，4 个 Core + 最多 2 个 Conditional，其中安全插件最多选择 1 个。

## 新版 Skill 矩阵

| Prompt | Core | Conditional | 通常实际数量 |
|---|---|---|---:|
| Frontend L1 | frontend-ui-engineering | shadcn | 1–2 |
| Frontend L2 | Impeccable | shadcn、React Best Practices、Browser DevTools | 1–4 |
| Frontend L3 | Impeccable | shadcn、React Best Practices、Browser DevTools | 2–4 |
| Backend L1 | TDD | Debugging | 1 |
| Backend L2 | API Design、TDD、Security | Source-driven | 3–4 |
| Backend L3 | Spec、API Design、TDD、Security | Source-driven、最多 1 个 Trail of Bits Assurance | 4–6 |

“Conditional”不是全部安装，而是命中明确触发条件才安装。

## 前端去重逻辑

旧版 L3 同时使用多个设计、审查和规范 Skill，容易产生：

- 重复读取同一套排版、颜色、响应式和可访问性规则；
- 多个 Reviewer 对同一设计反复推翻；
- 素材库也变成 Skill，导致上下文膨胀；
- 浏览器测试工具重复；
- 难度越高，初始化成本越高。

新版改为：

```text
L1：frontend-ui-engineering
     + 条件 shadcn

L2 / L3：Impeccable
          + 条件 shadcn
          + 条件 React / Next 性能规则
          + 只选一种浏览器测试路径
```

Impeccable 统一承担设计建模、Critique、Audit、Adapt、Harden 和 Polish。shadcn 只负责组件 Registry 和组件源码。Magic UI、Tailark、Tremor 只是免费素材来源，不再全部做成常驻 Skill。

## 后端去重逻辑

旧版通过总包、语言插件、数据库插件、安全插件、Observability 插件和多种 Review 插件叠加，容易出现：

- TDD、Debug、Review、Security 重复规定相同门禁；
- 通用 Backend Skill 与语言专项 Skill 重复；
- 数据库、日志、性能和部署关注点被误认为必须各装一个 Skill；
- 高档初始化大量插件，但实际任务只用少数几个；
- 不同仓库的工作流互相抢占执行顺序。

新版统一使用 Addy Osmani 仓库中的少量原子 Skill：

```text
简单任务：TDD
普通生产：API Design + TDD + Security
关键系统：Spec + API Design + TDD + Security
```

框架、数据库、事务、迁移、可靠性、Observability、性能和发布仍然严格要求，但写入 Prompt 主流程，不再形成常驻插件矩阵。Trail of Bits 只在高风险任务中按触发条件选择一个独立 Assurance 插件。

## 为什么选择这些社区项目

### Vercel `skills` CLI

- 官方仓库：https://github.com/vercel-labs/skills
- 许可证：MIT
- 用于项目级、按单个 Skill、非交互安装。

常用形式：

```bash
npx skills add <repo> --skill <name> -a codex --copy -y
npx skills list -a codex
```

### Addy Osmani Agent Skills

- 官方仓库：https://github.com/addyosmani/agent-skills
- 许可证：MIT
- 优点：同一仓库内提供原子化工程 Skill，可按任务选择，不需要安装全部套件。

注意：按单个 Skill 安装时可能不携带仓库级共享 `references/`。核心 Skill 仍然可用；不要为了补参考文件安装全部 25 个 Skill。

### Impeccable

- 官方仓库：https://github.com/pbakaus/impeccable
- 许可证：Apache-2.0
- 用于统一前端设计方向、审查和打磨，替代多个功能重叠的 UI Skill。

```bash
npx impeccable install --providers=codex --scope=project
```

Codex 安装或更新后需要人工进入 `/hooks` 批准项目 Hook。

### shadcn Skill

- 官方仓库：https://github.com/shadcn-ui/ui/tree/main/skills/shadcn
- 许可证：MIT
- 只在兼容项目中用于搜索、查看文档、安装和组合组件。

Monorepo 必须在实际 Web Workspace 中运行；所有 `add` 或更新操作先预览 Diff，并检查新增依赖和路径 Alias。

### Vercel React Best Practices

- 官方仓库：https://github.com/vercel-labs/agent-skills/tree/main/skills/react-best-practices
- 许可证：MIT
- 只在 React / Next.js 中使用；非 React 项目不安装。

### Trail of Bits Skills

- 官方仓库：https://github.com/trailofbits/skills
- Marketplace 许可证：CC-BY-SA-4.0
- 只用于 Backend L3 的独立专项验证，并且每次最多选择一个插件。

## 免费前端素材策略

允许按需使用：

| 来源 | 许可证 | URL |
|---|---|---|
| shadcn/ui | MIT | https://github.com/shadcn-ui/ui |
| Magic UI OSS | MIT | https://github.com/magicuidesign/magicui |
| Tailark OSS | MIT | https://github.com/tailark/blocks |
| Tremor | Apache-2.0 | https://github.com/tremorlabs/tremor |

这些是素材来源，不等于每个项目都要安装。单页通常只需：

```text
1 套 Base UI
+ 0/1 套页面或数据 Pattern
+ 0/1 套 Motion / Signature
```

强制排除：

- 21st.dev 与其他额度制服务；
- Pro / Premium 内容；
- 登录后才能复制；
- Commons Clause 或限制再分发的来源；
- 许可证不明确的模板；
- 社交媒体未知代码；
- 仅为展示效果而引入的大型依赖。

## 自动安装边界

Prompt 中的“自动安装”表示：

- 只安装当前项目所需的 Agent Skill；
- 只从文件中列出的官方来源安装；
- 不安装系统 Node、Git、Python、Docker、数据库、浏览器或 SDK；
- 不绕过 Hook、Plugin、目录信任或安全提示；
- 安装后验证 `SKILL.md`、Skill 清单和 `git diff`；
- 新 Skill 需要重载会话时如实标记。

## 使用方式

1. 选择与任务风险相匹配的 Prompt，而不是永远使用 L3。
2. 填写开头的 YAML 输入区。
3. 将整份 Markdown 作为项目任务 Prompt 使用。
4. Agent 会检测并只安装缺失且已经触发的 Skill。
5. 任务完成后根据最终报告检查安装项、文件变化和验证证据。

建议：

```text
简单 CRUD / 小 UI / 明确 Bug       → L1
普通正式业务功能或产品页面         → L2
身份、支付、多租户、复杂迁移、旗舰 UI → L3
```

高档 Prompt 不是默认选项。优先选择能够覆盖风险的最低档，减少上下文、安装和执行成本。

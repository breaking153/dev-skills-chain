# 概念

AI 游戏开发涉及开发期的代码与资源生成，以及运行时的角色决策与内容生成。本文围绕能巡逻、追逐并对话的 NPC，先建立技术分工，再用注释代码串起状态变化与对话结果处理；范围限定为小型单人游戏。

| 技术 | 输入与产出 | 本例中的位置 |
| --- | --- | --- |
| 开发期 AI 辅助 | 行为要求、项目上下文 → 代码或资源草稿 | 帮助制作游戏，产物仍需审阅与验证 |
| 有限状态机 | 感知结果、交互事件 → 当前行为 | 用明确条件控制巡逻、追逐与交谈 |
| 行为树与黑板 | 条件、动作分支、共享数据 → 行为选择 | 行为增多时可替换决策组织方式；[官方示例](https://dev.epicgames.com/documentation/en-us/unreal-engine/behavior-tree-in-unreal-engine---quick-start-guide)展示巡逻、追逐和黑板配合 |
| 学习策略 | 训练时的观察、动作与奖励 → 策略；运行时的观察 → 动作 | 适合可反复模拟并评价结果的任务，本文不训练模型；参见 [ML-Agents](https://unity-technologies.github.io/ml-agents/ML-Agents-Overview/) |
| 对话模型 | 角色背景、允许知道的事实、玩家话语 → 台词与动作建议 | 丰富表达，由游戏校验并决定动作是否执行 |

开发期辅助和项目内模型推理具有不同的接入位置，[Unity AI 文档](https://docs.unity.com/en-us/ai)也分别列出这两类能力。生成过代码的 NPC，其运行方式仍由实际执行的程序决定。

# 开发路径

下文两段 JavaScript 是据标准语言与 Node.js API 编写的独立教学示例，各自保存为 `.mjs` 即可运行，无第三方依赖。它们验证游戏逻辑，不包含画面、碰撞、网络请求或模型推理；断言使用 [Node.js `node:assert/strict`](https://nodejs.org/api/assert.html)。

实际画面接入只选择 Godot 这一条示例路径：NPC 场景组合显示、碰撞、感知和导航节点，控制脚本读取感知结果并更新行为。Godot 用节点树组成场景，场景可重复实例化，参见[节点与场景](https://docs.godotengine.org/en/stable/getting_started/step_by_step/nodes_and_scenes.html)。本文不创建项目；JavaScript 示例的规则需移植到引擎脚本，并连接真实的感知与移动接口。

# AI 辅助开发与资源制作

给代码助手的输入应包含场景组成、感知数据与行为条件，例如“敌对且可见时追逐，失去视线两秒后巡逻；非敌对且靠近时允许交谈，主动结束后等待下一次交互”。这些条件可以直接形成下文的调用与断言。生成代码仍需检查 API 版本、状态边界和场景表现。

图像或音频生成先用于资源草稿，再检查动画尺寸、朝向、轮廓连续性和声音衔接。Godot 的源资源旁保存 `<asset>.import` 导入配置，内部产物位于 `.godot/imported/`；维护源资源与配置，内部产物可重新生成，参见[资源导入流程](https://docs.godotengine.org/en/stable/tutorials/assets_pipeline/import_process.html)。

# 运行时行为

## 感知、状态与移动

有限状态机保存当前行为，通过感知与事件决定下一状态。下面用无障碍的一维坐标实际移动 NPC：`dt` 来自游戏更新间隔，单位为秒；位置、敌对关系、可见性和距离条件由游戏提供，交互与结束是当次更新的事件。巡逻点、速度和两秒记忆均为本例规则。

```javascript
// npc-state.mjs：可独立运行；感知由测试输入，移动仅覆盖无障碍直线。
import assert from "node:assert/strict";

const npc = {
  state: "PATROL", x: 0, patrolTarget: 4, lastSeenX: 0, lostSeconds: 0,
  session: null, sessionSequence: 0 // session 为 null 表示没有活跃对话。
};

function tick(npc, dt, {
  playerX = 0, exists = true, visible = false, hostile = false,
  near = false, interact = false, end = false, invalid = false
} = {}) {
  if (!Number.isFinite(dt) || dt < 0 || !Number.isFinite(playerX)) {
    throw new TypeError("dt 必须为非负有限秒数，playerX 必须为有限坐标");
  }
  if (exists && visible) {
    npc.lastSeenX = playerX;       // 只能用实际看见的位置更新追逐目标。
    npc.lostSeconds = 0;
  } else {
    npc.lostSeconds += dt;
  }

  const chase = exists && hostile && (visible ||
    (npc.state === "CHASE" && npc.lostSeconds < 2));
  const talk = exists && !hostile && near && !end && !invalid &&
    (interact || npc.state === "TALK"); // 结束优先于同帧交互。
  const next = chase ? "CHASE" : talk ? "TALK" : "PATROL";
  if (next !== npc.state) {
    npc.session = next === "TALK" ? ++npc.sessionSequence : null;
    npc.state = next;             // 离开交谈即作废旧会话，供响应端判过期。
  }

  let target;
  switch (npc.state) {
    case "PATROL":
      if (Math.abs(npc.x - npc.patrolTarget) < 0.01) {
        npc.patrolTarget = npc.patrolTarget === 4 ? 0 : 4;
      }
      target = npc.patrolTarget;
      break;
    case "CHASE": target = npc.lastSeenX; break;
    case "TALK": return npc.state; // 交谈时保持位置。
  }
  const distance = target - npc.x;
  npc.x += Math.sign(distance) * Math.min(Math.abs(distance), 2 * dt);
  return npc.state;                // 每秒两单位，单次位移不会越过目标。
}

assert.equal(tick(npc, 1), "PATROL");
assert.equal(npc.x, 2);
assert.equal(tick(npc, 0, { hostile: true, visible: true, playerX: 8 }), "CHASE");
assert.equal(tick(npc, 1, { hostile: true }), "CHASE");
assert.equal(npc.x, 4);             // 丢失视线后仍向最后看见的位置移动。
assert.equal(tick(npc, 1, { hostile: true }), "PATROL"); // 达到两秒。
tick(npc, 0, { hostile: true, visible: true });
assert.equal(tick(npc, 0, { hostile: false }), "PATROL");
assert.equal(tick(npc, 0, { near: true, interact: true }), "TALK");
const session = npc.session;
tick(npc, 0, { near: true, interact: true });
assert.equal(npc.session, session); // 重复交互不重复建立会话。
assert.equal(tick(npc, 0, { near: true, interact: true, end: true }), "PATROL");
assert.equal(npc.session, null);
assert.equal(tick(npc, 0, { near: true }), "PATROL"); // 必须再次主动交互。
tick(npc, 0, { near: true, interact: true });
assert.equal(tick(npc, 0, { exists: false, near: true }), "PATROL");
console.log("npc-state: passed");
```

引擎中的导航负责绕障路线，物理移动负责位移与碰撞。Godot 的 `NavigationAgent2D` 提供路径相关计算，实际角色移动仍由脚本处理，参见[导航代理](https://docs.godotengine.org/en/stable/tutorials/navigation/navigation_using_navigationagents.html)。上例只演示状态与直线位移；导航不可达、碰撞和目标销毁后的场景资源清理，需要在真实关卡中接入并验证。

# 对话服务接入

## 结构化结果与游戏动作

玩家提交一句话时，服务端将角色背景、允许知道的场景事实、必要的近期对话与本句输入交给模型。结构化输出可以约束字段类型与枚举，应用仍需验证值与业务条件，参见[结构化输出](https://ai.google.dev/gemini-api/docs/structured-output)。模型提出函数或动作建议后，由应用执行对应逻辑，参见[函数调用机制](https://ai.google.dev/gemini-api/docs/function-calling)。

下面只实现响应接收端。外部输入 `raw` 是模型服务返回的 JSON 字符串，协议固定为 `{ action: "say" | "claim_reward", text: string }`；`ticket` 由应用在请求发出前创建并由回调携带，不能从模型正文读取。示例使用固定输入演示校验，没有发送请求或调用真实模型。

```javascript
// npc-dialogue.mjs：独立运行；与上例通过 state、session 的含义衔接。
import assert from "node:assert/strict";

const npc = {
  state: "TALK", session: 1, requestId: 0, pending: false,
  questReady: true, rewardClaimed: false, gold: 0 // 游戏拥有的可信状态。
};

function begin(npc) {
  if (npc.state !== "TALK" || npc.session === null || npc.pending) {
    throw new Error("当前不能发起新对话请求");
  }
  npc.pending = true;
  return { session: npc.session, id: ++npc.requestId };
}

function receive(npc, ticket, raw) {
  if (npc.state !== "TALK" || !npc.pending ||
      ticket.session !== npc.session || ticket.id !== npc.requestId) {
    return { status: "stale", text: "" }; // 旧会话、超时或被替换的请求。
  }
  npc.pending = false;                     // 本次响应只允许消费一次。
  let reply;
  try {
    if (typeof raw !== "string" || raw.length > 4096) throw new Error();
    reply = JSON.parse(raw);              // 解析为数据，绝不执行生成的代码。
    if (!reply || Array.isArray(reply) || typeof reply !== "object" ||
        Object.keys(reply).sort().join(",") !== "action,text" ||
        !["say", "claim_reward"].includes(reply.action) ||
        typeof reply.text !== "string" || reply.text.length > 200) {
      throw new Error();                  // 拒绝未知动作、额外字段及错误类型。
    }
  } catch {
    return { status: "invalid", text: "暂时无法回答，请重试。" };
  }

  switch (reply.action) {
    case "say": return { status: "spoken", text: reply.text };
    case "claim_reward":
      if (!npc.questReady || npc.rewardClaimed) {
        return { status: "blocked", text: "条件未满足或奖励已经领取。" };
      }
      npc.rewardClaimed = true;           // 领取记录与金币都由游戏修改。
      npc.gold += 10;                     // 仅允许当前任务的固定奖励。
      return { status: "applied", text: "已领取 10 金币。" };
  }
}

const reward = '{"action":"claim_reward","text":"请求领取奖励"}';
assert.equal(receive(npc, begin(npc), reward).status, "applied");
assert.equal(receive(npc, begin(npc), reward).status, "blocked");
assert.equal(npc.gold, 10);               // 重试不能重复发奖。
for (const raw of ['{', 'null', '{"action":"give_gold","text":"金币"}',
                   '{"action":"say","text":7}']) {
  assert.equal(receive(npc, begin(npc), raw).status, "invalid");
}
const timedOut = begin(npc);
npc.pending = false;                     // 超时回调使请求失效，仍可继续交谈。
const current = begin(npc);
assert.equal(receive(npc, timedOut, reward).status, "stale");
assert.equal(receive(npc, current, '{"action":"say","text":"你好"}').text, "你好");
const leaving = begin(npc);
npc.state = "PATROL"; npc.session = null; npc.pending = false;
assert.equal(receive(npc, leaving, reward).status, "stale");
assert.equal(npc.gold, 10);
console.log("npc-dialogue: passed");
```

接入时在超时或网络失败后结束等待并显示预设台词；退出会话时关闭界面、清除等待并尝试取消请求。会话与请求编号过滤仍须保留，因为取消未必能停止远端计算。请求只随玩家提交话语触发，每帧移动继续独立执行。

台词以纯文本展示，游戏结果由受控动作返回；自由台词仍可能描述错误事实。流式输出可提前显示部分内容，但动作需等完整结果校验后执行，参见[流式输出与延迟](https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-latency)。本例领取记录只存在内存中；跨存档或多人服务需要在权威存储中原子记录领取与奖励。

# 运行与验证

分别保存两段代码后运行 `node npc-state.mjs` 和 `node npc-dialogue.mjs`。断言失败会抛错；成功时分别打印 `npc-state: passed` 和 `npc-dialogue: passed`。

本文两段代码已在 Node.js v24.12.0 下执行，内置断言通过。验证范围是状态、直线位移、会话变化、结构校验、动作限制和迟到响应过滤；未验证 Godot 场景、真实模型、网络超时调度、碰撞与导航效果。

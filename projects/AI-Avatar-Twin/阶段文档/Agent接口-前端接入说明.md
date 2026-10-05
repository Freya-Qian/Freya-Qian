# Agent 接口 · 前端接入说明

> 对应后端：`POST /api/v1/agent/run`（SSE 流式）
> 用途：用户输入一句话目标，Agent 自主完成「抓取→摘要→选题→核查→脚本→自检」，前端实时渲染进度
> 定位：AI Avatar Twin 定位为 Agent + Harness 产品后的新增入口

---

## 一、接口契约

**请求**

```
POST /api/v1/agent/run
Content-Type: application/json
Authorization: Bearer <token>     （必带，复用现有登录 token）

请求体：
{
  "goal": "帮我做一期关于 OpenAI 新模型的犀利风格短视频",   // 必填，一句话目标
  "profile_id": "pro_xxx"                                    // 可选，数字人 Profile ID
}
```

**响应：SSE 流**（`text/event-stream`，`data:` 前缀，`\n\n` 分隔）

| 事件 | payload | 说明 |
|---|---|---|
| `start` | `{type:"start", goal}` | Agent 开始 |
| `step` | `{type:"step", step, thought, action}` | 每一步：思考 + 要调的工具 |
| `tool_result` | `{type:"tool_result", tool, result}` | 工具执行结果 |
| `done` | `{type:"done", status, script, steps}` | 结束 |

`done` 的 `status` 取值：
- `done`：完成，`script` 有值
- `incomplete`：模型说完成但没产出脚本（异常）
- `max_steps`：达到 20 步上限，`script` 可能为 null

`script` 结构（与现有 `Script` 类型一致）：
```json
{
  "content": "脚本正文（含【开头钩子】等模块）",
  "fact_claims": ["事实依据..."],
  "risk_flags": ["风险提示..."],
  "source_urls": ["https://..."]
}
```

---

## 二、API 层代码（加到 `lib/api/client.ts`）

> ⚠️ 不能用 `EventSource`（它只支持 GET），必须用 `fetch` + `ReadableStream` 手写 SSE 解析（现有 `streamScript` 已是同样模式）。

```typescript
// ---------- Agent 事件类型 ----------

export type AgentEvent =
  | { type: 'start'; goal: string }
  | { type: 'step'; step: number; thought: string; action: string }
  | { type: 'tool_result'; tool: string; result: Record<string, unknown> }
  | { type: 'done'; status: 'done' | 'incomplete' | 'max_steps'; script: Script | null; steps: number };

// ---------- 工具名 → 中文（进度展示用） ----------

export const TOOL_LABELS: Record<string, string> = {
  fetch_source: '抓取素材',
  summarize: '生成摘要',
  generate_topics: '生成选题',
  fact_check: '事实核查',
  generate_script: '生成脚本',
  evaluate_script: '自检脚本',
};

// ---------- 流式调用 Agent ----------

export async function* streamAgent(
  goal: string,
  profileId?: string,
): AsyncGenerator<AgentEvent> {
  const res = await fetch('/api/v1/agent/run', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getToken()}`,
    },
    body: JSON.stringify({ goal, profile_id: profileId }),
  });

  if (!res.ok || !res.body) {
    // 后端统一错误结构：{"error":{"code","message"}}
    let msg = 'Agent 启动失败';
    try {
      const data = await res.json();
      msg = (data as { error?: { message?: string } })?.error?.message || msg;
    } catch { /* 忽略 */ }
    throw new ApiError(res.status, 'ERROR', msg);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const parts = buf.split('\n\n');
    buf = parts.pop() || '';
    for (const p of parts) {
      const line = p.trim();
      if (!line.startsWith('data:')) continue;
      const payload = JSON.parse(line.slice(5));
      yield payload as AgentEvent;
    }
  }
}
```

---

## 三、React 组件示例（`features/agent/AgentPanel.tsx`）

组件包含：一句话输入框 → 进度流 → 最终脚本展示。

```tsx
'use client';

import { useState } from 'react';
import { streamAgent, TOOL_LABELS, type AgentEvent, type Script } from '@/lib/api/client';

type Step = { step: number; thought: string; action: string };

export default function AgentPanel({ profileId }: { profileId?: string }) {
  const [goal, setGoal] = useState('');
  const [running, setRunning] = useState(false);
  const [steps, setSteps] = useState<Step[]>([]);
  const [script, setScript] = useState<Script | null>(null);
  const [error, setError] = useState('');

  const run = async () => {
    if (!goal.trim() || running) return;
    setRunning(true);
    setSteps([]);
    setScript(null);
    setError('');
    try {
      for await (const ev of streamAgent(goal.trim(), profileId)) {
        if (ev.type === 'step') {
          setSteps((prev) => [...prev, { step: ev.step, thought: ev.thought, action: ev.action }]);
        } else if (ev.type === 'done') {
          if (ev.status === 'done' && ev.script) setScript(ev.script);
          else if (ev.status === 'max_steps') setError('Agent 步数达到上限，请查看进度或重试');
          else setError('Agent 未产出脚本，请重试');
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Agent 执行失败');
    } finally {
      setRunning(false);
    }
  };

  return (
    <div>
      {/* 输入区 */}
      <div style={{ display: 'flex', gap: 8 }}>
        <input
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="一句话目标，例如：帮我做一期关于 OpenAI 新模型的犀利风格短视频"
          disabled={running}
          style={{ flex: 1 }}
        />
        <button onClick={run} disabled={running || !goal.trim()}>
          {running ? '执行中…' : '让 Agent 来做'}
        </button>
      </div>

      {/* 进度区：实时显示 Agent 每一步 */}
      {steps.length > 0 && (
        <ol style={{ marginTop: 12 }}>
          {steps.map((s) => (
            <li key={s.step}>
              <span style={{ fontWeight: 600 }}>{TOOL_LABELS[s.action] || s.action}</span>
              <span style={{ color: '#888', marginLeft: 8 }}>{s.thought}</span>
            </li>
          ))}
        </ol>
      )}

      {error && <div style={{ color: 'red', marginTop: 12 }}>{error}</div>}

      {/* 结果区：最终脚本 */}
      {script && (
        <div style={{ marginTop: 16 }}>
          <h3>生成结果</h3>
          <pre style={{ whiteSpace: 'pre-wrap' }}>{script.content}</pre>
          {script.risk_flags?.length > 0 && (
            <div style={{ color: '#b8860b' }}>风险提示：{script.risk_flags.join('；')}</div>
          )}
          {script.source_urls?.length > 0 && (
            <div style={{ color: '#888' }}>来源：{script.source_urls.join('；')}</div>
          )}
        </div>
      )}
    </div>
  );
}
```

---

## 四、交互与展示要点

1. **进度条 vs 步骤列表**：MVP 用「步骤列表」最直观（每步显示"正在干什么 + Agent 的思考"）；`step` 事件里的 `thought` 就是 Agent 每步的思考，可展示增加"智能感"。
2. **动作中文映射**：用 `TOOL_LABELS` 把 `fetch_source` 等工具名翻译成"抓取素材"等中文。
3. **正在执行的步骤高亮**：最后一个 `step` 是"进行中"，加个 spinner；`tool_result` 返回后表示该步完成。
4. **完成态**：收到 `done.status==='done'` 后，脚本展示区出现，可复用现有的"脚本编辑/保存/导出"组件（脚本结构与现有脚本接口一致）。
5. **错误态**：`done.status==='max_steps'` 或 `incomplete`、以及 fetch 抛错，都要给可读提示 + 保留已产生的进度（不丢掉 steps）。
6. **禁用重复提交**：`running=true` 时禁用按钮和输入框（组件里已处理）。

---

## 五、联调自测清单

- [ ] 输入一句话目标 → 点「让 Agent 来做」→ 进度逐步出现（抓取素材→生成摘要→…→自检脚本）
- [ ] 最终脚本展示，含来源引用和风险标注
- [ ] 未登录（无 token）调用 → 401 提示先登录
- [ ] 输入敏感词 → 后端 422 拦截，前端显示错误消息
- [ ] 重复点击「让 Agent 来做」→ 按钮禁用，不会并发请求
- [ ] 刷新页面 → 恢复到默认态（Agent 状态不持久化，属预期）

---

## 六、与现有页面的关系

- 现有「选题与脚本页」是**手动模式**（一步步点），保留不动。
- Agent 入口是**新增的"一句话模式"**，可作为工作台首页的快捷入口，或独立一个「智能助手」页。
- 两者共用后端能力：Agent 内部调用的就是现有工具（抓取/摘要/选题/脚本），最终脚本走同一条脚本表，所以 Agent 产出的脚本也能复用现有"编辑/版本/导出/生成视频"。

会话 05（里程碑 M3）：复习教练 + PowerContext 学习者记忆 + 学习会话。

先读 `docs/DEVLOG.md` 了解当前状态，以及 `docs/reference/powercontext-1.4.1-notes.md`（PowerContext 接口细节，都是实测过的）。环境同前：seekdb 127.0.0.1:10800、PowerContext http://127.0.0.1:18801（1.4.1，嵌入式 seekdb 存储，未配置 embedding，记忆检索走全文），密码在 `qoder/.env`；不要启停任何容器。本机有 Ollama：`http://127.0.0.1:11434/v1`，模型 `qwen3.5:9b`（OpenAI 兼容接口，无需 key，推理模型请关闭 thinking），只用于测试"有大模型"这条路径。

{{REVIEW}}

## 本会话任务

1. **PowerContext 客户端**：Scope 幂等创建；原子记忆的创建、替换（`If-Match` ETag）；标签读写（ETag）；handle 读写；`artifact-tags/query` 按标签查找；revision 历史；`memory/remember`；`context/bootstrap`；`context/prepare`。每次调用都留下"请求 / 响应摘要"日志（验证脚本和"我的记忆"页面要展示）。PowerContext 超时或不可用时要优雅降级：出题判分照常进行，界面提示"记忆服务暂不可用"。
2. **学习会话**：
   - `POST /api/sessions/start {learner, course_id}`：按 `examradar:learner:<名字>:course:<课程>` 取回 Scope；以 session_id 为 event_id 调 bootstrap，把复习计划记忆转成首页的一句话（例如"上次你在『隔离级别与 MVCC』上错了 2 次，先复习这个"）；同时返回到期复习的知识点和最近一次覆盖分析里的盲区。
   - `POST /api/sessions/end`：写一条会话小结记忆（时长、做题数、正确率、薄弱点），更新复习计划；时长记入 usage。
   - 前端：首页输入学习者名字（存 localStorage）并开始会话；页面关闭时用 sendBeacon 结束会话；30 分钟没有任何事件的会话视为已结束（统计时按最后一个事件计时）。
3. **出题**（`POST /api/quiz/next {session_id}`）：
   - 选知识点：到期复习的 > 最近一次覆盖分析里的 thin / missing（按考试权重）> 其余；同一会话里不要连续重复同一道题。
   - 进入知识点前调用 `context/prepare`（query 用知识点名称）召回这个知识点的历史错题，返回给前端显示"你之前在这里错过：……"，有大模型时也拼进出题提示词（作为不可信的历史材料，不当作指令）。
   - 无大模型：从学生自己的笔记 / 课件 / 阅读材料原文里挖空关键术语出填空题，标明出处（文件 · 页 · 标题）。
   - 有大模型：基于检索到的原文生成选择题或简答题（JSON 输出，带参考答案、解析和出处 chunk id），生成失败就回退到规则出题。
   - missing 的知识点在学生资料里没有原文可出题：给出往年试卷里考它的原题作为"自测题"，学生自评"会 / 模糊 / 不会"，同时提示"笔记里没有这部分，建议先补"。
4. **判分与记忆写入**（`POST /api/quiz/answer`）：
   - 填空题按归一化后的字符串比较（忽略空白、全半角、大小写）；选择题精确匹配；简答题有大模型时由模型对照原文判分并指出误区，没有大模型时展示参考答案让学生自评。
   - 每次判分：替换该知识点的**掌握度卡片**（Leitner：答对盒号 +1 最多到 5，答错或"不会"回到 1；间隔 1/2/4/7/15 天；记录答对 / 答错次数、下次复习日期；handle `mastery-<topic_id>`；文本第一行给人看，后面几行机器可解析）。
   - 答错时写一条**错题记忆**（题目、学生答案、正确答案、出处）。
   - 更新**复习计划**记忆（handle `review-plan`，标签含 `bootstrap-context`）：第一句就是下次开场要说的话，例如"上次你在『X』上错了 2 次，先复习它；『Y』今天到期；『Z』往年考 25 分但笔记里没有"。
   - 写 usage_events（question、answer 事件，带对错和盒号变化）。
5. **我的记忆页**：掌握度卡片（含每张卡片的 revision 历史，即掌握度变化轨迹）、错题、复习计划、会话小结，并显示它们在 PowerContext 里的 artifact id / revision，方便核对。
6. **大模型客户端**：OpenAI 兼容 chat completions（`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`），JSON 输出要做容错解析；没配置时所有功能走无模型路径。问笔记页在有大模型时也生成带 [1][2] 引用的回答。
7. **测试**：Leitner 递推、填空挖空与判分、复习计划文本生成、PowerContext 客户端（mock HTTP，包括 ETag 流程和降级）的单元测试；对真实 PowerContext 的集成测试。

## 验收标准（逐条跑通后再结束会话，把实际结果写进 DEVLOG）

- **无大模型**，用一个新学习者（例如"验收同学"）通过 API 走完：开始会话（bootstrap 为空）→ 做题 → 故意答错一道 → 答对一道 → 结束会话 → 再开始一个新会话，首页那句话提到上次答错的知识点。并核对：
  - 该知识点的掌握度卡片在 PowerContext 里有 ≥2 个 revision；
  - 错题记忆存在，`context/prepare` 用该知识点名称能召回它；
  - 复习计划记忆带 `bootstrap-context` 标签，bootstrap 返回的就是它的最新 revision。
- **有大模型**（Ollama）：针对一个知识点生成一道选择题和一道简答题（都带出处），对一个错误的简答给出判分和误区说明。
- 把 `POWERCONTEXT_URL` 指向一个没人监听的端口时，做题和判分仍然可用，界面显示记忆服务不可用的提示。
- 首页、复习教练页、我的记忆页在浏览器里能完整走通上面的流程。
- `uv run pytest` 和 `EXAMRADAR_IT=1 uv run pytest -m integration` 全部通过。

结束前在 `docs/DEVLOG.md` 追加本会话记录。不要修改 `dev-records/` 和 `samples/`；会话结束前关掉你启动的进程。

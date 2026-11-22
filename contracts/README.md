# 首轮联调接口

## HTTP

[OpenAPI 快照](openapi.json)是当前实现的 HTTP 契约。开发时也可以打开 API 的 `/docs`。前端仅通过相对路径调用 API，Vite 将 `/api` 请求转发给后端。

| 操作 | 请求 | 成功响应 |
| --- | --- | --- |
| 查内置策略及数据 | `GET /api/v1/catalog` | `200` 目录 |
| 创建提交 | `POST /api/v1/submissions` | `201` 提交 |
| 查提交历史 | `GET /api/v1/submissions` | `200` 提交列表 |
| 发起验证 | `POST /api/v1/runs`，带 `Idempotency-Key` | `202` 任务 |
| 查任务状态 | `GET /api/v1/runs/{run_id}` | `200` 任务 |
| 查净值和成交 | `GET /api/v1/runs/{run_id}/result` | `200` 结果。结果未就绪返回 `409`。 |

业务错误返回 `code` 与 `message`。请求字段校验采用 OpenAPI 中定义的 FastAPI `422` 结构。验证的幂等键在本地数据库内唯一，同键同参数返回相同任务，同键异参返回冲突。接入认证后应把幂等键范围收敛到队伍。

内置策略提交请求示例。

```json
{"name":"因子排序基线","source":{"kind":"baseline","baseline_id":"factor-rank"}}
```

拿到提交 ID 后创建任务。状态为 `QUEUED`、`RUNNING`、`SUCCEEDED` 或 `FAILED`。成功后请求结果。

```json
{"submission_id":"2556983a-4687-41ef-be99-455e8f80a071","dataset_id":"synthetic-v1"}
```

调整路由和模型后，从仓库根目录更新契约，并在前端目录重新生成类型。

```powershell
uv run --locked python -m agentquant.api contracts/openapi.json
npm --prefix apps/web run generate:api
```

## 进程和 Python 交接

| 生产方 → 消费方 | 契约 |
| --- | --- |
| API → Worker | `RunSpec`，固定运行 ID、提交、数据、规则版本与种子。首轮策略引用是 `baseline_id`。 |
| Worker → API | `EvaluationResult`，含摘要、逐日净值、成交。货币和比率为十进制字符串。完成时校验任务租约。 |
| 数据 → 评测 | `Dataset`，首轮使用 [synthetic-v1.json](../src/agentquant/synthetic-v1.json)，含日期、决策时间、可见因子及成交参考数据。 |
| 评测 → 策略 | `Snapshot` 和 `StrategyContext`。快照含当时可见的匿名因子、可选标的、现金和持仓。 |
| 策略 → 评测 | `KEEP` 或 `TARGET`。目标权重用整数基点，每个标的只出现一次，合计最多 10,000。 |

```json
{"action":"TARGET","weights":[{"asset_id":"A001","weight_bps":5000}]}
```

类型定义见 [contracts.py](../src/agentquant/contracts.py)、[sdk.py](../src/agentquant/sdk.py) 和 [evaluator.py](../src/agentquant/evaluator.py)。接口有变化时，提交模型、OpenAPI 快照、生成类型和受影响的测试。

首轮演示只运行服务端内置策略，使用本地 SQLite 和人工数据。真实账号、策略 ZIP、沙箱、正式行情以及封榜评审排在后续迭代。

## 数据接入交接

数据工作包交付标准化数据包和版本清单。清单至少记录数据集 ID、模式版本、数据分区、覆盖交易日、可用时间口径、文件校验值和发布范围。训练和验证下载包与主办方评测快照按发布范围交付。供应方凭据保留在采集侧。

赛务后端按数据集 ID 登记版本及授权信息。评测 Worker 按运行清单固定的数据集 ID 读取快照，校验版本和模式后交给评测器。前端通过业务 API 展示已授权的目录和下载入口。当前 [synthetic-v1.json](../src/agentquant/synthetic-v1.json) 可用于提前联调，真实数据包以评测输入模式和赛前数据规则验收。

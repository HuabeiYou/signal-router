# Signal Router MVP 设计文档

## 1. 目标与边界

### 1.1 业务目标
本项目用于接收外部交易信号，进行二次加工后，按可配置规则转发给多个企业微信群机器人（Webhook URL）。

### 1.2 MVP 范围
- 接收外部信号（HTTP Webhook）
- 记录历史信号（可查询）
- 可配置“包含某字段 -> 转发到某些机器人”的规则
- 提供简单 Web 页面用于规则管理与历史查看
- 具备基础安全能力（入站鉴权、管理员鉴权、敏感数据保护）

### 1.3 非目标（MVP 不做）
- 复杂规则编排（嵌套条件、脚本执行、回溯计算）
- 多消息渠道（仅企业微信机器人）
- 高可用集群、分布式队列
- 复杂权限系统（RBAC）

---

## 2. 技术选型

### 2.1 后端
- Python 3.11+
- FastAPI
- Uvicorn
- SQLModel（基于 SQLAlchemy）

选择原因：
- 开发速度快、依赖轻
- API 与模板渲染都能覆盖
- 后续扩展到 PostgreSQL 成本低

### 2.2 数据库
- SQLite（MVP）

选择原因：
- 单文件部署简单
- 无需额外数据库服务
- 足够支持小规模信号路由场景

### 2.3 页面渲染
- Jinja2 + Bootstrap

选择原因：
- 不做前后端分离，减少工程复杂度
- 可快速实现规则 CRUD 与历史列表

### 2.4 部署
- Docker 单容器部署（优先）
- 可选本机运行（systemd）

---

## 3. 系统设计

### 3.1 核心流程
1. 外部系统调用 `POST /webhook/{inbound_token}` 发送信号。
2. 服务校验 token，写入 `signals`（原始载荷 + 解析字段）。
3. 规则引擎读取启用规则，按优先级匹配。
4. 命中规则后，调用对应企业微信机器人 Webhook。
5. 每次转发写入 `deliveries`，记录状态与响应摘要。
6. 管理员可在 Web 页面查看/编辑规则和查看历史。

### 3.2 信号加工策略（MVP）
- 入站 body 统一存储原文 JSON。
- 提供最小字段提取：
  - 若 payload 已是结构化 JSON，直接使用其 key。
  - 若 payload 含 `text.content` 或 `markdown.content`，做 key-value 提取（如 `symbol=BTCUSDT`）。
- 最终形成 `parsed_fields`（JSON 对象）供规则匹配。

### 3.3 规则匹配策略（MVP）
- 仅支持 `contains_field`：字段存在即命中。
- 多条件关系仅支持 `AND`（全部满足才命中）。
- 命中后执行动作 `forward_wecom_webhooks`。
- 默认“一个信号可命中多条规则并转发多次”。

---

## 4. 接口契约

## 4.1 外部入站接口

### POST `/webhook/{inbound_token}`

用途：接收外部交易信号。

Path 参数：
- `inbound_token` (string, required): 入站鉴权 token。

请求头：
- `Content-Type: application/json`

请求体（兼容示例，服务不强依赖固定字段）：

```json
{
  "msgtype": "markdown",
  "markdown": {
    "content": "strategy=breakout\nsymbol=BTCUSDT\nside=BUY\nprice=62000"
  },
  "source": "external-signal-provider"
}
```

响应：

```json
{
  "ok": true,
  "signal_id": 123,
  "matched_rule_ids": [2, 5],
  "delivery_count": 3
}
```

错误码：
- `401` token 无效
- `400` body 非法
- `500` 服务内部错误

---

## 4.2 管理后台接口（页面）

### GET `/admin/login`
- 登录页

### POST `/admin/login`
- 提交管理员账号密码，创建会话

### POST `/admin/logout`
- 退出登录

### GET `/admin/rules`
- 规则列表页（支持状态筛选）

### GET `/admin/rules/new`
- 新建规则页

### POST `/admin/rules`
- 创建规则

### GET `/admin/rules/{rule_id}/edit`
- 编辑规则页

### POST `/admin/rules/{rule_id}`
- 更新规则

### POST `/admin/rules/{rule_id}/toggle`
- 启用/停用规则

### GET `/admin/signals`
- 历史信号列表页（支持时间/状态筛选）

### GET `/admin/signals/{signal_id}`
- 信号详情页（原始内容、解析字段、命中规则、转发结果）

> 说明：MVP 以服务端渲染为主，后台接口可直接返回 HTML，不强制提供完整 JSON Admin API。

---

## 5. 规则结构设计

## 5.1 规则对象（数据库持久化）

```json
{
  "name": "BTC信号转发",
  "enabled": true,
  "priority": 100,
  "conditions": {
    "op": "and",
    "items": [
      {
        "type": "contains_field",
        "field": "symbol"
      },
      {
        "type": "contains_field",
        "field": "side"
      }
    ]
  },
  "action": {
    "type": "forward_wecom_webhooks",
    "targets": [
      "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxx",
      "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=yyyy"
    ]
  }
}
```

## 5.2 字段约束
- `name`: 1~100 字符，唯一
- `enabled`: 布尔
- `priority`: 整数，越大越先匹配
- `conditions.op`: 固定 `and`（MVP）
- `conditions.items[].type`: 固定 `contains_field`（MVP）
- `conditions.items[].field`: 非空，匹配 `parsed_fields` 的 key
- `action.type`: 固定 `forward_wecom_webhooks`
- `action.targets`: 1..N 个企业微信机器人 Webhook URL

## 5.3 转发消息格式（MVP）
- 默认转发为企业微信 `markdown` 消息
- 内容包含：
  - 信号时间
  - 解析字段（key=value）
  - 原始载荷简版（截断）

示例：

```json
{
  "msgtype": "markdown",
  "markdown": {
    "content": "## Signal Routed\nsource=external-signal-provider\nsymbol=BTCUSDT\nside=BUY\nprice=62000"
  }
}
```

---

## 6. 数据表设计

## 6.1 `signals`
用途：保存所有接收到的信号。

字段：
- `id` INTEGER PRIMARY KEY AUTOINCREMENT
- `received_at` DATETIME NOT NULL
- `source` VARCHAR(100) NULL
- `raw_payload` JSON/TEXT NOT NULL
- `parsed_fields` JSON/TEXT NOT NULL
- `match_count` INTEGER NOT NULL DEFAULT 0
- `delivery_count` INTEGER NOT NULL DEFAULT 0

索引：
- `idx_signals_received_at(received_at)`
- `idx_signals_source(source)`

## 6.2 `rules`
用途：保存转发规则。

字段：
- `id` INTEGER PRIMARY KEY AUTOINCREMENT
- `name` VARCHAR(100) NOT NULL UNIQUE
- `enabled` BOOLEAN NOT NULL DEFAULT 1
- `priority` INTEGER NOT NULL DEFAULT 0
- `conditions_json` JSON/TEXT NOT NULL
- `action_json` JSON/TEXT NOT NULL
- `created_at` DATETIME NOT NULL
- `updated_at` DATETIME NOT NULL

索引：
- `idx_rules_enabled_priority(enabled, priority DESC)`

## 6.3 `deliveries`
用途：记录每次规则命中后的转发执行结果。

字段：
- `id` INTEGER PRIMARY KEY AUTOINCREMENT
- `signal_id` INTEGER NOT NULL REFERENCES signals(id)
- `rule_id` INTEGER NOT NULL REFERENCES rules(id)
- `target_masked` VARCHAR(255) NOT NULL
- `target_encrypted` TEXT NOT NULL
- `request_payload` JSON/TEXT NOT NULL
- `response_status` INTEGER NULL
- `response_body` TEXT NULL
- `success` BOOLEAN NOT NULL
- `error_message` TEXT NULL
- `created_at` DATETIME NOT NULL

索引：
- `idx_deliveries_signal_id(signal_id)`
- `idx_deliveries_rule_id(rule_id)`
- `idx_deliveries_created_at(created_at)`

## 6.4 建表 SQL（SQLite）

```sql
CREATE TABLE signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  received_at DATETIME NOT NULL,
  source VARCHAR(100),
  raw_payload TEXT NOT NULL,
  parsed_fields TEXT NOT NULL,
  match_count INTEGER NOT NULL DEFAULT 0,
  delivery_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_signals_received_at ON signals(received_at);
CREATE INDEX idx_signals_source ON signals(source);

CREATE TABLE rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name VARCHAR(100) NOT NULL UNIQUE,
  enabled BOOLEAN NOT NULL DEFAULT 1,
  priority INTEGER NOT NULL DEFAULT 0,
  conditions_json TEXT NOT NULL,
  action_json TEXT NOT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);
CREATE INDEX idx_rules_enabled_priority ON rules(enabled, priority DESC);

CREATE TABLE deliveries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  signal_id INTEGER NOT NULL,
  rule_id INTEGER NOT NULL,
  target_masked VARCHAR(255) NOT NULL,
  target_encrypted TEXT NOT NULL,
  request_payload TEXT NOT NULL,
  response_status INTEGER,
  response_body TEXT,
  success BOOLEAN NOT NULL,
  error_message TEXT,
  created_at DATETIME NOT NULL,
  FOREIGN KEY(signal_id) REFERENCES signals(id),
  FOREIGN KEY(rule_id) REFERENCES rules(id)
);
CREATE INDEX idx_deliveries_signal_id ON deliveries(signal_id);
CREATE INDEX idx_deliveries_rule_id ON deliveries(rule_id);
CREATE INDEX idx_deliveries_created_at ON deliveries(created_at);
```

---

## 7. 安全设计（MVP）

### 7.1 入站鉴权
- 使用高强度 `inbound_token`（环境变量）
- 未通过鉴权直接 `401`

### 7.2 管理后台鉴权
- 初版使用单管理员账号密码（环境变量）
- 登录成功后 Session Cookie（`HttpOnly`、`Secure`、`SameSite=Lax`）

### 7.3 敏感信息保护
- 目标 Webhook URL 使用 `Fernet` 对称加密后存储（密钥来自环境变量）
- 页面仅展示脱敏 URL（例如仅保留 key 前后片段）
- 日志中不打印完整 webhook/token

### 7.4 传输安全
- 部署时必须通过 HTTPS 暴露服务（Nginx/Caddy 终止 TLS）

### 7.5 风险控制
- 对入站请求设置大小限制（如 256KB）
- 对外发 HTTP 设置超时（如 5 秒）
- 基础频控（可选：按 IP 或 token）

---

## 8. 配置项（环境变量）

- `APP_ENV`：`dev` / `prod`
- `APP_HOST`：监听地址（默认 `0.0.0.0`）
- `APP_PORT`：监听端口（默认 `8000`）
- `DATABASE_URL`：默认 `sqlite:///./data/app.db`
- `INBOUND_TOKEN`：外部 webhook token
- `ADMIN_USERNAME`：后台管理员用户名
- `ADMIN_PASSWORD`：后台管理员密码
- `FERNET_KEY`：用于加密 webhook URL
- `LOG_LEVEL`：日志级别

---

## 9. 开发实施顺序

1. 搭建项目骨架、数据库模型、迁移初始化
2. 完成入站接口、信号落库、基础转发
3. 完成规则引擎（contains_field + and）
4. 完成管理页面（规则 CRUD + 历史查询）
5. 加固安全（登录会话、URL 加密、日志脱敏）
6. Docker 化和部署文档

---

## 10. 验收标准（MVP）

- 可通过 `POST /webhook/{token}` 成功接收并处理信号
- 至少支持 1 条规则：包含字段 `symbol` 时转发到指定企微机器人
- 管理页面可新增/编辑/启停规则
- 管理页面可查看信号历史与转发结果
- 数据库可追溯每条信号和每次转发
- 敏感配置不硬编码在代码中


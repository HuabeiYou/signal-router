# signal-router

交易信号接收与路由转发（MVP）。

## 1. 一键初始化

```bash
make init
```

## 2. 启动开发服务

```bash
make dev
```

## 3. 写入默认规则（仅保底转发）

```bash
make seed-demo FALLBACK_WEBHOOK='https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=your-fallback-key'
```

- 可选：写入 ETF 示例规则（用于演示）

```bash
make seed-example-etf \
  FALLBACK_WEBHOOK='https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=your-fallback-key' \
  ETF_WEBHOOK='https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=fake-etf-demo-key'
```

## 4. 使用

- 管理后台: `http://127.0.0.1:8000/admin/login`
- 入站接口: `POST /webhook/{INBOUND_TOKEN}`

示例请求：

```bash
curl -X POST "http://127.0.0.1:8000/webhook/${INBOUND_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "msgtype":"markdown",
    "markdown":{"content":"symbol=BTCUSDT\nside=BUY\nprice=62000"},
    "source":"demo"
  }'
```

## 5. 运行测试

```bash
make test
```

## 6. 功能覆盖

- 信号接收、字段提取、规则匹配
- 按规则转发到企业微信机器人 Webhook
- 规则管理页面（新建/编辑/启停）
- 历史信号和转发记录查看页面
- URL 加密存储与脱敏展示

## 7. 注意

- 生产环境请设置强随机 `INBOUND_TOKEN`、`ADMIN_PASSWORD`、`SESSION_SECRET`
- 生产环境必须设置 `FERNET_KEY`，否则服务会拒绝启动
- 管理后台 POST 操作已启用 CSRF 校验
- 仅允许转发到企业微信官方 webhook 域名（`https://qyapi.weixin.qq.com/cgi-bin/webhook/send`）
- 默认单条 webhook 最大 256KB，可通过 `MAX_WEBHOOK_PAYLOAD_BYTES` 调整
- 生产环境通过 HTTPS 暴露服务

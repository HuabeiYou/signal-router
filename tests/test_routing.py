import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from sqlmodel import Session, select


def _reload_app_modules():
    for name in ["app.main", "app.db", "app.config", "app.security"]:
        if name in sys.modules:
            del sys.modules[name]


class RoutingTestCase(unittest.TestCase):
    def test_etf_message_routes_to_fallback_and_matched_rule(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = os.path.join(tmpdir, "test.db")
            env = {
                "DATABASE_URL": f"sqlite:///{db_file}",
                "INBOUND_TOKEN": "test-token",
                "ADMIN_USERNAME": "admin",
                "ADMIN_PASSWORD": "admin-pass",
                "SESSION_SECRET": "test-session-secret",
                "FERNET_KEY": "",
            }

            with patch.dict(os.environ, env, clear=False):
                _reload_app_modules()

                from app.db import engine, init_db
                from app.main import app
                from app.models import Delivery, Rule, Signal
                from app.security import encrypt_text

                init_db()
                with Session(engine) as session:
                    session.add(
                        Rule(
                            name="保底转发",
                            enabled=True,
                            priority=1000,
                            conditions_json=json.dumps(
                                {"op": "and", "items": [{"type": "always"}]}, ensure_ascii=False
                            ),
                            action_json=json.dumps(
                                {
                                    "type": "forward_wecom_webhooks",
                                    "targets": [
                                        encrypt_text(
                                            "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=fallback-demo"
                                        )
                                    ],
                                },
                                ensure_ascii=False,
                            ),
                        )
                    )
                    session.add(
                        Rule(
                            name="ETF动量模型推送",
                            enabled=True,
                            priority=900,
                            conditions_json=json.dumps(
                                {
                                    "op": "and",
                                    "items": [{"type": "contains_text", "text": "ETF动量模型推送"}],
                                },
                                ensure_ascii=False,
                            ),
                            action_json=json.dumps(
                                {
                                    "type": "forward_wecom_webhooks",
                                    "targets": [
                                        encrypt_text(
                                            "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=etf-demo"
                                        )
                                    ],
                                },
                                ensure_ascii=False,
                            ),
                        )
                    )
                    session.commit()

                sent_targets = []

                async def fake_post(self, url, json=None, **kwargs):
                    sent_targets.append((url, json))
                    return httpx.Response(status_code=200, text='{"errcode":0}')

                payload = {
                    "msgtype": "markdown",
                    "markdown": {
                        "content": """📊 ETF动量模型推送
📊 ETF动量模型V2 - 每日推送

📅 数据更新至: 2026-02-09
📊 T+1应持有: 501018 (南方原油)
📉 当前回撤: 0.00%

💡 数据每日17:00更新
---
转发规则: ETF动量模型V2 - 每日推送
2026-02-09 17:01:07"""
                    },
                    "source": "wecom-group",
                }

                with patch.object(httpx.AsyncClient, "post", new=fake_post):
                    with TestClient(app) as client:
                        resp = client.post("/webhook/test-token", json=payload)

                self.assertEqual(resp.status_code, 200)
                body = resp.json()
                self.assertTrue(body["ok"])
                self.assertEqual(body["delivery_count"], 2)
                self.assertEqual(len(body["matched_rule_ids"]), 2)

                self.assertEqual(len(sent_targets), 2)
                sent_urls = {item[0] for item in sent_targets}
                self.assertIn("https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=fallback-demo", sent_urls)
                self.assertIn("https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=etf-demo", sent_urls)
                for _, sent_payload in sent_targets:
                    self.assertEqual(sent_payload, payload)

                with Session(engine) as session:
                    signals = session.exec(select(Signal)).all()
                    deliveries = session.exec(select(Delivery)).all()

                self.assertEqual(len(signals), 1)
                self.assertEqual(len(deliveries), 2)
                self.assertEqual(signals[0].match_count, 2)
                self.assertEqual(signals[0].delivery_count, 2)


if __name__ == "__main__":
    unittest.main()

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

    def test_news_message_can_match_contains_text_and_forward_raw_payload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = os.path.join(tmpdir, "test_news.db")
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
                from app.models import Delivery, Rule
                from app.security import encrypt_text

                init_db()
                with Session(engine) as session:
                    session.add(
                        Rule(
                            name="news关键词匹配",
                            enabled=True,
                            priority=100,
                            conditions_json=json.dumps(
                                {
                                    "op": "and",
                                    "items": [{"type": "contains_text", "text": "每日推送"}],
                                },
                                ensure_ascii=False,
                            ),
                            action_json=json.dumps(
                                {
                                    "type": "forward_wecom_webhooks",
                                    "targets": [
                                        encrypt_text(
                                            "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=news-demo"
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
                    "msgtype": "news",
                    "news": {
                        "articles": [
                            {
                                "title": "ETF动量模型V2 - 每日推送",
                                "description": "这是策略日报",
                                "url": "https://example.com/report/2026-02-12",
                                "picurl": "https://example.com/pic.png",
                            }
                        ]
                    },
                    "source": "wecom-group",
                }

                with patch.object(httpx.AsyncClient, "post", new=fake_post):
                    with TestClient(app) as client:
                        resp = client.post("/webhook/test-token", json=payload)

                self.assertEqual(resp.status_code, 200)
                body = resp.json()
                self.assertTrue(body["ok"])
                self.assertEqual(body["delivery_count"], 1)
                self.assertEqual(len(body["matched_rule_ids"]), 1)
                self.assertEqual(len(sent_targets), 1)
                self.assertEqual(sent_targets[0][1], payload)

                with Session(engine) as session:
                    deliveries = session.exec(select(Delivery)).all()
                self.assertEqual(len(deliveries), 1)

    def test_all_supported_wecom_msgtypes_are_accepted_and_forwarded_raw(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = os.path.join(tmpdir, "test_all_types.db")
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
                            name="all-msg-forward",
                            enabled=True,
                            priority=1000,
                            conditions_json=json.dumps({"op": "and", "items": [{"type": "always"}]}, ensure_ascii=False),
                            action_json=json.dumps(
                                {
                                    "type": "forward_wecom_webhooks",
                                    "targets": [
                                        encrypt_text(
                                            "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=all-types-demo"
                                        )
                                    ],
                                },
                                ensure_ascii=False,
                            ),
                        )
                    )
                    session.commit()

                payloads = [
                    {
                        "msgtype": "text",
                        "text": {"content": "hello world", "mentioned_list": ["@all"]},
                    },
                    {
                        "msgtype": "markdown",
                        "markdown": {"content": "## 标题\n内容"},
                    },
                    {
                        "msgtype": "markdown_v2",
                        "markdown_v2": {"content": "# 标题\n**加粗**"},
                    },
                    {
                        "msgtype": "image",
                        "image": {"base64": "R0lGODlhAQABAIAAAP", "md5": "0f343b0931126a20f133d67c2b018a3b"},
                    },
                    {
                        "msgtype": "news",
                        "news": {
                            "articles": [
                                {
                                    "title": "新闻标题",
                                    "description": "新闻描述",
                                    "url": "https://example.com/news",
                                    "picurl": "https://example.com/a.png",
                                }
                            ]
                        },
                    },
                    {
                        "msgtype": "file",
                        "file": {"media_id": "MEDIA_ID_FILE"},
                    },
                    {
                        "msgtype": "voice",
                        "voice": {"media_id": "MEDIA_ID_VOICE"},
                    },
                    {
                        "msgtype": "template_card",
                        "template_card": {
                            "card_type": "text_notice",
                            "main_title": {"title": "通知标题"},
                            "card_action": {"type": 1, "url": "https://example.com"},
                        },
                    },
                ]

                sent_targets = []

                async def fake_post(self, url, json=None, **kwargs):
                    sent_targets.append((url, json))
                    return httpx.Response(status_code=200, text='{"errcode":0}')

                with patch.object(httpx.AsyncClient, "post", new=fake_post):
                    with TestClient(app) as client:
                        for payload in payloads:
                            resp = client.post("/webhook/test-token", json=payload)
                            self.assertEqual(resp.status_code, 200, msg=f"failed payload: {payload.get('msgtype')}")
                            body = resp.json()
                            self.assertTrue(body["ok"])
                            self.assertEqual(body["delivery_count"], 1)
                            self.assertEqual(len(body["matched_rule_ids"]), 1)

                self.assertEqual(len(sent_targets), len(payloads))
                for index, payload in enumerate(payloads):
                    self.assertEqual(sent_targets[index][1], payload)

                with Session(engine) as session:
                    signals = session.exec(select(Signal)).all()
                    deliveries = session.exec(select(Delivery)).all()
                self.assertEqual(len(signals), len(payloads))
                self.assertEqual(len(deliveries), len(payloads))


if __name__ == "__main__":
    unittest.main()

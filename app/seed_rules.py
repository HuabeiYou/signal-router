import argparse
import json
from datetime import datetime

from sqlmodel import Session, select

from app.db import engine, init_db
from app.models import Rule
from app.security import encrypt_text


def upsert_rule(session: Session, name: str, priority: int, conditions: dict, target_urls: list[str]) -> Rule:
    rule = session.exec(select(Rule).where(Rule.name == name)).first()
    now = datetime.utcnow()
    action = {
        "type": "forward_wecom_webhooks",
        "targets": [encrypt_text(url) for url in target_urls],
    }
    if rule is None:
        rule = Rule(
            name=name,
            enabled=True,
            priority=priority,
            conditions_json=json.dumps(conditions, ensure_ascii=False),
            action_json=json.dumps(action, ensure_ascii=False),
            created_at=now,
            updated_at=now,
        )
    else:
        rule.enabled = True
        rule.priority = priority
        rule.conditions_json = json.dumps(conditions, ensure_ascii=False)
        rule.action_json = json.dumps(action, ensure_ascii=False)
        rule.updated_at = now

    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed default routing rules")
    parser.add_argument(
        "--fallback-webhook",
        required=True,
        help="保底群 webhook URL，所有消息都转发到该地址",
    )
    parser.add_argument(
        "--include-etf-example",
        action="store_true",
        help="是否额外写入 ETF 示例规则（默认不写入）",
    )
    parser.add_argument(
        "--etf-webhook",
        default="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=fake-etf-demo-key",
        help="ETF 示例规则命中时转发的 webhook URL",
    )
    args = parser.parse_args()

    init_db()
    with Session(engine) as session:
        fallback_rule = upsert_rule(
            session=session,
            name="保底转发",
            priority=1000,
            conditions={"op": "and", "items": [{"type": "always"}]},
            target_urls=[args.fallback_webhook],
        )
        fallback_info = (fallback_rule.id, fallback_rule.name)
        etf_info = None
        if args.include_etf_example:
            etf_rule = upsert_rule(
                session=session,
                name="ETF动量模型推送",
                priority=900,
                conditions={
                    "op": "and",
                    "items": [{"type": "contains_text", "text": "ETF动量模型推送"}],
                },
                target_urls=[args.etf_webhook],
            )
            etf_info = (etf_rule.id, etf_rule.name)

    print(f"Seeded fallback rule: id={fallback_info[0]}, name={fallback_info[1]}")
    if etf_info:
        print(f"Seeded ETF example rule: id={etf_info[0]}, name={etf_info[1]}")


if __name__ == "__main__":
    main()

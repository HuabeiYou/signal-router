import json
from datetime import datetime
from typing import Any, Optional

import httpx
from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app.config import settings
from app.db import get_session, init_db
from app.models import Delivery, Rule, Signal
from app.parser import parse_signal_fields
from app.rules import match_rule
from app.security import (
    build_session_token,
    decrypt_text,
    encrypt_text,
    mask_webhook,
    parse_session_token,
)

app = FastAPI(title="Signal Router")
templates = Jinja2Templates(directory="app/templates")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


def require_admin(request: Request) -> None:
    token = request.cookies.get("admin_session")
    username = parse_session_token(token) if token else None
    if username != settings.admin_username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


def _safe_json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


def _load_json(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _extract_targets(action_json: str) -> list[str]:
    action = _load_json(action_json)
    targets = action.get("targets", [])
    if not isinstance(targets, list):
        return []
    result: list[str] = []
    for item in targets:
        dec = decrypt_text(item) if isinstance(item, str) else None
        if dec:
            result.append(dec)
    return result


def _build_forward_payload(signal: Signal) -> dict[str, Any]:
    parsed = _load_json(signal.parsed_fields)
    lines = ["## Signal Routed"]
    if signal.source:
        lines.append(f"source={signal.source}")
    for key, value in parsed.items():
        lines.append(f"{key}={value}")
    return {
        "msgtype": "markdown",
        "markdown": {"content": "\\n".join(lines)},
    }


async def _dispatch_for_signal(session: Session, signal: Signal) -> tuple[list[int], int]:
    parsed_fields = _load_json(signal.parsed_fields)
    rules = session.exec(select(Rule).where(Rule.enabled == True).order_by(Rule.priority.desc())).all()  # noqa: E712

    matched_rule_ids: list[int] = []
    delivery_count = 0
    async with httpx.AsyncClient(timeout=5.0) as client:
        for rule in rules:
            conditions = _load_json(rule.conditions_json)
            if not match_rule(parsed_fields, conditions):
                continue
            matched_rule_ids.append(rule.id)
            targets = _extract_targets(rule.action_json)
            for target in targets:
                payload = _build_forward_payload(signal)
                success = False
                status_code: Optional[int] = None
                response_body: Optional[str] = None
                error_message: Optional[str] = None
                try:
                    resp = await client.post(target, json=payload)
                    status_code = resp.status_code
                    response_body = resp.text[:500]
                    success = resp.status_code == 200
                except Exception as exc:
                    error_message = str(exc)[:500]

                session.add(
                    Delivery(
                        signal_id=signal.id,
                        rule_id=rule.id,
                        target_masked=mask_webhook(target),
                        target_encrypted=encrypt_text(target),
                        request_payload=_safe_json_dumps(payload),
                        response_status=status_code,
                        response_body=response_body,
                        success=success,
                        error_message=error_message,
                    )
                )
                delivery_count += 1

    signal.match_count = len(matched_rule_ids)
    signal.delivery_count = delivery_count
    session.add(signal)
    session.commit()
    return matched_rule_ids, delivery_count


@app.post("/webhook/{inbound_token}")
async def inbound_webhook(
    inbound_token: str,
    request: Request,
    session: Session = Depends(get_session),
):
    if inbound_token != settings.inbound_token:
        raise HTTPException(status_code=401, detail="invalid token")

    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("payload must be object")
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json body")

    parsed_fields = parse_signal_fields(payload)
    signal = Signal(
        source=str(payload.get("source")) if payload.get("source") else None,
        raw_payload=_safe_json_dumps(payload),
        parsed_fields=_safe_json_dumps(parsed_fields),
    )
    session.add(signal)
    session.commit()
    session.refresh(signal)

    matched_rule_ids, delivery_count = await _dispatch_for_signal(session, signal)
    return {
        "ok": True,
        "signal_id": signal.id,
        "matched_rule_ids": matched_rule_ids,
        "delivery_count": delivery_count,
    }


@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/admin/login")
def admin_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    if username != settings.admin_username or password != settings.admin_password:
        return templates.TemplateResponse(request, "login.html", {"error": "用户名或密码错误"}, status_code=401)

    response = RedirectResponse(url="/admin/rules", status_code=303)
    response.set_cookie(
        key="admin_session",
        value=build_session_token(username),
        httponly=True,
        secure=settings.app_env == "prod",
        samesite="lax",
    )
    return response


@app.post("/admin/logout")
def admin_logout():
    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie("admin_session")
    return response


@app.get("/admin/rules", response_class=HTMLResponse)
def rules_page(request: Request, session: Session = Depends(get_session)):
    require_admin(request)
    rules = session.exec(select(Rule).order_by(Rule.priority.desc(), Rule.id.desc())).all()
    display_rules = []
    for rule in rules:
        action = _load_json(rule.action_json)
        masked_targets = [mask_webhook(decrypt_text(t) or "") for t in action.get("targets", []) if isinstance(t, str)]
        display_rules.append((rule, masked_targets))
    return templates.TemplateResponse(request, "rules.html", {"rules": display_rules})


@app.get("/admin/rules/new", response_class=HTMLResponse)
def rules_new_page(request: Request):
    require_admin(request)
    return templates.TemplateResponse(
        request,
        "rule_form.html",
        {
            "title": "新建规则",
            "form_action": "/admin/rules",
            "rule": None,
            "targets_text": "",
            "condition_type": "contains_field",
            "condition_value": "symbol",
        },
    )


@app.post("/admin/rules")
def rules_create(
    request: Request,
    session: Session = Depends(get_session),
    name: str = Form(...),
    enabled: Optional[str] = Form(None),
    priority: int = Form(0),
    condition_type: str = Form(...),
    condition_value: str = Form(""),
    target_urls: str = Form(...),
):
    require_admin(request)
    targets = [item.strip() for item in target_urls.splitlines() if item.strip()]
    if not targets:
        return JSONResponse(status_code=400, content={"ok": False, "error": "目标地址不能为空"})
    condition_value = condition_value.strip()
    if condition_type == "always":
        conditions = {"op": "and", "items": [{"type": "always"}]}
    elif condition_type == "contains_text":
        if not condition_value:
            return JSONResponse(status_code=400, content={"ok": False, "error": "关键词不能为空"})
        conditions = {"op": "and", "items": [{"type": "contains_text", "text": condition_value}]}
    elif condition_type == "contains_field":
        if not condition_value:
            return JSONResponse(status_code=400, content={"ok": False, "error": "字段名不能为空"})
        conditions = {"op": "and", "items": [{"type": "contains_field", "field": condition_value}]}
    else:
        return JSONResponse(status_code=400, content={"ok": False, "error": "不支持的规则类型"})

    action = {
        "type": "forward_wecom_webhooks",
        "targets": [encrypt_text(t) for t in targets],
    }

    now = datetime.utcnow()
    rule = Rule(
        name=name.strip(),
        enabled=enabled == "on",
        priority=priority,
        conditions_json=_safe_json_dumps(conditions),
        action_json=_safe_json_dumps(action),
        created_at=now,
        updated_at=now,
    )
    session.add(rule)
    session.commit()
    return RedirectResponse(url="/admin/rules", status_code=303)


@app.get("/admin/rules/{rule_id}/edit", response_class=HTMLResponse)
def rules_edit_page(rule_id: int, request: Request, session: Session = Depends(get_session)):
    require_admin(request)
    rule = session.get(Rule, rule_id)
    if not rule:
        raise HTTPException(status_code=404)

    conditions = _load_json(rule.conditions_json)
    condition_type = "contains_field"
    condition_value = ""
    if conditions.get("items"):
        first_item = conditions["items"][0]
        item_type = first_item.get("type")
        if item_type == "always":
            condition_type = "always"
        elif item_type == "contains_text":
            condition_type = "contains_text"
            condition_value = str(first_item.get("text", ""))
        else:
            condition_type = "contains_field"
            condition_value = str(first_item.get("field", ""))
    targets = _extract_targets(rule.action_json)

    return templates.TemplateResponse(
        request,
        "rule_form.html",
        {
            "title": "编辑规则",
            "form_action": f"/admin/rules/{rule.id}",
            "rule": rule,
            "targets_text": "\n".join(targets),
            "condition_type": condition_type,
            "condition_value": condition_value,
        },
    )


@app.post("/admin/rules/{rule_id}")
def rules_update(
    rule_id: int,
    request: Request,
    session: Session = Depends(get_session),
    name: str = Form(...),
    enabled: Optional[str] = Form(None),
    priority: int = Form(0),
    condition_type: str = Form(...),
    condition_value: str = Form(""),
    target_urls: str = Form(...),
):
    require_admin(request)
    rule = session.get(Rule, rule_id)
    if not rule:
        raise HTTPException(status_code=404)

    targets = [item.strip() for item in target_urls.splitlines() if item.strip()]
    if not targets:
        return JSONResponse(status_code=400, content={"ok": False, "error": "目标地址不能为空"})
    condition_value = condition_value.strip()
    if condition_type == "always":
        conditions = {"op": "and", "items": [{"type": "always"}]}
    elif condition_type == "contains_text":
        if not condition_value:
            return JSONResponse(status_code=400, content={"ok": False, "error": "关键词不能为空"})
        conditions = {"op": "and", "items": [{"type": "contains_text", "text": condition_value}]}
    elif condition_type == "contains_field":
        if not condition_value:
            return JSONResponse(status_code=400, content={"ok": False, "error": "字段名不能为空"})
        conditions = {"op": "and", "items": [{"type": "contains_field", "field": condition_value}]}
    else:
        return JSONResponse(status_code=400, content={"ok": False, "error": "不支持的规则类型"})

    rule.name = name.strip()
    rule.enabled = enabled == "on"
    rule.priority = priority
    rule.conditions_json = _safe_json_dumps(conditions)
    rule.action_json = _safe_json_dumps(
        {"type": "forward_wecom_webhooks", "targets": [encrypt_text(t) for t in targets]}
    )
    rule.updated_at = datetime.utcnow()

    session.add(rule)
    session.commit()
    return RedirectResponse(url="/admin/rules", status_code=303)


@app.post("/admin/rules/{rule_id}/toggle")
def rules_toggle(rule_id: int, request: Request, session: Session = Depends(get_session)):
    require_admin(request)
    rule = session.get(Rule, rule_id)
    if not rule:
        raise HTTPException(status_code=404)
    rule.enabled = not rule.enabled
    rule.updated_at = datetime.utcnow()
    session.add(rule)
    session.commit()
    return RedirectResponse(url="/admin/rules", status_code=303)


@app.get("/admin/signals", response_class=HTMLResponse)
def signals_page(request: Request, session: Session = Depends(get_session)):
    require_admin(request)
    signals = session.exec(select(Signal).order_by(Signal.id.desc()).limit(200)).all()
    return templates.TemplateResponse(request, "signals.html", {"signals": signals})


@app.get("/admin/signals/{signal_id}", response_class=HTMLResponse)
def signal_detail_page(signal_id: int, request: Request, session: Session = Depends(get_session)):
    require_admin(request)
    signal = session.get(Signal, signal_id)
    if not signal:
        raise HTTPException(status_code=404)

    deliveries = session.exec(select(Delivery).where(Delivery.signal_id == signal_id).order_by(Delivery.id.desc())).all()
    return templates.TemplateResponse(
        request,
        "signal_detail.html",
        {
            "signal": signal,
            "deliveries": deliveries,
            "parsed_fields": _load_json(signal.parsed_fields),
        },
    )


@app.get("/")
def root():
    return RedirectResponse(url="/admin/rules", status_code=303)

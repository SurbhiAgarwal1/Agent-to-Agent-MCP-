"""Unit and Integration Tests for Part 12 Notification Agent."""

import pytest
from app.services.notification_providers.console_provider import ConsoleNotificationProvider
from app.services.notification_providers.email_provider import EmailNotificationProvider
from app.services.notification_providers.sms_provider import SMSNotificationProvider
from app.agents.notification_agent import NotificationAgent


def test_notification_full_fulfillment():
    """Verify notifications generated for both hospital and matched sources on full fulfillment."""
    console = ConsoleNotificationProvider()
    agent = NotificationAgent(provider=console)

    plan = {
        "status": "FULLY_FULFILLED",
        "total_units": 3,
        "plan": [
            {"source_type": "BLOOD_BANK", "source_id": 1, "units": 2, "distance_km": 3.5, "estimated_time": "10 mins"},
            {"source_type": "DONOR", "source_id": 5, "units": 1, "distance_km": 5.0, "estimated_time": "15 mins"},
        ],
        "details": {"units_required": 3, "units_shortage": 0},
    }

    res = agent.notify_plan(hospital_id=1, request_id=101, fulfillment_plan=plan, hospital_name="City Hospital")

    assert res["success"] is True
    assert res["dispatched_count"] == 3  # 1 for hospital + 2 for sources
    notifs = res["notifications"]
    # Check hospital notification
    assert notifs[0]["recipient_type"] == "HOSPITAL"
    assert "FULLY FULFILLED" in notifs[0]["title"]
    # Check source notifications
    assert notifs[1]["recipient_type"] == "BLOOD_BANK"
    assert notifs[2]["recipient_type"] == "DONOR"


def test_notification_partial_fulfillment():
    """Verify notifications reflect shortage on partial fulfillment."""
    console = ConsoleNotificationProvider()
    agent = NotificationAgent(provider=console)

    plan = {
        "status": "PARTIALLY_FULFILLED",
        "total_units": 2,
        "plan": [
            {"source_type": "BLOOD_BANK", "source_id": 1, "units": 2, "distance_km": 2.0},
        ],
        "details": {"units_required": 5, "units_shortage": 3},
    }

    res = agent.notify_plan(hospital_id=2, request_id=102, fulfillment_plan=plan)

    assert res["dispatched_count"] == 2
    hosp_notif = res["notifications"][0]
    assert hosp_notif["recipient_type"] == "HOSPITAL"
    assert "PARTIALLY FULFILLED" in hosp_notif["title"]
    assert "shortage" in hosp_notif["message"].lower()


def test_notification_unfulfilled():
    """Verify emergency alert notification sent to hospital on unfulfilled request."""
    console = ConsoleNotificationProvider()
    agent = NotificationAgent(provider=console)

    plan = {
        "status": "UNFULFILLED",
        "total_units": 0,
        "plan": [],
        "details": {"units_required": 2, "units_shortage": 2},
    }

    res = agent.notify_plan(hospital_id=3, request_id=103, fulfillment_plan=plan)

    assert res["dispatched_count"] == 1
    hosp_notif = res["notifications"][0]
    assert hosp_notif["recipient_type"] == "HOSPITAL"
    assert "UNFULFILLED" in hosp_notif["title"]


def test_console_provider_output_format():
    """Verify console provider output schema and history recording."""
    provider = ConsoleNotificationProvider()
    rec = provider.send_notification("BLOOD_BANK", 12, "Pickup Ready", "Please collect 2 units")

    assert rec["channel"] == "CONSOLE"
    assert rec["recipient_type"] == "BLOOD_BANK"
    assert rec["recipient_id"] == 12
    assert rec["status"] == "DELIVERED"
    assert len(provider.get_history()) == 1


def test_provider_fallback_when_unconfigured(monkeypatch):
    """Verify email and SMS providers gracefully fallback to console when unconfigured."""
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMS_API_KEY", raising=False)

    email_p = EmailNotificationProvider()
    email_rec = email_p.send_notification("HOSPITAL", 1, "Email Alert", "Test email")
    assert email_rec["fallback"] is True
    assert email_rec["channel"] == "CONSOLE"

    sms_p = SMSNotificationProvider()
    sms_rec = sms_p.send_notification("DONOR", 4, "SMS Alert", "Test sms")
    assert sms_rec["fallback"] is True
    assert sms_rec["channel"] == "CONSOLE"

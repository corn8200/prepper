"""Email and Pushover delivery helpers."""

from __future__ import annotations

import logging
import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Dict, Iterable, Optional

import requests

LOGGER = logging.getLogger(__name__)


@dataclass
class AlertPayload:
    title: str
    body: str
    priority: int
    url: Optional[str] = None
    location_id: str = ""
    channels: Iterable[str] = ("email", "pushover")


class PushoverClient:
    API_URL = "https://api.pushover.net/1/messages.json"

    def __init__(self, user_key: Optional[str], app_token: Optional[str]) -> None:
        self.user_key = user_key
        self.app_token = app_token

    def send(self, payload: AlertPayload, emergency_retry: int, emergency_expire: int, dry_run: bool) -> bool:
        if not self.user_key or not self.app_token:
            LOGGER.info("Skipping Pushover send, missing credentials")
            return False
        if dry_run:
            LOGGER.info("[DRY] Would send Pushover: %s", payload.title)
            return True
        data: Dict[str, str | int] = {
            "token": self.app_token,
            "user": self.user_key,
            "title": payload.title,
            "message": payload.body,
            "priority": payload.priority,
        }
        if payload.url:
            data["url"] = payload.url
        if payload.priority == 2:
            data["retry"] = emergency_retry
            data["expire"] = emergency_expire
        resp = requests.post(self.API_URL, data=data, timeout=10)
        try:
            resp.raise_for_status()
        except requests.HTTPError as err:
            LOGGER.error("Pushover send failed: %s", err)
            return False
        return True


class EmailClient:
    def __init__(self, username: Optional[str], app_password: Optional[str], to_addr: Optional[str]) -> None:
        self.username = username
        self.app_password = app_password
        self.to_addr = to_addr

    def send(self, payload: AlertPayload, dry_run: bool) -> bool:
        if not (self.username and self.app_password and self.to_addr):
            LOGGER.info("Skipping email send, missing credentials")
            return False
        msg = EmailMessage()
        msg["Subject"] = payload.title
        msg["From"] = self.username
        msg["To"] = self.to_addr
        msg.set_content(payload.body)
        if payload.url:
            msg.add_alternative(f"<p>{payload.body}</p><p><a href='{payload.url}'>Details</a></p>", subtype="html")
        if dry_run:
            LOGGER.info("[DRY] Would send email: %s", payload.title)
            return True
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(self.username, self.app_password)
            smtp.send_message(msg)
        return True


class AlertDispatcher:
    def __init__(self, config: Dict[str, int | bool], dry_run: bool = False) -> None:
        outputs = config.get("outputs", {})
        emergency_retry = outputs.get("emergency_retry_sec", 60)  # type: ignore[arg-type]
        emergency_expire = outputs.get("emergency_expire_sec", 3600)  # type: ignore[arg-type]
        self.use_email = bool(outputs.get("use_email", True))
        self.use_pushover = bool(outputs.get("use_pushover", True))
        self.emergency_retry = int(emergency_retry)
        self.emergency_expire = int(emergency_expire)
        self.dry_run = dry_run
        self.pushover = PushoverClient(os.getenv("PUSHOVER_USER_KEY"), os.getenv("PUSHOVER_APP_TOKEN"))
        self.email = EmailClient(os.getenv("GMAIL_USER"), os.getenv("GMAIL_APP_PASSWORD"), os.getenv("ALERT_EMAIL_TO"))

    def dispatch(self, payload: AlertPayload) -> Dict[str, bool]:
        results = {"pushover": False, "email": False}
        if self.use_pushover and "pushover" in payload.channels:
            results["pushover"] = self.pushover.send(payload, self.emergency_retry, self.emergency_expire, self.dry_run)
        if self.use_email and "email" in payload.channels:
            results["email"] = self.email.send(payload, self.dry_run)
        return results

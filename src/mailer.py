from __future__ import annotations

import os
import re
import smtplib
from collections import OrderedDict
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .sources.base import Item

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def _render(items: list[Item], subject: str) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=select_autoescape())
    tpl = env.get_template("email.html")
    groups: "OrderedDict[str, list[Item]]" = OrderedDict()
    for it in items:
        groups.setdefault(it.source_label, []).append(it)
    for label in groups:
        groups[label].sort(key=lambda x: x.score, reverse=True)
    return tpl.render(
        subject=subject,
        total=len(items),
        groups=groups,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )


def send(items: list[Item], cfg: dict[str, Any]) -> None:
    if not items:
        return
    sender = os.environ["EMAIL_FROM"]
    to_raw = os.environ["EMAIL_TO"]
    password = os.environ["EMAIL_PASSWORD"]

    to_addrs = [a.strip() for a in re.split(r"[,;\s]+", to_raw) if a.strip()]
    if not to_addrs:
        return

    subject = f"{cfg.get('subject_prefix', '[Explorer]')} {datetime.now().strftime('%Y-%m-%d')}"
    html = _render(items, subject)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr(("Explorer Agent", sender))
    msg["To"] = ", ".join(to_addrs)
    msg.attach(MIMEText(html, "html", "utf-8"))

    host = cfg.get("smtp_host", "smtp.163.com")
    port = int(cfg.get("smtp_port", 465))
    with smtplib.SMTP_SSL(host, port, timeout=30) as s:
        s.login(sender, password)
        s.sendmail(sender, to_addrs, msg.as_string())

"""Envoi des fiches sur Telegram."""
import html
import json
import os

import httpx

API = "https://api.telegram.org/bot{token}/{method}"


def _call(method: str, **data) -> dict:
    r = httpx.post(API.format(token=os.environ["TELEGRAM_BOT_TOKEN"], method=method), data=data, timeout=30)
    return r.json()


def esc(s: str) -> str:
    return html.escape(str(s), quote=False)


def send_card(text: str, image: str | None, buttons: list[tuple[str, str]]) -> bool:
    markup = json.dumps({"inline_keyboard": [[{"text": t, "url": u}] for t, u in buttons]})
    chat = os.environ["TELEGRAM_CHAT_ID"]
    if image and len(text) <= 1024:
        res = _call("sendPhoto", chat_id=chat, photo=image, caption=text, parse_mode="HTML", reply_markup=markup)
        if res.get("ok"):
            return True
        print(f"  ! photo refusée ({res.get('description')}), envoi sans image")
    res = _call("sendMessage", chat_id=chat, text=text, parse_mode="HTML", reply_markup=markup,
                disable_web_page_preview="true")
    if not res.get("ok"):
        print(f"  ! Telegram: {res}")
    return bool(res.get("ok"))


def send_text(text: str) -> None:
    _call("sendMessage", chat_id=os.environ["TELEGRAM_CHAT_ID"], text=text, parse_mode="HTML",
          disable_web_page_preview="true")

"""Telegram bot: the original single-user human-in-the-loop approval interface.

NOT WIRED INTO THE MULTI-USER HOSTED APP. It still imports the removed
`src.stores` module and the old single-arg persona/service signatures, so it
will not run as-is. Kept for reference / a future per-user rework. The web
dashboard (`web/index.html`) is the supported approval interface.
"""
from __future__ import annotations
import asyncio
import logging

from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from src.config import get_settings
from src.models import ApprovalRequest
from src.stores import approval_store, raw_content_store, generated_content_store
from src.ai_brain.persona import load_persona
from src.generators.base import generate_content, FORMAT_NAMES
from src.publisher.facebook_publisher import publish_to_facebook
from src.publisher.wordpress_publisher import publish_to_wordpress

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# chat_id -> approval_id currently waiting for a free-text custom prompt reply
_awaiting_prompt: dict[int, str] = {}


def _topics_keyboard(approval: ApprovalRequest) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(f"{i + 1}. {t.title[:60]}", callback_data=f"topic:{approval.id}:{t.id}")]
        for i, t in enumerate(approval.topics)
    ]
    return InlineKeyboardMarkup(rows)


def _format_keyboard(approval_id: str, topic_id: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(f"{n}. {name}", callback_data=f"format:{approval_id}:{topic_id}:{n}")]
        for n, name in FORMAT_NAMES.items()
    ]
    return InlineKeyboardMarkup(rows)


def _publish_keyboard(generated_id: str, format_type: int) -> InlineKeyboardMarkup | None:
    if format_type == 1:
        return InlineKeyboardMarkup(
            [[InlineKeyboardButton("Publish to WordPress", callback_data=f"publish:{generated_id}:wordpress")]]
        )
    if format_type in (2, 3):
        return InlineKeyboardMarkup(
            [[InlineKeyboardButton("Publish to Facebook", callback_data=f"publish:{generated_id}:facebook")]]
        )
    return None


async def send_topics_for_approval(approval: ApprovalRequest) -> None:
    """Called by the FastAPI app right after the AI Brain generates topics."""
    settings = get_settings()
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are not configured.")

    bot = Bot(token=settings.telegram_bot_token)
    lines = ["*New content ideas ready for review:*\n"]
    for i, t in enumerate(approval.topics):
        lines.append(f"*{i + 1}. {t.title}*\n_{t.preview}_\n")

    message = await bot.send_message(
        chat_id=settings.telegram_chat_id,
        text="\n".join(lines),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_topics_keyboard(approval),
    )
    approval.telegram_chat_id = str(message.chat_id)
    approval.telegram_message_id = message.message_id
    approval_store().update(approval)


async def _on_topic_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, approval_id, topic_id = query.data.split(":")

    approval = approval_store().get(approval_id)
    approval.chosen_topic_id = topic_id
    approval.status = "topic_selected"
    approval_store().update(approval)

    _awaiting_prompt[query.message.chat_id] = approval_id
    await query.edit_message_text(
        "Got it. Reply with any custom style/tone instructions for this piece, "
        "or send /skip to use the default persona voice."
    )


async def _on_custom_prompt_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    approval_id = _awaiting_prompt.get(chat_id)
    if not approval_id:
        return  # not currently expecting free text from this chat — ignore

    approval = approval_store().get(approval_id)
    approval.custom_prompt = update.message.text
    approval_store().update(approval)
    del _awaiting_prompt[chat_id]

    await update.message.reply_text(
        "Custom instructions saved. Now choose a content format:",
        reply_markup=_format_keyboard(approval_id, approval.chosen_topic_id),
    )


async def _skip_custom_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    approval_id = _awaiting_prompt.pop(chat_id, None)
    if not approval_id:
        await update.message.reply_text("Nothing to skip right now.")
        return

    approval = approval_store().get(approval_id)
    await update.message.reply_text(
        "Using default persona voice. Now choose a content format:",
        reply_markup=_format_keyboard(approval_id, approval.chosen_topic_id),
    )


async def _on_format_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, approval_id, topic_id, format_type_str = query.data.split(":")
    format_type = int(format_type_str)

    approval = approval_store().get(approval_id)
    approval.chosen_format = format_type
    approval.status = "approved"
    approval_store().update(approval)

    await query.edit_message_text(f"Generating *{FORMAT_NAMES[format_type]}*…", parse_mode=ParseMode.MARKDOWN)

    raw_content = raw_content_store().get(approval.content_id)
    topic = next(t for t in approval.topics if t.id == topic_id)
    persona = load_persona()

    # Run the (blocking, LLM-bound) generator in a thread so the bot's event loop stays responsive.
    generated = await asyncio.to_thread(
        generate_content, format_type, topic, raw_content, persona, approval.id, approval.custom_prompt
    )

    if format_type == 4 and generated.extra.get("pdf_path"):
        with open(generated.extra["pdf_path"], "rb") as pdf_file:
            await context.bot.send_document(
                chat_id=query.message.chat_id,
                document=pdf_file,
                filename="lead_magnet.pdf",
                caption=f"*{generated.title}*",
                parse_mode=ParseMode.MARKDOWN,
            )
    else:
        text = generated.body if len(generated.body) < 4000 else generated.body[:4000] + "\n\n…(truncated, see stored draft)"
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=text,
            reply_markup=_publish_keyboard(generated.id, format_type),
        )


async def _on_publish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, generated_id, channel = query.data.split(":")
    generated = generated_content_store().get(generated_id)

    try:
        if channel == "wordpress":
            result = await asyncio.to_thread(publish_to_wordpress, generated.title, generated.body, "draft")
            link = result.get("link", "(draft created)")
        else:
            result = await asyncio.to_thread(publish_to_facebook, generated.body, None)
            link = result.get("post_id") or result.get("id", "(published)")

        generated.status = "published"
        generated_content_store().update(generated)
        await query.edit_message_text(f"Published to {channel}: {link}")
    except Exception as exc:  # surface publish errors directly in Telegram
        logger.exception("Publish failed")
        await query.edit_message_text(f"Publish to {channel} failed: {exc}")


def build_application() -> Application:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set in the environment.")

    app = Application.builder().token(settings.telegram_bot_token).build()
    app.add_handler(CallbackQueryHandler(_on_topic_chosen, pattern=r"^topic:"))
    app.add_handler(CallbackQueryHandler(_on_format_chosen, pattern=r"^format:"))
    app.add_handler(CallbackQueryHandler(_on_publish, pattern=r"^publish:"))
    app.add_handler(CommandHandler("skip", _skip_custom_prompt))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _on_custom_prompt_text))
    return app


if __name__ == "__main__":
    build_application().run_polling()

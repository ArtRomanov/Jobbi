"""Interactive dialog handler for creating applications via Telegram."""

import re

from sqlalchemy import delete, select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.core.config import get_settings
from app.core.constants import ApplicationStatus
from app.core.database import async_session
from app.models.telegram_conversation import TelegramConversation
from app.schemas.application import ApplicationCreate
from app.services.application_service import create_application
from app.services.telegram_service import get_link_by_chat
from app.bot.handlers.start import handle_code_verification

URL_PATTERN = re.compile(r"https?://\S+")

STEP_AWAITING_COMPANY = "awaiting_company"
STEP_AWAITING_ROLE = "awaiting_role"
STEP_AWAITING_STATUS = "awaiting_status"

NOT_LINKED_MESSAGE = (
    "🔒 Please link your account first. Send /start and enter your code."
)

STATUS_CALLBACK_PREFIX = "status:"


async def _get_conversation(db, chat_id: int) -> TelegramConversation | None:
    result = await db.execute(
        select(TelegramConversation).where(TelegramConversation.chat_id == chat_id)
    )
    return result.scalar_one_or_none()


async def _save_conversation(
    db, chat_id: int, step: str, context_data: dict
) -> None:
    existing = await _get_conversation(db, chat_id)
    if existing is None:
        conv = TelegramConversation(
            chat_id=chat_id, step=step, context_data=context_data
        )
        db.add(conv)
    else:
        existing.step = step
        existing.context_data = context_data
    await db.commit()


async def _clear_conversation(db, chat_id: int) -> None:
    await db.execute(
        delete(TelegramConversation).where(TelegramConversation.chat_id == chat_id)
    )
    await db.commit()


def _status_keyboard() -> InlineKeyboardMarkup:
    statuses = [
        ApplicationStatus.RESEARCHING,
        ApplicationStatus.APPLIED,
        ApplicationStatus.INTERVIEW,
        ApplicationStatus.OFFER,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
    ]
    rows = [
        [
            InlineKeyboardButton(
                s.value.capitalize(), callback_data=f"{STATUS_CALLBACK_PREFIX}{s.value}"
            )
        ]
        for s in statuses
    ]
    return InlineKeyboardMarkup(rows)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle any non-command text message from the user."""
    if update.effective_chat is None or update.message is None or update.message.text is None:
        return

    chat_id = update.effective_chat.id
    text = update.message.text.strip()

    # Ensure the user is linked
    async with async_session() as db:
        link = await get_link_by_chat(db, chat_id)

    if link is None:
        # Maybe this is a connection code
        handled = await handle_code_verification(update, context, text)
        if not handled:
            await context.bot.send_message(chat_id=chat_id, text=NOT_LINKED_MESSAGE)
        return

    # User is linked — continue or start a dialog
    async with async_session() as db:
        conv = await _get_conversation(db, chat_id)

    if conv is None:
        await _start_dialog(update, context, text)
    elif conv.step == STEP_AWAITING_COMPANY:
        await _handle_company(update, context, conv, text)
    elif conv.step == STEP_AWAITING_ROLE:
        await _handle_role(update, context, conv, text)
    else:
        # Shouldn't happen — expected status from keyboard, not text
        await context.bot.send_message(
            chat_id=chat_id,
            text="Please tap one of the status buttons above, or /cancel to abort.",
        )


async def _start_dialog(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
) -> None:
    assert update.effective_chat is not None
    chat_id = update.effective_chat.id

    url_match = URL_PATTERN.search(text)
    job_url = url_match.group(0) if url_match else None

    context_data = {"notes": text, "job_url": job_url}

    async with async_session() as db:
        await _save_conversation(db, chat_id, STEP_AWAITING_COMPANY, context_data)

    await context.bot.send_message(
        chat_id=chat_id, text="Got it! What company is this for?"
    )


async def _handle_company(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    conv: TelegramConversation,
    text: str,
) -> None:
    assert update.effective_chat is not None
    chat_id = update.effective_chat.id

    data = dict(conv.context_data or {})
    data["company_name"] = text

    async with async_session() as db:
        await _save_conversation(db, chat_id, STEP_AWAITING_ROLE, data)

    await context.bot.send_message(
        chat_id=chat_id, text="What's the role/title?"
    )


async def _handle_role(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    conv: TelegramConversation,
    text: str,
) -> None:
    assert update.effective_chat is not None
    chat_id = update.effective_chat.id

    data = dict(conv.context_data or {})
    data["role_title"] = text

    async with async_session() as db:
        await _save_conversation(db, chat_id, STEP_AWAITING_STATUS, data)

    await context.bot.send_message(
        chat_id=chat_id,
        text="Which status? Tap a button:",
        reply_markup=_status_keyboard(),
    )


async def handle_status_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle inline keyboard button press for status selection."""
    query = update.callback_query
    if query is None or query.data is None or update.effective_chat is None:
        return
    chat_id = update.effective_chat.id

    if not query.data.startswith(STATUS_CALLBACK_PREFIX):
        await query.answer()
        return

    status_value = query.data.removeprefix(STATUS_CALLBACK_PREFIX)

    async with async_session() as db:
        link = await get_link_by_chat(db, chat_id)
        if link is None:
            await query.answer("Please link your account first.")
            return

        conv = await _get_conversation(db, chat_id)
        if conv is None or conv.step != STEP_AWAITING_STATUS:
            await query.answer("No application in progress.")
            return

        data = dict(conv.context_data or {})
        company = data.get("company_name")
        role = data.get("role_title")
        if not company or not role:
            await query.answer("Missing fields. Start over with a new message.")
            await _clear_conversation(db, chat_id)
            return

        payload = ApplicationCreate(
            company_name=company,
            role_title=role,
            job_url=data.get("job_url"),
            notes=data.get("notes"),
            status=status_value,
        )
        app = await create_application(db, link.user_id, payload)
        await _clear_conversation(db, chat_id)

    settings = get_settings()
    confirmation = (
        f"✅ Application created: {app.company_name} — {app.role_title} "
        f"({app.status}).\nView it at {settings.JOBBI_PUBLIC_URL}/dashboard"
    )
    await query.answer()
    await query.edit_message_text(confirmation)

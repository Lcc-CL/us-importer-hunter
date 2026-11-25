"""Combine delivery configuration and queue facts for the operations view."""

from app.core.config import Settings
from app.domain.mail_operations import DispatchState, MailOperationsStore, MailQueueStatus
from app.workflows.mail_delivery.workflow import (
    configured_sender,
    delivery_configured,
    sender_fingerprint,
    verified_approval_required,
)


async def read_mail_operations(
    repository: MailOperationsStore,
    settings: Settings,
) -> MailQueueStatus:
    sender = configured_sender(settings)
    queue = await repository.snapshot(
        sender_fingerprint(sender) if sender else None,
        verified_only=verified_approval_required(settings),
    )
    state: DispatchState
    configured = delivery_configured(settings, sender)
    if queue.dispatch_workers > (queue.compatible_workers if configured else 0):
        state = "worker_config_mismatch"
    elif not settings.mail_send_enabled:
        state = "disabled"
    elif not configured:
        state = "not_configured"
    elif queue.compatible_workers == 0:
        state = "no_worker"
    elif queue.polling_workers == 0:
        state = "poll_stale"
    else:
        state = "polling"
    return MailQueueStatus(state, queue)

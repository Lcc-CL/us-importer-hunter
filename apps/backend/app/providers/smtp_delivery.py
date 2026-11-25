"""TLS SMTP transport. An ambiguous submission is never automatically retried."""

import asyncio
import smtplib
import ssl
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import formatdate

from app.core.config import Settings
from app.domain.mail_delivery import ClaimedMail, MailResult, MailSender, smtp_message_id


class SmtpDelivery:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.tls = ssl.create_default_context()

    async def send(self, mail: ClaimedMail, sender: MailSender) -> MailResult:
        return await asyncio.to_thread(self._send, mail, sender)

    def _send(self, mail: ClaimedMail, sender: MailSender) -> MailResult:
        url = sender.unsubscribe_url(mail.id)
        message = EmailMessage()
        message["From"] = Address(display_name=sender.name, addr_spec=sender.address)
        message["Reply-To"] = sender.reply_to
        message["To"] = mail.recipient
        message["Date"] = formatdate(usegmt=True)
        message["Subject"] = mail.subject
        message["Message-ID"] = smtp_message_id(mail.id, sender.address)
        message["List-Unsubscribe"] = f"<{url}>"
        message["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
        message.set_content(f"{mail.body}\n\nUnsubscribe: {url}\n")
        client: smtplib.SMTP | None = None
        submitting = False
        try:
            host = self.settings.mail_smtp_host
            port = self.settings.mail_smtp_port
            if self.settings.mail_smtp_tls == "implicit":
                client = smtplib.SMTP_SSL(host, port, timeout=10, context=self.tls)
            else:
                client = smtplib.SMTP(host, port, timeout=10)
                client.starttls(context=self.tls)
            client.login(
                self.settings.mail_smtp_username,
                self.settings.mail_smtp_password.get_secret_value(),
            )
            submitting = True
            client.send_message(message, from_addr=sender.address, to_addrs=[mail.recipient])
        except smtplib.SMTPRecipientsRefused as exc:
            code, _ = next(iter(exc.recipients.values()))
            return self._rejected(code)
        except smtplib.SMTPResponseException as exc:
            return self._rejected(exc.smtp_code)
        except ssl.SSLCertVerificationError:
            return MailResult("failed", "smtp_tls_verification_failed")
        except OSError:
            # A broken connection after entering SMTP submission might follow acceptance.
            return (
                MailResult("unknown", "smtp_submission_unconfirmed")
                if submitting
                else MailResult("retry", "smtp_connection_failed")
            )
        finally:
            if client is not None:
                client.close()
        return MailResult("accepted", "smtp_accepted")

    @staticmethod
    def _rejected(code: int) -> MailResult:
        if 400 <= code < 500:
            return MailResult("retry", f"smtp_{code}")
        return MailResult("failed", f"smtp_{code}")

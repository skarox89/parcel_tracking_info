# custom_components/parcel_tracking_info/helpers.py

import imaplib
import logging

_LOGGER = logging.getLogger(__name__)

def test_email_connection(imap_server, imap_port, email_account, email_password):
    """Test email connection."""
    try:
        with imaplib.IMAP4_SSL(imap_server, imap_port) as mail:
            mail.login(email_account, email_password)
        return True, ""
    except imaplib.IMAP4.error as e:
        return False, str(e)
    except Exception as e:
        _LOGGER.error(f"Unexpected error in test_email_connection: {e}")
        return False, "unknown_error"

def process_status_strings(status_strings):
    if isinstance(status_strings, str):
        return [s.strip() for s in status_strings.split(",") if s.strip()]
    elif isinstance(status_strings, list):
        return [s.strip() for s in status_strings if s.strip()]
    return []

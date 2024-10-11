# custom_components/parcel_tracking_info/__init__.py

import logging
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_HOST, CONF_PORT
from homeassistant.exceptions import ConfigEntryNotReady
from .const import DOMAIN
import imaplib
from . import config_flow  # Ensure config_flow is imported to register the flow

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass, config):
    """Set up the Parcel Tracking Info integration from YAML configuration."""
    _LOGGER.debug("Parcel Tracking Info setup using YAML is not supported.")
    return True


async def async_setup_entry(hass, entry):
    """Set up Parcel Tracking Info from a config entry."""
    _LOGGER.info(f"Setting up Parcel Tracking Info with configuration entry: {entry.title}")

    try:
        # Perform a connectivity check to the email server
        imap_server = entry.data.get(CONF_HOST)
        imap_port = entry.data.get(CONF_PORT)
        email_account = entry.data.get(CONF_EMAIL)
        email_password = entry.data.get(CONF_PASSWORD)

        # Attempt to connect to the email server
        connected, error_code = await hass.async_add_executor_job(
            test_email_connection, imap_server, imap_port, email_account, email_password
        )

        if not connected:
            error_message = {
                'invalid_auth': "Invalid username or password.",
                'imap_error': "IMAP error occurred. Please check the server address and port.",
                'cannot_connect': "Cannot connect to email server.",
            }.get(error_code, "Unknown error occurred during email connection.")

            _LOGGER.error(f"Email connection failed: {error_message}")
            raise ConfigEntryNotReady(error_message)

        # Forward the config entry setup to the sensor platform
        await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

        return True

    except Exception as ex:
        _LOGGER.error(f"Error setting up entry: {ex}")
        raise ConfigEntryNotReady from ex


async def async_unload_entry(hass, entry):
    """Unload a config entry."""
    _LOGGER.info(f"Unloading Parcel Tracking Info config entry: {entry.title}")

    # Remove the coordinator from hass.data
    hass.data.get(DOMAIN, {}).pop(entry.unique_id, None)

    # Unload the sensor platform
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])

    return unload_ok


async def async_reload_entry(hass, entry):
    """Reload config entry when options are updated."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


def test_email_connection(imap_server, imap_port, email_account, email_password):
    """Test the email server connection."""
    try:
        mail = imaplib.IMAP4_SSL(imap_server, imap_port)
        mail.login(email_account, email_password)
        mail.logout()
        return True, None
    except imaplib.IMAP4.error as e:
        if "authentication failed" in str(e).lower():
            return False, 'invalid_auth'
        else:
            return False, 'imap_error'
    except Exception as e:
        _LOGGER.error(f"Email server connection failed: {e}")
        return False, 'cannot_connect'

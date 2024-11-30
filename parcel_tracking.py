# custom_components/parcel_tracking_info/parcel_tracking.py

import imaplib
import email
import re
import logging
import aiohttp
import asyncio
from datetime import datetime, timedelta
import html
import functools
from collections import defaultdict

from .trackingstatus import map_status  # Import the updated mapping function
from .delivery_date_normalization import normalize_date  # New import
from bs4 import BeautifulSoup  # Import BeautifulSoup for HTML parsing
from .carrier_apis import CARRIER_API_CLASSES

_LOGGER = logging.getLogger(__name__)

def extract_tracking_number(email_body, tracking_pattern, processed_tracking_numbers):
    """Extract a tracking number from the email body."""
    _LOGGER.debug(f"Attempting to extract tracking number with pattern: {tracking_pattern}")
    matches = re.findall(tracking_pattern, email_body)
    if matches:
        _LOGGER.debug(f"Regex matched tracking numbers: {matches}")
        for match in matches:
            tracking_number = match.strip()
            if tracking_number not in processed_tracking_numbers:
                _LOGGER.debug(f"New tracking number found: {tracking_number}")
                processed_tracking_numbers.add(tracking_number)
                return tracking_number
            else:
                _LOGGER.debug(f"Duplicate tracking number found: {tracking_number}, skipping.")
    else:
        _LOGGER.debug("No tracking number found.")
    return None

def extract_email_body(msg):
    """Extract and return the email body from a message object."""
    email_body = ""
    if msg.is_multipart():
        html_body = ""
        text_body = ""
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            _LOGGER.debug(f"Processing part with content type: {content_type}")
            if content_type == "text/html" and "attachment" not in content_disposition:
                html_content = part.get_payload(decode=True).decode(
                    part.get_content_charset("utf-8"), errors="ignore"
                )
                # Use BeautifulSoup to extract text from HTML
                soup = BeautifulSoup(html_content, 'html.parser')
                html_body = soup.get_text(separator='\n')
                _LOGGER.debug(f"Extracted text/html email body: {html_body[:500]}...")
            elif content_type == "text/plain" and "attachment" not in content_disposition:
                text_content = part.get_payload(decode=True).decode(
                    part.get_content_charset("utf-8"), errors="ignore"
                )
                _LOGGER.debug(f"Extracted text/plain email body: {text_content[:500]}...")
                text_body = text_content
        # Prefer HTML body over text body if available
        if html_body.strip():
            email_body = html_body
        elif text_body.strip():
            email_body = text_body
        else:
            _LOGGER.debug("No non-empty email body found.")
    else:
        email_body = msg.get_payload(decode=True).decode(
            msg.get_content_charset("utf-8"), errors="ignore"
        )
        _LOGGER.debug(f"Extracted non-multipart email body: {email_body[:500]}...")
    return email_body
    
async def extract_eta_from_email(hass, email_body, eta_string, eta_pattern):
    """
    Extract and normalize ETA from the email based on the given pattern and string.

    Args:
        hass (HomeAssistant): The Home Assistant instance.
        email_body (str): The body of the email.
        eta_string (str): The string to search for before the date.
        eta_pattern (str): The regex pattern to extract the date.

    Returns:
        Optional[str]: The normalized ETA in DD.MM.YYYY format, or "N/A" if not found.
    """
    eta_index = email_body.lower().find(eta_string.lower())
    if eta_index != -1:
        # Look for the date after the eta_string
        text_after_eta = email_body[eta_index + len(eta_string):]
        match = re.search(eta_pattern, text_after_eta, re.IGNORECASE)
        if match:
            raw_eta = match.group(0)
            _LOGGER.debug(f"Extracted raw ETA: {raw_eta}")
            # Normalize the extracted date asynchronously
            normalized_eta = await hass.async_add_executor_job(normalize_date, raw_eta)
            if normalized_eta:
                return normalized_eta
            else:
                _LOGGER.warning(f"Failed to normalize ETA date: '{raw_eta}'")
                return "N/A"
    _LOGGER.debug("No ETA found.")
    return "N/A"

def extract_status_from_email(email_body, status_strings):
    """Extract status from the email based on status strings and map to standard status."""
    email_body_lower = email_body.lower()

    # First, check for status strings provided by the user
    for status in status_strings:
        if status.lower() in email_body_lower:
            _LOGGER.debug(f"Found status string '{status}' in email.")
            mapped_status = map_status(status)
            _LOGGER.debug(f"Mapped status: '{status}' to '{mapped_status}'")
            return mapped_status

    # If no status found, return None
    _LOGGER.debug("No status strings matched in the email.")
    return None

def get_imap_connection(imap_server, imap_port, email_account, email_password):
    """Create and return an IMAP connection."""
    try:
        _LOGGER.debug(f"Connecting to IMAP server: {imap_server} on port: {imap_port} with email: {email_account}")
        mail = imaplib.IMAP4_SSL(imap_server, imap_port)
        mail.login(email_account, email_password)
        _LOGGER.debug("Successfully connected and logged into IMAP server.")
        return mail
    except imaplib.IMAP4.error as e:
        _LOGGER.error(f"IMAP4 Error during login: {e}")
        raise
    except Exception as e:
        _LOGGER.error(f"Unexpected error connecting to IMAP server: {e}")
        raise

def format_search_criteria(search_criteria, date_cutoff):
    """Format the search criteria by adding the date cutoff."""
    # Ensure the criteria is enclosed in parentheses
    if not (search_criteria.startswith('(') and search_criteria.endswith(')')):
        search_criteria = f'({search_criteria})'
    # Check if SINCE is already included
    if 'SINCE' in search_criteria.upper():
        # Assume user is handling date filtering
        return search_criteria
    else:
        # Append the SINCE date
        return f'{search_criteria} SINCE {date_cutoff}'

async def fetch_emails(
    hass,
    imap_server,
    imap_port,
    email_account,
    email_password,
    email_folder,
    search_criteria,
    tracking_pattern,
    processed_tracking_numbers,
    lock,
    email_parsing=None,
    email_age=10,  # Default to 10 days
    api_required=False,
    api_template=None,
    api_key=None,
    api_url=None,
    carrier=None,
):
    """Fetch emails from the IMAP server and look for tracking numbers and additional info."""
    tracking_numbers = []
    try:
        async with lock:
            # Run the blocking code in the executor
            mail = await hass.async_add_executor_job(
                get_imap_connection,
                imap_server,
                imap_port,
                email_account,
                email_password,
            )

            # Select the email folder
            select_folder = functools.partial(mail.select, email_folder)
            status, messages = await hass.async_add_executor_job(select_folder)

            if status != "OK":
                _LOGGER.error(f"Failed to select folder '{email_folder}'. Status: {status}")
                return tracking_numbers

            # Calculate the SINCE date based on email_age
            date_cutoff = (datetime.now() - timedelta(days=email_age)).strftime("%d-%b-%Y")
            search_criteria = search_criteria or 'ALL'
            final_search_criteria = format_search_criteria(search_criteria, date_cutoff)

            _LOGGER.debug(f"Searching emails with criteria: {final_search_criteria}")
            search_emails = functools.partial(mail.search, None, final_search_criteria)
            status, messages = await hass.async_add_executor_job(search_emails)

            if status != "OK" or not messages[0]:
                _LOGGER.debug("No emails found with the given search criteria.")
                return tracking_numbers

            email_numbers = messages[0].split()
            _LOGGER.debug(f"Found {len(email_numbers)} emails to process.")
            email_numbers = email_numbers[::-1]

            for num in email_numbers:
                fetch_email = functools.partial(mail.fetch, num, "(BODY.PEEK[])")
                status, data = await hass.async_add_executor_job(fetch_email)
                if status != "OK":
                    _LOGGER.warning(f"Failed to fetch email number {num.decode()}. Skipping.")
                    continue

                msg = email.message_from_bytes(data[0][1])
                email_body = extract_email_body(msg)
                _LOGGER.debug(f"Email body extracted (first 500 chars): {email_body[:500]}...")

                tracking_number = extract_tracking_number(
                    email_body, tracking_pattern, processed_tracking_numbers
                )

                if tracking_number:
                    # Default tracking info structure
                    tracking_info = {
                        "tracking_number": tracking_number,
                        "status_code": "unknown",
                        "eta": "N/A",
                        "service_url": "N/A",
                    }

                    # Use email parsing rules if provided
                    if email_parsing:
                        eta_string = email_parsing.get('eta_string')
                        eta_date_pattern = email_parsing.get('eta_date_pattern')
                        status_strings = email_parsing.get('status_strings', [])

                        if eta_string and eta_date_pattern:
                            # Call the updated async extract_eta_from_email
                            eta = await extract_eta_from_email(hass, email_body, eta_string, eta_date_pattern)
                            if eta:
                                tracking_info['eta'] = eta
                            else:
                                _LOGGER.warning(f"ETA not found using patterns for tracking number {tracking_number}.")

                        if status_strings:
                            status = extract_status_from_email(email_body, status_strings)
                            if status:
                                tracking_info['status_code'] = status
                            else:
                                _LOGGER.warning(f"Status not found using strings for tracking number {tracking_number}.")

                    # Fetch additional tracking info via API if required
                    if api_required:
                        api_tracking_info = await fetch_tracking_info(
                            tracking_number,
                            api_key,
                            api_url,
                            api_template,
                            carrier,
                        )
                        tracking_info.update(api_tracking_info)

                    tracking_numbers.append(tracking_info)
                    _LOGGER.debug(f"Added tracking info: {tracking_info}")

            _LOGGER.debug(
                f"Processed {len(email_numbers)} emails. Found tracking numbers: {tracking_numbers}"
            )

    except imaplib.IMAP4.error as e:
        _LOGGER.error(f"IMAP connection error: {e}")
    except Exception as e:
        _LOGGER.error(f"Error fetching emails: {e}")

    return tracking_numbers

async def fetch_tracking_info(tracking_number, api_key, api_url, api_template, carrier):
    """Fetch tracking information using the selected API template."""
    if not api_template:
        # For backward compatibility, use the carrier name as the API template
        api_template = carrier.lower()

    if api_template == 'no_api':
        _LOGGER.debug("No API template selected. Skipping API call.")
        return {"status_code": "unknown", "service_url": "unknown", "eta": "N/A"}

    # Get the appropriate API class based on the api_template
    api_class = CARRIER_API_CLASSES.get(api_template.lower())
    if not api_class:
        _LOGGER.error(f"No API implementation found for template '{api_template}'.")
        return {"status_code": "unknown", "service_url": "unknown", "eta": "N/A"}

    # Instantiate the API class
    carrier_api = api_class(api_key, api_url)

    # Call the fetch_tracking_info method
    tracking_info = await carrier_api.fetch_tracking_info(tracking_number)
    return tracking_info
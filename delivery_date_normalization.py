# custom_components/parcel_tracking_info/delivery_date_normalization.py

import logging
import re
from datetime import datetime, timedelta
from typing import Optional

import dateparser

_LOGGER = logging.getLogger(__name__)

# Mapping of German month names to their respective numbers
GERMAN_MONTHS = {
    'januar': 1,
    'februar': 2,
    'märz': 3,
    'maerz': 3,  # Alternative spelling
    'april': 4,
    'mai': 5,
    'juni': 6,
    'juli': 7,
    'august': 8,
    'september': 9,
    'oktober': 10,
    'november': 11,
    'dezember': 12,
}

# Patterns to extract dates from different formats
DATE_PATTERNS = [
    r'\b(?:Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag),\s+(\d{1,2})\.(\d{1,2})\.(\d{4})\b',  # Montag, 15.07.2024
    r'Zustellung:\s+(?:Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag),\s+(\d{1,2})\s+(\w+)',  # Freitag, 4 Oktober
    r'am\s+(?:Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag),\s+den\s+(\d{1,2})\.(\d{1,2})\.',  # am Montag, den 16.09.
    r'(?:Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag),\s+(\d{1,2})\s+(\w+)',  # Freitag, 17. Mai
    r'in\s+(\d+)-(\d+)\s+Werktagen',  # Relative date: in 1-2 Werktagen
    # Add more patterns if needed
]

def normalize_date(date_string: str) -> Optional[str]:
    """
    Normalize various German date formats into DD.MM.YYYY.
    Handles both absolute and relative dates.

    Args:
        date_string (str): The raw date string extracted from the email.

    Returns:
        Optional[str]: The normalized date string in DD.MM.YYYY format, or None if parsing fails.
    """
    current_year = datetime.now().year

    for pattern in DATE_PATTERNS:
        match = re.search(pattern, date_string, re.IGNORECASE)
        if match:
            try:
                if pattern == DATE_PATTERNS[0]:
                    # Montag, 15.07.2024
                    day, month, year = match.groups()
                elif pattern == DATE_PATTERNS[1]:
                    # Freitag, 4 Oktober
                    day, month_str = match.groups()
                    month = GERMAN_MONTHS.get(month_str.lower())
                    year = current_year
                elif pattern == DATE_PATTERNS[2]:
                    # am Montag, den 16.09.
                    day, month = match.groups()
                    year = current_year
                elif pattern == DATE_PATTERNS[3]:
                    # Freitag, 17. Mai
                    day, month_str = match.groups()
                    month = GERMAN_MONTHS.get(month_str.lower())
                    year = current_year
                elif pattern == DATE_PATTERNS[4]:
                    # in 1-2 Werktagen
                    min_days, max_days = map(int, match.groups())
                    eta_date = datetime.now() + timedelta(days=max_days)  # Choose max days for ETA
                    normalized_date = eta_date.strftime("%d.%m.%Y")
                    _LOGGER.debug(f"Normalized relative ETA date: {normalized_date} from '{date_string}'")
                    return normalized_date
                else:
                    continue  # Unknown pattern

                if isinstance(month, int) and isinstance(day, str) and isinstance(year, str):
                    day = int(day)
                    year = int(year)
                    normalized_date = f"{day:02}.{month:02}.{year}"
                    _LOGGER.debug(f"Normalized date: {normalized_date} from '{date_string}'")
                    return normalized_date
            except Exception as e:
                _LOGGER.error(f"Error parsing date with pattern '{pattern}': {e}")
                continue

    # Attempt to parse using dateparser as a fallback
    try:
        parsed_date = dateparser.parse(
            date_string,
            languages=['de'],
            settings={'PREFER_DAY_OF_MONTH': 'first', 'RELATIVE_BASE': datetime.now()}
        )
        if parsed_date:
            normalized_date = parsed_date.strftime("%d.%m.%Y")
            _LOGGER.debug(f"Normalized date using dateparser: {normalized_date} from '{date_string}'")
            return normalized_date
    except Exception as e:
        _LOGGER.error(f"Error parsing date with dateparser: {e}")

    # Handle relative dates like "in 1-2 Werktagen"
    relative_match = re.search(r'in\s+(\d+)-(\d+)\s+Werktagen', date_string, re.IGNORECASE)
    if relative_match:
        try:
            min_days, max_days = map(int, relative_match.groups())
            # Choose the maximum days for the ETA
            eta_date = datetime.now() + timedelta(days=max_days)
            normalized_date = eta_date.strftime("%d.%m.%Y")
            _LOGGER.debug(f"Normalized relative ETA date: {normalized_date} from '{date_string}'")
            return normalized_date
        except Exception as e:
            _LOGGER.error(f"Error parsing relative date '{date_string}': {e}")

    _LOGGER.warning(f"Failed to normalize date: '{date_string}'")
    return None

# custom_components/parcel_tracking_info/trackingstatus.py

import logging
import re

_LOGGER = logging.getLogger(__name__)

# Define your status mappings here using regex patterns
STATUS_MAPPING = {
    "in Zustellung": [
        r"in transit",
        r"in delivery",
        r"out for delivery",
        r"in zustellung",
        r"wird zugestellt",
        r"wurde versandt",
        r"ist unterwegs",
        r"auf dem weg zu dir",
        r"ist fast da",
        r"ist auf dem weg",
        r"kommt ihr dpd paket",
        r"wird ihnen heute",
        r"wird ihnen voraussichtlich",
        r"paket kommt heute",
        r"sendung unterwegs",
        r"sendung ist unterwegs",
        r"unterwegs",
        r"versandt",
        r"bestellung versandt",
        r"transit",
        r"zustellung",
        r"wird in kürze zugestellt",
        r"stellen wir"
    ],
    "Zugestellt": [
        r"delivered",
        r"zugestellt",
        r"ausgeliefert",
        r"ihr paket ist da",
        r"paket angekommen",
        r"paket geliefert",
        r"ist da"
    ],
    "Warten": [
        r"pending",
        r"waiting",
        r"wartet",
        r"warte auf zustellung"
    ],
    "Zustellung fehlgeschlagen": [
        r"failed delivery",
        r"zustellung fehlgeschlagen",
        r"abholung fehlgeschlagen",
        r"paket konnte nicht zugestellt werden"
    ],
    "Abholbereit": [
        r"packstation",
        r"abholbereit",
        r"filiale",
        r"paket konnte nicht zugestellt werden",
        r"hinterlegt",
    ],
    # Add more mappings as needed
}

def map_status(status_string):
    """
    Map a given status string to the standard status using regex patterns.
    
    Args:
        status_string (str): The raw status string extracted from the email.
    
    Returns:
        str: The standardized status.
    """
    status_string_lower = status_string.lower()
    for standard_status, patterns in STATUS_MAPPING.items():
        for pattern in patterns:
            if re.search(pattern, status_string_lower):
                _LOGGER.debug(f"Mapping '{status_string}' to '{standard_status}'")
                return standard_status
    _LOGGER.debug(f"No mapping found for '{status_string}', returning original")
    return status_string

# custom_components/parcel_tracking_info/carrier_apis.py

import aiohttp
import logging
from .trackingstatus import map_status

_LOGGER = logging.getLogger(__name__)

class BaseCarrierAPI:
    """Base class for carrier APIs."""

    def __init__(self, api_key, api_url):
        self.api_key = api_key
        self.api_url = api_url

    async def fetch_tracking_info(self, tracking_number):
        """Fetch tracking information. To be implemented by subclasses."""
        raise NotImplementedError

class DHLAPI(BaseCarrierAPI):
    """API implementation for DHL."""

    async def fetch_tracking_info(self, tracking_number):
        if not tracking_number or tracking_number.lower() == "unknown":
            _LOGGER.debug(f"Invalid tracking number: {tracking_number}. Skipping API call.")
            return {"status_code": "unknown", "service_url": "unknown", "eta": "N/A"}

        # Ensure the api_url includes the scheme
        api_url = self.api_url
        if not api_url.startswith('http://') and not api_url.startswith('https://'):
            api_url = 'https://' + api_url

        _LOGGER.debug(f"Fetching DHL tracking info for number: {tracking_number} from API: {api_url}")
        headers = {"DHL-API-Key": self.api_key}
        params = {"trackingNumber": tracking_number}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    api_url, headers=headers, params=params, timeout=10
                ) as response:
                    response.raise_for_status()
                    tracking_info = await response.json()

            if "shipments" in tracking_info and len(tracking_info["shipments"]) > 0:
                shipment = tracking_info["shipments"][0]
                eta = shipment.get("estimatedTimeOfDelivery", "N/A")
                service_url = shipment.get("serviceUrl", "N/A")
                status_description = shipment.get("status", {}).get("statusCode", "unknown")
                _LOGGER.debug(f"Raw status description from DHL API: {status_description}")
                status_code = map_status(status_description)
                _LOGGER.debug(f"Normalized status code: {status_code}")
                return {
                    "status_code": status_code,
                    "service_url": service_url,
                    "eta": eta,
                }
            else:
                _LOGGER.debug(f"No shipment data found for tracking number {tracking_number}")
                return {"status_code": "unknown", "service_url": "unknown", "eta": "N/A"}

        except aiohttp.ClientError as e:
            _LOGGER.error(f"Client error while fetching DHL tracking info: {e}")
            return {"status_code": "unknown", "service_url": "unknown", "eta": "N/A"}
        except Exception as e:
            _LOGGER.error(f"Unexpected error while fetching DHL tracking info: {e}")
            return {"status_code": "unknown", "service_url": "unknown", "eta": "N/A"}

# Implement other carrier APIs similarly

class GLSAPI(BaseCarrierAPI):
    """API implementation for GLS."""

    async def fetch_tracking_info(self, tracking_number):
        # Implement GLS API call logic here
        pass

class HermesAPI(BaseCarrierAPI):
    """API implementation for Hermes."""

    async def fetch_tracking_info(self, tracking_number):
        # Implement Hermes API call logic here
        pass

class DPDAPI(BaseCarrierAPI):
    """API implementation for DPD."""

    async def fetch_tracking_info(self, tracking_number):
        # Implement DPD API call logic here
        pass

# Map carrier names to their respective API classes
CARRIER_API_CLASSES = {
    'dhl': DHLAPI,
    'gls': GLSAPI,
    'hermes': HermesAPI,
    'dpd': DPDAPI,
    # Add other carriers as needed
}

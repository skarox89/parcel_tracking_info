# custom_components/parcel_tracking_info/coordinator.py

import asyncio
from datetime import timedelta
import logging
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .parcel_tracking import fetch_tracking_info, fetch_emails
from .const import DOMAIN
from .carriers import CARRIER_TEMPLATES
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_HOST, CONF_PORT

_LOGGER = logging.getLogger(__name__)


class ParcelTrackingCoordinator(DataUpdateCoordinator):
    """Coordinator to manage fetching email data and API results efficiently."""

    def __init__(self, hass, entry):
        """Initialize the coordinator."""
        self.hass = hass
        self.entry = entry
        self.unique_id = entry.unique_id  # Use the unique_id from the config entry
        self.tracking_data = []
        self.lock = asyncio.Lock()  # Instance-specific lock
        self.processed_tracking_numbers = set()  # Instance-specific set
        self.active_indices = set()  # Track active sensor indices

        # Get the update interval from configuration
        update_interval_minutes = int(entry.options.get(
            'update_interval',
            entry.data.get('update_interval', 60)  # Default to 60 minutes
        ))
        update_interval = timedelta(minutes=update_interval_minutes)
        _LOGGER.debug(f"Update interval set to {update_interval_minutes} minutes.")

        super().__init__(
            hass,
            _LOGGER,
            name=f"Parcel Tracking Coordinator - {entry.title}",
            update_interval=update_interval,
        )

    async def _async_update_data(self):
        """Fetch data from emails and API."""
        _LOGGER.debug("Starting data update in coordinator.")

        try:
            # Reset processed_tracking_numbers at the beginning of each update
            self.processed_tracking_numbers = set()

            # Extract configuration values from entry options, fallback to data
            carrier = self.entry.options.get(
                "carrier", self.entry.data.get("carrier", "dhl")
            )
            api_template = self.entry.options.get(
                "api_template", self.entry.data.get("api_template", "")
            )
            imap_server = self.entry.options.get(
                CONF_HOST, self.entry.data.get(CONF_HOST, "")
            )
            imap_port = self.entry.options.get(
                CONF_PORT, self.entry.data.get(CONF_PORT, 0)
            )
            email_account = self.entry.options.get(
                CONF_EMAIL, self.entry.data.get(CONF_EMAIL, "")
            )
            email_password = self.entry.options.get(
                CONF_PASSWORD, self.entry.data.get(CONF_PASSWORD, "")
            )
            email_folder = self.entry.options.get(
                "email_folder", self.entry.data.get("email_folder", "inbox")
            )
            search_criteria = self.entry.options.get(
                "search_criteria", self.entry.data.get("search_criteria", f'(FROM "{carrier}")')
            )
            tracking_pattern = self.entry.options.get(
                "tracking_pattern",
                self.entry.data.get(
                    "tracking_pattern", r""
                ),
            )
            api_key = self.entry.options.get("api_key") or self.entry.data.get("api_key", "")
            api_url = (
                self.entry.options.get("api_url")
                or self.entry.data.get("api_url")
                or CARRIER_TEMPLATES.get(carrier.lower(), {}).get("api_url", "")
            )
            email_age = self.entry.options.get(
                'email_age', self.entry.data.get('email_age', 10)  # Default to 10 days
            )
            tracking_link_url = self.entry.options.get(
                "tracking_link_url", self.entry.data.get("tracking_link_url", "")
            )

            self.carrier = carrier.lower()  # Store carrier in lowercase for consistency

            _LOGGER.debug("Updating coordinator data.")

            # Fetch tracking numbers from emails
            new_tracking_data = await self.fetch_tracking_numbers(
                imap_server,
                imap_port,
                email_account,
                email_password,
                email_folder,
                search_criteria,
                tracking_pattern,
                email_age,  # Pass email_age
            )

            # Sort tracking_data to maintain consistent ordering
            new_tracking_data_sorted = sorted(new_tracking_data, key=lambda x: x["tracking_number"])

            # Update self.tracking_data with sorted data
            self.tracking_data = new_tracking_data_sorted

            # Determine new and removed indices
            new_indices = set(range(len(self.tracking_data)))
            removed_indices = self.active_indices - new_indices
            added_indices = new_indices - self.active_indices
            self.active_indices = new_indices

            # Fetch tracking info for each tracking number
            await self.fetch_tracking_info(api_key, api_url, api_template, carrier)

            # Handle tracking_link_url to set service_url
            if tracking_link_url:
                for tracking in self.tracking_data:
                    service_url = tracking.get("service_url", "N/A")
                    if service_url in ["unknown", "N/A"] and tracking.get("tracking_number"):
                        tracking_number = tracking["tracking_number"]
                        # Construct the tracking URL
                        tracking_url = self.construct_tracking_url(tracking_link_url, tracking_number)
                        tracking["service_url"] = tracking_url
                        _LOGGER.debug(f"Set service_url for {tracking_number} to {tracking['service_url']}")

            _LOGGER.debug(f"Coordinator tracking data after update: {self.tracking_data}")
            _LOGGER.debug("Data update completed successfully.")
            return self.tracking_data

        except Exception as e:
            _LOGGER.error(f"Error updating data: {e}")
            raise UpdateFailed(f"Error fetching data: {e}")

    def construct_tracking_url(self, base_url, tracking_number):
        """Construct the tracking URL with tracking number appended appropriately."""
        # Include your existing method implementation here
        from urllib.parse import urlparse, urlunparse, urlencode, parse_qs

        parsed_url = urlparse(base_url)
        query = parsed_url.query
        fragment = parsed_url.fragment
        path = parsed_url.path

        # Handle fragments
        if base_url.endswith('#') or fragment:
            # Append tracking number to fragment
            new_fragment = f"{fragment}{tracking_number}"
            new_parsed_url = parsed_url._replace(fragment=new_fragment)
            return urlunparse(new_parsed_url)
        
        # Handle query parameters
        query_params = parse_qs(query, keep_blank_values=True)
        empty_param_found = False
        for key in query_params:
            if query_params[key] == ['']:
                query_params[key] = [tracking_number]
                empty_param_found = True
        if empty_param_found:
            new_query = urlencode(query_params, doseq=True)
            new_parsed_url = parsed_url._replace(query=new_query)
            return urlunparse(new_parsed_url)
        elif base_url.endswith('?'):
            # URL ends with '?', but no query parameters
            new_query = urlencode({tracking_number: ''})
            new_parsed_url = parsed_url._replace(query=new_query)
            return urlunparse(new_parsed_url)
        elif query_params:
            # Append tracking number as a new query parameter
            query_params['tracking_number'] = [tracking_number]
            new_query = urlencode(query_params, doseq=True)
            new_parsed_url = parsed_url._replace(query=new_query)
            return urlunparse(new_parsed_url)
        else:
            # Append tracking number to path
            if not path.endswith('/'):
                new_path = f"{path}/{tracking_number}"
            else:
                new_path = f"{path}{tracking_number}"
            new_parsed_url = parsed_url._replace(path=new_path)
            return urlunparse(new_parsed_url)

    async def fetch_tracking_numbers(
        self,
        imap_server,
        imap_port,
        email_account,
        email_password,
        email_folder,
        search_criteria,
        tracking_pattern,
        email_age,  # New parameter
    ):
        """Fetch tracking numbers from the email."""
        _LOGGER.debug("Fetching tracking numbers from email.")

        # Get email parsing rules from config
        email_parsing = {
            'eta_string': self.entry.options.get('eta_string', self.entry.data.get('eta_string', '')),
            'eta_date_pattern': self.entry.options.get('eta_date_pattern', self.entry.data.get('eta_date_pattern', '')),
            'status_strings': self.entry.options.get('status_strings', self.entry.data.get('status_strings', [])),
        }

        new_tracking_data = await fetch_emails(
            self.hass,  # Pass hass instance
            imap_server,
            imap_port,
            email_account,
            email_password,
            email_folder,
            search_criteria,
            tracking_pattern,
            self.processed_tracking_numbers,  # Pass the instance-specific set
            self.lock,  # Pass the lock
            email_parsing,  # Pass the user-configured email parsing rules
            email_age=email_age  # Pass email_age
        )
        _LOGGER.debug(f"New tracking numbers fetched: {new_tracking_data}")
        return new_tracking_data

    async def fetch_tracking_info(self, api_key, api_url, api_template, carrier):
        """Fetch tracking info via the API for all tracking numbers."""
        _LOGGER.debug("Fetching tracking information via API.")

        for tracking in self.tracking_data:
            tracking_number = tracking.get("tracking_number", None)
            if tracking_number and api_key and api_url:
                api_data = await fetch_tracking_info(tracking_number, api_key, api_url, api_template, carrier)
                tracking.update(api_data)
                _LOGGER.debug(f"Updated tracking data with API info: {tracking}")
            else:
                _LOGGER.debug(
                    f"No API available or missing info for tracking number {tracking_number}. Using email data."
                )

    @property
    def total_packages(self):
        """Return the total number of tracked packages."""
        return len(self.tracking_data)

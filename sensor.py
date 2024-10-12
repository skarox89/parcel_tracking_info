# custom_components/parcel_tracking_info/sensor.py

import asyncio
from datetime import timedelta
import logging
from urllib.parse import urlparse, urlunparse, urlencode, parse_qs
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_HOST, CONF_PORT
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    CoordinatorEntity,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_registry import async_get
from .parcel_tracking import fetch_tracking_info, fetch_emails
from .const import DOMAIN
from .carriers import CARRIER_TEMPLATES  # Import carrier templates

_LOGGER = logging.getLogger(__name__)


class ParcelTrackingCoordinator(DataUpdateCoordinator):
    """Coordinator to manage fetching email data and API results efficiently."""

    def __init__(self, hass, entry):
        """Initialize the coordinator."""
        # Get the update interval from configuration
        update_interval_minutes = entry.options.get(
            'update_interval',
            entry.data.get('update_interval', 60)  # Default to 60 minutes
        )
        update_interval = timedelta(minutes=update_interval_minutes)

        super().__init__(
            hass,
            _LOGGER,
            name=f"Parcel Tracking Coordinator - {entry.title}",
            update_interval=update_interval,
        )
        self.hass = hass
        self.entry = entry
        self.unique_id = entry.unique_id  # Use the unique_id from the config entry
        self.tracking_data = []
        self.lock = asyncio.Lock()  # Instance-specific lock
        self.processed_tracking_numbers = set()  # Instance-specific set
        self.active_indices = set()  # Track active sensor indices

    async def _async_update_data(self):
        """Fetch data from emails and API."""
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
        return self.tracking_data


    def construct_tracking_url(self, base_url, tracking_number):
        """Construct the tracking URL with tracking number appended appropriately."""
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


async def async_setup_entry(hass, entry, async_add_entities: AddEntitiesCallback):
    """Set up the tracking sensors."""
    coordinators = hass.data.setdefault(DOMAIN, {})
    coordinator = coordinators.get(entry.unique_id)

    if not coordinator:
        # Create the coordinator
        coordinator = ParcelTrackingCoordinator(hass, entry)
        # Store the coordinator using the unique ID
        coordinators[entry.unique_id] = coordinator

    # Fetch initial data
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as ex:
        _LOGGER.error(f"Error during coordinator initial refresh: {ex}")
        return  # Do not proceed if initial data fetch fails

    carrier = coordinator.carrier  # Get the carrier from the coordinator

    # Retrieve display_name and tracking_link_url from hass.data
    display_names = hass.data.get(DOMAIN, {}).get('display_name', {})
    tracking_link_urls = hass.data.get(DOMAIN, {}).get('tracking_link_url', {})

    # Get the Entity Registry for cleanup
    entity_registry = async_get(hass)

    # Identify existing sensor indices to manage cleanup
    existing_indices = coordinator.active_indices.copy()
    new_indices = set(range(len(coordinator.tracking_data)))

    # Determine which indices have been removed
    removed_indices = existing_indices - new_indices

    # Remove sensors associated with removed indices
    for index in removed_indices:
        # Remove all sensor types associated with the index
        for sensor_type in ["tracking_number", "status", "tracking_link", "eta"]:
            entity_id = f"sensor.{DOMAIN}_{carrier}_{sensor_type}_{index}"
            entry = entity_registry.async_get(entity_id)
            if entry:
                _LOGGER.info(f"Removing obsolete sensor: {entity_id}")
                entity_registry.async_remove(entity_id)

    # Update the coordinator's active_indices
    coordinator.active_indices = new_indices

    # Create new sensors
    sensors = []
    for index, tracking in enumerate(coordinator.tracking_data):
        display_name = display_names.get(carrier, carrier.capitalize())
        tracking_link_url = tracking_link_urls.get(carrier, '')

        # Create sensors using index instead of tracking_number
        sensors.append(TrackingNumberSensor(coordinator, index, carrier, display_name, tracking_link_url))
        sensors.append(TrackingStatusSensor(coordinator, index, carrier, display_name, tracking_link_url))
        sensors.append(TrackingLinkSensor(coordinator, index, carrier, display_name, tracking_link_url))
        sensors.append(TrackingETASensor(coordinator, index, carrier, display_name, tracking_link_url))

    if sensors:
        async_add_entities(sensors)
    else:
        _LOGGER.warning("No sensors to add. Check if tracking data is available.")


class BaseTrackingSensor(CoordinatorEntity):
    """Base class for tracking sensors."""

    def __init__(self, coordinator, index, carrier, sensor_type, display_name, tracking_link_url):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.index = index
        self.carrier = carrier
        self.sensor_type = sensor_type
        self.display_name = display_name
        self.tracking_link_url = tracking_link_url

        self._attr_name = f"{self.display_name} {sensor_type.replace('_', ' ').capitalize()} {self.index}"
        self._attr_unique_id = f"{coordinator.unique_id}_{carrier}_{sensor_type}_{self.index}"
        self._attr_entity_id = f"sensor.{DOMAIN}_{carrier}_{sensor_type}_{self.index}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.unique_id)},
            name=f"{self.display_name} Tracking Info",
            manufacturer=carrier.upper(),
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def tracking_url(self):
        """Construct and return the tracking URL with tracking number appended appropriately."""
        if self.index < len(self.coordinator.data):
            tracking = self.coordinator.data[self.index]
            tracking_number = tracking.get('tracking_number', 'Unknown')
            if not self.tracking_link_url or tracking_number == "Unknown":
                return 'Unknown'

            parsed_url = urlparse(self.tracking_link_url)
            query = parsed_url.query
            fragment = parsed_url.fragment
            path = parsed_url.path

            # Handle fragments
            if self.tracking_link_url.endswith('#') or fragment:
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
            elif self.tracking_link_url.endswith('?'):
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
        else:
            _LOGGER.error(f"Index {self.index} out of range for coordinator data with length {len(self.coordinator.data)}")
            return 'Unknown'

    @property
    def available(self):
        """Return True if the sensor is available (i.e., index is within data range)."""
        is_available = self.index < len(self.coordinator.data)
        if not is_available:
            _LOGGER.warning(f"Sensor '{self.name}' index {self.index} is out of range. Data length: {len(self.coordinator.data)}")
        return is_available

    @property
    def state(self):
        """Return the state of the sensor."""
        raise NotImplementedError("Must be implemented by subclasses.")


class TrackingNumberSensor(BaseTrackingSensor):
    """Sensor for tracking number."""

    def __init__(self, coordinator, index, carrier, display_name, tracking_link_url):
        """Initialize the Tracking Number sensor."""
        sensor_type = "tracking_number"
        super().__init__(coordinator, index, carrier, sensor_type, display_name, tracking_link_url)

    @property
    def state(self):
        """Return the tracking number."""
        if self.available:
            tracking = self.coordinator.data[self.index]
            return tracking.get("tracking_number", "unknown")
        return "unknown"

    @property
    def icon(self):
        """Return the icon of the sensor."""
        return "mdi:package-variant-closed"


class TrackingStatusSensor(BaseTrackingSensor):
    """Sensor for tracking status."""

    def __init__(self, coordinator, index, carrier, display_name, tracking_link_url):
        """Initialize the Tracking Status sensor."""
        sensor_type = "status"
        super().__init__(coordinator, index, carrier, sensor_type, display_name, tracking_link_url)

    @property
    def state(self):
        """Return the status of the sensor."""
        if self.available:
            tracking = self.coordinator.data[self.index]
            return tracking.get("status_code", "unknown")
        return "unknown"
        
    @property
    def icon(self):
        """Return the icon of the sensor."""
        return "mdi:magnify-expand"


class TrackingETASensor(BaseTrackingSensor):
    """Sensor for ETA."""

    def __init__(self, coordinator, index, carrier, display_name, tracking_link_url):
        """Initialize the Tracking ETA sensor."""
        sensor_type = "eta"
        super().__init__(coordinator, index, carrier, sensor_type, display_name, tracking_link_url)

    @property
    def state(self):
        """Return the ETA of the sensor."""
        if self.available:
            tracking = self.coordinator.data[self.index]
            return tracking.get("eta", "N/A")
        return "N/A"

    @property
    def icon(self):
        """Return the icon of the sensor."""
        return "mdi:update"


class TrackingLinkSensor(BaseTrackingSensor):
    """Sensor for tracking link."""

    def __init__(self, coordinator, index, carrier, display_name, tracking_link_url):
        """Initialize the Tracking Link sensor."""
        sensor_type = "tracking_link"
        super().__init__(coordinator, index, carrier, sensor_type, display_name, tracking_link_url)

    @property
    def state(self):
        """Return the tracking link."""
        if self.available:
            tracking = self.coordinator.data[self.index]
            return tracking.get("service_url", "N/A")
        return "N/A"

    @property
    def device_class(self):
        """Return the device class of the sensor."""
        return "url"

    @property
    def icon(self):
        """Return the icon of the sensor."""
        return "mdi:link-variant"

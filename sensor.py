# custom_components/parcel_tracking_info/sensor.py

import logging
from urllib.parse import urlparse, urlunparse, urlencode, parse_qs
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_registry import async_get
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities: AddEntitiesCallback):
    """Set up the tracking sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

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
            entry_entity = entity_registry.async_get(entity_id)
            if entry_entity:
                _LOGGER.info(f"Removing obsolete sensor: {entity_id}")
                entity_registry.async_remove(entity_id)

    # Update the coordinator's active_indices
    coordinator.active_indices = new_indices

    # Create new sensors
    sensors = []
    boolean_sensors = []
    for index, tracking in enumerate(coordinator.tracking_data):
        display_name = display_names.get(carrier, carrier.capitalize())
        tracking_link_url = tracking_link_urls.get(carrier, '')

        # Create tracking sensors using index instead of tracking_number
        sensors.append(TrackingNumberSensor(coordinator, index, carrier, display_name, tracking_link_url))
        sensors.append(TrackingStatusSensor(coordinator, index, carrier, display_name, tracking_link_url))
        sensors.append(TrackingLinkSensor(coordinator, index, carrier, display_name, tracking_link_url))
        sensors.append(TrackingETASensor(coordinator, index, carrier, display_name, tracking_link_url))

        # Create corresponding boolean sensor
        boolean_sensors.append(TrackingActiveBooleanSensor(coordinator, index, carrier, display_name))

    if sensors:
        async_add_entities(sensors)
    else:
        _LOGGER.warning("No tracking sensors to add. Check if tracking data is available.")

    if boolean_sensors:
        async_add_entities(boolean_sensors)
    else:
        _LOGGER.warning("No boolean sensors to add. Check if tracking data is available.")


class BaseTrackingSensor(CoordinatorEntity, SensorEntity):
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

    # Rest of your methods remain unchanged

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


class TrackingActiveBooleanSensor(CoordinatorEntity, BinarySensorEntity):
    """Boolean sensor indicating if the tracking is active."""

    def __init__(self, coordinator, index, carrier, display_name):
        """Initialize the boolean sensor."""
        super().__init__(coordinator)
        self.index = index
        self.carrier = carrier
        self.display_name = display_name

        self._attr_name = f"{self.display_name} Active {self.index}"
        self._attr_unique_id = f"{coordinator.unique_id}_{carrier}_active_{self.index}"
        self._attr_entity_id = f"binary_sensor.{DOMAIN}_{carrier}_active_{self.index}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.unique_id)},
            name=f"{self.display_name} Tracking Info",
            manufacturer=carrier.upper(),
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def is_on(self):
        """Return True if the tracking is active."""
        return self.index in self.coordinator.active_indices

    @property
    def icon(self):
        """Return the icon of the boolean sensor."""
        return "mdi:check-circle" if self.is_on else "mdi:close-circle"

    @property
    def device_class(self):
        """Return the device class of the boolean sensor."""
        return "connectivity"

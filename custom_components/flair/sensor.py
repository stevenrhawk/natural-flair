"""Sensor platform for Flair integration."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from flairaio.model import Puck, Room, Structure, Vent

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import(
    ELECTRIC_POTENTIAL_VOLT,
    LIGHT_LUX,
    PERCENTAGE,
    PRESSURE_KPA,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    TEMP_CELSIUS,

)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FlairDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set Up Flair Sensor Entities."""

    coordinator: FlairDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    sensors = []

    for structure_id, structure_data in coordinator.data.structures.items():
            # Structures
            sensors.extend((
                HomeAwayHoldUntil(coordinator, structure_id),
            ))

            # Pucks
            if structure_data.pucks:
                for puck_id, puck_data in structure_data.pucks.items():
                    sensors.extend((
                        PuckTemp(coordinator, structure_id, puck_id),
                        PuckHumidity(coordinator, structure_id, puck_id),
                        PuckLight(coordinator, structure_id, puck_id),
                        PuckVoltage(coordinator, structure_id, puck_id),
                        PuckRSSI(coordinator, structure_id, puck_id),
                        PuckPressure(coordinator, structure_id, puck_id)
                    ))
            # Vents
            if structure_data.vents:
                for vent_id, vent_data in structure_data.vents.items():
                    sensors.extend((
                        DuctTemp(coordinator, structure_id, vent_id),
                        DuctPressure(coordinator, structure_id, vent_id),
                        VentVoltage(coordinator, structure_id, vent_id),
                        VentRSSI(coordinator, structure_id, vent_id)
                    ))
            # Rooms
            if structure_data.rooms:
                for room_id, room_data in structure_data.rooms.items():
                    sensors.extend((
                        HoldTempUntil(coordinator, structure_id, room_id),
                    ))

    async_add_entities(sensors)


class HomeAwayHoldUntil(CoordinatorEntity, SensorEntity):
    """Representation of default hold duration setting."""

    def __init__(self, coordinator, structure_id):
        super().__init__(coordinator)
        self.structure_id = structure_id

    @property
    def structure_data(self) -> Structure:
        """Handle coordinator structure data."""

        return self.coordinator.data.structures[self.structure_id]

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device registry information for this entity."""

        return {
            "identifiers": {(DOMAIN, self.structure_data.id)},
            "name": self.structure_data.attributes['name'],
            "manufacturer": "Flair",
            "model": "Structure",
            "configuration_url": "https://my.flair.co/",
        }

    @property
    def unique_id(self) -> str:
        """Sets unique ID for this entity."""

        return str(self.structure_data.id) + '_home_away_hold_until'

    @property
    def name(self) -> str:
        """Return name of the entity."""

        return "Home/Away holding until"

    @property
    def has_entity_name(self) -> bool:
        """Indicate that entity has name defined."""

        return True

    @property
    def native_value(self) -> datetime:
        """Date/time when hold will end.

        When home/away is set manually, returns date/time when hold will end.
        Only applicable if structure default hold duration is anything other
        than 'until next scheduled event'
        """

        if self.structure_data.attributes['hold-until']:
            return datetime.fromisoformat(self.structure_data.attributes['hold-until'])

    @property
    def device_class(self) -> SensorDeviceClass:
        """Return entity device class."""

        return SensorDeviceClass.TIMESTAMP

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Disable entity if system mode is set to manual on initial registration."""

        system_mode = self.structure_data.attributes['mode']
        if system_mode == 'manual':
            return False
        else:
            return True

    @property
    def available(self) -> bool:
        """Determine whether entity is available. 

        Return true if home/away is set manually and structure
        has a default hold duration other than next event.
        """

        if self.structure_data.attributes['hold-until']:
            return True
        else:
            return False


class PuckTemp(CoordinatorEntity, SensorEntity):
    """Representation of Puck Temperature."""

    def __init__(self, coordinator, structure_id, puck_id):
        super().__init__(coordinator)
        self.puck_id = puck_id
        self.structure_id = structure_id

    @property
    def puck_data(self) -> Puck:
        """Handle coordinator puck data."""

        return self.coordinator.data.structures[self.structure_id].pucks[self.puck_id]

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device registry information for this entity."""

        return {
            "identifiers": {(DOMAIN, self.puck_data.id)},
            "name": self.puck_data.attributes['name'],
            "manufacturer": "Flair",
            "model": "Puck",
            "configuration_url": "https://my.flair.co/",
        }

    @property
    def unique_id(self) -> str:
        """Sets unique ID for this entity."""

        return str(self.puck_data.id) + '_temperature'

    @property
    def name(self) -> str:
        """Return name of the entity."""

        return "Temperature"

    @property
    def has_entity_name(self) -> bool:
        """Indicate that entity has name defined."""

        return True

    @property
    def native_value(self) -> float:
        """Return current temperature in Celsius."""

        return self.puck_data.attributes['current-temperature-c']

    @property
    def native_unit_of_measurement(self) -> str:
        """Return Celsius as the native unit."""

        return TEMP_CELSIUS

    @property
    def device_class(self) -> SensorDeviceClass:
        """Return entity device class."""

        return SensorDeviceClass.TEMPERATURE

    @property
    def state_class(self) -> SensorStateClass:
        """Return the type of state class."""

        return SensorStateClass.MEASUREMENT

    @property
    def available(self) -> bool:
        """Return true if device is available."""

        if not self.puck_data.attributes['inactive']:
            return True
        else:
            return False


class PuckHumidity(CoordinatorEntity, SensorEntity):
    """Representation of Puck Humidity."""

    def __init__(self, coordinator, structure_id, puck_id):
        super().__init__(coordinator)
        self.puck_id = puck_id
        self.structure_id = structure_id

    @property
    def puck_data(self) -> Puck:
        """Handle coordinator puck data."""

        return self.coordinator.data.structures[self.structure_id].pucks[self.puck_id]

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device registry information for this entity."""

        return {
            "identifiers": {(DOMAIN, self.puck_data.id)},
            "name": self.puck_data.attributes['name'],
            "manufacturer": "Flair",
            "model": "Puck",
            "configuration_url": "https://my.flair.co/",
        }

    @property
    def unique_id(self) -> str:
        """Sets unique ID for this entity."""

        return str(self.puck_data.id) + '_humidity'

    @property
    def name(self) -> str:
        """Return name of the entity."""

        return "Humidity"

    @property
    def has_entity_name(self) -> bool:
        """Indicate that entity has name defined."""

        return True

    @property
    def native_value(self) -> float:
        """Return current humidity."""

        return self.puck_data.attributes['current-humidity']

    @property
    def native_unit_of_measurement(self) -> str:
        """Return percent as the native unit."""

        return PERCENTAGE

    @property
    def device_class(self) -> SensorDeviceClass:
        """Return entity device class."""

        return SensorDeviceClass.HUMIDITY

    @property
    def state_class(self) -> SensorStateClass:
        """Return the type of state class."""

        return SensorStateClass.MEASUREMENT

    @property
    def available(self) -> bool:
        """Return true if device is available."""

        if not self.puck_data.attributes['inactive']:
            return True
        else:
            return False


class PuckLight(CoordinatorEntity, SensorEntity):
    """Representation of Puck Light."""

    def __init__(self, coordinator, structure_id, puck_id):
        super().__init__(coordinator)
        self.puck_id = puck_id
        self.structure_id = structure_id

    @property
    def puck_data(self) -> Puck:
        """Handle coordinator puck data."""

        return self.coordinator.data.structures[self.structure_id].pucks[self.puck_id]

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device registry information for this entity."""

        return {
            "identifiers": {(DOMAIN, self.puck_data.id)},
            "name": self.puck_data.attributes['name'],
            "manufacturer": "Flair",
            "model": "Puck",
            "configuration_url": "https://my.flair.co/",
        }

    @property
    def unique_id(self) -> str:
        """Sets unique ID for this entity."""

        return str(self.puck_data.id) + '_light'

    @property
    def name(self) -> str:
        """Return name of the entity."""

        return "Light"

    @property
    def has_entity_name(self) -> bool:
        """Indicate that entity has name defined."""

        return True

    @property
    def native_value(self) -> float:
        """Return current lux level. 

        Convert value to Volts then multiply by 200
        for 200 lux per Volt.
        """

        return (self.puck_data.current_reading['light'] / 100) * 200

    @property
    def native_unit_of_measurement(self) -> str:
        """Return lux as the native unit."""

        return LIGHT_LUX

    @property
    def device_class(self) -> SensorDeviceClass:
        """Return entity device class."""

        return SensorDeviceClass.ILLUMINANCE

    @property
    def state_class(self) -> SensorStateClass:
        """Return the type of state class."""

        return SensorStateClass.MEASUREMENT

    @property
    def available(self) -> bool:
        """Return true if device is available."""

        if (self.puck_data.attributes['inactive'] == False) and \
                (self.puck_data.current_reading['light'] is not None):
            return True
        else:
            return False


class PuckVoltage(CoordinatorEntity, SensorEntity):
    """Representation of Puck Voltage."""

    def __init__(self, coordinator, structure_id, puck_id):
        super().__init__(coordinator)
        self.puck_id = puck_id
        self.structure_id = structure_id

    @property
    def puck_data(self) -> Puck:
        """Handle coordinator puck data."""

        return self.coordinator.data.structures[self.structure_id].pucks[self.puck_id]

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device registry information for this entity."""

        return {
            "identifiers": {(DOMAIN, self.puck_data.id)},
            "name": self.puck_data.attributes['name'],
            "manufacturer": "Flair",
            "model": "Puck",
            "configuration_url": "https://my.flair.co/",
        }

    @property
    def unique_id(self) -> str:
        """Sets unique ID for this entity."""

        return str(self.puck_data.id) + '_voltage'

    @property
    def name(self) -> str:
        """Return name of the entity."""

        return "Voltage"

    @property
    def has_entity_name(self) -> bool:
        """Indicate that entity has name defined."""

        return True

    @property
    def native_value(self) -> float:
        """Return voltage measurement."""

        return self.puck_data.attributes['voltage']

    @property
    def native_unit_of_measurement(self) -> str:
        """Return volts as the native unit."""

        return ELECTRIC_POTENTIAL_VOLT

    @property
    def device_class(self) -> SensorDeviceClass:
        """Return entity device class."""

        return SensorDeviceClass.VOLTAGE

    @property
    def state_class(self) -> SensorStateClass:
        """Return the type of state class."""

        return SensorStateClass.MEASUREMENT

    @property
    def entity_category(self) -> EntityCategory:
        """Set category to diagnostic."""

        return EntityCategory.DIAGNOSTIC

    @property
    def available(self) -> bool:
        """Return true if device is available."""

        if not self.puck_data.attributes['inactive']:
            return True
        else:
            return False


class PuckRSSI(CoordinatorEntity, SensorEntity):
    """Representation of Puck Voltage."""

    def __init__(self, coordinator, structure_id, puck_id):
        super().__init__(coordinator)
        self.puck_id = puck_id
        self.structure_id = structure_id

    @property
    def puck_data(self) -> Puck:
        """Handle coordinator puck data."""

        return self.coordinator.data.structures[self.structure_id].pucks[self.puck_id]

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device registry information for this entity."""

        return {
            "identifiers": {(DOMAIN, self.puck_data.id)},
            "name": self.puck_data.attributes['name'],
            "manufacturer": "Flair",
            "model": "Puck",
            "configuration_url": "https://my.flair.co/",
        }

    @property
    def unique_id(self) -> str:
        """Sets unique ID for this entity."""

        return str(self.puck_data.id) + '_rssi'

    @property
    def name(self) -> str:
        """Return name of the entity."""

        return "RSSI"

    @property
    def has_entity_name(self) -> bool:
        """Indicate that entity has name defined."""

        return True

    @property
    def native_value(self) -> float:
        """Return RSSI reading."""

        return self.puck_data.attributes['current-rssi']

    @property
    def native_unit_of_measurement(self) -> str:
        """Return dBm as the native unit."""

        return SIGNAL_STRENGTH_DECIBELS_MILLIWATT

    @property
    def device_class(self) -> SensorDeviceClass:
        """Return entity device class."""

        return SensorDeviceClass.SIGNAL_STRENGTH

    @property
    def state_class(self) -> SensorStateClass:
        """Return the type of state class."""

        return SensorStateClass.MEASUREMENT

    @property
    def entity_category(self) -> EntityCategory:
        """Set category to diagnostic."""

        return EntityCategory.DIAGNOSTIC

    @property
    def available(self) -> bool:
        """Return true if device is available."""

        if not self.puck_data.attributes['inactive']:
            return True
        else:
            return False


class PuckPressure(CoordinatorEntity, SensorEntity):
    """Representation of Puck pressure reading."""

    def __init__(self, coordinator, structure_id, puck_id):
        super().__init__(coordinator)
        self.puck_id = puck_id
        self.structure_id = structure_id

    @property
    def puck_data(self) -> Puck:
        """Handle coordinator puck data."""

        return self.coordinator.data.structures[self.structure_id].pucks[self.puck_id]

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device registry information for this entity."""

        return {
            "identifiers": {(DOMAIN, self.puck_data.id)},
            "name": self.puck_data.attributes['name'],
            "manufacturer": "Flair",
            "model": "Puck",
            "configuration_url": "https://my.flair.co/",
        }

    @property
    def unique_id(self) -> str:
        """Sets unique ID for this entity."""

        return str(self.puck_data.id) + '_pressure'

    @property
    def name(self) -> str:
        """Return name of the entity."""

        return "Pressure"

    @property
    def has_entity_name(self) -> bool:
        """Indicate that entity has name defined."""

        return True

    @property
    def native_value(self) -> float:
        """Return pressure reading."""

        return round(self.puck_data.current_reading['room-pressure'], 2)

    @property
    def native_unit_of_measurement(self) -> str:
        """Return kPa as the native unit."""

        return PRESSURE_KPA

    @property
    def device_class(self) -> SensorDeviceClass:
        """Return entity device class."""

        return SensorDeviceClass.PRESSURE

    @property
    def state_class(self) -> SensorStateClass:
        """Return the type of state class."""

        return SensorStateClass.MEASUREMENT

    @property
    def available(self) -> bool:
        """Return true if device is available."""

        if not self.puck_data.attributes['inactive']:
            return True
        else:
            return False


class DuctTemp(CoordinatorEntity, SensorEntity):
    """Representation of Duct Temperature."""

    def __init__(self, coordinator, structure_id, vent_id):
        super().__init__(coordinator)
        self.vent_id = vent_id
        self.structure_id = structure_id

    @property
    def vent_data(self) -> Vent:
        """Handle coordinator vent data."""

        return self.coordinator.data.structures[self.structure_id].vents[self.vent_id]

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device registry information for this entity."""

        return {
            "identifiers": {(DOMAIN, self.vent_data.id)},
            "name": self.vent_data.attributes['name'],
            "manufacturer": "Flair",
            "model": "Vent",
            "configuration_url": "https://my.flair.co/",
        }

    @property
    def unique_id(self) -> str:
        """Sets unique ID for this entity."""

        return str(self.vent_data.id) + '_duct_temperature'

    @property
    def name(self) -> str:
        """Return name of the entity."""

        return "Duct temperature"

    @property
    def has_entity_name(self) -> bool:
        """Indicate that entity has name defined."""

        return True

    @property
    def native_value(self) -> float:
        """Return current temperature in Celsius."""

        return self.vent_data.current_reading['duct-temperature-c']

    @property
    def native_unit_of_measurement(self) -> str:
        """Return Celsius as the native unit."""

        return TEMP_CELSIUS

    @property
    def device_class(self) -> SensorDeviceClass:
        """Return entity device class."""

        return SensorDeviceClass.TEMPERATURE

    @property
    def state_class(self) -> SensorStateClass:
        """Return the type of state class."""

        return SensorStateClass.MEASUREMENT

    @property
    def available(self) -> bool:
        """Return true if device is available."""

        if not self.vent_data.attributes['inactive']:
            return True
        else:
            return False


class DuctPressure(CoordinatorEntity, SensorEntity):
    """Representation of Duct Pressure."""

    def __init__(self, coordinator, structure_id, vent_id):
        super().__init__(coordinator)
        self.vent_id = vent_id
        self.structure_id = structure_id

    @property
    def vent_data(self) -> Vent:
        """Handle coordinator vent data."""

        return self.coordinator.data.structures[self.structure_id].vents[self.vent_id]

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device registry information for this entity."""

        return {
            "identifiers": {(DOMAIN, self.vent_data.id)},
            "name": self.vent_data.attributes['name'],
            "manufacturer": "Flair",
            "model": "Vent",
            "configuration_url": "https://my.flair.co/",
        }

    @property
    def unique_id(self) -> str:
        """Sets unique ID for this entity."""

        return str(self.vent_data.id) + '_duct_pressure'

    @property
    def name(self) -> str:
        """Return name of the entity."""

        return "Duct pressure"

    @property
    def has_entity_name(self) -> bool:
        """Indicate that entity has name defined."""

        return True

    @property
    def native_value(self) -> float:
        """Return current pressure in kPa."""

        return round(self.vent_data.current_reading['duct-pressure'], 2)

    @property
    def native_unit_of_measurement(self) -> str:
        """Return kPa as the native unit."""

        return PRESSURE_KPA

    @property
    def device_class(self) -> SensorDeviceClass:
        """Return entity device class."""

        return SensorDeviceClass.PRESSURE

    @property
    def state_class(self) -> SensorStateClass:
        """Return the type of state class."""

        return SensorStateClass.MEASUREMENT

    @property
    def available(self) -> bool:
        """Return true if device is available."""

        if not self.vent_data.attributes['inactive']:
            return True
        else:
            return False


class VentVoltage(CoordinatorEntity, SensorEntity):
    """Representation of Vent Voltage."""

    def __init__(self, coordinator, structure_id, vent_id):
        super().__init__(coordinator)
        self.vent_id = vent_id
        self.structure_id = structure_id


    @property
    def vent_data(self) -> Vent:
        """Handle coordinator vent data."""

        return self.coordinator.data.structures[self.structure_id].vents[self.vent_id]

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device registry information for this entity."""

        return {
            "identifiers": {(DOMAIN, self.vent_data.id)},
            "name": self.vent_data.attributes['name'],
            "manufacturer": "Flair",
            "model": "Vent",
            "configuration_url": "https://my.flair.co/",
        }

    @property
    def unique_id(self) -> str:
        """Sets unique ID for this entity."""

        return str(self.vent_data.id) + '_voltage'

    @property
    def name(self) -> str:
        """Return name of the entity."""

        return "Voltage"

    @property
    def has_entity_name(self) -> bool:
        """Indicate that entity has name defined."""

        return True

    @property
    def native_value(self) -> float:
        """Return voltage measurement."""

        return self.vent_data.attributes['voltage']

    @property
    def native_unit_of_measurement(self) -> str:
        """Return volts as the native unit."""

        return ELECTRIC_POTENTIAL_VOLT

    @property
    def device_class(self) -> SensorDeviceClass:
        """Return entity device class."""

        return SensorDeviceClass.VOLTAGE

    @property
    def state_class(self) -> SensorStateClass:
        """Return the type of state class."""

        return SensorStateClass.MEASUREMENT

    @property
    def entity_category(self) -> EntityCategory:
        """Set category to diagnostic."""

        return EntityCategory.DIAGNOSTIC

    @property
    def available(self) -> bool:
        """Return true if device is available."""

        if not self.vent_data.attributes['inactive']:
            return True
        else:
            return False


class VentRSSI(CoordinatorEntity, SensorEntity):
    """Representation of Vent RSSI."""

    def __init__(self, coordinator, structure_id, vent_id):
        super().__init__(coordinator)
        self.vent_id = vent_id
        self.structure_id = structure_id

    @property
    def vent_data(self) -> Vent:
        """Handle coordinator vent data."""

        return self.coordinator.data.structures[self.structure_id].vents[self.vent_id]

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device registry information for this entity."""

        return {
            "identifiers": {(DOMAIN, self.vent_data.id)},
            "name": self.vent_data.attributes['name'],
            "manufacturer": "Flair",
            "model": "Vent",
            "configuration_url": "https://my.flair.co/",
        }

    @property
    def unique_id(self) -> str:
        """Sets unique ID for this entity."""

        return str(self.vent_data.id) + '_rssi'

    @property
    def name(self) -> str:
        """Return name of the entity."""

        return "RSSI"

    @property
    def has_entity_name(self) -> bool:
        """Indicate that entity has name defined."""

        return True

    @property
    def native_value(self) -> int:
        """Return RSSI reading."""

        return self.vent_data.attributes['current-rssi']

    @property
    def native_unit_of_measurement(self) -> str:
        """Return dBm as the native unit."""

        return SIGNAL_STRENGTH_DECIBELS_MILLIWATT

    @property
    def device_class(self) -> SensorDeviceClass:
        """Return entity device class."""

        return SensorDeviceClass.SIGNAL_STRENGTH

    @property
    def state_class(self) -> SensorStateClass:
        """Return the type of state class."""

        return SensorStateClass.MEASUREMENT

    @property
    def entity_category(self) -> EntityCategory:
        """Set category to diagnostic."""

        return EntityCategory.DIAGNOSTIC

    @property
    def available(self) -> bool:
        """Return true if device is available."""

        if not self.vent_data.attributes['inactive']:
            return True
        else:
            return False


class HoldTempUntil(CoordinatorEntity, SensorEntity):
    """Representation of Room Temperature Hold End Time."""

    def __init__(self, coordinator, structure_id, room_id):
        super().__init__(coordinator)
        self.room_id = room_id
        self.structure_id = structure_id


    @property
    def room_data(self) -> Room:
        """Handle coordinator room data."""

        return self.coordinator.data.structures[self.structure_id].rooms[self.room_id]

    @property
    def structure_data(self) -> Structure:
        """Handle coordinator structure data."""

        return self.coordinator.data.structures[self.structure_id]

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device registry information for this entity."""

        return {
            "identifiers": {(DOMAIN, self.room_data.id)},
            "name": self.room_data.attributes['name'],
            "manufacturer": "Flair",
            "model": "Room",
            "configuration_url": "https://my.flair.co/",
        }

    @property
    def unique_id(self) -> str:
        """Sets unique ID for this entity."""

        return str(self.room_data.id) + '_hold_until'

    @property
    def name(self) -> str:
        """Return name of the entity."""

        return "Temperature holding until"

    @property
    def has_entity_name(self) -> bool:
        """Indicate that entity has name defined."""

        return True

    @property
    def native_value(self) -> datetime:
        """Date/time when hold will end.

        When room temperature is set manually,
        returns date/time when hold will end.
        """

        if self.room_data.attributes['hold-until']:
            return datetime.fromisoformat(self.room_data.attributes['hold-until'])

    @property
    def device_class(self) -> SensorDeviceClass:
        """Return entity device class."""

        return SensorDeviceClass.TIMESTAMP

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Disable entity if system mode is set to manual on initial registration."""

        system_mode = self.structure_data.attributes['mode']
        if system_mode == 'manual':
            return False
        else:
            return True

    @property
    def available(self) -> bool:
        """Determine if device is available.

        Return true if temp is set manually
        and structure has a default hold duration
        other than next event.
        """

        if self.room_data.attributes['hold-until']:
            return True
        else:
            return False

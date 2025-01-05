"""Climate platform for Flair integration."""
from __future__ import annotations

from typing import Any

from flairaio.exceptions import FlairError
from flairaio.model import HVACUnit, Puck, Room, Structure

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.components.climate.const import (
    ATTR_HVAC_MODE,
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    SWING_OFF,
    SWING_ON,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    UnitOfTemperature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.unit_system import METRIC_SYSTEM

from .const import (
    DOMAIN,
    HVAC_AVAILABLE_FAN_SPEEDS,
    HVAC_AVAILABLE_MODES_MAP,
    HVAC_CURRENT_ACTION,
    HVAC_CURRENT_FAN_SPEED,
    HVAC_CURRENT_MODE_MAP,
    HVAC_SWING_STATE,
    LOGGER,
    ROOM_HVAC_MAP,
)
from .coordinator import FlairDataUpdateCoordinator

# Mappings
ROOM_HVAC_MAP_TO_FLAIR = {v: k for (k, v) in ROOM_HVAC_MAP.items()}
HASS_HVAC_MODE_TO_FLAIR = {v: k for (k, v) in HVAC_CURRENT_MODE_MAP.items()}
HASS_HVAC_FAN_SPEED_TO_FLAIR = {v: k for (k, v) in HVAC_CURRENT_FAN_SPEED.items()}
HASS_HVAC_SWING_TO_FLAIR = {v: k for (k, v) in HVAC_SWING_STATE.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Flair Climate Entities."""

    coordinator: FlairDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    climates = []

    for structure_id, structure_data in coordinator.data.structures.items():
        # Structure-level climate entity
        climates.append(StructureClimate(coordinator, structure_id))

        # Room-level climate entities
        if structure_data.rooms:
            for room_id in structure_data.rooms:
                climates.append(RoomTemp(coordinator, structure_id, room_id))

        # IR mini-split / advanced HVAC units
        if structure_data.hvac_units:
            for hvac_id, hvac_data in structure_data.hvac_units.items():
                constraints = hvac_data.attributes["constraints"]
                if isinstance(constraints, dict):  # means it's a more advanced IR device
                    codesets = hvac_data.attributes["codesets"][0]
                    if (
                        "temperature-scale" not in constraints
                        and "temperature-scale" not in codesets
                    ):
                        unit_name = hvac_data.attributes["name"]
                        LOGGER.error(
                            f"Flair HVAC Unit {unit_name} does not have a temperature scale. "
                            "Contact Flair support to get this fixed."
                        )
                    else:
                        climates.append(HVAC(coordinator, structure_id, hvac_id))

    async_add_entities(climates)


class StructureClimate(CoordinatorEntity, ClimateEntity):
    """Representation of Structure-wide HVAC (like a central thermostat)."""

    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coordinator, structure_id):
        super().__init__(coordinator)
        self.structure_id = structure_id

    @property
    def structure_data(self) -> Structure:
        return self.coordinator.data.structures[self.structure_id]

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self.structure_data.id)},
            "name": self.structure_data.attributes["name"],
            "manufacturer": "Flair",
            "model": "Structure",
            "configuration_url": "https://my.flair.co/",
        }

    @property
    def unique_id(self) -> str:
        return f"{self.structure_data.id}_climate"

    @property
    def name(self) -> str:
        return "Structure"

    @property
    def has_entity_name(self) -> bool:
        return True

    @property
    def temperature_unit(self) -> UnitOfTemperature:
        # Convert celsius/fahrenheit based on HA’s system
        return (
            UnitOfTemperature.CELSIUS
            if self.hass.config.units is METRIC_SYSTEM
            else UnitOfTemperature.FAHRENHEIT
        )

    @property
    def target_temperature(self) -> float:
        """Return the structure set point, converting if necessary."""
        c_value = self.structure_data.attributes["set-point-temperature-c"]
        if self.hass.config.units is METRIC_SYSTEM:
            return c_value
        return round((c_value * 9 / 5) + 32)

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Map structure-heat-cool-mode to an HA HVACMode."""
        flair_mode = self.structure_data.attributes["structure-heat-cool-mode"]
        return ROOM_HVAC_MAP.get(flair_mode, HVACMode.OFF)

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Off, Heat, Cool, Heat/Cool at the structure level."""
        return [HVACMode.OFF, HVACMode.COOL, HVACMode.HEAT, HVACMode.HEAT_COOL]

    @property
    def supported_features(self) -> int:
        return ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.TURN_OFF

    @property
    def entity_registry_enabled_default(self) -> bool:
        # Disable if structure is in "manual" mode
        return self.structure_data.attributes["mode"] != "manual"

    @property
    def available(self) -> bool:
        # Also show as unavailable if "manual" system mode
        return self.structure_data.attributes["mode"] != "manual"

    async def async_turn_off(self) -> None:
        """Change structure's heat-cool-mode to 'float' which means off."""
        await self._update_structure_mode("float")
        self.structure_data.attributes["structure-heat-cool-mode"] = "float"
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set structure hvac mode."""
        flair_mode = ROOM_HVAC_MAP_TO_FLAIR.get(hvac_mode, "float")
        await self._update_structure_mode(flair_mode)
        self.structure_data.attributes["structure-heat-cool-mode"] = flair_mode
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs) -> None:
        """Change the set-point temperature at the structure."""
        if self.structure_data.attributes["set-point-mode"] == (
            "Home Evenness For Active Rooms Follow Third Party"
        ):
            LOGGER.error(
                f"Target temperature for {self.structure_data.attributes['name']} can only be set "
                "when the set point controller is Flair app"
            )
            return

        new_temp = kwargs.get(ATTR_TEMPERATURE)
        if not new_temp:
            LOGGER.error(f"Missing valid arguments for set_temperature in {kwargs}")
            return

        if self.hass.config.units is not METRIC_SYSTEM:
            # Convert from F to C
            new_temp = round(((new_temp - 32) * 5 / 9), 2)

        await self._update_structure_temp(new_temp)
        self.structure_data.attributes["set-point-temperature-c"] = new_temp
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def _update_structure_mode(self, flair_mode: str) -> None:
        """Send update to the structure for its heat-cool-mode."""
        data = {"structure-heat-cool-mode": flair_mode}
        await self.coordinator.client.update("structures", self.structure_data.id, data, relationships={})

    async def _update_structure_temp(self, new_temp_c: float) -> None:
        """Send new set point to structure in celsius."""
        data = {"set-point-temperature-c": new_temp_c}
        await self.coordinator.client.update("structures", self.structure_data.id, data, relationships={})


class RoomTemp(CoordinatorEntity, ClimateEntity):
    """Representation of a single Flair Room as a climate entity."""

    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coordinator, structure_id, room_id):
        super().__init__(coordinator)
        self.structure_id = structure_id
        self.room_id = room_id

    @property
    def room_data(self) -> Room:
        return self.coordinator.data.structures[self.structure_id].rooms[self.room_id]

    @property
    def structure_data(self) -> Structure:
        return self.coordinator.data.structures[self.structure_id]

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self.room_data.id)},
            "name": self.room_data.attributes["name"],
            "manufacturer": "Flair",
            "model": "Room",
            "configuration_url": "https://my.flair.co/",
        }

    @property
    def unique_id(self) -> str:
        return f"{self.room_data.id}_room"

    @property
    def name(self) -> str:
        return "Room"

    @property
    def has_entity_name(self) -> bool:
        return True

    @property
    def icon(self) -> str:
        return "mdi:door-open"

    @property
    def temperature_unit(self) -> UnitOfTemperature:
        """Flair room temps are always in celsius natively."""
        return UnitOfTemperature.CELSIUS

    @property
    def hvac_mode(self) -> HVACMode | None:
        """If the room is inactive, reflect OFF. Otherwise, map structure-heat-cool-mode."""
        if not self.room_data.attributes.get("active", True):
            return HVACMode.OFF

        flair_mode = self.structure_data.attributes["structure-heat-cool-mode"]
        return ROOM_HVAC_MAP.get(flair_mode, HVACMode.OFF)

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Allow OFF, COOL, HEAT, HEAT_COOL for rooms."""
        return [HVACMode.OFF, HVACMode.COOL, HVACMode.HEAT, HVACMode.HEAT_COOL]

    @property
    def current_temperature(self) -> float:
        return self.room_data.attributes.get("current-temperature-c") or 0.0

    @property
    def target_temperature(self) -> float:
        return self.room_data.attributes.get("set-point-c") or 0.0

    @property
    def current_humidity(self) -> int:
        return self.room_data.attributes.get("current-humidity") or 0

    @property
    def supported_features(self) -> int:
        return ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.TURN_OFF

    @property
    def entity_registry_enabled_default(self) -> bool:
        # If the system is manual, we don't enable by default
        return self.structure_data.attributes["mode"] != "manual"

    @property
    def available(self) -> bool:
        # If the system is manual, we show as unavailable
        if self.structure_data.attributes["mode"] == "manual":
            return False
        # Also, if the room has no current temperature reading, we consider it not available
        return self.room_data.attributes.get("current-temperature-c") is not None

    async def async_turn_off(self) -> None:
        """
        Instead of changing structure-heat-cool-mode for just this room,
        we can mark this room as inactive in Flair's API.
        """
        data = {"active": False}
        await self.coordinator.client.update("rooms", self.room_data.id, data, relationships={})
        self.room_data.attributes["active"] = False
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """
        If user sets OFF => mark the room inactive.
        Otherwise => mark the room active, then update structure mode.
        """
        if hvac_mode == HVACMode.OFF:
            # Mark room inactive
            data = {"active": False}
            await self.coordinator.client.update("rooms", self.room_data.id, data, relationships={})
            self.room_data.attributes["active"] = False
            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()
            return

        # If not OFF, ensure room is active
        if not self.room_data.attributes.get("active", True):
            data = {"active": True}
            await self.coordinator.client.update("rooms", self.room_data.id, data, relationships={})
            self.room_data.attributes["active"] = True

        # Now set the structure’s heat-cool-mode
        flair_mode = ROOM_HVAC_MAP_TO_FLAIR.get(hvac_mode, "float")
        struct_data = {"structure-heat-cool-mode": flair_mode}
        await self.coordinator.client.update("structures", self.structure_data.id, struct_data, relationships={})
        self.structure_data.attributes["structure-heat-cool-mode"] = flair_mode
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature for this room."""
        new_temp = kwargs.get(ATTR_TEMPERATURE)
        if new_temp is None:
            LOGGER.error(f"Missing valid arguments for set_temperature in {kwargs}")
            return

        data = {"set-point-c": new_temp, "active": True}
        await self.coordinator.client.update("rooms", self.room_data.id, data, relationships={})
        self.room_data.attributes["set-point-c"] = new_temp
        self.room_data.attributes["active"] = True
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()


class HVAC(CoordinatorEntity, ClimateEntity):
    """
    Representation of a single IR mini-split HVAC unit, which uses
    Flair’s IR commands. If you want “OFF => inactive room” logic,
    you can implement that similarly, but typically these IR units
    are controlled individually and *may* or may not reflect the
    underlying room's active status.
    """

    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coordinator, structure_id, hvac_id):
        super().__init__(coordinator)
        self.structure_id = structure_id
        self.hvac_id = hvac_id

    @property
    def hvac_data(self) -> HVACUnit:
        return self.coordinator.data.structures[self.structure_id].hvac_units[self.hvac_id]

    @property
    def structure_data(self) -> Structure:
        return self.coordinator.data.structures[self.structure_id]

    @property
    def puck_data(self) -> Puck:
        # For diagnostic availability, etc.
        puck_id = self.hvac_data.relationships["puck"]["data"]["id"]
        return self.structure_data.pucks[puck_id]

    @property
    def room_data(self) -> Room:
        room_id = self.hvac_data.relationships["room"]["data"]["id"]
        return self.structure_data.rooms[room_id]

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self.hvac_data.id)},
            "name": self.hvac_data.attributes["name"],
            "manufacturer": self.hvac_data.attributes["make-name"],
            "model": "HVAC Unit",
            "configuration_url": "https://my.flair.co/",
        }

    @property
    def unique_id(self) -> str:
        return f"{self.hvac_data.id}_hvac_unit"

    @property
    def name(self) -> str:
        return "HVAC unit"

    @property
    def has_entity_name(self) -> bool:
        return True

    @property
    def icon(self) -> str:
        return "mdi:hvac"

    @property
    def temperature_unit(self) -> UnitOfTemperature:
        # The unit is read from constraints
        constraints = self.hvac_data.attributes["constraints"]
        if "temperature-scale" in constraints:
            scale = constraints["temperature-scale"]
        else:
            scale = self.hvac_data.attributes["codesets"][0]["temperature-scale"]

        return (
            UnitOfTemperature.FAHRENHEIT
            if scale == "F"
            else UnitOfTemperature.CELSIUS
        )

    @property
    def is_on(self) -> bool:
        """If Flair says 'power': 'On', then it's on."""
        return self.hvac_data.attributes["power"] == "On"

    # ...Remaining logic for modes, fan speeds, swing, etc. remains largely the same...

    # If you want “OFF => inactive room,” replicate the same pattern from RoomTemp
    # (But typically these IR units are “manually” toggled, so it’s up to you.)

    # ...

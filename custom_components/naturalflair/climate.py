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
    HVAC_AVAILABLE_FAN_SPEEDS,       # e.g. [FAN_AUTO, FAN_LOW, FAN_MEDIUM, FAN_HIGH]
    HVAC_AVAILABLE_MODES_MAP,         # e.g. {"Cool": HVACMode.COOL, "Heat": HVACMode.HEAT, etc.}
    HVAC_CURRENT_ACTION,              # e.g. {"Cool": HVACAction.COOLING, "Heat": HVACAction.HEATING, ...}
    HVAC_CURRENT_FAN_SPEED,           # e.g. {"Auto": FAN_AUTO, "Low": FAN_LOW, ...}
    HVAC_CURRENT_MODE_MAP,            # e.g. {"Cool": HVACMode.COOL, "Off": HVACMode.OFF, ...}
    HVAC_SWING_STATE,                 # e.g. {"On": SWING_ON, "Off": SWING_OFF}
    LOGGER,
    ROOM_HVAC_MAP,                    # e.g. {"heat": HVACMode.HEAT, "float": HVACMode.OFF, ...}
)
from .coordinator import FlairDataUpdateCoordinator

# Reverse maps for converting from HA -> Flair
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

    # Loop through each structure
    for structure_id, structure_data in coordinator.data.structures.items():
        # Add a StructureClimate (like a central thermostat)
        climates.append(StructureClimate(coordinator, structure_id))

        # Add a RoomTemp entity for each room
        if structure_data.rooms:
            for room_id in structure_data.rooms:
                climates.append(RoomTemp(coordinator, structure_id, room_id))

        # Add an HVAC entity for each advanced IR mini-split / HVAC unit
        if structure_data.hvac_units:
            for hvac_id, hvac_data in structure_data.hvac_units.items():
                constraints = hvac_data.attributes["constraints"]
                if isinstance(constraints, dict):  # means it's a more advanced IR device
                    codesets = hvac_data.attributes["codesets"][0]
                    # If no recognized temperature scale, log an error
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
    def icon(self) -> str:
        return "mdi:home-thermometer"

    @property
    def temperature_unit(self) -> UnitOfTemperature:
        """Convert celsius/fahrenheit based on HA’s system settings."""
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
        """Disable if structure is in 'manual' mode."""
        return self.structure_data.attributes["mode"] != "manual"

    @property
    def available(self) -> bool:
        """Show as unavailable if 'manual' system mode."""
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

        # Convert from F to C if needed
        if self.hass.config.units is not METRIC_SYSTEM:
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
        return f"{self.room_data.id}"

    @property
    def name(self) -> str:
        """Use the Flair room name directly, so we don't get 'Room Room'."""
        return self.room_data.attributes["name"]

    @property
    def has_entity_name(self) -> bool:
        """False so it doesn't append anything to the name."""
        return False

    @property
    def icon(self) -> str:
        """Use a door icon to represent a room."""
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
        """If the system is manual, we don't enable by default."""
        return self.structure_data.attributes["mode"] != "manual"

    @property
    def available(self) -> bool:
        """If the system is manual, or there's no current temp reading, show unavailable."""
        if self.structure_data.attributes["mode"] == "manual":
            return False
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
        """Set new target temperature for this room (in Celsius)."""
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
    Flair’s IR commands. Typically, these devices are controlled
    individually. 
    If you want “OFF => inactive room,” replicate the pattern from RoomTemp.
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
        """For diagnostic availability, etc."""
        puck_id = self.hvac_data.relationships["puck"]["data"]["id"]
        return self.structure_data.pucks[puck_id]

    @property
    def room_data(self) -> Room:
        """Return the room object to which this HVAC is tied."""
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
        """Show a generic name plus the device name if needed."""
        return "HVAC unit"

    @property
    def has_entity_name(self) -> bool:
        return True

    @property
    def icon(self) -> str:
        return "mdi:hvac"

    @property
    def temperature_unit(self) -> UnitOfTemperature:
        """
        The unit is read from constraints or codesets. 
        This might be 'F' or 'C' based on your Flair IR config.
        """
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
        return self.hvac_data.attributes.get("power") == "On"

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Map Flair's 'mode' (cool/heat/fan/etc.) to an HA HVACMode."""
        flair_mode = self.hvac_data.attributes.get("mode", "Off")
        return HVAC_AVAILABLE_MODES_MAP.get(flair_mode, HVACMode.OFF)

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """
        Return all possible modes (based on the constraints).
        Typically: OFF, COOL, HEAT, DRY, FAN_ONLY, AUTO, etc.
        For Home Assistant, we often map 'Auto' -> HEAT_COOL or so.
        """
        # If your constraints/codesets contain certain modes only, 
        # you could dynamically parse them here. We'll assume 
        # something like [OFF, COOL, HEAT, FAN_ONLY, DRY, HEAT_COOL].
        return list(HASS_HVAC_MODE_TO_FLAIR.keys())

    @property
    def fan_mode(self) -> str | None:
        """Return the current fan speed in HA terms (auto, low, med, high)."""
        flair_fan = self.hvac_data.attributes.get("fan-speed")
        if flair_fan in HVAC_CURRENT_FAN_SPEED:
            return HVAC_CURRENT_FAN_SPEED[flair_fan]
        return FAN_AUTO  # fallback if unknown

    @property
    def fan_modes(self) -> list[str]:
        """Return all supported fan speeds."""
        return HVAC_AVAILABLE_FAN_SPEEDS  # e.g. [FAN_AUTO, FAN_LOW, FAN_MEDIUM, FAN_HIGH]

    @property
    def swing_mode(self) -> str | None:
        """Return the current swing state: 'on' or 'off' in HA terms."""
        flair_swing = self.hvac_data.attributes.get("swing")
        if flair_swing in HVAC_SWING_STATE:
            return HVAC_SWING_STATE[flair_swing]
        return SWING_OFF  # default if unknown

    @property
    def swing_modes(self) -> list[str]:
        """Return all supported swing modes."""
        return [SWING_OFF, SWING_ON]

    @property
    def current_temperature(self) -> float | None:
        """
        For IR units, Flair typically reports the temperature 
        from the associated puck or room. 
        """
        return self.room_data.attributes.get("current-temperature-c", 0.0)

    @property
    def target_temperature(self) -> float | None:
        """
        The set-point that Flair is sending to the mini-split. 
        This is stored in the hvac_data attributes as 'temperature'.
        """
        current_set = self.hvac_data.attributes.get("temperature")
        if current_set is None:
            return None
        # If the device uses Fahrenheit, just return as-is. 
        # If it's Celsius, we might also just return as-is. 
        # Typically, the user will want to see it in the same scale as the device. 
        return current_set

    @property
    def hvac_action(self) -> HVACAction | None:
        """
        The current operation (idle, heating, cooling, etc.)
        derived from hvac_data attributes or from mode/power.
        """
        # If it's off, we say 'off'.
        if not self.is_on:
            return HVACAction.OFF

        flair_mode = self.hvac_data.attributes.get("mode", "Off")
        return HVAC_CURRENT_ACTION.get(flair_mode, HVACAction.IDLE)

    @property
    def supported_features(self) -> int:
        """Fan speed, swing, and target temp are typically supported for IR units."""
        return (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.SWING_MODE
        )

    async def async_turn_on(self) -> None:
        """Turn the unit on (set power = 'On')."""
        await self._update_hvac({"power": "On"})
        self.hvac_data.attributes["power"] = "On"
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        """Turn the unit off (set power = 'Off')."""
        await self._update_hvac({"power": "Off"})
        self.hvac_data.attributes["power"] = "Off"
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode (cool, heat, etc.), turning on if needed."""
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
            return

        # Ensure it's powered on
        if not self.is_on:
            await self.async_turn_on()

        # Convert to Flair’s mode
        flair_mode = HASS_HVAC_MODE_TO_FLAIR.get(hvac_mode, "Off")
        await self._update_hvac({"mode": flair_mode})
        self.hvac_data.attributes["mode"] = flair_mode
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs) -> None:
        """
        Set a new target temperature for the mini-split (the IR device).
        We'll pass it as either F or C, depending on `temperature_unit`.
        """
        new_temp = kwargs.get(ATTR_TEMPERATURE)
        if new_temp is None:
            LOGGER.error(f"Missing valid arguments for set_temperature in {kwargs}")
            return

        # Make sure the unit is ON before adjusting temperature
        if not self.is_on:
            await self.async_turn_on()

        # If the device scale is Fahrenheit, pass the value as F. 
        # If Celsius, pass it as C. 
        # Typically, you'd confirm how Flair expects it. We'll assume if `temperature_unit` is F, 
        # then we just send the integer or float as is. 
        # If it's C, we do the same. 
        # But in real code, you might need to pass an integer, etc.
        data = {"temperature": new_temp}
        await self._update_hvac(data)
        self.hvac_data.attributes["temperature"] = new_temp
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Update the fan speed on the mini-split."""
        # Ensure it's on
        if not self.is_on:
            await self.async_turn_on()

        flair_fan = HASS_HVAC_FAN_SPEED_TO_FLAIR.get(fan_mode, "Auto")
        data = {"fan-speed": flair_fan}
        await self._update_hvac(data)
        self.hvac_data.attributes["fan-speed"] = flair_fan
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Update the swing mode (on/off)."""
        # Ensure it's on
        if not self.is_on:
            await self.async_turn_on()

        flair_swing = HASS_HVAC_SWING_TO_FLAIR.get(swing_mode, "Off")
        data = {"swing": flair_swing}
        await self._update_hvac(data)
        self.hvac_data.attributes["swing"] = flair_swing
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def _update_hvac(self, new_attrs: dict[str, Any]) -> None:
        """
        Send the changes to Flair’s API for this HVAC unit.
        E.g. {"mode": "Cool", "temperature": 72, "power": "On", "fan-speed": "High"}
        """
        await self.coordinator.client.update(
            "hvac-units", self.hvac_data.id, new_attrs, relationships={}
        )

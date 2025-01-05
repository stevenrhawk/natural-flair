"""Select platform for Flair integration."""
from __future__ import annotations

from typing import Any

from flairaio.model import Puck, Structure

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    AWAY_MODES,
    DEFAULT_HOLD_DURATION,
    DOMAIN,
    HOME_AWAY_MODE,
    HOME_AWAY_SET_BY,
    PUCK_BACKGROUND,
    SET_POINT_CONTROLLER,
    SYSTEM_MODES,
    TEMPERATURE_SCALES,
)
from .coordinator import FlairDataUpdateCoordinator


DEFAULT_HOLD_TO_FLAIR = {v: k for (k, v) in DEFAULT_HOLD_DURATION.items()}
HOME_AWAY_SET_BY_TO_FLAIR = {v: k for (k, v) in HOME_AWAY_SET_BY.items()}
SET_POINT_CONTROLLER_TO_FLAIR = {v: k for (k, v) in SET_POINT_CONTROLLER.items()}
TEMP_SCALE_TO_FLAIR = {v: k for (k, v) in TEMPERATURE_SCALES.items()}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set Up Flair Select Entities."""

    coordinator: FlairDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    selects = []

    for structure_id, structure_data in coordinator.data.structures.items():
        # Structures
        selects.extend((
            SystemMode(coordinator, structure_id),
            HomeAwayMode(coordinator, structure_id),
            HomeAwaySetBy(coordinator, structure_id),
            DefaultHoldDuration(coordinator, structure_id),
            SetPointController(coordinator, structure_id),
            Schedule(coordinator, structure_id),
            AwayMode(coordinator, structure_id),
        ))

        # Pucks
        if structure_data.pucks:
            for puck_id, puck_data in structure_data.pucks.items():
                selects.extend((
                    PuckBackground(coordinator, structure_id, puck_id),
                    PuckTempScale(coordinator, structure_id, puck_id),
                ))

    async_add_entities(selects)


class SystemMode(CoordinatorEntity, SelectEntity):
    """Representation of System Mode."""

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
        return f"{self.structure_data.id}_system_mode"

    @property
    def name(self) -> str:
        """Return name of the entity."""
        return "System mode"

    @property
    def has_entity_name(self) -> bool:
        """Indicate that entity has name defined."""
        return True

    @property
    def icon(self) -> str:
        """Set icon."""
        return "mdi:home-circle"

    @property
    def current_option(self) -> str:
        """Returns currently active system mode."""
        current_mode = self.structure_data.attributes["mode"]
        return current_mode.capitalize()

    @property
    def options(self) -> list[str]:
        """Return list of all the available system modes."""
        return SYSTEM_MODES

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        lowercase_option = option[0].lower() + option[1:]
        attributes = self.set_attributes(str(lowercase_option))
        await self.coordinator.client.update(
            "structures",
            self.structure_data.id,
            attributes=attributes,
            relationships={},
        )
        self.structure_data.attributes["mode"] = lowercase_option
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @staticmethod
    def set_attributes(mode: str) -> dict[str, str]:
        """Creates attributes dictionary."""
        return {"mode": mode}


class HomeAwayMode(CoordinatorEntity, SelectEntity):
    """Representation of Home/Away Mode."""

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
            "identifiers": {(DOMAIN, self.structure_id)},
            "name": self.structure_data.attributes["name"],
            "manufacturer": "Flair",
            "model": "Structure",
            "configuration_url": "https://my.flair.co/",
        }

    @property
    def unique_id(self) -> str:
        """Sets unique ID for this entity."""
        return f"{self.structure_data.id}_home_away_mode"

    @property
    def name(self) -> str:
        """Return name of the entity."""
        return "Home/Away"

    @property
    def has_entity_name(self) -> bool:
        """Indicate that entity has name defined."""
        return True

    @property
    def icon(self) -> str:
        """Set icon."""
        return "mdi:location-enter" if self.structure_data.attributes["home"] else "mdi:location-exit"

    @property
    def current_option(self) -> str | None:
        """Returns currently active home/away mode."""
        currently_home = self.structure_data.attributes["home"]
        return "Home" if currently_home else "Away"

    @property
    def options(self) -> list[str]:
        """Return list of all the available home/away modes."""
        return HOME_AWAY_MODE

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Disable entity if system mode is set to manual on initial registration."""
        system_mode = self.structure_data.attributes["mode"]
        return system_mode != "manual"

    @property
    def available(self) -> bool:
        """Marks entity as unavailable if system mode is set to Manual."""
        return self.structure_data.attributes["mode"] != "manual"

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        attributes = self.set_attributes(option)
        await self.coordinator.client.update(
            "structures",
            self.structure_data.id,
            attributes=attributes,
            relationships={},
        )
        self.structure_data.attributes["home"] = attributes["home"]
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @staticmethod
    def set_attributes(mode: str) -> dict[str, bool]:
        """Creates attributes dictionary."""
        return {"home": (mode == "Home")}


class HomeAwaySetBy(CoordinatorEntity, SelectEntity):
    """Representation of what sets Home/Away Mode."""

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
            "name": self.structure_data.attributes["name"],
            "manufacturer": "Flair",
            "model": "Structure",
            "configuration_url": "https://my.flair.co/",
        }

    @property
    def unique_id(self) -> str:
        """Sets unique ID for this entity."""
        return f"{self.structure_data.id}_home_away_set_by"

    @property
    def name(self) -> str:
        """Return name of the entity."""
        return "Home/Away mode set by"

    @property
    def has_entity_name(self) -> bool:
        """Indicate that entity has name defined."""
        return True

    @property
    def entity_category(self) -> EntityCategory:
        """Set category to config."""
        return EntityCategory.CONFIG

    @property
    def icon(self) -> str:
        """Set icon."""
        mode = self.structure_data.attributes["home-away-mode"]
        if mode == "Manual":
            return "mdi:account-circle"
        elif mode == "Third Party Home Away":
            return "mdi:thermostat"
        elif mode == "Flair Autohome Autoaway":
            return "mdi:cellphone"
        return "mdi:account-circle"

    @property
    def current_option(self) -> str | None:
        """Returns currently active home/away mode setter."""
        current = self.structure_data.attributes["home-away-mode"]
        return HOME_AWAY_SET_BY.get(current)

    @property
    def options(self) -> list[str]:
        """Return list of all the available home/away setters."""
        if self.structure_data.thermostats:
            return list(HOME_AWAY_SET_BY.values())
        else:
            return ["Manual", "Flair App Geolocation"]

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Disable entity if system mode is set to manual on initial registration."""
        return self.structure_data.attributes["mode"] != "manual"

    @property
    def available(self) -> bool:
        """Marks entity as unavailable if system mode is set to Manual."""
        return self.structure_data.attributes["mode"] != "manual"

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        ha_to_flair = HOME_AWAY_SET_BY_TO_FLAIR.get(option)
        attributes = self.set_attributes(ha_to_flair)
        await self.coordinator.client.update(
            "structures",
            self.structure_data.id,
            attributes=attributes,
            relationships={},
        )
        self.structure_data.attributes["home-away-mode"] = ha_to_flair
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @staticmethod
    def set_attributes(setter: str) -> dict[str, str]:
        """Creates attributes dictionary."""
        return {"home-away-mode": setter}


class DefaultHoldDuration(CoordinatorEntity, SelectEntity):
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
            "name": self.structure_data.attributes["name"],
            "manufacturer": "Flair",
            "model": "Structure",
            "configuration_url": "https://my.flair.co/",
        }

    @property
    def unique_id(self) -> str:
        """Sets unique ID for this entity."""
        return f"{self.structure_data.id}_default_hold_duration"

    @property
    def name(self) -> str:
        """Return name of the entity."""
        return "Default hold duration"

    @property
    def has_entity_name(self) -> bool:
        """Indicate that entity has name defined."""
        return True

    @property
    def entity_category(self) -> EntityCategory:
        """Set category to config."""
        return EntityCategory.CONFIG

    @property
    def icon(self) -> str:
        """Set icon."""
        return "mdi:timer"

    @property
    def current_option(self) -> str | None:
        """Returns currently active default hold duration."""
        current = self.structure_data.attributes["default-hold-duration"]
        return DEFAULT_HOLD_DURATION.get(current)

    @property
    def options(self) -> list[str]:
        """Return list of all the available default hold durations."""
        return list(DEFAULT_HOLD_DURATION.values())

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Disable entity if system mode is set to manual on initial registration."""
        return self.structure_data.attributes["mode"] != "manual"

    @property
    def available(self) -> bool:
        """Marks entity as unavailable if system mode is set to Manual."""
        return self.structure_data.attributes["mode"] != "manual"

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        ha_to_flair = DEFAULT_HOLD_TO_FLAIR.get(option)
        attributes = self.set_attributes(ha_to_flair)
        await self.coordinator.client.update(
            "structures",
            self.structure_data.id,
            attributes=attributes,
            relationships={},
        )
        self.structure_data.attributes["default-hold-duration"] = ha_to_flair
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @staticmethod
    def set_attributes(duration: str) -> dict[str, str]:
        """Creates attributes dictionary."""
        return {"default-hold-duration": duration}


class SetPointController(CoordinatorEntity, SelectEntity):
    """Representation of set point controller setting."""

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
            "name": self.structure_data.attributes["name"],
            "manufacturer": "Flair",
            "model": "Structure",
            "configuration_url": "https://my.flair.co/",
        }

    @property
    def unique_id(self) -> str:
        """Sets unique ID for this entity."""
        return f"{self.structure_data.id}_set_point_controller"

    @property
    def name(self) -> str:
        """Return name of the entity."""
        return "Set point controller"

    @property
    def has_entity_name(self) -> bool:
        """Indicate that entity has name defined."""
        return True

    @property
    def entity_category(self) -> EntityCategory:
        """Set category to config."""
        return EntityCategory.CONFIG

    @property
    def icon(self) -> str:
        """Set icon."""
        return "mdi:controller"

    @property
    def current_option(self) -> str | None:
        """Returns current set point controller."""
        current = self.structure_data.attributes["set-point-mode"]
        return SET_POINT_CONTROLLER.get(current)

    @property
    def options(self) -> list[str]:
        """Return list of all the available set point controllers."""
        if self.structure_data.thermostats:
            return list(SET_POINT_CONTROLLER.values())
        return ["Flair App"]

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Disable entity if system mode is set to manual on initial registration."""
        return self.structure_data.attributes["mode"] != "manual"

    @property
    def available(self) -> bool:
        """Marks entity as unavailable if system mode is set to Manual."""
        return self.structure_data.attributes["mode"] != "manual"

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        ha_to_flair = SET_POINT_CONTROLLER_TO_FLAIR.get(option)
        attributes = self.set_attributes(ha_to_flair)
        await self.coordinator.client.update(
            "structures",
            self.structure_data.id,
            attributes=attributes,
            relationships={},
        )
        self.structure_data.attributes["set-point-mode"] = ha_to_flair
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @staticmethod
    def set_attributes(option: str) -> dict[str, str]:
        """Creates attributes dictionary."""
        return {"set-point-mode": option}


class Schedule(CoordinatorEntity, SelectEntity):
    """Representation of available structure schedules."""

    def __init__(self, coordinator, structure_id):
        super().__init__(coordinator)
        self.structure_id = structure_id

    @property
    def structure_data(self) -> Structure:
        """Handle coordinator structure data."""
        return self.coordinator.data.structures[self.structure_id]

    @property
    def schedules(self) -> dict[str, str]:
        """Create dictionary with all available schedules."""
        schedules: dict[str, str] = {"No Schedule": "No Schedule"}
        if self.structure_data.schedules:
            for sid, schedule_obj in self.structure_data.schedules.items():
                schedules[schedule_obj.id] = schedule_obj.attributes["name"]
        return schedules

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device registry information for this entity."""
        return {
            "identifiers": {(DOMAIN, self.structure_data.id)},
            "name": self.structure_data.attributes["name"],
            "manufacturer": "Flair",
            "model": "Structure",
            "configuration_url": "https://my.flair.co/",
        }

    @property
    def unique_id(self) -> str:
        """Sets unique ID for this entity."""
        return f"{self.structure_data.id}_schedule"

    @property
    def name(self) -> str:
        """Return name of the entity."""
        return "Active schedule"

    @property
    def has_entity_name(self) -> bool:
        """Indicate that entity has name defined."""
        return True

    @property
    def icon(self) -> str:
        """Set icon."""
        return "mdi:calendar"

    @property
    def current_option(self) -> str:
        """Returns current active schedule."""
        active_schedule = self.structure_data.attributes["active-schedule-id"]
        if active_schedule is None:
            return "No Schedule"
        return self.schedules.get(active_schedule, "No Schedule")

    @property
    def options(self) -> list[str]:
        """Return list of all the available schedules."""
        return list(self.schedules.values())

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Disable entity if system mode is set to manual on initial registration."""
        return self.structure_data.attributes["mode"] != "manual"

    @property
    def available(self) -> bool:
        """Marks entity as unavailable if system mode is set to Manual."""
        return self.structure_data.attributes["mode"] != "manual"

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        schedule_name_to_id = {v: k for k, v in self.schedules.items()}
        ha_to_flair = None if option == "No Schedule" else schedule_name_to_id.get(option)

        attributes = self.set_attributes(ha_to_flair)
        await self.coordinator.client.update(
            "structures",
            self.structure_data.id,
            attributes=attributes,
            relationships={},
        )
        self.structure_data.attributes["active-schedule-id"] = ha_to_flair
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @staticmethod
    def set_attributes(option: str) -> dict[str, str]:
        """Creates attributes dictionary."""
        return {"active-schedule-id": option}


class AwayMode(CoordinatorEntity, SelectEntity):
    """Representation of structure away mode setting."""

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
            "name": self.structure_data.attributes["name"],
            "manufacturer": "Flair",
            "model": "Structure",
            "configuration_url": "https://my.flair.co/",
        }

    @property
    def unique_id(self) -> str:
        """Sets unique ID for this entity."""
        return f"{self.structure_data.id}_away_mode"

    @property
    def name(self) -> str:
        """Return name of the entity."""
        return "Away Mode"

    @property
    def has_entity_name(self) -> bool:
        """Indicate that entity has name defined."""
        return True

    @property
    def entity_category(self) -> EntityCategory:
        """Set category to config."""
        return EntityCategory.CONFIG

    @property
    def icon(self) -> str:
        """Set icon."""
        return "mdi:clipboard-list"

    @property
    def current_option(self) -> str:
        """Returns current away mode setting."""
        return self.structure_data.attributes["structure-away-mode"]

    @property
    def options(self) -> list[str]:
        """Return list of all the available away modes."""
        return AWAY_MODES

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Disable entity if system mode is set to manual on initial registration."""
        return self.structure_data.attributes["mode"] != "manual"

    @property
    def available(self) -> bool:
        """Marks entity as unavailable if system mode is set to Manual."""
        return self.structure_data.attributes["mode"] != "manual"

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        attributes = self.set_attributes(option)
        await self.coordinator.client.update(
            "structures",
            self.structure_data.id,
            attributes=attributes,
            relationships={},
        )
        self.structure_data.attributes["structure-away-mode"] = option
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @staticmethod
    def set_attributes(option: str) -> dict[str, str]:
        """Creates attributes dictionary."""
        return {"structure-away-mode": option}


class PuckBackground(CoordinatorEntity, SelectEntity):
    """Representation of puck background color."""

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
            "name": self.puck_data.attributes["name"],
            "manufacturer": "Flair",
            "model": "Puck",
            "configuration_url": "https://my.flair.co/",
        }

    @property
    def unique_id(self) -> str:
        """Sets unique ID for this entity."""
        return f"{self.puck_data.id}_background_color"

    @property
    def name(self) -> str:
        """Return name of the entity."""
        return "Background color"

    @property
    def has_entity_name(self) -> bool:
        """Indicate that entity has name defined."""
        return True

    @property
    def entity_category(self) -> EntityCategory:
        """Set category to config."""
        return EntityCategory.CONFIG

    @property
    def icon(self) -> str:
        """Set icon."""
        return "mdi:invert-colors"

    @property
    def current_option(self) -> str:
        """Returns current puck background color."""
        return self.puck_data.attributes["puck-display-color"].capitalize()

    @property
    def options(self) -> list[str]:
        """Return list of all the available puck background colors."""
        return PUCK_BACKGROUND

    @property
    def available(self) -> bool:
        """Return true if puck is active."""
        return not self.puck_data.attributes["inactive"]

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        ha_to_flair = option.lower()
        attributes = self.set_attributes(ha_to_flair)
        await self.coordinator.client.update(
            "pucks",
            self.puck_data.id,
            attributes=attributes,
            relationships={},
        )
        self.puck_data.attributes["puck-display-color"] = ha_to_flair
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @staticmethod
    def set_attributes(option: str) -> dict[str, str]:
        """Creates attributes dictionary."""
        return {"puck-display-color": option}


class PuckTempScale(CoordinatorEntity, SelectEntity):
    """Representation of puck temp scale selection."""

    def __init__(self, coordinator, structure_id, puck_id):
        super().__init__(coordinator)
        self.puck_id = puck_id
        self.structure_id = structure_id

    @property
    def puck_data(self) -> Puck:
        """Handle coordinator puck data."""
        return self.coordinator.data.structures[self.structure_id].pucks[self.puck_id]

    @property
    def structure_data(self) -> Structure:
        """Handle coordinator structure data."""
        return self.coordinator.data.structures[self.structure_id]

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device registry information for this entity."""
        # Some pucks might have 'make-name' in attributes
        manufacturer = self.puck_data.attributes.get("make-name", "Flair")

        return {
            "identifiers": {(DOMAIN, self.puck_data.id)},
            "name": self.puck_data.attributes["name"],
            "manufacturer": manufacturer,
            "model": "Puck",
            "configuration_url": "https://my.flair.co/",
        }

    @property
    def unique_id(self) -> str:
        """Sets unique ID for this entity."""
        return f"{self.puck_data.id}_temp_scale"

    @property
    def name(self) -> str:
        """Return name of the entity."""
        return "Temperature scale"

    @property
    def has_entity_name(self) -> bool:
        """Indicate that entity has name defined."""
        return True

    @property
    def entity_category(self) -> EntityCategory:
        """Set category to config."""
        return EntityCategory.CONFIG

    @property
    def icon(self) -> str:
        """Set icon based on the current scale."""
        temp_scale = self.structure_data.attributes["temperature-scale"]
        if temp_scale == "F":
            return "mdi:temperature-fahrenheit"
        if temp_scale == "C":
            return "mdi:temperature-celsius"
        if temp_scale == "K":
            return "mdi:temperature-kelvin"
        return "mdi:thermometer"

    @property
    def current_option(self) -> str:
        """Returns current puck temp scale."""
        current_scale = self.structure_data.attributes["temperature-scale"]
        return TEMPERATURE_SCALES.get(current_scale, "Fahrenheit")

    @property
    def options(self) -> list[str]:
        """Return list of all the available temperature scales."""
        return list(TEMPERATURE_SCALES.values())

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        ha_to_flair = TEMP_SCALE_TO_FLAIR.get(option)
        attributes = self.set_attributes(ha_to_flair)
        await self.coordinator.client.update(
            "structures",
            self.structure_data.id,
            attributes=attributes,
            relationships={},
        )
        self.puck_data.attributes["temperature-scale"] = ha_to_flair
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @staticmethod
    def set_attributes(option: str) -> dict[str, str]:
        """Creates attributes dictionary."""
        return {"temperature-scale": option}

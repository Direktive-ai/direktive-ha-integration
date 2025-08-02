"""Sensor for Direktive.ai Directives."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    SENSOR_NAME,
    SENSOR_ATTRIBUTE_DIRECTIVES,
    SENSOR_ATTRIBUTE_LAST_UPDATE,
    SENSOR_ATTRIBUTE_ERROR,
    UPDATE_INTERVAL,
    UPDATE_INTERVAL_ERROR,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Direktive.ai Directives sensor."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    sensor = DirektiveSensor(coordinator, config_entry)
    hass.data[DOMAIN][config_entry.entry_id]["sensor"] = sensor
    # Force an update before adding the entity
    await sensor.async_update()
    async_add_entities([sensor], update_before_add=True)

class DirektiveSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Direktive.ai Directives sensor."""

    def __init__(
        self,
        coordinator: Any,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = SENSOR_NAME
        self._attr_unique_id = f"{config_entry.entry_id}_{SENSOR_NAME}"
        self._attr_native_value = 0
        self._attr_should_poll = True
        self._attr_available = True
        self._attr_icon = "mdi:script-text"
        self._attr_device_class = None
        self._attr_state_class = None
        self._post_restart = True
        self._conversations = {}  # Store conversations for each directive
        self._attr_extra_state_attributes = {
            SENSOR_ATTRIBUTE_DIRECTIVES: [],
            SENSOR_ATTRIBUTE_LAST_UPDATE: None,
            SENSOR_ATTRIBUTE_ERROR: None,
        }

    @property
    def state(self) -> str:
        """Return the state of the sensor."""
        # _LOGGER.debug("Sensor: Getting state")
        if not self.coordinator.data:
            # _LOGGER.debug("Sensor: No data available")
            return "unknown"
        # _LOGGER.debug("Sensor: Data available: %s", self.coordinator.data)
        return str(len(self.coordinator.data.get("directives", [])))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes of the sensor."""
        # _LOGGER.debug("Sensor: Getting extra state attributes")
        if not self.coordinator.data:
            # _LOGGER.debug("Sensor: No data available for attributes")
            return self._attr_extra_state_attributes
        # _LOGGER.debug("Sensor: Attributes data: %s", self.coordinator.data)
        
        current_attributes = self._attr_extra_state_attributes.copy()
        current_attributes["directives"] = self.coordinator.data.get("directives", [])
        
        return current_attributes

    async def async_update(self) -> None:
        """Update the sensor."""
        # _LOGGER.debug("Sensor: Starting async_update")
        # No need to request refresh here as the coordinator will handle that
        # _LOGGER.debug("Sensor: Finished async_update")
        try:
            # Get directives from coordinator
            directives = await self.coordinator.async_get_directives()
            
            # Update sensor state
            self._attr_extra_state_attributes[SENSOR_ATTRIBUTE_DIRECTIVES] = directives
            self._attr_extra_state_attributes[SENSOR_ATTRIBUTE_LAST_UPDATE] = datetime.now().isoformat()
            self._attr_extra_state_attributes[SENSOR_ATTRIBUTE_ERROR] = None
            self._attr_available = True
            
            # Reset post_restart flag after first update
            if self._post_restart:
                self._post_restart = False
            
        except Exception as err:
            _LOGGER.error("Error updating directives sensor: %s", err)
            self._attr_extra_state_attributes[SENSOR_ATTRIBUTE_ERROR] = str(err)
            self._attr_available = False            

    async def async_set_state(self, state: str | dict, value: str | None = None | bool):
        """Set the state of the sensor."""
        if isinstance(state, dict):
            self._attr_extra_state_attributes.update(state)
        else:
            self._attr_extra_state_attributes[state] = value
        self.async_write_ha_state()

    async def async_set_directive_state(self, directive_id: str, state: str | dict, value: str | None = None | bool):
        """Set the state of a directive."""
        directives = self._attr_extra_state_attributes.get("directives", [])
        directive_to_update = next((d for d in directives if d.get("id") == directive_id), None)

        if not directive_to_update:
            # _LOGGER.debug("Directive %s not found, adding it to state.", directive_id)
            directive_to_update = {"id": directive_id}
            directives.append(directive_to_update)
            self._attr_extra_state_attributes["directives"] = directives

        if isinstance(state, dict):
            directive_to_update.update(state)
        else:
            directive_to_update[state] = value
        self.async_write_ha_state()

    # async def async_create_directive(self, message: str) -> bool:
    #     """Create a new directive."""
    #     _LOGGER.debug("-- CREATING NEW DIRECTIVE: %s", message)
    #     try:
    #         await self.coordinator.async_create_directive(message)
    #         # Force an immediate update of the sensor
    #         await self.async_update()
    #         return True
    #     except Exception as err:
    #         _LOGGER.error("Error creating directive: %s", err)
    #         return False

    async def async_update_directive(self, directive_id: str, message: str) -> bool:
        """Update an existing directive."""
        try:
            await self.coordinator.async_update_directive(directive_id, message)
            await self.async_update()
            return True
        except Exception as err:
            _LOGGER.error("Error updating directive: %s", err)
            return False

    async def async_delete_directive(self, directive_id: str) -> bool:
        """Delete a directive."""
        try:
            await self.coordinator.async_delete_directive(directive_id)
            await self.async_update()
            return True
        except Exception as err:
            _LOGGER.error("Error deleting directive: %s", err)
            return False

    async def async_download_directive(self, directive_id: str, message: str) -> bool:
        """Download/Activate a directive."""
        # _LOGGER.debug("-- DOWNLOADING/ACTIVATING DIRECTIVE: %s", directive_id)
        try:
            await self.coordinator.async_update_directive(directive_id, message)
            # Force an immediate update of the sensor
            await self.async_update()
            return True
        except Exception as err:
            _LOGGER.error("Error downloading/activating directive: %s", err)
            return False

    async def async_get_conversation(self, directive_id: str) -> list[dict[str, Any]]:
        """Get conversation history for a directive."""
        try:
            if directive_id not in self._conversations:
                result = await self.coordinator.async_get_conversation(directive_id)
                if result.get("success"):
                    self._conversations[directive_id] = result.get("messages", [])
                    # Update state attributes to include conversations
                    self._attr_extra_state_attributes["conversations"] = self._conversations
                    self.async_write_ha_state()
            return self._conversations.get(directive_id, [])
        except Exception as err:
            _LOGGER.error("Error getting conversation: %s", err)
            return []

    async def async_send_conversation_message(self, directive_id: str, prompt: str) -> bool:
        """Send a message to the conversation for a directive."""
        try:
            result = await self.coordinator.async_send_conversation_message(directive_id, prompt)
            if result.get("success"):
                # Refresh conversation history after sending message
                await self.async_get_conversation(directive_id)
                return True
            return False
        except Exception as err:
            _LOGGER.error("Error sending conversation message: %s", err)
            return False 
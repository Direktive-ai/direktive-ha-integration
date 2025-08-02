"""Coordinator for Direktive.ai API communication."""
from __future__ import annotations

import logging
import aiohttp
import asyncio
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DOMAIN,
    API_URL,
    CONF_API_KEY,
    CONF_ENCRYPTION_KEY,
    API_ENDPOINT_DIRECTIVES,
    API_ENDPOINT_DIRECTIVE,
    UPDATE_INTERVAL,
    UPDATE_INTERVAL_ERROR,
)

_LOGGER = logging.getLogger(__name__)

class DirektiveCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the API."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: dict[str, Any],
    ) -> None:
        """Initialize the coordinator."""
        self.api_key = config_entry[CONF_API_KEY]
        self.encryption_key = config_entry.get(CONF_ENCRYPTION_KEY)
        self.session = None
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,
            update_method=self._async_update_data,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API endpoint."""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            headers = {
                "x-api-key": self.api_key,
            }
            if self.encryption_key:
                headers["x-encryption-key"] = self.encryption_key

            _LOGGER.debug("Coordinator: Making GET request to fetch directives")
            async with self.session.get(
                f"{API_URL.rstrip('/')}{API_ENDPOINT_DIRECTIVES}",
                headers=headers,
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    # _LOGGER.debug("Coordinator: Received data: %s", data)
                    return data
                else:
                    raise Exception(f"API returned status {response.status}")

        except Exception as err:
            _LOGGER.error("Coordinator: Error fetching data: %s", err)
            self.update_interval = None
            raise Exception(f"Error fetching data: {err}")

    async def async_get_directives(self) -> list[dict[str, Any]]:
        """Get all directives."""
        data = await self._async_update_data()
        return data.get("directives", [])
    
    async def async_poll_directive(self, directive_id: str) -> dict[str, Any] | None:
        """Poll a directive by ID."""  
        start_time = asyncio.get_running_loop().time()
        # entry_id = next(iter(self.hass.data[DOMAIN].keys()))
        # sensor = self.hass.data[DOMAIN][entry_id].get("sensor")

        while (asyncio.get_running_loop().time() - start_time) < 380:
            stage_info = await self.async_get_directive_stage(directive_id)
            stage = stage_info.get("stage")
            stage_message = stage_info.get("stage_message")
            message = stage_info.get("message")
            title = stage_info.get("title")
            status = stage_info.get("status")
            _LOGGER.debug(f"Polling directive {directive_id}, stage: {stage}")

            if stage == "completed":
                _LOGGER.debug("Directive completed stage for %s", directive_id)
                return await self.async_get_directive(directive_id)

            elif stage == "failed":
                _LOGGER.error("Directive failed stage for %s: %s", directive_id, stage_message)
                return await self.async_get_directive(directive_id)
            
            # Update coordinator's directive data with stage and stage_message
            if self.data and "directives" in self.data:
                original_directives = self.data["directives"]
                directive_found = False
                updated_directives = []

                for directive in original_directives:
                    if directive.get("id") == directive_id:
                        directive_found = True
                        updated_directive = directive.copy()
                        updated_directive["creation_stage"] = stage
                        updated_directive["creation_message"] = stage_message
                        updated_directive["status"] = status
                        updated_directives.append(updated_directive)
                    else:
                        updated_directives.append(directive)

                if not directive_found:
                    _LOGGER.debug("Directive %s not found during poll, adding to coordinator data.", directive_id)
                    new_directive = {
                        "id": directive_id,
                        "creation_stage": stage,
                        "creation_message": stage_message,
                        "message": message,
                        "title": title,
                        "status": "creating",
                        "discovery": False
                    }
                    updated_directives.append(new_directive)
                
                new_data = self.data.copy()
                new_data["directives"] = updated_directives
                self.async_set_updated_data(new_data)

            await asyncio.sleep(10) # Poll every 5 seconds
        else:
            # This block runs if the while loop finishes, i.e., it times out.
            _LOGGER.error(f"Directive creation for {directive_id} timed out after 5 minutes.")
            if self.data and "directives" in self.data:
                directives = list(self.data["directives"])
                directive_to_update = next((d for d in directives if d.get("id") == directive_id), None)
                if directive_to_update:
                    directive_to_update["creation_stage"] = "failed"
                    directive_to_update["creation_message"] = "Directive creation timed out after 3 minutes."
                    directive_to_update["status"] = "error"
                    
                    new_data = self.data.copy()
                    new_data["directives"] = directives
                    self.async_set_updated_data(new_data)

        return None
    
    async def async_get_directive(self, directive_id: str) -> dict[str, Any] | None:
        """Get a directive by ID."""
        try:
            _LOGGER.debug("GET directive with id: %s", directive_id)
            if not self.session:
                self.session = aiohttp.ClientSession()

            headers = {
                "x-api-key": self.api_key,
            }
            if self.encryption_key:
                headers["x-encryption-key"] = self.encryption_key

            async with self.session.get(
                f"{API_URL.rstrip('/')}{API_ENDPOINT_DIRECTIVE.format(directive_id=directive_id)}",
                headers=headers,
            ) as response:
                if response.status == 200:
                    api_response = await response.json()
                    # _LOGGER.debug("API response: %s", api_response)

                    directive_data = api_response.get("directive")
                    if not directive_data:
                        _LOGGER.error("API response for directive %s is missing 'directive' key.", directive_id)
                        return None

                    if self.data and "directives" in self.data:
                        directives = self.data["directives"]
                        
                        # Add wahtever messages are in the existing directive to the new directive
                        directive_data["messages"] = next((d.get("messages", []) for d in directives if d.get("id") == directive_id), [])

                        # Create a new list with the updated or added directive
                        updated_directives = [d for d in directives if d.get("id") != directive_id]
                        updated_directives.append(directive_data)
                        
                        # Create a new data object for the coordinator
                        new_data = self.data.copy()
                        new_data["directives"] = updated_directives
                        
                        # Update coordinator data and notify listeners
                        self.async_set_updated_data(new_data)
                    else:
                        # Fallback for when coordinator data isn't populated yet.
                        # This can happen if polling finishes before the first full update.
                        entry_id = next(iter(self.hass.data[DOMAIN].keys()))
                        sensor = self.hass.data[DOMAIN][entry_id].get("sensor")
                        if sensor:
                            _LOGGER.debug("Coordinator data not yet available, updating sensor directly.")
                            await sensor.async_set_directive_state(directive_id, directive_data)

                    return directive_data
                else:
                    error_text = await response.text()
                    raise Exception(f"API returned status {response.status}: {error_text}")

        except Exception as err:
            _LOGGER.error("Error getting directive: %s", err, exc_info=True)
            raise Exception(f"Error getting directive: {err}")

    async def async_create_directive(self, message: str) -> dict[str, Any]:
        """Create a new directive."""
        try:
            _LOGGER.debug("Creating directive with message: %s", message)
            if not self.session:
                self.session = aiohttp.ClientSession()

            headers = {
                "x-api-key": self.api_key,
            }
            if self.encryption_key:
                headers["x-encryption-key"] = self.encryption_key

            async with self.session.post(
                f"{API_URL.rstrip('/')}{API_ENDPOINT_DIRECTIVES}",
                headers=headers,
                json={"message": message},
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    # _LOGGER.debug("API response: %s", result)
                    self.hass.async_create_task(self.async_poll_directive(result.get("directive_id")))
                    # await self.async_request_refresh()
                    return result
                else:
                    error_text = await response.text()
                    raise Exception(f"API returned status {response.status}: {error_text}")

        except Exception as err:
            _LOGGER.error("Error creating directive: %s", err, exc_info=True)
            raise Exception(f"Error creating directive: {err}")

    async def async_update_directive(self, directive_id: str, message: str) -> dict[str, Any]:
        """Update an existing directive."""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            headers = {
                "x-api-key": self.api_key,
            }
            if self.encryption_key:
                headers["x-encryption-key"] = self.encryption_key

            async with self.session.put(
                f"{API_URL.rstrip('/')}{API_ENDPOINT_DIRECTIVE.format(directive_id=directive_id)}",
                headers=headers,
                json={"message": message},
            ) as response:
                if response.status == 200:
                    # _LOGGER.debug("Requesting coordinator refresh")
                    await self.async_request_refresh()
                    return await response.json()
                else:
                    await self.async_request_refresh()
                    raise Exception(f"API returned status {response.status}")

        except Exception as err:
            raise Exception(f"Error updating directive: {err}")

    async def async_delete_directive(self, directive_id: str) -> bool:
        """Delete a directive."""
        try:
            if self.data and "directives" in self.data:
                original_directives = self.data["directives"]
                updated_directives = []
                for directive in original_directives:
                    if directive.get("id") == directive_id:
                        updated_directive = directive.copy()
                        updated_directive["status"] = "deleting"
                        updated_directives.append(updated_directive)
                    else:
                        updated_directives.append(directive)

                new_data = self.data.copy()
                new_data["directives"] = updated_directives
                self.async_set_updated_data(new_data)

            if not self.session:
                self.session = aiohttp.ClientSession()

            headers = {
                "x-api-key": self.api_key,
            }
            if self.encryption_key:
                headers["x-encryption-key"] = self.encryption_key

            async with self.session.delete(
                f"{API_URL.rstrip('/')}{API_ENDPOINT_DIRECTIVE.format(directive_id=directive_id)}",
                headers=headers,
            ) as response:
                if response.status == 200:
                    await self.async_request_refresh()
                    return True
                else:
                    error_text = await response.text()
                    raise Exception(f"API returned status {response.status}: {error_text}")

        except Exception as err:
            _LOGGER.error("Error deleting directive: %s", err, exc_info=True)
            raise Exception(f"Error deleting directive: {err}")

    async def async_download_directive(self, directive_id: str) -> dict[str, Any]:
        """Activate a directive (mark as active)."""
        try:
            updated_directive = None
            if self.data and "directives" in self.data:
                original_directives = self.data["directives"]
                updated_directives = []
                for directive in original_directives:
                    if directive.get("id") == directive_id:
                        updated_directive = directive.copy()
                        updated_directive["status"] = "creating"
                        updated_directive["discovery"] = False
                        updated_directives.append(updated_directive)
                    else:
                        updated_directives.append(directive)

                new_data = self.data.copy()
                new_data["directives"] = updated_directives
                self.async_set_updated_data(new_data)

            if not updated_directive:
                raise Exception(f"Directive {directive_id} not found")

            if not self.session:
                self.session = aiohttp.ClientSession()

            headers = {
                "x-api-key": self.api_key,
            }
            if self.encryption_key:
                headers["x-encryption-key"] = self.encryption_key

            async with self.session.put(
                f"{API_URL.rstrip('/')}{API_ENDPOINT_DIRECTIVE.format(directive_id=directive_id)}",
                headers=headers,
                json={"message": updated_directive.get("message")},
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    self.hass.async_create_task(self.async_poll_directive(result.get("directive_id")))
                    # await self.async_request_refresh()
                    return True
                else:
                    error_text = await response.text()
                    raise Exception(f"API returned status {response.status}: {error_text}")

        except Exception as err:
            _LOGGER.error("Error activating directive: %s", err, exc_info=True)
            raise Exception(f"Error activating directive: {err}")

    async def async_get_directive_stage(self, directive_id: str) -> dict[str, Any]:
        """Get the creation stage of a directive."""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            headers = {
                "x-api-key": self.api_key,
            }
            if self.encryption_key:
                headers["x-encryption-key"] = self.encryption_key

            async with self.session.get(
                f"{API_URL.rstrip('/')}/directive/stage/{directive_id}",
                headers=headers,
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    _LOGGER.error("API error getting directive stage: %s", error_text)
                    raise Exception(f"API returned status {response.status}: {error_text}")

        except Exception as err:
            _LOGGER.error("Error getting directive stage: %s", err, exc_info=True)
            raise Exception(f"Error getting directive stage: {err}")

    async def async_close(self):
        """Close the session."""
        if self.session:
            await self.session.close()
            self.session = None

    async def async_get_conversation(self, directive_id: str) -> dict[str, Any]:
        """Get conversation history for a directive."""
        _LOGGER.debug(f"Getting conversation for directive {directive_id}")
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            headers = {
                "x-api-key": self.api_key,
            }
            if self.encryption_key:
                headers["x-encryption-key"] = self.encryption_key

            async with self.session.get(
                f"{API_URL.rstrip('/')}/conversation/{directive_id}",
                headers=headers,
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    messages = result.get("messages") or []

                    if self.data and "directives" in self.data and messages:
                        original_directives = self.data["directives"]
                        updated_directives = []

                        for directive in original_directives:
                            if directive.get("id") == directive_id:
                                updated_directive = directive.copy()
                                updated_directive["messages"] = messages
                                updated_directives.append(updated_directive)
                            else:
                                updated_directives.append(directive)

                        new_data = self.data.copy()
                        new_data["directives"] = updated_directives
                        self.async_set_updated_data(new_data)

                    return await response.json()
                else:
                    raise Exception(f"API returned status {response.status}")

        except Exception as err:
            raise Exception(f"Error getting conversation: {err}")

    async def async_send_conversation_message(self, directive_id: str, prompt: str) -> dict[str, Any]:
        """Send a message to the conversation for a directive."""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            headers = {
                "x-api-key": self.api_key,
            }
            if self.encryption_key:
                headers["x-encryption-key"] = self.encryption_key

            async with self.session.post(
                f"{API_URL.rstrip('/')}/conversation",
                headers=headers,
                json={"directive_id": directive_id, "prompt": prompt},
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    _LOGGER.debug("Conversation result: %s", result)
                    self.hass.async_create_task(self.async_get_conversation(directive_id))
                    if (result.get("pull")):
                        self.hass.async_create_task(self.async_poll_directive(directive_id))
                    return result
                else:
                    raise Exception(f"API returned status {response.status}")

        except Exception as err:
            raise Exception(f"Error sending conversation message: {err}")

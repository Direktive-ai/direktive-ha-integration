"""WebSocket API for Direktive.ai integration."""
from __future__ import annotations

import voluptuous as vol
import logging
import asyncio
from datetime import datetime

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the WebSocket API."""
    websocket_api.async_register_command(hass, handle_get_directives)
    websocket_api.async_register_command(hass, handle_create_directive)
    websocket_api.async_register_command(hass, handle_update_directive)
    websocket_api.async_register_command(hass, handle_delete_directive)
    websocket_api.async_register_command(hass, handle_download_directive)
    websocket_api.async_register_command(hass, handle_get_conversation)
    websocket_api.async_register_command(hass, handle_send_conversation_message)
    return True

@websocket_api.websocket_command(
    {
        vol.Required("type"): "direktive/get_directives",
    }
)
@websocket_api.async_response
async def handle_get_directives(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Handle get directives command."""
    try:
        # Get the first entry ID since we only support one instance
        entry_id = next(iter(hass.data[DOMAIN].keys()))
        coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
        directives = await coordinator.async_get_directives()
        connection.send_result(msg["id"], {"success": True, "directives": directives})
    except Exception as err:
        _LOGGER.error("Error getting directives: %s", err)
        connection.send_error(msg["id"], str(err))

@websocket_api.websocket_command(
    {
        vol.Required("type"): "direktive/create_directive",
        vol.Required("message"): str,
    }
)
@websocket_api.async_response
async def handle_create_directive(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Handle create directive command."""
    entry_id = next(iter(hass.data[DOMAIN].keys()))
    sensor = hass.data[DOMAIN][entry_id].get("sensor")

    try:
        
        # _LOGGER.debug("Creating directive with message: %s", msg["message"])
        coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
        
        initial_result = await coordinator.async_create_directive(msg["message"])
        # _LOGGER.debug("Directive creation initiated: %s", initial_result)
        
        directive_id = initial_result.get("directive_id")
        connection.send_result(msg["id"], {
            "success": True,
            "directive_id": directive_id
        })
        
        if not directive_id:
            raise Exception("Directive creation failed to return a directive ID.")

    except Exception as err:
        _LOGGER.error("Error creating directive: %s", err, exc_info=True)
        if sensor:
            await sensor.async_set_state({
                "creating": False,
                "error": str(err)
            })
        connection.send_error(msg["id"], "unknown_error", str(err))

@websocket_api.websocket_command(
    {
        vol.Required("type"): "direktive/update_directive",
        vol.Required("directive_id"): str,
        vol.Required("message"): str,
    }
)
@websocket_api.async_response
async def handle_update_directive(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Handle update directive command."""
    entry_id = next(iter(hass.data[DOMAIN].keys()))
    sensor = hass.data[DOMAIN][entry_id].get("sensor")

    try:
        if sensor:
            await sensor.async_set_state({
                "creating": True,
                "creation_stage": None,
                "creation_message": None,
                "error": None,
                "deleting": False,
                "downloading": False
            })
        # Get the first entry ID since we only support one instance
        coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
        result = await coordinator.async_update_directive(msg["directive_id"], msg["message"])
        if sensor:
            await sensor.async_set_state("creating", False)
        connection.send_result(msg["id"], {"success": True, "result": result})
    except Exception as err:
        _LOGGER.error("Error updating directive: %s", err)
        if sensor:
            await sensor.async_set_state({
                "creating": False,
                "error": str(err)
            })
        connection.send_error(msg["id"], str(err))

@websocket_api.websocket_command(
    {
        vol.Required("type"): "direktive/delete_directive",
        vol.Required("directive_id"): str,
    }
)
@websocket_api.async_response
async def handle_delete_directive(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Handle delete directive command."""
    entry_id = next(iter(hass.data[DOMAIN].keys()))
    sensor = hass.data[DOMAIN][entry_id].get("sensor")
    try:
        # if sensor:
        #     await sensor.async_set_state({
        #         "deleting": True,
        #         "error": None,
        #         "creating": False,
        #         "creation_stage": None,
        #         "creation_message": None,
        #         "downloading": False
        #     })
        # Get the first entry ID since we only support one instance
        coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
        await coordinator.async_delete_directive(msg["directive_id"])
        connection.send_result(msg["id"], {"success": True})
    except Exception as err:
        _LOGGER.error("Error deleting directive: %s", err)
        if sensor:
            await sensor.async_set_state({
                "deleting": False,
                "error": str(err)
            })
        connection.send_error(msg["id"], str(err))

@websocket_api.websocket_command(
    {
        vol.Required("type"): "direktive/download_directive",
        vol.Required("directive_id"): str,
    }
)
@websocket_api.async_response
async def handle_download_directive(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Handle download/activate directive command."""
    entry_id = next(iter(hass.data[DOMAIN].keys()))
    # sensor = hass.data[DOMAIN][entry_id].get("sensor")
    try:
        # _LOGGER.debug("Downloading/activating directive with ID: %s%s", msg["directive_id"], msg["message"])
        # if sensor:
        #     await sensor.async_set_state({
        #         "downloading": msg["directive_id"],
        #         "error": None,
        #         "creating": False,
        #         "creation_stage": None,
        #         "creation_message": None,
        #         "deleting": False
        #     })
        
        coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
        result = await coordinator.async_download_directive(msg["directive_id"])
        _LOGGER.debug("Directive download/activation result: %s", result)
        
        # Get updated directives after download/activation
        updated_directives = await coordinator.async_get_directives()
        
        # if sensor:
        #     await sensor.async_set_state("downloading", False)
            
        connection.send_result(msg["id"], {
            "success": True, 
            "directives": updated_directives
        })
    except Exception as err:
        _LOGGER.error("Error downloading/activating directive: %s", err)
        # if sensor:
        #     await sensor.async_set_state({
        #         "success": False,
        #         "error": "download_failed: " + str(err)
        #     })
        connection.send_error(msg["id"], "download_failed", str(err))

@websocket_api.websocket_command(
    {
        vol.Required("type"): "direktive/get_conversation",
        vol.Required("directive_id"): str,
    }
)
@websocket_api.async_response
async def handle_get_conversation(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Handle get conversation history command."""
    try:
        _LOGGER.debug("Getting conversation history for directive: %s", msg["directive_id"])
        entry_id = next(iter(hass.data[DOMAIN].keys()))
        coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
        response = await coordinator.async_get_conversation(msg["directive_id"])
        
        # Extract messages from the response if it's nested
        messages = response.get("messages", []) if isinstance(response, dict) else response
        
        connection.send_result(msg["id"], {
            "success": True,
            "messages": messages  # Send messages directly without nesting
        })
    except Exception as err:
        _LOGGER.error("Error getting conversation history: %s", err)
        connection.send_error(msg["id"], str(err))

@websocket_api.websocket_command(
    {
        vol.Required("type"): "direktive/send_conversation_message",
        vol.Required("directive_id"): str,
        vol.Required("prompt"): str,
    }
)
@websocket_api.async_response
async def handle_send_conversation_message(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Handle send conversation message command."""
    try:
        entry_id = next(iter(hass.data[DOMAIN].keys()))
        coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
        await coordinator.async_send_conversation_message(msg["directive_id"], msg["prompt"])            

        connection.send_result(msg["id"], {
            "success": True
        })
    except Exception as err:
        _LOGGER.error("Error sending conversation message: %s", err)
        connection.send_error(msg["id"], str(err)) 
"""The Home Assistant Direktive.ai integration."""
import asyncio
import logging
import json
from datetime import timedelta
import pprint

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EVENT_STATE_CHANGED,
    MATCH_ALL,
    Platform,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import homeassistant.components.mqtt as mqtt

from .const import (
    DOMAIN, 
    API_URL,
    CONF_ENTITIES, 
    CONF_API_KEY,
    CONF_SUBSCRIPTION_TYPE,
    CONF_ENCRYPTION_KEY,
    SUBSCRIPTION_TYPE_PRO,
    MQTT_SCENARIO_TRIGGER_TOPIC,
    CONF_WEBHOOK_SECRET,
    CONF_WEBHOOK_REGISTERED_TO_API,
    CONF_HA_BASE_URL,
    CONF_INITIAL_BULK_UPDATE_PERFORMED,
)
from .encryption import encrypt_data, should_encrypt, decrypt_data
from .coordinator import DirektiveCoordinator
from .sensor import async_setup_entry as async_setup_sensor
from .websocket import async_setup as async_setup_websocket
from .webhook import async_register_integration_webhook, async_unregister_integration_webhook


EXPOSED_ENTITIES_UPDATED_EVENT = "exposed_entities_updated"
_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    config = entry.data
    api_key = config[CONF_API_KEY]
    entity_ids = config.get(CONF_ENTITIES, [])
    subscription_type = config.get(CONF_SUBSCRIPTION_TYPE, "basic")
    encryption_key = config.get(CONF_ENCRYPTION_KEY)
    
    # Set up coordinator
    coordinator = DirektiveCoordinator(hass, config)
    await coordinator.async_config_entry_first_refresh()
    
    # Set up platforms
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
    }
    
    # Set up WebSocket API with the entry ID
    await async_setup_websocket(hass, {"entry_id": entry.entry_id})
    
    # Register the webhook
    # The webhook_id used by HA will be the entry.entry_id for uniqueness.
    # We also pass entry.entry_id as config_entry_id for our handler to use.
    await async_register_integration_webhook(hass, entry.entry_id, entry.entry_id)

    # ---- BEGIN: Register Webhook with External Direktive.ai API (Once) ----
    if not entry.data.get(CONF_WEBHOOK_REGISTERED_TO_API):
        try:
            webhook_secret = entry.data.get(CONF_WEBHOOK_SECRET)
            current_api_key = entry.data.get(CONF_API_KEY)
            ha_instance_url_from_config = entry.data.get(CONF_HA_BASE_URL) # Get from config entry

            if webhook_secret and current_api_key:
                # Prioritize the user-configured HA base URL
                ha_instance_url = ha_instance_url_from_config
                if not ha_instance_url:
                    # Fallback to auto-detection if not configured (should ideally be configured via flow)
                    ha_instance_url = hass.config.external_url or hass.config.internal_url
                    if not ha_instance_url:
                        _LOGGER.warning(
                            "Home Assistant base URL not configured and could not be auto-detected. "
                            "Cannot provide full webhook URL to Direktive.ai API. "
                            "Your API will need to know how to construct it using the webhook_ha_id: /api/webhook/{webhook_ha_id}"
                        )
                
                registration_url = f"{API_URL.rstrip('/')}/register-ha-webhook"

                # Get Home Assistant's location (country and user-defined location name) and timezone.
                # Note: 'city' is not directly available, so we use 'location_name'.
                ha_country = getattr(hass.config, 'country', None)
                ha_timezone = hass.config.time_zone
                ha_location = hass.config.location_name

                payload_to_your_api = {
                    "webhook_ha_id": entry.entry_id,
                    "webhook_secret": webhook_secret,
                    "ha_base_url": ha_instance_url,
                    "ha_country": ha_country,
                    "ha_timezone": ha_timezone,
                    "ha_location": ha_location,
                }

                headers_for_your_api = {
                    "x-api-key": current_api_key,
                    "x-encryption-key": encryption_key,
                    "Content-Type": "application/json",
                }
                _LOGGER.info(f"Attempting to register HA webhook details with Direktive.ai API at {registration_url}")
                
                async with aiohttp.ClientSession() as http_session:
                    async with http_session.post(
                        registration_url,
                        json=payload_to_your_api,
                        headers=headers_for_your_api
                    ) as response:
                        if 200 <= response.status < 300:
                            _LOGGER.info(f"Successfully registered HA webhook details with Direktive.ai API. Status: {response.status}")
                            new_data = {**entry.data, CONF_WEBHOOK_REGISTERED_TO_API: True}
                            hass.config_entries.async_update_entry(entry, data=new_data)
                        else:
                            response_text = await response.text()
                            _LOGGER.error(
                                f"Failed to register HA webhook with Direktive.ai API. Status: {response.status}, Response: {response_text}. "
                                f"Please ensure your Direktive.ai service is configured with this HA instance's webhook details (ID: {entry.entry_id}, Secret: OMITTED_FOR_LOG) manually if necessary."
                            )
            else:
                missing_data = []
                if not webhook_secret: missing_data.append("webhook_secret")
                if not current_api_key: missing_data.append("API key")
                _LOGGER.warning(f"Skipping HA webhook registration with Direktive.ai API due to missing data: {', '.join(missing_data)}.")

        except Exception as e_reg:
            _LOGGER.error(f"Error occurred while trying to register HA webhook with Direktive.ai API: {e_reg}", exc_info=True)
    else:
        _LOGGER.info("HA Webhook details already registered with Direktive.ai API, skipping.")

    # Set up sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR])
    
    # Set up Direktive.ai
    direktive = Direktive(
        hass, 
        api_key, 
        entity_ids,
        subscription_type,
        encryption_key,
        entry.entry_id
    )
    
    # Add Direktive.ai to hass data
    hass.data[DOMAIN][entry.entry_id]["direktive"] = direktive
    
    # Start monitoring
    await direktive.async_start()

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    direktive = data["direktive"]
    coordinator = data["coordinator"]
    
    # Close coordinator session
    await coordinator.async_close()
    
    # Stop Direktive.ai
    await direktive.async_stop()
    
    # Unregister the webhook
    await async_unregister_integration_webhook(hass, entry.entry_id)
    
    # Unload platforms
    await hass.config_entries.async_unload_platforms(entry, [Platform.SENSOR])
    
    hass.data[DOMAIN].pop(entry.entry_id)
    
    return True

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Reload a config entry."""
    # First unload the entry
    await async_unload_entry(hass, entry)
    # Then set it up again
    return await async_setup_entry(hass, entry)

class Direktive:
    """Class to manage Direktive.ai of entity states."""

    def __init__(
        self, 
        hass: HomeAssistant, 
        api_key: str, 
        entity_ids: list,
        subscription_type: str = "basic",
        encryption_key: str = None,
        entry_id: str = None
    ):
        """Initialize the sync class."""
        self.hass = hass
        self.api_key = api_key
        self.entity_ids = set(entity_ids)
        self.entity_ids.add("sun.sun")
        self.session = None
        self._cleanup_callbacks = []
        self._headers = {"x-api-key": api_key, "x-encryption-key": encryption_key}
        self._subscription_type = subscription_type
        self._encryption_key = encryption_key
        self._entry_id = entry_id
        self._mqtt_unsubscribe_scenario_trigger = None

        if encryption_key:
            self._headers["x-encryption-key"] = encryption_key

    @callback
    async def _async_handle_mqtt_scenario_trigger(self, msg: mqtt.models.ReceiveMessage):
        """Handle incoming MQTT messages for scenario triggers."""
        _LOGGER.debug(f"Received scenario trigger on MQTT topic {msg.topic} with payload: {msg.payload}")
        try:
            # Assuming payload is a JSON string of the scenarios list
            scenarios = json.loads(msg.payload)
            if isinstance(scenarios, list) and scenarios:
                await self._handle_triggered_scenarios(scenarios) 
            elif scenarios:
                _LOGGER.warning(f"Received MQTT scenario trigger, but payload was not a list or was empty: {scenarios}")
            else:
                _LOGGER.debug(f"Received empty or null scenario list from MQTT: {scenarios}")

        except json.JSONDecodeError:
            _LOGGER.error(f"Failed to decode JSON from MQTT scenario trigger: {msg.payload}")
        except Exception as e:
            _LOGGER.error(f"Error handling MQTT scenario trigger: {e}", exc_info=True)

    async def async_start(self):
        """Start monitoring entity changes."""
        # Clean up any existing callbacks
        await self.async_stop()
        
        self.session = aiohttp.ClientSession()
        
        # Send initial bulk update of all entity states
        await self._send_bulk_update()
        
        # Set up state change listener for configured entities
        if self.entity_ids:
            _LOGGER.debug("Setting up state change listener for: %s", self.entity_ids)
            self._cleanup_callbacks.append(
                async_track_state_change(
                    self.hass,
                    list(self.entity_ids),
                    self._handle_state_change
                )
            )
        else:
            _LOGGER.warning("No entities configured to track for state changes!")

        # Subscribe to MQTT topic for scenario triggers from the addon
        try:
            self._mqtt_unsubscribe_scenario_trigger = await mqtt.async_subscribe(
                self.hass,
                MQTT_SCENARIO_TRIGGER_TOPIC,
                self._async_handle_mqtt_scenario_trigger,
                qos=1,
                encoding='utf-8'
            )
            _LOGGER.info(f"Successfully subscribed to MQTT topic: {MQTT_SCENARIO_TRIGGER_TOPIC}")
        except Exception as e_mqtt_sub:
            _LOGGER.error(f"Failed to subscribe to MQTT topic {MQTT_SCENARIO_TRIGGER_TOPIC}: {e_mqtt_sub}", exc_info=True)

    async def _send_bulk_update(self):
        """Send bulk update of all entity states.
        This initial bulk update will only run once per integration installation.
        """
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if not entry:
            _LOGGER.error(
                f"Cannot perform initial bulk update: Config entry {self._entry_id} not found."
            )
            return

        if entry.data.get(CONF_INITIAL_BULK_UPDATE_PERFORMED, False):
            _LOGGER.info(
                "Initial bulk update already performed for this integration instance (via __init__ call). Skipping."
            )
            return

        try:
            _LOGGER.info(f"__init__: Performing initial bulk update of all entity states (once per setup).")
            entities_data = []
            for entity_id in self.entity_ids:
                state = self.hass.states.get(entity_id)
                if state:
                    # Only send essential attributes
                    safe_attributes = {
                        k: v for k, v in state.attributes.items()
                        if k in [
                            "brightness", "color_temp", "rgb_color", "xy_color",
                            "current_position", "current_temperature", "temperature",
                            "hvac_mode", "preset_mode"
                        ]
                    }
                    
                    entity_data = {
                        "entity_id": entity_id,
                        "state": state.state,
                        "attributes": safe_attributes
                    }
                    
                    entities_data.append(entity_data)
            
            if entities_data:
                if should_encrypt(self._subscription_type):
                    entities_data = encrypt_data(entities_data, self._encryption_key)

            payload = {
                "entities": {"data": entities_data, "encrypted": should_encrypt(self._subscription_type)},
                "bulk": True,
                "refresh": True
            }

            if entities_data:
                async with self.session.post(
                    f"{API_URL.rstrip('/')}/update-entity-state",
                    json=payload,
                    headers=self._headers
                ) as response:
                    if response.status != 200:
                        _LOGGER.error(
                            "Failed to send initial bulk update: %s",
                            await response.text()
                        )
                        # Do NOT set the flag if the update failed
                        return

                    response_data = await response.json()
                    
                    # If the bulk update was successful, set the flag
                    new_data = {**entry.data, CONF_INITIAL_BULK_UPDATE_PERFORMED: True}
                    self.hass.config_entries.async_update_entry(entry, data=new_data)
                    _LOGGER.info("Initial bulk update successful and marked as performed.")

                    # Get the coordinator instance to refresh it
                    coordinator_instance = self.hass.data[DOMAIN][self._entry_id].get("coordinator")
                    if coordinator_instance:
                        _LOGGER.debug("Requesting coordinator refresh after initial entity sync in _send_bulk_update.")
                        await coordinator_instance.async_request_refresh()
                    else:
                        _LOGGER.error("Coordinator instance not found in _send_bulk_update, cannot refresh.")

                    # Handle any triggered scenarios
                    if "triggered_scenarios" in response_data:
                        await self._handle_triggered_scenarios(response_data["triggered_scenarios"])

        except Exception as err:
            _LOGGER.error("Error sending initial bulk update: %s", str(err), exc_info=True)
            # Do NOT set the flag if an exception occurred during the update process

    async def async_stop(self):
        """Stop monitoring."""
        for cleanup_callback in self._cleanup_callbacks:
            cleanup_callback()
        self._cleanup_callbacks = []
        
        if self.session:
            await self.session.close()
            self.session = None
        
        # Unsubscribe from MQTT topic if subscribed
        if self._mqtt_unsubscribe_scenario_trigger:
            _LOGGER.debug(f"Unsubscribing from MQTT topic: {MQTT_SCENARIO_TRIGGER_TOPIC}")
            try:
                self._mqtt_unsubscribe_scenario_trigger()
                self._mqtt_unsubscribe_scenario_trigger = None
            except Exception as e_mqtt_unsub:
                _LOGGER.error(f"Error unsubscribing from MQTT topic {MQTT_SCENARIO_TRIGGER_TOPIC}: {e_mqtt_unsub}")

    async def _handle_state_change(self, entity_id, from_state, to_state):
        """Handle state changes for monitored entities."""
        if entity_id not in self.entity_ids or to_state is None:
            return
            
        await self._async_update_remote_state(entity_id, to_state)

    async def _async_update_remote_state(self, entity_id, state):
        """Update remote state and handle response."""
        _LOGGER.debug("--- Updating remote state for %s: %s", entity_id, state)
        try:
            # Prepare payload
            # Only send essential attributes
            ALLOWED_KEYS = {
                "brightness", "color_temp", "rgb_color", "xy_color",
                "current_position", "current_temperature", "temperature",
                "hvac_mode", "preset_mode"
            }

            safe_attributes = {
                str(k): v for k, v in state.attributes.items()
                if k in ALLOWED_KEYS and k is not None
            }
            
            entities_data = [{
                "entity_id": entity_id,
                "state": state.state,
                "attributes": safe_attributes
            }]

            # Encrypt data for pro users
            if should_encrypt(self._subscription_type):
                entities_data = encrypt_data(entities_data, self._encryption_key)

            payload = {
                "entities": {"data": entities_data, "encrypted": False},
            }
            # Send update to remote server
            async with self.session.post(
                f"{API_URL.rstrip('/')}/update-entity-state",
                json=payload,
                headers=self._headers
            ) as response:
                if response.status != 200:
                    _LOGGER.error(
                        "Failed to update remote state for %s: %s",
                        entity_id,
                        await response.text()
                    )
                    return

                response_data = await response.json()
                
                # Handle triggered scenarios
                if "triggered_scenarios" in response_data:
                    _LOGGER.debug("--- Triggered scenarios debug: %s", pprint.pformat(response_data["triggered_scenarios"]))
                    await self._handle_triggered_scenarios(response_data["triggered_scenarios"])

        except Exception as err:
            _LOGGER.error(
                "Error updating remote state for %s: %s",
                entity_id,
                str(err)
            )

    async def _handle_triggered_scenarios(self, scenarios):
        """Handle triggered scenarios from the remote server."""

        if should_encrypt(self._subscription_type):
            scenarios = decrypt_data(scenarios, self._encryption_key)

        for scenario in scenarios:
            _LOGGER.debug("Processing scenario: %s", scenario.get("scenario_name"))
            
            for outcome in scenario["outcomes"]:
                try:
                    entity_id = outcome.get("entity_id")
                    new_state = outcome.get("state")
                    attributes = outcome.get("attributes", {})

                    if not entity_id or new_state is None:
                        _LOGGER.warning("Invalid outcome data: missing entity_id or state")
                        continue

                    # Determine domain and service based on entity type
                    domain = entity_id.split('.')[0]
                    service_data = {"entity_id": entity_id}

                    # Handle different entity types
                    if domain == "light":
                        if new_state == "on":
                            service = "turn_on"
                            # Add light-specific attributes
                            if "brightness" in attributes:
                                service_data["brightness"] = attributes["brightness"]
                            if "color_temp" in attributes:
                                service_data["color_temp"] = attributes["color_temp"]
                            if "rgb_color" in attributes:
                                service_data["rgb_color"] = attributes["rgb_color"]
                            if "xy_color" in attributes:
                                service_data["xy_color"] = attributes["xy_color"]
                        else:
                            service = "turn_off"

                    elif domain == "switch":
                        service = "turn_on" if new_state == "on" else "turn_off"

                    elif domain == "alarm_control_panel":
                        if new_state in ["armed_home", "armed_away", "armed_night", "disarmed"]:
                            service = new_state
                            # Some alarm panels might need a code
                            if "code" in attributes:
                                service_data["code"] = attributes["code"]

                    elif domain == "cover":
                        if new_state == "open":
                            service = "open_cover"
                        elif new_state == "closed":
                            service = "close_cover"
                        elif new_state == "stop":
                            service = "stop_cover"
                        # Handle position if available
                        if "position" in attributes:
                            service = "set_cover_position"
                            service_data["position"] = attributes["position"]

                    elif domain == "climate":
                        if new_state in ["heat", "cool", "auto", "off"]:
                            service = "set_hvac_mode"
                            service_data["hvac_mode"] = new_state
                        # Handle temperature settings
                        if "temperature" in attributes:
                            await self.hass.services.async_call(
                                domain,
                                "set_temperature",
                                {"entity_id": entity_id, "temperature": attributes["temperature"]},
                                blocking=True
                            )

                    elif domain == "number":
                        service = "set_value"
                        service_data["value"] = new_state

                    else:
                        # Generic handling for other domains
                        service = "turn_on" if new_state == "on" else "turn_off"

                    _LOGGER.debug(
                        "Calling service %s.%s with data: %s",
                        domain,
                        service,
                        service_data
                    )

                    # Call the service
                    await self.hass.services.async_call(
                        domain,
                        service,
                        service_data,
                        blocking=True
                    )

                    _LOGGER.info(
                        "Successfully updated %s to state: %s with attributes: %s",
                        entity_id,
                        new_state,
                        attributes
                    )

                except Exception as err:
                    _LOGGER.error(
                        "Error executing scenario outcome for entity %s: %s",
                        outcome.get("entity_id"),
                        str(err),
                        exc_info=True
                    )
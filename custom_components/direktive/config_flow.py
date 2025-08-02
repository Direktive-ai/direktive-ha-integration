"""Config flow for Direktive.ai integration."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
import logging
from homeassistant.helpers.selector import (
    EntitySelector,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
import aiohttp
import secrets

from .const import (
    DOMAIN, 
    API_URL,
    CONF_ENTITIES, 
    CONF_API_KEY, 
    CONF_ENCRYPTION_KEY,
    CONF_SUBSCRIPTION_TYPE,
    SUBSCRIPTION_TYPE_BASIC,
    SUBSCRIPTION_TYPE_PRO,
    CONF_WEBHOOK_SECRET,
    CONF_HA_BASE_URL,
)
from .encryption import generate_encryption_key, encrypt_data, should_encrypt

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)

SUPPORTED_DOMAINS = {
    "light", "switch", "cover", "number", "sensor", "binary_sensor"
}

class DirektiveConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Direktive.ai."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self._selected_entities = set()
        self._api_key = None
        self._subscription_type = None
        self._encryption_key = None
        self._webhook_secret = None
        self._ha_base_url = None

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            try:
                if CONF_API_KEY in user_input:
                    
                    # Test connection to API endpoint with API key
                    try:
                        # User has provided API endpoint, key, and potentially HA Base URL
                        self._api_key = user_input[CONF_API_KEY]
                        self._ha_base_url = user_input.get(CONF_HA_BASE_URL) # Get HA base URL from input

                        # If HA base URL is not provided or empty, try to auto-detect
                        if not self._ha_base_url:
                            self._ha_base_url = self.hass.config.external_url or self.hass.config.internal_url
                            if not self._ha_base_url: # If still not found, it will be an issue for API registration but proceed for now
                                    _LOGGER.warning("HA Base URL could not be auto-detected and was not provided.")
                                    # We could make it strictly required by raising an error or adding to errors dict if critical now

                        async with aiohttp.ClientSession() as session:
                            headers = {"x-api-key": self._api_key}
                            async with session.get(
                                f"{API_URL.rstrip('/')}/health",
                                headers=headers
                            ) as response:
                                if response.status != 200:
                                    errors["base"] = "cannot_connect"
                                    _LOGGER.error(
                                        "Failed to connect to API endpoint: %s, status: %s",
                                        API_URL,
                                        response.status
                                    )
                                else:
                                    # Check response content
                                    response_data = await response.json()
                                    if response_data.get('status') != 'healthy':
                                        errors["base"] = "unhealthy_service"
                                        _LOGGER.error(
                                            "Service is unhealthy: %s",
                                            response_data.get('error', 'Unknown error')
                                        )
                                    else:
                                        # Get subscription type
                                        async with session.get(
                                            f"{API_URL.rstrip('/')}/subscription",
                                            headers=headers
                                        ) as sub_response:
                                            if sub_response.status == 200:
                                                sub_data = await sub_response.json()
                                                self._subscription_type = sub_data.get('plan', SUBSCRIPTION_TYPE_BASIC)
                                                self._encryption_key = generate_encryption_key()
                                                self._webhook_secret = secrets.token_hex(32)
                                                
                                                return await self.async_step_entity_select()
                                            else:
                                                _LOGGER.error("Failed to get subscription info, status: %s", sub_response.status)
                                                errors["base"] = "no_subscription_type"
                    except aiohttp.ClientError as err:
                        errors["base"] = "cannot_connect"
                        _LOGGER.error("Connection error: %s", str(err))
            except Exception as err:
                errors["base"] = "unknown"
                _LOGGER.exception("Unexpected error in config flow: %s", str(err))

        # Schema for the user form
        # Try to get default for ha_base_url
        default_ha_url = self.hass.config.external_url or self.hass.config.internal_url or ""

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_API_KEY): str,
                vol.Optional(CONF_HA_BASE_URL, default=default_ha_url): str, # Add HA Base URL field, suggest if possible
            }),
            errors=errors,
        )

    async def async_step_entity_select(self, user_input=None):
        """Handle entity selection."""
        errors = {}

        if user_input is not None:
            try:
                if "entities" in user_input:
                    self._selected_entities = set(user_input["entities"])
                    
                    # Prepare config data
                    config_data = {
                        CONF_API_KEY: self._api_key,
                        CONF_ENTITIES: list(self._selected_entities),
                        CONF_SUBSCRIPTION_TYPE: self._subscription_type,
                        CONF_WEBHOOK_SECRET: self._webhook_secret,
                        CONF_HA_BASE_URL: self._ha_base_url,
                        CONF_ENCRYPTION_KEY: self._encryption_key
                    }
                    _LOGGER.debug("Config data: %s", config_data)
                    
                    return self.async_create_entry(
                        title="Direktive.ai",
                        data=config_data
                    )
            except Exception as err:
                errors["base"] = "unknown"
                _LOGGER.exception("Error in entity selection: %s", str(err))

        # Get available entities from supported domains
        entity_registry = er.async_get(self.hass)
        
        if not self._subscription_type:
            return self.async_show_form(
                step_id="entity_select",
                data_schema=vol.Schema({}),
                description_placeholders={"subscription_info": "Could not retrieve subscription details. Please go back and try again."},
                errors={"base": "no_subscription_type"}
            )

        schema = {
            vol.Optional(
                "entities", 
                default=list(self._selected_entities)
            ): EntitySelector({
                "include_entities": [
                    entity.entity_id for entity in entity_registry.entities.values()
                    if entity.domain in SUPPORTED_DOMAINS
                ],
                "multiple": True
            })
        }

        # Create description with subscription info if needed
        description = None
        if self._subscription_type == SUBSCRIPTION_TYPE_PRO:
            description = f"Subscritpion: Pro Plan - Encryption key: {self._encryption_key}"
        else:
            description = f"Subscritpion: Basic Plan - Encryption key: {self._encryption_key}"

        return self.async_show_form(
            step_id="entity_select",
            data_schema=vol.Schema(schema),
            description_placeholders={"subscription_info": description},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry
        self._selected_entities = set(config_entry.data.get(CONF_ENTITIES, []))
        self._subscription_type = config_entry.data.get(CONF_SUBSCRIPTION_TYPE, SUBSCRIPTION_TYPE_BASIC)
        self._encryption_key = config_entry.data.get(CONF_ENCRYPTION_KEY)
        self._webhook_secret = config_entry.data.get(CONF_WEBHOOK_SECRET)
        self._ha_base_url = config_entry.data.get(CONF_HA_BASE_URL)

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        errors = {}

        if user_input is not None:
            try:
                _LOGGER.info(f"config_flow: Sending bulk update of all entity states")
                # Get the current entities from the config entry
                current_entities = set(self.config_entry.data.get(CONF_ENTITIES, []))
                new_entities = set(user_input.get("entities", []))
                
                # Only proceed if entities have changed
                if current_entities != new_entities:
                    api_key = self.config_entry.data.get(CONF_API_KEY)
                    
                    # Prepare the bulk update payload
                    entities_data = []
                    for entity_id in new_entities:
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
                        else:
                            entity_data = {
                                "entity_id": entity_id,
                                "state": "unknown",
                                "attributes": {}
                            }
                        
                        entities_data.append(entity_data)
                    
                    # Encrypt data for pro users
                    if should_encrypt(self._subscription_type):
                        _LOGGER.debug("--- ENCRYPTING payload: %s", entities_data)
                        entities_data = encrypt_data(entities_data, self._encryption_key)
                    
                    payload = {
                        "entities": {"data": entities_data, "encrypted": should_encrypt(self._subscription_type)},
                        "bulk": True,
                        "refresh": False
                    }
                    
                    # Send bulk update request
                    try:
                        async with aiohttp.ClientSession() as session:
                            headers = {"x-api-key": api_key, "x-encryption-key": self._encryption_key}
                                
                            async with session.post(
                                f"{API_URL.rstrip('/')}/update-entity-state",
                                headers=headers,
                                json=payload
                            ) as response:
                                if response.status != 200:
                                    errors["base"] = "api_error"
                                    _LOGGER.error(
                                        "Failed to update entities: %s, status: %s",
                                        await response.text(),
                                        response.status
                                    )
                                else:
                                    # Update was successful, save the new entities
                                    self._selected_entities = new_entities
                                    
                                    # Get the coordinator instance to refresh it
                                    coordinator_instance = self.hass.data[DOMAIN][self.config_entry.entry_id].get("coordinator")
                                    
                                    if coordinator_instance:
                                        # Explicitly refresh coordinator data after entity update in options flow
                                        _LOGGER.debug("Requesting coordinator refresh after entity update in options flow.")
                                        await coordinator_instance.async_request_refresh()
                                    else:
                                        _LOGGER.error("Coordinator not found in options flow, cannot refresh.")
                                    
                                    # Update the config entry data
                                    new_data = dict(self.config_entry.data)
                                    new_data[CONF_ENTITIES] = list(self._selected_entities)
                                    new_data[CONF_SUBSCRIPTION_TYPE] = self._subscription_type
                                    if self._encryption_key:
                                        new_data[CONF_ENCRYPTION_KEY] = self._encryption_key
                                    if self._webhook_secret:
                                        new_data[CONF_WEBHOOK_SECRET] = self._webhook_secret
                                    if self._ha_base_url: # Save HA base URL
                                        new_data[CONF_HA_BASE_URL] = self._ha_base_url
                                    
                                    self.hass.config_entries.async_update_entry(
                                        self.config_entry,
                                        data=new_data
                                    )
                                    
                                    # Reload the config entry to update entity tracking
                                    await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                                    
                                    return self.async_create_entry(
                                        title="",
                                        data={
                                            CONF_ENTITIES: list(self._selected_entities),
                                            CONF_SUBSCRIPTION_TYPE: self._subscription_type,
                                            CONF_ENCRYPTION_KEY: self._encryption_key,
                                            CONF_WEBHOOK_SECRET: self._webhook_secret,
                                            CONF_HA_BASE_URL: self._ha_base_url, # Include HA base URL
                                        }
                                    )
                    except aiohttp.ClientError as err:
                        errors["base"] = "api_error"
                        _LOGGER.error("API request failed: %s", str(err))
                else:
                    # No changes to entities, just return the current config
                    return self.async_create_entry(
                        title="",
                        data={
                            CONF_ENTITIES: list(self._selected_entities),
                            CONF_SUBSCRIPTION_TYPE: self._subscription_type,
                            CONF_ENCRYPTION_KEY: self._encryption_key,
                            CONF_WEBHOOK_SECRET: self._webhook_secret,
                            CONF_HA_BASE_URL: self._ha_base_url, # Include HA base URL
                        }
                    )
            except Exception as err:
                errors["base"] = "unknown"
                _LOGGER.exception("Error updating entities: %s", str(err))

        # Get available entities from supported domains
        entity_registry = er.async_get(self.hass)
        
        schema = {
            vol.Optional(
                "entities", 
                default=list(self._selected_entities)
            ): EntitySelector({
                "include_entities": [
                    entity.entity_id for entity in entity_registry.entities.values()
                    if entity.domain in SUPPORTED_DOMAINS
                ],
                "multiple": True
            })
        }

        # Create description with subscription info if needed
        description = None
        if self._subscription_type == SUBSCRIPTION_TYPE_PRO:
            description = f"Subscritpion: Pro Plan - Encryption key: {self._encryption_key}"
        else:
            description = f"Subscritpion: Basic Plan - Encryption key: {self._encryption_key}"

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema),
            description_placeholders={"subscription_info": description},
            errors=errors,
        )
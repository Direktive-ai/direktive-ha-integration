"""Webhook handler for Direktive.ai integration."""
import logging
import json
from typing import Coroutine, Dict, Any
from http import HTTPStatus

from aiohttp import web
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.components.webhook import (
    async_register as async_register_webhook,
    async_unregister as async_unregister_webhook,
)
from homeassistant.const import (
    CONTENT_TYPE_JSON,
)
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN, 
    CONF_WEBHOOK_SECRET, 
    CONF_ENCRYPTION_KEY, 
    CONF_SUBSCRIPTION_TYPE,
    SUBSCRIPTION_TYPE_PRO,
)
from .encryption import decrypt_data, should_encrypt

_LOGGER = logging.getLogger(__name__)

async def async_register_integration_webhook(
    hass: HomeAssistant, 
    webhook_id: str, 
    config_entry_id: str
) -> None:
    """Register the webhook for this integration."""
    webhook_key = f"webhook_registered_{webhook_id}"
    if hass.data.get(DOMAIN, {}).get(webhook_key):
        _LOGGER.debug(f"Webhook {webhook_id} already registered.")
        return

    _LOGGER.info(f"Registering webhook with ID: {webhook_id} for config entry: {config_entry_id}")
    # Pass config_entry_id to the handler context or partially apply it
    async def handler_wrapper(hass_inner: HomeAssistant, wh_id: str, request: web.Request):
        return await async_handle_webhook(hass_inner, wh_id, request, config_entry_id)
        
    async_register_webhook(
        hass,
        domain=DOMAIN,  # Add domain
        name=DOMAIN,    # Add name
        webhook_id=webhook_id, # This is the entry_id
        handler=handler_wrapper, # The actual handler function
        local_only=False # Allow external access
    )
    hass.data.setdefault(DOMAIN, {})[webhook_key] = True

async def async_unregister_integration_webhook(hass: HomeAssistant, webhook_id: str) -> None:
    """Unregister the webhook for this integration."""
    _LOGGER.info(f"Unregistering webhook with ID: {webhook_id}")
    async_unregister_webhook(hass, webhook_id)
    hass.data.get(DOMAIN, {}).pop(f"webhook_registered_{webhook_id}", None)


async def async_handle_webhook(
    hass: HomeAssistant, 
    webhook_id: str, # This is the entry_id used as webhook_id
    request: web.Request,
    config_entry_id: str # Explicitly passed config_entry_id
) -> web.Response:
    """Handle incoming webhook from Direktive.ai API."""
    _LOGGER.debug(f"Webhook {webhook_id} received for config entry {config_entry_id}")

    # Get the config entry for this webhook
    config_entry = hass.config_entries.async_get_entry(config_entry_id)
    if not config_entry:
        _LOGGER.error(f"Webhook {webhook_id}: Config entry {config_entry_id} not found.")
        return web.Response(text="Configuration not found.", status=HTTPStatus.INTERNAL_SERVER_ERROR)

    # Authenticate the request using the X-Webhook-Secret header
    expected_secret = config_entry.data.get(CONF_WEBHOOK_SECRET)
    received_secret = request.headers.get("X-Webhook-Secret")

    if not expected_secret or not received_secret or received_secret != expected_secret:
        _LOGGER.warning(f"Webhook {webhook_id}: Unauthorized access attempt. Secret mismatch or missing.")
        return web.Response(text="Unauthorized.", status=HTTPStatus.UNAUTHORIZED)

    _LOGGER.debug(f"Webhook {webhook_id}: Authenticated successfully.")

    try:
        payload_bytes = await request.read()
        if not payload_bytes:
            _LOGGER.warning(f"Webhook {webhook_id}: Empty payload received.")
            return web.Response(text="Bad Request: Empty payload.", status=HTTPStatus.BAD_REQUEST)
        
        request_data = json.loads(payload_bytes.decode('utf-8'))
        _LOGGER.debug(f"Webhook {webhook_id}: Received raw data: {request_data}")

    except json.JSONDecodeError:
        _LOGGER.warning(f"Webhook {webhook_id}: Invalid JSON received.")
        return web.Response(text="Bad Request: Invalid JSON.", status=HTTPStatus.BAD_REQUEST)
    except Exception as e:
        _LOGGER.error(f"Webhook {webhook_id}: Error reading request body: {e}")
        return web.Response(text="Error processing request.", status=HTTPStatus.INTERNAL_SERVER_ERROR)

    service_call_data: Dict[str, Any]
    subscription_type = config_entry.data.get(CONF_SUBSCRIPTION_TYPE)
    encryption_key = config_entry.data.get(CONF_ENCRYPTION_KEY)

    if should_encrypt(subscription_type):
        if not encryption_key:
            _LOGGER.error(f"Webhook {webhook_id}: Encryption key missing for PRO user.")
            return web.Response(text="Internal Server Error: Encryption key missing.", status=HTTPStatus.INTERNAL_SERVER_ERROR)
        
        encrypted_payload_str = request_data.get("encrypted_payload")
        if not encrypted_payload_str:
            _LOGGER.warning(f"Webhook {webhook_id}: 'encrypted_payload' missing in request for PRO user.")
            return web.Response(text="Bad Request: Missing 'encrypted_payload'.", status=HTTPStatus.BAD_REQUEST)
        
        try:
            # We need to pass the data in the format decrypt_data expects.
            # Assuming your decrypt_data now expects the raw encrypted string directly.
            service_call_data = decrypt_data(encrypted_payload_str, encryption_key)
            _LOGGER.debug(f"Webhook {webhook_id}: Decrypted data: {service_call_data}")
        except Exception as e:
            _LOGGER.error(f"Webhook {webhook_id}: Failed to decrypt payload: {e}")
            return web.Response(text="Bad Request: Failed to decrypt payload.", status=HTTPStatus.BAD_REQUEST)
    else:
        # For basic users, the payload is expected directly (not encrypted)
        # We still expect it under a key, e.g. "service_call"
        service_call_data = request_data.get("service_call")
        if not service_call_data:
            _LOGGER.warning(f"Webhook {webhook_id}: 'service_call' data missing for non-PRO user.")
            return web.Response(text="Bad Request: Missing 'service_call' data.", status=HTTPStatus.BAD_REQUEST)
        _LOGGER.debug(f"Webhook {webhook_id}: Received unencrypted data: {service_call_data}")


    # Validate decrypted payload
    if not isinstance(service_call_data, dict):
        _LOGGER.warning(f"Webhook {webhook_id}: Decrypted payload is not a dictionary.")
        return web.Response(text="Bad Request: Invalid payload structure.", status=HTTPStatus.BAD_REQUEST)

    service_domain = service_call_data.get("domain")
    service_name = service_call_data.get("service")
    service_entity_id = service_call_data.get("entity_id") # Optional
    service_data = service_call_data.get("service_data", {}) # Optional, defaults to empty dict

    if not service_domain or not service_name:
        _LOGGER.warning(f"Webhook {webhook_id}: 'domain' or 'service' missing in payload.")
        return web.Response(text="Bad Request: 'domain' or 'service' missing in payload.", status=HTTPStatus.BAD_REQUEST)

    # Prepare service data, including target if entity_id is provided
    if service_entity_id:
        if "entity_id" not in service_data: # only add if not already in service_data to avoid conflict
             service_data["entity_id"] = service_entity_id
        elif service_data["entity_id"] != service_entity_id: # if it is, ensure it matches
             _LOGGER.warning(f"Webhook {webhook_id}: Mismatch between top-level 'entity_id' and 'entity_id' in 'service_data'. Using 'service_data'.")
             # service_data already contains the entity_id, so we prefer that.


    _LOGGER.info(f"Webhook {webhook_id}: Attempting to call service {service_domain}.{service_name} with data: {service_data}")

    try:
        # Check if the service exists
        if not hass.services.has_service(service_domain, service_name):
            _LOGGER.error(f"Webhook {webhook_id}: Service {service_domain}.{service_name} not found.")
            return web.Response(
                text=f"Bad Request: Service {service_domain}.{service_name} not found.", 
                status=HTTPStatus.BAD_REQUEST,
                content_type=CONTENT_TYPE_JSON
            )

        # Call the service
        # Some services might support returning a response, but many don't.
        # Removing return_response=True to avoid ServiceValidationError for services like cover.open_cover.
        await hass.services.async_call(
            domain=service_domain,
            service=service_name,
            service_data=service_data,
            blocking=True, # Wait for the service to complete
            # return_response=True # Removed to prevent ServiceValidationError
        )
        
        response_data = {"success": True, "message": f"Service {service_domain}.{service_name} called successfully."}
        # Since we removed return_response, there's no service_response to add here.

        _LOGGER.info(f"Webhook {webhook_id}: Service {service_domain}.{service_name} called.")
        return web.json_response(response_data, status=HTTPStatus.OK)

    except Exception as e:
        _LOGGER.error(f"Webhook {webhook_id}: Error calling service {service_domain}.{service_name}: {e}", exc_info=True)
        return web.json_response(
            {"success": False, "error": f"Error calling service: {e}"}, 
            status=HTTPStatus.INTERNAL_SERVER_ERROR
        ) 
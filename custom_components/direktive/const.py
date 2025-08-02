"""Constants for the Direktive.ai Remote Sync integration."""
DOMAIN = "direktive"
API_URL = "https://api.direktive.ai"
CONF_ENTITIES = "entities"
CONF_API_KEY = "api_key"
CONF_ENCRYPTION_KEY = "encryption_key"
CONF_SUBSCRIPTION_TYPE = "subscription_type"
CONF_WEBHOOK_SECRET = "webhook_secret"
CONF_WEBHOOK_REGISTERED_TO_API = "webhook_registered_to_api"
CONF_HA_BASE_URL = "ha_base_url"
CONF_INITIAL_BULK_UPDATE_PERFORMED = "initial_bulk_update_performed"

# Sync status constants
SYNC_STATUS_OK = "ok"
SYNC_STATUS_PENDING = "pending"
SYNC_STATUS_ERROR = "error"

# Subscription types
SUBSCRIPTION_TYPE_BASIC = "basic"
SUBSCRIPTION_TYPE_PRO = "pro"

# Encryption constants
ENCRYPTION_ALGORITHM = "AES-256-CBC"
ENCRYPTION_KEY_LENGTH = 32  # 256 bits
ENCRYPTION_IV_LENGTH = 16  # 128 bits

# Directives sensor constants
SENSOR_NAME = "direktive_sensor"
SENSOR_ATTRIBUTE_DIRECTIVES = "directives"
SENSOR_ATTRIBUTE_LAST_UPDATE = "last_update"
SENSOR_ATTRIBUTE_ERROR = "error"

# API endpoints
API_ENDPOINT_DIRECTIVES = "/directive"
API_ENDPOINT_DIRECTIVE = "/directive/{directive_id}"

# Update intervals
UPDATE_INTERVAL = 30000  # 5 minutes
UPDATE_INTERVAL_ERROR = 60  # 1 minute on error

# MQTT Topic for scenario triggers from addon
# ADDON_NAME in consumer.py is 'direktive-vision-ha-addon'
MQTT_SCENARIO_TRIGGER_TOPIC = "direktive-vision-ha-addon/scenario_triggers"
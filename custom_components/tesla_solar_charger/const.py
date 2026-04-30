"""Constants for Tesla Solar Charger integration."""
from enum import StrEnum

DOMAIN = "tesla_solar_charger"

# Platforms
PLATFORMS = ["select", "number", "switch", "sensor"]

# Default values
DEFAULT_NAME = "Tesla Solar Charger"
DEFAULT_VOLTAGE = 230
DEFAULT_UPDATE_INTERVAL_SECONDS = 30
DEFAULT_MIN_AMPS = 5
DEFAULT_MAX_AMPS = 32
DEFAULT_MARGIN_W = 0
DEFAULT_MIN_SOLAR_GENERATION_W = 200
DEFAULT_STOP_DELAY_SECONDS = 360  # 6 minutes
DEFAULT_RESTART_DELAY_SECONDS = 900  # 15 minutes

# Voltage limits
VOLTAGE_MIN = 100
VOLTAGE_MAX = 260

# Amps limits
AMPS_MIN_LIMIT = 1
AMPS_MAX_LIMIT = 32

# Update interval limits
UPDATE_INTERVAL_MIN = 10
UPDATE_INTERVAL_MAX = 300

# Margin limits
MARGIN_MIN = -5000
MARGIN_MAX = 5000

# Min solar generation limits
MIN_SOLAR_GENERATION_MIN = 0
MIN_SOLAR_GENERATION_MAX = 10000


class Mode(StrEnum):
    """Charging modes."""

    OFF = "Off"
    SOLAR_ONLY = "Solar Only"
    SOLAR_PLUS_GRID = "Solar + Grid"
    CHARGE_NOW = "Charge Now"


class ControllerState(StrEnum):
    """Controller state machine states."""

    DISABLED = "disabled"  # Mode is Off or master enable is off
    IDLE = "idle"  # Enabled but car not plugged in
    TRACKING = "tracking"  # Actively setting amps based on excess
    STOPPING = "stopping"  # Excess fell below threshold, running 6-min timer
    COOLDOWN = "cooldown"  # Charging stopped, running 15-min restart lockout
    FORCED = "forced"  # Charge Now mode active


# IEC 61851 states that indicate plugged in (from ESPHome Tesla BLE proxy)
# Values: Disconnected, Complete, Stopped, Starting, Charging, Calibrating, NoPower, Unknown
IEC_PLUGGED_IN_STATES = {"Complete", "Stopped", "Starting", "Charging", "Calibrating"}


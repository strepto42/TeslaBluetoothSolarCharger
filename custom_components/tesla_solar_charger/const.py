"""Constants for Tesla Solar Charger integration."""
from enum import StrEnum

DOMAIN = "tesla_solar_charger"

# Platforms
PLATFORMS = ["select", "number", "switch", "sensor", "binary_sensor"]

# Default values
DEFAULT_NAME = "Tesla Solar Charger"
DEFAULT_VOLTAGE = 230
DEFAULT_UPDATE_INTERVAL_SECONDS = 5
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
UPDATE_INTERVAL_MIN = 5
UPDATE_INTERVAL_MAX = 300

# Margin limits
MARGIN_MIN = -5000
MARGIN_MAX = 5000

# Min solar generation limits
MIN_SOLAR_GENERATION_MIN = 0
MIN_SOLAR_GENERATION_MAX = 10000

# Home battery awareness (optional — see ChargeHQ KB:
# https://chargehq.net/kb/home-battery-charge-priority-limit-configuration)
DEFAULT_BATTERY_PRIORITY_CHARGE_LIMIT_PCT = 80
BATTERY_PRIORITY_LIMIT_MIN = 0
BATTERY_PRIORITY_LIMIT_MAX = 100

# Battery priority styles. "hard_cutoff" matches ChargeHQ's published
# behaviour: below limit → battery priority, EV idle; at/above limit → all
# excess to EV. "graduated" mirrors the bucketed deduction curve from a
# known-good local Home Assistant automation: as SoC rises through 5%
# bands above the limit, the deduction shrinks from 20A down to 1A.
BATTERY_PRIORITY_STYLE_HARD_CUTOFF = "hard_cutoff"
BATTERY_PRIORITY_STYLE_GRADUATED = "graduated"
DEFAULT_BATTERY_PRIORITY_STYLE = BATTERY_PRIORITY_STYLE_HARD_CUTOFF
BATTERY_PRIORITY_STYLES = (
    BATTERY_PRIORITY_STYLE_HARD_CUTOFF,
    BATTERY_PRIORITY_STYLE_GRADUATED,
)

# Bucket deductions for the graduated style, in amps. Buckets are evaluated
# relative to the configured battery_priority_charge_limit_pct (L):
#   SoC <= L              → 0 amps allowed (battery has full priority)
#   L  <  SoC <= L+5      → -20 A
#   L+5 <  SoC <= L+10    → -15 A
#   L+10 < SoC <= L+15    → -10 A
#   L+15 < SoC <= L+19    → -5  A
#   SoC > L+19            → -1  A
BATTERY_GRADUATED_BUCKETS_A: tuple[tuple[int, int], ...] = (
    (5, 20),
    (10, 15),
    (15, 10),
    (19, 5),
)
BATTERY_GRADUATED_TOP_DEDUCTION_A = 1


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

# IEC 61851 state that means the car is *actually drawing* charge current right
# now. Used as the source of truth for whether charging is happening, instead
# of trusting that a service call we issued actually crossed the (unreliable)
# BLE link.
IEC_CHARGING_STATE = "Charging"

# Minimum seconds between re-sending the *same* switch command. While the car's
# reported state disagrees with what we want (e.g. a turn_off was dropped over
# BLE), we re-assert the command — but no more often than this, so the known
# multi-second BLE latency (and stubborn cases like a Complete car we keep
# telling to charge) can't flood the link. A genuine change of desired state
# bypasses this and sends immediately.
SWITCH_RESEND_INTERVAL_SECONDS = 30


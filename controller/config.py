"""
Sentinet Configuration
======================
Central configuration for the Sentinet SDN Controller.
Modify these values to change system behavior.
"""

# =============================================================================
# BACKEND CONNECTION
# =============================================================================
# WebSocket server address where the Backend API listens
# The Backend team should provide these values
BACKEND_HOST = "localhost"
BACKEND_PORT = 8765
BACKEND_ENABLED = False  # Set to True when Backend is ready

# =============================================================================
# CONTROLLER SETTINGS
# =============================================================================
# How often to poll switches for flow statistics (seconds)
POLL_INTERVAL = 2

# Idle timeout for flow rules (seconds) - flows expire after this
FLOW_IDLE_TIMEOUT = 30

# Hard timeout for flow rules (seconds) - flows always expire after this
FLOW_HARD_TIMEOUT = 300

# =============================================================================
# AI SETTINGS
# =============================================================================
# Enable/disable AI modules (set to False for testing without AI)
SENTINEL_ENABLED = False  # Security AI - set True when model is ready
NAVIGATOR_ENABLED = False  # Routing AI - set True when model is ready

# Path to trained model files (Security team provides these)
SENTINEL_MODEL_PATH = "../ai_models/sentinel_model.joblib"
NAVIGATOR_MODEL_PATH = "../ai_models/navigator_model.joblib"

# =============================================================================
# DEMO / PRESENTATION SETTINGS
# =============================================================================
# How long to keep alerts "sticky" for visualization (seconds)
ALERT_COOLDOWN = 10

# Thresholds for manual attack detection (used when AI is disabled)
# If pps exceeds this, flag as potential attack
ATTACK_PPS_THRESHOLD = 1000

# If bps exceeds this, flag as potential attack  
ATTACK_BPS_THRESHOLD = 100000

# =============================================================================
# LOGGING
# =============================================================================
# Enable verbose logging of flow stats
VERBOSE_STATS = True

# Enable CSV logging (for training data generation)
CSV_LOGGING = True
CSV_FILE_PATH = "traffic_data.csv"

# =============================================================================
# TOPOLOGY METADATA
# =============================================================================
# Used for JSON output to Backend AND for port number calculation!
#
# ⚠️  CRITICAL SYNCHRONIZATION WARNING ⚠️
# This MUST EXACTLY MATCH topo.py in:
#   1. Host order (which switch each host connects to)
#   2. Link order (the ORDER links are added determines port numbers)
#
# If you modify topo.py, you MUST update this to match!
# Failure to sync will cause Navigator AI to route to WRONG PORTS!
#
TOPOLOGY = {
    "switches": [
        {"id": "s1", "dpid": 1, "role": "core"},
        {"id": "s2", "dpid": 2, "role": "distribution"},
        {"id": "s3", "dpid": 3, "role": "access"},
        {"id": "s4", "dpid": 4, "role": "access"},
        {"id": "s5", "dpid": 5, "role": "access"}
    ],
    "hosts": [
        {"id": "h1", "mac": "00:00:00:00:00:01", "ip": "10.0.0.1", "switch": "s3"},
        {"id": "h2", "mac": "00:00:00:00:00:02", "ip": "10.0.0.2", "switch": "s3"},
        {"id": "h3", "mac": "00:00:00:00:00:03", "ip": "10.0.0.3", "switch": "s3"},
        {"id": "h4", "mac": "00:00:00:00:00:04", "ip": "10.0.0.4", "switch": "s2"},
        {"id": "h5", "mac": "00:00:00:00:00:05", "ip": "10.0.0.5", "switch": "s4"},
        {"id": "h6", "mac": "00:00:00:00:00:06", "ip": "10.0.0.6", "switch": "s5"},
        {"id": "h7", "mac": "00:00:00:00:00:07", "ip": "10.0.0.7", "switch": "s5"},
        {"id": "h8", "mac": "00:00:00:00:00:08", "ip": "10.0.0.8", "switch": "s5"}
    ],
    "links": [
        {"from": "s1", "to": "s2", "bw_mbps": 100, "delay_ms": 1},
        {"from": "s1", "to": "s4", "bw_mbps": 50,  "delay_ms": 2},
        {"from": "s1", "to": "s5", "bw_mbps": 100, "delay_ms": 1},
        {"from": "s2", "to": "s3", "bw_mbps": 50,  "delay_ms": 3}
    ]
}

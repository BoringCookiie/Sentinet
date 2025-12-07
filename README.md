# Sentinet - Self-Healing SDN Network

A Software-Defined Network with AI-powered DDoS detection and automatic mitigation.

## Architecture

```
┌───────────────────────┐        ┌──────────────┐       ┌──────────────┐
│      CONTROLLER       │        │   BACKEND    │       │   FRONTEND   │
│        (Ryu)          │───────▶│    (API)     │──────▶│   (React)    │
│  ┌─────────────────┐  │        └──────────────┘       └──────────────┘
│  │   AI MODELS     │  │
│  │ Sentinel+Navigator │
│  └─────────────────┘  │
└───────────────────────┘
```

## Prerequisites

### System Requirements
- **OS**: Linux / WSL2 on Windows
- **Python**: 3.9+
- **Mininet**: 2.3.0+
- **Open vSwitch**: 2.13+

### Installation (WSL2 / Ubuntu)

```bash
# 1. Install system dependencies
sudo apt update
sudo apt install -y mininet openvswitch-switch python3-pip

# 2. Clone the repository
git clone <your-repo-url>
cd ethique

# 3. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 4. Install Python dependencies
pip install -r requirements.txt
```

## Quick Start

### Terminal 1: Start the Controller

```bash
# Always clean Mininet first
sudo mn -c

# Activate environment and start Ryu
source .venv/bin/activate
cd controller
ryu-manager sentinet_controller.py
```

**Expected output:**
```
[SENTINET] Controller initialized
[AI] Sentinel: {'enabled': False, 'mode': 'Threshold Fallback'}
[AI] Navigator: {'enabled': False, 'mode': 'Default Flooding'}
```

### Terminal 2: Start the Network

```bash
source .venv/bin/activate
cd controller
sudo python3 topo.py
```

**Expected output:**
```
*** Network is UP. Running CLI...
mininet>
```

### Terminal 2: Test Connectivity

```bash
mininet> pingall
# Expected: Results: 0% dropped (56/56 received)
```

## Project Structure

```
ethique/
├── controller/
│   ├── sentinet_controller.py  # Main Ryu controller
│   ├── ai_interface.py         # AI model wrappers
│   ├── backend_client.py       # WebSocket client
│   ├── config.py               # Configuration
│   ├── topo.py                 # Mininet topology
│   └── traffic_data.csv        # Generated training data
│
├── ai_models/                   # AI team's models go here
│   └── sentinel_model.joblib   # Trained security model
│
├── backend/                     # Backend team's API
│
├── frontend/                    # Frontend team's React app
│
├── ARCHITECTURE.md             # System architecture docs
└── requirements.txt            # Python dependencies
```

## Team Integration Guide

### For Security Team (Sentinel AI)

1. **Input**: The controller calls your model with:
   ```python
   prediction = model.predict([[pps, bps, avg_pkt_size]])
   ```

2. **Output**: Return `-1` for attack, `1` for normal

3. **Deliverable**: Place `sentinel_model.joblib` in `ai_models/`

4. **Enable**: Set `SENTINEL_ENABLED = True` in `controller/config.py`

### For Routing Team (Navigator AI)

1. **Input**: The controller calls your model with:
   ```python
   path = model.get_path(src_mac, dst_mac, network_graph)
   ```

2. **Output**: Return list of switch IDs, e.g., `["s3", "s2", "s1", "s5"]`

3. **Deliverable**: Place `navigator_model.joblib` in `ai_models/`

4. **Enable**: Set `NAVIGATOR_ENABLED = True` in `controller/config.py`

### For Backend Team

1. **Connection**: WebSocket server at `ws://localhost:8765`

2. **Messages received**:
   - `{"type": "topology", ...}` - On boot
   - `{"type": "stats_update", ...}` - Every 2s
   - `{"type": "security_alert", ...}` - On attack

3. **Enable**: Set `BACKEND_ENABLED = True` in `controller/config.py`

4. **Update**: Set `BACKEND_HOST` and `BACKEND_PORT` in config

### For Frontend Team

1. **Data source**: WebSocket from Backend

2. **Topology**: JSON with switches, hosts, links

3. **Stats**: Flow data every 2s for live charts

4. **Alerts**: Security events for red node highlighting

## Generating Training Data

```bash
# In Mininet CLI
h2 iperf -s &                          # Start receiver
h1 iperf -c 10.0.0.2 -t 60 &          # Normal traffic (60s)
h4 ping -c 120 -i 0.5 10.0.0.1 &      # Background noise

# Wait 60 seconds, then check:
# controller/traffic_data.csv
```

## Simulating an Attack

```bash
# In Mininet CLI - DDoS from h3 (attacker)
h3 hping3 --flood -1 10.0.0.6

# Controller should detect and block within 2-4 seconds
# Check Terminal 1 for: [ATTACK] DDoS detected: 00:00:00:00:00:03 -> 00:00:00:00:00:06
```

## Configuration

Edit `controller/config.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `BACKEND_ENABLED` | `False` | Enable WebSocket to Backend |
| `SENTINEL_ENABLED` | `False` | Enable Security AI |
| `NAVIGATOR_ENABLED` | `False` | Enable Routing AI |
| `POLL_INTERVAL` | `2` | Stats polling interval (seconds) |
| `ALERT_COOLDOWN` | `10` | Alert stickiness for demo (seconds) |
| `ATTACK_PPS_THRESHOLD` | `1000` | Fallback attack threshold |

## Troubleshooting

### "Cannot connect to controller"
```bash
sudo mn -c  # Clean up Mininet
# Restart controller first, then topology
```

### "Permission denied"
```bash
sudo python3 topo.py  # Mininet needs root
```

### "Module not found"
```bash
source .venv/bin/activate
pip install -r requirements.txt
```

## License

MIT

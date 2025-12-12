# Sentinet: AI-Powered SDN Defense & Routing System

Sentinet is a Software Defined Networking (SDN) project that uses Artificial Intelligence to secure and optimize network traffic. It features a custom Ryu Controller that integrates three distinct AI models:

- **Sentinel** (Anomaly Detection): Detecting 0-day threats.
- **Analyst** (Traffic Classifier): Distinguishing between SYN Floods and Volumetric DDoS.
- **Navigator** (Traffic Engineer): Using Reinforcement Learning (Q-Learning) to reroute traffic around congestion.

---

## 📋 Prerequisites

- **OS**: Ubuntu 20.04/22.04 (or WSL2 on Windows).
- **Python**: Version 3.9 (Strict Requirement for Ryu/Eventlet compatibility).
- **Mininet**: Installed on the system.

---

## ⚙️ Installation Guide

### 1. System Dependencies

```bash
sudo apt update
sudo apt install python3.9 python3.9-venv python3.9-dev mininet openvswitch-testcontroller -y
```

### 2. Set Up Virtual Environment

Do not use the system Python. Create a specific environment for the project.

```bash
cd ~/sentinet

# Create venv using Python 3.9
python3.9 -m venv venv

# Activate it (Run this every time you open a terminal)
source venv/bin/activate
```

### 3. Install Python Libraries

We need specific versions to avoid compatibility errors between Ryu and the AI libraries.

```bash
# Upgrade pip first
pip install --upgrade pip

# Install Core & AI libraries
pip install pandas numpy scikit-learn joblib fastapi uvicorn requests sqlalchemy networkx

# Install SDN libraries (Specific versions required!)
pip install ryu
pip install "eventlet==0.30.2" "greenlet==1.1.2"
```

---

## 🧠 Model Training (Do this first!)

Before running the controller, you must train the "Brains" of the system.

```bash
# 1. Generate synthetic training data (Normal Baseline)
python generate_traffic.py

# 2. Train the Anomaly Detector (The Guard)
python ai_models/train_anomaly.py

# 3. Train the Classifier (The Analyst)
python ai_models/train_classifier.py
```

**Success Check**: Ensure `.joblib` files appear in the `ai_models/` folder.

---

## 🚀 How to Run the System

You need **3 separate terminal windows**. Always activate the venv (`source venv/bin/activate`) in Terminals 1 and 2.

### Terminal 1: The Backend (Database & Logs)

Starts the API server to record alerts and stats.

```bash
cd ~/sentinet/backend
python3 -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Terminal 2: The Controller (The Brain)

Runs the Ryu Controller with our custom AI logic.

```bash
cd ~/sentinet/controller
# Use -W ignore to hide Sklearn warnings
python -W ignore -m ryu.cmd.manager sentinet_controller.py
```

### Terminal 3: The Simulation (The Network)

Runs Mininet. We have two topologies depending on what you want to test.

---

## 🧪 Demo Scenarios

### Scenario A: Security Defense (DDoS Detection)

**Goal**: Prove the AI can distinguish between different attacks and block them.

**Config**: Ensure `SENTINEL_ENABLED = True` in `controller/config.py`.

**Start Mininet (Terminal 3)**:

```bash
sudo python3 controller/topo_smart.py
```

**Test 1: SYN Flood** (Fast, Small Packets)

```bash
h1 ping -i 0.05 h2
```

**Result**: Controller logs show `[ATTACK] SYN Flood detected`. Ping stops.

**Test 2: Volumetric DDoS** (Heavy Bandwidth)

Wait 60s for the block to expire.

Run:

```bash
h1 ping -i 0.05 -s 1200 h2
```

**Result**: Controller logs show `[ATTACK] Volumetric DDoS detected`. Ping stops.

---

### Scenario B: Smart Routing (Traffic Engineering)

**Goal**: Prove the AI can reroute traffic around a "Traffic Jam."

**Config**: ⚠️ **IMPORTANT**: Set `SENTINEL_ENABLED = False` in `controller/config.py` (otherwise the Guard will block the heavy traffic test).

**Restart Controller (Terminal 2)**.

**Start Mininet (Terminal 3)**:

```bash
sudo python3 controller/topo_smart.py
```

**Establish Baseline**:

```bash
h1 ping -c 3 h2
```

**Result**: Low latency (~1ms). Traffic is on the Fast Path.

**Create Traffic Jam**:

```bash
# Start receiver on h2
h2 iperf -s &

# Start heavy transfer from h1 (30 seconds)
h1 iperf -c h2 -t 30 &
```

**Verify Reroute**:

Immediately run ping again:

```bash
h1 ping -c 5 h2
```

**Result**: Latency jumps to ~20-30ms. This proves the AI moved traffic to the backup path (which has artificial delay) to avoid the jam.

---

## 🔧 Troubleshooting

### Error: `AttributeError: module 'eventlet' has no attribute 'ALREADY_HANDLED'`

**Fix**: You installed the wrong eventlet. Run:
```bash
pip install "eventlet==0.30.2" "greenlet==1.1.2"
```

### Error: `Address already in use` (Controller)

**Fix**: Run `sudo fuser -k 6633/tcp` to kill the zombie controller process.

### Error: Mininet crashes.

**Fix**: Always run `sudo mn -c` to clean up Mininet before starting a new topology.

---

## 📁 Project Structure

```
sentinet/
├── controller/
│   ├── sentinet_controller.py   # Main Ryu controller
│   ├── ai_interface.py          # AI model wrappers
│   ├── config.py                # Configuration flags
│   ├── topo.py                  # Production topology
│   └── topo_smart.py            # Diamond test topology
│
├── ai_models/
│   ├── navigator_brain.py       # Q-Learning routing
│   ├── train_anomaly.py         # Isolation Forest training
│   ├── train_classifier.py      # Random Forest training
│   └── *.joblib                 # Trained models
│
├── backend/
│   └── main.py                  # FastAPI server
│
├── generate_traffic.py          # Training data generator
└── README.md                    # This file
```

---

## 👥 Team

- **Member 1**: SDN Controller Development
- **Member 2**: Security AI (Sentinel + Analyst)
- **Member 3**: Routing AI (Navigator)
- **Member 4**: Backend & Dashboard

---

*Sentinet v1.0 - AI-Powered Self-Healing Network*
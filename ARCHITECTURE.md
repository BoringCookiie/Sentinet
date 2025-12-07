# Sentinet Architecture & Data Flow

## System Overview

```
┌────────────────────────────────────────────────────────────────────────────┐
│                             SENTINET SYSTEM                                 │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│    ┌───────────────────────┐        ┌──────────────┐       ┌──────────────┐│
│    │      CONTROLLER       │        │   BACKEND    │       │   FRONTEND   ││
│    │        (Ryu)          │───────▶│    (API)     │──────▶│   (React)    ││
│    │  ┌─────────────────┐  │        └──────────────┘       └──────────────┘│
│    │  │   AI MODELS     │  │                                                │
│    │  │ ┌─────────────┐ │  │                                                │
│    │  │ │  Sentinel   │ │  │◀── Fast Path (microseconds)                   │
│    │  │ │  (Security) │ │  │                                                │
│    │  │ └─────────────┘ │  │                                                │
│    │  │ ┌─────────────┐ │  │                                                │
│    │  │ │  Navigator  │ │  │◀── Path calculation                           │
│    │  │ │  (Routing)  │ │  │                                                │
│    │  │ └─────────────┘ │  │                                                │
│    │  └─────────────────┘  │                                                │
│    └───────────────────────┘                                                │
│                                                                             │
└────────────────────────────────────────────────────────────────────────────┘
```

> **Why AI is inside Controller?**  
> Latency. If AI lived in Backend, blocking would take 100-200ms extra.  
> With AI inside Controller, blocking happens in **microseconds**.

---

## Data Flow Sequences

### Flow A: The "Heartbeat" (Every 2 seconds)

```
┌──────────┐    OFPFlowStatsRequest    ┌──────────┐
│Controller│ ─────────────────────────▶│ Switches │
│          │◀───────────────────────── │ s1..s5   │
└────┬─────┘    OFPFlowStatsReply      └──────────┘
     │
     ├──▶ [pps, bps] ──▶ Sentinel AI ──▶ Safe/Attack
     │
     └──▶ JSON Stats ──▶ Backend ──▶ Frontend (Live Charts)
```

### Flow B: The "Reflex" (New Connection)

```
┌────┐  Packet   ┌────┐  PACKET_IN   ┌──────────┐
│ h1 │ ────────▶ │ s3 │ ───────────▶ │Controller│
└────┘           └────┘              └────┬─────┘
                                          │
                                          ▼
                                    ┌───────────┐
                                    │ Navigator │ "Path h1→h7?"
                                    │    AI     │
                                    └─────┬─────┘
                                          │ [s3, s2, s1, s5]
                                          ▼
┌────┐           ┌────┐  FLOW_MOD   ┌──────────┐
│ h7 │ ◀──────── │ s5 │ ◀────────── │Controller│
└────┘           └────┘             └──────────┘
```

### Flow C: The "Immune Response" (Attack Detected)

```
Heartbeat ──▶ Sentinel AI ──▶ ANOMALY (-1)
                                    │
         ┌──────────────────────────┘
         ▼
┌──────────────┐
│  Controller  │
│  1. FLOW_MOD │──▶ All Switches: DROP attacker
│  2. Alert    │──▶ Backend ──▶ Frontend (RED NODE)
└──────────────┘
```

---

## Controller Outputs

### Output 1: Topology (On Boot)

```json
{
    "type": "topology",
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
```

### Output 2: Flow Stats (Every 2s)

```json
{
    "type": "stats_update",
    "timestamp": 1765099563.148,
    "switches": [
        {
            "dpid": 1,
            "flows": [
                {
                    "src_mac": "00:00:00:00:00:01",
                    "dst_mac": "00:00:00:00:00:02",
                    "pps": 21.98,
                    "bps": 2153.85,
                    "avg_pkt_size": 98.0
                }
            ]
        }
    ]
}
```

### Output 3: Security Alert (On Attack)

```json
{
    "type": "security_alert",
    "timestamp": 1765099570.000,
    "attacker_mac": "00:00:00:00:00:03",
    "attacker_ip": "10.0.0.3",
    "target_ip": "10.0.0.6",
    "severity": "CRITICAL",
    "action_taken": "BLOCKED",
    "block_duration_sec": 60
}
```

---

## Demo Techniques (For Presentation)

### 1. Alert "Stickiness" (Controller)
Keep alerts active for 10 seconds even if attack stops instantly.
```python
if is_attack:
    self.attack_cooldown = time.time() + 10
# Keep sending alert while cooldown active
```

### 2. Traffic Smoothing (Backend)
Use moving average instead of raw spiky data.
```
Raw:      500 → 0 → 600
Smoothed: 500 → 250 → 425
```

### 3. Slow-Motion Attack Script
```python
# attack_simulation.py (run on h3)
print("Ramping up: 10%...")
os.system("timeout 3s hping3 -i u10000 10.0.0.6")
print("Ramping up: 50%...")
os.system("timeout 3s hping3 -i u1000 10.0.0.6")
print("FULL POWER...")
os.system("timeout 5s hping3 --flood 10.0.0.6")
```

---

## Team Responsibilities

| Component | Owner | Input | Output |
|-----------|-------|-------|--------|
| **Controller + AI** | Architect | Network Traffic | Topology + Stats + Blocking |
| **Sentinel Model** | Security Lead | [pps, bps, avg_size] | -1 (attack) or 1 (safe) |
| **Navigator Model** | Routing Lead | (src, dst) | Path list |
| **Backend** | Backend Lead | JSON from Controller | WebSocket to Frontend |
| **Frontend** | Frontend Lead | WebSocket JSON | Visualization |

---

## Communication Protocol

| Connection | Protocol | Direction |
|------------|----------|-----------|
| Controller → Backend | TCP Socket / ZeroMQ | Push (Controller sends) |
| Backend → Frontend | WebSocket (Socket.io) | Push (Backend sends) |
| AI ↔ Controller | Direct Python Import | In-process |

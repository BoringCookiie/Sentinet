# Sentinet Backend API Documentation

## Architecture Overview

```
Controller ──POST──> Backend ──WebSocket/HTTP──> Frontend
                      │
                      └──SQLite (Alerts only)
```

The backend acts as a **bridge** between the SDN controller and the frontend, using:
- **HTTP POST** endpoints to receive data from the controller
- **WebSocket** for real-time streaming to the frontend
- **HTTP GET** endpoints for frontend queries

---

## 1. Data Sent FROM Controller TO Backend (HTTP POST)

### A. Topology Data - `POST /api/topology`

**When**: Controller startup or topology changes  
**Purpose**: Provide network structure for visualization  

**Message Body**:
```json
{
  "type": "topology",
  "switches": [
    {
      "id": "s1",
      "dpid": 1,
      "role": "core"
    },
    {
      "id": "s2",
      "dpid": 2,
      "role": "distribution"
    }
  ],
  "hosts": [
    {
      "id": "h1",
      "ip": "10.0.0.1",
      "switch": "s3",
      "mac": "00:00:00:00:00:01"
    },
    {
      "id": "h2",
      "ip": "10.0.0.2",
      "switch": "s3",
      "mac": "00:00:00:00:00:02"
    }
  ],
  "links": [
    {
      "from": "s1",
      "to": "s2",
      "bw_mbps": 100,
      "delay_ms": 1
    },
    {
      "from": "s2",
      "to": "s3",
      "bw_mbps": 100,
      "delay_ms": 1
    }
  ]
}
```

**Backend Action**: Stores in memory + broadcasts to all WebSocket clients

---

### B. Traffic Statistics - `POST /api/stats`

**When**: Every `POLL_INTERVAL` seconds (~2s)  
**Purpose**: Real-time flow statistics for monitoring  

**Message Body**:
```json
{
  "type": "stats_update",
  "timestamp": 1734234567.89,
  "data": {
    "s3": {
      "flows": [
        {
          "src_mac": "00:00:00:00:00:01",
          "dst_mac": "00:00:00:00:00:02",
          "packet_count": 1250,
          "byte_count": 420000,
          "pps": 50.5,
          "bps": 16800.2,
          "avg_pkt_size": 336
        }
      ]
    }
  }
}
```

**Backend Action**: **Pass-through only** - broadcasts to WebSocket clients immediately, NOT stored in DB

---

### C. Security Alerts - `POST /api/alert`

**When**: Sentinel AI detects an attack  
**Purpose**: Notify of security threats  

**Message Body**:
```json
{
  "type": "security_alert",
  "timestamp": 1734234567.89,
  "attacker_ip": "10.0.0.3",
  "target_ip": "10.0.0.6",
  "severity": "CRITICAL",
  "action_taken": "BLOCK"
}
```

**Severity Levels**: `INFO`, `WARNING`, `CRITICAL`  
**Action Types**: `BLOCK`, `RATE_LIMIT`, `ALERT_ONLY`  

**Backend Action**:
1. Saves to SQLite database (persistent)
2. Broadcasts to all WebSocket clients (real-time)

**Database Alert Record**:
```json
{
  "id": 42,
  "timestamp": 1734234567.89,
  "attacker_ip": "10.0.0.3",
  "target_ip": "10.0.0.6",
  "severity": "CRITICAL",
  "action_taken": "BLOCK",
  "created_at": "2025-12-15T10:30:45.123456"
}
```

---

## 2. Data Sent FROM Backend TO Frontend

### Via WebSocket (`ws://localhost:8000/ws`)

The WebSocket broadcasts **three types of messages** in real-time:

#### A. Topology Update

**Sent**: On controller startup, topology changes, or when client first connects  

**Message**:
```json
{
  "type": "topology_update",
  "data": {
    "type": "topology",
    "switches": [...],
    "hosts": [...],
    "links": [...]
  }
}
```
*(Same structure as controller POST body)*

---

#### B. Stats Update

**Sent**: Every ~2 seconds (transient, real-time only)  

**Message**:
```json
{
  "type": "stats_update",
  "timestamp": 1734234567.89,
  "data": {
    "s3": {
      "flows": [
        {
          "src_mac": "00:00:00:00:00:01",
          "dst_mac": "00:00:00:00:00:02",
          "pps": 50.5,
          "bps": 16800.2,
          "avg_pkt_size": 336
        }
      ]
    }
  }
}
```

**Frontend Use**: Display real-time traffic graphs, link utilization, flow tables

---

#### C. Security Alert

**Sent**: Immediately when attack detected  

**Message**:
```json
{
  "type": "security_alert",
  "timestamp": 1734234567.89,
  "data": {
    "id": 42,
    "attacker_ip": "10.0.0.3",
    "target_ip": "10.0.0.6",
    "severity": "CRITICAL",
    "action_taken": "BLOCK"
  }
}
```

**Frontend Use**: Flash red nodes, show alert banner, trigger sound/notification

---

#### D. Command Queued

**Sent**: When frontend requests manual block  

**Message**:
```json
{
  "type": "command_queued",
  "data": {
    "command": "block",
    "ip": "10.0.0.5",
    "status": "pending"
  }
}
```

**Frontend Use**: Show "blocking in progress" indicator

---

### Via HTTP GET Endpoints (Frontend Queries)

#### A. Get Current Topology - `GET /api/topology`

**Response**:
```json
{
  "type": "topology",
  "switches": [...],
  "hosts": [...],
  "links": [...]
}
```

**Use**: Initial load or refresh

---

#### B. Get Alert History - `GET /api/history/alerts?limit=50`

**Response**:
```json
[
  {
    "id": 42,
    "timestamp": 1734234567.89,
    "attacker_ip": "10.0.0.3",
    "target_ip": "10.0.0.6",
    "severity": "CRITICAL",
    "action_taken": "BLOCK",
    "created_at": "2025-12-15T10:30:45.123456"
  },
  {
    "id": 41,
    "timestamp": 1734234500.12,
    "attacker_ip": "10.0.0.5",
    "target_ip": "10.0.0.2",
    "severity": "WARNING",
    "action_taken": "RATE_LIMIT",
    "created_at": "2025-12-15T10:29:30.987654"
  }
]
```

**Use**: Populate alerts history panel/table

---

#### C. Health Check - `GET /api/health`

**Response**:
```json
{
  "status": "healthy",
  "connected_clients": 3,
  "timestamp": 1734234567.89
}
```

**Use**: Monitoring, uptime checks

---

## 3. Data Sent FROM Frontend TO Backend

### A. Manual IP Block Request - `POST /api/control/block-ip`

**Request Body**:
```json
{
  "ip": "10.0.0.5",
  "duration": 60
}
```

**Response**:
```json
{
  "status": "success",
  "message": "Block command for 10.0.0.5 queued",
  "queue_size": 1
}
```

**Flow**: Frontend → Backend queue → Controller polls → Executes block

---

### B. View Command Queue - `GET /api/control/queue`

**Response**:
```json
{
  "queue_size": 2,
  "commands": [
    {
      "command": "block",
      "ip": "10.0.0.5",
      "duration": 60,
      "timestamp": 1734234567.89
    },
    {
      "command": "block",
      "ip": "10.0.0.7",
      "duration": 120,
      "timestamp": 1734234570.12
    }
  ]
}
```

**Use**: Debug or show pending commands in UI

---

## 4. Controller Polling Endpoint

### Get Pending Commands - `GET /api/control/pending`

**Called by**: Controller every ~1 second  

**Response (if commands exist)**:
```json
{
  "command": "block",
  "ip": "10.0.0.5",
  "duration": 60
}
```

**Response (if queue empty)**:
```json
{
  "command": null,
  "ip": null,
  "duration": null
}
```

**Action**: Controller executes command, command removed from queue (FIFO)

---

## Key Design Patterns

### 1. "Pulse" Strategy
- **Stats** = transient (no DB, WebSocket only)
- **Alerts** = persistent (DB + WebSocket for "sticky" visualization)
- **Topology** = cached in-memory for instant retrieval

### 2. Broadcast Model
All connected frontends receive same real-time data simultaneously

### 3. Mailbox Pattern
Frontend puts commands in queue, controller polls and executes

### 4. Connection Management
Tracks active WebSocket clients, auto-cleans disconnected

---

## Complete Data Flow Example

```
1. Controller detects DDoS attack
   └─> POST /api/alert {"attacker_ip": "10.0.0.3", ...}

2. Backend receives alert
   ├─> Saves to SQLite (id: 42)
   └─> Broadcasts via WebSocket to all frontends

3. Frontend receives WebSocket message
   ├─> {"type": "security_alert", "data": {...}}
   └─> Highlights attacker node in red, shows alert banner

4. User clicks "Block IP" button
   └─> Frontend: POST /api/control/block-ip {"ip": "10.0.0.3"}

5. Backend queues command
   └─> Broadcasts {"type": "command_queued", ...}

6. Controller polls every 1s
   └─> GET /api/control/pending returns block command

7. Controller executes block
   └─> Installs DROP flow rules on all switches
```

---

## Testing the API

### Start Backend Server
```bash
cd backend
python main.py
```

Server will run on: `http://localhost:8000`  
API Docs: `http://localhost:8000/docs`  
WebSocket: `ws://localhost:8000/ws`

### Test with curl

**Send Topology**:
```bash
curl -X POST http://localhost:8000/api/topology \
  -H "Content-Type: application/json" \
  -d '{
    "type": "topology",
    "switches": [{"id": "s1", "dpid": 1, "role": "core"}],
    "hosts": [{"id": "h1", "ip": "10.0.0.1", "switch": "s1"}],
    "links": []
  }'
```

**Send Alert**:
```bash
curl -X POST http://localhost:8000/api/alert \
  -H "Content-Type: application/json" \
  -d '{
    "type": "security_alert",
    "timestamp": 1734234567.89,
    "attacker_ip": "10.0.0.3",
    "target_ip": "10.0.0.6",
    "severity": "CRITICAL",
    "action_taken": "BLOCK"
  }'
```

**Get Topology**:
```bash
curl http://localhost:8000/api/topology
```

**Get Alerts**:
```bash
curl http://localhost:8000/api/history/alerts?limit=10
```

**Block IP**:
```bash
curl -X POST http://localhost:8000/api/control/block-ip \
  -H "Content-Type: application/json" \
  -d '{"ip": "10.0.0.5", "duration": 60}'
```

### Test WebSocket (Python)

```python
import asyncio
import websockets
import json

async def test_websocket():
    uri = "ws://localhost:8000/ws"
    async with websockets.connect(uri) as websocket:
        print("Connected to Sentinet Backend")
        
        while True:
            message = await websocket.recv()
            data = json.loads(message)
            print(f"Received: {data['type']}")
            print(json.dumps(data, indent=2))

asyncio.run(test_websocket())
```

### Test WebSocket (JavaScript)

```javascript
const ws = new WebSocket('ws://localhost:8000/ws');

ws.onopen = () => {
    console.log('Connected to Sentinet Backend');
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('Received:', data.type);
    console.log(data);
};

ws.onerror = (error) => {
    console.error('WebSocket error:', error);
};

ws.onclose = () => {
    console.log('Disconnected');
};
```

---

## Frontend Integration Checklist

- [ ] Connect to WebSocket on component mount
- [ ] Handle `topology_update` messages to render network graph
- [ ] Handle `stats_update` messages to update real-time metrics
- [ ] Handle `security_alert` messages to show notifications
- [ ] Fetch initial topology via `GET /api/topology`
- [ ] Fetch alert history via `GET /api/history/alerts`
- [ ] Implement manual block via `POST /api/control/block-ip`
- [ ] Handle WebSocket reconnection on disconnect
- [ ] Display connection status indicator

---

## Database Schema

### Alerts Table

| Column       | Type     | Description                          |
|--------------|----------|--------------------------------------|
| id           | INTEGER  | Primary key (auto-increment)         |
| timestamp    | FLOAT    | Unix timestamp from controller       |
| attacker_ip  | STRING   | Attacker IP address                  |
| target_ip    | STRING   | Target IP address                    |
| severity     | STRING   | Alert severity (INFO/WARNING/CRITICAL)|
| action_taken | STRING   | Response action (BLOCK/RATE_LIMIT/etc)|
| created_at   | DATETIME | Database insertion timestamp         |

---

## Troubleshooting

### WebSocket not connecting
- Check if backend is running: `curl http://localhost:8000/api/health`
- Verify CORS settings allow your frontend origin
- Check browser console for connection errors

### No stats updates
- Verify controller is POSTing to `/api/stats`
- Check backend logs for received messages
- Ensure WebSocket connection is active

### Alerts not appearing
- Check SQLite database: `sqlite3 sentinet.db "SELECT * FROM alerts;"`
- Verify controller is POSTing to `/api/alert`
- Check WebSocket connection is receiving messages

### Commands not executing
- Verify controller is polling `GET /api/control/pending`
- Check command queue: `curl http://localhost:8000/api/control/queue`
- Check backend logs for command dispatch

---

## API Endpoints Summary

| Method | Endpoint                    | Caller     | Purpose                          |
|--------|----------------------------|------------|----------------------------------|
| POST   | `/api/topology`            | Controller | Send network topology            |
| POST   | `/api/stats`               | Controller | Send traffic statistics          |
| POST   | `/api/alert`               | Controller | Send security alert              |
| GET    | `/api/control/pending`     | Controller | Poll for manual commands         |
| GET    | `/api/topology`            | Frontend   | Get current topology             |
| GET    | `/api/history/alerts`      | Frontend   | Get alert history                |
| POST   | `/api/control/block-ip`    | Frontend   | Request IP block                 |
| GET    | `/api/control/queue`       | Frontend   | View pending commands            |
| GET    | `/api/health`              | Any        | Health check                     |
| WS     | `/ws`                      | Frontend   | Real-time updates                |

---

**Last Updated**: December 15, 2025  
**Sentinet Version**: 1.0.0

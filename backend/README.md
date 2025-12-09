# Sentinet Backend Integration

> Backend Integrator Module for the Sentinet SDN Project

This module bridges the **Ryu Controller** (Python) and the **React Frontend** using a FastAPI server with WebSocket support.

---

##  Overview

```
┌─────────────┐      REST API       ┌─────────────┐      WebSocket      ┌─────────────┐
│ Controller  │ ─────────────────►  │   Backend   │ ─────────────────►  │  Frontend   │
│    (Ryu)    │  POST /api/*        │  (FastAPI)  │  ws://localhost     │   (React)   │
└─────────────┘                     └─────────────┘                     └─────────────┘
       │                                   │
       │  GET /api/control/pending         │
       │◄──────────────────────────────────│  (Command Polling)
       │                                   │
       └───────────────────────────────────┴──► SQLite (Alerts only)
```

### The "Pulse" Strategy
- **Stats**: Pass-through only (no DB storage) - broadcast in real-time
- **Alerts**: Persisted to SQLite AND broadcast immediately
- **Topology**: Cached in-memory for instant retrieval
- **Commands**: Queued in-memory, polled by Controller

---

##  Tech Stack

| Component | Technology |
|-----------|------------|
| Framework | FastAPI |
| Database | SQLite + SQLAlchemy |
| Real-time | WebSocket |
| HTTP Client | Requests (with threading) |
| Validation | Pydantic |

---

##  File Structure

```
backend/
├── main.py         # FastAPI server (endpoints, WebSocket, CORS)
├── database.py     # SQLAlchemy setup, Alert model, CRUD operations
├── models.py       # Pydantic models (data validation schemas)
└── sentinet.db     # SQLite database (auto-created)

controller/
├── backend_client.py   # REST client for Controller → Backend communication
└── config.py           # Backend URL configuration (BACKEND_HOST, BACKEND_PORT)
```

---

##  Quick Start

### 1. Install Dependencies
```bash
cd sentinet
source .venv/bin/activate
pip install fastapi uvicorn sqlalchemy pydantic requests
```

### 2. Start Backend Server
```bash
cd backend
python main.py
```

Server runs at:
- **REST API**: `http://localhost:8000`
- **WebSocket**: `ws://localhost:8000/ws`
- **API Docs**: `http://localhost:8000/docs`

### 3. Controller Integration
The Controller uses `BackendClient` automatically. Ensure `BACKEND_ENABLED = True` in `controller/config.py`.

---

##  API Endpoints

### Controller → Backend (Data Receivers)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/topology` | Receive network topology |
| POST | `/api/stats` | Receive traffic statistics |
| POST | `/api/alert` | Receive security alert (saves to DB) |

### Frontend → Backend (Data Providers)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/topology` | Get current topology |
| GET | `/api/history/alerts?limit=50` | Get recent alerts from DB |
| GET | `/api/health` | Health check |
| WS | `/ws` | Real-time updates |

### Manual Intervention (Command Polling)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/control/block-ip` | Queue a block command |
| GET | `/api/control/pending` | Poll next command (for Controller) |
| GET | `/api/control/queue` | View pending commands |

---

##  Data Contracts (JSON Schemas)

### Topology
```json
{
  "type": "topology",
  "switches": [{"id": "s1", "dpid": 1, "role": "core"}],
  "hosts": [{"id": "h1", "ip": "10.0.0.1", "switch": "s3"}],
  "links": [{"from": "s1", "to": "s2", "bw_mbps": 100}]
}
```

### Security Alert
```json
{
  "type": "security_alert",
  "timestamp": 1712345678.9,
  "attacker_ip": "10.0.0.3",
  "target_ip": "10.0.0.5",
  "severity": "CRITICAL",
  "action_taken": "BLOCK"
}
```

### Block IP Command
```json
{
  "ip": "10.0.0.5",
  "duration": 60
}
```

---

##  WebSocket Messages

Frontend connects to `ws://localhost:8000/ws` and receives:

| Type | Description |
|------|-------------|
| `topology_update` | Network topology changed |
| `stats_update` | Live traffic statistics |
| `security_alert` | Attack detected |
| `command_queued` | Block command pending |

---

##  Command Polling (Manual Intervention)

The Controller polls the Backend every ~1 second for commands:

```python
# In Controller's monitor loop:
command = self.backend.fetch_pending_commands()
if command and command["command"] == "block":
    self._block_ip(command["ip"], command["duration"])
```

**Flow:**
1. User clicks "Block IP" on Frontend
2. Frontend → `POST /api/control/block-ip {"ip": "10.0.0.5"}`
3. Backend adds to queue
4. Controller → `GET /api/control/pending`
5. Controller executes block rule

---

##  Testing

### Test Backend Endpoints
```bash
# Health check
curl http://localhost:8000/api/health

# Add block command
curl -X POST http://localhost:8000/api/control/block-ip \
  -H "Content-Type: application/json" \
  -d '{"ip": "10.0.0.5"}'

# Poll command
curl http://localhost:8000/api/control/pending
```

### Test with Controller Client
```python
from backend_client import BackendClient

client = BackendClient()
client.connect()
client.send_topology({"switches": [...], "hosts": [...], "links": [...]})
client.send_alert({"attacker_ip": "10.0.0.5", "target_ip": "10.0.0.1", ...})
```

---

##  Configuration

Edit `controller/config.py`:
```python
BACKEND_HOST = "localhost"
BACKEND_PORT = 8000
BACKEND_ENABLED = True
```

---

##  Notes for Other Members

### For Frontend Team (Member 5)
- Connect to WebSocket at `ws://localhost:8000/ws`
- On connect, you'll receive current topology
- Listen for `security_alert` events to trigger "red pulse" effect
- Use `POST /api/control/block-ip` for manual intervention

### For Controller Team (Member 1)
- `BackendClient` is already integrated
- Uses threading - won't block network operations
- Handles reconnection automatically

### For Security AI Team (Member 2)
- Alerts sent via `controller.backend.send_alert()`
- Check `backend/database.py` for Alert schema

---

##  License

Part of the Sentinet SDN Project.

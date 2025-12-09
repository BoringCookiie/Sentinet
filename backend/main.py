"""
Sentinet Backend API
====================
FastAPI server for bridging the SDN Controller and React Frontend.

This module provides:
- REST endpoints for receiving data from Controller
- REST endpoints for serving data to Frontend
- WebSocket endpoint for real-time updates to Frontend

Architecture:
    Controller ──POST──> Backend ──WebSocket──> Frontend
                         │
                         └──SQLite (Alerts only)

The "Pulse" Strategy:
    - Stats are transient (pass-through, no DB storage)
    - Alerts are persisted AND broadcast for "sticky" visualization
    - Topology is cached in-memory for instant retrieval
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
import json
import logging
import time

# Local imports
from database import init_db, get_db, create_alert, get_recent_alerts, Alert

# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# =============================================================================
# FASTAPI APPLICATION
# =============================================================================

app = FastAPI(
    title="Sentinet Backend API",
    description="Backend integrator for Sentinet SDN - Connects Controller to Frontend",
    version="1.0.0",
    docs_url="/docs",  # Swagger UI
    redoc_url="/redoc"  # ReDoc UI
)

# =============================================================================
# CORS MIDDLEWARE (Allow Frontend access)
# =============================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for localhost development
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

# =============================================================================
# PYDANTIC MODELS (Data Contracts)
# =============================================================================

class SwitchModel(BaseModel):
    """Switch node in the topology."""
    id: str = Field(..., example="s1")
    dpid: int = Field(..., example=1)
    role: str = Field(..., example="core")


class HostModel(BaseModel):
    """Host node in the topology."""
    id: str = Field(..., example="h1")
    ip: str = Field(..., example="10.0.0.1")
    switch: str = Field(..., example="s3")
    mac: Optional[str] = Field(None, example="00:00:00:00:00:01")


class LinkModel(BaseModel):
    """Link between nodes in the topology."""
    # Using 'from_node' and 'to_node' because 'from' is a Python keyword
    from_node: str = Field(..., alias="from", example="s1")
    to_node: str = Field(..., alias="to", example="s2")
    bw_mbps: Optional[int] = Field(100, example=100)
    delay_ms: Optional[int] = Field(1, example=1)
    
    class Config:
        populate_by_name = True


class TopologyModel(BaseModel):
    """Complete network topology."""
    type: str = Field(default="topology")
    switches: List[SwitchModel]
    hosts: List[HostModel]
    links: List[LinkModel]


class AlertModel(BaseModel):
    """Security alert from the Controller."""
    type: str = Field(default="security_alert")
    timestamp: float = Field(..., example=1712345678.9)
    attacker_ip: str = Field(..., example="10.0.0.3")
    target_ip: str = Field(..., example="10.0.0.5")
    severity: str = Field(..., example="CRITICAL")
    action_taken: str = Field(..., example="BLOCK")


class StatsModel(BaseModel):
    """Traffic statistics from the Controller."""
    type: str = Field(default="stats_update")
    timestamp: Optional[float] = Field(default_factory=time.time)
    data: Dict[str, Any] = Field(..., description="Switch flow statistics")


class AlertResponse(BaseModel):
    """Response model for alert endpoints."""
    id: int
    timestamp: float
    attacker_ip: str
    target_ip: str
    severity: str
    action_taken: str
    created_at: Optional[str] = None


# =============================================================================
# IN-MEMORY STATE
# =============================================================================

# Current network topology (updated by Controller)
CURRENT_TOPOLOGY: Dict[str, Any] = {
    "type": "topology",
    "switches": [],
    "hosts": [],
    "links": []
}

# Command queue for manual intervention (Frontend -> Controller)
# Commands are added by Frontend and polled by Controller
PENDING_COMMANDS: List[Dict[str, Any]] = []


# =============================================================================
# CONTROL MODELS (Manual Intervention)
# =============================================================================

class BlockIPRequest(BaseModel):
    """Request to block an IP address."""
    ip: str = Field(..., example="10.0.0.5", description="IP address to block")
    duration: Optional[int] = Field(60, example=60, description="Block duration in seconds")


class PendingCommandResponse(BaseModel):
    """Response containing a pending command for the Controller."""
    command: Optional[str] = Field(None, description="Command type: 'block' or None")
    ip: Optional[str] = Field(None, description="Target IP address")
    duration: Optional[int] = Field(None, description="Duration in seconds")


# =============================================================================
# WEBSOCKET CONNECTION MANAGER
# =============================================================================

class ConnectionManager:
    """
    Manages active WebSocket connections to Frontend clients.
    
    Features:
    - Track all connected clients
    - Broadcast messages to all clients simultaneously
    - Handle connection/disconnection gracefully
    
    Usage:
        manager = ConnectionManager()
        
        # In WebSocket endpoint:
        await manager.connect(websocket)
        await manager.broadcast({"type": "alert", "data": {...}})
    """
    
    def __init__(self):
        # List of active WebSocket connections
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        """
        Accept a new WebSocket connection.
        
        Args:
            websocket: The WebSocket connection to accept
        """
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"[WS] Client connected. Total clients: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        """
        Remove a WebSocket connection from the active list.
        
        Args:
            websocket: The WebSocket connection to remove
        """
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"[WS] Client disconnected. Total clients: {len(self.active_connections)}")
    
    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """
        Send a message to a specific client.
        
        Args:
            message: Dictionary to send as JSON
            websocket: Target WebSocket connection
        """
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"[WS] Failed to send personal message: {e}")
    
    async def broadcast(self, message: dict):
        """
        Broadcast a message to ALL connected Frontend clients.
        
        This is the core method for the "Pulse" technique:
        - Stats updates go to all clients in real-time
        - Security alerts go to all clients immediately
        
        Args:
            message: Dictionary to broadcast as JSON
        """
        disconnected = []
        
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"[WS] Broadcast failed for a client: {e}")
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)
        
        if self.active_connections:
            logger.debug(f"[WS] Broadcast sent to {len(self.active_connections)} clients")


# Global connection manager instance
manager = ConnectionManager()


# =============================================================================
# STARTUP EVENT
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize database on application startup."""
    logger.info("[STARTUP] Initializing Sentinet Backend...")
    init_db()
    logger.info("[STARTUP] Backend ready!")


# =============================================================================
# REST ENDPOINTS - RECEIVERS (Called by Controller)
# =============================================================================

@app.post("/api/topology", summary="Receive topology from Controller")
async def receive_topology(topology: TopologyModel):
    """
    Receive and store the network topology from the Controller.
    
    Called by: Controller on startup or topology change
    Action: Store in-memory for instant retrieval by Frontend
    
    Args:
        topology: Full network topology JSON
    
    Returns:
        dict: Confirmation message
    """
    global CURRENT_TOPOLOGY
    
    # Convert Pydantic model to dict for storage
    CURRENT_TOPOLOGY = topology.model_dump(by_alias=True)
    
    logger.info(f"[TOPOLOGY] Received: {len(topology.switches)} switches, "
                f"{len(topology.hosts)} hosts, {len(topology.links)} links")
    
    # Broadcast topology update to all connected Frontend clients
    await manager.broadcast({
        "type": "topology_update",
        "data": CURRENT_TOPOLOGY
    })
    
    return {"status": "success", "message": "Topology stored and broadcast"}


@app.post("/api/stats", summary="Receive traffic stats from Controller")
async def receive_stats(stats: StatsModel):
    """
    Receive traffic statistics from the Controller.
    
    Called by: Controller every POLL_INTERVAL seconds
    Action: Immediately broadcast to Frontend (no DB storage)
    
    Note: Stats are transient - we don't persist them to save I/O.
    The Frontend displays real-time metrics only.
    
    Args:
        stats: Traffic statistics JSON
    
    Returns:
        dict: Confirmation message
    """
    # Broadcast stats to all connected Frontend clients
    await manager.broadcast({
        "type": "stats_update",
        "timestamp": stats.timestamp or time.time(),
        "data": stats.data
    })
    
    logger.debug(f"[STATS] Broadcast stats update")
    
    return {"status": "success", "message": "Stats broadcast to clients"}


@app.post("/api/alert", summary="Receive security alert from Controller")
async def receive_alert(alert: AlertModel, db: Session = Depends(get_db)):
    """
    Receive a security alert from the Controller.
    
    Called by: Controller when Sentinel AI detects an attack
    Action: 
        1. Save to SQLite database (persistence)
        2. Immediately broadcast to Frontend (real-time notification)
    
    This is critical for the "Pulse" technique:
    - The alert is broadcast immediately
    - Frontend holds the "red state" for visual persistence
    - DB storage enables historical analysis
    
    Args:
        alert: Security alert JSON
        db: Database session (injected)
    
    Returns:
        dict: Created alert with database ID
    """
    # Save to database
    db_alert = create_alert(db, {
        "timestamp": alert.timestamp,
        "attacker_ip": alert.attacker_ip,
        "target_ip": alert.target_ip,
        "severity": alert.severity,
        "action_taken": alert.action_taken
    })
    
    logger.warning(f"[ALERT] 🚨 {alert.severity}: {alert.attacker_ip} -> {alert.target_ip} "
                   f"| Action: {alert.action_taken}")
    
    # Broadcast alert to all connected Frontend clients
    await manager.broadcast({
        "type": "security_alert",
        "timestamp": alert.timestamp,
        "data": {
            "id": db_alert.id,
            "attacker_ip": alert.attacker_ip,
            "target_ip": alert.target_ip,
            "severity": alert.severity,
            "action_taken": alert.action_taken
        }
    })
    
    return {
        "status": "success",
        "message": "Alert saved and broadcast",
        "alert_id": db_alert.id
    }


# =============================================================================
# REST ENDPOINTS - PROVIDERS (Called by Frontend)
# =============================================================================

@app.get("/api/topology", summary="Get current network topology")
async def get_topology():
    """
    Get the current network topology for Frontend visualization.
    
    Called by: Frontend on initial load or refresh
    
    Returns:
        dict: Current topology with switches, hosts, and links
    """
    return CURRENT_TOPOLOGY


@app.get("/api/history/alerts", response_model=List[AlertResponse], 
         summary="Get recent security alerts")
async def get_alert_history(limit: int = 50, db: Session = Depends(get_db)):
    """
    Get historical security alerts from the database.
    
    Called by: Frontend to populate the alerts history panel
    
    Args:
        limit: Maximum number of alerts to return (default: 50)
        db: Database session (injected)
    
    Returns:
        list: Recent alerts in descending order (newest first)
    """
    alerts = get_recent_alerts(db, limit=limit)
    return [alert.to_dict() for alert in alerts]


@app.get("/api/health", summary="Health check endpoint")
async def health_check():
    """
    Health check endpoint for monitoring.
    
    Returns:
        dict: Server status and connection count
    """
    return {
        "status": "healthy",
        "connected_clients": len(manager.active_connections),
        "timestamp": time.time()
    }


# =============================================================================
# REST ENDPOINTS - CONTROL (Manual Intervention)
# =============================================================================

@app.post("/api/control/block-ip", summary="Request to block an IP address")
async def request_block_ip(request: BlockIPRequest):
    """
    Add a block command to the pending queue.
    
    Called by: Frontend when user clicks "Block IP" button
    Action: Add command to queue, Controller will pick it up
    
    Flow:
        Frontend -> POST /api/control/block-ip
        Backend adds to PENDING_COMMANDS queue
        Controller polls GET /api/control/pending
        Controller executes the block
    
    Args:
        request: BlockIPRequest with IP and optional duration
    
    Returns:
        dict: Confirmation message
    """
    command = {
        "command": "block",
        "ip": request.ip,
        "duration": request.duration or 60,
        "timestamp": time.time()
    }
    
    PENDING_COMMANDS.append(command)
    
    logger.info(f"[CONTROL] 🎯 Block command queued: {request.ip} for {request.duration}s")
    
    # Also broadcast to Frontend for immediate visual feedback
    await manager.broadcast({
        "type": "command_queued",
        "data": {
            "command": "block",
            "ip": request.ip,
            "status": "pending"
        }
    })
    
    return {
        "status": "success",
        "message": f"Block command for {request.ip} queued",
        "queue_size": len(PENDING_COMMANDS)
    }


@app.get("/api/control/pending", response_model=PendingCommandResponse,
         summary="Get next pending command (polled by Controller)")
async def get_pending_command():
    """
    Get and remove the next pending command from the queue.
    
    Called by: Controller every ~1 second (polling)
    Action: Return first command and remove from queue (FIFO)
    
    This implements the "mailbox" pattern:
    - Frontend puts commands in the mailbox
    - Controller checks the mailbox periodically
    - Commands are processed in order
    
    Returns:
        PendingCommandResponse: Next command or {command: None}
    """
    if PENDING_COMMANDS:
        command = PENDING_COMMANDS.pop(0)  # FIFO: Get first, remove it
        
        logger.info(f"[CONTROL] 📤 Command dispatched to Controller: {command['command']} {command['ip']}")
        
        return {
            "command": command["command"],
            "ip": command["ip"],
            "duration": command.get("duration", 60)
        }
    
    # No pending commands
    return {"command": None, "ip": None, "duration": None}


@app.get("/api/control/queue", summary="View pending commands queue")
async def view_command_queue():
    """
    View all pending commands without removing them.
    
    Called by: Frontend to show queue status
    
    Returns:
        dict: List of pending commands and queue size
    """
    return {
        "queue_size": len(PENDING_COMMANDS),
        "commands": PENDING_COMMANDS.copy()
    }


# =============================================================================
# WEBSOCKET ENDPOINT
# =============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time Frontend updates.
    
    Connection flow:
        1. Frontend connects to ws://localhost:8000/ws
        2. Backend accepts and tracks the connection
        3. Backend broadcasts updates (stats, alerts, topology)
        4. Frontend receives and renders in real-time
    
    Messages sent to Frontend:
        - {"type": "stats_update", "data": {...}}
        - {"type": "security_alert", "data": {...}}
        - {"type": "topology_update", "data": {...}}
    
    Args:
        websocket: The WebSocket connection
    """
    await manager.connect(websocket)
    
    # Send current topology immediately upon connection
    if CURRENT_TOPOLOGY["switches"]:
        await manager.send_personal_message({
            "type": "topology_update",
            "data": CURRENT_TOPOLOGY
        }, websocket)
        logger.info("[WS] Sent current topology to new client")
    
    try:
        while True:
            # Keep connection alive, listen for any client messages
            # (Frontend might send commands in the future)
            data = await websocket.receive_text()
            
            # Handle client messages if needed
            try:
                message = json.loads(data)
                logger.info(f"[WS] Received from client: {message.get('type', 'unknown')}")
                
                # Future: Handle client commands here
                # e.g., subscribe to specific switches, request topology refresh
                
            except json.JSONDecodeError:
                logger.warning(f"[WS] Invalid JSON from client: {data[:100]}")
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("[WS] Client disconnected gracefully")
    except Exception as e:
        manager.disconnect(websocket)
        logger.error(f"[WS] Connection error: {e}")


# =============================================================================
# MAIN (for direct execution)
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    print("=" * 60)
    print("  SENTINET BACKEND SERVER")
    print("=" * 60)
    print("\n  Endpoints:")
    print("    - REST API:    http://localhost:8000")
    print("    - WebSocket:   ws://localhost:8000/ws")
    print("    - API Docs:    http://localhost:8000/docs")
    print("\n  Controller should POST to:")
    print("    - POST /api/topology")
    print("    - POST /api/stats")
    print("    - POST /api/alert")
    print("    - GET  /api/control/pending  (polling)")
    print("\n  Frontend should connect to:")
    print("    - GET  /api/topology")
    print("    - GET  /api/history/alerts")
    print("    - POST /api/control/block-ip")
    print("    - WS   /ws")
    print("=" * 60)
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Enable auto-reload during development
        log_level="info"
    )

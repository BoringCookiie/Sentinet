"""
Sentinet Pydantic Models
========================
Data validation models for the Backend API.

These models define the JSON schemas for data exchanged between:
- Controller -> Backend (topology, stats, alerts)
- Backend -> Frontend (via REST and WebSocket)
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


# =============================================================================
# TOPOLOGY MODELS
# =============================================================================

class SwitchModel(BaseModel):
    """
    Switch node in the network topology.
    
    Attributes:
        id: Unique switch identifier (e.g., "s1")
        dpid: Datapath ID used by OpenFlow
        role: Switch role in the network hierarchy
    """
    id: str = Field(..., example="s1", description="Switch identifier")
    dpid: int = Field(..., example=1, description="Datapath ID")
    role: str = Field(..., example="core", description="Switch role: core, distribution, access")


class HostModel(BaseModel):
    """
    Host node in the network topology.
    
    Attributes:
        id: Unique host identifier (e.g., "h1")
        ip: Host IP address
        switch: ID of the switch this host connects to
        mac: Optional MAC address
    """
    id: str = Field(..., example="h1", description="Host identifier")
    ip: str = Field(..., example="10.0.0.1", description="Host IP address")
    switch: str = Field(..., example="s3", description="Connected switch ID")
    mac: Optional[str] = Field(None, example="00:00:00:00:00:01", description="MAC address")


class LinkModel(BaseModel):
    """
    Link between network nodes.
    
    Note: Uses alias for 'from' field since it's a Python keyword.
    
    Attributes:
        from_node: Source node ID
        to_node: Destination node ID  
        bw_mbps: Bandwidth in Mbps
        delay_ms: Delay in milliseconds
    """
    from_node: str = Field(..., alias="from", example="s1", description="Source node")
    to_node: str = Field(..., alias="to", example="s2", description="Destination node")
    bw_mbps: Optional[int] = Field(100, example=100, description="Bandwidth (Mbps)")
    delay_ms: Optional[int] = Field(1, example=1, description="Link delay (ms)")
    
    class Config:
        populate_by_name = True  # Allow both "from" and "from_node"


class TopologyModel(BaseModel):
    """
    Complete network topology structure.
    
    This represents the entire network graph with all nodes and links.
    Sent by Controller on startup, used by Frontend for visualization.
    """
    type: str = Field(default="topology", description="Message type identifier")
    switches: List[SwitchModel] = Field(default=[], description="List of switches")
    hosts: List[HostModel] = Field(default=[], description="List of hosts")
    links: List[LinkModel] = Field(default=[], description="List of links")


# =============================================================================
# TRAFFIC STATISTICS MODELS
# =============================================================================

class FlowStatModel(BaseModel):
    """
    Statistics for a single flow (traffic between two hosts).
    
    Attributes:
        src_mac: Source MAC address
        dst_mac: Destination MAC address
        packet_count: Total packets in this flow
        byte_count: Total bytes in this flow
        pps: Packets per second (rate)
        bps: Bits per second (rate)
        avg_pkt_size: Average packet size in bytes
    """
    src_mac: str = Field(..., description="Source MAC address")
    dst_mac: str = Field(..., description="Destination MAC address")
    packet_count: int = Field(default=0, description="Total packets")
    byte_count: int = Field(default=0, description="Total bytes")
    duration_sec: float = Field(default=0.0, description="Flow duration")
    pps: float = Field(default=0.0, description="Packets per second")
    bps: float = Field(default=0.0, description="Bits per second")
    avg_pkt_size: float = Field(default=0.0, description="Average packet size")


class StatsUpdateModel(BaseModel):
    """
    Traffic statistics update from Controller.
    
    Contains flow statistics for a specific switch.
    Broadcast to Frontend but NOT persisted to database.
    """
    type: str = Field(default="stats_update", description="Message type")
    timestamp: float = Field(..., description="Unix timestamp")
    data: Dict[str, Any] = Field(..., description="Statistics payload")


# =============================================================================
# SECURITY ALERT MODELS
# =============================================================================

class AlertModel(BaseModel):
    """
    Security alert from the Sentinel AI.
    
    Generated when the AI detects abnormal traffic patterns
    (e.g., DDoS attack, port scan, anomaly).
    
    Attributes:
        type: Message type (always "security_alert")
        timestamp: When the alert was generated
        attacker_ip: IP address of the attacking host
        target_ip: IP address of the victim host
        severity: Alert severity level
        action_taken: Mitigation action by Controller
    """
    type: str = Field(default="security_alert", description="Message type")
    timestamp: float = Field(..., example=1712345678.9, description="Unix timestamp")
    attacker_ip: str = Field(..., example="10.0.0.3", description="Attacker IP")
    target_ip: str = Field(..., example="10.0.0.5", description="Target IP")
    severity: str = Field(
        default="WARNING",
        example="CRITICAL",
        description="Severity: INFO, WARNING, CRITICAL"
    )
    action_taken: str = Field(
        default="ALERT_ONLY",
        example="BLOCK",
        description="Action: BLOCK, RATE_LIMIT, ALERT_ONLY"
    )


class AlertResponseModel(BaseModel):
    """
    Alert record returned from database queries.
    
    Includes the database ID and creation timestamp.
    """
    id: int = Field(..., description="Database record ID")
    timestamp: float = Field(..., description="Original alert timestamp")
    attacker_ip: str = Field(..., description="Attacker IP address")
    target_ip: str = Field(..., description="Target IP address")
    severity: str = Field(..., description="Alert severity")
    action_taken: str = Field(..., description="Mitigation action")
    created_at: Optional[str] = Field(None, description="Database insertion time (ISO format)")


# =============================================================================
# WEBSOCKET MESSAGE MODELS
# =============================================================================

class WebSocketMessage(BaseModel):
    """
    Generic WebSocket message structure.
    
    All messages sent over WebSocket follow this structure.
    The 'type' field indicates how to interpret the 'data' field.
    
    Types:
        - "topology_update": data = TopologyModel
        - "stats_update": data = flow statistics
        - "security_alert": data = AlertModel
    """
    type: str = Field(..., description="Message type identifier")
    timestamp: Optional[float] = Field(None, description="Unix timestamp")
    data: Dict[str, Any] = Field(default={}, description="Message payload")


# =============================================================================
# API RESPONSE MODELS
# =============================================================================

class SuccessResponse(BaseModel):
    """Standard success response."""
    status: str = Field(default="success")
    message: str = Field(..., description="Response message")


class AlertCreatedResponse(SuccessResponse):
    """Response when a new alert is created."""
    alert_id: int = Field(..., description="ID of created alert")


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(default="healthy")
    connected_clients: int = Field(..., description="Active WebSocket connections")
    timestamp: float = Field(..., description="Current server time")

"""
Sentinet Backend Client
=======================
WebSocket client for communication with the Backend API.
Sends topology, flow stats, and security alerts.

The Backend team should run a WebSocket server at the configured address.
"""

import json
import logging
import threading
import time
from queue import Queue, Empty

# Try to import websocket library
try:
    import websocket
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False
    logging.warning("websocket-client not installed. Backend connection disabled.")

from config import BACKEND_HOST, BACKEND_PORT, BACKEND_ENABLED


class BackendClient:
    """
    WebSocket client for Backend communication.
    
    Features:
    - Async message queue (non-blocking sends)
    - Auto-reconnection
    - Graceful fallback when backend unavailable
    
    Usage:
        client = BackendClient()
        client.connect()
        client.send_topology(topology_dict)
        client.send_stats(stats_dict)
        client.send_alert(alert_dict)
    """
    
    def __init__(self, host: str = None, port: int = None):
        self.host = host or BACKEND_HOST
        self.port = port or BACKEND_PORT
        self.url = f"ws://{self.host}:{self.port}"
        
        self.ws = None
        self.connected = False
        self.enabled = BACKEND_ENABLED and WEBSOCKET_AVAILABLE
        
        # Message queue for async sending
        self.message_queue = Queue()
        self.sender_thread = None
        self.running = False
    
    def connect(self):
        """Establish WebSocket connection to Backend."""
        if not self.enabled:
            logging.info("[BACKEND] Backend connection disabled in config")
            return False
        
        try:
            logging.info(f"[BACKEND] Connecting to {self.url}...")
            self.ws = websocket.create_connection(self.url, timeout=5)
            self.connected = True
            self.running = True
            
            # Start sender thread
            self.sender_thread = threading.Thread(target=self._sender_loop, daemon=True)
            self.sender_thread.start()
            
            logging.info(f"[BACKEND] Connected to {self.url}")
            return True
            
        except Exception as e:
            logging.warning(f"[BACKEND] Connection failed: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Close WebSocket connection."""
        self.running = False
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
        self.connected = False
        logging.info("[BACKEND] Disconnected")
    
    def _sender_loop(self):
        """Background thread that sends queued messages."""
        while self.running:
            try:
                # Wait for message with timeout
                message = self.message_queue.get(timeout=1)
                self._send_raw(message)
            except Empty:
                continue
            except Exception as e:
                logging.error(f"[BACKEND] Sender error: {e}")
    
    def _send_raw(self, message: str):
        """Send raw message string to Backend."""
        if not self.connected or not self.ws:
            return False
        
        try:
            self.ws.send(message)
            return True
        except Exception as e:
            logging.error(f"[BACKEND] Send failed: {e}")
            self.connected = False
            # Attempt reconnection
            self._try_reconnect()
            return False
    
    def _try_reconnect(self):
        """Attempt to reconnect after connection loss."""
        if not self.enabled:
            return
            
        logging.info("[BACKEND] Attempting reconnection...")
        time.sleep(2)  # Wait before retry
        self.connect()
    
    def _queue_message(self, message_dict: dict):
        """Add message to send queue."""
        if self.enabled:
            self.message_queue.put(json.dumps(message_dict))
    
    # =========================================================================
    # PUBLIC API - Called by Controller
    # =========================================================================
    
    def send_topology(self, topology: dict):
        """
        Send network topology on controller boot.
        
        Args:
            topology: Topology dict from config.py
        """
        message = {
            "type": "topology",
            "timestamp": time.time(),
            "data": topology
        }
        self._queue_message(message)
        logging.info("[BACKEND] Topology queued for sending")
    
    def send_stats(self, stats: dict):
        """
        Send flow statistics update.
        
        Args:
            stats: Dictionary containing switch flow stats
        """
        message = {
            "type": "stats_update",
            "timestamp": time.time(),
            "data": stats
        }
        self._queue_message(message)
    
    def send_alert(self, alert: dict):
        """
        Send security alert when attack detected.
        
        Args:
            alert: Alert information dict
        """
        message = {
            "type": "security_alert",
            "timestamp": time.time(),
            "data": alert
        }
        self._queue_message(message)
        logging.warning(f"[BACKEND] ALERT queued: {alert}")
    
    def send_switch_event(self, event_type: str, dpid: int):
        """
        Send switch connect/disconnect event.
        
        Args:
            event_type: "connected" or "disconnected"
            dpid: Switch datapath ID
        """
        message = {
            "type": "switch_event",
            "timestamp": time.time(),
            "event": event_type,
            "dpid": dpid
        }
        self._queue_message(message)
        logging.info(f"[BACKEND] Switch event queued: {event_type} dpid={dpid}")
    
    def get_status(self) -> dict:
        """Return connection status for debugging."""
        return {
            "url": self.url,
            "enabled": self.enabled,
            "connected": self.connected,
            "queue_size": self.message_queue.qsize()
        }


# =============================================================================
# MOCK BACKEND FOR TESTING
# =============================================================================

class MockBackendClient(BackendClient):
    """
    Mock backend client for testing without actual WebSocket server.
    Logs all messages to console instead of sending.
    """
    
    def __init__(self):
        super().__init__()
        self.enabled = True  # Always enabled
        self.connected = True  # Pretend connected
        self.messages = []  # Store messages for inspection
    
    def connect(self):
        logging.info("[MOCK-BACKEND] Mock connection established")
        return True
    
    def _send_raw(self, message: str):
        parsed = json.loads(message)
        self.messages.append(parsed)
        logging.info(f"[MOCK-BACKEND] Would send: {parsed['type']}")
        return True
    
    def _queue_message(self, message_dict: dict):
        self._send_raw(json.dumps(message_dict))

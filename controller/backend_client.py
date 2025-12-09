"""
Sentinet Backend Client (REST API Version)
==========================================
Non-blocking HTTP client for communication with the Backend API.
Sends topology, flow stats, and security alerts via REST endpoints.

Key Design Principle: NON-BLOCKING
    The Ryu Controller processes thousands of packets per second.
    If the Backend API is slow, the Controller MUST NOT freeze.
    
    Solution: Every HTTP request runs in a separate thread.
    The Controller's main event loop is never blocked.

Usage in Controller:
    from backend_client import BackendClient
    
    client = BackendClient()
    client.send_topology(topology_dict)
    client.send_stats(stats_dict)
    client.send_alert(alert_dict)
"""

import json
import logging
import threading
import time
from queue import Queue, Empty
from typing import Optional, Dict, Any

# Try to import requests library
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    logging.warning("requests library not installed. Backend connection disabled.")

# Import configuration
try:
    from config import BACKEND_HOST, BACKEND_PORT, BACKEND_ENABLED
except ImportError:
    # Fallback defaults if config not available
    BACKEND_HOST = "localhost"
    BACKEND_PORT = 8000
    BACKEND_ENABLED = True


# =============================================================================
# CONFIGURATION
# =============================================================================

# Backend API base URL (FastAPI server)
DEFAULT_BACKEND_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}"

# Request timeout in seconds (don't wait forever)
REQUEST_TIMEOUT = 5

# Maximum queue size (drop old messages if backend is too slow)
MAX_QUEUE_SIZE = 100


# =============================================================================
# BACKEND CLIENT CLASS
# =============================================================================

class BackendClient:
    """
    Non-blocking HTTP client for Backend REST API communication.
    
    Features:
    - Async message queue (non-blocking sends)
    - Thread-per-request for true async behavior
    - Automatic retry on failure
    - Graceful fallback when backend unavailable
    
    API Endpoints:
        POST /api/topology  - Send network topology
        POST /api/stats     - Send traffic statistics
        POST /api/alert     - Send security alert
    
    Usage:
        client = BackendClient()
        client.send_topology(topology_dict)
        client.send_stats(stats_dict)  
        client.send_alert(alert_dict)
    """
    
    def __init__(self, base_url: str = None, enabled: bool = None):
        """
        Initialize the Backend client.
        
        Args:
            base_url: Backend API URL (default: from config)
            enabled: Whether to enable backend communication (default: from config)
        """
        self.base_url = base_url or DEFAULT_BACKEND_URL
        self.enabled = enabled if enabled is not None else BACKEND_ENABLED
        self.enabled = self.enabled and REQUESTS_AVAILABLE
        
        # Track backend availability
        self.backend_available = True
        self.last_error_time = 0
        self.error_backoff = 5  # Seconds to wait before retry after error
        
        # Statistics for monitoring
        self.stats = {
            "topology_sent": 0,
            "stats_sent": 0,
            "alerts_sent": 0,
            "errors": 0
        }
        
        if self.enabled:
            logging.info(f"[BACKEND] Client initialized: {self.base_url}")
        else:
            logging.info("[BACKEND] Client disabled (config or missing requests lib)")
    
    # =========================================================================
    # INTERNAL: Thread-based async HTTP
    # =========================================================================
    
    def _post_async(self, endpoint: str, data: dict, message_type: str):
        """
        Send HTTP POST request in a separate thread (non-blocking).
        
        This is the core method that ensures the Controller never blocks.
        
        Args:
            endpoint: API endpoint (e.g., "/api/alert")
            data: Dictionary to send as JSON body
            message_type: Type of message for logging/stats
        """
        if not self.enabled:
            return
        
        # Check if we should skip due to recent errors (backoff)
        if not self.backend_available:
            if time.time() - self.last_error_time < self.error_backoff:
                return  # Still in backoff period
            else:
                self.backend_available = True  # Try again
        
        # Spawn a new thread for the HTTP request
        thread = threading.Thread(
            target=self._post_sync,
            args=(endpoint, data, message_type),
            daemon=True  # Thread dies when main program exits
        )
        thread.start()
    
    def _post_sync(self, endpoint: str, data: dict, message_type: str):
        """
        Synchronous HTTP POST (runs in separate thread).
        
        Args:
            endpoint: API endpoint
            data: JSON body
            message_type: For logging
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = requests.post(
                url,
                json=data,
                timeout=REQUEST_TIMEOUT,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                logging.debug(f"[BACKEND] {message_type} sent successfully")
                self._increment_stat(message_type)
            else:
                logging.warning(f"[BACKEND] {message_type} failed: HTTP {response.status_code}")
                self.stats["errors"] += 1
                
        except requests.exceptions.ConnectionError:
            logging.warning(f"[BACKEND] Connection failed - Backend not available")
            self._handle_error()
            
        except requests.exceptions.Timeout:
            logging.warning(f"[BACKEND] Request timeout - Backend too slow")
            self._handle_error()
            
        except Exception as e:
            logging.error(f"[BACKEND] Unexpected error: {e}")
            self._handle_error()
    
    def _handle_error(self):
        """Handle backend communication error with backoff."""
        self.backend_available = False
        self.last_error_time = time.time()
        self.stats["errors"] += 1
    
    def _increment_stat(self, message_type: str):
        """Increment the appropriate stats counter."""
        if message_type == "topology":
            self.stats["topology_sent"] += 1
        elif message_type == "stats":
            self.stats["stats_sent"] += 1
        elif message_type == "alert":
            self.stats["alerts_sent"] += 1
    
    # =========================================================================
    # PUBLIC API - Called by Controller
    # =========================================================================
    
    def send_topology(self, topology: dict):
        """
        Send network topology to Backend.
        
        Called by: Controller on startup or when topology changes
        
        Args:
            topology: Topology dictionary with format:
                {
                    "type": "topology",
                    "switches": [{"id": "s1", "dpid": 1, "role": "core"}, ...],
                    "hosts": [{"id": "h1", "ip": "10.0.0.1", "switch": "s3"}, ...],
                    "links": [{"from": "s1", "to": "s2", "bw_mbps": 100}, ...]
                }
        """
        # Ensure type field is set
        data = {
            "type": "topology",
            **topology
        }
        
        self._post_async("/api/topology", data, "topology")
        logging.info("[BACKEND] Topology queued for sending")
    
    def send_stats(self, stats: dict):
        """
        Send traffic statistics to Backend.
        
        Called by: Controller every POLL_INTERVAL seconds
        
        Note: Stats are high-frequency updates. The Backend will
        immediately broadcast to Frontend without DB storage.
        
        Args:
            stats: Statistics dictionary with format:
                {
                    "dpid": 1,
                    "flows": [
                        {
                            "src_mac": "00:00:00:00:00:01",
                            "dst_mac": "00:00:00:00:00:02",
                            "pps": 1500.0,
                            "bps": 120000.0,
                            ...
                        },
                        ...
                    ]
                }
        """
        data = {
            "type": "stats_update",
            "timestamp": time.time(),
            "data": stats
        }
        
        self._post_async("/api/stats", data, "stats")
    
    def send_alert(self, alert: dict):
        """
        Send security alert to Backend.
        
        Called by: Controller when Sentinel AI detects an attack
        
        CRITICAL: Alerts are high-priority messages. They are:
        1. Saved to database for historical analysis
        2. Immediately broadcast to Frontend for the "Pulse" effect
        
        Args:
            alert: Alert dictionary with format:
                {
                    "timestamp": 1712345678.9,
                    "attacker_ip": "10.0.0.3",
                    "target_ip": "10.0.0.5",
                    "severity": "CRITICAL",
                    "action_taken": "BLOCK"
                }
        """
        # Map MAC addresses to IPs if available
        # The Controller might send MAC addresses, but Backend expects IPs
        data = {
            "type": "security_alert",
            "timestamp": alert.get("timestamp", time.time()),
            "attacker_ip": alert.get("attacker_ip", alert.get("attacker_mac", "unknown")),
            "target_ip": alert.get("target_ip", alert.get("target_mac", "unknown")),
            "severity": alert.get("severity", "WARNING"),
            "action_taken": alert.get("action_taken", "ALERT_ONLY")
        }
        
        self._post_async("/api/alert", data, "alert")
        logging.warning(f"[BACKEND] 🚨 ALERT queued: {data['severity']} - "
                       f"{data['attacker_ip']} -> {data['target_ip']}")
    
    def send_switch_event(self, event_type: str, dpid: int):
        """
        Send switch connect/disconnect event.
        
        Args:
            event_type: "connected" or "disconnected"
            dpid: Switch datapath ID
        """
        # For now, include switch events in stats updates
        # Could be extended to a dedicated endpoint if needed
        data = {
            "type": "stats_update",
            "timestamp": time.time(),
            "data": {
                "event": "switch_" + event_type,
                "dpid": dpid
            }
        }
        
        self._post_async("/api/stats", data, "stats")
        logging.info(f"[BACKEND] Switch event queued: {event_type} dpid={dpid}")
    
    # =========================================================================
    # STATUS & DEBUGGING
    # =========================================================================
    
    def connect(self) -> bool:
        """
        Test connection to Backend (for compatibility with old interface).
        
        Returns:
            bool: True if backend is reachable
        """
        if not self.enabled:
            logging.info("[BACKEND] Client disabled")
            return False
        
        try:
            response = requests.get(
                f"{self.base_url}/api/health",
                timeout=REQUEST_TIMEOUT
            )
            if response.status_code == 200:
                logging.info(f"[BACKEND] Connected to {self.base_url}")
                self.backend_available = True
                return True
            else:
                logging.warning(f"[BACKEND] Health check failed: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            logging.warning(f"[BACKEND] Connection test failed: {e}")
            self.backend_available = False
            return False
    
    def disconnect(self):
        """
        Cleanup method (for compatibility with old interface).
        
        No-op for REST client, but kept for interface compatibility.
        """
        logging.info("[BACKEND] Client shutdown")
    
    # =========================================================================
    # COMMAND POLLING - Manual Intervention from Frontend
    # =========================================================================
    
    def fetch_pending_commands(self) -> Optional[Dict[str, Any]]:
        """
        Poll the Backend for pending commands from the Frontend.
        
        This implements the "mailbox" pattern for manual intervention:
        - Frontend adds commands (e.g., "Block IP 10.0.0.5")
        - Controller polls this method every ~1 second
        - If a command exists, it's returned and removed from queue
        
        Called by: Controller's monitor loop (every 1 second)
        
        Returns:
            dict: Command dict with keys {command, ip, duration} or None
            
        Example return:
            {"command": "block", "ip": "10.0.0.5", "duration": 60}
            or None if no pending commands
        """
        if not self.enabled or not self.backend_available:
            return None
        
        try:
            response = requests.get(
                f"{self.base_url}/api/control/pending",
                timeout=REQUEST_TIMEOUT
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Check if there's an actual command
                if data.get("command"):
                    logging.info(f"[BACKEND] 📥 Received command: {data['command']} -> {data['ip']}")
                    return data
                
                # No pending command
                return None
            else:
                logging.warning(f"[BACKEND] Command poll failed: HTTP {response.status_code}")
                return None
                
        except requests.exceptions.ConnectionError:
            # Backend not available - don't spam logs, just return None
            self.backend_available = False
            self.last_error_time = time.time()
            return None
            
        except requests.exceptions.Timeout:
            # Timeout - backend too slow
            return None
            
        except Exception as e:
            logging.error(f"[BACKEND] Command poll error: {e}")
            return None
    
    def get_status(self) -> dict:
        """
        Get current client status for debugging.
        
        Returns:
            dict: Status information including stats and availability
        """
        return {
            "base_url": self.base_url,
            "enabled": self.enabled,
            "backend_available": self.backend_available,
            "stats": self.stats.copy()
        }


# =============================================================================
# MOCK CLIENT FOR TESTING
# =============================================================================

class MockBackendClient(BackendClient):
    """
    Mock backend client for testing without actual Backend server.
    
    Logs all messages to console instead of sending HTTP requests.
    Useful for development and testing the Controller independently.
    """
    
    def __init__(self):
        super().__init__(enabled=False)
        self.enabled = True  # Override to enable logging
        self.messages = []  # Store messages for inspection
    
    def _post_async(self, endpoint: str, data: dict, message_type: str):
        """Log instead of sending HTTP request."""
        self.messages.append({
            "endpoint": endpoint,
            "data": data,
            "type": message_type,
            "timestamp": time.time()
        })
        logging.info(f"[MOCK-BACKEND] Would POST to {endpoint}: {message_type}")
        self._increment_stat(message_type)
    
    def connect(self) -> bool:
        """Mock connection always succeeds."""
        logging.info("[MOCK-BACKEND] Mock connection established")
        return True
    
    def get_messages(self) -> list:
        """Get all captured messages for testing."""
        return self.messages.copy()
    
    def clear_messages(self):
        """Clear captured messages."""
        self.messages.clear()
    
    def fetch_pending_commands(self) -> Optional[Dict[str, Any]]:
        """Mock command polling - always returns None."""
        return None


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 60)
    print("  SENTINET BACKEND CLIENT TEST")
    print("=" * 60)
    
    # Test with real client
    client = BackendClient()
    
    print(f"\nClient Status: {client.get_status()}")
    
    # Test connection
    print("\nTesting connection...")
    connected = client.connect()
    print(f"Connected: {connected}")
    
    if connected:
        # Send test topology
        print("\nSending test topology...")
        client.send_topology({
            "switches": [{"id": "s1", "dpid": 1, "role": "core"}],
            "hosts": [{"id": "h1", "ip": "10.0.0.1", "switch": "s1"}],
            "links": []
        })
        
        # Send test stats
        print("Sending test stats...")
        client.send_stats({
            "dpid": 1,
            "flows": [
                {"src_mac": "00:00:00:00:00:01", "dst_mac": "00:00:00:00:00:02", "pps": 100}
            ]
        })
        
        # Send test alert
        print("Sending test alert...")
        client.send_alert({
            "timestamp": time.time(),
            "attacker_ip": "10.0.0.3",
            "target_ip": "10.0.0.5",
            "severity": "CRITICAL",
            "action_taken": "BLOCK"
        })
        
        # Wait for async sends to complete
        print("\nWaiting for async sends...")
        time.sleep(2)
        
        print(f"\nFinal Status: {client.get_status()}")
    else:
        print("\nBackend not available. Testing with mock client...")
        
        mock_client = MockBackendClient()
        mock_client.send_alert({
            "timestamp": time.time(),
            "attacker_ip": "10.0.0.3",
            "target_ip": "10.0.0.5",
            "severity": "CRITICAL",
            "action_taken": "BLOCK"
        })
        
        print(f"\nMock messages: {mock_client.get_messages()}")
    
    print("\n" + "=" * 60)
    print("  TEST COMPLETE")
    print("=" * 60)

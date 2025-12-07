"""
Sentinet AI Interface
=====================
Wrapper classes for AI models (Sentinel and Navigator).
Provides clean interfaces for the Controller to call.

The Security and Routing teams implement the actual models.
This module handles loading, calling, and graceful fallback.
"""

import os
import logging

# Try to import ML libraries (may not be installed)
try:
    import joblib
    import numpy as np
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    logging.warning("ML libraries not available. AI will use fallback mode.")

from config import (
    SENTINEL_ENABLED, NAVIGATOR_ENABLED,
    SENTINEL_MODEL_PATH, NAVIGATOR_MODEL_PATH,
    ATTACK_PPS_THRESHOLD, ATTACK_BPS_THRESHOLD
)


class SentinelAI:
    """
    Security AI - DDoS Detection using Isolation Forest
    
    Input: Flow statistics (pps, bps, avg_pkt_size)
    Output: True if attack detected, False if normal
    
    Usage:
        sentinel = SentinelAI()
        is_attack = sentinel.predict(pps=5000, bps=500000, avg_pkt_size=64)
    """
    
    def __init__(self):
        self.model = None
        self.enabled = SENTINEL_ENABLED and ML_AVAILABLE
        
        if self.enabled:
            self._load_model()
    
    def _load_model(self):
        """Load the trained Isolation Forest model."""
        try:
            if os.path.exists(SENTINEL_MODEL_PATH):
                self.model = joblib.load(SENTINEL_MODEL_PATH)
                logging.info(f"[SENTINEL] Model loaded from {SENTINEL_MODEL_PATH}")
            else:
                logging.warning(f"[SENTINEL] Model not found at {SENTINEL_MODEL_PATH}")
                self.enabled = False
        except Exception as e:
            logging.error(f"[SENTINEL] Failed to load model: {e}")
            self.enabled = False
    
    def predict(self, pps: float, bps: float, avg_pkt_size: float) -> bool:
        """
        Predict if the given flow statistics indicate an attack.
        
        Args:
            pps: Packets per second
            bps: Bytes per second
            avg_pkt_size: Average packet size in bytes
            
        Returns:
            True if attack detected, False otherwise
        """
        if self.enabled and self.model is not None:
            # Use trained model
            features = np.array([[pps, bps, avg_pkt_size]])
            prediction = self.model.predict(features)
            return prediction[0] == -1  # -1 = anomaly in sklearn
        else:
            # Fallback: Simple threshold-based detection
            return self._fallback_predict(pps, bps)
    
    def _fallback_predict(self, pps: float, bps: float) -> bool:
        """Simple threshold-based attack detection when AI is unavailable."""
        if pps > ATTACK_PPS_THRESHOLD:
            logging.warning(f"[SENTINEL-FALLBACK] High PPS detected: {pps}")
            return True
        if bps > ATTACK_BPS_THRESHOLD:
            logging.warning(f"[SENTINEL-FALLBACK] High BPS detected: {bps}")
            return True
        return False
    
    def get_status(self) -> dict:
        """Return status information for debugging."""
        return {
            "name": "Sentinel",
            "enabled": self.enabled,
            "model_loaded": self.model is not None,
            "mode": "AI" if self.enabled else "Threshold Fallback"
        }


class NavigatorAI:
    """
    Routing AI - Path Optimization using Q-Learning
    
    Input: Source MAC, Destination MAC, Network Graph
    Output: Optimal path as list of switch IDs
    
    Usage:
        navigator = NavigatorAI()
        path = navigator.get_path("00:00:00:00:00:01", "00:00:00:00:00:07", graph)
    """
    
    def __init__(self):
        self.model = None
        self.enabled = NAVIGATOR_ENABLED and ML_AVAILABLE
        
        if self.enabled:
            self._load_model()
    
    def _load_model(self):
        """Load the trained routing model."""
        try:
            if os.path.exists(NAVIGATOR_MODEL_PATH):
                self.model = joblib.load(NAVIGATOR_MODEL_PATH)
                logging.info(f"[NAVIGATOR] Model loaded from {NAVIGATOR_MODEL_PATH}")
            else:
                logging.warning(f"[NAVIGATOR] Model not found at {NAVIGATOR_MODEL_PATH}")
                self.enabled = False
        except Exception as e:
            logging.error(f"[NAVIGATOR] Failed to load model: {e}")
            self.enabled = False
    
    def get_path(self, src_mac: str, dst_mac: str, network_graph: dict) -> list:
        """
        Calculate optimal path from source to destination.
        
        Args:
            src_mac: Source MAC address
            dst_mac: Destination MAC address
            network_graph: Current network topology with link weights
            
        Returns:
            List of switch IDs representing the path, e.g., ["s3", "s2", "s1", "s5"]
        """
        if self.enabled and self.model is not None:
            # Use trained model (implementation depends on routing team)
            return self._ai_path(src_mac, dst_mac, network_graph)
        else:
            # Fallback: Use simple shortest path (BFS)
            return self._fallback_path(src_mac, dst_mac, network_graph)
    
    def _ai_path(self, src_mac: str, dst_mac: str, network_graph: dict) -> list:
        """AI-based path calculation. Routing team implements this."""
        # Placeholder - routing team will implement Q-learning based selection
        return self._fallback_path(src_mac, dst_mac, network_graph)
    
    def _fallback_path(self, src_mac: str, dst_mac: str, network_graph: dict) -> list:
        """Simple BFS shortest path when AI is unavailable."""
        # For now, return empty - controller will use default flooding
        # Routing team can implement proper graph traversal here
        logging.debug(f"[NAVIGATOR-FALLBACK] Path request: {src_mac} -> {dst_mac}")
        return []
    
    def get_status(self) -> dict:
        """Return status information for debugging."""
        return {
            "name": "Navigator",
            "enabled": self.enabled,
            "model_loaded": self.model is not None,
            "mode": "AI" if self.enabled else "Default Flooding"
        }


# =============================================================================
# DATA PROVIDER FUNCTIONS
# =============================================================================
# These functions are called by the AI models to get required data.
# They are designed to be called from the controller context.

def prepare_sentinel_input(flow_stats: dict) -> tuple:
    """
    Prepare input data for Sentinel AI from raw flow statistics.
    
    Args:
        flow_stats: Dictionary containing flow information
        
    Returns:
        Tuple of (pps, bps, avg_pkt_size)
    """
    packet_count = flow_stats.get('packet_count', 0)
    byte_count = flow_stats.get('byte_count', 0)
    duration = flow_stats.get('duration_sec', 1)
    
    # Avoid division by zero
    if duration <= 0:
        duration = 0.001
    
    pps = packet_count / duration
    bps = byte_count / duration
    avg_pkt_size = byte_count / packet_count if packet_count > 0 else 0
    
    return (pps, bps, avg_pkt_size)


def prepare_navigator_input(mac_to_port: dict, topology: dict) -> dict:
    """
    Prepare network graph for Navigator AI.
    
    Args:
        mac_to_port: MAC address to port mapping from controller
        topology: Topology configuration from config.py
        
    Returns:
        Network graph dictionary suitable for path calculation
    """
    # Build adjacency list from topology
    graph = {}
    
    for link in topology.get('links', []):
        src = link['from']
        dst = link['to']
        weight = link.get('delay_ms', 1)
        
        if src not in graph:
            graph[src] = []
        if dst not in graph:
            graph[dst] = []
            
        graph[src].append({'node': dst, 'weight': weight})
        graph[dst].append({'node': src, 'weight': weight})
    
    return graph


def format_flow_for_ai(stat, dpid: int, timestamp: float) -> dict:
    """
    Format a single flow statistic for AI processing.
    
    Args:
        stat: OpenFlow flow stat object
        dpid: Switch datapath ID
        timestamp: Current timestamp
        
    Returns:
        Dictionary with all flow information
    """
    duration = stat.duration_sec + (stat.duration_nsec / 1e9)
    
    if duration > 0:
        pps = stat.packet_count / duration
        bps = stat.byte_count / duration
    else:
        pps = 0
        bps = 0
    
    avg_pkt_size = stat.byte_count / stat.packet_count if stat.packet_count > 0 else 0
    
    # Extract output port from instructions if available
    out_port = 0
    if hasattr(stat, 'instructions') and stat.instructions:
        for inst in stat.instructions:
            if hasattr(inst, 'actions'):
                for action in inst.actions:
                    if hasattr(action, 'port'):
                        out_port = action.port
                        break
    
    return {
        'timestamp': timestamp,
        'dpid': dpid,
        'src_mac': stat.match.get('eth_src', 'unknown'),
        'dst_mac': stat.match.get('eth_dst', 'unknown'),
        'in_port': stat.match.get('in_port', 0),
        'out_port': out_port,
        'packet_count': stat.packet_count,
        'byte_count': stat.byte_count,
        'duration_sec': duration,
        'pps': pps,
        'bps': bps,
        'avg_pkt_size': avg_pkt_size
    }

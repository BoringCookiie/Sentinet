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
    import pandas as pd
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    logging.warning("ML libraries not available. AI will use fallback mode.")

from config import (
    SENTINEL_ENABLED, NAVIGATOR_ENABLED,
    SENTINEL_MODEL_PATH, NAVIGATOR_MODEL_PATH,
    SENTINEL_CLASSIFIER_PATH, SENTINEL_SCALER_PATH,  # Add SENTINEL_SCALER_PATH
    ATTACK_PPS_THRESHOLD, ATTACK_BPS_THRESHOLD
)


class SentinelAI:
    """
    Security AI - DDoS Detection using Isolation Forest AND Random Forest Classifier.
    
    Input: Flow statistics (pps, bps, avg_pkt_size)
    Output: Dictionary with threat status and attack type.
    """
    
    def __init__(self):
        self.anomaly_model = None
        self.classifier_model = None
        self.scaler = None  # Add this
        self.enabled = SENTINEL_ENABLED and ML_AVAILABLE
        
        if self.enabled:
            self._load_models()
    
    def _load_models(self):
        """Load both Anomaly and Classifier models."""
        try:
            # Load Anomaly Detector
            if os.path.exists(SENTINEL_MODEL_PATH):
                self.anomaly_model = joblib.load(SENTINEL_MODEL_PATH)
                logging.info(f"[SENTINEL] Anomaly Model loaded from {SENTINEL_MODEL_PATH}")
            else:
                logging.warning(f"[SENTINEL] Anomaly Model not found at {SENTINEL_MODEL_PATH}")
                self.enabled = False

            # Load Classifier (Optional but recommended)
            if os.path.exists(SENTINEL_CLASSIFIER_PATH):
                self.classifier_model = joblib.load(SENTINEL_CLASSIFIER_PATH)
                logging.info(f"[SENTINEL] Classifier Model loaded from {SENTINEL_CLASSIFIER_PATH}")
            else:
                logging.warning(f"[SENTINEL] Classifier Model not found at {SENTINEL_CLASSIFIER_PATH}")
        
            # Load Scaler for Anomaly Model  # Add this block
            if os.path.exists(SENTINEL_SCALER_PATH):
                self.scaler = joblib.load(SENTINEL_SCALER_PATH)
                logging.info(f"[SENTINEL] Scaler loaded from {SENTINEL_SCALER_PATH}")
            else:
                logging.warning(f"[SENTINEL] Scaler not found at {SENTINEL_SCALER_PATH}")
                self.enabled = False
            
        except Exception as e:
            logging.error(f"[SENTINEL] Failed to load models: {e}")
            self.enabled = False
    
    def predict(self, pps: float, bps: float, avg_pkt_size: float) -> dict:
        """
        Predict if the given flow statistics indicate an attack.
        Uses both Anomaly Detection (Isolation Forest) and Classification (Random Forest).
        
        Logic: Alarm if EITHER model detects a threat.
        """
        if not self.enabled:
            # Fallback
            is_threat = self._fallback_predict(pps, bps)
            return {"is_threat": is_threat, "attack_type": "Fallback Threshold" if is_threat else "Normal"}

        try:
            features = pd.DataFrame([{'pps': pps, 'bps': bps, 'avg_pkt_size': avg_pkt_size}])
            
            # Scale features for anomaly detection
            if self.scaler:
                features_scaled = pd.DataFrame(self.scaler.transform(features), columns=features.columns)
            else:
                features_scaled = features
            
            # 1. Anomaly Detection (-1 is anomaly)
            anomaly_score = 1
            if self.anomaly_model:
                anomaly_score = self.anomaly_model.predict(features_scaled)[0]
            
            # 2. Classification (uses raw features)
            attack_type = "Normal"
            confidence = 0.0
            if self.classifier_model:
                attack_type = self.classifier_model.predict(features)[0]
                probs = self.classifier_model.predict_proba(features)
                confidence = np.max(probs)
            
            # 3. Decision Logic (OR Gate)
            is_threat = False
            final_type = "Normal"
            
            if anomaly_score == -1:
                is_threat = True
                final_type = "Unknown Anomaly"
            
            if attack_type != "Normal":
                is_threat = True
                final_type = attack_type # Specific type overrides generic "Unknown"
            
            return {
                "is_threat": is_threat,
                "attack_type": final_type,
                "confidence": round(float(confidence), 4)
            }

        except Exception as e:
            logging.error(f"[SENTINEL] Prediction error: {e}")
            return {"is_threat": False, "attack_type": "Error"}
    
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
            "anomaly_loaded": self.anomaly_model is not None,
            "classifier_loaded": self.classifier_model is not None,
            "mode": "Dual-Model AI" if self.enabled else "Threshold Fallback"
        }


class NavigatorAI:
    """
    Routing AI - Path Optimization using Q-Learning
    
    This class wraps the NavigatorBrain Q-Learning engine and provides
    a clean interface for the controller.
    
    Input: Source MAC, Destination MAC, Network Graph
    Output: Optimal path as list of switch IDs
    
    Usage:
        navigator = NavigatorAI()
        navigator.initialize_topology(topology_dict)
        path = navigator.get_path("00:00:00:00:00:01", "00:00:00:00:00:07", graph)
    """
    
    def __init__(self):
        self.brain = None
        self.enabled = NAVIGATOR_ENABLED and ML_AVAILABLE
        self.topology = None
        self.host_to_switch = {}  # MAC -> switch_id mapping
        self.save_counter = 0  # Counter for auto-saving Q-table
        
        if self.enabled:
            self._initialize_brain()
    
    def _initialize_brain(self):
        """Initialize the Q-Learning brain."""
        try:
            # Import the brain module
            import sys
            ai_models_path = os.path.join(os.path.dirname(__file__), '..', 'ai_models')
            if ai_models_path not in sys.path:
                sys.path.insert(0, ai_models_path)
            
            from navigator_brain import NavigatorBrain
            
            self.brain = NavigatorBrain(
                learning_rate=0.1,
                discount_factor=0.9,
                epsilon=0.1,  # 10% exploration
                epsilon_decay=0.995,
                min_epsilon=0.01
            )
            
            # Try to load saved model
            model_path = NAVIGATOR_MODEL_PATH
            if os.path.exists(model_path):
                self.brain.load(model_path)
                logging.info(f"[NAVIGATOR] Brain loaded from {model_path}")
            else:
                logging.info("[NAVIGATOR] Brain initialized (no saved model)")
                
        except Exception as e:
            logging.error(f"[NAVIGATOR] Failed to initialize brain: {e}")
            self.enabled = False
    
    def initialize_topology(self, topology: dict):
        """
        Initialize the navigator with network topology.
        
        Must be called before get_path().
        
        Args:
            topology: Dictionary matching config.py TOPOLOGY format
        """
        if not self.enabled or self.brain is None:
            return
        
        self.topology = topology
        self.brain.initialize_from_topology(topology)
        
        # Build host-to-switch mapping
        for host in topology.get('hosts', []):
            mac = host.get('mac', '')
            switch = host.get('switch', '')
            if mac and switch:
                self.host_to_switch[mac] = switch
        
        logging.info(f"[NAVIGATOR] Topology initialized: {len(self.host_to_switch)} hosts")
    
    def update_link_stats(self, link_stats: dict):
        """
        Update link weights based on live traffic.
        
        Called by controller after collecting flow stats.
        
        Args:
            link_stats: Dict mapping (from_sw, to_sw) -> {'bps': float, 'bandwidth': float}
        """
        if not self.enabled or self.brain is None:
            return
        
        self.brain.update_link_weights(link_stats)
    
    def get_path(self, src_mac: str, dst_mac: str, network_graph: dict = None) -> list:
        """
        Get optimal path between two hosts using Q-Learning.
        
        Args:
            src_mac: Source MAC address
            dst_mac: Destination MAC address
            network_graph: Optional - ignored (using internal brain state)
            
        Returns:
            List of switch IDs representing the path, e.g., ["s3", "s2", "s1", "s5"]
        """
        if not self.enabled or self.brain is None:
            return self._fallback_path(src_mac, dst_mac, network_graph)
        
        # Get switches for the MAC addresses
        src_switch = self.host_to_switch.get(src_mac)
        dst_switch = self.host_to_switch.get(dst_mac)
        
        if not src_switch or not dst_switch:
            logging.debug(f"[NAVIGATOR] Unknown MAC: src={src_mac}, dst={dst_mac}")
            return self._fallback_path(src_mac, dst_mac, network_graph)
        
        # Use Q-Learning brain to find optimal path
        path = self.brain.get_optimal_path(src_switch, dst_switch)
        
        # Auto-save Q-table every 10 path calculations
        self.save_counter += 1
        if self.save_counter % 10 == 0:
            self.save_model()
        
        if path:
            logging.debug(f"[NAVIGATOR] Path: {src_mac} -> {dst_mac} via {path}")
            return path
        else:
            return self._fallback_path(src_mac, dst_mac, network_graph)
    
    def _fallback_path(self, src_mac: str, dst_mac: str, network_graph: dict) -> list:
        """Simple BFS shortest path when AI is unavailable."""
        logging.debug(f"[NAVIGATOR-FALLBACK] Path request: {src_mac} -> {dst_mac}")
        
        # Use simple BFS if we have a graph
        if network_graph and isinstance(network_graph, dict):
            src_switch = self.host_to_switch.get(src_mac)
            dst_switch = self.host_to_switch.get(dst_mac)
            
            if src_switch and dst_switch:
                return self._bfs_path(src_switch, dst_switch, network_graph)
        
        return []
    
    def _bfs_path(self, src: str, dst: str, graph: dict) -> list:
        """BFS shortest path algorithm."""
        if src == dst:
            return [src]
        
        visited = {src}
        queue = [[src]]
        
        while queue:
            path = queue.pop(0)
            current = path[-1]
            
            # Get neighbors
            neighbors = graph.get(current, [])
            if isinstance(neighbors, list):
                for neighbor_info in neighbors:
                    if isinstance(neighbor_info, dict):
                        neighbor = neighbor_info.get('node', neighbor_info.get('neighbor', ''))
                    else:
                        neighbor = str(neighbor_info)
                    
                    if neighbor and neighbor not in visited:
                        new_path = path + [neighbor]
                        
                        if neighbor == dst:
                            return new_path
                        
                        visited.add(neighbor)
                        queue.append(new_path)
        
        return []
    
    def save_model(self):
        """Save the current Q-table to disk."""
        if self.brain:
            self.brain.save(NAVIGATOR_MODEL_PATH)
    
    def get_status(self) -> dict:
        """Return status information for debugging."""
        if self.brain:
            brain_status = self.brain.get_status()
            return {
                "name": "Navigator",
                "enabled": self.enabled,
                "brain_initialized": brain_status.get('initialized', False),
                "epsilon": brain_status.get('epsilon', 0),
                "paths_calculated": brain_status.get('paths_calculated', 0),
                "mode": "Q-Learning AI" if self.enabled else "BFS Fallback"
            }
        return {
            "name": "Navigator",
            "enabled": self.enabled,
            "model_loaded": False,
            "mode": "Default Flooding"
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

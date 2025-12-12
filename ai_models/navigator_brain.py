"""
Navigator Brain - Q-Learning Routing Engine
============================================
Member 3: The Traffic Engineer

This module implements a Reinforcement Learning agent that learns
optimal routing paths based on network congestion.

Concept:
- States: Network switches (s1, s2, s3, s4, ...)
- Actions: Which neighbor switch to forward to
- Reward: Negative of (latency + congestion penalty)

The agent learns to avoid congested links and find the fastest
path even if it's not the shortest hop count.

Usage:
    brain = NavigatorBrain()
    brain.initialize_from_topology(topology_dict)
    brain.update_link_weights(live_stats)
    path = brain.get_optimal_path("s1", "s4")
"""

import numpy as np
import random
import logging
from collections import defaultdict
from typing import Dict, List, Tuple, Optional
import os

try:
    import joblib
    JOBLIB_AVAILABLE = True
except ImportError:
    JOBLIB_AVAILABLE = False


class NavigatorBrain:
    """
    Q-Learning based intelligent routing engine.
    
    The brain learns from network conditions and optimizes
    packet routing to minimize latency and avoid congestion.
    """
    
    def __init__(self, 
                 learning_rate: float = 0.1,
                 discount_factor: float = 0.9,
                 epsilon: float = 0.1,
                 epsilon_decay: float = 0.995,
                 min_epsilon: float = 0.01):
        """
        Initialize the Navigator Brain.
        
        Args:
            learning_rate: Alpha - how fast to learn new values (0.1 = moderate)
            discount_factor: Gamma - importance of future rewards (0.9 = long-term focused)  
            epsilon: Exploration rate (0.1 = 10% random exploration)
            epsilon_decay: How fast epsilon decreases (for exploitation over time)
            min_epsilon: Minimum exploration rate
        """
        # Q-Learning hyperparameters
        self.alpha = learning_rate
        self.gamma = discount_factor
        self.epsilon = epsilon
        self.epsilon_decay = epsilon_decay
        self.min_epsilon = min_epsilon
        
        # Q-Table: Q[state][action] = expected reward
        # state = current switch, action = next switch
        self.q_table: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        
        # Network topology (adjacency list with weights)
        self.graph: Dict[str, List[Dict]] = {}
        
        # Link statistics (updated from controller)
        self.link_stats: Dict[Tuple[str, str], Dict] = {}
        
        # Configuration
        self.switches: List[str] = []
        self.initialized = False
        
        # Statistics for monitoring
        self.total_updates = 0
        self.paths_calculated = 0
        
        logging.info("[NAVIGATOR BRAIN] Initialized with alpha=%.2f, gamma=%.2f, epsilon=%.2f",
                     learning_rate, discount_factor, epsilon)
    
    # =========================================================================
    # INITIALIZATION
    # =========================================================================
    
    def initialize_from_topology(self, topology: dict):
        """
        Build the network graph from topology configuration.
        
        Args:
            topology: Dictionary with 'switches' and 'links' keys
                     (matches config.py TOPOLOGY format)
        """
        self.switches = [s['id'] for s in topology.get('switches', [])]
        self.graph = {s: [] for s in self.switches}
        
        # Build adjacency list with initial weights
        for link in topology.get('links', []):
            src = link.get('from', '')
            dst = link.get('to', '')
            
            # Skip host connections (we only care about switch-to-switch)
            if not src.startswith('s') or not dst.startswith('s'):
                continue
                
            bandwidth = link.get('bw_mbps', 100)
            delay = link.get('delay_ms', 1)
            
            # Initial weight = delay (lower is better)
            weight = delay
            
            # Add bidirectional edges
            self.graph[src].append({
                'neighbor': dst,
                'weight': weight,
                'bandwidth': bandwidth,
                'delay': delay,
                'current_bps': 0,
                'congestion': 0.0
            })
            
            self.graph[dst].append({
                'neighbor': src,
                'weight': weight,
                'bandwidth': bandwidth,
                'delay': delay,
                'current_bps': 0,
                'congestion': 0.0
            })
        
        # Initialize Q-table with small random values
        for switch in self.switches:
            for neighbor_info in self.graph.get(switch, []):
                neighbor = neighbor_info['neighbor']
                # Small positive bias towards lower latency paths
                initial_q = -neighbor_info['delay'] + random.uniform(0, 0.1)
                self.q_table[switch][neighbor] = initial_q
        
        self.initialized = True
        logging.info("[NAVIGATOR BRAIN] Initialized from topology: %d switches, %d links",
                     len(self.switches), sum(len(v) for v in self.graph.values()) // 2)
    
    # =========================================================================
    # NETWORK STATE UPDATES
    # =========================================================================
    
    def update_link_weights(self, link_stats: Dict[Tuple[str, str], Dict]):
        """
        Update link weights based on live traffic statistics from controller.
        
        Args:
            link_stats: Dictionary mapping (from_switch, to_switch) to stats
                       Each stat contains: {'bps': float, 'bandwidth': float}
        
        This is called periodically by the controller with fresh data.
        The agent uses this to learn and adapt.
        """
        self.link_stats = link_stats
        
        # Update graph weights based on congestion
        for switch in self.graph:
            for edge in self.graph[switch]:
                neighbor = edge['neighbor']
                link_key = (switch, neighbor)
                
                if link_key in link_stats:
                    stats = link_stats[link_key]
                    
                    # Handle both dict and float input types
                    if isinstance(stats, dict):
                        current_bps = stats.get('bps', 0)
                    else:
                        # Raw float representing BPS
                        current_bps = float(stats)
                    
                    bandwidth = edge['bandwidth'] * 1_000_000  # Mbps to bps
                    
                    # Calculate congestion ratio (0.0 to 1.0)
                    congestion = min(1.0, current_bps / bandwidth) if bandwidth > 0 else 0
                    
                    edge['current_bps'] = current_bps
                    edge['congestion'] = congestion
                    
                    # Update weight: base_delay + congestion_penalty
                    # Higher congestion = higher weight = less attractive
                    congestion_penalty = congestion * 100  # Scale penalty
                    edge['weight'] = edge['delay'] + congestion_penalty
        
        self.total_updates += 1
        
        # Decay epsilon for more exploitation over time
        if self.epsilon > self.min_epsilon:
            self.epsilon *= self.epsilon_decay
    
    def update_from_experience(self, path: List[str], final_reward: float):
        """
        Update Q-values based on a completed path experience.
        
        Uses backward Q-learning update along the path.
        
        Args:
            path: List of switches traversed, e.g., ['s1', 's2', 's4']
            final_reward: The final reward received (negative latency/congestion)
        """
        if len(path) < 2:
            return
        
        # Backward pass through the path
        reward = final_reward
        for i in range(len(path) - 2, -1, -1):
            current_state = path[i]
            action = path[i + 1]
            next_state = path[i + 1] if i + 1 < len(path) - 1 else None
            
            # Get max Q-value for next state
            if next_state and next_state in self.q_table:
                max_next_q = max(self.q_table[next_state].values()) if self.q_table[next_state] else 0
            else:
                max_next_q = 0
            
            # Q-learning update: Q(s,a) = Q(s,a) + alpha * (r + gamma * max_Q(s') - Q(s,a))
            old_q = self.q_table[current_state][action]
            new_q = old_q + self.alpha * (reward + self.gamma * max_next_q - old_q)
            self.q_table[current_state][action] = new_q
    
    # =========================================================================
    # PATH CALCULATION
    # =========================================================================
    
    def get_optimal_path(self, src_switch: str, dst_switch: str) -> List[str]:
        """
        Calculate the optimal path from source to destination switch.
        
        Uses epsilon-greedy policy:
        - With probability epsilon: explore (random neighbor)
        - With probability 1-epsilon: exploit (best Q-value)
        
        Args:
            src_switch: Starting switch ID (e.g., "s1")
            dst_switch: Destination switch ID (e.g., "s4")
            
        Returns:
            List of switch IDs representing the path, e.g., ["s1", "s2", "s4"]
            Empty list if no path found.
        """
        if not self.initialized:
            logging.warning("[NAVIGATOR BRAIN] Not initialized, returning empty path")
            return []
        
        if src_switch not in self.graph or dst_switch not in self.graph:
            logging.warning("[NAVIGATOR BRAIN] Invalid switches: %s -> %s", src_switch, dst_switch)
            return []
        
        if src_switch == dst_switch:
            return [src_switch]
        
        path = [src_switch]
        visited = {src_switch}
        current = src_switch
        max_hops = len(self.switches) + 1  # Prevent infinite loops
        
        while current != dst_switch and len(path) < max_hops:
            neighbors = self.graph.get(current, [])
            if not neighbors:
                break
            
            # Filter out visited neighbors
            valid_neighbors = [n for n in neighbors if n['neighbor'] not in visited]
            if not valid_neighbors:
                # Backtrack if stuck
                if len(path) > 1:
                    path.pop()
                    visited.discard(current)
                    current = path[-1]
                    continue
                else:
                    break
            
            # Epsilon-greedy action selection
            if random.random() < self.epsilon:
                # Explore: random choice
                next_info = random.choice(valid_neighbors)
            else:
                # Exploit: choose based on Q-values + heuristic towards destination
                best_neighbor = None
                best_score = float('-inf')
                
                for neighbor_info in valid_neighbors:
                    neighbor = neighbor_info['neighbor']
                    
                    # Q-value component
                    q_value = self.q_table[current].get(neighbor, 0)
                    
                    # Heuristic: bonus if neighbor is destination
                    destination_bonus = 100 if neighbor == dst_switch else 0
                    
                    # Weight penalty (prefer lower weight = less congested)
                    weight_penalty = -neighbor_info['weight']
                    
                    score = q_value + destination_bonus + weight_penalty * 0.1
                    
                    if score > best_score:
                        best_score = score
                        best_neighbor = neighbor_info
                
                next_info = best_neighbor
            
            if next_info:
                next_switch = next_info['neighbor']
                path.append(next_switch)
                visited.add(next_switch)
                current = next_switch
        
        self.paths_calculated += 1
        
        # Calculate reward for this path and update Q-values
        if path[-1] == dst_switch:
            reward = self._calculate_path_reward(path)
            self.update_from_experience(path, reward)
            logging.debug("[NAVIGATOR BRAIN] Path found: %s (reward: %.2f)", path, reward)
            return path
        else:
            logging.warning("[NAVIGATOR BRAIN] No valid path from %s to %s", src_switch, dst_switch)
            return []
    
    def get_path_for_hosts(self, src_mac: str, dst_mac: str, 
                           host_to_switch: Dict[str, str]) -> List[str]:
        """
        Get optimal path between two hosts.
        
        Args:
            src_mac: Source host MAC address
            dst_mac: Destination host MAC address
            host_to_switch: Mapping of MAC addresses to connected switches
            
        Returns:
            Path as list of switch IDs
        """
        src_switch = host_to_switch.get(src_mac)
        dst_switch = host_to_switch.get(dst_mac)
        
        if not src_switch or not dst_switch:
            logging.warning("[NAVIGATOR BRAIN] Unknown host MAC: %s or %s", src_mac, dst_mac)
            return []
        
        return self.get_optimal_path(src_switch, dst_switch)
    
    def _calculate_path_reward(self, path: List[str]) -> float:
        """
        Calculate the reward for a given path.
        
        Reward = -(total_latency + congestion_penalty)
        
        Higher reward = better path (less negative).
        """
        if len(path) < 2:
            return 0.0
        
        total_latency = 0.0
        total_congestion = 0.0
        
        for i in range(len(path) - 1):
            current = path[i]
            next_switch = path[i + 1]
            
            # Find the edge
            for edge in self.graph.get(current, []):
                if edge['neighbor'] == next_switch:
                    total_latency += edge['delay']
                    total_congestion += edge['congestion']
                    break
        
        # Reward is negative of cost (minimize latency + congestion)
        reward = -(total_latency + total_congestion * 50)
        return reward
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def get_status(self) -> dict:
        """Return status information for monitoring."""
        return {
            "name": "Navigator Brain",
            "initialized": self.initialized,
            "switches": len(self.switches),
            "epsilon": round(self.epsilon, 4),
            "total_updates": self.total_updates,
            "paths_calculated": self.paths_calculated,
            "q_table_size": sum(len(v) for v in self.q_table.values())
        }
    
    def get_link_info(self) -> List[dict]:
        """Get current link information for debugging."""
        links = []
        seen = set()
        
        for switch in self.graph:
            for edge in self.graph[switch]:
                link_key = tuple(sorted([switch, edge['neighbor']]))
                if link_key not in seen:
                    seen.add(link_key)
                    links.append({
                        'from': switch,
                        'to': edge['neighbor'],
                        'weight': round(edge['weight'], 2),
                        'congestion': round(edge['congestion'], 2),
                        'current_bps': edge['current_bps'],
                        'bandwidth_mbps': edge['bandwidth']
                    })
        
        return links
    
    def save(self, filepath: str):
        """Save the Q-table and configuration to disk."""
        if not JOBLIB_AVAILABLE:
            logging.warning("[NAVIGATOR BRAIN] joblib not available, cannot save")
            return
        
        data = {
            'q_table': dict(self.q_table),
            'epsilon': self.epsilon,
            'total_updates': self.total_updates,
            'paths_calculated': self.paths_calculated
        }
        joblib.dump(data, filepath)
        logging.info("[NAVIGATOR BRAIN] Saved to %s", filepath)
    
    def load(self, filepath: str):
        """Load Q-table and configuration from disk."""
        if not JOBLIB_AVAILABLE:
            logging.warning("[NAVIGATOR BRAIN] joblib not available, cannot load")
            return
        
        if os.path.exists(filepath):
            data = joblib.load(filepath)
            self.q_table = defaultdict(lambda: defaultdict(float), data.get('q_table', {}))
            self.epsilon = data.get('epsilon', self.epsilon)
            self.total_updates = data.get('total_updates', 0)
            self.paths_calculated = data.get('paths_calculated', 0)
            logging.info("[NAVIGATOR BRAIN] Loaded from %s", filepath)


# =============================================================================
# STANDALONE TEST
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    print("\n" + "="*60)
    print("NAVIGATOR BRAIN - Q-Learning Test")
    print("="*60)
    
    # Create a sample topology (Diamond)
    test_topology = {
        "switches": [
            {"id": "s1", "dpid": 1},
            {"id": "s2", "dpid": 2},
            {"id": "s3", "dpid": 3},
            {"id": "s4", "dpid": 4}
        ],
        "links": [
            # Fast path
            {"from": "s1", "to": "s4", "bw_mbps": 100, "delay_ms": 1},
            # Slow path
            {"from": "s1", "to": "s2", "bw_mbps": 10, "delay_ms": 10},
            {"from": "s2", "to": "s3", "bw_mbps": 10, "delay_ms": 10},
            {"from": "s3", "to": "s4", "bw_mbps": 10, "delay_ms": 10}
        ]
    }
    
    # Initialize brain
    brain = NavigatorBrain(epsilon=0.2)  # Higher exploration for testing
    brain.initialize_from_topology(test_topology)
    
    print("\n--- Initial State ---")
    print(f"Status: {brain.get_status()}")
    print(f"Links: {brain.get_link_info()}")
    
    # Test path finding (should prefer fast path s1 -> s4)
    print("\n--- Path Finding Test (No Congestion) ---")
    for i in range(10):
        path = brain.get_optimal_path("s1", "s4")
        print(f"  Run {i+1}: {path}")
    
    # Simulate congestion on fast path
    print("\n--- Simulating Congestion on Fast Path ---")
    congested_stats = {
        ("s1", "s4"): {"bps": 95_000_000, "bandwidth": 100}  # 95% utilized
    }
    brain.update_link_weights(congested_stats)
    
    print(f"Links after congestion: {brain.get_link_info()}")
    
    # Test path finding with congestion (should sometimes use slow path)
    print("\n--- Path Finding Test (With Congestion) ---")
    for i in range(10):
        path = brain.get_optimal_path("s1", "s4")
        print(f"  Run {i+1}: {path}")
    
    print("\n--- Final Status ---")
    print(f"Status: {brain.get_status()}")
    print("="*60)

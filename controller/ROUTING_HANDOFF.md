# Routing Module Handoff Document

## Your Mission

Implement the **Navigator AI** for intelligent traffic routing using **Q-Learning** or another RL algorithm.

### What the Model Should Do:
1. Given a source and destination host, calculate the **optimal path**
2. Consider **link congestion** (not just shortest path)
3. Return a list of switch IDs representing the path

---

## Data You Receive

### Input 1: Network Graph

Called via: `navigator.get_path(src_mac, dst_mac, network_graph)`

The `network_graph` dictionary contains:

```python
{
    "s1": [
        {"node": "s2", "weight": 1, "utilization_bps": 5000000, "congestion": 0.05},
        {"node": "s4", "weight": 2, "utilization_bps": 100000, "congestion": 0.002},
        {"node": "s5", "weight": 1, "utilization_bps": 0, "congestion": 0.0}
    ],
    "s2": [
        {"node": "s1", "weight": 1, "utilization_bps": 5000000, "congestion": 0.05},
        {"node": "s3", "weight": 3, "utilization_bps": 200000, "congestion": 0.004}
    ],
    # ... more switches
    "_link_stats": {
        ("s1", "s2"): 5000000,  # Total BPS on this link
        ("s2", "s1"): 5000000,
        # ...
    }
}
```

### Key Fields:
| Field | Description |
|-------|-------------|
| `weight` | Link delay in ms (lower = faster) |
| `utilization_bps` | Current bandwidth usage in bytes/sec |
| `congestion` | 0.0-1.0 ratio (usage / capacity) |

---

## Output Expected

Return a **list of switch IDs** from source to destination:

```python
["s3", "s2", "s1", "s5"]  # Path from h1/h2/h3 to h6/h7/h8
```

### Rules:
1. First switch must be where the **source host** is connected
2. Last switch must be where the **destination host** is connected
3. Order matters: `["s3", "s2"]` means s3 → s2

---

## Host-to-Switch Mapping

| Host | MAC | Switch |
|------|-----|--------|
| h1 | 00:00:00:00:00:01 | s3 |
| h2 | 00:00:00:00:00:02 | s3 |
| h3 | 00:00:00:00:00:03 | s3 |
| h4 | 00:00:00:00:00:04 | s2 |
| h5 | 00:00:00:00:00:05 | s4 |
| h6 | 00:00:00:00:00:06 | s5 |
| h7 | 00:00:00:00:00:07 | s5 |
| h8 | 00:00:00:00:00:08 | s5 |

---

## Implementation Location

Edit: `controller/ai_interface.py`

### Where to Add Your Code:

```python
class NavigatorAI:
    def _ai_path(self, src_mac: str, dst_mac: str, network_graph: dict) -> list:
        """
        YOUR Q-LEARNING IMPLEMENTATION HERE
        
        Args:
            src_mac: Source host MAC
            dst_mac: Destination host MAC
            network_graph: Graph with congestion data
            
        Returns:
            List of switch IDs, e.g., ["s3", "s2", "s1", "s5"]
        """
        # 1. Find source switch (where src_mac is connected)
        # 2. Find destination switch
        # 3. Use Q-learning to find optimal path considering congestion
        # 4. Return path as list of switch IDs
        pass
```

---

## Q-Learning Hints

### State Space:
- Current switch ID
- Destination switch ID

### Action Space:
- Choose next hop (neighbor switch)

### Reward Function:
```python
def reward(link):
    delay_penalty = link['weight']  # Higher delay = worse
    congestion_penalty = link['congestion'] * 10  # Congested links are bad
    return -delay_penalty - congestion_penalty
```

### Exploration:
- Use ε-greedy: 90% exploit best path, 10% explore alternatives

---

## Testing Your Implementation

1. Enable Navigator in config:
   ```python
   # controller/config.py
   NAVIGATOR_ENABLED = True
   ```

2. Run the network:
   ```bash
   ryu-manager sentinet_controller.py
   sudo python3 topo.py
   ```

3. Generate traffic to create congestion:
   ```bash
   mininet> h1 iperf -c 10.0.0.7 -t 60 &  # Congests s3-s2-s1-s5 path
   ```

4. Watch controller logs for path decisions:
   ```
   [NAVIGATOR] Path ['s3', 's2', 's1', 's5'], using port 4
   ```

---

## Deliverables

1. **Update** `ai_interface.py` with working `_ai_path()` method
2. **Optional**: If using a trained model, place `navigator_model.joblib` in `ai_models/`

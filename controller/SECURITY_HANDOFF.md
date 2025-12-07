# Security Module Handoff Document


## 1. Your Mission

Train an **Isolation Forest** model to detect **DDoS attacks** in real-time network traffic.

### What the Model Should Do:
1. Learn what "normal" traffic looks like from the training data
2. Flag traffic as **ANOMALY** when it deviates significantly (potential DDoS)
3. Return a prediction that the Controller can use to block malicious flows

### Attack Signatures to Detect:
| Attack Type | What to Look For |
|-------------|------------------|
| **Volumetric DDoS** | Extremely high `pps` (>1000) and `bps` |
| **SYN Flood** | High `pps` with small `avg_pkt_size` (~64 bytes) |
| **Amplification** | Asymmetric traffic (one direction has 10x+ the `bps`) |

---

## 2. Dataset: `traffic_data.csv`

### Column Descriptions:

| Column | Type | Description | Use for Training? |
|--------|------|-------------|-------------------|
| `timestamp` | float | Unix epoch when stats were collected | ❌ No (identifier only) |
| `dpid` | int | Switch ID (1-5) that reported this flow | ❌ No (identifier only) |
| `src` | MAC | Source host address (e.g., `00:00:00:00:00:01`) | ❌ No (identifier only) |
| `dst` | MAC | Destination host address | ❌ No (identifier only) |
| `packet_count` | int | Total packets in this flow since creation | ⚠️ Maybe (cumulative) |
| `byte_count` | int | Total bytes in this flow since creation | ⚠️ Maybe (cumulative) |
| `duration_sec` | float | How long the flow has existed (seconds) | ⚠️ Maybe |
| **`pps`** | float | **Packets Per Second** = packet_count / duration | ✅ **PRIMARY FEATURE** |
| **`bps`** | float | **Bytes Per Second** = byte_count / duration | ✅ **PRIMARY FEATURE** |
| **`avg_pkt_size`** | float | **Average Packet Size** = byte_count / packet_count | ✅ **PRIMARY FEATURE** |

### Recommended Training Features:
```python
features = ['pps', 'bps', 'avg_pkt_size']
```

---

## 3. Data Preprocessing Required

### Issue: Per-Switch Redundancy
The same flow is logged by multiple switches (the packet passes through several switches). You'll see the same `src→dst` pair at the same timestamp from different `dpid` values.

### Solution: Aggregate by Flow
```python
import pandas as pd

df = pd.read_csv('traffic_data.csv')

# Group by time window + flow, take max rates
df['time_bucket'] = (df['timestamp'] // 2).astype(int)  # 2-second buckets
clean_df = df.groupby(['time_bucket', 'src', 'dst']).agg({
    'pps': 'max',
    'bps': 'max',
    'avg_pkt_size': 'mean',
    'packet_count': 'max',
    'byte_count': 'max'
}).reset_index()
```

---

## 4. Training the Model

### Basic Isolation Forest Implementation:
```python
from sklearn.ensemble import IsolationForest
import joblib

# 1. Load and preprocess data
df = pd.read_csv('traffic_data.csv')
X = df[['pps', 'bps', 'avg_pkt_size']].fillna(0)

# 2. Train Isolation Forest
model = IsolationForest(
    contamination=0.05,  # Expect ~5% anomalies
    random_state=42,
    n_estimators=100
)
model.fit(X)

# 3. Save the trained model
joblib.dump(model, 'sentinel_model.joblib')
```

### What `contamination` means:
- Set to the expected % of attack traffic in your dataset
- If this is clean "normal" traffic, use `0.01` (1%)
- If you inject attack data, adjust accordingly

---

## 5. Deliverables Expected

Please provide the following back to the Architect:

### A. Trained Model File
```
sentinel_model.joblib
```

### B. Prediction Function
A Python function we can call from the Controller:

```python
def predict(pps: float, bps: float, avg_pkt_size: float) -> int:
    """
    Returns:
        1  = Normal traffic
        -1 = ANOMALY (potential attack)
    """
    # Your implementation here
    pass
```

### C. Integration Module
A file called `sentinel.py` that the Controller can import:

```python
# sentinel.py
import joblib
import numpy as np

class Sentinel:
    def __init__(self, model_path='sentinel_model.joblib'):
        self.model = joblib.load(model_path)
    
    def is_attack(self, pps, bps, avg_pkt_size) -> bool:
        """Returns True if traffic is anomalous (potential DDoS)"""
        features = np.array([[pps, bps, avg_pkt_size]])
        prediction = self.model.predict(features)
        return prediction[0] == -1  # -1 = anomaly in sklearn
```

---

## 6. Testing Your Model

### Generate Attack Traffic (for validation):
In Mininet, simulate a DDoS from h3 (attacker):
```bash
# In Mininet CLI
h3 hping3 -1 --flood 10.0.0.6  # ICMP flood to h6
# OR
h3 hping3 -S --flood -p 80 10.0.0.6  # SYN flood
```

Your model should flag these flows as anomalies.

---


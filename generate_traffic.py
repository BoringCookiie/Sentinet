
import pandas as pd
import numpy as np
import time
import os
import random

def generate_normal_traffic(num_samples=1000, output_file='controller/traffic_data.csv'):
    """
    Generates synthetic 'Normal' traffic data for training the anomaly detection model.
    """
    print(f"[INFO] Generating {num_samples} samples of synthetic traffic data...")

    # Timestamps: generate a sequence
    start_time = time.time()
    timestamps = [start_time + i for i in range(num_samples)]

    # Switches: s1, s2, s3, s4
    switches = [1, 2, 3, 4]

    # MAC Addresses (Dummy)
    macs = [f"00:00:00:00:00:0{i}" for i in range(1, 9)]

    data = []

    for ts in timestamps:
        dpid = random.choice(switches)
        src = random.choice(macs)
        dst = random.choice(macs)
        while dst == src:
            dst = random.choice(macs)

        # Generate NORMAL traffic features
        # PPS: 1 - 5 (Quieter baseline to fix "Goldilocks" problem)
        pps = np.random.randint(1, 6)  # randint is exclusive at the top for numpy? No, python random is inclusive, numpy is exclusive. 
        # Using numpy.random.randint(low, high) -> [low, high)
        # So randint(1, 6) gives 1, 2, 3, 4, 5
        
        # Avg Packet Size: 64 - 1500 bytes (Normal distribution centered around common sizes)
        # Using a simple choice for readability and realism
        avg_pkt_size = np.random.choice([64, 128, 512, 1024, 1500], p=[0.3, 0.2, 0.2, 0.2, 0.1])
        
        # BPS: Derived from PPS * Avg Size * 8 (bits) roughly, plus some variation
        bps = pps * avg_pkt_size * 8 * np.random.uniform(0.9, 1.1)

        # Duration: Short flows
        duration = np.random.uniform(1, 60)
        
        # Counts
        packet_count = int(pps * duration)
        byte_count = int(bps * duration / 8)

        data.append({
            "timestamp": ts,
            "dpid": dpid,
            "src_mac": src,
            "dst_mac": dst,
            "packet_count": packet_count,
            "byte_count": byte_count,
            "duration_sec": duration,
            "pps": pps,
            "bps": bps,
            "avg_pkt_size": avg_pkt_size
        })

    df = pd.DataFrame(data)
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # Save to CSV
    df.to_csv(output_file, index=False)
    print(f"[INFO] Successfully saved {len(df)} rows to {output_file}")
    
    # Preview
    print("\n[INFO] Data Preview:")
    print(df[['pps', 'bps', 'avg_pkt_size']].describe())

if __name__ == "__main__":
    # Ensure we write to the correct relative path
    # Assuming script is run from project root or its own dir
    # We want it in controller/traffic_data.csv relative to project root
    
    # Determine absolute path to controller directory
    base_dir = os.path.dirname(os.path.abspath(__file__))
    target_path = os.path.join(base_dir, 'controller', 'traffic_data.csv')
    
    generate_normal_traffic(output_file=target_path)

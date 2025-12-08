import pandas as pd
from sklearn.ensemble import IsolationForest
import joblib
import os

print("[INFO] Anomaly Training Script starting...")

# 1. Path Setup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, '../controller/traffic_data.csv')
MODEL_PATH = os.path.join(BASE_DIR, 'sentinel_model.joblib')

# 2. Load Data
try:
    print(f"[INFO] Loading data from {DATA_PATH}...")
    df = pd.read_csv(DATA_PATH)
    df.columns = df.columns.str.strip()
    
    if 'pps' not in df.columns:
        df = pd.read_csv(DATA_PATH, names=['timestamp','src','dst','pps','bps','avg_pkt_size','label'])
        
    # Safety: Fill NaNs
    df.fillna(0, inplace=True)

except Exception as e:
    print(f"[ERROR] Failed to read CSV: {e}")
    exit()

# 3. Train the Brain
print("[INFO] Training Isolation Forest...")
features = ['pps', 'bps', 'avg_pkt_size']
model = IsolationForest(n_estimators=100, contamination=0.01, random_state=42)
model.fit(df[features])

# 4. Save
print(f"[INFO] Saving model to {MODEL_PATH}...")
joblib.dump(model, MODEL_PATH)
print("✅ DONE! Anomaly Model saved.")
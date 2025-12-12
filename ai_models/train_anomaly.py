import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import joblib
import os

print("[INFO] Anomaly Training Script starting...")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, '../controller/traffic_data.csv')
MODEL_PATH = os.path.join(BASE_DIR, 'sentinel_model.joblib')
SCALER_PATH = os.path.join(BASE_DIR, 'sentinel_scaler.joblib')

try:
    print(f"[INFO] Loading data from {DATA_PATH}...")
    df = pd.read_csv(DATA_PATH)
    df.columns = df.columns.str.strip()
    
    if 'pps' not in df.columns:
        df = pd.read_csv(DATA_PATH, names=['timestamp','src','dst','pps','bps','avg_pkt_size','label'])
        
    df.fillna(0, inplace=True)

except Exception as e:
    print(f"[ERROR] Failed to read CSV: {e}")
    exit()

features = ['pps', 'bps', 'avg_pkt_size']

# Data Validation to prevent "Empty Brain"
if df.empty:
    print("[ERROR] dataset is empty. Aborting training.")
    exit()

if (df[features] == 0).all().all():
    print("[ERROR] dataset contains only zeros. Aborting training to prevent 'Empty Brain' model.")
    print("       Please run 'generate_traffic.py' to create valid traffic data.")
    exit()

# Check if we have enough data points
if len(df) < 50:
    print("[WARNING] Dataset is very small (< 50 rows). Model might be unreliable.")

# Show training data stats
print(f"[INFO] Training data: {len(df)} samples, PPS range: {df['pps'].min():.2f} - {df['pps'].max():.2f}")

# Normalize features so PPS changes are weighted equally with BPS
print("[INFO] Normalizing features with StandardScaler...")
scaler = StandardScaler()
X_scaled = scaler.fit_transform(df[features])

# Train with low contamination for tight boundary
print("[INFO] Training Isolation Forest (contamination=0.01)...")
model = IsolationForest(
    n_estimators=100, 
    contamination=0.01,  # Tight boundary for sensitive detection
    random_state=42
)
model.fit(X_scaled)

# Save both model and scaler
print(f"[INFO] Saving model to {MODEL_PATH}...")
joblib.dump(model, MODEL_PATH)
print(f"[INFO] Saving scaler to {SCALER_PATH}...")
joblib.dump(scaler, SCALER_PATH)
print("[INFO] Anomaly Model and Scaler saved successfully.")
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
import joblib
import os

print("[INFO] Script starting...")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, '../controller/traffic_data.csv')
MODEL_PATH = os.path.join(BASE_DIR, 'sentinel_classifier.joblib')

# 1. Load Existing "Normal" Data
try:
    print(f"[INFO] Loading data from {DATA_PATH}...")
    df_normal = pd.read_csv(DATA_PATH)
    df_normal.columns = df_normal.columns.str.strip()
    
    if 'pps' not in df_normal.columns:
        print("[INFO] No headers found. Reloading...")
        df_normal = pd.read_csv(DATA_PATH, names=['timestamp','src','dst','pps','bps','avg_pkt_size','label'])
        
    df_normal.fillna(0, inplace=True)
    
except FileNotFoundError:
    print(f"[ERROR] CSV not found at {DATA_PATH}. Check your path.")
    exit()
except Exception as e:
    print(f"[ERROR] Error reading CSV: {e}")
    exit()

# 2. Data Augmentation (Synthesize Attacks)
print("[INFO] Synthesizing Attack Data...")

# Generate SYN Flood (High PPS, Small Packets)
syn_rows = 500
syn_data = []
for _ in range(syn_rows):
    pps = np.random.randint(15, 201)  # <--- Lowered from 50 to 15 to catch ping floods
    avg_pkt_size = 64
    bps = pps * avg_pkt_size * 8
    syn_data.append({'pps': pps, 'bps': bps, 'avg_pkt_size': avg_pkt_size})

# Generate Volumetric DDoS (Medium PPS, Large Packets)
vol_rows = 500
vol_data = []
for _ in range(vol_rows):
    pps = np.random.randint(15, 101)  # <--- Lowered from 30 to 15
    avg_pkt_size = np.random.randint(1000, 1501)
    bps = pps * avg_pkt_size * 8
    vol_data.append({'pps': pps, 'bps': bps, 'avg_pkt_size': avg_pkt_size})

# Combine
df_syn = pd.DataFrame(syn_data)
df_vol = pd.DataFrame(vol_data)

# Keep only necessary features for training from normal data
features = ['pps', 'bps', 'avg_pkt_size']
df_combined = pd.concat([df_normal[features], df_syn, df_vol], ignore_index=True)

# 3. Smart Labeling Logic
print("[INFO] Applying Smart Labels...")

labels = []
for index, row in df_combined.iterrows():
    pps = row['pps']
    size = row['avg_pkt_size']
    
    if pps < 10:
        labels.append("Normal")
    elif pps >= 15 and size < 100:  # <--- Threshold lowered to 15
        labels.append("SYN Flood")
    elif pps >= 15 and size >= 100: # <--- Threshold lowered to 15
        labels.append("Volumetric DDoS")
    else:
        labels.append("Unknown Anomaly") # Fallback for gaps

df_combined['label'] = labels
print(f"[DEBUG] Class Distribution: {df_combined['label'].value_counts().to_dict()}")

# 4. Train Model
X = df_combined[features]
y = df_combined['label']

print("[INFO] Splitting data...")
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)

print("[INFO] Training Random Forest Classifier...")
clf = RandomForestClassifier(n_estimators=100, class_weight='balanced', random_state=42)
clf.fit(X_train, y_train)

print("[INFO] Evaluating model...")
y_pred = clf.predict(X_test)
acc = accuracy_score(y_test, y_pred)
print(f"Accuracy: {acc:.4f}")
print("\nClassification Report:\n", classification_report(y_test, y_pred))

print(f"[INFO] Saving model to {MODEL_PATH}...")
joblib.dump(clf, MODEL_PATH)
print(" DONE! Classification model saved.")
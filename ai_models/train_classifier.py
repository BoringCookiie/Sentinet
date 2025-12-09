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

try:
    print(f"[INFO] Loading data from {DATA_PATH}...")
    df = pd.read_csv(DATA_PATH)
    
    df.columns = df.columns.str.strip()
    

    if 'pps' not in df.columns:
        print("[INFO] No headers found in CSV. Reloading with default names...")
        df = pd.read_csv(DATA_PATH, names=['timestamp','src','dst','pps','bps','avg_pkt_size','label'])

    print(f"[DEBUG] Columns found: {list(df.columns)}")

except FileNotFoundError:
    print(f"[ERROR] CSV not found at {DATA_PATH}. Check your path.")
    exit()
except Exception as e:
    print(f"[ERROR] Error reading CSV: {e}")
    exit()

df.fillna(0, inplace=True)

if 'label' not in df.columns:
    print("[WARN] No 'label' column found! Synthesizing labels based on thresholds...")
    
    labels = []
    for index, row in df.iterrows():
        pps = row.get('pps', 0)
        bps = row.get('bps', 0)
        
        if pps > 1000 or bps > 1000000:
            labels.append("DDoS")
        elif pps > 500:
            labels.append("Suspicious")
        else:
            labels.append("Normal")
            
    df['label'] = labels
    print("[INFO] Labels synthesized successfully.")
    print(f"[DEBUG] Class Distribution: {df['label'].value_counts().to_dict()}")

required_features = ['pps', 'bps', 'avg_pkt_size']
missing_features = [f for f in required_features if f not in df.columns]

if missing_features:
    print(f"[CRITICAL] Missing feature columns: {missing_features}")
    exit()

X = df[required_features]
y = df['label']

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
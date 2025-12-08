import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
import joblib

print("DEBUG: Script starting...")

# 1. Load Data
try:
    print("Loading data...")
    df = pd.read_csv('../controller/traffic_data.csv')
    
    # Clean up column names (remove spaces)
    df.columns = df.columns.str.strip()
    print(f"Columns found: {list(df.columns)}")

except Exception as e:
    print(f"❌ Error reading CSV: {e}")
    exit()

# 2. auto-Labeling Logic (The Fix)
# If 'label' is missing, we create it based on thresholds
if 'label' not in df.columns:
    print("⚠️  No 'label' column found! Synthesizing labels based on thresholds...")
    
    # Create a list to hold our fake labels
    labels = []
    
    for index, row in df.iterrows():
        pps = row.get('pps', 0)
        bps = row.get('bps', 0)
        
        # LOGIC: Define what an attack looks like
        # Adjust these numbers based on your specific traffic
        if pps > 1000 or bps > 1000000:  # Example: >1000 packets/sec
            labels.append("DDoS")
        elif pps > 500:
            labels.append("Suspicious")
        else:
            labels.append("Normal")
            
    df['label'] = labels
    print("✅ Labels synthesized successfully.")
    print(f"Distribution: {df['label'].value_counts().to_dict()}")

# 3. Prepare Features (X) and Target (y)
required_features = ['pps', 'bps', 'avg_pkt_size']
missing_features = [f for f in required_features if f not in df.columns]

if missing_features:
    print(f"❌ Critical Error: Missing feature columns: {missing_features}")
    exit()

X = df[required_features]
y = df['label']

# 4. Split Data
print("Splitting data...")
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)

# 5. Train
print("Training Random Forest Classifier...")
clf = RandomForestClassifier(n_estimators=100, random_state=42)
clf.fit(X_train, y_train)

# 6. Evaluate
print("Evaluating model...")
y_pred = clf.predict(X_test)
acc = accuracy_score(y_test, y_pred)
print(f"Accuracy: {acc:.4f}")
print("\nClassification Report:\n", classification_report(y_test, y_pred))

# 7. Save
print("Saving model to sentinel_classifier.joblib...")
joblib.dump(clf, 'sentinel_classifier.joblib')
print("✅ DONE! Classification model saved.")
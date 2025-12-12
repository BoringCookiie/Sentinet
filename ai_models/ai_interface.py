import joblib
import pandas as pd
import numpy as np
import os
import sys

class SentinelAI:
    def __init__(self):
        """
        Initializes the Sentinel AI Engine.
        Dynamically locates and loads the serialized model files (.joblib).
        """
        self.base_path = os.path.dirname(os.path.abspath(__file__))
        
        self.anomaly_path = os.path.join(self.base_path, 'sentinel_model.joblib')
        self.classifier_path = os.path.join(self.base_path, 'sentinel_classifier.joblib')
        self.scaler_path = os.path.join(self.base_path, 'sentinel_scaler.joblib')
        
        self.anomaly_model = None
        self.classifier_model = None
        self.scaler = None
        self.initialized = False  
        self._load_models()

    def _load_models(self):
        """Internal method to load model artifacts from disk."""
        try:
            print(f"[INFO] Sentinel AI: Initializing models...")
            
            if not os.path.exists(self.anomaly_path) or not os.path.exists(self.classifier_path):
                raise FileNotFoundError(f"Model files missing in {self.base_path}")

            self.anomaly_model = joblib.load(self.anomaly_path)
            self.classifier_model = joblib.load(self.classifier_path)
            
            # Load scaler if available (for normalized anomaly detection)
            if os.path.exists(self.scaler_path):
                self.scaler = joblib.load(self.scaler_path)
            
            self.initialized = True  
            print("[INFO] Sentinel AI: Systems Online. Models loaded successfully.")
            
        except Exception as e:
            self.initialized = False
            print(f"[ERROR] Sentinel AI: Failed to load models. Details: {e}", file=sys.stderr)

    def get_health(self):
        """Simple health check for the Dashboard (Member 4)"""
        return {
            "status": "online" if self.initialized else "offline",
            "models_loaded": self.initialized
        }

    def predict(self, pps, bps, avg_pkt_size):
        """
        Analyzes network flow statistics to detect potential threats.
        """
        if not self.initialized:
            return {
                "is_threat": False, 
                "attack_type": "System Error: AI Models Not Initialized", 
                "confidence": 0.0
            }

        features = pd.DataFrame([{
            'pps': pps, 
            'bps': bps, 
            'avg_pkt_size': avg_pkt_size
        }])

        try:
            # Run anomaly detection (with normalization if scaler available)
            if self.scaler is not None:
                features_scaled = self.scaler.transform(features)
                anomaly_prediction = self.anomaly_model.predict(features_scaled)[0]
            else:
                anomaly_prediction = self.anomaly_model.predict(features)[0]
            
            # Run classification
            attack_type = self.classifier_model.predict(features)[0]
            probs = self.classifier_model.predict_proba(features)
            confidence = np.max(probs)
            
            # Determine threat status (OR logic: either model can trigger)
            is_threat = False
            
            if anomaly_prediction == -1:
                is_threat = True
            
            if attack_type != "Normal":
                is_threat = True
                
            final_label = attack_type
            if is_threat and attack_type == "Normal":
                final_label = "Unknown Anomaly"

            return {
                "is_threat": is_threat,
                "attack_type": final_label,
                "confidence": round(float(confidence), 4)
            }
            
        except Exception as e:
            print(f"[ERROR] Prediction failed: {e}", file=sys.stderr)
            return {
                "is_threat": False,
                "attack_type": "Prediction Error",
                "confidence": 0.0
            }

# --- Unit Test ---
if __name__ == "__main__":
    print("--- SentinelAI Interface Unit Test ---")
    ai = SentinelAI()
    
    # Check Health
    print(f"\n[TEST] Health Check: {ai.get_health()}")

    # Test Case 1
    print("\n[TEST] 1. Normal Traffic (100 PPS)...")
    print(f"Result: {ai.predict(pps=100, bps=50000, avg_pkt_size=64)}")
    
    # Test Case 2
    print("\n[TEST] 2. DDoS Simulation (5000 PPS)...")
    print(f"Result: {ai.predict(pps=5000, bps=10_000_000, avg_pkt_size=64)}")
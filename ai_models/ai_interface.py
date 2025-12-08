import joblib
import pandas as pd
import numpy as np
import os

class SentinelAI:
    def __init__(self):
        """
        Initialize the AI Engine.
        This automatically finds the model files relative to THIS script,
        so it works no matter where you import it from.
        """
        # Get the directory where ai_interface.py is located
        base_path = os.path.dirname(os.path.abspath(__file__))
        
        # Define paths to the brains
        self.anomaly_path = os.path.join(base_path, 'sentinel_model.joblib')
        self.classifier_path = os.path.join(base_path, 'sentinel_classifier.joblib')
        
        self.anomaly_model = None
        self.classifier_model = None
        
        # Load them immediately
        self.load_models()

    def load_models(self):
        try:
            print(f"🧠 Sentinel AI: Loading models...")
            # Load the Watchman (Isolation Forest)
            self.anomaly_model = joblib.load(self.anomaly_path)
            
            # Load the Specialist (Random Forest)
            self.classifier_model = joblib.load(self.classifier_path)
            print("✅ Sentinel AI: Systems Online.")
        except FileNotFoundError as e:
            print(f"❌ CRITICAL ERROR: Model file not found. Check path: {e}")
        except Exception as e:
            print(f"❌ Sentinel AI: Failed to load models: {e}")

    def predict(self, pps, bps, avg_pkt_size):
        """
        The Main Public API.
        Member 1 calls this function.
        
        Args:
            pps (float): Packets Per Second
            bps (float): Bits Per Second
            avg_pkt_size (float): Average Packet Size
            
        Returns:
            dict: { 'is_threat': bool, 'attack_type': str, 'confidence': float }
        """
        if not self.anomaly_model or not self.classifier_model:
            return {"error": "Models not loaded"}

        # 1. Format input into the DataFrame the models expect
        # We must use the exact same column names as training
        features = pd.DataFrame([{
            'pps': pps, 
            'bps': bps, 
            'avg_pkt_size': avg_pkt_size
        }])

        # 2. Ask Model 1 (The Watchman)
        # Returns: 1 (Normal) or -1 (Anomaly)
        anomaly_score = self.anomaly_model.predict(features)[0]
        
        # 3. Ask Model 2 (The Specialist)
        # Returns: "DDoS", "Normal", etc.
        attack_type = self.classifier_model.predict(features)[0]
        
        # Get confidence probability (0.0 to 1.0)
        # We take the max probability of the predicted class
        probs = self.classifier_model.predict_proba(features)
        confidence = np.max(probs)

        # 4. Fusion Logic (The Final Decision)
        # If the Watchman sees weirdness OR the Specialist sees a signature...
        is_threat = False
        
        if anomaly_score == -1:
            is_threat = True
        
        if attack_type != "Normal":
            is_threat = True
            
        # Refine the name: If Watchman says anomaly but Specialist says Normal,
        # we call it "Unknown Anomaly"
        final_label = attack_type
        if is_threat and attack_type == "Normal":
            final_label = "Unknown Anomaly"

        return {
            "is_threat": is_threat,
            "attack_type": final_label,
            "confidence": round(float(confidence), 4)
        }

# --- TEST BLOCK ---
# This allows you to run "python ai_interface.py" directly to test it.
if __name__ == "__main__":
    print("--- Running Self-Diagnostic ---")
    ai = SentinelAI()
    
    # Test 1: Normal Traffic (Low PPS)
    print("\nTest 1: Normal Traffic (100 pps)")
    result = ai.predict(pps=100, bps=50000, avg_pkt_size=64)
    print(f"Result: {result}")
    
    # Test 2: Attack Traffic (High PPS)
    print("\nTest 2: DDoS Simulation (5000 pps)")
    result = ai.predict(pps=5000, bps=10000000, avg_pkt_size=64)
    print(f"Result: {result}")
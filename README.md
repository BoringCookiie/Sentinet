#  AI Models 

This directory (`ai_models/`) contains the machine learning logic responsible for analyzing network traffic patterns, detecting anomalies, and classifying potential DDoS attacks.

##  Project Structure & File Descriptions

Here is an explanation of the files contained in this module:

###  Core Models (Serialized)
* **`sentinel_model.joblib`**
    * **Type:** Anomaly Detection Model (Unsupervised).
    * **Purpose:** This pre-trained model defines "normal" baseline traffic. It flags any traffic that deviates significantly from the norm as an anomaly. This is useful for detecting zero-day attacks or unknown attack patterns.
* **`sentinel_classifier.joblib`**
    * **Type:** Traffic Classifier (Supervised).
    * **Purpose:** This pre-trained model categorizes traffic into specific labels (e.g., `Normal`, `SYN Flood`, `UDP Flood`, `HTTP Flood`). It is used when a known attack signature is detected.

###  Source Code
* **`ai_interface.py`**
    * **Role:** The Integration Bridge.
    * **Function:** This script acts as the API/Wrapper for the models. It contains the classes/functions that the Backend or API calls to get predictions. It handles loading the `.joblib` files and processing incoming data into the format the models expect.
* **`train_anomaly.py`**
    * **Role:** Anomaly Training Script.
    * **Function:** Run this script to retrain the `sentinel_model.joblib`. It processes the dataset to learn normal traffic patterns (typically using algorithms like Isolation Forest or Autoencoders).
* **`train_classifier.py`**
    * **Role:** Classifier Training Script.
    * **Function:** Run this script to retrain the `sentinel_classifier.joblib`. It uses labeled datasets containing both benign and attack traffic to teach the model how to distinguish between specific attack types.

###  Configuration & Dependencies
* **`requirements.txt`**
    * Contains the list of Python dependencies required to run these models (e.g., `scikit-learn`, `pandas`, `numpy`, `joblib`).
* **`venv/`**
    * The Python virtual environment containing the installed libraries.

---

##  Setup & Installation

To run or retrain the models, ensure you have Python installed, then follow these steps:

1. **Activate the Virtual Environment:**
   ```bash
   # Windows
   .\venv\Scripts\activate

   # Linux/Mac
   source venv/bin/activate
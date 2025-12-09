"""
Sentinet Database Module
========================
SQLite database setup using SQLAlchemy for persistent storage.

This module provides:
- SQLAlchemy engine and session management
- Alert table for storing security alerts

Note: Live traffic stats are NOT stored in DB (transient pass-through).
Only security alerts are persisted for historical analysis.
"""

from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime

# =============================================================================
# DATABASE CONFIGURATION
# =============================================================================

# SQLite database file path (will be created in backend directory)
DATABASE_URL = "sqlite:///./sentinet.db"

# Create SQLAlchemy engine
# check_same_thread=False allows usage across multiple threads (required for FastAPI)
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False  # Set to True for SQL debugging
)

# Session factory - each request should use a new session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all database models
Base = declarative_base()


# =============================================================================
# DATABASE MODELS
# =============================================================================

class Alert(Base):
    """
    Security Alert Model
    
    Stores detected security incidents (DDoS attacks, anomalies, etc.)
    from the Sentinel AI/Controller.
    
    Attributes:
        id: Unique identifier (auto-increment)
        timestamp: Unix timestamp when the alert was generated
        attacker_ip: IP address of the attacking host
        target_ip: IP address of the targeted host
        severity: Alert severity level (INFO, WARNING, CRITICAL)
        action_taken: Response action (BLOCK, RATE_LIMIT, ALERT_ONLY, etc.)
        created_at: Database insertion timestamp
    """
    __tablename__ = "alerts"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    timestamp = Column(Float, nullable=False)  # Unix timestamp from controller
    attacker_ip = Column(String(45), nullable=False)  # IPv4 or IPv6
    target_ip = Column(String(45), nullable=False)
    severity = Column(String(20), nullable=False, default="WARNING")
    action_taken = Column(String(50), nullable=False, default="ALERT_ONLY")
    created_at = Column(DateTime, default=datetime.utcnow)  # DB timestamp
    
    def __repr__(self):
        return f"<Alert(id={self.id}, attacker={self.attacker_ip}, target={self.target_ip}, severity={self.severity})>"
    
    def to_dict(self) -> dict:
        """Convert Alert model to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "attacker_ip": self.attacker_ip,
            "target_ip": self.target_ip,
            "severity": self.severity,
            "action_taken": self.action_taken,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


# =============================================================================
# DATABASE INITIALIZATION
# =============================================================================

def init_db():
    """
    Initialize the database by creating all tables.
    
    Call this function once at application startup.
    Safe to call multiple times - won't recreate existing tables.
    """
    Base.metadata.create_all(bind=engine)
    print("[DATABASE] Tables created successfully")


def get_db():
    """
    Dependency function for FastAPI to get a database session.
    
    Usage in FastAPI endpoint:
        @app.get("/example")
        def example(db: Session = Depends(get_db)):
            # use db session
            pass
    
    Yields:
        SessionLocal: SQLAlchemy session instance
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =============================================================================
# CRUD OPERATIONS
# =============================================================================

def create_alert(db, alert_data: dict) -> Alert:
    """
    Create a new alert record in the database.
    
    Args:
        db: SQLAlchemy session
        alert_data: Dictionary containing alert fields
            Required: timestamp, attacker_ip, target_ip
            Optional: severity, action_taken
    
    Returns:
        Alert: The created Alert model instance
    """
    alert = Alert(
        timestamp=alert_data.get("timestamp"),
        attacker_ip=alert_data.get("attacker_ip"),
        target_ip=alert_data.get("target_ip"),
        severity=alert_data.get("severity", "WARNING"),
        action_taken=alert_data.get("action_taken", "ALERT_ONLY")
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def get_recent_alerts(db, limit: int = 50) -> list:
    """
    Retrieve the most recent alerts from the database.
    
    Args:
        db: SQLAlchemy session
        limit: Maximum number of alerts to return (default: 50)
    
    Returns:
        list: List of Alert model instances, newest first
    """
    return db.query(Alert).order_by(Alert.id.desc()).limit(limit).all()


def get_alert_by_id(db, alert_id: int) -> Alert:
    """
    Retrieve a single alert by its ID.
    
    Args:
        db: SQLAlchemy session
        alert_id: The alert's unique identifier
    
    Returns:
        Alert or None: The Alert if found, None otherwise
    """
    return db.query(Alert).filter(Alert.id == alert_id).first()


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == "__main__":
    # Initialize database when run directly
    print("[DATABASE] Initializing Sentinet database...")
    init_db()
    
    # Test connection
    db = SessionLocal()
    try:
        # Insert a test alert
        test_alert = create_alert(db, {
            "timestamp": 1712345678.9,
            "attacker_ip": "10.0.0.3",
            "target_ip": "10.0.0.5",
            "severity": "CRITICAL",
            "action_taken": "BLOCK"
        })
        print(f"[DATABASE] Test alert created: {test_alert}")
        
        # Retrieve alerts
        alerts = get_recent_alerts(db, limit=10)
        print(f"[DATABASE] Found {len(alerts)} alerts")
        for alert in alerts:
            print(f"  - {alert.to_dict()}")
    finally:
        db.close()
    
    print("[DATABASE] Database test complete!")

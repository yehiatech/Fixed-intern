import os
import requests
import logging
from dotenv import load_dotenv

# Load env variables (if testing locally)
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Configuration
# If running inside docker compose, use internal hostnames. If running locally, use external IPs.
ESPO_URL = os.getenv("ESPO_API_URL", "http://107.20.124.171:8080/api/v1")
ESPO_KEY = os.getenv("ESPO_API_KEY", "a7a0307817c91ab7feea464170c310f6")
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:8001/calls")

HEADERS = {
    "X-Api-Key": ESPO_KEY,
    "Content-Type": "application/json",
    "Accept": "application/json"
}

def get_pending_calls():
    """Fetch all CFollowUpCall records with status 'Pending' from EspoCRM."""
    # Note: EspoCRM filters can be complex. For this script, we fetch and filter locally for simplicity.
    url = f"{ESPO_URL}/CFollowUpCall?maxSize=100"
    try:
        res = requests.get(url, headers=HEADERS)
        res.raise_for_status()
        data = res.json()
        calls = data.get("list", [])
        return [c for c in calls if c.get("status") == "Pending" or c.get("status") == "pending"]
    except Exception as e:
        logging.error(f"Error fetching pending calls: {e}")
        return []

def trigger_voice_api(call_record):
    """Send the pending call to the Voice AI Orchestrator."""
    payload = {
        "call_id": call_record.get("id"),
        "customer_phone": call_record.get("customerPhone", "+201000000000"), # Fallback if empty
        "customer_name": call_record.get("customerName", "Customer"),
        "org_id": call_record.get("orgId", "fixed"),
        "retry_attempt": call_record.get("callAttempts", 0),
        "assigned_agent": call_record.get("assignedUserId", "system"),
        "language": "ar-EG"
    }

    url = f"{ORCHESTRATOR_URL}/trigger"
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code == 202:
            logging.info(f"Successfully triggered call_id {payload['call_id']}")
            return True
        else:
            logging.error(f"Failed to trigger call {payload['call_id']}: {res.status_code} - {res.text}")
            return False
    except Exception as e:
        logging.error(f"Error reaching Voice API for call {payload['call_id']}: {e}")
        return False

def update_espo_status(call_id, new_status):
    """Update the CFollowUpCall status in EspoCRM to In Progress."""
    url = f"{ESPO_URL}/CFollowUpCall/{call_id}"
    payload = {"status": new_status}
    try:
        res = requests.put(url, headers=HEADERS, json=payload)
        res.raise_for_status()
        logging.info(f"Updated CFollowUpCall {call_id} status to {new_status}")
    except Exception as e:
        logging.error(f"Error updating EspoCRM for call {call_id}: {e}")

def main():
    logging.info("Starting Call Trigger Sync...")
    pending_calls = get_pending_calls()
    
    if not pending_calls:
        logging.info("No pending calls found.")
        return

    for call in pending_calls:
        call_id = call.get("id")
        logging.info(f"Processing pending call: {call_id}")
        
        # 1. Trigger the Voice AI
        success = trigger_voice_api(call)
        
        # 2. If accepted by Voice AI, update EspoCRM to prevent double-calling
        if success:
            update_espo_status(call_id, "In Progress")

if __name__ == "__main__":
    main()

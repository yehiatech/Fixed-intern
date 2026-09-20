import os
import requests
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

ESPO_URL = os.getenv("ESPO_API_URL", "http://107.20.124.171:8080/api/v1")
ESPO_KEY = os.getenv("ESPO_API_KEY", "a7a0307817c91ab7feea464170c310f6")
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:8001/calls")

HEADERS = {
    "X-Api-Key": ESPO_KEY,
    "Content-Type": "application/json",
    "Accept": "application/json"
}

def get_in_progress_calls():
    """Fetch CFollowUpCall records with status 'In Progress'."""
    url = f"{ESPO_URL}/CFollowUpCall?maxSize=100"
    try:
        res = requests.get(url, headers=HEADERS)
        res.raise_for_status()
        calls = res.json().get("list", [])
        return [c for c in calls if c.get("status") in ("In Progress", "in_progress")]
    except Exception as e:
        logging.error(f"Error fetching in_progress calls: {e}")
        return []

def check_voice_api_result(call_id):
    """Check the Voice API for the result of a specific call."""
    url = f"{ORCHESTRATOR_URL}/result/{call_id}"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            return res.json()
        elif res.status_code == 404:
            logging.warning(f"Call {call_id} not found in Voice API.")
            return None
        else:
            logging.error(f"Error checking call {call_id}: {res.status_code} - {res.text}")
            return None
    except Exception as e:
        logging.error(f"Error reaching Voice API for call {call_id}: {e}")
        return None

def update_espo_result(call_id, result_data, current_attempts):
    """Write the AI transcript, summary, and sentiment back to EspoCRM."""
    url = f"{ESPO_URL}/CFollowUpCall/{call_id}"
    
    status = result_data.get("status")
    payload = {}

    if status == "completed":
        payload = {
            "status": "Completed",
            "transcript": result_data.get("transcript"),
            "summary": result_data.get("summary"),
            "sentiment": result_data.get("sentiment"),
            "resolution": result_data.get("resolution")
        }
    elif status == "unanswered":
        new_attempts = current_attempts + 1
        if new_attempts >= 3:
            payload = {"status": "Failed", "callAttempts": new_attempts}
        else:
            # Requeue for next attempt
            payload = {"status": "Pending", "callAttempts": new_attempts}
    elif status == "in_progress":
        logging.info(f"Call {call_id} is still in progress, no update needed.")
        return

    if not payload:
        return

    try:
        res = requests.put(url, headers=HEADERS, json=payload)
        res.raise_for_status()
        logging.info(f"Successfully updated EspoCRM for call {call_id} to status: {payload.get('status')}")
    except Exception as e:
        logging.error(f"Error updating EspoCRM result for call {call_id}: {e}")

def main():
    logging.info("Starting Call Result Sync...")
    in_progress_calls = get_in_progress_calls()
    
    if not in_progress_calls:
        logging.info("No in-progress calls found.")
        return

    for call in in_progress_calls:
        call_id = call.get("id")
        current_attempts = call.get("callAttempts", 0)
        logging.info(f"Checking status for call: {call_id}")
        
        result_data = check_voice_api_result(call_id)
        if result_data:
            update_espo_result(call_id, result_data, current_attempts)

if __name__ == "__main__":
    main()

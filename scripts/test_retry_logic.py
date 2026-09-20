import unittest
from unittest.mock import patch, MagicMock
import datetime
import sys
import os

# Add the directory to sys path so we can import the scripts
sys.path.append(os.path.dirname(__file__))

import call_result_sync
import call_trigger

class TestBridgeScripts(unittest.TestCase):
    
    @patch('call_result_sync.requests.put')
    def test_unanswered_retry_under_3(self, mock_put):
        # Current attempts < 3
        current_attempts = 1
        result_data = {"status": "unanswered"}
        call_id = "test_call_1"
        
        # mock put response
        mock_res = MagicMock()
        mock_res.raise_for_status.return_value = None
        mock_put.return_value = mock_res
        
        call_result_sync.update_espo_result(call_id, result_data, current_attempts)
        
        mock_put.assert_called_once()
        args, kwargs = mock_put.call_args
        payload = kwargs.get("json")
        self.assertEqual(payload["status"], "pending")
        self.assertEqual(payload["callAttempts"], 2)
        self.assertIn("nextRetryAt", payload)
        
    @patch('call_result_sync.requests.put')
    def test_unanswered_retry_max(self, mock_put):
        # Current attempts == 2 (so new will be 3)
        current_attempts = 2
        result_data = {"status": "unanswered"}
        call_id = "test_call_2"
        
        # mock put response
        mock_res = MagicMock()
        mock_res.raise_for_status.return_value = None
        mock_put.return_value = mock_res

        call_result_sync.update_espo_result(call_id, result_data, current_attempts)
        
        mock_put.assert_called_once()
        args, kwargs = mock_put.call_args
        payload = kwargs.get("json")
        self.assertEqual(payload["status"], "failed_max_retries")
        self.assertEqual(payload["callAttempts"], 3)
        self.assertNotIn("nextRetryAt", payload)

    @patch('call_trigger.requests.get')
    def test_call_trigger_next_retry_at(self, mock_get):
        mock_response = MagicMock()
        
        now = datetime.datetime.utcnow()
        past = now - datetime.timedelta(minutes=10)
        future = now + datetime.timedelta(minutes=10)
        
        mock_response.json.return_value = {
            "list": [
                {"id": "1", "status": "Pending", "nextRetryAt": None},
                {"id": "2", "status": "Pending", "nextRetryAt": past.strftime("%Y-%m-%d %H:%M:%S")},
                {"id": "3", "status": "Pending", "nextRetryAt": future.strftime("%Y-%m-%d %H:%M:%S")},
                {"id": "4", "status": "Completed"}
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        
        valid_calls = call_trigger.get_pending_calls()
        self.assertEqual(len(valid_calls), 2)
        ids = [c["id"] for c in valid_calls]
        self.assertIn("1", ids)
        self.assertIn("2", ids)

if __name__ == '__main__':
    unittest.main()

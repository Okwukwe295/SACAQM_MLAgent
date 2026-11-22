"""Check that unavailable and empty responses survive restart with different meanings."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
import pandas as pd
import requests
from scripts import ingest


class ResumeTests(unittest.TestCase):
    def test_failure_retries_and_empty_is_cached(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            span=[(pd.Timestamp("2026-03-01"),pd.Timestamp("2026-04-01"))]
            response=Mock()
            response.json.return_value=[]
            with patch.object(ingest,"CACHE",root/"cache"),patch.object(ingest,"RESULT",root/"results"),patch.object(ingest,"roster",return_value=["A","B"]),patch.object(ingest,"windows",return_value=span),patch.object(ingest.requests,"get",side_effect=[requests.ConnectionError(),response,response]) as get:
                self.assertEqual([r["status"] for r in ingest.reconcile(True)],["failed","unrequested"])
                self.assertEqual([r["status"] for r in ingest.reconcile(True)],["empty","empty"])
                self.assertEqual([r["status"] for r in ingest.reconcile(True)],["empty","empty"])
                self.assertEqual(get.call_count,3)
                attempts=pd.read_csv(ingest.CACHE/"attempts.csv")
                self.assertEqual(attempts.status.tolist(),["failed","empty","empty"])

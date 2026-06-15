"""Tests for Data & Integration — Module K.

Pure unit tests — no live DB. Covers:
- Tally XML parse (masters + vouchers) on a realistic sample
- group→account_type mapping incl. parent-chain fallback + unmapped flag
- Tally amount sign convention (negative = debit)
- dry-run preview: new vs duplicate, unbalanced detection, ready_to_commit
- webhook HMAC sign/verify round-trip, tamper + replay rejection, backoff curve
"""
import os
import sys
import time

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017/test")
os.environ.setdefault("DB_NAME", "test_erp")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.tally_parser import (
    parse_tally_xml, build_preview, map_group_to_type, map_voucher_type, _to_float,
)
from core.webhooks import sign_payload, verify_signature, backoff_delay


# ── A realistic (trimmed) Tally XML export ──
TALLY_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ENVELOPE>
 <BODY>
  <IMPORTDATA>
   <REQUESTDATA>
    <TALLYMESSAGE>
     <GROUP NAME="Sundry Debtors"><PARENT>Current Assets</PARENT></GROUP>
    </TALLYMESSAGE>
    <TALLYMESSAGE>
     <LEDGER NAME="ABC Traders"><PARENT>Sundry Debtors</PARENT><OPENINGBALANCE>15000.00</OPENINGBALANCE></LEDGER>
    </TALLYMESSAGE>
    <TALLYMESSAGE>
     <LEDGER NAME="Sales - Local"><PARENT>Sales Accounts</PARENT><OPENINGBALANCE>0</OPENINGBALANCE></LEDGER>
    </TALLYMESSAGE>
    <TALLYMESSAGE>
     <LEDGER NAME="Weird Custom Group Ledger"><PARENT>Some Custom Group</PARENT></LEDGER>
    </TALLYMESSAGE>
    <TALLYMESSAGE>
     <STOCKITEM NAME="Widget A"><BASEUNITS>Nos</BASEUNITS><OPENINGBALANCE>100</OPENINGBALANCE><OPENINGRATE>50</OPENINGRATE></STOCKITEM>
    </TALLYMESSAGE>
    <TALLYMESSAGE>
     <UNIT NAME="Nos"></UNIT>
    </TALLYMESSAGE>
    <TALLYMESSAGE>
     <VOUCHER VCHTYPE="Sales">
      <DATE>20240601</DATE>
      <VOUCHERNUMBER>S-001</VOUCHERNUMBER>
      <PARTYLEDGERNAME>ABC Traders</PARTYLEDGERNAME>
      <NARRATION>Sale of widgets</NARRATION>
      <ALLLEDGERENTRIES.LIST>
       <LEDGERNAME>ABC Traders</LEDGERNAME><AMOUNT>-11800.00</AMOUNT>
      </ALLLEDGERENTRIES.LIST>
      <ALLLEDGERENTRIES.LIST>
       <LEDGERNAME>Sales - Local</LEDGERNAME><AMOUNT>10000.00</AMOUNT>
      </ALLLEDGERENTRIES.LIST>
      <ALLLEDGERENTRIES.LIST>
       <LEDGERNAME>Output CGST</LEDGERNAME><AMOUNT>900.00</AMOUNT>
      </ALLLEDGERENTRIES.LIST>
      <ALLLEDGERENTRIES.LIST>
       <LEDGERNAME>Output SGST</LEDGERNAME><AMOUNT>900.00</AMOUNT>
      </ALLLEDGERENTRIES.LIST>
     </VOUCHER>
    </TALLYMESSAGE>
   </REQUESTDATA>
  </IMPORTDATA>
 </BODY>
</ENVELOPE>"""


class TestTallyParse:
    def setup_method(self):
        self.parsed = parse_tally_xml(TALLY_XML)

    def test_counts(self):
        assert len(self.parsed["groups"]) == 1
        assert len(self.parsed["ledgers"]) == 3
        assert len(self.parsed["stock_items"]) == 1
        assert len(self.parsed["units"]) == 1
        assert len(self.parsed["vouchers"]) == 1
        assert self.parsed["errors"] == []

    def test_ledger_mapping(self):
        by_name = {l["name"]: l for l in self.parsed["ledgers"]}
        assert by_name["ABC Traders"]["account_type"] == "ASSET"      # Sundry Debtors
        assert by_name["Sales - Local"]["account_type"] == "INCOME"   # Sales Accounts
        assert by_name["ABC Traders"]["opening_balance"] == 15000.0

    def test_voucher_lines_and_sign(self):
        v = self.parsed["vouchers"][0]
        assert v["voucher_type"] == "SALES"
        assert v["number"] == "S-001"
        lines = {l["ledger"]: l for l in v["lines"]}
        # negative AMOUNT → debit
        assert lines["ABC Traders"]["is_debit"] is True
        assert lines["ABC Traders"]["amount"] == 11800.0
        # positive → credit
        assert lines["Sales - Local"]["is_debit"] is False
        assert lines["Sales - Local"]["amount"] == 10000.0

    def test_voucher_balances(self):
        v = self.parsed["vouchers"][0]
        dr = sum(l["amount"] for l in v["lines"] if l["is_debit"])
        cr = sum(l["amount"] for l in v["lines"] if not l["is_debit"])
        assert abs(dr - cr) < 0.01   # 11800 == 10000 + 900 + 900


class TestPreview:
    def test_preview_new_and_unmapped(self):
        parsed = parse_tally_xml(TALLY_XML)
        preview = build_preview(parsed, existing_ledger_names=set())
        assert preview["ledgers_new"] == 3
        assert preview["ledgers_duplicate"] == 0
        # the custom-group ledger couldn't map → flagged
        names = [u["ledger"] for u in preview["unmapped_ledgers"]]
        assert "Weird Custom Group Ledger" in names
        # the sample voucher is balanced
        assert preview["unbalanced_vouchers"] == []
        assert preview["ready_to_commit"] is True

    def test_preview_detects_duplicates(self):
        parsed = parse_tally_xml(TALLY_XML)
        preview = build_preview(parsed, existing_ledger_names={"ABC Traders"})
        assert preview["ledgers_duplicate"] == 1
        assert preview["ledgers_new"] == 2

    def test_preview_flags_unbalanced(self):
        parsed = parse_tally_xml(TALLY_XML)
        # corrupt a line so the voucher no longer balances
        parsed["vouchers"][0]["lines"][1]["amount"] = 9999
        preview = build_preview(parsed, set())
        assert len(preview["unbalanced_vouchers"]) == 1
        assert preview["ready_to_commit"] is False


class TestMapping:
    def test_direct_group(self):
        assert map_group_to_type("Sales Accounts") == "INCOME"
        assert map_group_to_type("Current Liabilities") == "LIABILITY"
        assert map_group_to_type("Capital Account") == "EQUITY"

    def test_parent_chain_fallback(self):
        # unknown leaf, but a known ancestor in the chain
        assert map_group_to_type("My Subgroup", ["Direct Expenses"]) == "EXPENSE"

    def test_unmapped_defaults_asset(self):
        assert map_group_to_type("Totally Unknown") == "ASSET"

    def test_voucher_type_map(self):
        assert map_voucher_type("Sales") == "SALES"
        assert map_voucher_type("Receipt") == "RECEIPT"
        assert map_voucher_type("Whatever") == "JOURNAL"


class TestAmountParse:
    def test_negative(self):
        assert _to_float("-1,234.50") == -1234.5

    def test_with_suffix(self):
        assert _to_float("1234.50 Dr") == 1234.5

    def test_empty(self):
        assert _to_float("") == 0.0
        assert _to_float(None) == 0.0


class TestWebhookSigning:
    def test_sign_verify_round_trip(self):
        secret = "whsec_test"
        payload = {"event": "invoice.created", "id": "INV-1"}
        headers = sign_payload(secret, payload)
        body = headers["_body"]
        assert verify_signature(secret, body, headers["X-Webhook-Signature"],
                                headers["X-Webhook-Timestamp"]) is True

    def test_tampered_body_rejected(self):
        secret = "whsec_test"
        headers = sign_payload(secret, {"a": 1})
        assert verify_signature(secret, '{"a":2}', headers["X-Webhook-Signature"],
                                headers["X-Webhook-Timestamp"]) is False

    def test_wrong_secret_rejected(self):
        headers = sign_payload("right", {"a": 1})
        assert verify_signature("wrong", headers["_body"], headers["X-Webhook-Signature"],
                                headers["X-Webhook-Timestamp"]) is False

    def test_replay_old_timestamp_rejected(self):
        secret = "whsec_test"
        old_ts = int(time.time()) - 1000
        headers = sign_payload(secret, {"a": 1}, timestamp=old_ts)
        assert verify_signature(secret, headers["_body"], headers["X-Webhook-Signature"],
                                headers["X-Webhook-Timestamp"], tolerance_seconds=300) is False

    def test_backoff_curve(self):
        assert backoff_delay(1) == 5
        assert backoff_delay(2) == 10
        assert backoff_delay(3) == 20
        assert backoff_delay(4) == 40
        assert backoff_delay(20, cap=3600) == 3600   # capped

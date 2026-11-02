"""Test setup shared by the tests: temporary files instead of the GM's real ones. FG-EXIT-01 step 4 (2026-10-26):
authorized_request (the old bridge's HTTP token) and its saved AI mode went to archive/fg_exit_2026-10-26/ with it."""
import os, tempfile
# v0.7.51: tests never read the real rules cache (it holds the GM's purchased books); tests that need one set their own.
TEST_RULES_DB=os.path.join(tempfile.mkdtemp(),"rules.sqlite")
os.environ["MYTHASTRIA_RULES_DB"]=TEST_RULES_DB
# v0.7.60: ...nor the real stat-block plan cache
os.environ["MYTHASTRIA_PLANS_FILE"]=os.path.join(tempfile.mkdtemp(),"statblock_plans.json")

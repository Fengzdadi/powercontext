import os

# Integration tests run against a separate database. The switch happens here
# and only here: application code never reads EXAMRADAR_IT, so a shell that
# still has the flag set can never silently point the CLI or the server at
# the test database. conftest is imported before any examradar module, so
# get_settings() picks up the override.
if os.environ.get("EXAMRADAR_IT"):
    os.environ["SEEKDB_DATABASE"] = os.environ.get(
        "SEEKDB_TEST_DATABASE", "examradar_test")

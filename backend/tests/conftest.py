"""All automated tests are offline unless an individual test installs a fake transport."""
import os
import tempfile

_test_dir = tempfile.mkdtemp(prefix="zaowu-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_test_dir}/test.db"
os.environ["STORAGE_DIR"] = f"{_test_dir}/files"
os.environ["AHOLO_QUOTE_ENABLED"] = "false"

for name in ("DEEPSEEK_API_KEY", "AHOLO_API_KEY", "IMAGE_API_KEY", "IMAGE_PROVIDER", "ALIPAY_APP_ID"):
    os.environ[name] = ""

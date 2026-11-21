"""Tests never touch the real CRM file, the saved fx rate or the live 5U API, even with the team key exported."""
import os
import tempfile

os.environ["DB_PATH"] = ":memory:"
os.environ["FIVEU_API_KEY"] = ""
os.environ["FX_FILE"] = os.path.join(tempfile.mkdtemp(), "fx.json")

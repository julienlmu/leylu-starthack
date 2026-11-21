"""Tests never touch the real CRM file or the live 5U API, even with the team key exported."""
import os

os.environ["DB_PATH"] = ":memory:"
os.environ["FIVEU_API_KEY"] = ""

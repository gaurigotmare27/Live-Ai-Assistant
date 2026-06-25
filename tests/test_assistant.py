import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Setup mock GenAI client before importing the app to avoid credentials issues
mock_client = MagicMock()
mock_response = MagicMock()
mock_response.text = "Mocked AI Response"
mock_chat = MagicMock()
mock_chat.send_message.return_value = mock_response
mock_client.chats.create.return_value = mock_chat

with patch('google.genai.Client', return_value=mock_client):
    from server.main import app
    from server.database import Base, get_db
    from server.memory import ChatMessage, save_message, get_session_history, clear_session_history

# Setup in-memory database with StaticPool to share connection/data across threads
TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DATABASE_URL, 
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

class TestLiveAIAssistant(unittest.TestCase):
    def setUp(self):
        # Create all tables for each test
        Base.metadata.create_all(bind=test_engine)
        self.db = TestingSessionLocal()
        self.client = TestClient(app)

    def tearDown(self):
        # Close session and drop all tables
        self.db.close()
        Base.metadata.drop_all(bind=test_engine)

    def test_database_operations(self):
        session_id = "test-session-db"
        # Test save_message
        msg1 = save_message(self.db, session_id, role="user", content="Message 1")
        self.assertEqual(msg1.session_id, session_id)
        self.assertEqual(msg1.role, "user")
        self.assertEqual(msg1.content, "Message 1")

        # Test get_session_history returns correct order
        save_message(self.db, session_id, role="model", content="Message 2")
        history = get_session_history(self.db, session_id, limit=10)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].content, "Message 1")
        self.assertEqual(history[1].content, "Message 2")

    def test_get_session_history_limit_and_order(self):
        session_id = "test-session-limit"
        # Insert 12 messages
        for i in range(1, 13):
            # Use distinct roles or content to identify
            role = "user" if i % 2 != 0 else "model"
            save_message(self.db, session_id, role=role, content=f"Msg {i}")

        # Fetch history with limit of 10.
        # It should fetch the LATEST 10 messages (Msg 3 to Msg 12)
        # and return them in ascending order of time (Msg 3, Msg 4, ..., Msg 12)
        history = get_session_history(self.db, session_id, limit=10)
        self.assertEqual(len(history), 10)
        self.assertEqual(history[0].content, "Msg 3")
        self.assertEqual(history[-1].content, "Msg 12")

    def test_clear_session_history(self):
        session_id = "test-session-clear"
        save_message(self.db, session_id, role="user", content="Hello")
        save_message(self.db, session_id, role="model", content="Hi")
        
        history = get_session_history(self.db, session_id, limit=10)
        self.assertEqual(len(history), 2)

        clear_session_history(self.db, session_id)
        history = get_session_history(self.db, session_id, limit=10)
        self.assertEqual(len(history), 0)

    def test_rest_endpoints(self):
        # 1. Health check
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers.get("content-type", ""))
        self.assertIn("Quantum AI Console", response.text)

        # 2. Chat endpoint
        payload = {"session_id": "test-session-rest", "message": "Hello Agent"}
        response = self.client.post("/api/chat", json=payload)
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertEqual(json_data["session_id"], "test-session-rest")
        self.assertEqual(json_data["response"], "Mocked AI Response")

        # Verify message was stored in database
        history = get_session_history(self.db, "test-session-rest", limit=10)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].role, "user")
        self.assertEqual(history[0].content, "Hello Agent")
        self.assertEqual(history[1].role, "model")
        self.assertEqual(history[1].content, "Mocked AI Response")

        # 3. Clear session endpoint
        response = self.client.delete("/api/chat/test-session-rest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")

        # Verify messages cleared
        history = get_session_history(self.db, "test-session-rest", limit=10)
        self.assertEqual(len(history), 0)

    def test_websocket_endpoint(self):
        session_id = "test-session-ws"
        with self.client.websocket_connect(f"/ws/live/{session_id}") as websocket:
            # Receive initial connection message
            data = websocket.receive_json()
            self.assertEqual(data["type"], "status")
            self.assertIn("Connected to session", data["content"])

            # Send a text message
            websocket.send_text("Hello via WebSocket")

            # Receive the response
            data = websocket.receive_json()
            self.assertEqual(data["type"], "response")
            self.assertEqual(data["content"], "Mocked AI Response")

        # Verify interaction was saved in database
        history = get_session_history(self.db, session_id, limit=10)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].role, "user")
        self.assertEqual(history[0].content, "Hello via WebSocket")
        self.assertEqual(history[1].role, "model")
        self.assertEqual(history[1].content, "Mocked AI Response")

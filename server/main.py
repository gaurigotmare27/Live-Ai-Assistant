import os
from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from server.database import engine, Base, get_db
from server.agent import LiveAIAgent
from server.memory import clear_session_history

# Load environment variables
load_dotenv()

# Initialize database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Live AI Assistant API",
    description="Real-time Web Search, Tool Calling, and Memory-Enabled AI Assistant Service.",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Agent orchestrator
agent = LiveAIAgent()

# Pydantic request models
class ChatRequest(BaseModel):
    session_id: str
    message: str

class ChatResponse(BaseModel):
    session_id: str
    response: str

@app.get("/")
def read_root():
    return {"status": "healthy", "service": "Live AI Assistant API"}

@app.post("/api/chat", response_model=ChatResponse)
def rest_chat_endpoint(payload: ChatRequest, db: Session = Depends(get_db)):
    """Standard HTTP POST endpoint for single turn chat interaction (with history and tools)."""
    try:
        response_text = agent.run(
            session_id=payload.session_id,
            user_input=payload.message,
            db=db
        )
        return ChatResponse(session_id=payload.session_id, response=response_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent loop execution failed: {str(e)}")

@app.delete("/api/chat/{session_id}")
def delete_session(session_id: str, db: Session = Depends(get_db)):
    """Endpoint to clear memory history for a given session."""
    try:
        clear_session_history(db, session_id)
        return {"status": "success", "message": f"Cleared memory for session {session_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear session history: {str(e)}")

@app.websocket("/ws/live/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str, db: Session = Depends(get_db)):
    """
    WebSocket endpoint for real-time audio/video/text streaming assistant sessions.
    Establishes connection and handles real-time message relaying.
    """
    await websocket.accept()
    print(f"WebSocket session established: {session_id}")
    
    try:
        # Send initial connection success message
        await websocket.send_json({
            "type": "status", 
            "content": f"Connected to session {session_id}. Ready for live stream."
        })
        
        while True:
            # Receive text or binary data from client
            data = await websocket.receive_text()
            
            # Placeholder for parsing streaming audio/video frames or text frames
            # In a full live implementation, we'd pipe the WebSocket stream directly
            # to/from the Gemini Multimodal Live API
            
            # Simple Echo/Processing Stub
            response_text = agent.run(
                session_id=session_id,
                user_input=data,
                db=db
            )
            
            # Send result back to client
            await websocket.send_json({
                "type": "response",
                "content": response_text
            })
            
    except WebSocketDisconnect:
        print(f"WebSocket session disconnected: {session_id}")
    except Exception as e:
        print(f"WebSocket error in session {session_id}: {str(e)}")
        try:
            await websocket.close()
        except:
            pass

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("server.main:app", host=host, port=port, reload=True)

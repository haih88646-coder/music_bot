from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from typing import Optional
import uvicorn
import base64
import os
import tempfile
from datetime import datetime
from contextlib import asynccontextmanager

# Define request models
class MusicRequest(BaseModel):
    prompt: str
    style: str = "lofi"
    mood: str = "calm"
    tempo: str = "medium"
    instrument: str = "guitar"
    duration: int = 30

class MusicResponse(BaseModel):
    success: bool
    title: str
    style: str
    mood: str
    tempo: str
    instrument: str
    duration: int
    audio_url: Optional[str] = None
    audio_base64: Optional[str] = None
    error: Optional[str] = None

# In-memory storage for generated tracks
generated_tracks = {}
track_counter = 1

# Mock audio generation
def generate_mock_audio(prompt: str, duration: int) -> bytes:
    """Generate mock audio data for demonstration"""
    sample_rate = 44100
    num_channels = 2
    bits_per_sample = 16
    num_samples = sample_rate * duration
    
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    subchunk2_size = num_samples * num_channels * bits_per_sample // 8
    
    wav_header = bytearray()
    wav_header.extend(b'RIFF')
    wav_header.extend((36 + subchunk2_size).to_bytes(4, 'little'))
    wav_header.extend(b'WAVE')
    wav_header.extend(b'fmt ')
    wav_header.extend((16).to_bytes(4, 'little'))
    wav_header.extend((1).to_bytes(2, 'little'))
    wav_header.extend(num_channels.to_bytes(2, 'little'))
    wav_header.extend(sample_rate.to_bytes(4, 'little'))
    wav_header.extend(byte_rate.to_bytes(4, 'little'))
    wav_header.extend(block_align.to_bytes(2, 'little'))
    wav_header.extend(bits_per_sample.to_bytes(2, 'little'))
    wav_header.extend(b'data')
    wav_header.extend(subchunk2_size.to_bytes(4, 'little'))
    
    silent_data = bytes([0] * subchunk2_size)
    return bytes(wav_header) + silent_data

def generate_title(prompt: str) -> str:
    """Generate a track title from the prompt"""
    words = prompt.split()[:5]
    if len(words) < 3:
        return " ".join(words).title() if words else "AI Generated Track"
    return " ".join(words[:3]).title() + "..."

# Lifespan context manager for cleanup
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🎵 MelodyAI API starting...")
    yield
    # Shutdown
    print("🧹 Cleaning up temporary files...")
    for track_id, track_info in generated_tracks.items():
        file_path = track_info.get("file_path")
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass

# Initialize FastAPI app with lifespan
app = FastAPI(
    title="MelodyAI Music Generator API",
    description="AI Music Generation API",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "MelodyAI Music Generator",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/generate", response_model=MusicResponse)
async def generate_music(request: MusicRequest):
    try:
        if request.duration < 5 or request.duration > 120:
            raise HTTPException(status_code=400, detail="Duration must be between 5 and 120 seconds")
        
        global track_counter
        track_id = f"track_{track_counter}"
        track_counter += 1
        
        title = generate_title(request.prompt)
        audio_data = generate_mock_audio(request.prompt, request.duration)
        
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
            tmp_file.write(audio_data)
            tmp_file_path = tmp_file.name
        
        generated_tracks[track_id] = {
            "id": track_id,
            "title": title,
            "prompt": request.prompt,
            "style": request.style,
            "mood": request.mood,
            "tempo": request.tempo,
            "instrument": request.instrument,
            "duration": request.duration,
            "file_path": tmp_file_path,
            "created_at": datetime.now().isoformat()
        }
        
        audio_base64 = base64.b64encode(audio_data).decode('utf-8')
        
        return MusicResponse(
            success=True,
            title=title,
            style=request.style.title(),
            mood=request.mood.title(),
            tempo=request.tempo.title(),
            instrument=request.instrument.title(),
            duration=request.duration,
            audio_url=f"/audio/{track_id}",
            audio_base64=audio_base64
        )
        
    except Exception as e:
        return MusicResponse(
            success=False,
            title="Error",
            style="",
            mood="",
            tempo="",
            instrument="",
            duration=0,
            error=str(e)
        )

@app.get("/audio/{track_id}")
async def get_audio(track_id: str):
    if track_id not in generated_tracks:
        raise HTTPException(status_code=404, detail="Track not found")
    
    track_info = generated_tracks[track_id]
    file_path = track_info["file_path"]
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Audio file not found")
    
    return FileResponse(
        path=file_path,
        media_type="audio/wav",
        filename=f"melodyai_{track_id}.wav"
    )

@app.get("/")
async def root():
    return {
        "message": "MelodyAI Music Generator API",
        "endpoints": {
            "GET /health": "Health check",
            "POST /generate": "Generate music",
            "GET /audio/{id}": "Get audio",
            "GET /docs": "API documentation"
        }
    }

# Run the application
if __name__ == "__main__":
    print("🎵 Starting MelodyAI Music Generator API...")
    print("📍 API URL: http://localhost:8000")
    print("📚 Documentation: http://localhost:8000/docs")
    print("🌐 Frontend should be at: http://localhost:3000")
    print("\nEndpoints:")
    print("  POST /generate - Generate music from text")
    print("  GET  /audio/{id} - Download generated audio")
    print("  GET  /health - Check API status")
    print("\nPress Ctrl+C to stop the server")
    
    uvicorn.run(
        "FastAPI:app",  # As import string to avoid warning
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
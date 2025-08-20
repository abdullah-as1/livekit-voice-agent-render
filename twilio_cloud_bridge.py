"""
Simplified Twilio bridge for LiveKit Cloud Agents
This creates rooms and lets LiveKit Cloud Agents handle the agent deployment
"""

import asyncio
import json
import logging
import base64
import audioop
import uuid
from typing import Dict
from fastapi import FastAPI, WebSocket, Form, Request
from fastapi.responses import PlainTextResponse
from twilio.twiml.voice_response import VoiceResponse
from livekit import api, rtc
import os
from dotenv import load_dotenv

load_dotenv(".env.local")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Twilio LiveKit Cloud Bridge")

# LiveKit configuration
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")
LIVEKIT_URL = os.getenv("LIVEKIT_URL")
PUBLIC_URL = os.getenv("PUBLIC_URL", "ws://localhost:8000")

# Store active connections
active_connections: Dict[str, dict] = {}

class TwilioCloudBridge:
    """
    Simplified bridge that creates LiveKit rooms for Cloud Agents
    """
    
    def __init__(self, call_sid: str):
        self.call_sid = call_sid
        self.room_name = f"twilio-call-{call_sid}"
        self.livekit_api = api.LiveKitAPI(
            url=LIVEKIT_URL,
            api_key=LIVEKIT_API_KEY,
            api_secret=LIVEKIT_API_SECRET,
        )
        self.room = None
        
    async def create_room(self):
        """Create a LiveKit room for the call"""
        try:
            # Create room
            room_info = await self.livekit_api.room.create_room(
                api.CreateRoomRequest(name=self.room_name)
            )
            logger.info(f"Created room: {self.room_name}")
            
            # Create participant token for Twilio
            token = api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
            token.with_identity(f"twilio-{self.call_sid}")
            token.with_name(f"Twilio Call {self.call_sid}")
            token.with_grants(api.VideoGrants(
                room_join=True,
                room=self.room_name,
            ))
            
            return {
                "room_name": self.room_name,
                "token": token.to_jwt(),
                "url": LIVEKIT_URL
            }
            
        except Exception as e:
            logger.error(f"Failed to create room: {e}")
            return None

@app.post("/twilio/voice")
async def handle_voice_webhook(request: Request):
    """Handle incoming Twilio voice webhook"""
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    
    logger.info(f"Incoming call: {call_sid}")
    
    # Create LiveKit room for this call
    bridge = TwilioCloudBridge(call_sid)
    room_info = await bridge.create_room()
    
    if not room_info:
        # Fallback response
        response = VoiceResponse()
        response.say("Sorry, there was an error connecting your call.")
        return PlainTextResponse(str(response), media_type="application/xml")
    
    # Store connection info
    active_connections[call_sid] = {
        "room_name": room_info["room_name"],
        "token": room_info["token"],
        "created_at": asyncio.get_event_loop().time()
    }
    
    # Create TwiML response to start media stream
    response = VoiceResponse()
    response.say("Connecting you to our AI assistant. Please wait.")
    
    # Start media stream
    start = response.start()
    start.stream(
        url=f"wss://{request.headers.get('host', 'localhost')}/twilio/media/{call_sid}",
        track="both_tracks"
    )
    
    return PlainTextResponse(str(response), media_type="application/xml")

@app.websocket("/twilio/media/{call_sid}")
async def handle_media_stream(websocket: WebSocket, call_sid: str):
    """Handle Twilio media stream WebSocket"""
    await websocket.accept()
    logger.info(f"Media stream connected for call: {call_sid}")
    
    # Get room info
    room_info = active_connections.get(call_sid)
    if not room_info:
        logger.error(f"No room info found for call: {call_sid}")
        await websocket.close()
        return
    
    try:
        # Connect to LiveKit room
        room = rtc.Room()
        
        async def on_participant_connected(participant: rtc.RemoteParticipant):
            logger.info(f"Participant connected: {participant.identity}")
        
        async def on_track_subscribed(track: rtc.Track, publication: rtc.TrackPublication, participant: rtc.RemoteParticipant):
            logger.info(f"Track subscribed: {track.kind}")
            if track.kind == rtc.TrackKind.KIND_AUDIO:
                # Handle audio from LiveKit agent
                audio_stream = rtc.AudioStream(track)
                async for frame in audio_stream:
                    # Convert and send to Twilio
                    audio_data = frame.data.tobytes()
                    # Convert to mulaw and base64 encode
                    mulaw_data = audioop.lin2ulaw(audio_data, 2)
                    b64_audio = base64.b64encode(mulaw_data).decode()
                    
                    media_message = {
                        "event": "media",
                        "streamSid": call_sid,
                        "media": {
                            "payload": b64_audio
                        }
                    }
                    await websocket.send_text(json.dumps(media_message))
        
        room.on("participant_connected", on_participant_connected)
        room.on("track_subscribed", on_track_subscribed)
        
        # Connect to room
        await room.connect(LIVEKIT_URL, room_info["token"])
        logger.info(f"Connected to LiveKit room: {room_info['room_name']}")
        
        # Create audio source for incoming Twilio audio
        audio_source = rtc.AudioSource(24000, 1)  # 24kHz mono
        track = rtc.LocalAudioTrack.create_audio_track("twilio-audio", audio_source)
        options = rtc.TrackPublishOptions()
        options.source = rtc.TrackSource.SOURCE_MICROPHONE
        
        publication = await room.local_participant.publish_track(track, options)
        logger.info("Published audio track to LiveKit")
        
        # Handle incoming Twilio media
        async for message in websocket.iter_text():
            try:
                data = json.loads(message)
                
                if data.get("event") == "media":
                    # Decode audio from Twilio
                    payload = data["media"]["payload"]
                    audio_data = base64.b64decode(payload)
                    
                    # Convert from mulaw to PCM
                    pcm_data = audioop.ulaw2lin(audio_data, 2)
                    
                    # Create audio frame and push to LiveKit
                    frame = rtc.AudioFrame.create(24000, 1, len(pcm_data) // 2)
                    frame.data[:] = pcm_data
                    
                    await audio_source.capture_frame(frame)
                    
                elif data.get("event") == "start":
                    logger.info("Twilio media stream started")
                    
                elif data.get("event") == "stop":
                    logger.info("Twilio media stream stopped")
                    break
                    
            except Exception as e:
                logger.error(f"Error processing media: {e}")
                continue
                
    except Exception as e:
        logger.error(f"Error in media stream: {e}")
    finally:
        # Cleanup
        if call_sid in active_connections:
            del active_connections[call_sid]
        
        try:
            await room.disconnect()
        except:
            pass
        
        await websocket.close()
        logger.info(f"Media stream closed for call: {call_sid}")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy", 
        "active_calls": len(active_connections),
        "livekit_url": LIVEKIT_URL,
        "service": "twilio-livekit-bridge"
    }

@app.get("/")
async def root():
    """Root endpoint with service info"""
    return {
        "service": "Twilio LiveKit Cloud Bridge",
        "version": "1.0.0",
        "deployment": "LiveKit Cloud Agents",
        "endpoints": {
            "voice_webhook": "/twilio/voice",
            "media_stream": "/twilio/media/{call_sid}",
            "health": "/health"
        }
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=port,
        log_level="info"
    )

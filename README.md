# LiveKit Voice Agent - Render Deployment

This is a clean deployment package for the LiveKit Voice Agent on Render.

## Quick Start

1. Deploy on Render.com
2. Add environment variables through Render dashboard
3. Update Twilio webhook URL

## Environment Variables Required

Add these in Render dashboard:
- `LIVEKIT_API_KEY` - Your LiveKit API key
- `LIVEKIT_API_SECRET` - Your LiveKit API secret
- `LIVEKIT_URL` - Your LiveKit WebSocket URL
- `TWILIO_ACCOUNT_SID` - Your Twilio Account SID
- `TWILIO_AUTH_TOKEN` - Your Twilio Auth Token
- `TWILIO_PHONE_NUMBER` - Your Twilio phone number
- `PORT=10000` - Port for the service

## Deployment Steps

1. Go to [Render.com](https://render.com)
2. Sign up/Login with GitHub
3. Click "New +" → "Web Service"
4. Connect this GitHub repository
5. Render will auto-detect `render.yaml`
6. Add environment variables listed above
7. Click "Create Web Service"

## After Deployment

1. Get your Render URL (e.g., `https://livekit-voice-agent-xyz.onrender.com`)
2. Update your Twilio webhook to: `https://your-render-url.onrender.com/twilio/voice`
3. Test by calling your Twilio number

## Endpoints

- `/health` - Health check
- `/twilio/voice` - Twilio voice webhook
- `/twilio/media/{call_sid}` - Media stream WebSocket

## Support

- Render Documentation: https://render.com/docs
- LiveKit Documentation: https://docs.livekit.io
- Twilio Documentation: https://www.twilio.com/docs

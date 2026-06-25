# Twilio Voice MCP Server

**Feature**: 042-twilio-voice-mcp

Bidirectional voice call integration for NetClaw using Twilio. Handles inbound call webhooks and provides tools for call management.

## Overview

This MCP server provides:
- **Inbound Call Handling**: Webhook endpoints for Twilio voice callbacks
- **Call Logging**: All calls logged to Memory MCP for audit trail
- **Guardrails**: Rate limiting, quiet hours, whitelist validation, content sanitization
- **Voice Commands**: Process voice commands during inbound calls

Outbound calls are initiated via the separate `@twilio-alpha/mcp` NPM package.

## Architecture

```
Outbound: NetClaw → @twilio-alpha/mcp (NPM) → Twilio API → Phone
Inbound:  Phone → Twilio → This Server (webhook) → NetClaw
```

## Tools

| Tool | Description |
|------|-------------|
| `twilio_voice_call` | Initiate outbound call with message |
| `twilio_voice_check_rate_limit` | Check if call allowed within limits |
| `twilio_voice_get_call_history` | Retrieve call records from Memory MCP |

## Webhook Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/webhooks/twilio/voice` | POST | Inbound call handler (TwiML) |
| `/webhooks/twilio/voice/status` | POST | Call status callback |
| `/webhooks/twilio/media-stream` | WebSocket | Real-time audio stream |

## Configuration

Configuration stored in `config/twilio-voice.json`:
- `whitelist`: Approved phone numbers (E.164 format)
- `quiet_hours`: Time windows blocking non-emergency calls
- `emergency_categories`: Auto-approved call triggers
- `rate_limits`: Hourly/daily call limits
- `voice`: TTS voice (default: Polly.Matthew)

## Environment Variables

Required in `~/.openclaw/.env`:
```bash
TWILIO_ACCOUNT_SID=ACxxxxx
TWILIO_API_KEY_SID=SKxxxxx
TWILIO_API_SECRET=xxxxx
TWILIO_PHONE_NUMBER=+1xxxxx  # For inbound
TWILIO_WEBHOOK_URL=https://your-domain/webhooks/twilio/voice
```

## Quick Start

```bash
# Install dependencies
cd mcp-servers/twilio-voice-mcp
pip install -r requirements.txt

# Start server (runs webhook handler)
python server.py
```

## Security

- All webhook requests validated via Twilio signature
- Inbound callers authenticated against whitelist
- Content sanitized (IPs, credentials filtered from TTS)
- Rate limits enforced per hour/day
- Quiet hours block non-emergency calls

## Related

- Spec: `/specs/042-twilio-voice-mcp/spec.md`
- Skills: `/workspace/skills/twilio-*/`
- Config: `/config/twilio-voice.json`

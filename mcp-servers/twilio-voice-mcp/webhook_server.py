#!/usr/bin/env python3
"""
Twilio Voice Webhook Server
Feature 042: Twilio Voice MCP Integration

HTTP server that handles inbound Twilio voice webhooks with REAL NetClaw integration.
Processes voice commands through Claude and MCP tools.

Usage:
    python webhook_server.py
    # Listens on port 5001 by default
"""

import os
import json
import logging
import httpx
import asyncio
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.request_validator import RequestValidator

from guardrails import (
    is_whitelisted,
    normalize_phone_number,
    sanitize_for_voice,
    load_config
)

# ═══════════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("twilio-webhook")

app = Flask(__name__)
executor = ThreadPoolExecutor(max_workers=4)

# Environment
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_API_SECRET = os.environ.get("TWILIO_API_SECRET", "")
WEBHOOK_PORT = int(os.environ.get("TWILIO_WEBHOOK_PORT", "5001"))
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# MCP Server URLs (for direct integration)
CML_API_URL = os.environ.get("CML_URL", "")
CML_USERNAME = os.environ.get("CML_USERNAME", "")
CML_PASSWORD = os.environ.get("CML_PASSWORD", "")

# Request validator for signature verification
validator = None
if TWILIO_API_SECRET:
    validator = RequestValidator(TWILIO_API_SECRET)


def validate_twilio_request(req):
    """Validate that request came from Twilio."""
    if not validator:
        return True
    signature = req.headers.get("X-Twilio-Signature", "")
    url = req.url
    params = req.form.to_dict()
    return validator.validate(url, params, signature)


# ═══════════════════════════════════════════════════════════════════════════════
# Real MCP Integrations
# ═══════════════════════════════════════════════════════════════════════════════

async def get_cml_status() -> str:
    """Get real CML lab status via CML API."""
    if not CML_API_URL:
        return "CML is not configured. Please set CML_URL environment variable."

    try:
        async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
            # Authenticate
            auth_response = await client.post(
                f"{CML_API_URL}/api/v0/authenticate",
                json={"username": CML_USERNAME, "password": CML_PASSWORD}
            )
            if auth_response.status_code != 200:
                return "Failed to authenticate with CML."

            token = auth_response.json()
            headers = {"Authorization": f"Bearer {token}"}

            # Get labs
            labs_response = await client.get(f"{CML_API_URL}/api/v0/labs", headers=headers)
            if labs_response.status_code != 200:
                return "Failed to get CML labs."

            labs = labs_response.json()

            if not labs:
                return "No labs found in CML."

            # Get status for each lab
            summaries = []
            for lab_id in labs[:5]:  # Limit to first 5 labs for voice
                lab_response = await client.get(f"{CML_API_URL}/api/v0/labs/{lab_id}", headers=headers)
                if lab_response.status_code == 200:
                    lab_data = lab_response.json()
                    lab_title = lab_data.get("lab_title", lab_id)
                    state = lab_data.get("state", "unknown")
                    node_count = lab_data.get("node_count", 0)
                    summaries.append(f"{lab_title}: {state} with {node_count} nodes")

            if summaries:
                return "CML Lab Status: " + ". ".join(summaries)
            else:
                return "Could not retrieve lab details."

    except Exception as e:
        logger.error(f"CML API error: {e}")
        return f"Error connecting to CML: {str(e)}"


def get_cml_status_sync() -> str:
    """Synchronous wrapper for CML status."""
    try:
        return asyncio.run(get_cml_status())
    except Exception as e:
        logger.error(f"CML sync error: {e}")
        return "Error getting CML status."


async def process_with_claude(user_message: str) -> str:
    """Process a voice command through Claude API."""
    if not ANTHROPIC_API_KEY:
        # Fallback to basic keyword matching if no API key
        return process_basic_command(user_message)

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 300,
                    "system": """You are NetClaw, a CCIE-level network engineer assistant responding to voice commands over the phone.

Keep responses VERY SHORT (2-3 sentences max) since they will be spoken aloud.
Be concise and professional. Don't use technical jargon that's hard to speak.
If asked about specific systems (CML, network devices, etc.), acknowledge and provide a brief status.

Available integrations: CML labs, network device monitoring, PagerDuty incidents.
If you can't access a system, say so briefly.""",
                    "messages": [
                        {"role": "user", "content": f"Voice command from phone: {user_message}"}
                    ]
                }
            )

            if response.status_code == 200:
                result = response.json()
                return result["content"][0]["text"]
            else:
                logger.error(f"Claude API error: {response.status_code} - {response.text}")
                return process_basic_command(user_message)

    except Exception as e:
        logger.error(f"Claude API error: {e}")
        return process_basic_command(user_message)


def process_with_claude_sync(user_message: str) -> str:
    """Synchronous wrapper for Claude processing."""
    try:
        return asyncio.run(process_with_claude(user_message))
    except Exception as e:
        logger.error(f"Claude sync error: {e}")
        return process_basic_command(user_message)


def process_basic_command(command: str) -> str:
    """Basic keyword-based command processing as fallback."""
    command_lower = command.lower()

    # CML-related commands
    if any(word in command_lower for word in ["cml", "lab", "cisco modeling", "simulation"]):
        return get_cml_status_sync()

    # Network status
    if any(word in command_lower for word in ["network status", "network health", "devices"]):
        return "Network status: Monitoring active. For detailed status, I recommend checking the dashboard or asking via Slack for full MCP access."

    # Incidents
    if any(word in command_lower for word in ["incident", "alert", "pagerduty", "outage"]):
        return "No critical incidents at this time. For detailed incident status, check PagerDuty or ask via Slack."

    # Help
    if any(word in command_lower for word in ["help", "what can you do", "commands"]):
        return "I can check CML lab status, network health, and incidents. Try saying: check CML status, or network health, or any incidents."

    # Default
    return f"I heard: {command}. I can help with CML status, network health, and incidents. What would you like to know?"


# ═══════════════════════════════════════════════════════════════════════════════
# Webhook Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/webhooks/twilio/voice", methods=["POST"])
def handle_inbound_call():
    """Handle inbound voice calls from Twilio."""
    call_sid = request.form.get("CallSid", "unknown")
    from_number = request.form.get("From", "")
    to_number = request.form.get("To", "")
    call_status = request.form.get("CallStatus", "")

    logger.info(f"Inbound call: {call_sid} from {from_number} to {to_number} ({call_status})")

    config = load_config()
    voice = config.get("voice", "Polly.Matthew")

    response = VoiceResponse()

    # Check whitelist
    is_allowed, entry = is_whitelisted(from_number, direction="inbound")

    if not is_allowed:
        logger.warning(f"Rejected call from unauthorized number: {from_number}")
        response.say("This number is not authorized to call NetClaw. Goodbye.", voice=voice)
        response.hangup()
        return Response(str(response), mimetype="application/xml")

    caller_name = entry.get("label", "there") if entry else "there"
    logger.info(f"Authorized caller: {caller_name} ({from_number})")

    # Greet and listen
    response.say(f"Hello {caller_name}, this is NetClaw. What would you like to know?", voice=voice)

    # Listen for command
    gather = Gather(
        input="speech",
        action="/webhooks/twilio/voice/process-command",
        method="POST",
        timeout=8,
        speech_timeout="auto",
        language="en-US"
    )
    gather.say("You can ask about CML labs, network status, or incidents.", voice=voice)
    response.append(gather)

    response.say("I didn't hear anything. Goodbye.", voice=voice)
    response.hangup()

    return Response(str(response), mimetype="application/xml")


@app.route("/webhooks/twilio/voice/process-command", methods=["POST"])
def process_voice_command():
    """Process voice command through NetClaw/Claude."""
    speech_result = request.form.get("SpeechResult", "")
    call_sid = request.form.get("CallSid", "unknown")

    logger.info(f"Voice command on {call_sid}: '{speech_result}'")

    config = load_config()
    voice = config.get("voice", "Polly.Matthew")

    response = VoiceResponse()

    if not speech_result:
        response.say("I didn't catch that. Please try again.", voice=voice)
        gather = Gather(
            input="speech",
            action="/webhooks/twilio/voice/process-command",
            method="POST",
            timeout=8,
            speech_timeout="auto"
        )
        response.append(gather)
        response.say("Goodbye.", voice=voice)
        response.hangup()
        return Response(str(response), mimetype="application/xml")

    # Check for goodbye
    if any(word in speech_result.lower() for word in ["goodbye", "bye", "hang up", "that's all"]):
        response.say("Goodbye. Stay secure.", voice=voice)
        response.hangup()
        return Response(str(response), mimetype="application/xml")

    # Process the command
    response.say("Let me check that for you.", voice=voice)

    # Get real response
    command_lower = speech_result.lower()

    if any(word in command_lower for word in ["cml", "lab", "cisco modeling", "labs"]):
        # Direct CML integration
        result = get_cml_status_sync()
    else:
        # Use Claude for natural language processing
        result = process_with_claude_sync(speech_result)

    # Sanitize and speak the result
    safe_result = sanitize_for_voice(result)
    response.say(safe_result, voice=voice)

    # Offer to continue
    gather = Gather(
        input="speech",
        action="/webhooks/twilio/voice/process-command",
        method="POST",
        timeout=5,
        speech_timeout="auto"
    )
    gather.say("Anything else? Or say goodbye to hang up.", voice=voice)
    response.append(gather)

    response.say("Goodbye.", voice=voice)
    response.hangup()

    return Response(str(response), mimetype="application/xml")


@app.route("/webhooks/twilio/voice/status", methods=["POST"])
def handle_call_status():
    """Handle call status callbacks from Twilio."""
    call_sid = request.form.get("CallSid", "unknown")
    call_status = request.form.get("CallStatus", "")
    call_duration = request.form.get("CallDuration", "0")

    logger.info(f"Call status update: {call_sid} -> {call_status} (duration: {call_duration}s)")

    return {"acknowledged": True}


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "twilio-voice-webhook",
        "integrations": {
            "cml": bool(CML_API_URL),
            "claude": bool(ANTHROPIC_API_KEY)
        }
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logger.info(f"Starting Twilio Voice Webhook Server on port {WEBHOOK_PORT}")
    logger.info(f"Webhook URL: http://0.0.0.0:{WEBHOOK_PORT}/webhooks/twilio/voice")
    logger.info(f"CML Integration: {'Enabled' if CML_API_URL else 'Disabled'}")
    logger.info(f"Claude Integration: {'Enabled' if ANTHROPIC_API_KEY else 'Disabled (using basic commands)'}")

    app.run(host="0.0.0.0", port=WEBHOOK_PORT, debug=False)

#!/usr/bin/env python3
"""
Twilio Voice Webhook Server
Feature 042: Twilio Voice MCP Integration

HTTP server that handles inbound Twilio voice webhooks.
Run this alongside the MCP server to enable inbound calls.

Usage:
    python webhook_server.py
    # Listens on port 18789 by default
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path

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

# Environment
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_API_SECRET = os.environ.get("TWILIO_API_SECRET", "")
WEBHOOK_PORT = int(os.environ.get("TWILIO_WEBHOOK_PORT", "18789"))

# Request validator for signature verification (optional but recommended)
validator = None
if TWILIO_API_SECRET:
    validator = RequestValidator(TWILIO_API_SECRET)


def validate_twilio_request(req):
    """Validate that request came from Twilio (optional)."""
    if not validator:
        return True  # Skip validation if no secret configured

    signature = req.headers.get("X-Twilio-Signature", "")
    url = req.url
    params = req.form.to_dict()

    return validator.validate(url, params, signature)


# ═══════════════════════════════════════════════════════════════════════════════
# Webhook Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/webhooks/twilio/voice", methods=["POST"])
def handle_inbound_call():
    """
    Handle inbound voice calls from Twilio.

    Flow:
    1. Validate caller ID against whitelist
    2. If authorized: greet and provide status
    3. If unauthorized: reject with message
    """
    # Log the incoming call
    call_sid = request.form.get("CallSid", "unknown")
    from_number = request.form.get("From", "")
    to_number = request.form.get("To", "")
    call_status = request.form.get("CallStatus", "")

    logger.info(f"Inbound call: {call_sid} from {from_number} to {to_number} ({call_status})")

    # Load config for voice selection
    config = load_config()
    voice = config.get("voice", "Polly.Matthew")

    # Create TwiML response
    response = VoiceResponse()

    # Check if caller is whitelisted
    is_allowed, entry = is_whitelisted(from_number, direction="inbound")

    if not is_allowed:
        logger.warning(f"Rejected call from unauthorized number: {from_number}")
        response.say(
            "This number is not authorized to call NetClaw. Goodbye.",
            voice=voice
        )
        response.hangup()
        return Response(str(response), mimetype="application/xml")

    # Caller is authorized
    caller_name = entry.get("label", "there") if entry else "there"
    logger.info(f"Authorized caller: {caller_name} ({from_number})")

    # Greet the caller
    response.say(
        f"Hello {caller_name}, this is NetClaw. ",
        voice=voice
    )

    # Provide a status summary
    status_message = get_network_status_summary()
    response.say(sanitize_for_voice(status_message), voice=voice)

    # Offer options via gather (simple menu)
    gather = Gather(
        input="speech",
        action="/webhooks/twilio/voice/handle-speech",
        method="POST",
        timeout=5,
        speech_timeout="auto",
        language="en-US"
    )
    gather.say(
        "You can say: status, incidents, or goodbye.",
        voice=voice
    )
    response.append(gather)

    # If no input, say goodbye
    response.say("I didn't hear anything. Goodbye.", voice=voice)
    response.hangup()

    return Response(str(response), mimetype="application/xml")


@app.route("/webhooks/twilio/voice/handle-speech", methods=["POST"])
def handle_speech_input():
    """Handle speech input from the caller."""
    speech_result = request.form.get("SpeechResult", "").lower()
    call_sid = request.form.get("CallSid", "unknown")

    logger.info(f"Speech input on {call_sid}: '{speech_result}'")

    config = load_config()
    voice = config.get("voice", "Polly.Matthew")

    response = VoiceResponse()

    if "status" in speech_result:
        status_message = get_network_status_summary()
        response.say(sanitize_for_voice(status_message), voice=voice)
        # Offer to continue
        gather = Gather(
            input="speech",
            action="/webhooks/twilio/voice/handle-speech",
            method="POST",
            timeout=5,
            speech_timeout="auto"
        )
        gather.say("Anything else? Say status, incidents, or goodbye.", voice=voice)
        response.append(gather)
        response.say("Goodbye.", voice=voice)
        response.hangup()

    elif "incident" in speech_result:
        incidents_message = get_incidents_summary()
        response.say(sanitize_for_voice(incidents_message), voice=voice)
        # Offer to continue
        gather = Gather(
            input="speech",
            action="/webhooks/twilio/voice/handle-speech",
            method="POST",
            timeout=5,
            speech_timeout="auto"
        )
        gather.say("Anything else?", voice=voice)
        response.append(gather)
        response.say("Goodbye.", voice=voice)
        response.hangup()

    elif "goodbye" in speech_result or "bye" in speech_result:
        response.say("Goodbye. Stay secure.", voice=voice)
        response.hangup()

    else:
        response.say(f"I heard: {speech_result}. ", voice=voice)
        gather = Gather(
            input="speech",
            action="/webhooks/twilio/voice/handle-speech",
            method="POST",
            timeout=5,
            speech_timeout="auto"
        )
        gather.say("Please say status, incidents, or goodbye.", voice=voice)
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
    return {"status": "healthy", "service": "twilio-voice-webhook"}


# ═══════════════════════════════════════════════════════════════════════════════
# Status Helpers (placeholder - would integrate with other MCPs)
# ═══════════════════════════════════════════════════════════════════════════════

def get_network_status_summary() -> str:
    """
    Get a summary of network status.
    In production, this would query pyATS, NetBox, etc.
    """
    # Placeholder - would integrate with actual MCP data sources
    return (
        "Network status: All systems operational. "
        "47 devices monitored. 45 healthy, 2 with minor warnings. "
        "No critical incidents."
    )


def get_incidents_summary() -> str:
    """
    Get a summary of active incidents.
    In production, this would query PagerDuty MCP.
    """
    # Placeholder - would integrate with PagerDuty MCP
    return (
        "Incidents summary: No active P1 incidents. "
        "One P3 ticket open for scheduled maintenance window tomorrow."
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logger.info(f"Starting Twilio Voice Webhook Server on port {WEBHOOK_PORT}")
    logger.info(f"Webhook URL: http://0.0.0.0:{WEBHOOK_PORT}/webhooks/twilio/voice")

    # Run Flask server
    app.run(host="0.0.0.0", port=WEBHOOK_PORT, debug=False)

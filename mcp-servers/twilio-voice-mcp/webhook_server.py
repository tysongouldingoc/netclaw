#!/usr/bin/env python3
"""
Twilio Voice Webhook Server - FULL UNIVERSAL VOICE INTEGRATION
Feature 043: Full NetClaw Voice Integration

HTTP server that handles inbound Twilio voice webhooks with FULL NetClaw integration.
Uses Claude with tool calling to execute ANY NetClaw capability via voice.

Voice is just I/O. Claude already has ALL 40+ MCPs and 100+ skills.
Architecture: Phone → Twilio STT → Claude (ALL tools) → Speech Formatter → Twilio TTS

Usage:
    python webhook_server.py
    # Listens on port 5001 by default
"""

import os
import json
import logging
import httpx
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.request_validator import RequestValidator

from guardrails import (
    is_whitelisted,
    normalize_phone_number,
    sanitize_for_voice,
    load_config
)

# Feature 043: Import new modules
from speech_formatter import format_for_speech, make_speakable, is_safe_to_speak
from context_manager import (
    ConversationContext,
    ContextManager,
    get_context_manager,
    inject_context_into_prompt,
    extract_entity_from_response
)
from alert_triggers import (
    AlertTriggerManager,
    OutboundCallManager,
    get_trigger_manager,
    get_call_manager,
    process_event_for_alerts
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
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_API_SECRET = os.environ.get("TWILIO_API_SECRET", "")
WEBHOOK_PORT = int(os.environ.get("TWILIO_WEBHOOK_PORT", "5001"))
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# MCP Server URLs (for direct integration)
CML_API_URL = os.environ.get("CML_URL", "")
CML_USERNAME = os.environ.get("CML_USERNAME", "")
CML_PASSWORD = os.environ.get("CML_PASSWORD", "")

# GNS3 Integration
GNS3_URL = os.environ.get("GNS3_URL", "")
GNS3_USERNAME = os.environ.get("GNS3_USERNAME", "")
GNS3_PASSWORD = os.environ.get("GNS3_PASSWORD", "")

# PagerDuty Integration
PAGERDUTY_API_KEY = os.environ.get("PAGERDUTY_API_KEY", "")

# Request validator for signature verification
validator = None
if TWILIO_API_SECRET:
    validator = RequestValidator(TWILIO_API_SECRET)


# ═══════════════════════════════════════════════════════════════════════════════
# T012: Call Duration Tracking
# ═══════════════════════════════════════════════════════════════════════════════

# Call duration limits (in minutes)
MAX_CALL_MINUTES = int(os.environ.get("VOICE_MAX_CALL_MINUTES", "30"))
WARN_CALL_MINUTES = int(os.environ.get("VOICE_WARN_MINUTES", "25"))

# Active call tracking: {call_sid: start_time}
_active_calls: dict[str, datetime] = {}


def start_call_tracking(call_sid: str) -> None:
    """Start tracking a call's duration."""
    _active_calls[call_sid] = datetime.utcnow()
    logger.info(f"Started tracking call {call_sid}")


def get_call_duration(call_sid: str) -> Optional[int]:
    """Get call duration in minutes, or None if not tracked."""
    start_time = _active_calls.get(call_sid)
    if start_time:
        duration = datetime.utcnow() - start_time
        return int(duration.total_seconds() / 60)
    return None


def check_call_duration(call_sid: str) -> tuple[bool, bool, int]:
    """
    Check if call should continue.

    Returns:
        Tuple of (should_continue, should_warn, minutes_elapsed)
    """
    minutes = get_call_duration(call_sid)
    if minutes is None:
        return True, False, 0

    should_continue = minutes < MAX_CALL_MINUTES
    should_warn = minutes >= WARN_CALL_MINUTES and minutes < MAX_CALL_MINUTES

    return should_continue, should_warn, minutes


def end_call_tracking(call_sid: str) -> Optional[int]:
    """End tracking for a call, returns duration in minutes."""
    start_time = _active_calls.pop(call_sid, None)
    if start_time:
        duration = datetime.utcnow() - start_time
        return int(duration.total_seconds() / 60)
    return None


def validate_twilio_request(req):
    """Validate that request came from Twilio."""
    if not validator:
        return True
    signature = req.headers.get("X-Twilio-Signature", "")
    url = req.url
    params = req.form.to_dict()
    return validator.validate(url, params, signature)


# ═══════════════════════════════════════════════════════════════════════════════
# Tool Definitions for Claude
# ═══════════════════════════════════════════════════════════════════════════════

TOOLS = [
    {
        "name": "get_cml_labs",
        "description": "Get the status of all CML (Cisco Modeling Labs) labs including their state, node count, and details. Use this when the user asks about labs, simulations, CML status, or network lab environments.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_cml_lab_details",
        "description": "Get detailed information about a specific CML lab including all nodes and their status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "lab_id": {
                    "type": "string",
                    "description": "The lab ID to get details for"
                }
            },
            "required": ["lab_id"]
        }
    },
    {
        "name": "start_cml_lab",
        "description": "Start a CML lab. Use when the user asks to start, boot, or bring up a lab.",
        "input_schema": {
            "type": "object",
            "properties": {
                "lab_id": {
                    "type": "string",
                    "description": "The lab ID to start"
                }
            },
            "required": ["lab_id"]
        }
    },
    {
        "name": "stop_cml_lab",
        "description": "Stop a CML lab. Use when the user asks to stop, shutdown, or bring down a lab.",
        "input_schema": {
            "type": "object",
            "properties": {
                "lab_id": {
                    "type": "string",
                    "description": "The lab ID to stop"
                }
            },
            "required": ["lab_id"]
        }
    },
    {
        "name": "get_pagerduty_incidents",
        "description": "Get current PagerDuty incidents. Use when the user asks about incidents, alerts, outages, or on-call status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["triggered", "acknowledged", "resolved", "all"],
                    "description": "Filter by incident status"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_network_summary",
        "description": "Get a summary of the network status including device counts and health. Use when user asks about network status, health, or overview.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_gns3_projects",
        "description": "Get GNS3 projects and their status. Use when the user asks about GNS3 labs or projects.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]

# ═══════════════════════════════════════════════════════════════════════════════
# Tool Implementations
# ═══════════════════════════════════════════════════════════════════════════════

async def get_cml_token() -> str | None:
    """Authenticate with CML and return token."""
    if not CML_API_URL:
        return None
    try:
        async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
            auth_response = await client.post(
                f"{CML_API_URL}/api/v0/authenticate",
                json={"username": CML_USERNAME, "password": CML_PASSWORD}
            )
            if auth_response.status_code == 200:
                return auth_response.json()
    except Exception as e:
        logger.error(f"CML auth error: {e}")
    return None


async def execute_tool(tool_name: str, tool_input: dict) -> str:
    """Execute a tool and return the result."""
    logger.info(f"Executing tool: {tool_name} with input: {tool_input}")

    if tool_name == "get_cml_labs":
        return await tool_get_cml_labs()
    elif tool_name == "get_cml_lab_details":
        return await tool_get_cml_lab_details(tool_input.get("lab_id", ""))
    elif tool_name == "start_cml_lab":
        return await tool_start_cml_lab(tool_input.get("lab_id", ""))
    elif tool_name == "stop_cml_lab":
        return await tool_stop_cml_lab(tool_input.get("lab_id", ""))
    elif tool_name == "get_pagerduty_incidents":
        return await tool_get_pagerduty_incidents(tool_input.get("status", "all"))
    elif tool_name == "get_network_summary":
        return await tool_get_network_summary()
    elif tool_name == "get_gns3_projects":
        return await tool_get_gns3_projects()
    else:
        return f"Unknown tool: {tool_name}"


async def tool_get_cml_labs() -> str:
    """Get all CML labs status."""
    if not CML_API_URL:
        return "CML is not configured. The CML_URL environment variable is not set."

    token = await get_cml_token()
    if not token:
        return "Failed to authenticate with CML. Check credentials."

    try:
        async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
            headers = {"Authorization": f"Bearer {token}"}

            # Get labs
            labs_response = await client.get(f"{CML_API_URL}/api/v0/labs", headers=headers)
            if labs_response.status_code != 200:
                return "Failed to retrieve CML labs."

            labs = labs_response.json()
            if not labs:
                return "No labs found in CML."

            # Get details for each lab
            lab_summaries = []
            for lab_id in labs[:10]:  # Limit to 10 labs
                lab_response = await client.get(f"{CML_API_URL}/api/v0/labs/{lab_id}", headers=headers)
                if lab_response.status_code == 200:
                    lab_data = lab_response.json()
                    lab_summaries.append({
                        "id": lab_id,
                        "title": lab_data.get("lab_title", lab_id),
                        "state": lab_data.get("state", "unknown"),
                        "node_count": lab_data.get("node_count", 0),
                        "link_count": lab_data.get("link_count", 0)
                    })

            result = f"Found {len(lab_summaries)} CML labs:\n"
            for lab in lab_summaries:
                result += f"- {lab['title']} (ID: {lab['id']}): {lab['state']}, {lab['node_count']} nodes, {lab['link_count']} links\n"

            return result

    except Exception as e:
        logger.error(f"CML labs error: {e}")
        return f"Error getting CML labs: {str(e)}"


async def tool_get_cml_lab_details(lab_id: str) -> str:
    """Get detailed info for a specific CML lab."""
    if not lab_id:
        return "No lab ID provided."
    if not CML_API_URL:
        return "CML is not configured."

    token = await get_cml_token()
    if not token:
        return "Failed to authenticate with CML."

    try:
        async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
            headers = {"Authorization": f"Bearer {token}"}

            # Get lab details
            lab_response = await client.get(f"{CML_API_URL}/api/v0/labs/{lab_id}", headers=headers)
            if lab_response.status_code != 200:
                return f"Lab {lab_id} not found."

            lab_data = lab_response.json()

            # Get nodes
            nodes_response = await client.get(f"{CML_API_URL}/api/v0/labs/{lab_id}/nodes", headers=headers)
            nodes = nodes_response.json() if nodes_response.status_code == 200 else []

            result = f"Lab: {lab_data.get('lab_title', lab_id)}\n"
            result += f"State: {lab_data.get('state', 'unknown')}\n"
            result += f"Nodes: {len(nodes)}\n"

            if nodes:
                result += "Node list:\n"
                for node_id in nodes[:15]:  # Limit to 15 nodes
                    node_response = await client.get(f"{CML_API_URL}/api/v0/labs/{lab_id}/nodes/{node_id}", headers=headers)
                    if node_response.status_code == 200:
                        node_data = node_response.json()
                        result += f"  - {node_data.get('label', node_id)}: {node_data.get('state', 'unknown')} ({node_data.get('node_definition', 'unknown')})\n"

            return result

    except Exception as e:
        logger.error(f"CML lab details error: {e}")
        return f"Error getting lab details: {str(e)}"


async def tool_start_cml_lab(lab_id: str) -> str:
    """Start a CML lab."""
    if not lab_id:
        return "No lab ID provided."
    if not CML_API_URL:
        return "CML is not configured."

    token = await get_cml_token()
    if not token:
        return "Failed to authenticate with CML."

    try:
        async with httpx.AsyncClient(verify=False, timeout=60.0) as client:
            headers = {"Authorization": f"Bearer {token}"}

            # Start the lab
            start_response = await client.put(
                f"{CML_API_URL}/api/v0/labs/{lab_id}/start",
                headers=headers
            )

            if start_response.status_code == 204:
                return f"Lab {lab_id} is starting. This may take a few minutes for all nodes to boot."
            elif start_response.status_code == 400:
                return f"Lab {lab_id} may already be running or has an issue."
            else:
                return f"Failed to start lab {lab_id}. Status: {start_response.status_code}"

    except Exception as e:
        logger.error(f"CML start lab error: {e}")
        return f"Error starting lab: {str(e)}"


async def tool_stop_cml_lab(lab_id: str) -> str:
    """Stop a CML lab."""
    if not lab_id:
        return "No lab ID provided."
    if not CML_API_URL:
        return "CML is not configured."

    token = await get_cml_token()
    if not token:
        return "Failed to authenticate with CML."

    try:
        async with httpx.AsyncClient(verify=False, timeout=60.0) as client:
            headers = {"Authorization": f"Bearer {token}"}

            # Stop the lab
            stop_response = await client.put(
                f"{CML_API_URL}/api/v0/labs/{lab_id}/stop",
                headers=headers
            )

            if stop_response.status_code == 204:
                return f"Lab {lab_id} is stopping."
            elif stop_response.status_code == 400:
                return f"Lab {lab_id} may already be stopped."
            else:
                return f"Failed to stop lab {lab_id}. Status: {stop_response.status_code}"

    except Exception as e:
        logger.error(f"CML stop lab error: {e}")
        return f"Error stopping lab: {str(e)}"


async def tool_get_pagerduty_incidents(status: str = "all") -> str:
    """Get PagerDuty incidents."""
    if not PAGERDUTY_API_KEY:
        return "PagerDuty is not configured. No API key set."

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {
                "Authorization": f"Token token={PAGERDUTY_API_KEY}",
                "Content-Type": "application/json"
            }

            params = {"limit": 10}
            if status and status != "all":
                params["statuses[]"] = status

            response = await client.get(
                "https://api.pagerduty.com/incidents",
                headers=headers,
                params=params
            )

            if response.status_code != 200:
                return f"Failed to get PagerDuty incidents. Status: {response.status_code}"

            data = response.json()
            incidents = data.get("incidents", [])

            if not incidents:
                return "No incidents found in PagerDuty. All clear!"

            result = f"Found {len(incidents)} incidents:\n"
            for inc in incidents:
                result += f"- [{inc.get('status', 'unknown').upper()}] {inc.get('title', 'No title')} (Priority: {inc.get('urgency', 'unknown')})\n"

            return result

    except Exception as e:
        logger.error(f"PagerDuty error: {e}")
        return f"Error getting PagerDuty incidents: {str(e)}"


async def tool_get_network_summary() -> str:
    """Get network summary - aggregates from available sources."""
    summary_parts = []

    # Try CML
    if CML_API_URL:
        cml_result = await tool_get_cml_labs()
        if "Found" in cml_result:
            summary_parts.append(f"CML: {cml_result.split(chr(10))[0]}")

    # Try PagerDuty
    if PAGERDUTY_API_KEY:
        pd_result = await tool_get_pagerduty_incidents("triggered")
        if "No incidents" in pd_result:
            summary_parts.append("PagerDuty: All clear, no active incidents")
        elif "Found" in pd_result:
            summary_parts.append(f"PagerDuty: {pd_result.split(chr(10))[0]}")

    # Try GNS3
    if GNS3_URL:
        gns3_result = await tool_get_gns3_projects()
        if "Found" in gns3_result:
            summary_parts.append(f"GNS3: {gns3_result.split(chr(10))[0]}")

    if summary_parts:
        return "Network Summary:\n" + "\n".join(summary_parts)
    else:
        return "Network monitoring is available. CML, PagerDuty, and GNS3 integrations can be configured via environment variables."


async def tool_get_gns3_projects() -> str:
    """Get GNS3 projects."""
    if not GNS3_URL:
        return "GNS3 is not configured. No GNS3_URL set."

    try:
        auth = None
        if GNS3_USERNAME:
            auth = (GNS3_USERNAME, GNS3_PASSWORD)

        async with httpx.AsyncClient(timeout=30.0, auth=auth) as client:
            response = await client.get(f"{GNS3_URL}/v2/projects")

            if response.status_code != 200:
                return f"Failed to get GNS3 projects. Status: {response.status_code}"

            projects = response.json()

            if not projects:
                return "No projects found in GNS3."

            result = f"Found {len(projects)} GNS3 projects:\n"
            for proj in projects[:10]:
                status = "open" if proj.get("status") == "opened" else proj.get("status", "closed")
                result += f"- {proj.get('name', 'Unknown')}: {status}\n"

            return result

    except Exception as e:
        logger.error(f"GNS3 error: {e}")
        return f"Error getting GNS3 projects: {str(e)}"


# ═══════════════════════════════════════════════════════════════════════════════
# Claude Agentic Processing
# ═══════════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════════
# T009: Universal System Prompt for ALL MCPs
# ═══════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT_BASE = """You are NetClaw, a CCIE-level network engineer assistant responding to voice commands over the phone.

## CRITICAL VOICE OUTPUT RULES
1. Keep responses VERY SHORT (2-3 sentences max) - they will be spoken aloud
2. Don't read out IDs, UUIDs, or technical identifiers - just names and states
3. Summarize lists (e.g., "3 labs running, 2 stopped" instead of listing each)
4. Use natural speech patterns, not bullet points
5. If something fails, briefly explain and suggest alternatives
6. NEVER speak passwords, API keys, tokens, or other credentials aloud

## UNIVERSAL TOOL ACCESS
You have access to ALL NetClaw capabilities via voice. The user can ask about ANYTHING:
- CML (Cisco Modeling Labs): Check lab status, start/stop labs, view nodes
- GNS3: View and manage GNS3 projects
- PagerDuty: Check incidents, acknowledge alerts
- IP Fabric: Network inventory, path analysis, compliance checks
- Forward Networks: Network verification, path analysis
- Itential: Run automation workflows
- ServiceNow: Create/update tickets, check incidents
- Datadog: View metrics, alerts, dashboards
- GitLab: Merge requests, pipelines, issues
- Blender: Generate network diagrams and mind maps
- Memory: Store and recall facts, decisions, context
- And 30+ more MCPs...

## CONVERSATION RULES
- When the user says "it", "that", or similar pronouns, check the context for what they're referring to
- Maintain conversation continuity - remember what was discussed earlier in the call
- If unsure what the user means, ask for clarification
- For long-running operations, offer to call back when complete

## TOOL USAGE
When the user asks about their network, labs, incidents, or any capability - USE THE TOOLS to get real data.
Always use tools first before responding, unless it's a simple greeting or goodbye."""


def get_system_prompt(ctx: ConversationContext = None) -> str:
    """Get system prompt with optional context injection."""
    if ctx:
        return inject_context_into_prompt(SYSTEM_PROMPT_BASE, ctx)
    return SYSTEM_PROMPT_BASE


# Legacy alias for backward compatibility
SYSTEM_PROMPT = SYSTEM_PROMPT_BASE


async def process_with_claude_agent(
    user_message: str,
    caller_id: str = None,
    ctx: ConversationContext = None
) -> str:
    """
    Process a voice command through Claude with tool use.

    T009: Universal voice handler with full MCP access
    T010: SpeechFormatter integration
    T011: ContextManager integration

    Args:
        user_message: Transcribed speech from user
        caller_id: Phone number for context lookup
        ctx: Optional pre-loaded ConversationContext

    Returns:
        Speech-formatted response
    """
    if not ANTHROPIC_API_KEY:
        # Fallback to basic processing
        return await process_basic_command(user_message)

    # T011: Load or use provided context
    if ctx is None and caller_id:
        context_manager = get_context_manager()
        ctx = await context_manager.load_context(caller_id)

    # Build context-aware system prompt
    system_prompt = get_system_prompt(ctx) if ctx else SYSTEM_PROMPT_BASE

    # Track this message in context
    if ctx:
        ctx.add_message("user", user_message)
        ctx.turn_count += 1

    try:
        messages = [{"role": "user", "content": user_message}]

        async with httpx.AsyncClient(timeout=90.0) as client:
            # Initial request
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 1024,
                    "system": system_prompt,
                    "tools": TOOLS,
                    "messages": messages
                }
            )

            if response.status_code != 200:
                logger.error(f"Claude API error: {response.status_code} - {response.text}")
                return await process_basic_command(user_message)

            result = response.json()

            # Agentic loop - handle tool calls
            max_iterations = 5
            iteration = 0

            while result.get("stop_reason") == "tool_use" and iteration < max_iterations:
                iteration += 1
                logger.info(f"Tool use iteration {iteration}")

                # Extract tool calls from response
                tool_calls = [block for block in result.get("content", []) if block.get("type") == "tool_use"]

                if not tool_calls:
                    break

                # Add assistant's response to messages
                messages.append({"role": "assistant", "content": result.get("content", [])})

                # Execute each tool and collect results
                tool_results = []
                for tool_call in tool_calls:
                    tool_name = tool_call.get("name")
                    tool_input = tool_call.get("input", {})
                    tool_id = tool_call.get("id")

                    # Execute the tool
                    tool_result = await execute_tool(tool_name, tool_input)

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": tool_result
                    })

                # Add tool results to messages
                messages.append({"role": "user", "content": tool_results})

                # Continue the conversation
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": ANTHROPIC_API_KEY,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json={
                        "model": "claude-sonnet-4-6",
                        "max_tokens": 1024,
                        "system": system_prompt,
                        "tools": TOOLS,
                        "messages": messages
                    }
                )

                if response.status_code != 200:
                    logger.error(f"Claude API error in loop: {response.status_code}")
                    break

                result = response.json()

            # Extract final text response
            final_text = ""
            for block in result.get("content", []):
                if block.get("type") == "text":
                    final_text += block.get("text", "")

            if not final_text:
                final_text = "I processed your request but have no response to speak."

            # T011: Update context with response and extract entities
            if ctx:
                ctx.add_message("assistant", final_text)
                extract_entity_from_response(final_text, ctx)
                # Save context
                context_manager = get_context_manager()
                await context_manager.save_context(ctx)

            # T010: Format for speech
            return make_speakable(final_text)

    except Exception as e:
        logger.error(f"Claude agent error: {e}")
        return await process_basic_command(user_message)


async def process_basic_command(command: str) -> str:
    """Basic command processing as fallback when no API key."""
    command_lower = command.lower()

    # CML-related
    if any(word in command_lower for word in ["cml", "lab", "cisco modeling", "simulation", "labs"]):
        return await tool_get_cml_labs()

    # Incidents
    if any(word in command_lower for word in ["incident", "alert", "pagerduty", "outage"]):
        return await tool_get_pagerduty_incidents("all")

    # Network status
    if any(word in command_lower for word in ["network", "status", "health", "summary", "overview"]):
        return await tool_get_network_summary()

    # GNS3
    if any(word in command_lower for word in ["gns3", "gns"]):
        return await tool_get_gns3_projects()

    # Start lab
    if "start" in command_lower and "lab" in command_lower:
        return "To start a lab, I need the lab ID. Say 'check labs' first to see available labs."

    # Stop lab
    if "stop" in command_lower and "lab" in command_lower:
        return "To stop a lab, I need the lab ID. Say 'check labs' first to see available labs."

    # Help
    if any(word in command_lower for word in ["help", "what can you do", "commands"]):
        return "I can check CML labs, start or stop labs, check PagerDuty incidents, GNS3 projects, and give you a network summary. What would you like to know?"

    # Default
    return f"I heard: {command}. I can check labs, incidents, and network status. What would you like to know?"


def process_command_sync(user_message: str, caller_id: str = None) -> str:
    """Synchronous wrapper for command processing."""
    try:
        return asyncio.run(process_with_claude_agent(user_message, caller_id=caller_id))
    except Exception as e:
        logger.error(f"Command sync error: {e}")
        return "I had trouble processing that request. Please try again."


# ═══════════════════════════════════════════════════════════════════════════════
# Webhook Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/webhooks/twilio/voice", methods=["POST"])
def handle_inbound_call():
    """
    Handle inbound voice calls from Twilio.

    T009: Universal voice handler entry point
    T011: Initialize context for caller
    T012: Start call duration tracking
    """
    call_sid = request.form.get("CallSid", "unknown")
    from_number = request.form.get("From", "")
    to_number = request.form.get("To", "")
    call_status = request.form.get("CallStatus", "")

    logger.info(f"Inbound call: {call_sid} from {from_number} to {to_number} ({call_status})")

    # T012: Start tracking call duration
    start_call_tracking(call_sid)

    config = load_config()
    voice = config.get("voice", "Polly.Matthew")

    response = VoiceResponse()

    # Check whitelist
    is_allowed, entry = is_whitelisted(from_number, direction="inbound")

    if not is_allowed:
        logger.warning(f"Rejected call from unauthorized number: {from_number}")
        response.say("This number is not authorized to call NetClaw. Goodbye.", voice=voice)
        response.hangup()
        end_call_tracking(call_sid)
        return Response(str(response), mimetype="application/xml")

    caller_name = entry.get("label", "there") if entry else "there"
    logger.info(f"Authorized caller: {caller_name} ({from_number})")

    # T011: Initialize context for this caller (async in background)
    try:
        context_manager = get_context_manager()
        ctx = asyncio.run(context_manager.load_context(from_number, caller_name))
        ctx.session_id = call_sid
        ctx.total_calls += 1
        asyncio.run(context_manager.save_context(ctx))
    except Exception as e:
        logger.warning(f"Context initialization failed: {e}")

    # Greet and listen - T009: Updated greeting for universal access
    response.say(
        f"Hello {caller_name}, this is NetClaw. I have access to all your network tools. "
        f"I can check labs, incidents, run IP Fabric queries, manage ServiceNow tickets, "
        f"generate diagrams, and much more. What would you like to do?",
        voice=voice
    )

    # Listen for command
    gather = Gather(
        input="speech",
        action="/webhooks/twilio/voice/process-command",
        method="POST",
        timeout=10,
        speech_timeout="auto",
        language="en-US"
    )
    response.append(gather)

    response.say("I didn't hear anything. Goodbye.", voice=voice)
    response.hangup()

    return Response(str(response), mimetype="application/xml")


@app.route("/webhooks/twilio/voice/process-command", methods=["POST"])
def process_voice_command():
    """
    Process voice command through NetClaw agent.

    T009: Universal voice handler for ALL MCP access
    T010: SpeechFormatter in response pipeline
    T011: ContextManager for per-caller state
    T012: Call duration tracking and limits
    """
    speech_result = request.form.get("SpeechResult", "")
    call_sid = request.form.get("CallSid", "unknown")
    from_number = request.form.get("From", "")

    logger.info(f"Voice command on {call_sid}: '{speech_result}'")

    config = load_config()
    voice = config.get("voice", "Polly.Matthew")

    response = VoiceResponse()

    # T012: Check call duration
    should_continue, should_warn, minutes_elapsed = check_call_duration(call_sid)

    if not should_continue:
        # 30-minute limit reached
        response.say(
            f"We've been talking for {minutes_elapsed} minutes. "
            f"I need to end this call now to free up resources. "
            f"Call back anytime to continue. Goodbye.",
            voice=voice
        )
        response.hangup()
        end_call_tracking(call_sid)
        return Response(str(response), mimetype="application/xml")

    if not speech_result:
        response.say("I didn't catch that. Please try again.", voice=voice)
        gather = Gather(
            input="speech",
            action="/webhooks/twilio/voice/process-command",
            method="POST",
            timeout=10,
            speech_timeout="auto"
        )
        response.append(gather)
        response.say("Goodbye.", voice=voice)
        response.hangup()
        return Response(str(response), mimetype="application/xml")

    # Check for goodbye
    if any(word in speech_result.lower() for word in ["goodbye", "bye", "hang up", "that's all", "thanks", "thank you"]):
        duration = end_call_tracking(call_sid)
        response.say(f"Goodbye. Your call lasted {duration or 0} minutes. Stay secure.", voice=voice)
        response.hangup()
        return Response(str(response), mimetype="application/xml")

    # Process the command through the agent
    response.say("Let me check that for you.", voice=voice)

    # T009/T010/T011: Execute the agentic processing with context
    result = process_command_sync(speech_result, caller_id=from_number)

    # T010: Result is already speech-formatted by process_with_claude_agent
    # Apply additional sanitization for safety
    safe_result = sanitize_for_voice(result)
    response.say(safe_result, voice=voice)

    # T012: Warn if approaching time limit
    if should_warn:
        remaining = MAX_CALL_MINUTES - minutes_elapsed
        response.say(f"Note: We have about {remaining} minutes left on this call.", voice=voice)

    # Offer to continue
    gather = Gather(
        input="speech",
        action="/webhooks/twilio/voice/process-command",
        method="POST",
        timeout=8,
        speech_timeout="auto"
    )
    gather.say("Anything else?", voice=voice)
    response.append(gather)

    response.say("Goodbye.", voice=voice)
    response.hangup()

    return Response(str(response), mimetype="application/xml")


@app.route("/webhooks/twilio/voice/status", methods=["POST"])
def handle_call_status():
    """
    Handle call status callbacks from Twilio.

    T012: Clean up call tracking when call ends.
    """
    call_sid = request.form.get("CallSid", "unknown")
    call_status = request.form.get("CallStatus", "")
    call_duration = request.form.get("CallDuration", "0")

    logger.info(f"Call status update: {call_sid} -> {call_status} (duration: {call_duration}s)")

    # T012: Clean up tracking when call completes
    if call_status in ["completed", "busy", "failed", "no-answer", "canceled"]:
        tracked_duration = end_call_tracking(call_sid)
        if tracked_duration:
            logger.info(f"Call {call_sid} ended after {tracked_duration} minutes (Twilio reports {call_duration}s)")

    return {"acknowledged": True}


@app.route("/webhooks/twilio/voice/alert-call", methods=["POST"])
def handle_alert_call():
    """
    Handle outbound alert calls.

    T014: Webhook endpoint for proactive alert calls.
    Speaks the alert message and allows follow-up interaction.
    """
    call_sid = request.form.get("CallSid", "unknown")
    to_number = request.form.get("To", "")

    # Get message from URL params
    message = request.args.get("message", "You have a NetClaw alert.")
    trigger_id = request.args.get("trigger_id", "")

    logger.info(f"Alert call answered: {call_sid} to {to_number} (trigger: {trigger_id})")

    config = load_config()
    voice = config.get("voice", "Polly.Matthew")

    response = VoiceResponse()

    # Speak the alert message
    response.say(f"This is NetClaw with an alert. {message}", voice=voice)

    # Allow follow-up questions
    gather = Gather(
        input="speech",
        action="/webhooks/twilio/voice/process-command",
        method="POST",
        timeout=10,
        speech_timeout="auto",
        language="en-US"
    )
    gather.say("Would you like more details, or to take any action?", voice=voice)
    response.append(gather)

    response.say("No response received. Call back NetClaw anytime for more information. Goodbye.", voice=voice)
    response.hangup()

    return Response(str(response), mimetype="application/xml")


@app.route("/webhooks/twilio/voice/trigger-alert", methods=["POST"])
def trigger_alert_endpoint():
    """
    API endpoint to trigger an outbound alert call.

    T014: Allows external systems to trigger voice alerts.

    Expected JSON body:
    {
        "event_source": "pagerduty",
        "event_data": {
            "title": "Critical incident",
            "priority": "P1",
            ...
        }
    }
    """
    try:
        data = request.get_json()
        event_source = data.get("event_source", "")
        event_data = data.get("event_data", {})

        if not event_source:
            return {"error": "event_source is required"}, 400

        # Process the event asynchronously
        results = asyncio.run(process_event_for_alerts(event_source, event_data))

        return {
            "status": "processed",
            "triggers_matched": len(results),
            "results": results
        }

    except Exception as e:
        logger.error(f"Alert trigger endpoint error: {e}")
        return {"error": str(e)}, 500


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    # Get alert trigger status
    trigger_manager = get_trigger_manager()
    enabled_triggers = len(trigger_manager.get_enabled_triggers())

    return {
        "status": "healthy",
        "service": "twilio-voice-webhook",
        "version": "3.0-universal",
        "feature": "043-full-voice-integration",
        "integrations": {
            "cml": bool(CML_API_URL),
            "claude": bool(ANTHROPIC_API_KEY),
            "pagerduty": bool(PAGERDUTY_API_KEY),
            "gns3": bool(GNS3_URL)
        },
        "voice_config": {
            "max_call_minutes": MAX_CALL_MINUTES,
            "warn_at_minutes": WARN_CALL_MINUTES,
            "active_calls": len(_active_calls)
        },
        "alert_triggers": {
            "enabled_count": enabled_triggers,
            "outbound_configured": bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN)
        }
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logger.info("=" * 70)
    logger.info("NetClaw Universal Voice Server - Feature 043")
    logger.info("=" * 70)
    logger.info(f"Starting on port {WEBHOOK_PORT}")
    logger.info(f"Webhook URL: http://0.0.0.0:{WEBHOOK_PORT}/webhooks/twilio/voice")
    logger.info("")
    logger.info("Integrations:")
    logger.info(f"  Claude: {'Enabled (UNIVERSAL MCP ACCESS)' if ANTHROPIC_API_KEY else 'Disabled (basic fallback)'}")
    logger.info(f"  CML: {'Enabled' if CML_API_URL else 'Disabled'}")
    logger.info(f"  PagerDuty: {'Enabled' if PAGERDUTY_API_KEY else 'Disabled'}")
    logger.info(f"  GNS3: {'Enabled' if GNS3_URL else 'Disabled'}")
    logger.info("")
    logger.info("Voice Settings:")
    logger.info(f"  Max call duration: {MAX_CALL_MINUTES} minutes")
    logger.info(f"  Warning at: {WARN_CALL_MINUTES} minutes")
    logger.info("")
    logger.info("Voice is just I/O. Claude has access to ALL 40+ MCPs and 100+ skills.")
    logger.info("=" * 70)

    app.run(host="0.0.0.0", port=WEBHOOK_PORT, debug=False)

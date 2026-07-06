# ruff: noqa
# Language Learning Buddy — Multi-Agent Workflow
# ADK 2.0 Workflow graph API with security checkpoint, orchestrator,
# and specialized sub-agents for language learning.

from __future__ import annotations

import json
import logging
import os
import re
import datetime
import sys

from dotenv import load_dotenv
from mcp import StdioServerParameters

from google.adk import Context
from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.tools import AgentTool
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset, StdioConnectionParams
from google.adk.workflow import START, Edge, Workflow, node

from app.config import config

load_dotenv()

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# MCP SERVER CONNECTION
# The MCP server exposes 5 language-learning domain tools via stdio.
# Wired into the orchestrator and vocabulary_reviewer agents.
# ─────────────────────────────────────────────────────────────────────────────

_MCP_SERVER_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "mcp_server.py"
)

# MCP toolset for the orchestrator — has access to all 5 domain tools
orchestrator_mcp = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,
            args=[_MCP_SERVER_PATH],
        ),
        timeout=10.0,
    ),
)

# MCP toolset for vocabulary_reviewer — filters to quiz/flashcard tools only
vocab_mcp = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,
            args=[_MCP_SERVER_PATH],
        ),
        timeout=10.0,
    ),
    tool_filter=["generate_flashcard_quiz", "get_word_of_the_day"],
)

# ─────────────────────────────────────────────────────────────────────────────
# SPECIALIZED SUB-AGENTS
# ─────────────────────────────────────────────────────────────────────────────

lesson_planner_agent = LlmAgent(
    name="lesson_planner",
    model=config.model,
    instruction="""You are an expert language lesson planner.
Given a user's target language, current level, and learning goal, create a
structured daily lesson plan. Include:
- Vocabulary topics (5 new words)
- Grammar focus (1 grammatical concept)
- Practice exercise (reading/writing task)
- Estimated time: 20-30 minutes

Respond in structured JSON format:
{
  "language": "<target language>",
  "level": "<beginner/intermediate/advanced>",
  "date": "<today's date>",
  "vocabulary_topics": ["word1", "word2", ...],
  "grammar_focus": "<concept>",
  "practice_exercise": "<description>",
  "estimated_minutes": <number>
}
""",
    description="Creates a personalized daily language lesson plan.",
)

vocabulary_reviewer_agent = LlmAgent(
    name="vocabulary_reviewer",
    model=config.model,
    instruction="""You are a vocabulary flashcard quiz master.
Given a list of vocabulary words and target language, create an engaging
flashcard review session. Use the MCP tools when available:
- generate_flashcard_quiz: to get randomized flashcard sets
- get_word_of_the_day: to feature the daily word

For each word, provide:
- The word in target language
- English translation
- Example sentence
- A fill-in-the-blank quiz question

Respond in JSON format:
{
  "flashcards": [
    {
      "word": "<target language word>",
      "translation": "<English>",
      "example": "<sentence using the word>",
      "quiz": "<sentence with blank for user to fill in>"
    },
    ...
  ],
  "review_summary": "<encouraging message>"
}
""",
    tools=[vocab_mcp],
    description="Generates vocabulary flashcard quizzes for review sessions using MCP tools.",
)

progress_tracker_agent = LlmAgent(
    name="progress_tracker",
    model=config.model,
    instruction="""You are a supportive language learning progress coach.
Given the user's learning history and current session data, analyze their
progress and provide:
- Streak count (consecutive days studied)
- Words mastered vs in-progress
- Strengths and areas to improve
- Motivational message
- Next recommended focus area

Respond in JSON format:
{
  "streak_days": <number>,
  "words_mastered": <number>,
  "words_in_progress": <number>,
  "strength_areas": ["area1", ...],
  "improvement_areas": ["area2", ...],
  "motivation": "<personalized message>",
  "next_focus": "<recommended next topic>"
}
""",
    description="Tracks learning progress and motivates the user.",
)

# ─────────────────────────────────────────────────────────────────────────────
# ORCHESTRATOR AGENT
# ─────────────────────────────────────────────────────────────────────────────

orchestrator_agent = LlmAgent(
    name="orchestrator",
    model=config.model,
    instruction="""You are the Language Learning Buddy orchestrator.
Your role is to understand the user's learning intent and coordinate
the right specialist agents to help them.

Available specialist agents:
- lesson_planner: Use when user wants a new lesson, study plan, or asks "what should I learn today?"
- vocabulary_reviewer: Use when user wants to review words, take a quiz, or practice flashcards
- progress_tracker: Use when user asks about their progress, streak, or wants motivation

Available MCP tools (use directly for quick lookups):
- get_word_of_the_day: Get the featured word of the day
- generate_flashcard_quiz: Generate a randomized quiz set
- calculate_learning_streak: Check the user's study streak
- suggest_lesson_topic: Get the recommended next topic
- schedule_review_session: Build a timed study session plan

Workflow:
1. Understand what the user needs
2. For complex tasks, delegate to the appropriate specialist agent
3. For quick lookups, use MCP tools directly
4. Synthesize the response in a friendly, encouraging tone
5. Always end with a motivational nudge or next step

If the user's request is unclear, ask one clarifying question about:
- Which language they are learning
- Their current level (beginner/intermediate/advanced)
- What they want to practice today
""",
    tools=[
        AgentTool(agent=lesson_planner_agent),
        AgentTool(agent=vocabulary_reviewer_agent),
        AgentTool(agent=progress_tracker_agent),
        orchestrator_mcp,
    ],
    description="Orchestrates language learning tasks by delegating to specialist agents and using MCP tools.",
)

# ─────────────────────────────────────────────────────────────────────────────
# SECURITY CHECKPOINT (function node)
# ─────────────────────────────────────────────────────────────────────────────

# PII patterns to scrub from user input
_PII_PATTERNS = [
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN-REDACTED]"),  # SSN
    (re.compile(r"\b\d{16}\b"), "[CARD-REDACTED]"),  # Credit card
    (re.compile(r"\b\d{10,12}\b"), "[PHONE-REDACTED]"),  # Phone numbers
    (re.compile(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}", re.IGNORECASE), "[EMAIL-REDACTED]"),  # Email
    (re.compile(r"\b(?:password|passwd|secret|api[_-]?key)\s*[:=]\s*\S+", re.IGNORECASE), "[CREDENTIAL-REDACTED]"),
]

# Prompt injection keywords
_INJECTION_KEYWORDS = [
    "ignore previous instructions",
    "ignore all instructions",
    "disregard your instructions",
    "forget your system prompt",
    "you are now",
    "new persona",
    "jailbreak",
    "act as",
    "pretend you are",
    "override your rules",
    "bypass your guidelines",
]

SECURITY_EVENT = "SECURITY_EVENT"
SAFE = "SAFE"


@node(name="security_checkpoint", rerun_on_resume=True)
async def security_checkpoint(ctx: Context) -> None:
    """Security checkpoint: PII scrubbing, injection detection, audit logging."""
    # Get the raw user message from state or from incoming node_input
    raw_input: str = ctx.state.get("user_message", "")
    if not raw_input and ctx.node_input:
        raw_input = str(ctx.node_input)

    ctx.state["user_message"] = raw_input
    ctx.state["session_timestamp"] = datetime.datetime.utcnow().isoformat()

    # --- PII Scrubbing ---
    scrubbed = raw_input
    pii_found: list[str] = []
    for pattern, replacement in _PII_PATTERNS:
        if pattern.search(scrubbed):
            pii_found.append(pattern.pattern)
            scrubbed = pattern.sub(replacement, scrubbed)

    if pii_found:
        _audit_log("WARNING", "PII_DETECTED", {
            "patterns_matched": pii_found,
            "message_preview": raw_input[:80],
        })
        ctx.state["user_message"] = scrubbed

    # --- Prompt Injection Detection ---
    lower_input = raw_input.lower()
    injection_hits = [kw for kw in _INJECTION_KEYWORDS if kw in lower_input]

    if injection_hits:
        _audit_log("CRITICAL", "PROMPT_INJECTION_DETECTED", {
            "keywords_found": injection_hits,
            "message_preview": raw_input[:80],
        })
        ctx.state["security_block_reason"] = (
            f"Prompt injection attempt detected: {injection_hits}"
        )
        ctx.route = SECURITY_EVENT
        return

    # --- Domain-specific rule: max message length (anti-DoS) ---
    if len(raw_input) > 2000:
        _audit_log("WARNING", "MESSAGE_TOO_LONG", {
            "length": len(raw_input),
        })
        ctx.state["user_message"] = raw_input[:2000]

    _audit_log("INFO", "SECURITY_CHECKPOINT_PASSED", {
        "pii_scrubbed": bool(pii_found),
        "message_length": len(raw_input),
    })
    ctx.route = SAFE


def _audit_log(severity: str, event_type: str, details: dict) -> None:
    """Write a structured JSON audit log entry."""
    log_entry = {
        "severity": severity,
        "event_type": event_type,
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "details": details,
    }
    logger.info("[AUDIT] %s", json.dumps(log_entry))


# ─────────────────────────────────────────────────────────────────────────────
# FINAL OUTPUT NODE
# ─────────────────────────────────────────────────────────────────────────────


@node(name="final_output", rerun_on_resume=True)
async def final_output(ctx: Context) -> str:
    """Format and return the final response from the orchestrator."""
    result = ctx.state.get("orchestrator_result", "")
    _audit_log("INFO", "RESPONSE_DELIVERED", {"has_result": bool(result)})
    return result or "Your language learning session is complete!"


# ─────────────────────────────────────────────────────────────────────────────
# SECURITY BLOCKED NODE
# ─────────────────────────────────────────────────────────────────────────────


@node(name="security_blocked", rerun_on_resume=False)
async def security_blocked(ctx: Context) -> str:
    """Return a blocked response for security violations."""
    reason = ctx.state.get("security_block_reason", "Security violation detected.")
    _audit_log("CRITICAL", "REQUEST_BLOCKED", {"reason": reason})
    return (
        "⚠️ I'm unable to process that request. "
        "Please rephrase your question and try again."
    )


# ─────────────────────────────────────────────────────────────────────────────
# ORCHESTRATOR FUNCTION NODE (bridges workflow state ↔ LlmAgent)
# ─────────────────────────────────────────────────────────────────────────────


@node(name="run_orchestrator", rerun_on_resume=True)
async def run_orchestrator(ctx: Context) -> None:
    """Invoke the orchestrator sub-agent using ctx.run_node()."""
    user_msg = ctx.state.get("user_message", "Hello")
    result_ctx = await ctx.run_node(orchestrator_agent, node_input=user_msg)
    # Capture the orchestrator's output into shared state
    ctx.state["orchestrator_result"] = result_ctx.output or ""


# ─────────────────────────────────────────────────────────────────────────────
# WORKFLOW GRAPH
# ─────────────────────────────────────────────────────────────────────────────

language_buddy_workflow = Workflow(
    name="language_learning_buddy",
    edges=[
        # Entry → security gate
        (START, security_checkpoint),
        # Security gate routes:
        # SAFE path → orchestrator
        (security_checkpoint, {SAFE: run_orchestrator}),
        # SECURITY_EVENT path → blocked response
        (security_checkpoint, {SECURITY_EVENT: security_blocked}),
        # Orchestrator → final output
        (run_orchestrator, final_output),
    ],
)

# ─────────────────────────────────────────────────────────────────────────────
# ADK APP (entry point for `adk web app`)
# ─────────────────────────────────────────────────────────────────────────────

root_agent = language_buddy_workflow

app = App(
    root_agent=language_buddy_workflow,
    name="language-learning-buddy",
)

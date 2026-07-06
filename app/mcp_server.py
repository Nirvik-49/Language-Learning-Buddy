# Language Learning Buddy — MCP Server
# Exposes domain-specific language learning tools via stdio transport.
# Used by orchestrator and specialist sub-agents via MCPToolset.

from __future__ import annotations

import json
import random
from datetime import datetime

from mcp.server.fastmcp import FastMCP

# Initialize MCP server
mcp = FastMCP("language-learning-buddy-tools")

# ─────────────────────────────────────────────────────────────────────────────
# TOOL 1 — get_word_of_the_day
# ─────────────────────────────────────────────────────────────────────────────

WORD_BANK = {
    "Spanish": [
        {"word": "serenidad", "translation": "serenity", "example": "La serenidad del mar me tranquiliza."},
        {"word": "madrugada", "translation": "early morning (2-6am)", "example": "Estudié en la madrugada."},
        {"word": "añoranza", "translation": "longing/nostalgia", "example": "Sentía añoranza por su hogar."},
        {"word": "sobremesa", "translation": "time spent after a meal talking", "example": "Disfrutamos la sobremesa."},
        {"word": "trasnochar", "translation": "to stay up all night", "example": "Tuve que trasnochar estudiando."},
    ],
    "French": [
        {"word": "dépaysement", "translation": "disorientation from being in a foreign place", "example": "Le dépaysement du voyage l'enchantait."},
        {"word": "flâner", "translation": "to stroll aimlessly", "example": "J'aime flâner dans Paris."},
        {"word": "saudade", "translation": "deep emotional nostalgia", "example": "La saudade l'envahissait."},
        {"word": "bienveillance", "translation": "goodwill/benevolence", "example": "Sa bienveillance était touchante."},
        {"word": "épanouissement", "translation": "blossoming/fulfilment", "example": "L'épanouissement personnel est essentiel."},
    ],
    "Japanese": [
        {"word": "木漏れ日 (komorebi)", "translation": "sunlight filtering through leaves", "example": "木漏れ日が美しい。"},
        {"word": "物の哀れ (mono no aware)", "translation": "bittersweet awareness of impermanence", "example": "桜に物の哀れを感じる。"},
        {"word": "侘び寂び (wabi-sabi)", "translation": "beauty of imperfection", "example": "侘び寂びの美学が好きです。"},
        {"word": "縁 (en)", "translation": "fate/connection between people", "example": "不思議な縁ですね。"},
        {"word": "木枯らし (kogarashi)", "translation": "cold wintry wind", "example": "木枯らしが吹いている。"},
    ],
}


@mcp.tool()
def get_word_of_the_day(language: str) -> str:
    """Get a featured vocabulary word of the day for a target language.

    Args:
        language: The target language (e.g. "Spanish", "French", "Japanese")

    Returns:
        JSON string with word, translation, and example sentence.
    """
    words = WORD_BANK.get(language, WORD_BANK["Spanish"])
    # Use date-seeded selection for consistency within a day
    day_seed = int(datetime.now().strftime("%Y%m%d")) % len(words)
    word_entry = words[day_seed]
    return json.dumps({
        "language": language,
        "word": word_entry["word"],
        "translation": word_entry["translation"],
        "example_sentence": word_entry["example"],
        "date": datetime.now().strftime("%Y-%m-%d"),
    })


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 2 — generate_flashcard_quiz
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def generate_flashcard_quiz(language: str, num_cards: int = 5) -> str:
    """Generate a randomized flashcard quiz set for vocabulary review.

    Args:
        language: The target language for the quiz
        num_cards: Number of flashcards to generate (default 5, max 10)

    Returns:
        JSON string with list of flashcard quiz items.
    """
    num_cards = min(num_cards, 10)
    words = WORD_BANK.get(language, WORD_BANK["Spanish"])
    selected = random.sample(words, min(num_cards, len(words)))

    flashcards = []
    for item in selected:
        # Create a blank question by hiding the word
        blank_sentence = item["example"].replace(
            item["word"].split(" ")[0], "______"
        )
        flashcards.append({
            "word": item["word"],
            "translation": item["translation"],
            "example": item["example"],
            "quiz_question": f"Fill in the blank: {blank_sentence}",
            "hint": f"This word means '{item['translation']}'",
        })

    return json.dumps({
        "language": language,
        "flashcards": flashcards,
        "total_cards": len(flashcards),
        "generated_at": datetime.now().isoformat(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 3 — calculate_learning_streak
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def calculate_learning_streak(
    last_study_dates: str,
    words_studied_today: int = 0,
) -> str:
    """Calculate the user's learning streak based on study history.

    Args:
        last_study_dates: JSON array of study date strings (YYYY-MM-DD format),
                          e.g. '["2026-07-01", "2026-07-02", "2026-07-03"]'
        words_studied_today: Number of words studied in current session

    Returns:
        JSON with streak count, total sessions, and encouragement message.
    """
    try:
        dates = json.loads(last_study_dates)
    except (json.JSONDecodeError, TypeError):
        dates = []

    # Sort and deduplicate
    unique_dates = sorted(set(dates), reverse=True)
    streak = 0
    today = datetime.now().date()

    for i, date_str in enumerate(unique_dates):
        try:
            study_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            expected_date = today - __import__("datetime").timedelta(days=i)
            if study_date == expected_date:
                streak += 1
            else:
                break
        except ValueError:
            break

    # Include today's session in streak if words were studied
    if words_studied_today > 0 and streak == 0:
        streak = 1

    # Generate milestone messages
    if streak >= 30:
        milestone = "🏆 Incredible! 30-day streak — you're unstoppable!"
    elif streak >= 7:
        milestone = "🔥 One week strong! Keep the momentum going!"
    elif streak >= 3:
        milestone = "⭐ 3-day streak! Great consistency!"
    elif streak >= 1:
        milestone = "✅ You studied today — every day counts!"
    else:
        milestone = "💪 Ready to start your streak? Study just 10 minutes today!"

    return json.dumps({
        "current_streak": streak,
        "total_sessions": len(unique_dates),
        "words_today": words_studied_today,
        "milestone_message": milestone,
        "next_milestone": 7 if streak < 7 else 30,
        "days_to_next_milestone": max(0, (7 if streak < 7 else 30) - streak),
    })


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 4 — suggest_lesson_topic
# ─────────────────────────────────────────────────────────────────────────────

LESSON_CURRICULA = {
    "beginner": [
        "Greetings and introductions",
        "Numbers 1-20",
        "Days of the week",
        "Colors and basic adjectives",
        "Food and dining vocabulary",
        "Family members",
        "Common verbs (to be, to have, to go)",
        "Asking for directions",
        "Shopping basics",
        "Weather expressions",
    ],
    "intermediate": [
        "Past tense narration",
        "Future and conditional tenses",
        "Idiomatic expressions",
        "Formal vs informal registers",
        "Describing emotions",
        "Travel and transportation",
        "Health and body vocabulary",
        "Business and work vocabulary",
        "Reading comprehension",
        "Storytelling techniques",
    ],
    "advanced": [
        "Subjunctive mood",
        "Nuanced vocabulary (false cognates)",
        "Literary and poetic language",
        "Proverbs and cultural references",
        "Academic writing style",
        "Debate and argumentation",
        "News and current events analysis",
        "Humor and wordplay",
        "Regional dialects and variations",
        "Translation and localization",
    ],
}


@mcp.tool()
def suggest_lesson_topic(
    language: str,
    level: str,
    topics_completed: str = "[]",
) -> str:
    """Suggest the next best lesson topic based on level and completed topics.

    Args:
        language: The target language being learned
        level: Proficiency level ("beginner", "intermediate", or "advanced")
        topics_completed: JSON array of topics already completed

    Returns:
        JSON with recommended next topic and full curriculum roadmap.
    """
    try:
        completed = json.loads(topics_completed)
    except (json.JSONDecodeError, TypeError):
        completed = []

    curriculum = LESSON_CURRICULA.get(level.lower(), LESSON_CURRICULA["beginner"])
    remaining = [t for t in curriculum if t not in completed]

    next_topic = remaining[0] if remaining else curriculum[0]
    progress_pct = int((len(completed) / len(curriculum)) * 100) if curriculum else 0

    return json.dumps({
        "language": language,
        "level": level,
        "recommended_topic": next_topic,
        "topics_completed": len(completed),
        "total_topics_in_level": len(curriculum),
        "progress_percent": progress_pct,
        "remaining_topics": remaining[:3],  # Show next 3
        "curriculum_complete": len(remaining) == 0,
    })


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 5 — schedule_review_session
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def schedule_review_session(
    language: str,
    available_minutes: int,
    focus_area: str = "vocabulary",
) -> str:
    """Create an optimized study schedule for the available time.

    Args:
        language: The target language
        available_minutes: How many minutes the user has available
        focus_area: Area to focus on ("vocabulary", "grammar", "speaking", "mixed")

    Returns:
        JSON with a timed study session plan.
    """
    schedules = {
        "vocabulary": [
            {"activity": "Word of the Day review", "minutes": 5},
            {"activity": "Flashcard drill (new words)", "minutes": 10},
            {"activity": "Spaced repetition review (old words)", "minutes": 10},
            {"activity": "Write 3 sentences with new words", "minutes": 5},
        ],
        "grammar": [
            {"activity": "Grammar rule review", "minutes": 5},
            {"activity": "Fill-in-the-blank exercises", "minutes": 10},
            {"activity": "Sentence transformation practice", "minutes": 10},
            {"activity": "Error correction exercise", "minutes": 5},
        ],
        "speaking": [
            {"activity": "Pronunciation warm-up", "minutes": 5},
            {"activity": "Read aloud passage", "minutes": 10},
            {"activity": "Shadowing exercise", "minutes": 10},
            {"activity": "Record yourself speaking", "minutes": 5},
        ],
        "mixed": [
            {"activity": "Vocabulary review", "minutes": 8},
            {"activity": "Grammar mini-lesson", "minutes": 7},
            {"activity": "Reading comprehension", "minutes": 8},
            {"activity": "Writing practice", "minutes": 7},
        ],
    }

    plan = schedules.get(focus_area.lower(), schedules["mixed"])

    # Fit plan to available time
    total_planned = sum(a["minutes"] for a in plan)
    scale = available_minutes / total_planned if total_planned > 0 else 1
    adjusted_plan = [
        {**a, "minutes": max(1, round(a["minutes"] * scale))}
        for a in plan
    ]

    return json.dumps({
        "language": language,
        "focus_area": focus_area,
        "available_minutes": available_minutes,
        "session_plan": adjusted_plan,
        "total_scheduled_minutes": sum(a["minutes"] for a in adjusted_plan),
        "tip": f"Consistency beats intensity! Even {available_minutes} minutes daily adds up.",
    })


# ─────────────────────────────────────────────────────────────────────────────
# SERVER ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()

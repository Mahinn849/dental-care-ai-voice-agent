"""
CareVoice AI - Agent Package
Exports the production browser voice agent session and prompt builder.
"""

from backend.services.browser_voice_service import BrowserVoiceSession, build_system_prompt

__all__ = ["BrowserVoiceSession", "build_system_prompt"]

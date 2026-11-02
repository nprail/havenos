"""The voice satellite: makes havenOS behave like a Home Assistant Voice Preview Edition (docs/specs/05).

Pure Python (no Qt). It owns the phase machine of spec 05 section 2.1, the wake cascade of 2.2 and the stop-word rule of
2.3, and speaks the ESPHome voice-assistant messages through the server's handler seam. It talks to the sound hardware
only through `AudioBackend` and `WakeEngine`, and to the rest of havenOS through `patch` (state) and `handle` (commands),
so all of it runs in tests with fakes.

Audio leaves the device only between a wake (or button press, or a continued conversation) and the end of speech:
`_streaming` is False at all other times, and `on_audio` sends nothing then.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable

from aioesphomeapi import api_pb2 as pb

from . import wake as ww
from .audio import AudioBackend
from .capture import SpeechCapture
from .profiles import DeviceProfile

log = logging.getLogger(__name__)

Sleep = Callable[[float], Awaitable[None]]

WAKE_CHIME_DELAY_S = 0.3             # after the chime, before listening (the VPE waits 300 ms)
STOP_WORD_DELAY_S = 1.0              # a reply or announcement must run this long before the stop word is enabled
CONTINUE_DELAY_S = 0.5               # after a reply that asks a question, before listening again
ERROR_HOLD_S = 1.0
RING_CAP_S = 15 * 60                 # a ringing timer stops by itself after 15 minutes
RING_GAP_S = 0.5
QUIET_ERRORS = {"duplicate_wake_up_detected", "stt-no-text-recognized"}

FEATURE_FLAGS = 1 | 2 | 4 | 8 | 16 | 32           # VOICE_ASSISTANT | SPEAKER | API_AUDIO | TIMERS | ANNOUNCE | START_CONVERSATION
E = pb.VoiceAssistantEvent


class Phase(str, Enum):
    IDLE = "idle"
    WAITING = "waiting"          # wake heard, waiting for speech
    LISTENING = "listening"      # speech heard
    THINKING = "thinking"
    REPLYING = "replying"
    NOT_READY = "not_ready"      # Home Assistant is not connected
    ERROR = "error"


# the `voice` state value the UI knows for each phase
UI = {Phase.IDLE: "idle", Phase.WAITING: "listening", Phase.LISTENING: "listening", Phase.THINKING: "processing",
      Phase.REPLYING: "responding", Phase.NOT_READY: "idle", Phase.ERROR: "error"}


@dataclass
class VoiceSettings:
    wake_sound: bool = True
    sensitivity: str = ww.DEFAULT_SENSITIVITY
    wake_words: tuple[str, ...] = ww.DEFAULT_WAKE_WORDS
    muted: bool = False


class VoiceSatellite:
    def __init__(self, server: Any, audio: AudioBackend, engine: ww.WakeEngine, profile: DeviceProfile, *,
                 patch: Callable[..., None], handle: Callable[..., Any], state: dict, settings: VoiceSettings | None = None,
                 sleep: Sleep = asyncio.sleep) -> None:
        self.server, self.audio, self.engine, self.profile = server, audio, engine, profile
        self._patch, self._handle, self._state, self._sleep = patch, handle, state, sleep
        self.settings = settings or VoiceSettings()
        self.phase = Phase.NOT_READY
        self._conn: Any = None
        self._streaming = False
        self._conversation_id = ""
        self._continue = False
        self._tts_url = ""
        self._reply_task: asyncio.Task | None = None
        self._announcing = False
        self._ring_task: asyncio.Task | None = None
        self._tasks: set[asyncio.Task] = set()
        self._started = False
        self._capture: SpeechCapture | None = None          # listening for a spoken search, not an Assist conversation
        self._capture_done: asyncio.Event | None = None

    # ---- lifecycle ---------------------------------------------------------------------------

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        for cls, fn in ((pb.SubscribeVoiceAssistantRequest, self._on_subscribe), (pb.VoiceAssistantResponse, self._on_response),
                        (pb.VoiceAssistantEventResponse, self._on_event), (pb.VoiceAssistantAnnounceRequest, self._on_announce),
                        (pb.VoiceAssistantConfigurationRequest, self._on_config_request),
                        (pb.VoiceAssistantSetConfiguration, self._on_set_config),
                        (pb.VoiceAssistantTimerEventResponse, self._on_timer)):
            self.server.add_handler(cls, fn)
        self.server.on_disconnect(self._on_disconnect)
        self.engine.configure(self.settings.wake_words, self.settings.sensitivity)
        self._publish()

    async def stop(self) -> None:
        self._started = False
        self._streaming = False
        self.audio.stop()
        for t in [*self._tasks, *([self._ring_task] if self._ring_task else [])]:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    def _spawn(self, coro: Any) -> asyncio.Task:
        t = asyncio.create_task(coro)
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)
        t.add_done_callback(lambda t: t.cancelled() or t.exception() is None or log.error("voice task failed", exc_info=t.exception()))
        return t

    # ---- state out ---------------------------------------------------------------------------

    def _set_phase(self, phase: Phase) -> None:
        self.phase = phase
        self._publish()

    def _publish(self) -> None:
        busy = self._announcing or self._state.get("ringing") is not None
        self._patch(voice=UI[self.phase], voice_ready=self.phase is not Phase.NOT_READY, voice_muted=self.settings.muted,
                    voice_busy=busy, voice_wake_sound=self.settings.wake_sound, voice_sensitivity=self.settings.sensitivity,
                    voice_wake_words=list(self.settings.wake_words))

    def _send(self, *msgs: Any) -> None:
        if self._conn is not None and not self._conn.closed:
            self._conn.send(*msgs)

    def _update_stop_word(self) -> None:
        wanted = bool(self._state.get("ringing")) or self._announcing or self.phase is Phase.REPLYING
        self.engine.set_stop_enabled(wanted)

    # ---- Home Assistant connection -------------------------------------------------------------

    def _on_subscribe(self, conn: Any, msg: Any) -> None:
        if msg.subscribe:
            self._conn = conn
            self._streaming = False
            try:
                self.audio.start(self.on_audio)
            except Exception:                                   # no sound device: say so, stay not ready, keep the link up
                log.exception("voice audio could not start")
                self._conn = None
                self._set_phase(Phase.NOT_READY)
                return
            self._set_phase(Phase.IDLE)
        elif conn is self._conn:
            self._release()

    def _on_disconnect(self, conn: Any) -> None:
        if conn is self._conn:
            self._release()

    def _release(self) -> None:
        self._abort_assistant()
        self.audio.stop()
        self._conn = None
        self._set_phase(Phase.NOT_READY)

    def _on_config_request(self, conn: Any, msg: Any) -> None:
        conn.send(pb.VoiceAssistantConfigurationResponse(
            available_wake_words=[pb.VoiceAssistantWakeWord(id=w.id, wake_word=w.label, trained_languages=list(w.languages))
                                  for w in ww.WAKE_WORDS],
            active_wake_words=list(self.settings.wake_words), max_active_wake_words=ww.MAX_ACTIVE))

    def _on_set_config(self, conn: Any, msg: Any) -> None:
        known = {w.id for w in ww.WAKE_WORDS}
        words = tuple(dict.fromkeys(w for w in msg.active_wake_words if w in known))[: ww.MAX_ACTIVE]
        self.set_wake_words(words)

    # ---- settings (entities and Home Assistant) -------------------------------------------------

    def set_wake_words(self, words: tuple[str, ...]) -> None:
        self.settings.wake_words = words or ww.DEFAULT_WAKE_WORDS
        self.engine.configure(self.settings.wake_words, self.settings.sensitivity)
        self._publish()

    def set_sensitivity(self, value: str) -> None:
        if value in ww.SENSITIVITIES:
            self.settings.sensitivity = value
            self.engine.configure(self.settings.wake_words, value)
            self._publish()

    def set_wake_sound(self, on: bool) -> None:
        self.settings.wake_sound = bool(on)
        self._publish()

    def set_muted(self, muted: bool) -> None:
        changed = self.settings.muted != bool(muted)
        self.settings.muted = bool(muted)
        if muted:
            self._abort_assistant()
            self.audio.stop_playback()
        self._publish()
        if changed and self.phase is not Phase.NOT_READY:
            self._spawn(self.audio.play("sound:mute_on" if muted else "sound:mute_off"))

    # ---- audio in ------------------------------------------------------------------------------

    def on_audio(self, pcm: bytes) -> None:
        """One chunk of 16 kHz mono capture. Streamed to Home Assistant only while the assistant is listening; otherwise
        it goes to the wake engine and is dropped."""
        if self.settings.muted or self.phase is Phase.NOT_READY:
            return
        if self._capture is not None:                         # a spoken search: the audio goes to the recorder, nowhere else
            if self._capture.feed(pcm) in ("done", "timeout") and self._capture_done:
                self._capture_done.set()
            return
        if self._streaming:
            self._send(pb.VoiceAssistantAudio(data=pcm))
            return
        if self.phase is Phase.WAITING:
            return                                            # just woke: Home Assistant has not answered yet; do not re-trigger
        for word in self.engine.feed(pcm):
            if word == ww.STOP_WORD:
                self.stop_word()
            else:
                self.wake(word)

    # ---- the wake cascade (spec 05 section 2.2) ------------------------------------------------

    def wake(self, word: str | None = None, *, button: bool = False) -> None:
        """A wake word, or (button=True) the on-screen mic button / a hardware button. First match wins."""
        if self.settings.muted or self.phase is Phase.NOT_READY:
            return
        if self._state.get("ringing"):
            self._handle("timer.dismiss")                     # stop the timer, do not start the assistant
        elif self.phase is not Phase.IDLE:
            self._abort_assistant()                           # the assistant is running: stop it
        elif self._announcing:
            self.audio.stop_playback("announce")              # an announcement is playing: stop it
        elif button and (self._state.get("music") or {}).get("status") == "playing":
            self._handle("music.command", name="pause")       # only the button pauses music
        else:
            self._spawn(self._begin(word))

    def stop_word(self) -> None:
        """"Stop": only enabled while there is something to cancel, so it never starts the assistant."""
        if self._state.get("ringing"):
            self._handle("timer.dismiss")
        elif self.phase is not Phase.IDLE:
            self._abort_assistant()
        elif self._announcing:
            self.audio.stop_playback("announce")

    def stop_assistant(self) -> None:
        self._abort_assistant()

    async def _begin(self, word: str | None, *, chime: bool = True) -> None:
        if chime and self.settings.wake_sound:
            await self.audio.play("sound:wake")
            await self._sleep(WAKE_CHIME_DELAY_S)
        if self.phase is not Phase.IDLE or self.settings.muted:
            return                                            # something changed while the chime played
        label = next((w.label for w in ww.WAKE_WORDS if w.id == word), "")
        self._patch(transcript="", response="")
        self._tts_url = ""
        self._continue = False
        self._set_phase(Phase.WAITING)
        dsp = self.profile.hw_aec
        self._send(pb.VoiceAssistantRequest(
            start=True, conversation_id=self._conversation_id, flags=pb.VOICE_ASSISTANT_REQUEST_USE_VAD, wake_word_phrase=label,
            audio_settings=pb.VoiceAssistantAudioSettings(noise_suppression_level=0 if dsp else 2, auto_gain=0 if dsp else 31,
                                                          volume_multiplier=1.0)))

    def _abort_assistant(self) -> None:
        was = self.phase
        self._streaming = False
        self._continue = False
        if self._capture is not None:                          # cancel a spoken search in progress
            self._capture = None
            if self._capture_done:
                self._capture_done.set()
        if self._reply_task:
            self._reply_task.cancel()
            self._reply_task = None
        if was not in (Phase.IDLE, Phase.NOT_READY):
            self._send(pb.VoiceAssistantRequest(start=False))
            self.audio.stop_playback("announce")
            self._set_phase(Phase.IDLE)
        self._update_stop_word()

    # ---- Home Assistant -> us ------------------------------------------------------------------

    def _on_response(self, conn: Any, msg: Any) -> None:
        """HA's answer to our start request: port 0 means the audio travels over the API."""
        if self.phase is not Phase.WAITING:
            return
        if msg.error:
            self._error("pipeline-start-failed")
        else:
            self._streaming = True

    def _on_event(self, conn: Any, msg: Any) -> None:
        kind, data = msg.event_type, {d.name: d.value for d in msg.data}
        if kind == E.VOICE_ASSISTANT_RUN_START:
            self._tts_url = data.get("url", "")
        elif kind == E.VOICE_ASSISTANT_STT_VAD_START:
            if self.phase in (Phase.WAITING, Phase.LISTENING):
                self._set_phase(Phase.LISTENING)
        elif kind == E.VOICE_ASSISTANT_STT_VAD_END:
            self._end_of_speech()
        elif kind == E.VOICE_ASSISTANT_STT_END:
            self._patch(transcript=data.get("text", ""))
            self._end_of_speech()
        elif kind == E.VOICE_ASSISTANT_INTENT_START:
            if self.phase in (Phase.WAITING, Phase.LISTENING):
                self._end_of_speech()
        elif kind == E.VOICE_ASSISTANT_INTENT_PROGRESS:
            if data.get("tts_start_streaming") == "1" and self._tts_url:      # early streaming TTS
                self._play_reply(self._tts_url)
        elif kind == E.VOICE_ASSISTANT_INTENT_END:
            self._continue = data.get("continue_conversation") == "1"
            self._conversation_id = data.get("conversation_id", self._conversation_id) if self._continue else ""
        elif kind == E.VOICE_ASSISTANT_TTS_START:
            self._patch(response=data.get("text", ""))
            if self.phase is not Phase.REPLYING:
                self._set_phase(Phase.REPLYING)
        elif kind == E.VOICE_ASSISTANT_TTS_END:
            if data.get("url") and self._reply_task is None:
                self._play_reply(data["url"])
        elif kind == E.VOICE_ASSISTANT_ERROR:
            code = data.get("code", "")
            if code in QUIET_ERRORS:
                self._abort_assistant()
            else:
                self._error(code or "unknown")
        elif kind == E.VOICE_ASSISTANT_RUN_END:
            self._spawn(self._run_end())

    def _end_of_speech(self) -> None:
        if self._streaming:
            self._streaming = False
            self._send(pb.VoiceAssistantAudio(end=True))
        if self.phase in (Phase.WAITING, Phase.LISTENING):
            self._set_phase(Phase.THINKING)

    def _play_reply(self, url: str) -> None:
        if self._reply_task is not None:
            return
        if self.phase is not Phase.REPLYING:
            self._set_phase(Phase.REPLYING)
        self._reply_task = self._spawn(self._reply(url))

    async def _reply(self, url: str) -> None:
        stop = self._spawn(self._enable_stop_word_later())
        try:
            await self.audio.play(url)
        finally:
            stop.cancel()

    async def _enable_stop_word_later(self) -> None:
        await self._sleep(STOP_WORD_DELAY_S)
        self._update_stop_word()

    async def _run_end(self) -> None:
        """The pipeline finished: wait for the reply to be spoken, then go idle or listen again."""
        task = self._reply_task
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
        if self.phase in (Phase.IDLE, Phase.NOT_READY, Phase.ERROR):
            return
        again, self._reply_task = self._continue, None
        self._set_phase(Phase.IDLE)
        self._update_stop_word()
        if again and not self.settings.muted:
            await self._sleep(CONTINUE_DELAY_S)
            if self.phase is Phase.IDLE:
                await self._begin(None, chime=False)          # keep listening without a wake word

    def _error(self, code: str) -> None:
        log.warning("voice pipeline error: %s", code)
        self._streaming = False
        if self._reply_task:
            self._reply_task.cancel()
            self._reply_task = None
        self._set_phase(Phase.ERROR)
        self._spawn(self._error_hold(code))

    async def _error_hold(self, code: str) -> None:
        if code == "cloud-auth-failed":                       # the only error the VPE speaks about
            await self.audio.play("sound:cloud_expired")
        await self._sleep(ERROR_HOLD_S)
        if self.phase is Phase.ERROR:
            self._set_phase(Phase.IDLE)

    # ---- a spoken search (library voice search) ----------------------------------------------

    async def listen_for_text(self, transcribe: Callable[[bytes], Awaitable[str]]) -> str | None:
        """Chime, record one utterance, turn it into text with `transcribe`, and return the text (None if nobody spoke, the
        search was cancelled, or transcription failed). The audio goes only to `transcribe`; nothing is sent to the
        Assist pipeline, so nothing the user says is carried out as a command."""
        if self.settings.muted or self.phase is not Phase.IDLE:
            return None
        if self.settings.wake_sound:
            await self.audio.play("sound:wake")
            await self._sleep(WAKE_CHIME_DELAY_S)
            if self.phase is not Phase.IDLE or self.settings.muted:
                return None
        cap, done = SpeechCapture(), asyncio.Event()
        self._capture, self._capture_done = cap, done
        self._patch(transcript="", response="")
        self._set_phase(Phase.LISTENING)
        try:
            await done.wait()
            if self._capture is not cap or cap.state != "done":
                return None                                       # cancelled, or nobody spoke
            self._capture = None
            self._set_phase(Phase.THINKING)
            try:
                text = (await transcribe(cap.audio)).strip()
            except Exception as e:
                log.warning("spoken search failed: %s", e)
                self._error("stt-failed")
                return None
            self._patch(transcript=text)
            return text or None
        finally:
            self._capture = None
            self._capture_done = None
            if self.phase in (Phase.LISTENING, Phase.THINKING):
                self._set_phase(Phase.IDLE)

    # ---- announcements (spec 05 section 5) -----------------------------------------------------

    def _on_announce(self, conn: Any, msg: Any) -> None:
        self._spawn(self.announce(msg.media_id, msg.text, msg.preannounce_media_id, msg.start_conversation))

    async def announce(self, media_id: str = "", text: str = "", preannounce: str = "", start_conversation: bool = False) -> bool:
        if self.settings.muted:
            self._send(pb.VoiceAssistantAnnounceFinished(success=False))
            return False
        self._announcing = True
        self._publish()
        stop = self._spawn(self._enable_stop_word_later())
        ok = True
        try:
            if text:
                self._handle("announce.show", message=text, title="", kind="info")
            if preannounce:
                await self.audio.play(preannounce)
            if media_id:
                ok = await self.audio.play(media_id)
        finally:
            stop.cancel()
            self._announcing = False
            self._publish()
            self._update_stop_word()
        self._send(pb.VoiceAssistantAnnounceFinished(success=ok))
        if start_conversation and self.phase is Phase.IDLE and not self.settings.muted:
            await self._begin(None, chime=False)
        return ok

    # ---- timers ----------------------------------------------------------------------------------

    def _on_timer(self, conn: Any, msg: Any) -> None:
        self._handle("voice.timer", kind=int(msg.event_type), ha_id=msg.timer_id, name=msg.name,
                     total=int(msg.total_seconds), left=int(msg.seconds_left),
                     active=bool(msg.is_active))

    def on_state(self, patch: dict) -> None:
        """Called with every state patch: starts and stops the ringing sound when a timer rings or is dismissed."""
        if "ringing" not in patch:
            return
        if patch["ringing"]:
            if self._ring_task is None and self.phase is not Phase.NOT_READY:
                self._ring_task = self._spawn(self._ring())
        elif self._ring_task:
            self._ring_task.cancel()
            self._ring_task = None
            self.audio.stop_playback("announce")
        self._publish()
        self._update_stop_word()

    async def _ring(self) -> None:
        loop = asyncio.get_running_loop()
        began = loop.time()
        try:
            while loop.time() - began < RING_CAP_S:
                await self.audio.play("sound:timer")
                await self._sleep(RING_GAP_S)
        finally:
            self._ring_task = None
        if self._state.get("ringing"):
            self._handle("timer.dismiss")                     # the 15-minute cap

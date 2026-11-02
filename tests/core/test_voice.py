"""The voice satellite end to end: a real aioesphomeapi client plays Home Assistant over a Noise-encrypted link, and the
audio hardware and wake engine are fakes. Nothing here touches a microphone, a speaker or a real Home Assistant."""
import asyncio

import pytest
from aioesphomeapi import APIClient, VoiceAssistantEventType as Ev, VoiceAssistantTimerEventType as TimerEv
from aioesphomeapi import api_pb2 as pb

from havenos.core import Core
from havenos.core.esphome import ESPHomeDevice, noise
from havenos.core.media.sources.fake import FakeSource
from havenos.core.persist import SettingsPersister
from havenos.core.voice import satellite as sat_mod
from conftest import instant_sleep, wait_for
from fakes import FakeAudio, ScriptedWake

CHUNK = b"\x01\x00" * 160


class HA:
    """What Home Assistant sees of the satellite."""

    def __init__(self) -> None:
        self.starts: list[tuple] = []
        self.audio: list[bytes] = []
        self.stops: list[bool] = []
        self.finished: list[bool] = []

    async def on_start(self, conversation_id, flags, settings, wake_word):
        self.starts.append((conversation_id, flags, settings, wake_word))
        return 0

    async def on_stop(self, abort):
        self.stops.append(abort)

    async def on_audio(self, data, data2=None):
        self.audio.append(data)


@pytest.fixture
async def rig(make_config, clock):
    core = Core(make_config(voice_enabled=True), clock=clock, sleep=instant_sleep)
    await core.start()
    audio, engine = FakeAudio(), ScriptedWake()
    key = noise.generate_key()
    dev = ESPHomeDevice(core, name="havenos-test", port=0, host="127.0.0.1", advertise=False, key=key,
                        voice_audio=audio, voice_engine=engine)
    await dev.start()
    client = APIClient("127.0.0.1", dev.port, None, noise_psk=key, client_info="pytest-ha")
    await client.connect(login=True)
    ha = HA()
    client.subscribe_voice_assistant(handle_start=ha.on_start, handle_stop=ha.on_stop, handle_audio=ha.on_audio)
    await wait_for(lambda: audio.on_chunk is not None)

    class Rig:
        pass
    r = Rig()
    r.core, r.audio, r.engine, r.dev, r.client, r.ha, r.sat, r.clock = core, audio, engine, dev, client, ha, dev.voice, clock

    def event(kind, **data):
        client.send_voice_assistant_event(kind, {k: str(v) for k, v in data.items()})

    async def wake(word="okay_nabu"):
        engine.queue.append(word)
        audio.on_chunk(CHUNK)
        await wait_for(lambda: len(ha.starts) >= 1)
    r.event, r.wake = event, wake
    yield r
    await client.disconnect()
    await dev.stop()
    await core.stop()


async def converse(r, *, reply_url="http://ha/tts.mp3", text="turn on the lights", answer="Okay.", **intent_end):
    """Drive HA's side of one normal pipeline run after the wake word."""
    r.event(Ev.VOICE_ASSISTANT_RUN_START, url=reply_url)
    r.event(Ev.VOICE_ASSISTANT_STT_VAD_START)
    r.event(Ev.VOICE_ASSISTANT_STT_VAD_END)
    r.event(Ev.VOICE_ASSISTANT_STT_END, text=text)
    r.event(Ev.VOICE_ASSISTANT_INTENT_START)
    r.event(Ev.VOICE_ASSISTANT_INTENT_END, **intent_end)
    r.event(Ev.VOICE_ASSISTANT_TTS_START, text=answer)
    r.event(Ev.VOICE_ASSISTANT_TTS_END, url=reply_url)
    r.event(Ev.VOICE_ASSISTANT_RUN_END)


# ---- setup and gating --------------------------------------------------------------------------------------------

async def test_voice_refuses_to_run_without_noise_encryption(make_config, clock):
    core = Core(make_config(voice_enabled=True), clock=clock, sleep=instant_sleep)
    await core.start()
    d = ESPHomeDevice(core, name="havenos-test", port=0, host="127.0.0.1", advertise=False)       # no key
    assert d.voice is None and d._device_info().voice_assistant_feature_flags == 0
    assert core.voice is None
    await core.stop()


async def test_voice_is_off_unless_enabled(make_config, clock):
    core = Core(make_config(), clock=clock, sleep=instant_sleep)
    await core.start()
    d = ESPHomeDevice(core, name="havenos-test", port=0, host="127.0.0.1", advertise=False, key=noise.generate_key())
    assert d.voice is None
    await core.stop()


async def test_advertises_vpe_features_entities_and_announce_support(rig):
    info = await rig.client.device_info()
    assert info.voice_assistant_feature_flags == 63                 # voice, speaker, API audio, timers, announce, start_conversation
    ents, _ = await rig.client.list_entities_services()
    by = {e.object_id: e for e in ents}
    assert {"mute", "wake_sound", "wake_word_sensitivity"} <= set(by)
    assert by["wake_word_sensitivity"].options == ["Slightly sensitive", "Moderately sensitive", "Very sensitive"]
    assert by["media_player"].feature_flags & 1048576 and by["media_player"].feature_flags & 512      # announce + play_media


async def test_ready_state_follows_the_home_assistant_connection(rig):
    await wait_for(lambda: rig.core.state["voice_ready"])
    await rig.client.disconnect()
    await wait_for(lambda: not rig.core.state["voice_ready"])
    rig.core.handle("voice.start")                                  # the mic button says why nothing happens
    assert rig.core.state["announcement"] and "not connected" in rig.core.state["announcement"]["message"]
    assert rig.ha.starts == []


async def test_wake_word_configuration_roundtrip(rig):
    cfg = await rig.client.get_voice_assistant_configuration(3)
    assert [w.id for w in cfg.available_wake_words] == ["okay_nabu", "hey_jarvis", "hey_mycroft"]
    assert cfg.active_wake_words == ["okay_nabu"] and cfg.max_active_wake_words == 2
    await rig.client.set_voice_assistant_configuration(["hey_jarvis", "okay_nabu", "hey_mycroft", "bogus"])
    await wait_for(lambda: rig.core.state["voice_wake_words"] == ["hey_jarvis", "okay_nabu"])       # known only, at most two
    assert rig.engine.configured[-1][0] == ("hey_jarvis", "okay_nabu")
    cfg = await rig.client.get_voice_assistant_configuration(3)
    assert cfg.active_wake_words == ["hey_jarvis", "okay_nabu"]


async def test_settings_entities_drive_the_satellite(rig):
    ents, _ = await rig.client.list_entities_services()
    by = {e.object_id: e for e in ents}
    got = {}
    rig.client.subscribe_states(lambda s: got.__setitem__(s.key, s))
    await wait_for(lambda: by["mute"].key in got)
    rig.client.select_command(by["wake_word_sensitivity"].key, "Very sensitive")
    await wait_for(lambda: rig.engine.configured[-1][1] == "Very sensitive")
    await wait_for(lambda: got[by["wake_word_sensitivity"].key].state == "Very sensitive")
    rig.client.switch_command(by["wake_sound"].key, False)
    await wait_for(lambda: rig.core.state["voice_wake_sound"] is False)
    rig.client.switch_command(by["mute"].key, True)
    await wait_for(lambda: got[by["mute"].key].state is True and rig.core.state["voice_muted"])
    rig.client.select_command(by["wake_word_sensitivity"].key, "nonsense")                           # ignored
    await asyncio.sleep(0.05)
    assert rig.core.state["voice_sensitivity"] == "Very sensitive"


# ---- a conversation ----------------------------------------------------------------------------------------------

async def test_wake_word_runs_a_full_conversation(rig):
    await rig.wake()
    assert rig.audio.sources()[0] == "sound:wake"                    # the chime came first
    conv, flags, settings, phrase = rig.ha.starts[0]
    assert phrase == "Okay Nabu" and flags == pb.VOICE_ASSISTANT_REQUEST_USE_VAD
    assert (settings.noise_suppression_level, settings.auto_gain) == (2, 31)       # default profile: no DSP chip, so HA cleans up
    await wait_for(lambda: rig.core.state["voice"] == "listening")

    for _ in range(3):
        rig.audio.on_chunk(CHUNK)                                    # speech streams to HA while listening
    await wait_for(lambda: len(rig.ha.audio) >= 3 and rig.ha.audio[0] == CHUNK)

    states = []
    rig.core.bus.subscribe(lambda ev: states.append(ev.data["patch"]["voice"]) if ev.type == "state.patch" and "voice" in ev.data["patch"] else None)
    await converse(rig)
    await wait_for(lambda: rig.core.state["voice"] == "idle" and "responding" in states)
    assert states == ["processing", "responding", "idle"]          # (listening was already showing)
    assert rig.core.state["transcript"] == "turn on the lights" and rig.core.state["response"] == "Okay."
    assert rig.audio.sources() == ["sound:wake", "http://ha/tts.mp3"]                         # the reply played once
    before = len(rig.ha.audio)
    rig.audio.on_chunk(CHUNK)                                       # speech is over: nothing more goes to HA
    await asyncio.sleep(0.05)
    assert len(rig.ha.audio) == before


async def test_audio_never_leaves_the_device_before_a_wake(rig):
    for _ in range(20):
        rig.audio.on_chunk(CHUNK)
    await asyncio.sleep(0.1)
    assert rig.ha.audio == [] and rig.ha.starts == [] and rig.engine.fed == 20


async def test_no_chime_when_wake_sound_is_off(rig):
    rig.sat.set_wake_sound(False)
    await rig.wake()
    assert "sound:wake" not in rig.audio.sources()


async def test_streaming_tts_starts_early_and_plays_once(rig):
    await rig.wake()
    rig.audio.gate.clear()                                           # the reply takes a while to speak
    rig.event(Ev.VOICE_ASSISTANT_RUN_START, url="http://ha/stream.mp3")
    rig.event(Ev.VOICE_ASSISTANT_STT_VAD_END)
    rig.event(Ev.VOICE_ASSISTANT_INTENT_PROGRESS, tts_start_streaming="1")
    await wait_for(lambda: "http://ha/stream.mp3" in rig.audio.sources())
    assert rig.core.state["voice"] == "responding"
    rig.event(Ev.VOICE_ASSISTANT_TTS_START, text="Hello there")
    rig.event(Ev.VOICE_ASSISTANT_TTS_END, url="http://ha/stream.mp3")
    rig.event(Ev.VOICE_ASSISTANT_RUN_END)
    await asyncio.sleep(0.1)
    assert rig.core.state["voice"] == "responding"                   # run ended but the reply is still being spoken
    rig.audio.gate.set()
    await wait_for(lambda: rig.core.state["voice"] == "idle")
    assert rig.audio.sources().count("http://ha/stream.mp3") == 1


async def test_continued_conversation_listens_again_without_a_wake_word(rig):
    await rig.wake()
    await converse(rig, continue_conversation="1", conversation_id="conv-1", answer="Which room?")
    await wait_for(lambda: len(rig.ha.starts) == 2)
    assert rig.ha.starts[1][0] == "conv-1" and rig.ha.starts[1][3] in (None, "")
    assert rig.audio.sources().count("sound:wake") == 1               # no second chime
    await wait_for(lambda: rig.core.state["voice"] == "listening")
    await converse(rig)                                              # the follow-up ends the conversation normally
    await wait_for(lambda: rig.core.state["voice"] == "idle")
    await asyncio.sleep(0.05)
    assert len(rig.ha.starts) == 2


async def test_pipeline_errors(rig):
    await rig.wake()
    rig.event(Ev.VOICE_ASSISTANT_ERROR, code="stt-no-text-recognized", message="nothing heard")
    await wait_for(lambda: rig.core.state["voice"] == "idle")
    assert not any(s.startswith("sound:") and s != "sound:wake" for s in rig.audio.sources())     # quiet: nothing was said

    rig.ha.starts.clear()
    await rig.wake()
    seen = []
    rig.core.bus.subscribe(lambda ev: seen.append(ev.data["patch"]["voice"]) if ev.type == "state.patch" and "voice" in ev.data["patch"] else None)
    rig.event(Ev.VOICE_ASSISTANT_ERROR, code="intent-failed", message="boom")
    await wait_for(lambda: "error" in seen and rig.core.state["voice"] == "idle")
    assert "sound:cloud_expired" not in rig.audio.sources()           # like the VPE: red display, no sound, for ordinary errors

    rig.ha.starts.clear()
    await rig.wake()
    rig.event(Ev.VOICE_ASSISTANT_ERROR, code="cloud-auth-failed", message="expired")
    await wait_for(lambda: "sound:cloud_expired" in rig.audio.sources())          # the one error it speaks about


# ---- the wake cascade --------------------------------------------------------------------------------------------

async def test_mute_ignores_wake_and_stops_the_assistant(rig):
    await rig.wake()
    rig.sat.set_muted(True)
    await wait_for(lambda: rig.ha.stops or rig.core.state["voice"] == "idle")
    assert rig.core.state["voice_muted"] is True and rig.core.state["voice"] == "idle"
    rig.ha.starts.clear()
    fed = rig.engine.fed
    rig.engine.queue.append("okay_nabu")
    rig.audio.on_chunk(CHUNK)
    rig.core.handle("voice.start")
    await asyncio.sleep(0.1)
    assert rig.ha.starts == [] and rig.engine.fed == fed              # muted: the engine does not even hear the audio


async def test_wake_while_a_timer_rings_stops_the_timer_not_the_assistant(rig):
    rig.core.state["ringing"] = {"id": 1, "label": "Pasta", "total": 60, "end": 0}
    await asyncio.sleep(0)
    rig.engine.queue.append("okay_nabu")
    rig.audio.on_chunk(CHUNK)
    await wait_for(lambda: rig.core.state["ringing"] is None)
    await asyncio.sleep(0.05)
    assert rig.ha.starts == [] and rig.core.state["voice"] == "idle"


async def test_wake_while_the_assistant_runs_stops_it(rig):
    await rig.wake()
    await wait_for(lambda: rig.core.state["voice"] == "listening")
    rig.engine.queue.append("okay_nabu")
    rig.audio.on_chunk(CHUNK)                                         # streaming now, so this chunk is audio, not a wake...
    rig.sat.wake("okay_nabu")                                         # ...a wake word during a reply or by the button stops it
    await wait_for(lambda: rig.core.state["voice"] == "idle")
    await wait_for(lambda: rig.ha.stops)


async def test_only_the_button_pauses_music(rig):
    src = FakeSource("spotify", "Spotify")
    rig.core.music.register(src)
    src.connect("phone")
    src.play()
    await wait_for(lambda: rig.core.state["music"]["status"] == "playing")
    rig.sat.wake("okay_nabu")                                         # a wake word does not touch the music...
    await wait_for(lambda: rig.ha.starts)
    assert rig.core.state["music"]["status"] == "playing"
    rig.sat.stop_assistant()
    await wait_for(lambda: rig.core.state["voice"] == "idle")
    rig.core.handle("voice.start")                                    # ...the mic button does
    await wait_for(lambda: rig.core.state["music"]["status"] == "paused")
    assert len(rig.ha.starts) == 1


async def test_the_mic_button_starts_and_the_dismiss_button_stops(rig):
    rig.core.handle("voice.start")
    await wait_for(lambda: rig.ha.starts)
    await wait_for(lambda: rig.core.state["voice"] == "listening")
    rig.core.handle("voice.stop")
    await wait_for(lambda: rig.core.state["voice"] == "idle" and rig.ha.stops)


async def test_music_ducks_while_the_assistant_runs(rig):
    ducks = []
    rig.core.music.duck = lambda on: ducks.append(on)
    await rig.wake()
    await wait_for(lambda: True in ducks)
    rig.sat.stop_assistant()
    await wait_for(lambda: ducks[-1] is False)


# ---- stop word ---------------------------------------------------------------------------------------------------

async def test_stop_word_is_only_enabled_when_there_is_something_to_cancel(rig):
    assert rig.engine.stop_enabled is False
    rig.core._set(ringing={"id": 1, "label": "Tea", "total": 60, "end": 0})
    await wait_for(lambda: rig.engine.stop_enabled)
    rig.engine.queue.append("stop")
    rig.audio.on_chunk(CHUNK)                                         # "stop" ends the ring
    await wait_for(lambda: rig.core.state["ringing"] is None)
    await wait_for(lambda: not rig.engine.stop_enabled)

    await rig.wake()
    rig.audio.gate.clear()
    rig.event(Ev.VOICE_ASSISTANT_RUN_START, url="http://ha/long.mp3")
    rig.event(Ev.VOICE_ASSISTANT_STT_VAD_END)
    rig.event(Ev.VOICE_ASSISTANT_INTENT_PROGRESS, tts_start_streaming="1")
    await wait_for(lambda: rig.engine.stop_enabled)                   # a reply is being spoken: "stop" can cancel it
    rig.engine.queue.append("stop")
    rig.audio.on_chunk(CHUNK)
    await wait_for(lambda: rig.core.state["voice"] == "idle" and not rig.engine.stop_enabled)
    assert rig.ha.stops


# ---- announcements -----------------------------------------------------------------------------------------------

async def test_announcement_plays_reports_back_and_ducks_the_music(rig):
    busy = []
    rig.core.bus.subscribe(lambda ev: busy.append(ev.data["patch"]["voice_busy"]) if ev.type == "state.patch" and "voice_busy" in ev.data["patch"] else None)
    r = await rig.client.send_voice_assistant_announcement_await_response(
        "http://ha/ding.mp3", 3, text="Dinner is ready", preannounce_media_id="http://ha/pre.mp3")
    assert r.success is True
    assert rig.audio.sources() == ["http://ha/pre.mp3", "http://ha/ding.mp3"]                       # pre-announce first
    assert busy == [True, False]
    assert rig.core.state["announcement"]["message"] == "Dinner is ready"


async def test_announcement_can_start_a_conversation(rig):
    r = await rig.client.send_voice_assistant_announcement_await_response("http://ha/q.mp3", 3, text="Want the lights on?",
                                                                          start_conversation=True)
    assert r.success is True
    await wait_for(lambda: rig.ha.starts)
    assert rig.audio.sources().count("sound:wake") == 0               # it already spoke; no chime


async def test_muted_satellite_refuses_announcements(rig):
    rig.sat.set_muted(True)
    r = await rig.client.send_voice_assistant_announcement_await_response("http://ha/ding.mp3", 3)
    assert r.success is False and "http://ha/ding.mp3" not in rig.audio.sources()


async def test_media_player_announce_plays_through_the_satellite(rig):
    ents, _ = await rig.client.list_entities_services()
    mp = next(e for e in ents if e.object_id == "media_player")
    rig.client.media_player_command(mp.key, media_url="http://ha/alert.mp3", announcement=True)
    await wait_for(lambda: "http://ha/alert.mp3" in rig.audio.sources())


# ---- timers ------------------------------------------------------------------------------------------------------

async def test_voice_timers_feed_the_timer_book_and_ring(rig):
    c, core = rig.client, rig.core
    base = len(core.state["timers"])                                  # the demo "Pasta" timer is already there
    c.send_voice_assistant_timer_event(TimerEv.VOICE_ASSISTANT_TIMER_STARTED, "t1", "Eggs", 600, 600, True)
    await wait_for(lambda: len(core.state["timers"]) == base + 1)
    t = next(t for t in core.state["timers"] if t["label"] == "Eggs")
    assert t["total"] == 600 and t["end"] == int(rig.clock() * 1000) + 600_000
    c.send_voice_assistant_timer_event(TimerEv.VOICE_ASSISTANT_TIMER_UPDATED, "t1", "Eggs", 600, 300, True)
    await wait_for(lambda: next(t for t in core.state["timers"] if t["label"] == "Eggs")["end"] == int(rig.clock() * 1000) + 300_000)

    c.send_voice_assistant_timer_event(TimerEv.VOICE_ASSISTANT_TIMER_STARTED, "t2", "", 60, 60, True)
    await wait_for(lambda: any(t["label"] == "Timer" for t in core.state["timers"]))
    c.send_voice_assistant_timer_event(TimerEv.VOICE_ASSISTANT_TIMER_CANCELLED, "t2", "", 60, 30, False)
    await wait_for(lambda: not any(t["label"] == "Timer" for t in core.state["timers"]))

    c.send_voice_assistant_timer_event(TimerEv.VOICE_ASSISTANT_TIMER_FINISHED, "t1", "Eggs", 600, 0, False)
    await wait_for(lambda: any(t["label"] == "Eggs" and t["end"] <= int(rig.clock() * 1000) for t in core.state["timers"]))
    await core.tick()                                                 # the existing ring takeover takes it from here
    assert core.state["ringing"]["label"] == "Eggs"
    await wait_for(lambda: "sound:timer" in rig.audio.sources())      # the satellite rings the speaker
    assert core.state["voice_busy"] is True
    core.handle("timer.dismiss")
    await wait_for(lambda: core.state["ringing"] is None and core.state["voice_busy"] is False)
    assert None in rig.audio.stopped or "announce" in rig.audio.stopped


async def test_ringing_stops_by_itself_after_the_cap(rig, monkeypatch):
    monkeypatch.setattr(sat_mod, "RING_CAP_S", 0.05)
    rig.core._set(ringing={"id": 1, "label": "Tea", "total": 60, "end": 0})
    await wait_for(lambda: rig.core.state["ringing"] is None)         # dismissed by the satellite at the cap
    assert rig.audio.sources().count("sound:timer") >= 1


async def test_a_ringing_timer_stays_for_fifteen_minutes_not_thirty_seconds(rig):
    assert rig.core.config.ring_auto_dismiss_s >= 15 * 60


# ---- profiles, persistence ----------------------------------------------------------------------------------------

async def test_a_dsp_board_asks_home_assistant_for_no_extra_processing(rig):
    from havenos.core.voice.profiles import XVF3800
    rig.sat.profile = XVF3800                                          # the chip already cleaned the audio, like the VPE's
    await rig.wake()
    _, _, settings, _ = rig.ha.starts[0]
    assert (settings.noise_suppression_level, settings.auto_gain, settings.volume_multiplier) == (0, 0, 1.0)


async def test_voice_settings_persist_only_when_voice_is_on(rig, make_config, clock, tmp_path):
    rig.sat.set_sensitivity("Very sensitive")
    rig.sat.set_wake_words(("hey_jarvis",))
    p = SettingsPersister(rig.core)
    assert p.flush() is True
    import tomllib
    toml = tomllib.loads(rig.core.config.config_path.read_text())
    assert toml["voice"] == {"wake_sound": True, "sensitivity": "Very sensitive", "wake_words": ["hey_jarvis"]}

    off = Core(make_config(config_path=tmp_path / "other" / "c.toml"), clock=clock, sleep=instant_sleep)
    await off.start()
    SettingsPersister(off).flush()
    assert "voice" not in tomllib.loads(off.config.config_path.read_text())
    await off.stop()


def test_voice_config_loads_from_toml(tmp_path, monkeypatch):
    from havenos.core.config import Config
    cfg = tmp_path / "c.toml"
    cfg.write_text('[esphome]\nenabled = true\nkey = "abc"\n[voice]\nenabled = true\nprofile = "xvf3800"\nsensitivity = "Very sensitive"\nwake_words = ["hey_jarvis", "okay_nabu"]\n')
    for k in ("HAVENOS_VOICE", "HAVENOS_VOICE_PROFILE", "HAVENOS_ESPHOME_KEY", "HAVENOS_ESPHOME"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("HAVENOS_CONFIG", str(cfg))
    c = Config.from_env(tmp_path)
    assert (c.voice_enabled, c.voice_profile, c.esphome_key) == (True, "xvf3800", "abc")
    assert c.voice_sensitivity == "Very sensitive" and c.voice_wake_words == ("hey_jarvis", "okay_nabu")


async def test_voice_can_pause_and_resume_a_timer(rig):
    c, core, clock = rig.client, rig.core, rig.clock
    timer = lambda: next(t for t in core.state["timers"] if t["label"] == "Eggs")
    c.send_voice_assistant_timer_event(TimerEv.VOICE_ASSISTANT_TIMER_STARTED, "t1", "Eggs", 600, 600, True)
    await wait_for(lambda: any(t["label"] == "Eggs" for t in core.state["timers"]))
    clock.advance(30)
    c.send_voice_assistant_timer_event(TimerEv.VOICE_ASSISTANT_TIMER_UPDATED, "t1", "Eggs", 600, 500, False)   # "pause the eggs timer"
    await wait_for(lambda: timer()["paused"])
    assert timer()["left"] == 500
    clock.advance(100)                                                 # time passes while paused: it does not run down
    await core.tick()
    assert core.state["ringing"] is None and timer()["left"] == 500

    c.send_voice_assistant_timer_event(TimerEv.VOICE_ASSISTANT_TIMER_UPDATED, "t1", "Eggs", 600, 500, True)   # resume
    await wait_for(lambda: not timer()["paused"])
    assert timer()["end"] == int(clock() * 1000) + 500_000 and timer()["total"] == 600

    c.send_voice_assistant_timer_event(TimerEv.VOICE_ASSISTANT_TIMER_UPDATED, "t1", "Eggs", 600, 400, False)
    await wait_for(lambda: timer()["paused"])
    c.send_voice_assistant_timer_event(TimerEv.VOICE_ASSISTANT_TIMER_FINISHED, "t1", "Eggs", 600, 0, False)   # finishing wins over a pause
    await wait_for(lambda: any(t["label"] == "Eggs" and not t["paused"] for t in core.state["timers"]))
    await core.tick()
    assert core.state["ringing"]["label"] == "Eggs"


# ---- spoken library search -----------------------------------------------------------------------------------------

import numpy as np

from havenos.core.media.library import DemoLibrary


def _noise(secs, db=-60):
    return (np.random.default_rng(5).normal(0, 1, int(16000 * secs)) * 32768 * 10 ** (db / 20)).astype(np.int16)


def _speech(secs=1.0):
    t = np.arange(int(16000 * secs)) / 16000
    return (np.sin(2 * np.pi * 300 * t) * 32768 * 10 ** (-22 / 20)).astype(np.int16)


async def _say(rig, pcm, chunk=640):
    for i in range(0, len(pcm), chunk):
        rig.audio.on_chunk(pcm[i:i + chunk].tobytes())
        await asyncio.sleep(0)


async def _spoken(rig, *, quiet_after=3.0):
    await wait_for(lambda: rig.core.state["voice"] == "listening")
    await _say(rig, np.concatenate([_noise(0.4), _speech(1.0), _noise(quiet_after)]))


async def test_a_spoken_search_records_transcribes_and_never_touches_the_assist_pipeline(rig):
    heard = []

    async def transcribe(pcm):
        heard.append(pcm)
        return "  play some jazz "

    states = []
    rig.core.bus.subscribe(lambda ev: states.append(ev.data["patch"]["voice"]) if ev.type == "state.patch" and "voice" in ev.data["patch"] else None)
    task = asyncio.create_task(rig.sat.listen_for_text(transcribe))
    await _spoken(rig)
    assert await asyncio.wait_for(task, 3) == "play some jazz"
    assert len(heard) == 1 and len(heard[0]) > 16000 * 2             # about a second of speech, as 16-bit PCM
    assert rig.audio.sources() == ["sound:wake"]                      # the same chime as the assistant
    assert states == ["listening", "processing", "idle"] and rig.core.state["transcript"] == "play some jazz"
    assert rig.ha.starts == [] and rig.ha.audio == []                 # nothing reached Home Assistant's Assist pipeline


async def test_nothing_said_or_a_failed_transcription_returns_none(rig):
    async def boom(pcm):
        raise RuntimeError("no stt")

    task = asyncio.create_task(rig.sat.listen_for_text(boom))
    await wait_for(lambda: rig.core.state["voice"] == "listening")
    await _say(rig, _noise(8))                                        # silence until the wait runs out
    assert await asyncio.wait_for(task, 3) is None and rig.core.state["voice"] == "idle"

    seen = []
    rig.core.bus.subscribe(lambda ev: seen.append(ev.data["patch"]["voice"]) if ev.type == "state.patch" and "voice" in ev.data["patch"] else None)
    task = asyncio.create_task(rig.sat.listen_for_text(boom))
    await _spoken(rig)
    assert await asyncio.wait_for(task, 3) is None
    await wait_for(lambda: rig.core.state["voice"] == "idle")
    assert "error" in seen                                            # the red sheet, like any pipeline error


async def test_a_spoken_search_is_refused_while_muted_or_busy_and_can_be_cancelled(rig):
    async def never(pcm):
        return "x"

    rig.sat.set_muted(True)
    assert await rig.sat.listen_for_text(never) is None
    rig.sat.set_muted(False)

    task = asyncio.create_task(rig.sat.listen_for_text(never))
    await wait_for(lambda: rig.core.state["voice"] == "listening")
    assert await rig.sat.listen_for_text(never) is None               # one at a time
    rig.sat.wake("okay_nabu")                                         # a wake word or the mic button cancels it
    assert await asyncio.wait_for(task, 3) is None
    await wait_for(lambda: rig.core.state["voice"] == "idle")
    assert rig.ha.starts == []                                        # ...and does not start the assistant


async def test_the_library_mic_button_searches_by_voice(rig):
    core = rig.core
    core.library = DemoLibrary(lambda item: None)
    core._set(library={**core.state["library"], "available": True})

    async def transcribe(pcm):
        return "evening"                                              # something the demo library has
    core._transcribe = transcribe
    core.handle("library.voice")
    await wait_for(lambda: core.state["library"]["listening"])
    await _spoken(rig)
    await wait_for(lambda: core.state["library"]["query"] == "evening" and not core.state["library"]["busy"])
    lib = core.state["library"]
    assert lib["listening"] is False and lib["sections"] and lib["error"] == ""


async def test_a_spoken_search_with_nothing_heard_says_so(rig):
    core = rig.core
    core.library = DemoLibrary(lambda item: None)

    async def transcribe(pcm):
        return ""
    core._transcribe = transcribe
    core.handle("library.voice")
    await _spoken(rig)
    await wait_for(lambda: core.state["library"]["error"] == "Didn't catch that")
    assert core.state["library"]["listening"] is False


async def test_the_library_mic_needs_voice_to_be_ready(rig):
    core = rig.core
    core.library = DemoLibrary(lambda item: None)
    await rig.client.disconnect()
    await wait_for(lambda: not core.state["voice_ready"])
    core.handle("library.voice")
    assert "Voice search needs" in core.state["announcement"]["message"]
    core.library = None
    core._announce_queue.clear()
    core._set(announcement=None)
    core.handle("library.voice")                                      # no library: nothing at all
    assert core.state["announcement"] is None


async def test_transcription_goes_to_home_assistants_stt(make_config, clock, ha):
    from havenos.core.config import HAConfig
    ha.set("stt.whisper", "unknown")
    core = Core(make_config(ha=HAConfig(url=ha.url, token="good-token"), voice_stt_entity="stt.whisper"),
                clock=clock, sleep=instant_sleep)
    await core.start()
    try:
        await wait_for(lambda: core.state["ha_status"] == "connected")
        assert await core._transcribe(b"\x01\x00" * 100) == "play some jazz"
        assert ha.stt_requests[0]["entity"] == "stt.whisper"
        ha.stt_status = 500
        with pytest.raises(Exception, match="500"):
            await core._transcribe(b"\x01\x00" * 100)
    finally:
        await core.stop()
    demo = Core(make_config(), clock=clock, sleep=instant_sleep)               # demo mode has no Home Assistant at all
    with pytest.raises(Exception, match="not connected"):
        await demo._transcribe(b"\0\0")

# Spec 05: voice pipeline that behaves like a Home Assistant Voice Preview Edition (VPE)

Status: **partly built** (section 9 says what and how far it was checked). It builds on `04-esphome-integration.md` (the ESPHome server and its `add_handler` seam).

## 1. Goal and what "match the VPE" means

To Home Assistant, a havenOS display should look like a VPE satellite to it (close, not byte-for-byte identical; where unsure, do what is reasonable): the same entities and options, the same wake words, the same conversation, announcement and timer behavior, and to the user the same *feel* (wake chime, ducking music, "stop", ringing timers, mute). Where hardware differs, the **screen replaces the LED ring**.

Parity is judged against two references:

1. **The VPE firmware source** (`esphome/home-assistant-voice-pe` at `d4e6fa4`, Sep 2026): read in full for the voice logic. Its YAML is MIT; its C++ ESPHome components are GPLv3 (we do not copy those); its sounds are CC BY 4.0 (usable with attribution to Clayton Charles Tapp).
2. **A real VPE (firmware 26.9.0, ESPHome 2026.6.0)**, read from HA's registries (read-only). Its entity list is the contract in section 3.

Not matchable, by design: the VPE's exact XMOS DSP tuning (our USB mic array carries a sibling XMOS chip, section 6), the LED ring hardware, the rotary dial and the physical mute switch.

## 2. VPE behavior, extracted from the firmware

### 2.1 Phases (a single state machine drives everything else)

| # | Phase | Entered when | VPE shows (LED ring) | havenOS shows (planned) |
|---|---|---|---|---|
| 1 | idle | pipeline ended, or client connected | off | nothing (small mic glyph if muted) |
| 2 | waiting for command | wake word / button, listening begins | slow clockwise spin | voice sheet opens, pulsing mic |
| 3 | listening | STT VAD start (speech heard) | fast clockwise spin | live waveform + partial transcript |
| 4 | thinking | STT VAD end | spin stops, 2 LEDs blink | dots / spinner |
| 5 | replying | `INTENT_PROGRESS` with a streaming TTS URL, or `TTS_START` | fast anticlockwise spin | reply text + waveform |
| 10 | not ready | HA not connected | red twinkle | greyed mic, "Home Assistant unreachable" |
| 11 | error | pipeline error (not `duplicate_wake_up_detected`, not `stt-no-text-recognized`) | fast red pulse, held 1 s | red voice sheet for 1 s |

Also: **timer ticking** (ring shows remaining fraction), **timer ringing** (pulsing ring), **muted** (red LED by the mics). Those become dashboard/ambient timer UI (already built) and a mute indicator.

### 2.2 What happens on a wake word (priority cascade, in this order)

1. Muted: ignore.
2. A timer is ringing: **stop the timer, do not start the assistant** ("stop the timer by voice").
3. The assistant is running: stop it.
4. An announcement is playing: stop it.
5. Otherwise: if *Wake sound* is on, play the wake chime (priority, interrupts anything), wait **300 ms**, then start the assistant with that wake word.

The center button runs the same cascade with one extra step before 5: if media is playing, **pause it** instead of starting. In havenOS the on-screen mic button is the center button; the existing touch events map to its double / triple / long press events.

### 2.3 The stop word ("stop")

A built-in microWakeWord model that is **only enabled while there is something to cancel**: while a timer rings, and while a spoken reply or announcement plays *if it lasts more than 1 s* (the VPE waits for the announcement to start, then 1 s, then enables it, and disables it when playback ends). This avoids false triggers from the assistant's own speech.

### 2.4 Audio output and ducking

- Two output pipelines into one mixer at 48 kHz stereo: **announcement** (mono FLAC; chimes, TTS, timer sound) and **media** (stereo FLAC; music). Volume range is clamped to 0.4-0.85, steps of 0.05.
- **Ducking: media is lowered 20 dB, instantly, when** the assistant starts, an announcement starts, or a timer starts ringing. It is restored to 0 dB over **1 s** when all three have ended. (The OHF Linux voice project ducks to 50% instead; the VPE's 20 dB is the target.)
- Timer sound repeats with a 500 ms gap; a timer stops ringing by itself after **15 minutes**.

### 2.5 Pipeline details

- Wake word runs **on the device** (microWakeWord, on-device models `okay_nabu`, `hey_jarvis`, `hey_mycroft`, plus the internal `stop`); `use_wake_word` is off on the HA side. Up to **two** wake words active at once.
- **Sensitivity** is one select (Slightly / Moderately / Very sensitive) that sets per-model probability cutoffs (uint8 of 0-255): Okay Nabu 217 / 176 / 143, Hey Jarvis 247 / 235 / 212, Hey Mycroft 253 / 242 / 237. The firmware's comments give the false-accepts-per-hour measured for each.
- The firmware applies **no software noise suppression, gain or volume multiplier** (`noise_suppression_level: 0`, `auto_gain: 0 dbfs`, `volume_multiplier: 1`): the XMOS chip already cleaned the audio. The XMOS chip on our USB mic array plays that role (section 6); software DSP is the fallback.
- Audio to HA is 16 kHz, 16-bit mono, streamed over the API (`API_AUDIO`), starting right after wake detection (nothing is buffered before the wake word).
- TTS can start **before** the response is complete: `INTENT_PROGRESS` carrying a streaming TTS URL starts playback early.
- The mute switch is software-and-hardware; while muted the wake and stop words are ignored; mute does not touch music.

## 3. The entity contract (from your real VPE)

Read from HA's registries. Entities marked *HA* are created by HA's Assist-satellite integration from what the device reports; the rest are created by the device.

| Entity | Type / options | Created by | havenOS plan |
|---|---|---|---|
| Assist satellite | `assist_satellite`, features ANNOUNCE + START_CONVERSATION | HA, from the voice feature flags | advertise the flags |
| Media Player | `media_player`, class speaker; supports pause, volume set/mute, play media, stop, play, browse media, **media announce** (no seek, no next/prev) | device | ESPHome media_player entity with exactly that feature set |
| Mute | switch (config) | device | add |
| Wake sound | switch (config), default on | device | add |
| Wake word sensitivity | select: Slightly / Moderately / Very sensitive (config) | device | add |
| Wake word, Wake word 2 | select: `no_wake_word`, Hey Jarvis, Hey Mycroft, Okay Nabu | HA, from `available_wake_words` / `max_active_wake_words = 2` | answer `VoiceAssistantConfigurationRequest` |
| Assistant, Assistant 2 | select: preferred / Home Assistant | HA | nothing to do |
| Finished speaking detection | select: default / relaxed / aggressive | HA | nothing to do (HA-side VAD tuning) |
| Button press | event (button): single / double / triple / long press | device | reuse the existing Touch event |
| LED ring | light (config) | device | no hardware: map to the screen, optional "voice indicator" light entity later |
| Disable physical controls | switch, disabled by default | device | optional |
| Update, Restart, Beta firmware | | | not applicable |

Device identity to copy: model "Home Assistant Voice PE"-style naming (we keep our own), `esphome_version` should track a current ESPHome release (the real one reports 2026.6.0; the prototype claims 2025.9.0 and should be bumped).

## 4. Architecture

```
 core process (Qt + asyncio, one loop)                         audio worker process
 ──────────────────────────────────────                        ───────────────────────────
 ESPHome server ◄──► VoiceSatellite (state machine, phases) ◄──pipe──► capture → AEC/NS → wake/stop word
        │                    │  events: phase, transcript,             mixer (announce + media) ← decoders
        │                    │  reply, timers, mute                    ducking ramps, playback, level meters
        ▼                    ▼
   Core.state  ──►  voice sheet, timers, mute glyph (QML)
```

- **Audio in its own process.** The GUI thread and the asyncio loop share a GIL; audio callbacks that miss a deadline glitch or drop wake words. A worker process (like the photo pool) owns capture, DSP, wake/stop word, mixing and playback, and talks to the core over a pipe (commands in, events and 16 kHz PCM chunks out). It never imports Qt.
- **`VoiceSatellite`** (core, pure Python, no Qt) holds the phase machine in 2.1 and the wake cascade in 2.2. It registers handlers on the ESPHome server (`VoiceAssistantConfigurationRequest`, `VoiceAssistantEventResponse`, `VoiceAssistantAudio`, `VoiceAssistantAnnounceRequest`, `VoiceAssistantTimerEventResponse`, `VoiceAssistantSetConfiguration`, media-player commands) and sends `VoiceAssistantRequest`/`VoiceAssistantAudio`.
- **Our own mixer, not mpv.** Decode (PyAV or ffmpeg) to 48 kHz PCM, mix two buses with per-bus gain ramps. That gives exact VPE ducking, and the mixer's output is a perfect **echo reference** for software AEC (section 6.1).
- **Existing UI keeps working.** `Core.state` already carries `voice`, `transcript`, `response`; the satellite fills them from real events, replacing `core/voice.py`'s simulation. HA voice timers feed `TimerBook`, so the existing ring takeover handles "timer finished".

## 5. HA protocol plan (what to send, answer and map)

| Step | Message | Plan |
|---|---|---|
| Advertise | `DeviceInfoResponse.voice_assistant_feature_flags` | VOICE_ASSISTANT, SPEAKER, API_AUDIO, TIMERS, ANNOUNCE, START_CONVERSATION (add MULTI_CHANNEL_AUDIO only if we send a reference channel). An exact match with the VPE's flags is not required; use what is reasonable. |
| Wake words | `VoiceAssistantConfigurationRequest/Response`, `VoiceAssistantSetConfiguration` | `available_wake_words` = the three models (same ids/names as the VPE), `max_active_wake_words = 2`; apply `active_wake_words` when HA changes them. |
| Start | `VoiceAssistantRequest(start, wake_word_phrase, flags, audio_settings)` | send from wake word (flags: no HA-side wake word); `audio_settings` zeros if our DSP handles it. |
| Audio | `VoiceAssistantAudio` | 16 kHz s16 mono chunks, begins after wake; stop on `STT_VAD_END`. |
| Events | `VoiceAssistantEventResponse` | map per the phase table; ignore `duplicate_wake_up_detected` and `stt-no-text-recognized` errors quietly. |
| Reply | `INTENT_PROGRESS` (streaming URL) / `TTS_END` URL | download/stream the URL and play on the announcement bus; reply text from `TTS_START` / `INTENT_END` for the screen. |
| Continue | `INTENT_END` with `continue_conversation` | after the reply plus ~0.5 s, listen again without a wake word; keep media ducked until the conversation ends. |
| Announce | `VoiceAssistantAnnounceRequest` (media, text, pre-announce, `start_conversation`) | duck, optional pre-announce chime, play, `VoiceAssistantAnnounceFinished`, then optionally listen. |
| Timers | `VoiceAssistantTimerEventResponse` (started/updated/cancelled/finished) | map to `TimerBook` and the ring takeover; finished = duck + repeat sound + enable stop word. |
| Media | media_player commands | play/pause/stop/volume/mute on the music side; `play_media` URLs play as the Home Assistant music source (spec 07); announcements play on the announce bus. |

## 6. Hardware and the DSP

The VPE's XMOS chip does echo cancellation, beamforming, noise suppression and gain before the host sees audio; that is why its firmware applies none. A Pi has no such chip, so we use a **USB mic array that has one**. Two Seeed boards are supported, and the audio worker takes a device profile (capture device, playback device, playback rate, `hw_aec` flag) so either works with the same code.

| | **reSpeaker XVF3800 USB 4-Mic Array** (preferred) | **reSpeaker Lite 2-Mic Array** (USB, no ESP32) |
|---|---|---|
| Chip | XMOS XVF3800 | XMOS XU316 |
| Mics | 4, circular, multi-beamforming, up to 5 m | 2, up to 3 m, beamforming not stated |
| USB audio rate | a `48k2ch` firmware image exists; flash it (the generic v2.1.0 name does not imply 48 kHz). **Decided: assume it works at 48 kHz**; bring-up only confirms | USB firmware (v2.0.7) is **16 kHz**; the "USB 48K" build is listed as TODO, 48 kHz exists only as I2S for an ESP32-S3 |
| Speaker out | LM48511 class D amp on a JST connector ("5 W amplified speakers") plus a 3.5 mm jack | speaker connector ("5 W amplifier speakers") plus a 3.5 mm jack |
| Mute / LEDs | mute button with red LED, 12 WS2812 | mute button with red LED, USR button, 1 WS2812 |
| Role | all audio (TTS, chimes, timers, music) at 48 kHz through the board | all audio (TTS, chimes, timers, music) at 16 kHz through the board; see the music note below |

Shared design rules:

- **USB, so no header pins.** Nothing conflicts with the display or touch panel. Both enumerate as USB Audio Class 2.0 with no driver; flash firmware with `dfu-util` and a udev rule, and check the version after flashing (the bring-up script does this).
- **Hardware AEC: decided to assume it works** on both boards, cancelling what we play to the board's own USB output. Neither wiki says how the chip gets its echo reference, and a Home Assistant forum thread reports XU316 AEC not removing speaker audio on the real VPE and on a FutureProofHomes Satellite1 (unresolved, newer firmware untested), so the Lite is the riskier of the two. Bring-up (V0b) confirms it rather than gating the build.
- **Software AEC stays as the fallback.** If bring-up later shows a board's own AEC does not work, the audio worker runs WebRTC/speexdsp AEC (section 6.1 below) with the mixer output as the reference. Capture and playback share one USB device, which is the good case for software AEC (the delay is fixed and measured once with a chirp). The KEYESTUDIO ReSpeaker 2-Mic Pi HAT (KS0314, WM8960 codec, no DSP) was the earlier choice; it was dropped because it has no DSP and a driver risk (`seeed-voicecard` on newer kernels), but it still fits the device profile as a software-DSP-only option.
- **Capture:** use the board's processed channel only, downsample to 16 kHz s16 mono for the wake word and Home Assistant. Raw mic channels are ignored, so `MULTI_CHANNEL_AUDIO` is not needed.
- **Wake word while audio plays** should be much closer to the VPE with working hardware AEC, but that is unverified. Keep the mitigations: a volume cap, the stop word, the board's mute button and the touchscreen.
- **Lite music: decided to play everything through it at 16 kHz.** Music will sound like a phone call; that is the accepted cost, and hardware AEC covers all audio. A separate music output would sit on another clock and hurt AEC, so it is not planned. The XVF3800 does not have this limit.
- **Speaker: not a concern for this version.** Both boards' amps are rated for 5 W speakers; we use whatever the amp drives and do not measure loudness or pick a model.
- **Mute:** the board's mute button mutes the mics inside the chip. Reading its state from the host goes through the vendor control tool (`xvf_host` on the XVF3800); this is unchecked. Keep a software mute and an on-screen indicator regardless.
- **Buttons and LEDs:** the touchscreen mic button is the VPE center button (single press runs the wake cascade in 2.2, double / triple / long press become the existing button events). The Lite's USR button can be mapped to it; the XVF3800 has only the mute button. The XVF3800's 12 LEDs can echo the phase colors (idle off, listening blue, thinking, replying, error red) as an optional extra via `xvf_host`; the Lite has one LED.
- **No hardware switch for physical-controls disable**, as on the VPE.

### 6.1 Software echo-cancellation options (fallback)

In order of preference: (1) our own mixer output into WebRTC AEC (or speexdsp) in the worker; (2) PipeWire's `echo-cancel` module; (3) `MULTI_CHANNEL_AUDIO` to HA, only if it checks out.

## 7. Milestones

| # | Deliverable | Verification |
|---|---|---|
| V0 | **Check parity with the VPE where it matters:** compare its DeviceInfo flags, entity categories and media-player features against ours using the registry data we already have; exact matches are not required, do what is reasonable | short list of differences and what we chose |
| V0b | **Mic array bring-up on the Pi, per board (XVF3800 with the `48k2ch` image; Lite):** firmware flashed and version checked, formats the host reports (`arecord -l`), gain staging without clipping, a playback-while-recording check that the chip's AEC works as assumed, mute button and LEDs readable | a bring-up script and a recorded playback-while-recording WAV per board |
| V1 | Audio worker: capture, playback, mixer with ducking ramps, the VPE sounds (CC BY, attributed), level meters | unit tests with a fake audio device; a ducking test that asserts -20 dB instant, 1 s release |
| V1b | **Software AEC spike, only if bring-up shows a board's own AEC does not work (we assume it does):** WebRTC/speexdsp AEC + NS + AGC in the worker using the mixer reference; measure echo reduction and CPU on the Pi 4 | echo-return-loss numbers on recorded playback; CPU under 25% of one core |
| V2 | Wake word + stop word with the VPE's models and cutoffs; sensitivity select; mute | recorded-clip tests; false-accept soak on the Pi |
| V3 | `VoiceSatellite`: phase machine, config exchange, request/audio/events, voice sheet driven by real events | an in-process fake HA (like `tests/fakes.py`) replaying pipeline event scripts; then real Assist |
| V4 | Replies (early streaming TTS), continue conversation, announcements, start_conversation | fake-HA scripts plus real HA |
| V5 | Timers from voice; ringing, stop by word/tap, 15 min cap | scripted timer events |
| V6 | Media player entity with the exact feature set; ducking while media plays | `aioesphomeapi` client tests |
| V7 | Tuning: wake while music or a timer plays, volume cap, optional LED phase colors, the USR button cascade (Lite) | bench tests on the Pi |
| V8 | **Side-by-side with your real VPE:** same phrases from the same spot, compare wake latency, time to first TTS audio, false wakes, ducking feel | scored checklist |

## 8. Risks and open questions

- **Hardware:** two options, the reSpeaker XVF3800 (preferred) and the reSpeaker Lite (section 6). We assume the chips' own AEC and the XVF3800's 48 kHz USB firmware work; neither is verified (no wiki explains the echo reference). The Lite plays everything at 16 kHz. AEC quality drives wake-while-playing performance and is the biggest gap against the VPE; software AEC is the fallback.
- **Pi 4 CPU budget:** microWakeWord (tiny) plus decode/mix plus Qt rendering should fit, but must be measured; the audio worker process is the mitigation.
- **Protocol drift:** the real VPE reports ESPHome 2026.6.0; HA may use newer message fields than our current 1.10 API level. Exact parity is not required; keep `aioesphomeapi` reasonably current and fix what breaks.
- **Security:** the ESPHome link is still plain text with no password; once it carries microphone audio that matters far more. **Decided: use ESPHome Noise encryption**; it lands before voice goes live.
- **Privacy:** audio leaves the device only after the wake word fires (the VPE does the same); keep that invariant and test it.
- **Licensing:** the CC BY sounds are credited in `assets/sounds/ATTRIBUTION.md`; do not copy ESPHome's GPL C++.

## 9. Status: built and not built

Checked on 2026-11-01 on a Mac with the project venv. **Nothing below has run on a microphone, a speaker, a Pi or a real Home Assistant.**

**Built, with what checked it**

- **Noise encryption** for the ESPHome link (`core/esphome/noise.py`; config `[esphome] key`). Checked with the real `aioesphomeapi` client, including a wrong key and a plain-text client. Not checked against Home Assistant itself.
- **Device profiles** for the XVF3800 and the Lite (`core/voice/profiles.py`). Which XVF3800 channel is the processed one is a guess (channel 1) for bring-up to confirm.
- **The VPE sounds** (CC BY 4.0, from the firmware at `d4e6fa4`, unmodified): wake chime, timer, mute on and off, and the cloud-expired message, with `assets/sounds/ATTRIBUTION.md`. Each decodes and plays at both boards' rates (tested). Like the VPE, ordinary pipeline errors show the red sheet with **no sound**; only `cloud-auth-failed` is spoken. A synthesized tone stands in only if a file is missing.
- **Timer pause and resume from voice:** an update with `is_active` false freezes the timer at its remaining time (shown as "paused" on the dashboard, frozen on the ambient pill); active again resumes it; a finish while paused still rings.
- **Play from HA URLs:** `media_player.play_media` plays on the display as the "Home Assistant" music source (play and pause, takeover toast, volume), and the media player now advertises `PLAY_MEDIA`. Tested with real ffmpeg and a fake sink.
- **Mixer and media bus** (`core/audio/`): two buses, 20 dB instant ducking, 1 s restore, the 0.4-0.85 volume clamp, and any number of streams per bus. Music sources and the voice satellite share one `AudioHub` (one mixer, one output), so the mixer output is the exact echo reference. Unit-tested at 48 kHz and 16 kHz with fake devices; the sound-device path has not run.
- **Spoken library search** (`VoiceSatellite.listen_for_text`, `voice/capture.py`): chime, an energy-based end-of-speech detector that learns the room from the first 200 ms, then Home Assistant speech-to-text. Detector tested on synthetic audio and macOS speech; the rest on fakes.
- **Local audio** (`core/voice/audio.py`): sounddevice capture and playback, ffmpeg decode of URLs, stateful 48 to 16 kHz downsampler, channel pick. The decode and mixer path is tested with real ffmpeg and real files; the sound device path is not run. It runs **in-process**, not in the separate worker process section 4 wants, behind the same `AudioBackend` interface.
- **Wake engine** (`core/voice/microwake.py`): microWakeWord through `pymicro-wakeword` with the VPE's cutoffs and a 2 s refractory period. Tested on macOS speech synthesis saying "okay nabu" (heard once, not by a different wake word) and on silence and noise. Not tested on a real voice, a Pi, or for false accepts over time or CPU.
- **VoiceSatellite** (`core/voice/satellite.py`): the phase machine, wake cascade, stop-word rule, early streaming TTS, continued conversation, announcements (including pre-announce and start_conversation), mute, wake word configuration exchange, timers from voice (into `TimerBook` and the ring takeover) and a 15 minute ring cap. Tested end to end over an encrypted link with the real `aioesphomeapi` client playing Home Assistant, and a fake microphone and speaker. The event data names follow Home Assistant's ESPHome integration as I recall it; a real Assist run may differ.
- **Entities:** Mute, Wake sound and Wake word sensitivity, plus the feature flags and `MEDIA_ANNOUNCE` on the media player. Wake word, sensitivity and wake sound are saved to `config.toml` (only when voice is on).
- **UI:** the voice sheet shows real events; an error state; the mic button runs the cascade and says so when Home Assistant is not connected.
- **Bring-up tool** (`python -m havenos.core.voice.bringup`) for V0b. The device listing runs; the playback-while-recording check has not been run on a board.

**Not built**

- The audio worker as a **separate process** (it runs in-process behind the same interface).
- The VPE's **"stop" model** is not bundled with `pymicro-wakeword`; give `[voice] stop_model` its `.json` to enable the stop word. Without it, stop a timer or reply by button, tap or wake word.
- **Software AEC** (V1b), by design only needed if bring-up shows a board's own AEC does not work.
- Pausing a timer from the display (only voice pauses, because Home Assistant owns those timers and has no message to hear about a local pause).
- A mute indicator on screen (the state reaches the UI as `voiceMuted`; no QML draws it), the optional LED colours, and the Lite's USR button.
- V8, the side-by-side with a real VPE.


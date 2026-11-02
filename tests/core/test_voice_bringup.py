import numpy as np

from havenos.core.voice import bringup


def sine(rate, secs, hz, amp):
    t = np.arange(int(rate * secs)) / rate
    return (np.sin(2 * np.pi * hz * t) * amp * 32767).astype(np.int16)


def test_tone_level_ignores_other_frequencies():
    rate = 16000
    mixed = sine(rate, 1, 880, 0.1) + sine(rate, 1, 300, 0.4)
    assert abs(bringup.tone_dbfs_at(mixed, rate) - bringup.dbfs(sine(rate, 1, 880, 0.1) * 1.414)) < 1.5      # -20 dBFS tone
    assert bringup.tone_dbfs_at(sine(rate, 1, 300, 0.4), rate) < -60
    assert bringup.tone_dbfs_at(np.zeros(0, dtype=np.int16), rate) == -120.0


def test_verdicts_follow_the_measured_echo_return_loss():
    played = -10.5
    assert "WORKING" in bringup.verdict(played, -80, -78)          # the tone is at the noise floor
    assert "PARTLY" in bringup.verdict(played, -80, -40)           # about 30 dB down
    assert "NOT working" in bringup.verdict(played, -80, -20)      # only 10 dB down

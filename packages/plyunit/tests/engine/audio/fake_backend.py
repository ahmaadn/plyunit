from __future__ import annotations


class FakeBackend:
    def __init__(self) -> None:
        self.ready = False
        self.master = 1.0
        self.sounds: dict[str, object] = {}
        self.music: dict[str, object] = {}
        self.playing_voices: dict[int, dict] = {}
        self.music_playing: dict[object, bool] = {}
        self.music_volume: dict[object, float] = {}
        self.music_loop: dict[object, bool] = {}
        self.updated: list[object] = []
        self._voice_seq = 0
        self.init_calls = 0
        self.close_calls = 0

    def init_device(self) -> None:
        self.init_calls += 1
        self.ready = True

    def close_device(self) -> None:
        self.close_calls += 1
        self.ready = False

    def is_device_ready(self) -> bool:
        return self.ready

    def set_master_volume(self, volume: float) -> None:
        self.master = volume

    def load_sound(self, path: str) -> object:
        raw = object()
        self.sounds[path] = raw
        return raw

    def unload_sound(self, raw: object) -> None:
        pass

    def play_sound(
        self, raw: object, volume: float, pitch: float, pan: float
    ) -> object:
        self._voice_seq += 1
        vid = self._voice_seq
        self.playing_voices[vid] = {
            "raw": raw,
            "volume": volume,
            "pitch": pitch,
            "pan": pan,
            "playing": True,
        }
        return vid

    def stop_voice(self, voice_raw: object) -> None:
        # pyrefly: ignore [bad-argument-type]
        rec = self.playing_voices.get(voice_raw)
        if rec is not None:
            rec["playing"] = False

    def is_voice_playing(self, voice_raw: object) -> bool:
        # pyrefly: ignore [bad-argument-type]
        rec = self.playing_voices.get(voice_raw)
        return bool(rec and rec["playing"])

    def set_voice_volume(self, voice_raw: object, volume: float) -> None:
        if voice_raw in self.playing_voices:
            self.playing_voices[voice_raw]["volume"] = volume

    def set_voice_pitch(self, voice_raw: object, pitch: float) -> None:
        if voice_raw in self.playing_voices:
            self.playing_voices[voice_raw]["pitch"] = pitch

    def set_voice_pan(self, voice_raw: object, pan: float) -> None:
        if voice_raw in self.playing_voices:
            self.playing_voices[voice_raw]["pan"] = pan

    def load_music_stream(self, path: str) -> object:
        raw = object()
        self.music[path] = raw
        return raw

    def unload_music_stream(self, raw: object) -> None:
        pass

    def play_music_stream(self, raw: object) -> None:
        self.music_playing[raw] = True

    def stop_music_stream(self, raw: object) -> None:
        self.music_playing[raw] = False

    def pause_music_stream(self, raw: object) -> None:
        self.music_playing[raw] = False

    def resume_music_stream(self, raw: object) -> None:
        self.music_playing[raw] = True

    def update_music_stream(self, raw: object) -> None:
        self.updated.append(raw)

    def is_music_stream_playing(self, raw: object) -> bool:
        return bool(self.music_playing.get(raw, False))

    def set_music_volume(self, raw: object, volume: float) -> None:
        self.music_volume[raw] = volume

    def set_music_looping(self, raw: object, loop: bool) -> None:
        self.music_loop[raw] = loop

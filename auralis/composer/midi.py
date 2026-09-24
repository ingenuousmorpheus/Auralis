"""Standard MIDI File writer/reader for arrangements (no third-party dependency).

Writes a type-1 file: a tempo/meter track, then one track per part with a
name and General-MIDI program. Drums use channel 10. The reader is small and
exists so tests (and later phases) can check what was written.
"""
from __future__ import annotations

import struct

PPQ = 480
# part → (channel, GM program, track name)
PARTS = {
    "keys": (0, 4, "Keys (electric piano)"),
    "pad": (1, 89, "Pad"),
    "bass": (2, 38, "Bass"),
    "drums": (9, 0, "Drums"),
    "fx": (3, 99, "FX"),
    "melody": (4, 53, "Melody guide (not in the instrumental)"),
}


def _vlq(n: int) -> bytes:
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    return bytes(reversed(out))


def _track(events: list[tuple[int, bytes]]) -> bytes:
    # at one tick: meta, then program change, then note-offs, then note-ons
    order = {0xF0: 0, 0xC0: 1, 0x80: 2, 0x90: 3}
    events.sort(key=lambda e: (e[0], order.get(e[1][0] & 0xF0, 4)))
    data, now = bytearray(), 0
    for tick, msg in events:
        data += _vlq(max(0, tick - now)) + msg
        now = max(now, tick)
    data += b"\x00\xff\x2f\x00"
    return b"MTrk" + struct.pack(">I", len(data)) + bytes(data)


def write_midi(arrangement: dict, path: str) -> dict:
    tempo_us = int(round(60_000_000 / arrangement["tempo"]))
    meta = [(0, b"\xff\x51\x03" + tempo_us.to_bytes(3, "big")),
            (0, b"\xff\x58\x04\x04\x02\x18\x08"),
            (0, b"\xff\x03" + _vlq(len(b"Auralis blueprint")) + b"Auralis blueprint")]
    chunks = [_track(meta)]
    counts = {}
    for part, notes in arrangement["tracks"].items():
        if part not in PARTS or not notes:
            continue
        ch, program, name = PARTS[part]
        nb = name.encode("utf-8")
        ev = [(0, b"\xff\x03" + _vlq(len(nb)) + nb)]
        if ch != 9:
            ev.append((0, bytes([0xC0 | ch, program])))
        for start, length, pitch, vel in notes:
            on = int(round(start * PPQ))
            off = max(on + 1, int(round((start + length) * PPQ)))
            p = max(0, min(127, int(pitch)))
            ev.append((on, bytes([0x90 | ch, p, max(1, min(127, int(vel)))])))
            ev.append((off, bytes([0x80 | ch, p, 0])))
        chunks.append(_track(ev))
        counts[part] = len(notes)
    header = b"MThd" + struct.pack(">IHHH", 6, 1, len(chunks), PPQ)
    with open(path, "wb") as f:
        f.write(header + b"".join(chunks))
    return counts


def read_midi(path: str) -> dict:
    """Minimal reader: tempo, and per track its name and notes (start/length in beats)."""
    data = open(path, "rb").read()
    assert data[:4] == b"MThd"
    _, fmt, ntracks, ppq = struct.unpack(">IHHH", data[4:14])
    pos, tempo, tracks = 14, None, []
    for _ in range(ntracks):
        assert data[pos:pos + 4] == b"MTrk"
        length = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        body, pos = data[pos + 8:pos + 8 + length], pos + 8 + length
        i, tick, name, open_notes, notes, status = 0, 0, "", {}, [], 0
        while i < len(body):
            delta = 0
            while True:
                b = body[i]; i += 1
                delta = (delta << 7) | (b & 0x7F)
                if not b & 0x80:
                    break
            tick += delta
            if body[i] == 0xFF:
                kind = body[i + 1]; i += 2
                ln = 0
                while True:
                    b = body[i]; i += 1
                    ln = (ln << 7) | (b & 0x7F)
                    if not b & 0x80:
                        break
                payload = body[i:i + ln]; i += ln
                if kind == 0x51:
                    tempo = 60_000_000 / int.from_bytes(payload, "big")
                elif kind == 0x03:
                    name = payload.decode("utf-8", "replace")
                continue
            if body[i] & 0x80:
                status = body[i]; i += 1
            hi = status & 0xF0
            if hi in (0xC0, 0xD0):
                i += 1
                continue
            a, b2 = body[i], body[i + 1]; i += 2
            if hi == 0x90 and b2 > 0:
                open_notes.setdefault(a, []).append((tick, b2))
            elif hi in (0x80, 0x90) and open_notes.get(a):
                start, vel = open_notes[a].pop(0)
                notes.append((start / ppq, (tick - start) / ppq, a, vel))
        tracks.append({"name": name, "notes": sorted(notes)})
    return {"format": fmt, "ppq": ppq, "tempo": tempo, "tracks": tracks}

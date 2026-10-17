"""Passive plugin catalog. Never imports or instantiates a plugin binary.

VST2 DLLs remain candidates: a filename/PE header cannot prove a VST entrypoint.
VST3 moduleinfo provides individual classes, including shell/container products.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import struct
from pathlib import Path

CATEGORIES = ['Pitch correction', 'Vocal alignment', 'Equalization', 'Compression',
              'De-essing', 'Saturation', 'Reverb', 'Delay', 'Noise reduction',
              'Limiting', 'Stereo processing', 'Vocal effects', 'Instruments', 'Unknown']
# Exact product families; vendor alone never implies a capability.
RULES = [
    (r'^(?:auto-tune )?vocal reverb$', 'Reverb', 'Adds vocal ambience.'),
    (r'^auto-tune vocal compressor$', 'Compression', 'Controls vocal dynamics.'),
    (r'^auto-tune vocal eq$|^fabfilter pro-q 2', 'Equalization', 'Shapes frequency balance.'),
    (r'^auto-tune soundsoap$', 'Noise reduction', 'Reduces background noise.'),
    (r'^auto-tune (?:vocodist|slice)$', 'Vocal effects', 'Adds creative vocal effects.'),
    (r'^tube-tech cl 1b$', 'Compression', 'Controls dynamics with optical-style compression.'),
    (r'^auto[ -]?tune(?: (?:access|artist|pro|efx\+?|evo))?(?: \d[\w .-]*)?$', 'Pitch correction', 'Corrects vocal pitch.'),
    (r'^vocalign(?:[ -]?(?:pro|project|standard))?(?:[ p0-9.-]*)$', 'Vocal alignment', 'Aligns vocal takes in time; edition and host support require checking.'),
    (r'echoboy(?:\b|_)', 'Delay', 'Adds rhythmic echoes.'),
    (r'decapitator(?:\b|_)', 'Saturation', 'Adds harmonic distortion and colour.'),
    (r'little plate(?:\b|_)', 'Reverb', 'Adds plate-style ambience.'),
    (r'\bde[ -]?esser\b|\bsibilance\b', 'De-essing', 'Reduces sharp vocal sibilance.'),
    (r'\brvox\b|\brenaissance vox\b|\bcla[ -]?(?:2a|3a|76)\b', 'Compression', 'Controls vocal dynamics.'),
]
SUBCATEGORIES = {'EQ': 'Equalization', 'Reverb': 'Reverb',
                 'Delay': 'Delay', 'Distortion': 'Saturation', 'Instrument': 'Instruments',
                 'Spatial': 'Stereo processing', 'Pitch Shift': 'Vocal effects'}
# Dynamics alone does not distinguish compressor/limiter: leave it unknown.
PURPOSES = {'Equalization': 'Shapes frequency balance.', 'Compression': 'Controls level changes.',
            'De-essing': 'Reduces sibilance.', 'Pitch correction': 'Corrects vocal pitch.',
            'Vocal alignment': 'Tightens timing between takes.', 'Saturation': 'Adds harmonic colour.',
            'Reverb': 'Adds space.', 'Delay': 'Adds echoes.', 'Noise reduction': 'Reduces unwanted noise.',
            'Limiting': 'Controls peaks.', 'Stereo processing': 'Shapes stereo width.',
            'Vocal effects': 'Adds creative vocal colour.', 'Instruments': 'Generates musical sound.'}
TEMPLATES = {
    'Clean natural lead': ['Noise reduction', 'Pitch correction', 'Equalization', 'Compression', 'De-essing', 'Reverb'],
    'Modern pop/R&B lead': ['Pitch correction', 'Equalization', 'Compression', 'De-essing', 'Saturation', 'Delay', 'Reverb'],
    'Doubles and harmonies': ['Vocal alignment', 'Pitch correction', 'Equalization', 'Compression', 'Stereo processing'],
    'Smooth melodic vocal': ['Pitch correction', 'Equalization', 'Compression', 'De-essing', 'Reverb', 'Delay'],
    'Creative atmospheric vocal': ['Pitch correction', 'Vocal effects', 'Saturation', 'Delay', 'Reverb', 'Stereo processing'],
}


def standard_roots():
    roots = []
    for base in dict.fromkeys(filter(None, [os.environ.get('ProgramW6432'), os.environ.get('ProgramFiles'), os.environ.get('ProgramFiles(x86)')])):
        roots.extend(Path(base) / p for p in ['Common Files/VST3', 'Common Files/VST2', 'VstPlugins', 'Steinberg/VstPlugins'])
    if os.environ.get('LOCALAPPDATA'):
        roots.append(Path(os.environ['LOCALAPPDATA']) / 'Programs/Common/VST3')
    return roots


def linked(path):
    """Reject Windows junctions/reparse points as well as symbolic links."""
    return path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0) & 0x400)


def architecture(path):
    try:
        with path.open('rb') as stream:
            if stream.read(2) != b'MZ':
                return 'Unknown'
            stream.seek(60)
            offset = struct.unpack('<I', stream.read(4))[0]
            if offset > 16 * 1024 * 1024:
                return 'Unknown'
            stream.seek(offset)
            if stream.read(4) != b'PE\0\0':
                return 'Unknown'
            return {0x8664: 'x64', 0x14c: 'x86', 0xaa64: 'ARM64'}.get(struct.unpack('<H', stream.read(2))[0], 'Unknown')
    except (OSError, ValueError, struct.error):
        return 'Unknown'


def clean(value, fallback='Unknown'):
    # Do not echo arbitrary metadata (paths, activation fields, multiline content).
    if not isinstance(value, str) or not re.fullmatch(r'[\w .+()&®™-]{1,120}', value):
        return fallback
    return value


def version_metadata(path):
    """Windows version-resource API reads data only, never LoadLibrary on a plugin."""
    if os.name != 'nt' or not path.is_file():
        return {}
    import ctypes
    from ctypes import wintypes
    api = ctypes.WinDLL('version', use_last_error=True, winmode=0x800)  # System32 only
    api.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    api.GetFileVersionInfoSizeW.restype = wintypes.DWORD
    api.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    api.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT)]
    size = api.GetFileVersionInfoSizeW(str(path), None)
    if not 0 < size <= 1024 * 1024:
        return {}
    data = ctypes.create_string_buffer(size)
    if not api.GetFileVersionInfoW(str(path), 0, size, data):
        return {}
    pointer, length = ctypes.c_void_p(), wintypes.UINT()
    if not api.VerQueryValueW(data, r'\VarFileInfo\Translation', ctypes.byref(pointer), ctypes.byref(length)) or length.value < 4:
        return {}
    language, codepage = struct.unpack('<HH', ctypes.string_at(pointer, 4))
    result = {}
    for field in ['CompanyName', 'FileVersion']:
        key = f'\\StringFileInfo\\{language:04x}{codepage:04x}\\{field}'
        if api.VerQueryValueW(data, key, ctypes.byref(pointer), ctypes.byref(length)) and 0 < length.value <= 121:
            value = clean(ctypes.wstring_at(pointer, length.value).rstrip('\0'))
            if value != 'Unknown':
                result[field] = value
    return result


def classify(name, subcategories=''):
    categories, evidence, descriptions = [], [], []
    for pattern, category, description in RULES:
        if re.search(pattern, name, re.I):
            categories.append(category)
            descriptions.append(description)
            evidence.append('Product-name rule: ' + pattern)
    tokens = subcategories.split('|') if isinstance(subcategories, str) else subcategories if isinstance(subcategories, list) else []
    for token in tokens:
        if not isinstance(token, str):
            continue
        if token in SUBCATEGORIES:
            category = SUBCATEGORIES[token]
            categories.append(category)
            evidence.append('VST3 declared category: ' + token)
    categories = list(dict.fromkeys(categories))
    return categories or ['Unknown'], evidence, ' '.join(descriptions) or (' '.join(PURPOSES[c] for c in categories) if categories else 'Purpose unknown; manual identification needed.')


def inspect_plugin(path):
    fmt = 'VST3' if path.suffix.lower() == '.vst3' else 'VST2 candidate'
    binary, classes, vendor, version, status = path, [], 'Unknown', 'Unknown', 'unverified candidate'
    if path.is_dir():
        binary = path / 'Contents/x86_64-win' / path.name
        metadata = path / 'Contents/Resources/moduleinfo.json'
        if not metadata.exists():
            metadata = path / 'Contents/moduleinfo.json'
        try:
            # Every ancestor is checked; a bundle cannot redirect metadata reads.
            if any(linked(p) for p in [metadata.parent.parent, metadata.parent, metadata]):
                raise ValueError()
            if metadata.stat().st_size > 1024 * 1024:
                raise ValueError()
            info = json.loads(metadata.read_text(encoding='utf-8'))
            vendor = clean(info.get('Factory Info', {}).get('Vendor'))
            version = clean(info.get('Version'))
            classes = [c for c in info.get('Classes', []) if isinstance(c, dict) and c.get('Category') == 'Audio Module Class']
            status = 'metadata declared' if classes else 'unverified candidate'
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError, AttributeError):
            status = 'invalid metadata'
        # Never follow a linked binary or ancestor.
        if any(p.exists() and linked(p) for p in [binary.parent, binary.parent.parent, binary]):
            binary = None
    arch = architecture(binary) if binary else 'Unknown'
    if fmt == 'VST3' and status == 'unverified candidate' and arch != 'Unknown':
        status = 'VST3 file candidate'
    resources = version_metadata(binary) if binary else {}
    vendor = resources.get('CompanyName', vendor) if vendor == 'Unknown' else vendor
    version = resources.get('FileVersion', version) if version == 'Unknown' else version
    records = []
    for item in classes or [{}]:
        name = clean(item.get('Name'), clean(path.stem))
        categories, evidence, description = classify(name, item.get('Sub Categories', []))
        cid = item.get('CID', '')
        cid = cid.upper() if isinstance(cid, str) and re.fullmatch('[0-9a-fA-F]{32}', cid) else ''
        records.append(dict(id=hashlib.sha256((str(path) + cid + name).encode()).hexdigest()[:20], name=name,
            manufacturer=clean(item.get('Vendor'), vendor), version=clean(item.get('Version'), version), format=fmt, path=str(path),
            categories=categories, classification_evidence=evidence, description=description,
            architecture=arch, discovery_status=status, class_id=cid,
            compatibility=('Unknown — x86 bridge/host support must be verified' if arch == 'x86' else 'Unknown — not tested in Mixcraft'), duplicate_ids=[]))
    return records


def scan(roots=None, max_entries=20000):
    """Only plugin roots supplied by the owner or the fixed standard list.

    No registry, subprocesses, DLL loading, logs, or persistent inventory writes.
    """
    plugins, locations, seen, visited = [], [], set(), 0
    for index, raw in enumerate(standard_roots() if roots is None else roots):
        root = Path(raw)
        location = {'root_index': index, 'status': 'complete'}
        locations.append(location)
        try:
            if not root.is_absolute() or root == Path(root.anchor) or str(root).startswith('\\\\'):
                location['status'] = 'rejected root'; continue
            root = Path(os.path.abspath(root))
            protected = [Path(v) for v in [os.environ.get('USERPROFILE'), os.environ.get('WINDIR'), os.environ.get('ProgramFiles'), os.environ.get('ProgramFiles(x86)')] if v]
            if any(root == p or root in p.parents for p in protected) or root.name.casefold() in {'documents', 'desktop', 'downloads', 'pictures', 'videos', 'music', 'appdata', 'users'}:
                location['status'] = 'rejected broad or private root'; continue
            if not root.exists():
                location['status'] = 'missing'; continue
            if any(linked(p) for p in [root, *root.parents]) or not root.is_dir():
                location['status'] = 'rejected root'; continue
            pending = [root]
            while pending:
                directory = pending.pop()
                with os.scandir(directory) as entries:
                    for entry in entries:
                        visited += 1
                        if visited > max_entries:
                            location['status'] = 'entry limit'; break
                        path = Path(entry.path)
                        if linked(path):
                            continue
                        key = str(path).casefold()
                        if key in seen:
                            continue
                        seen.add(key)
                        if path.suffix.lower() in {'.vst3', '.dll'}:
                            if path.is_file() or path.suffix.lower() == '.vst3':
                                plugins.extend(inspect_plugin(path))
                        elif entry.is_dir(follow_symlinks=False):
                            pending.append(path)
                if visited > max_entries:
                    break
        except (OSError, ValueError):
            location['status'] = 'unreadable'
    groups = {}
    for p in plugins:
        # Name-based grouping is only a possible duplicate, never proof of identity.
        key = p['class_id'] or (p['manufacturer'].casefold(), p['name'].casefold())
        groups.setdefault(str(key), []).append(p)
    for group in groups.values():
        for p in group:
            p['duplicate_ids'] = [q['id'] for q in group if q is not p]
    return {'plugins': plugins, 'locations': locations, 'categories': CATEGORIES, 'templates': list(TEMPLATES),
            'notice': 'Passive inventory; DLLs are candidates. Compatibility and licensing are unverified. Duplicate groups are possible matches.'}


def search(catalog, query='', category=''):
    return [p for p in catalog['plugins'] if (not category or category in p['categories']) and
            query.casefold() in ' '.join([p['name'], p['manufacturer'], p['description'], *p['categories']]).casefold()]


def recommend(catalog, template):
    if template not in TEMPLATES:
        raise ValueError('Unknown chain template')
    steps = []
    for category in TEMPLATES[template]:
        matches = [p for p in catalog['plugins'] if category in p['categories'] and
                   p['discovery_status'] in {'metadata declared', 'VST3 file candidate'} and p['architecture'] == 'x64']
        matches.sort(key=lambda p: (p['name'].casefold(), p['id']))
        steps.append({'category': category, 'plugin_id': matches[0]['id'] if matches else None,
                      'plugin_name': matches[0]['name'] if matches else None,
                      'reason': PURPOSES[category], 'status': 'Candidate — verify in Mixcraft' if matches else 'Unavailable or unverified'})
    return {'template': template, 'steps': steps, 'notice': 'Planning only; no audio processed. Use reverb/delay on sends when appropriate. Apply cleanup only when needed; audition against bypass.'}

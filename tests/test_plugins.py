import json
import struct
from pathlib import Path

import pytest
from auralis.plugins import architecture, classify, inspect_plugin, recommend, scan, search, TEMPLATES


def pe(path, machine=0x8664):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = bytearray(72)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 60, 64)
    data[64:68] = b'PE\0\0'
    struct.pack_into('<H', data, 68, machine)
    path.write_bytes(data)
    return path


def bundle(root, name='Example', cid='A' * 32, sub='Fx|EQ', machine=0x8664):
    path = root / (name + '.vst3')
    pe(path / 'Contents/x86_64-win' / path.name, machine)
    meta = path / 'Contents/Resources/moduleinfo.json'
    meta.parent.mkdir(parents=True)
    meta.write_text(json.dumps({'Factory Info': {'Vendor': 'Example Audio'}, 'Version': '1.2',
        'Classes': [{'Name': name, 'CID': cid, 'Category': 'Audio Module Class', 'Sub Categories': sub.split('|')}]}))
    return path


def test_duplicates_overlap_and_formats(tmp_path):
    bundle(tmp_path / 'a')
    bundle(tmp_path / 'b')
    pe(tmp_path / 'Example.dll')
    result = scan([tmp_path, tmp_path / 'a'])
    assert len(result['plugins']) == 3
    declared = [p for p in result['plugins'] if p['class_id']]
    assert all(len(p['duplicate_ids']) == 1 for p in declared)
    assert {p['format'] for p in result['plugins']} == {'VST3', 'VST2 candidate'}


def test_missing_unknown_and_bad_pe(tmp_path):
    (tmp_path / 'Mystery.dll').write_bytes(b'not code')
    (tmp_path / 'private.txt').write_text('SECRET-LICENSE')
    result = scan([tmp_path, tmp_path / 'absent'])
    assert result['locations'][1]['status'] == 'missing'
    assert result['plugins'][0]['categories'] == ['Unknown']
    assert result['plugins'][0]['architecture'] == 'Unknown'
    assert 'SECRET-LICENSE' not in json.dumps(result)
    assert not any(s['plugin_id'] for s in recommend(result, 'Clean natural lead')['steps'])


@pytest.mark.parametrize('metadata', ['{', '[]', '{"Factory Info": []}', '{"Classes": null}'])
def test_invalid_metadata(tmp_path, metadata):
    path = bundle(tmp_path)
    (path / 'Contents/Resources/moduleinfo.json').write_text(metadata)
    assert inspect_plugin(path)[0]['discovery_status'] == 'invalid metadata'


@pytest.mark.parametrize('name,expected', [
    ('Auto-Tune Pro', 'Pitch correction'), ('Auto-Tune Vocal EQ', 'Equalization'),
    ('Auto-Tune Vocal Compressor', 'Compression'), ('Auto-Tune SoundSoap', 'Noise reduction'),
    ('Auto-Key', 'Unknown'), ('VocALignPro', 'Vocal alignment'), ('EchoBoy', 'Delay'),
    ('Unknown Waves Product', 'Unknown'), ('Unknown Soundtoys Product', 'Unknown')])
def test_rules(name, expected):
    categories, evidence, _ = classify(name)
    assert categories == [expected]
    assert bool(evidence) == (expected != 'Unknown')


def test_multi_category_and_search(tmp_path):
    bundle(tmp_path, sub='Fx|EQ|Reverb')
    result = scan([tmp_path])
    assert result['plugins'][0]['categories'] == ['Equalization', 'Reverb']
    assert search(result, 'example audio', 'Reverb')
    assert not search(result, 'nonexistent')


def test_recommendations_are_inventory_only(tmp_path):
    bundle(tmp_path, sub='Fx|EQ')
    pe(tmp_path / 'Auto-Tune Pro.vst3')
    pe(tmp_path / 'Decapitator.dll')  # unverified VST2 is never recommended
    result = scan([tmp_path])
    for template in TEMPLATES:
        chain = recommend(result, template)
        assert all(s['plugin_id'] in {p['id'] for p in result['plugins']} for s in chain['steps'] if s['plugin_id'])
    steps = recommend(result, 'Modern pop/R&B lead')['steps']
    assert steps[0]['plugin_name'] == 'Auto-Tune Pro'
    assert next(s for s in steps if s['category'] == 'Saturation')['plugin_id'] is None
    with pytest.raises(ValueError):
        recommend(result, 'invented')


def test_read_only_no_execution_or_logs(tmp_path, monkeypatch, capsys, caplog):
    import ctypes
    import subprocess
    bundle(tmp_path)
    pe(tmp_path / 'Auto-Tune Access.vst3')
    before = {str(p): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    def forbidden(*args, **kwargs):
        raise AssertionError('Execution attempted')
    monkeypatch.setattr(ctypes, 'CDLL', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr('auralis.plugins.version_metadata', lambda p: {})
    scan([tmp_path])
    assert before == {str(p): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    assert capsys.readouterr().out == ''
    assert caplog.text == ''


def test_reparse_points_are_skipped(tmp_path, monkeypatch):
    import auralis.plugins as module
    bundle(tmp_path / 'redirect')
    original = module.linked
    monkeypatch.setattr(module, 'linked', lambda p: p.name == 'redirect' or original(p))
    assert scan([tmp_path])['plugins'] == []


def test_entry_limit_and_architecture(tmp_path):
    pe(tmp_path / 'a.dll', 0x14c)
    assert architecture(tmp_path / 'a.dll') == 'x86'
    assert scan([tmp_path], max_entries=0)['locations'][0]['status'] == 'entry limit'
    assert scan([Path(tmp_path.anchor)])['locations'][0]['status'] == 'rejected root'


def test_api(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import auralis.api.plugins as api
    bundle(tmp_path)
    monkeypatch.setattr('auralis.plugins.standard_roots', lambda: [])
    monkeypatch.setattr(api, '_catalog', {'plugins': [], 'locations': []})
    app = FastAPI()
    app.include_router(api.router)
    client = TestClient(app)
    assert client.post('/plugins/scan', json={'paths': [str(tmp_path)]}).status_code == 200
    assert len(client.get('/plugins?category=Equalization').json()['plugins']) == 1
    assert client.get('/plugins/chains', params={'template': 'Modern pop/R&B lead'}).status_code == 200
    assert client.get('/plugins/chains?template=bad').status_code == 422
    assert client.post('/plugins/scan', json={'paths': ['x'] * 25}).status_code == 422

def test_private_roots_rejected(tmp_path):
    private = tmp_path / 'Documents'
    pe(private / 'pretend.dll')
    result = scan([private])
    assert result['plugins'] == []
    assert result['locations'][0]['status'] == 'rejected broad or private root'


def test_sensitive_metadata_not_returned(tmp_path):
    path = bundle(tmp_path)
    meta = path / 'Contents/Resources/moduleinfo.json'
    info = json.loads(meta.read_text())
    info['LicenseKey'] = 'SECRET-ACTIVATION'
    info['Factory Info']['Vendor'] = 'C:\\private\\license.txt'
    meta.write_text(json.dumps(info))
    result = scan([tmp_path])
    assert result['plugins'][0]['manufacturer'] == 'Unknown'
    assert 'SECRET-ACTIVATION' not in json.dumps(result)
    assert 'license.txt' not in json.dumps(result)


def test_bundle_binary_reparse_not_read(tmp_path, monkeypatch):
    import auralis.plugins as module
    path = bundle(tmp_path)
    original = module.linked
    monkeypatch.setattr(module, 'linked', lambda p: p.name == 'x86_64-win' or original(p))
    assert inspect_plugin(path)[0]['architecture'] == 'Unknown'


def test_legacy_moduleinfo_location(tmp_path):
    path = bundle(tmp_path)
    (path / 'Contents/Resources/moduleinfo.json').rename(path / 'Contents/moduleinfo.json')
    assert inspect_plugin(path)[0]['categories'] == ['Equalization']


def test_multiple_classes_and_invalid_subcategory(tmp_path):
    path = bundle(tmp_path)
    meta = path / 'Contents/Resources/moduleinfo.json'
    info = json.loads(meta.read_text())
    info['Classes'].append({'Name': 'Synth', 'CID': 'B' * 32, 'Category': 'Audio Module Class', 'Sub Categories': ['Instrument', None, {}]})
    meta.write_text(json.dumps(info))
    records = scan([tmp_path])['plugins']
    assert len(records) == 2
    assert records[1]['categories'] == ['Instruments']
    assert records[0]['id'] != records[1]['id']


def test_normalized_private_root(tmp_path):
    private = tmp_path / 'Documents'
    private.mkdir()
    assert scan([private / '..' / 'Documents'])['locations'][0]['status'] == 'rejected broad or private root'

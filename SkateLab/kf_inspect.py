"""Read-only KF/BSA inspection for local mod development."""
from pathlib import Path
import sys, time, inspect, struct, zlib, io, json
sys.path.insert(0, str(Path(__file__).parent / 'vendor/python'))
time.clock = time.perf_counter
inspect.getargspec = inspect.getfullargspec
from pyffi.formats.nif import NifFormat as N

ROOT = Path(__file__).resolve().parents[1]

def bsa_files(path):
    with path.open('rb') as f:
        magic, version, offset, flags, folders, files, folder_bytes, file_bytes, file_flags = struct.unpack('<4s8I', f.read(36))
        assert magic == b'BSA\0' and version == 104
        f.seek(offset)
        folder_records = [struct.unpack('<QII', f.read(16)) for _ in range(folders)]
        entries = []
        for _, count, _ in folder_records:
            length = f.read(1)[0]
            folder_name = f.read(length).rstrip(b'\0').decode('cp1252')
            for _ in range(count):
                _, size, position = struct.unpack('<QII', f.read(16))
                entries.append((folder_name, size, position))
        names = f.read(file_bytes).split(b'\0')
        assert len(entries) == files
        for entry, name in zip(entries, names):
            yield entry[0] + '\\' + name.decode('cp1252'), entry[1], entry[2], flags

def bsa_read(path, name):
    item = next(x for x in bsa_files(path) if x[0].lower() == name.lower())
    _, size, offset, flags = item
    compressed = bool(flags & 4) ^ bool(size & 0x40000000)
    size &= 0x3fffffff
    with path.open('rb') as f:
        f.seek(offset)
        payload = f.read(size)
    if flags & 0x100:
        payload = payload[payload[0] + 1:]
    if compressed:
        length, = struct.unpack('<I', payload[:4])
        payload = zlib.decompress(payload[4:])
        assert len(payload) == length
    return payload

def vec(v):
    return [round(v.x, 5), round(v.y, 5), round(v.z, 5)]

def quat(q):
    return [round(q.w, 5), round(q.x, 5), round(q.y, 5), round(q.z, 5)]

def inspect_kf(payload, label):
    data = N.Data()
    data.read(io.BytesIO(payload))
    seq = data.roots[0]
    output = {'path': label, 'name': str(seq.name), 'start': seq.start_time, 'stop': seq.stop_time,
              'cycle': seq.cycle_type, 'frequency': seq.frequency, 'target': str(seq.target_name),
              'version': [data.version, data.user_version, data.user_version_2],
              'keys': [(k.time, str(k.value)) for k in seq.text_keys.text_keys], 'bones': []}
    for controlled in seq.controlled_blocks:
        i = controlled.interpolator
        bone = {'node': str(controlled.node_name), 'controller': str(controlled.controller_type),
                'priority': controlled.priority, 'interp': type(i).__name__}
        if isinstance(i, N.NiTransformInterpolator):
            bone.update(translation=vec(i.translation), rotation=quat(i.rotation), scale=i.scale)
            if i.data:
                d = i.data
                bone.update(rotation_type=d.rotation_type, rotations=d.num_rotation_keys,
                            translations=d.translations.num_keys,
                            translation_keys=[(k.time, vec(k.value)) for k in d.translations.keys][:1] + [(k.time, vec(k.value)) for k in d.translations.keys][-1:])
                if d.rotation_type != 4:
                    bone['rotation_keys'] = [(k.time, quat(k.value)) for k in d.quaternion_keys][:3]
        elif isinstance(i, N.NiBSplineTransformInterpolator):
            translations = list(i.get_translations())
            rotations = list(i.get_rotations())
            bone.update(translation_control_points=translations[:1] + translations[-1:],
                        rotation_control_points=rotations[:1] + rotations[-1:])
        if '--root-only' not in sys.argv or controlled.node_name in (b'Bip01', b'Bip01 NonAccum'):
            output['bones'].append(bone)
    print(json.dumps(output, indent=2))

if __name__ == '__main__':
    for name in sys.argv[1:]:
        if name.startswith('--'):
            continue
        if name.startswith('bsa:'):
            inner = name[4:]
            inspect_kf(bsa_read(ROOT / 'Data/Fallout - Meshes.bsa', inner), name)
        else:
            inspect_kf(Path(name).read_bytes(), name)

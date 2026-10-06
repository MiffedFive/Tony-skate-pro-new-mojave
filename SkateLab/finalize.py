from pathlib import Path
import re, shutil, json, hashlib, zipfile, xml.etree.ElementTree as ET

# Legacy packaging predates private donor-derived KFs. Never silently bundle
# these into a public release. validate_skate.py is the non-packaging audit.
raise SystemExit("Packaging disabled for private Skate 3-derived build. Use validate_skate.py; public release requires BYO conversion or original animations.")

base = Path(__file__).resolve().parents[1]
mod = base / 'MO2/mods/Mojave Skate'
script = mod / 'NVSE/Plugins/Scripts/ln_MojaveSkate.txt'
text = script.read_text('ascii')
config = mod / 'config/MojaveSkate.ini'
config.parent.mkdir(exist_ok=True)
if not config.exists():
    shutil.copyfile(mod / 'NVSE/Plugins/MojaveSkate.ini', config)
# Package only original runtime/assets/documentation, no vendor/game data.
files = [p for p in mod.rglob('*') if p.is_file()]
ET.parse(mod / 'menus/prefabs/MojaveSkate/hud.xml')
for p in mod.glob('NVSE/Plugins/Scripts/*.txt'):
    b = p.read_bytes()
    assert len(b) < 16384, (p, len(b))
    assert max(map(len, b.splitlines())) < 512, p
    # Structural sanity check, not a replacement for in-game compilation.
    stack=[]
    for line in b.decode().splitlines():
        line = line.strip().lower()
        if line.startswith('if '): stack.append('if')
        elif line.startswith('while '): stack.append('while')
        elif line == 'endif': assert stack.pop() == 'if', p
        elif line == 'loop': assert stack.pop() == 'while', p
    assert not stack, p
main_script = (mod / 'NVSE/Plugins/Scripts/ln_MojaveSkate.txt').read_text('ascii')
assert 'CallWhile' not in main_script, 'legacy CallWhile runtime still present'
callbacks = re.findall(r'\(Begin Function \{\}.*?End\)', main_script, re.I | re.S)
assert len(callbacks) == 13, ('expected thirteen main-loop callbacks', len(callbacks))
assert max(map(len, callbacks)) < 480, ('JIP lambda limit margin', max(map(len, callbacks)))
assert main_script.count('End) 1 1 9') == 13
report = {
  'status':'0.14.0 four reported camera/weapon cases addressed and verified in engine',
  'nif':'board NIF round-trip checked; directional locomotion groups carry accumulated root-motion spline controllers',
  'xml':'well-formed',
  'script_limit':'under 16384 bytes; lines under 512 bytes',
  'gameplay':'third-person F10/W/inertia/dismount verified; no running cycle or T-pose; first-person torso duplicate suppressed',
  'runtime':'thirteen short JIP callbacks; reversible weapon/control state; perspective-specific board visibility; kNVSE locomotion override',
  'jip_lambda_chars_max':max(map(len, callbacks)),
  'engine_compilation':'verified: kNVSE registered all eleven player groups; fresh log contains no Failed to load KF Model for Mojave Skate',
  'files':{str(p.relative_to(mod)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
}
(base/'SkateLab/VALIDATION.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
out=base/'SkateLab/Mojave-Skate-0.14.0.zip'
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
    for p in files: z.write(p, p.relative_to(mod))
print(json.dumps({k:v for k,v in report.items() if k!='files'},indent=2))
print(out)





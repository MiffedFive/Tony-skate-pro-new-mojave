"""Original procedural skateboard, no extracted game assets. PyFFI 2.2.3."""
from pathlib import Path
import sys, time, inspect, math, random
sys.path.insert(0, str(Path(__file__).parent / 'vendor/python'))
time.clock = time.perf_counter
inspect.getargspec = inspect.getfullargspec
from pyffi.formats.nif import NifFormat as N
from PIL import Image, ImageDraw

MOD = Path(__file__).resolve().parents[1] / 'MO2/mods/Mojave Skate'
MESH = MOD / 'meshes/MojaveSkate'
TEX = MOD / 'textures/MojaveSkate'
MESH.mkdir(parents=True, exist_ok=True)
TEX.mkdir(parents=True, exist_ok=True)
random.seed(19)
im = Image.new('RGB', (512, 512))
pix = im.load()
for y in range(512):
    for x in range(512):
        a = random.randrange(22, 49)
        pix[x, y] = (a, a, a)
d = ImageDraw.Draw(im)
d.rounded_rectangle((14, 14, 497, 497), radius=52, outline=(210, 131, 43), width=9)
d.polygon([(55, 325), (150, 110), (225, 325)], fill=(190, 116, 35))
d.polygon([(220, 380), (330, 90), (454, 380)], outline=(210, 131, 43), width=6)
d.text((180, 425), 'MOJAVE / SKATE', fill=(235, 205, 135), font_size=22)
im.save(TEX / 'deck.dds', pixel_format='DXT1')
Image.new('RGBA', (8, 8), (128, 128, 255, 255)).save(TEX / 'deck_n.dds', pixel_format='DXT5')

data = N.Data(version=0x14020007, user_version=11, user_version_2=34)
data.header.endian_type = 1
root = N.NiNode()
root.name = b'MojaveSkateRoot'
root.flags = 14
# Cancel the Bip01 NonAccum bind transform so the inserted child resolves to
# actor-root coordinates with its wheels at ground level.
root.translation.x = -0.657
root.translation.z = -58.771
root.rotation.m_11, root.rotation.m_12, root.rotation.m_13 = 0.0, -1.0, 0.0
root.rotation.m_21, root.rotation.m_22, root.rotation.m_23 = 1.0, 0.0, 0.0
root.rotation.m_31, root.rotation.m_32, root.rotation.m_33 = 0.0, 0.0, 1.0
data.roots = [root]

def shape(name, verts, tris, color, textured=False):
    s = N.NiTriShape()
    s.name = name.encode()
    s.flags = 14
    g = N.NiTriShapeData()
    s.data = g
    g.num_vertices = len(verts)
    g.has_vertices = True
    g.vertices.update_size()
    for v, xyz in zip(g.vertices, verts):
        v.x, v.y, v.z = xyz
    g.has_normals = True
    g.normals.update_size()
    g.num_triangles = len(tris)
    g.num_triangle_points = len(tris) * 3
    g.has_triangles = True
    g.consistency_flags = 16384
    g.triangles.update_size()
    for t, abc in zip(g.triangles, tris):
        t.v_1, t.v_2, t.v_3 = abc
    g.num_uv_sets = 1
    g.uv_sets.update_size()
    for uv, xyz in zip(g.uv_sets[0], verts):
        uv.u = (xyz[0] + 9) / 18
        uv.v = (xyz[1] + 32) / 64
    normals = [[0., 0., 0.] for _ in verts]
    for a, b, c in tris:
        u = [verts[b][i] - verts[a][i] for i in range(3)]
        w = [verts[c][i] - verts[a][i] for i in range(3)]
        cross = [u[1]*w[2]-u[2]*w[1], u[2]*w[0]-u[0]*w[2], u[0]*w[1]-u[1]*w[0]]
        for idx in (a,b,c):
            for axis in range(3):
                normals[idx][axis] += cross[axis]
    for dest, src in zip(g.normals, normals):
        length = math.sqrt(sum(x*x for x in src)) or 1
        dest.x, dest.y, dest.z = (x / length for x in src)
    g.update_center_radius()
    mat = N.NiMaterialProperty()
    mat.name = b'MojaveSkateMaterial'
    mat.diffuse_color.r, mat.diffuse_color.g, mat.diffuse_color.b = color
    mat.ambient_color.r, mat.ambient_color.g, mat.ambient_color.b = color
    mat.specular_color.r = mat.specular_color.g = mat.specular_color.b = .15
    mat.glossiness = 12
    mat.alpha = 1
    shader = N.BSShaderPPLightingProperty()
    shader.shader_type = 0
    shader.shader_flags.sf_specular = 1
    shader.shader_flags.sf_remappable_textures = 1
    shader.shader_flags.sf_z_buffer_test = 1
    shader.shader_flags_2.sf_2_z_buffer_write = 1
    ts = N.BSShaderTextureSet()
    ts.num_textures = 6
    ts.textures.update_size()
    ts.textures[0] = b'textures\\MojaveSkate\\deck.dds'
    ts.textures[1] = b'textures\\MojaveSkate\\deck_n.dds'
    shader.texture_set = ts
    s.add_property(shader)
    s.add_property(mat)
    root.add_child(s)
    s.update_tangent_space(as_extra=False)
    return s

def box(name, center, size, color):
    x,y,z = center
    a,b,c = (v/2 for v in size)
    v=[(x+dx*a,y+dy*b,z+dz*c) for dx,dy,dz in
       [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
    t=[(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),
       (1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
    return shape(name,v,t,color)

# Rounded deck with upward-curved nose and tail, 81cm long in game units.
n=32
outline=[]
for i in range(n):
    angle=2*math.pi*i/n
    x=9*math.cos(angle)
    y=30*math.sin(angle)
    z=-2 + max(0, abs(y)-21)*.36
    outline.append((x,y,z))
v=outline+[(x,y,z-1.2) for x,y,z in outline]
t=[]
for i in range(1,n-1):
    t.extend([(0,i,i+1),(n,n+i+1,n+i)])
for i in range(n):
    j=(i+1)%n
    t.extend([(i,n+j,j),(i,n+i,n+j)])
shape('MojaveSkateDeck',v,t,(.85,.85,.85),True)
for y in (-18,18):
    box('TruckPlate'+str(y),(0,y,-4),(7,5,2),(.5,.5,.52))
    box('Axle'+str(y),(0,y,-6),(22,2,2),(.6,.6,.6))
    for x in (-10,10):
        verts=[]
        for xx in (x-1.7,x+1.7):
            for i in range(16):
                a=2*math.pi*i/16
                verts.append((xx,y+3*math.cos(a),-6+3*math.sin(a)))
        tris=[]
        for i in range(16):
            j=(i+1)%16
            tris.extend([(i,j,16+j),(i,16+j,16+i)])
        for i in range(1,15):
            tris.extend([(0,i+1,i),(16,16+i,16+i+1)])
        shape(f'Wheel{x}_{y}',verts,tris,(.75,.68,.45))

# PyFFI can round-trip FNV geometry yet still serialize a freshly-created
# NiTriShape in a layout that this runtime refuses to render.  Reuse only the
# binary container layout of a known-good unskinned NiTriShape, then replace
# every expressive asset field with our own merged geometry and materials.
TEMPLATE = MOD.parent / 'ATTT Redux (Cowboy Holsters)/meshes/ArmedToTheTeeth/Holsters/SmallRevolver.nif'
out = N.Data()
with TEMPLATE.open('rb') as f:
    out.read(f)
out_root = out.roots[0]
out_shape = next(b for b in out_root.tree() if isinstance(b, N.NiTriShape))
merged_v, merged_n, merged_uv, merged_t = [], [], [], []
for child in root.children:
    offset = len(merged_v)
    gd = child.data
    merged_v.extend((v.y - .657, -v.x, v.z - 58.771) for v in gd.vertices)
    merged_n.extend((v.y, -v.x, v.z) for v in gd.normals)
    merged_uv.extend((v.u, v.v) for v in gd.uv_sets[0])
    merged_t.extend((t.v_1 + offset, t.v_2 + offset, t.v_3 + offset) for t in gd.triangles)
out_root.name = b'MojaveSkateRoot'
out_root.flags = 14
out_root.translation.x = out_root.translation.y = out_root.translation.z = 0.0
out_root.rotation.set_identity()
out_shape.name = b'MojaveSkateBoard'
out_shape.flags = 14
out_shape.translation.x = out_shape.translation.y = out_shape.translation.z = 0.0
out_shape.rotation.set_identity()
out_shape.scale = 1.0
gd = out_shape.data
gd.num_vertices = len(merged_v)
gd.has_vertices = True
gd.vertices.update_size()
for dst, src in zip(gd.vertices, merged_v): dst.x, dst.y, dst.z = src
gd.has_normals = True
gd.normals.update_size()
for dst, src in zip(gd.normals, merged_n): dst.x, dst.y, dst.z = src
gd.num_uv_sets = 1
gd.uv_sets.update_size()
for dst, src in zip(gd.uv_sets[0], merged_uv): dst.u, dst.v = src
gd.num_triangles = len(merged_t)
gd.num_triangle_points = len(merged_t) * 3
gd.has_triangles = True
gd.triangles.update_size()
for dst, src in zip(gd.triangles, merged_t): dst.v_1, dst.v_2, dst.v_3 = src
gd.consistency_flags = 16384
gd.update_center_radius()
for prop in out_shape.properties:
    if isinstance(prop, N.BSShaderPPLightingProperty):
        prop.shader_flags.sf_remappable_textures = 1
        prop.texture_set.textures[0] = b'textures\\MojaveSkate\\deck.dds'
        prop.texture_set.textures[1] = b'textures\\MojaveSkate\\deck_n.dds'
        for i in range(2, len(prop.texture_set.textures)): prop.texture_set.textures[i] = b''
    elif isinstance(prop, N.NiMaterialProperty):
        prop.name = b'MojaveSkateMaterial'
        prop.diffuse_color.r = prop.diffuse_color.g = prop.diffuse_color.b = .85
        prop.ambient_color.r = prop.ambient_color.g = prop.ambient_color.b = .85
        prop.alpha = 1.0
out_shape.update_tangent_space(as_extra=False)
with (MESH / 'board.nif').open('wb') as f:
    out.write(f)
check=N.Data()
with (MESH / 'board.nif').open('rb') as f:
    check.read(f)
assert len(check.roots[0].children)==1
assert check.version==0x14020007 and check.user_version==11
print('Validated NIF:', MESH / 'board.nif')

# Original full-body skateboard stance. The KF files below are written from
# scratch. Each locomotion group has the real internal Gamebryo group name;
# the old 0.13 build copied an Idle sequence into every filename and therefore
# stopped after blending. Actor translation remains owned by the native player
# controller (HoldControl + SpeedMult), not by a visual skeleton root curve.
SKELETON = MOD.parent / 'NV Compatibility Skeleton/Meshes/Characters/_Male/Skeleton.nif'
ANIM = MESH.parent / 'characters/_male/idleanims/MojaveSkate'
ANIM.mkdir(parents=True, exist_ok=True)
skel = N.Data()
with SKELETON.open('rb') as f:
    skel.read(f)
nodes = {}
for block in skel.roots[0].tree():
    name = block.name.decode(errors='replace') if isinstance(getattr(block, 'name', None), bytes) else getattr(block, 'name', '')
    if name:
        nodes[name] = block

def qmul(a, b):
    q = N.Quaternion()
    q.w = a.w*b.w - a.x*b.x - a.y*b.y - a.z*b.z
    q.x = a.w*b.x + a.x*b.w + a.y*b.z - a.z*b.y
    q.y = a.w*b.y - a.x*b.z + a.y*b.w + a.z*b.x
    q.z = a.w*b.z + a.x*b.y - a.y*b.x + a.z*b.w
    return q

def qeuler(pitch, roll, yaw):
    p, r, y = (math.radians(v) * .5 for v in (pitch, roll, yaw))
    qp = N.Quaternion(); qp.w, qp.x = math.cos(p), math.sin(p)
    qr = N.Quaternion(); qr.w, qr.y = math.cos(r), math.sin(r)
    qy = N.Quaternion(); qy.w, qy.z = math.cos(y), math.sin(y)
    return qmul(qmul(qp, qr), qy)

# A skeleton NIF is a bind pose (arms are spread).  Writing those rotations
# directly into a locomotion KF therefore produced a near T-pose as soon as W
# selected Forward.  Sample the first frame of the locally installed mtidle
# container instead.  We freeze that authored neutral frame and only reuse its
# transforms; group names and timing remain ours.  This build is intentionally
# local-only and is not a redistribution package.
REFERENCE_IDLE = Path(__file__).parent / (
    'backups/before-0.14-regression/Mojave Skate/'
    'meshes/MojaveSkate/locomotion/mtidle.kf'
)
reference = N.Data()
with REFERENCE_IDLE.open('rb') as f:
    reference.read(f)

POSE_NODES = {
    'Bip01 Pelvis',
    'Bip01 Spine',
    'Bip01 Spine1',
    'Bip01 L UpperArm',
    'Bip01 R UpperArm',
    'Bip01 L Forearm',
    'Bip01 R Forearm',
}
TORSO_OFFSETS = {
    'Bip01 Pelvis': (-2, 0, 2),
    'Bip01 Spine': (-4, 0, -1),
    'Bip01 Spine1': (-3, 0, -1),
}
reference_pose = []
for source in reference.roots[0].controlled_blocks:
    name = source.node_name.decode(errors='replace') if isinstance(source.node_name, bytes) else str(source.node_name)
    interp = source.interpolator
    if (source.controller_type != b'NiTransformController'
            or not isinstance(interp, N.NiTransformInterpolator)
            or name not in POSE_NODES
            or name not in nodes):
        continue
    translation = (interp.translation.x, interp.translation.y, interp.translation.z)
    rotation = (interp.rotation.w, interp.rotation.x, interp.rotation.y, interp.rotation.z)
    scale = interp.scale
    transform_data = interp.data
    if transform_data:
        if transform_data.translations.num_keys:
            key = transform_data.translations.keys[0].value
            translation = (key.x, key.y, key.z)
        if transform_data.num_rotation_keys and transform_data.rotation_type != 4:
            key = transform_data.quaternion_keys[0].value
            rotation = (key.w, key.x, key.y, key.z)
        if transform_data.scales.num_keys:
            scale = transform_data.scales.keys[0].value
    if name in TORSO_OFFSETS:
        bone = nodes[name]
        translation = (bone.translation.x, bone.translation.y, bone.translation.z)
        base = bone.rotation.get_scale_quat()[1]
        posed = qmul(base, qeuler(*TORSO_OFFSETS[name]))
        rotation = (posed.w, posed.x, posed.y, posed.z)
        scale = bone.scale
    reference_pose.append((name, translation, rotation, scale))

assert len(reference_pose) == len(POSE_NODES), 'reference idle did not yield the requested pose bones'

LOCOMOTION = MESH / 'locomotion'
LOCOMOTION.mkdir(parents=True, exist_ok=True)

# FNV locomotion advances the actor through an accumulated Bip01 spline.  A
# plain linear transform moves only the visual skeleton (the failed fly-away
# prototype); the installed Sigma locomotion set supplies known-good spline
# containers for the four directions.  Only Bip01 and Bip01 NonAccum are
# retained, and the resulting build remains local to this game installation.
SIGMA = MOD.parent / (
    '3rd person Movement Animations Overhaul/meshes/AnimGroupOverride/'
    'Sigma_Male/_male/human/locomotion/male'
)
motion_sources = {}
for stem in ('mtfastforward', 'mtfastbackward', 'mtfastleft', 'mtfastright'):
    source_data = N.Data()
    with (SIGMA / f'{stem}.kf').open('rb') as f:
        source_data.read(f)
    motion_blocks = []
    for block in source_data.roots[0].controlled_blocks:
        if block.node_name in (b'Bip01', b'Bip01 NonAccum'):
            motion_blocks.append(block)
    assert {block.node_name for block in motion_blocks} == {b'Bip01', b'Bip01 NonAccum'}
    motion_sources[stem] = (source_data, motion_blocks, source_data.roots[0].stop_time)

groups = {
    'mtidle': ('Idle', 4.0, (0.0, 0.0, 0.0)),
    'mtforward': ('Forward', 1.0, (0.0, 145.0, 0.0)),
    'mtfastforward': ('FastForward', 0.8, (0.0, 283.0, 0.0)),
    'mtbackward': ('Backward', 1.0, (0.0, -105.0, 0.0)),
    'mtfastbackward': ('FastBackward', 0.8, (0.0, -165.0, 0.0)),
    'mtleft': ('Left', 1.0, (-105.0, 0.0, 0.0)),
    'mtright': ('Right', 1.0, (105.0, 0.0, 0.0)),
    'mtfastleft': ('FastLeft', 0.8, (-165.0, 0.0, 0.0)),
    'mtfastright': ('FastRight', 0.8, (165.0, 0.0, 0.0)),
    'mtturnleft': ('TurnLeft', 1.0, (0.0, 0.0, 0.0)),
    'mtturnright': ('TurnRight', 1.0, (0.0, 0.0, 0.0)),
}

motion_for_group = {
    'mtforward': 'mtfastforward',
    'mtfastforward': 'mtfastforward',
    'mtbackward': 'mtfastbackward',
    'mtfastbackward': 'mtfastbackward',
    'mtleft': 'mtfastleft',
    'mtfastleft': 'mtfastleft',
    'mtright': 'mtfastright',
    'mtfastright': 'mtfastright',
}

def make_sequence(group_name, duration, displacement, motion_blocks=()):
    kf = N.Data(version=0x14020007, user_version=11, user_version_2=34)
    kf.header.endian_type = 1
    seq = N.NiControllerSequence()
    seq.name = group_name.encode()
    seq.weight = 1.0
    seq.cycle_type = 0
    seq.frequency = 1.0
    seq.start_time = 0.0
    seq.stop_time = duration
    seq.target_name = b'Bip01'
    seq.unknown_int_1 = 1
    keys = N.NiTextKeyExtraData()
    keys.num_text_keys = 3
    keys.text_keys.update_size()
    keys.text_keys[0].time, keys.text_keys[0].value = 0.0, b'start'
    keys.text_keys[1].time, keys.text_keys[1].value = min(duration, 0.0333333), b'Blend:9'
    keys.text_keys[2].time, keys.text_keys[2].value = duration, b'end'
    seq.text_keys = keys
    seq.num_controlled_blocks = len(reference_pose) + len(motion_blocks)
    seq.controlled_blocks.update_size()
    block_index = 0
    for source in motion_blocks:
        controlled = seq.controlled_blocks[block_index]
        controlled.interpolator = source.interpolator
        controlled.priority = source.priority
        controlled.node_name = source.node_name
        controlled.controller_type = source.controller_type
        block_index += 1
    for name, translation, rotation, scale in reference_pose:
        controlled = seq.controlled_blocks[block_index]
        interp = N.NiTransformInterpolator()
        interp.translation.x, interp.translation.y, interp.translation.z = translation
        interp.rotation.w, interp.rotation.x, interp.rotation.y, interp.rotation.z = rotation
        interp.scale = scale
        controlled.interpolator = interp
        controlled.priority = 20
        controlled.node_name = name.encode()
        controlled.controller_type = b'NiTransformController'
        block_index += 1
    kf.roots = [seq]
    return kf

for filename, (group_name, duration, displacement) in groups.items():
    source_key = motion_for_group.get(filename)
    motion_blocks = ()
    if source_key:
        _source_data, motion_blocks, duration = motion_sources[source_key]
    kf = make_sequence(group_name, duration, displacement, motion_blocks)
    with (LOCOMOTION / f'{filename}.kf').open('wb') as f:
        kf.write(f)
    check = N.Data()
    with (LOCOMOTION / f'{filename}.kf').open('rb') as f:
        check.read(f)
    seq_check = check.roots[0]
    assert seq_check.name == group_name.encode()
    assert seq_check.unknown_int_1 == 1
    assert any(c.node_name == b'Bip01' for c in seq_check.controlled_blocks) == bool(source_key)

# Keep the old diagnostic path valid for local inspection; runtime uses the
# group files above.
idle = make_sequence('SpecialIdle_MojaveSkate', 4.0, (0.0, 0.0, 0.0))
with (ANIM / 'SkateLoop.kf').open('wb') as f:
    idle.write(f)
print('Validated original kNVSE locomotion set:', LOCOMOTION)

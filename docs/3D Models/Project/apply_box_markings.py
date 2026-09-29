"""Apply the LumosAir laser-marking artwork to the black box in Node.blend as decals.

Run from Blender's Text Editor (Run Script), or via the MCP.  Safe to re-run.
Creates 4 thin decal planes (one per side) parented to the black body. Each uses the
mark PNGs in ./textures (white = laser mark).  One switch drives all four:
    Shader node group "LumosAir marking | node role"  ->  Value 0 = LASER node, 1 = FAN node
"""
import bpy, os, math

BODY = '01 Black body | 90 x 115 x 40 mm'
TEX = os.path.join(os.path.dirname(bpy.data.filepath), 'textures')
COLL = 'Box laser marking (decals)'
MARK_RGB = (0.62, 0.62, 0.60)    # UV mark on black ABS: light grey, slightly matte
OFF = 0.03                       # mm proud of the wall

body = bpy.data.objects[BODY]
coll = bpy.data.collections.get(COLL)
if not coll:
    coll = bpy.data.collections.new(COLL)
    (body.users_collection[0] if body.users_collection else bpy.context.scene.collection).children.link(coll)

# ---------- shared role switch ----------
grp = bpy.data.node_groups.get('LumosAir marking | node role')
if not grp:
    grp = bpy.data.node_groups.new('LumosAir marking | node role', 'ShaderNodeTree')
    grp.interface.new_socket('Role (0 laser, 1 fan)', in_out='OUTPUT', socket_type='NodeSocketFloat')
    val = grp.nodes.new('ShaderNodeValue'); val.name = 'ROLE'; val.label = 'ROLE: 0 = laser node, 1 = fan node'
    val.outputs[0].default_value = 0.0
    out = grp.nodes.new('NodeGroupOutput')
    grp.links.new(val.outputs[0], out.inputs[0])


def img(name):
    p = os.path.join(TEX, name)
    im = bpy.data.images.get(name) or bpy.data.images.load(p, check_existing=True)
    im.colorspace_settings.name = 'Non-Color'
    return im


def material(face):
    mname = f'Laser marking | {face}'
    m = bpy.data.materials.get(mname) or bpy.data.materials.new(mname)
    m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    tc = nt.nodes.new('ShaderNodeTexCoord')
    il = nt.nodes.new('ShaderNodeTexImage'); il.image = img(f'mark_laser_node_{face}.png'); il.interpolation = 'Cubic'
    ifn = nt.nodes.new('ShaderNodeTexImage'); ifn.image = img(f'mark_fan_node_{face}.png'); ifn.interpolation = 'Cubic'
    for n in (il, ifn):
        n.extension = 'CLIP'
        nt.links.new(tc.outputs['UV'], n.inputs['Vector'])
    g = nt.nodes.new('ShaderNodeGroup'); g.node_tree = grp
    mix = nt.nodes.new('ShaderNodeMix'); mix.data_type = 'FLOAT'
    nt.links.new(g.outputs[0], mix.inputs['Factor'])
    nt.links.new(il.outputs['Color'], mix.inputs[2])
    nt.links.new(ifn.outputs['Color'], mix.inputs[3])
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Base Color'].default_value = (*MARK_RGB, 1)
    bsdf.inputs['Roughness'].default_value = 0.72
    nt.links.new(mix.outputs[0], bsdf.inputs['Alpha'])
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    for i, n in enumerate((tc, il, ifn, g, mix, bsdf, out)):
        n.location = (i * 260 - 800, (i % 2) * -260)
    try:
        m.surface_render_method = 'DITHERED'
    except Exception:
        pass
    m.use_backface_culling = True
    return m


def plane(face, corners_uv):
    """corners_uv: list of 4 (world xyz, uv) counter-clockwise seen from outside"""
    name = f'Laser marking decal | {face}'
    me = bpy.data.meshes.get(name) or bpy.data.meshes.new(name)
    me.clear_geometry()
    me.from_pydata([c for c, uv in corners_uv], [], [(0, 1, 2, 3)])
    uvl = me.uv_layers.new(name='UVMap') if not me.uv_layers else me.uv_layers[0]
    for li, (c, uv) in enumerate(corners_uv):
        uvl.data[li].uv = uv
    me.materials.clear(); me.materials.append(material(face))
    ob = bpy.data.objects.get(name)
    if not ob:
        ob = bpy.data.objects.new(name, me); coll.objects.link(ob)
    ob.data = me
    ob.parent = body
    ob.matrix_parent_inverse = body.matrix_world.inverted()
    ob.matrix_world = __import__('mathutils').Matrix.Identity(4)
    ob.visible_shadow = False
    return ob


# world geometry of the base (outside): x +-45, y 117.48 .. 232.48, z 0 .. 40
X, Y0, Y1, H = 45.0, 117.48, 232.48, 40.0
o = OFF
plane('PX', [((X + o, Y0, 0), (0, 0)), ((X + o, Y1, 0), (1, 0)), ((X + o, Y1, H), (1, 1)), ((X + o, Y0, H), (0, 1))])
plane('MX', [((-X - o, Y1, 0), (0, 0)), ((-X - o, Y0, 0), (1, 0)), ((-X - o, Y0, H), (1, 1)), ((-X - o, Y1, H), (0, 1))])
plane('USB', [((-X, Y0 - o, 0), (0, 0)), ((X, Y0 - o, 0), (1, 0)), ((X, Y0 - o, H), (1, 1)), ((-X, Y0 - o, H), (0, 1))])
plane('ANT', [((X, Y1 + o, 0), (0, 0)), ((-X, Y1 + o, 0), (1, 0)), ((-X, Y1 + o, H), (1, 1)), ((X, Y1 + o, H), (0, 1))])
print('decals applied; role =', grp.nodes['ROLE'].outputs[0].default_value)

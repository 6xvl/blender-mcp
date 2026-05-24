# Tool Reference

Auto-generated from `server/server.py`. **264 tools**.

## Quick index

| Category | Tools |
|---|---|
| **add** (23) | `bm_add_armature`, `bm_add_armature_modifier`, `bm_add_bone_chain`, `bm_add_bone_constraint`, `bm_add_cloth`, `bm_add_collision`, `bm_add_constraint`, `bm_add_curve_primitive`, `bm_add_driver`, `bm_add_fluid`, `bm_add_force_field`, `bm_add_modifier`, `bm_add_particle_system`, `bm_add_primitive`, `bm_add_reference_image`, `bm_add_rigidbody`, `bm_add_shape_key`, `bm_add_skin_modifier`, `bm_add_softbody`, `bm_add_solidify_modifier`, `bm_add_subsurf`, `bm_add_to_collection`, `bm_add_wireframe_modifier` |
| **align** (4) | `bm_align_edge_to_axis`, `bm_align_face_to_face`, `bm_align_normal_to_axis`, `bm_align_objects` |
| **angle** (1) | `bm_angle_vectors` |
| **animate** (1) | `bm_animate_visibility` |
| **append** (1) | `bm_append_from_blend` |
| **apply** (3) | `bm_apply_all_modifiers`, `bm_apply_modifier`, `bm_apply_transforms` |
| **array** (2) | `bm_array_modifier`, `bm_array_objects_along_edge` |
| **assign** (3) | `bm_assign_action`, `bm_assign_material`, `bm_assign_vertex_group` |
| **auto** (2) | `bm_auto_smooth`, `bm_auto_weights` |
| **bake** (2) | `bm_bake_physics`, `bm_bake_pose_keyframes` |
| **bevel** (1) | `bm_bevel_edges` |
| **bezier** (1) | `bm_bezier_from_4pts` |
| **bisect** (1) | `bm_bisect_plane` |
| **blend** (1) | `bm_blend_actions` |
| **bridge** (1) | `bm_bridge_edge_loops` |
| **build** (1) | `bm_build_viewmodel_rig` |
| **center** (2) | `bm_center_of_mass`, `bm_center_to_origin` |
| **centroid** (1) | `bm_centroid_of_points` |
| **check** (2) | `bm_check_symmetry`, `bm_check_topology` |
| **circle** (2) | `bm_circle_arc`, `bm_circle_from_3pts` |
| **clean** (2) | `bm_clean_topology`, `bm_clean_weights` |
| **clear** (5) | `bm_clear_action_keys`, `bm_clear_bone_constraints`, `bm_clear_constraints`, `bm_clear_parent`, `bm_clear_pose` |
| **color** (2) | `bm_color_faces`, `bm_color_faces_by_side` |
| **compare** (1) | `bm_compare_meshes` |
| **convert** (1) | `bm_convert_format` |
| **copy** (2) | `bm_copy_action`, `bm_copy_weights` |
| **count** (1) | `bm_count_vgroup_weights` |
| **create** (6) | `bm_create_action`, `bm_create_collection`, `bm_create_control_bone`, `bm_create_curve`, `bm_create_empty`, `bm_create_material` |
| **cursor** (3) | `bm_cursor_to_object`, `bm_cursor_to_origin`, `bm_cursor_to_selected` |
| **curve** (2) | `bm_curve_modifier`, `bm_curve_to_mesh` |
| **cyclic** (1) | `bm_cyclic_action` |
| **decimate** (2) | `bm_decimate_planar`, `bm_decimate_unsubdivide` |
| **delete** (2) | `bm_delete_action`, `bm_delete_objects` |
| **dissolve** (1) | `bm_dissolve_limited` |
| **dist** (2) | `bm_dist_point_to_line`, `bm_dist_point_to_plane` |
| **distribute** (1) | `bm_distribute_objects` |
| **dump** (1) | `bm_dump_objects` |
| **edge** (2) | `bm_edge_slide`, `bm_edge_split` |
| **edit** (1) | `bm_edit_bone` |
| **emboss** (1) | `bm_emboss_text` |
| **equalize** (1) | `bm_equalize_edges` |
| **export** (3) | `bm_export_fbx`, `bm_export_format`, `bm_export_weights` |
| **extrude** (1) | `bm_extrude_along_normal` |
| **fill** (1) | `bm_fill_face` |
| **find** (3) | `bm_find_by_property`, `bm_find_closest_vertex`, `bm_find_objects` |
| **flatten** (1) | `bm_flatten_verts` |
| **force** (1) | `bm_force_mode_set` |
| **get** (6) | `bm_get_bbox`, `bm_get_bone_world`, `bm_get_evaluated_vertex`, `bm_get_transform`, `bm_get_vertex`, `bm_get_weights_at_vert` |
| **grid** (1) | `bm_grid_fill` |
| **identify** (1) | `bm_identify_faces` |
| **import** (2) | `bm_import_format`, `bm_import_weights` |
| **inset** (1) | `bm_inset_faces` |
| **inspect** (2) | `bm_inspect_animation`, `bm_inspect_modifier` |
| **intersect** (1) | `bm_intersect_line_plane` |
| **isolate** (1) | `bm_isolate_bone_weights` |
| **join** (1) | `bm_join_objects` |
| **keyframe** (5) | `bm_keyframe_bone`, `bm_keyframe_material_color`, `bm_keyframe_material_emission`, `bm_keyframe_pose_dict`, `bm_keyframe_property` |
| **label** (1) | `bm_label_faces_by_side` |
| **level** (1) | `bm_level_to_ground` |
| **list** (5) | `bm_list_actions`, `bm_list_bones`, `bm_list_collections`, `bm_list_modifiers`, `bm_list_workspaces` |
| **local** (1) | `bm_local_to_world` |
| **loop** (1) | `bm_loop_cut` |
| **make** (2) | `bm_make_lod_set`, `bm_make_orthogonal_corner` |
| **mark** (2) | `bm_mark_seam`, `bm_mark_sharp` |
| **measure** (1) | `bm_measure_edge_length` |
| **merge** (1) | `bm_merge_verts` |
| **mesh** (2) | `bm_mesh_separate`, `bm_mesh_thickness_stats` |
| **minimize** (1) | `bm_minimize_poles` |
| **mirror** (4) | `bm_mirror_bones`, `bm_mirror_object`, `bm_mirror_verts`, `bm_mirror_weights` |
| **misc** (18) | `bm_boolean`, `bm_decimate`, `bm_distance`, `bm_duplicate`, `bm_hide`, `bm_lerp`, `bm_list`, `bm_ping`, `bm_quadrify`, `bm_remesh`, `bm_rename`, `bm_rotate`, `bm_scale`, `bm_select`, `bm_subdivide`, `bm_symmetrize`, `bm_translate`, `bm_triangulate` |
| **normal** (1) | `bm_normal_from_3pts` |
| **normalize** (1) | `bm_normalize_vertex_groups` |
| **object** (1) | `bm_object_to_cursor` |
| **offset** (1) | `bm_offset_curve` |
| **optimize** (1) | `bm_optimize_for_polycount` |
| **paint** (1) | `bm_paint_weight_to_bone` |
| **parent** (1) | `bm_parent_to_bone` |
| **pca** (1) | `bm_pca_align` |
| **perfect** (1) | `bm_perfect_box` |
| **planar** (1) | `bm_planar_faces` |
| **pole** (1) | `bm_pole_count` |
| **pose** (1) | `bm_pose_bone_xform` |
| **proportional** (1) | `bm_proportional_translate` |
| **punch** (1) | `bm_punch_pattern` |
| **push** (1) | `bm_push_to_nla` |
| **quadriflow** (1) | `bm_quadriflow_remesh` |
| **quick** (1) | `bm_quick_fps_pose` |
| **read** (1) | `bm_read_console` |
| **recalc** (1) | `bm_recalc_normals` |
| **reload** (1) | `bm_reload_addon` |
| **remove** (5) | `bm_remove_doubles`, `bm_remove_from_collection`, `bm_remove_loose_geometry`, `bm_remove_modifier`, `bm_remove_zero_weights` |
| **render** (1) | `bm_render_image` |
| **resize** (1) | `bm_resize_texture` |
| **rotate** (1) | `bm_rotate_verts` |
| **round** (1) | `bm_round_vert_positions` |
| **save** (1) | `bm_save_blend` |
| **score** (1) | `bm_score_mesh_quality` |
| **screenshot** (1) | `bm_screenshot_views` |
| **select** (12) | `bm_select_all`, `bm_select_by_material`, `bm_select_edge_loop`, `bm_select_edge_ring`, `bm_select_high_poles`, `bm_select_inside_bbox`, `bm_select_linked`, `bm_select_ngons`, `bm_select_non_manifold`, `bm_select_pattern`, `bm_select_stretched_tris`, `bm_select_tris` |
| **separate** (4) | `bm_separate_by_bbox`, `bm_separate_by_material`, `bm_separate_by_normal`, `bm_separate_by_vgroup` |
| **set** (28) | `bm_set_active`, `bm_set_active_vgroup`, `bm_set_area_type`, `bm_set_armature_mode`, `bm_set_bone_display`, `bm_set_bone_roll`, `bm_set_camera`, `bm_set_cursor`, `bm_set_curve_bevel`, `bm_set_edge_bevel_weight`, `bm_set_edge_crease`, `bm_set_edge_position`, `bm_set_frame`, `bm_set_gravity`, `bm_set_keyframe_interp`, `bm_set_mode`, `bm_set_origin`, `bm_set_origin_to_face`, `bm_set_origin_to_vert`, `bm_set_parent`, `bm_set_pose_from_dict`, `bm_set_render`, `bm_set_shading_smooth`, `bm_set_transform`, `bm_set_vert_bevel_weight`, `bm_set_vertex`, `bm_set_view`, `bm_set_workspace` |
| **setup** (4) | `bm_setup_arm_ik`, `bm_setup_car_template`, `bm_setup_ik`, `bm_setup_leg_ik` |
| **shrinkwrap** (1) | `bm_shrinkwrap_to` |
| **slerp** (1) | `bm_slerp_quat` |
| **smart** (1) | `bm_smart_bevel` |
| **smooth** (2) | `bm_smooth_verts`, `bm_smooth_weights` |
| **snap** (1) | `bm_snap_to_grid` |
| **split** (1) | `bm_split_area` |
| **text** (1) | `bm_text_3d` |
| **transfer** (1) | `bm_transfer_weights` |
| **translate** (1) | `bm_translate_verts` |
| **uv** (1) | `bm_uv_unwrap` |
| **view** (1) | `bm_view_camera` |
| **warn** (1) | `bm_warn_topology` |
| **weight** (4) | `bm_weight_by_axis_split`, `bm_weight_by_plane_split`, `bm_weight_falloff_from_point`, `bm_weight_gradient` |
| **world** (1) | `bm_world_to_local` |

---

## add

### `bm_add_armature`

```
bm_add_armature(name: str, bones: list)
```

Create armature with bones.
    bones = [{"name": str, "head": [x,y,z], "tail": [x,y,z], "parent": str|None, "connect": bool}]

### `bm_add_armature_modifier`

```
bm_add_armature_modifier(mesh_name: str, armature_name: str, vgroups: bool = True, envelopes: bool = False)
```

Bind mesh to armature via Armature modifier + parenting.

### `bm_add_bone_chain`

```
bm_add_bone_chain(armature_name: str, names: list, head_positions: list, tail_positions: list = None, parent_chain: bool = True, parent_first_to: str = None, connect: bool = True)
```

Add chain of bones. tail auto-derived from next head if None. parent_chain: each bone parents to previous.

### `bm_add_bone_constraint`

```
bm_add_bone_constraint(armature_name: str, bone_name: str, type: str, target: str = None, subtarget: str = None)
```

Add bone constraint. type: IK|TRACK_TO|COPY_LOCATION|COPY_ROTATION|COPY_TRANSFORMS|LIMIT_ROTATION|DAMPED_TRACK.

### `bm_add_cloth`

```
bm_add_cloth(name: str, mass: float = 0.3, tension_stiffness: float = 15, compression_stiffness: float = 15, shear_stiffness: float = 5, bending_stiffness: float = 0.5, quality: int = 5)
```

Add Cloth physics to mesh.

### `bm_add_collision`

```
bm_add_collision(name: str, damping: float = 0.1, friction: float = 0.5)
```

Add collision for cloth/fluid/softbody to bounce off.

### `bm_add_constraint`

```
bm_add_constraint(name: str, type: str, target: str = None, track_axis: str = "TRACK_NEGATIVE_Z", up_axis: str = "UP_Y", subtarget: str = None, influence: float = 1.0)
```

Add constraint. type: TRACK_TO|COPY_LOCATION|COPY_ROTATION|CHILD_OF|LIMIT_LOCATION|IK.

### `bm_add_curve_primitive`

```
bm_add_curve_primitive(type: str, name: str = None, location: list = None, radius: float = 1.0)
```

Add curve primitive. type: BEZIER_CIRCLE|BEZIER_CURVE|NURBS_CIRCLE|NURBS_PATH.

### `bm_add_driver`

```
bm_add_driver(target_object: str, target_data_path: str, source_object: str, source_data_path: str, expression: str = "var")
```

Add driver: target_obj.target_data_path driven by source_obj.source_data_path with Python expression (var = source value).

### `bm_add_fluid`

```
bm_add_fluid(name: str, type: str = "DOMAIN", domain_type: str = "GAS", resolution: int = 64)
```

type: DOMAIN|FLOW|EFFECTOR. domain_type: GAS|LIQUID.

### `bm_add_force_field`

```
bm_add_force_field(name: str = "ForceField", type: str = "WIND", location: list = None, strength: float = 1.0)
```

type: WIND|VORTEX|TURBULENCE|MAGNETIC|HARMONIC|CURVE_GUIDE|GUIDE.

### `bm_add_modifier`

```
bm_add_modifier(name: str, mod_type: str, mod_name: str = None, properties: dict = None)
```

Add modifier. mod_type: SUBSURF|MIRROR|ARMATURE|SOLIDIFY|BEVEL|SMOOTH|DECIMATE|BOOLEAN|ARRAY|LATTICE|SHRINKWRAP.
    properties: dict like {'levels':2, 'object':'OtherObjName'} (object refs auto-resolved).

### `bm_add_particle_system`

```
bm_add_particle_system(name: str, type: str = "EMITTER", count: int = 1000, frame_start: int = 1, frame_end: int = 200, lifetime: int = 50)
```

type: EMITTER|HAIR.

### `bm_add_primitive`

```
bm_add_primitive(type: str, name: str = None, location: list = None, size: float = 1.0, segments: int = 32, rings: int = 16)
```

Add primitive. type: CUBE|UV_SPHERE|ICO_SPHERE|CYLINDER|CONE|TORUS|PLANE|CIRCLE|MONKEY.

### `bm_add_reference_image`

```
bm_add_reference_image(filepath: str, axis: str = "FRONT", location: list = None, size: float = 1.0, opacity: float = 0.5)
```

Add background reference image for blueprint modeling. axis: FRONT|BACK|LEFT|RIGHT|TOP|BOTTOM.

### `bm_add_rigidbody`

```
bm_add_rigidbody(name: str, type: str = "ACTIVE", mass: float = 1.0, collision_shape: str = "CONVEX_HULL", friction: float = 0.5, restitution: float = 0.0)
```

type: ACTIVE|PASSIVE. shape: BOX|SPHERE|CAPSULE|CONVEX_HULL|MESH.

### `bm_add_shape_key`

```
bm_add_shape_key(mesh_name: str, name: str, from_mix: bool = False)
```

Add shape key to mesh (auto-creates Basis on first call).

### `bm_add_skin_modifier`

```
bm_add_skin_modifier(name: str, root_vert_index: int = 0, default_size: float = 0.05)
```

Skin modifier — turns edge graph into cylinders. Set root vert + default radius.

### `bm_add_softbody`

```
bm_add_softbody(name: str, mass: float = 1.0, friction: float = 0.5, goal_default: float = 0.7)
```

Add Soft Body physics.

### `bm_add_solidify_modifier`

```
bm_add_solidify_modifier(name: str, thickness: float = 0.01, offset: float = -1.0)
```

Solidify modifier — gives sheet thickness. offset: -1=inside, 0=center, 1=outside.

### `bm_add_subsurf`

```
bm_add_subsurf(name: str, levels: int = 2, render_levels: int = None)
```

Add Subdivision Surface modifier.

### `bm_add_to_collection`

```
bm_add_to_collection(object_names: list, collection_name: str)
```

Add objects to a collection.

### `bm_add_wireframe_modifier`

```
bm_add_wireframe_modifier(name: str, thickness: float = 0.01, offset: float = 0.0)
```

Wireframe modifier — converts mesh to 3D wire.

## align

### `bm_align_edge_to_axis`

```
bm_align_edge_to_axis(name: str, edge_index: int, axis: str = "x", fix: str = "HEAD")
```

Snap edge exactly along axis. fix: HEAD (keep head, move tail) | TAIL | CENTER.

### `bm_align_face_to_face`

```
bm_align_face_to_face(src_name: str, src_face: int, dst_name: str, dst_face: int, flip: bool = False)
```

Move + rotate src so its face touches dst's face (normals opposite). Critical for assembling gun parts.

### `bm_align_normal_to_axis`

```
bm_align_normal_to_axis(name: str, face_index: int, target_axis: str = "z")
```

Rotate entire object so face's normal aligns with world axis. target_axis: x|y|z|-x|-y|-z.

### `bm_align_objects`

```
bm_align_objects(names: list, axis: str = "z", target: str = "MIN", value: float = None)
```

Align bboxes of multiple objects along axis. target: MIN|MAX|CENTER.

## angle

### `bm_angle_vectors`

```
bm_angle_vectors(v1: list, v2: list)
```

Angle (deg) between two vectors.

## animate

### `bm_animate_visibility`

```
bm_animate_visibility(object_name: str, frame: int, visible: bool = True)
```

Keyframe object visibility (viewport + render).

## append

### `bm_append_from_blend`

```
bm_append_from_blend(filepath: str, object_names: list = None, action_names: list = None)
```

Append objects + actions from another .blend file.

## apply

### `bm_apply_all_modifiers`

```
bm_apply_all_modifiers(name: str)
```

Apply all modifiers in stack order.

### `bm_apply_modifier`

```
bm_apply_modifier(name: str, modifier_name: str)
```

Apply (bake) modifier into mesh data.

### `bm_apply_transforms`

```
bm_apply_transforms(name: str, location: bool = False, rotation: bool = True, scale: bool = True)
```

Apply object transform to mesh data (bake).

## array

### `bm_array_modifier`

```
bm_array_modifier(name: str, count: int = 3, axis: str = "x", offset: float = 1.0, fit_type: str = "FIXED_COUNT", curve: str = None)
```

Array modifier (non-destructive).

### `bm_array_objects_along_edge`

```
bm_array_objects_along_edge(template_name: str, target_name: str, edge_indices: list, count_per_edge: int = 5)
```

Place instances of template along edges of target — rivets, screws, body trim.

## assign

### `bm_assign_action`

```
bm_assign_action(armature_name: str, action_name: str)
```

Assign action to armature's animation_data.action.

### `bm_assign_material`

```
bm_assign_material(name: str, material_name: str, face_indices: list = None)
```

Assign material to object or specific faces.

### `bm_assign_vertex_group`

```
bm_assign_vertex_group(mesh_name: str, group_name: str, vert_indices: list, weight: float = 1.0)
```

Add verts to vertex group with weight. Creates group if missing.

## auto

### `bm_auto_smooth`

```
bm_auto_smooth(name: str, angle_deg: float = 30, enabled: bool = True)
```

Enable mesh auto-smooth with angle threshold.

### `bm_auto_weights`

```
bm_auto_weights(mesh_name: str, armature_name: str)
```

Bind mesh to armature with AUTOMATIC heat-map weights (no manual weight painting needed).

## bake

### `bm_bake_physics`

```
bm_bake_physics(start_frame: int = 1, end_frame: int = 250)
```

Bake all physics simulations in scene.

### `bm_bake_pose_keyframes`

```
bm_bake_pose_keyframes(armature_name: str, frame: int, bone_names: list = None)
```

Snapshot current pose into keyframes at frame. bone_names=None => all bones.

## bevel

### `bm_bevel_edges`

```
bm_bevel_edges(name: str, offset: float = 0.02, segments: int = 2, profile: float = 0.5, edge_indices: list = None)
```

Bevel edges. edge_indices=None => all edges.

## bezier

### `bm_bezier_from_4pts`

```
bm_bezier_from_4pts(p0: list, p1: list, p2: list, p3: list, segments: int = 16, name: str = "Bezier")
```

Create cubic Bezier curve from 4 control points.

## bisect

### `bm_bisect_plane`

```
bm_bisect_plane(name: str, plane_point: list, plane_normal: list, fill: bool = True, clear_inner: bool = False, clear_outer: bool = False)
```

Bisect mesh with plane. clear_inner removes side opposite normal.

## blend

### `bm_blend_actions`

```
bm_blend_actions(target_armature: str, action1: str, action2: str, weight: float = 0.5, blend_mode: str = "REPLACE")
```

Blend two actions via NLA strips. weight: 0=action1, 1=action2.

## bridge

### `bm_bridge_edge_loops`

```
bm_bridge_edge_loops(name: str, edge_indices: list = None)
```

Bridge two edge loops. edge_indices: list forming two loops, or None for current selection.

## build

### `bm_build_viewmodel_rig`

```
bm_build_viewmodel_rig(r_arm_mesh: str = None, l_arm_mesh: str = None, gun_body: str = None, gun_mag: str = None, r_wrist: list = None, l_wrist: list = None, r_shoulder: list = None, l_shoulder: list = None, rig_name: str = "ViewModel_Rig")
```

Auto-build FPS viewmodel rig: Root → R_Arm, L_Arm, Gun_Body → Gun_Mag. Bone-parents meshes.

## center

### `bm_center_of_mass`

```
bm_center_of_mass(name: str)
```

Geometric centroid of all verts (world space). For balance checks.

### `bm_center_to_origin`

```
bm_center_to_origin(name: str, axes: str = "xyz")
```

Translate so bbox center on selected axes = origin. axes: substring of 'xyz' (e.g. 'xy' = ground but keep Z).

## centroid

### `bm_centroid_of_points`

```
bm_centroid_of_points(points: list)
```

Centroid of a list of points.

## check

### `bm_check_symmetry`

```
bm_check_symmetry(name: str, axis: str = "x", tolerance: float = 0.001)
```

Verify mesh is symmetric across axis. Returns matched/unmatched + symmetry %.

### `bm_check_topology`

```
bm_check_topology(name: str)
```

Report tris/quads/ngons/non-manifold/loose stats.

## circle

### `bm_circle_arc`

```
bm_circle_arc(p1: list, p2: list, p3: list, segments: int = 16, name: str = "Arc")
```

Create curve arc passing through 3 points (p2 is the mid-point hint).

### `bm_circle_from_3pts`

```
bm_circle_from_3pts(p1: list, p2: list, p3: list)
```

Center + radius of circle through 3 coplanar points.

## clean

### `bm_clean_topology`

```
bm_clean_topology(name: str, merge_distance: float = 0.0001, quadrify: bool = True, recalc_normals: bool = True, remove_loose: bool = True)
```

One-shot cleanup: merge doubles + recalc normals + tris→quads + remove loose.

### `bm_clean_weights`

```
bm_clean_weights(mesh_name: str, threshold: float = 0.01)
```

Remove weights below threshold from all groups.

## clear

### `bm_clear_action_keys`

```
bm_clear_action_keys(action_name: str, frame_start: float = None, frame_end: float = None)
```

Remove keyframes from action. If frame range given, only within range.

### `bm_clear_bone_constraints`

```
bm_clear_bone_constraints(armature_name: str, bone_name: str)
```

Remove all constraints from bone.

### `bm_clear_constraints`

```
bm_clear_constraints(name: str)
```

Remove all constraints from object.

### `bm_clear_parent`

```
bm_clear_parent(name: str, keep_transform: bool = True)
```

Unparent object.

### `bm_clear_pose`

```
bm_clear_pose(name: str)
```

Reset all pose bones of an armature to rest (loc=0, rot=identity, scale=1).

## color

### `bm_color_faces`

```
bm_color_faces(name: str, face_indices: list, color: list, material_name: str = None)
```

Assign solid color material to specific face indices. color=[r,g,b,a] 0-1.

### `bm_color_faces_by_side`

```
bm_color_faces_by_side(name: str, color_map: dict, threshold: float = 0.7)
```

Identify + color faces by side in one call.
    color_map: {'TOP': [r,g,b,a], 'FRONT': [r,g,b,a], ...} — only listed sides get colored.
    Great for orientation debugging — give each side a distinct color to track which way is which.

## compare

### `bm_compare_meshes`

```
bm_compare_meshes(name1: str, name2: str)
```

Compare 2 meshes: vert/poly diff, dim diff, quality score diff.

## convert

### `bm_convert_format`

```
bm_convert_format(src_filepath: str, dst_filepath: str, src_format: str = None, dst_format: str = None)
```

Convert one 3D file to another format (import + export in one call).

## copy

### `bm_copy_action`

```
bm_copy_action(src: str, dst: str)
```

Duplicate action.

### `bm_copy_weights`

```
bm_copy_weights(mesh_name: str, src_group: str, dst_group: str)
```

Copy weights from src vgroup to dst vgroup.

## count

### `bm_count_vgroup_weights`

```
bm_count_vgroup_weights(mesh_name: str, threshold: float = 0.5)
```

Distribution of vertex weights per vgroup. Returns full/partial counts +
    total weight sum + zero-weight vert count. Debug weight painting issues.

## create

### `bm_create_action`

```
bm_create_action(name: str, fake_user: bool = True)
```

Create empty action (or return existing). Use bm_assign_action to attach to armature.

### `bm_create_collection`

```
bm_create_collection(name: str, parent_collection: str = None)
```

Create a collection (or return existing).

### `bm_create_control_bone`

```
bm_create_control_bone(armature_name: str, name: str, head: list, tail: list, parent: str = None, custom_shape_obj: str = None)
```

Add non-deforming control bone (used as IK target etc.). custom_shape_obj: name of object to use as bone shape.

### `bm_create_curve`

```
bm_create_curve(name: str, points: list, type: str = "BEZIER", cyclic: bool = False, resolution: int = 12)
```

Create curve from control points. type: BEZIER|NURBS|POLY.

### `bm_create_empty`

```
bm_create_empty(name: str, location: list = [0, 0, 0], display_type: str = "PLAIN_AXES", size: float = 0.1, parent: str = None, parent_bone: str = None)
```

Create empty marker. display_type: PLAIN_AXES|ARROWS|SPHERE|CUBE|CIRCLE|CONE.

### `bm_create_material`

```
bm_create_material(name: str, base_color: list = None, metallic: float = 0.0, roughness: float = 0.5, emission: list = None, emission_strength: float = 0.0)
```

Create Principled BSDF material. base_color=[r,g,b,a] 0-1.

## cursor

### `bm_cursor_to_object`

```
bm_cursor_to_object(name: str)
```

Snap cursor to object's origin point.

### `bm_cursor_to_origin`

Reset 3D cursor to world origin.

### `bm_cursor_to_selected`

Snap 3D cursor to center of currently-selected objects.

## curve

### `bm_curve_modifier`

```
bm_curve_modifier(name: str, curve_name: str, axis: str = "POS_X")
```

Deform mesh along curve via Curve modifier. axis: POS_X|NEG_X|POS_Y|NEG_Y|POS_Z|NEG_Z.

### `bm_curve_to_mesh`

```
bm_curve_to_mesh(name: str)
```

Convert curve object to mesh.

## cyclic

### `bm_cyclic_action`

```
bm_cyclic_action(action_name: str, mode: str = "REPEAT", before: str = "NONE")
```

Loop action forever via Cycles f-modifier. mode: REPEAT|REPEAT_OFFSET|MIRROR.

## decimate

### `bm_decimate_planar`

```
bm_decimate_planar(name: str, angle_limit_deg: float = 5)
```

Planar decimation — preserves curvature, collapses flat regions.

### `bm_decimate_unsubdivide`

```
bm_decimate_unsubdivide(name: str, iterations: int = 2)
```

Reverse subdivision.

## delete

### `bm_delete_action`

```
bm_delete_action(name: str)
```

Delete an action.

### `bm_delete_objects`

```
bm_delete_objects(names: list)
```

Bulk delete objects by name.

## dissolve

### `bm_dissolve_limited`

```
bm_dissolve_limited(name: str, angle_deg: float = 5)
```

Limited Dissolve — removes unnecessary geometry below angle threshold. Best topology cleanup tool.

## dist

### `bm_dist_point_to_line`

```
bm_dist_point_to_line(point: list, line_p1: list, line_p2: list)
```

Distance from point to line segment + closest point.

### `bm_dist_point_to_plane`

```
bm_dist_point_to_plane(point: list, plane_point: list, plane_normal: list)
```

Signed distance from point to infinite plane.

## distribute

### `bm_distribute_objects`

```
bm_distribute_objects(names: list, axis: str = "x", spacing: float = None, anchor: str = "CENTER")
```

Distribute objects evenly along axis. spacing=None => uses range/(n-1). anchor: MIN|MAX|CENTER.

## dump

### `bm_dump_objects`

```
bm_dump_objects(types: list = None)
```

Dump ALL objects in one call: name, type, loc, rot, scale, parent, bbox local + world, vgroups, modifiers.
    Replaces multiple get_object_info calls. types: optional filter like ['MESH','ARMATURE'].

## edge

### `bm_edge_slide`

```
bm_edge_slide(name: str, edge_indices: list, factor: float = 0.5)
```

Slide edge loop along adjacent edges. factor: -1..1.

### `bm_edge_split`

```
bm_edge_split(name: str, angle_deg: float = 30, edge_indices: list = None)
```

Split edges by angle threshold (no edge_indices) or by explicit indices.

## edit

### `bm_edit_bone`

```
bm_edit_bone(armature_name: str, bone_name: str, head: list = None, tail: list = None, parent: str = None, connect: bool = None)
```

Edit existing bone (head/tail/parent/connect). Any param None = unchanged.

## emboss

### `bm_emboss_text`

```
bm_emboss_text(target_name: str, text: str, location: list, size: float = 0.05, depth: float = 0.01, axis: str = "z", operation: str = "DIFFERENCE")
```

Emboss/engrave text into target via Boolean. operation: DIFFERENCE (engrave) | UNION (emboss).

## equalize

### `bm_equalize_edges`

```
bm_equalize_edges(name: str, iterations: int = 3, factor: float = 0.5)
```

Relax verts to make edge lengths more uniform.

## export

### `bm_export_fbx`

```
bm_export_fbx(filepath: str, selection_only: bool = False, object_names: list = None, axis_up: str = "Y", axis_forward: str = "-Z", bake_anim: bool = True, apply_scale: bool = True)
```

Export FBX with Roblox-compatible defaults (Y-up, -Z forward, bake anim).

### `bm_export_format`

```
bm_export_format(filepath: str, format: str = None, selection_only: bool = False, object_names: list = None, axis_up: str = "Y", axis_forward: str = "-Z")
```

Universal exporter. format inferred from extension if None. Supports: fbx, obj, gltf, glb, dae, stl, ply, x3d, usd, usda, usdc, abc.

### `bm_export_weights`

```
bm_export_weights(mesh_name: str, filepath: str)
```

Export vertex group weights to JSON.

## extrude

### `bm_extrude_along_normal`

```
bm_extrude_along_normal(name: str, face_indices: list, distance: float)
```

Extrude specific faces along their normals by distance.

## fill

### `bm_fill_face`

```
bm_fill_face(name: str, vert_indices: list)
```

Fill a polygon from given verts.

## find

### `bm_find_by_property`

```
bm_find_by_property(type: str = None, has_material: str = None, has_vgroup: str = None, has_modifier: str = None, has_parent: bool = None)
```

Filter objects by properties.

### `bm_find_closest_vertex`

```
bm_find_closest_vertex(name: str, point: list)
```

Find index + distance + position of vertex closest to given world point.

### `bm_find_objects`

```
bm_find_objects(pattern: str, type: str = None)
```

Find objects by name fnmatch pattern (e.g. 'Gun_*', '*Arm*'). Optionally filter by type.

## flatten

### `bm_flatten_verts`

```
bm_flatten_verts(name: str, axis: str = "z", value: float = 0.0, vert_filter: dict = None)
```

Flatten filtered verts to a plane (set axis coord = value).

## force

### `bm_force_mode_set`

```
bm_force_mode_set(name: str, mode: str)
```

Robust object-mode change with VIEW_3D area override built-in.
    Replaces brittle bm_set_mode that fails with 'context is incorrect'.
    mode: OBJECT|EDIT|POSE|WEIGHT_PAINT|SCULPT|VERTEX_PAINT|TEXTURE_PAINT.

## get

### `bm_get_bbox`

```
bm_get_bbox(name: str, space: str = "world")
```

Single object bbox + dims. space: world|local.

### `bm_get_bone_world`

```
bm_get_bone_world(armature_name: str, bone_name: str)
```

Get world-space head + tail + length for a bone (current pose).

### `bm_get_evaluated_vertex`

```
bm_get_evaluated_vertex(name: str, index: int, space: str = "world")
```

Vertex position AFTER all modifiers + pose deform applied (depsgraph eval).
    Use to verify Armature modifier actually deforms the mesh. space: world|local.

### `bm_get_transform`

```
bm_get_transform(name: str)
```

Single object TRS (loc/rot_deg/scale/parent) — compact.

### `bm_get_vertex`

```
bm_get_vertex(name: str, index: int, space: str = "world")
```

Get vertex position by index. space: world|local.

### `bm_get_weights_at_vert`

```
bm_get_weights_at_vert(mesh_name: str, vert_index: int)
```

Debug: list all vertex groups + weights for a single vert.

## grid

### `bm_grid_fill`

```
bm_grid_fill(name: str, edge_indices: list = None, span: int = 2)
```

Grid-fill closed edge loop.

## identify

### `bm_identify_faces`

```
bm_identify_faces(name: str, threshold: float = 0.7, use_world: bool = True, assign_all: bool = False)
```

Classify mesh polygons by normal direction. Returns {TOP, BOTTOM, FRONT, BACK, LEFT, RIGHT, UNKNOWN: [face_indices]}.
    Convention (world space): +X=RIGHT, -X=LEFT, +Y=BACK, -Y=FRONT, +Z=TOP, -Z=BOTTOM.
    threshold: dot-product cutoff (0.7 ~ 45° tolerance). Faces too tilted go to UNKNOWN.
    assign_all: when True, sub-threshold faces still claim their best-matching side (no UNKNOWN).

## import

### `bm_import_format`

```
bm_import_format(filepath: str, format: str = None)
```

Universal importer. Returns list of new object names.

### `bm_import_weights`

```
bm_import_weights(mesh_name: str, filepath: str)
```

Restore weights from JSON.

## inset

### `bm_inset_faces`

```
bm_inset_faces(name: str, face_indices: list, thickness: float = 0.02, depth: float = 0.0, individual: bool = False)
```

Inset faces. Critical for adding edge loops around features without breaking topology.

## inspect

### `bm_inspect_animation`

```
bm_inspect_animation(armature_name: str = None, object_name: str = None)
```

Animation introspection: pose bone rotation_mode + current rotation values,
    action name + fcurve count + slots/layers (Blender 4.x action API).

### `bm_inspect_modifier`

```
bm_inspect_modifier(name: str, modifier_name: str = None)
```

Detailed modifier dump — use_vertex_groups, use_bone_envelopes, object ref,
    levels, segments, etc. Set modifier_name=None for all modifiers on the object.

## intersect

### `bm_intersect_line_plane`

```
bm_intersect_line_plane(line_p1: list, line_p2: list, plane_point: list, plane_normal: list)
```

Intersection point of line and plane.

## isolate

### `bm_isolate_bone_weights`

```
bm_isolate_bone_weights(mesh_name: str, group_name: str)
```

Visually isolate one bone's weights.

## join

### `bm_join_objects`

```
bm_join_objects(names: list, into: str)
```

Join meshes into one. 'into' must be in 'names'.

## keyframe

### `bm_keyframe_bone`

```
bm_keyframe_bone(armature_name: str, bone_name: str, frame: int, location: list = None, rotation_quaternion: list = None, scale = None)
```

Insert pose-bone keyframe. Creates action if armature has none yet.

### `bm_keyframe_material_color`

```
bm_keyframe_material_color(material_name: str, color: list, frame: int)
```

Keyframe Principled BSDF base color. color: [r,g,b,a] 0-1.

### `bm_keyframe_material_emission`

```
bm_keyframe_material_emission(material_name: str, strength: float, frame: int)
```

Keyframe Principled BSDF emission strength (for light on/off animations).

### `bm_keyframe_pose_dict`

```
bm_keyframe_pose_dict(armature_name: str, pose_dict: dict, frame: int)
```

Keyframe multiple bones at once. pose_dict: {bone_name: {location?, rotation_quaternion?, rotation_euler?, scale?}}.

### `bm_keyframe_property`

```
bm_keyframe_property(object_name: str, data_path: str, frame: int, value, index: int = -1)
```

Insert keyframe on ANY property. data_path examples: 'location', 'hide_render', 'rotation_euler'.

## label

### `bm_label_faces_by_side`

```
bm_label_faces_by_side(name: str, texture_dir: str, threshold: float = 0.7, sides: list = None, use_world: bool = False, mirror_lr: bool = False, mirror_fb: bool = False, mirror_tb: bool = False, assign_all: bool = True)
```

Apply per-side image-texture materials to faces.
    Reads <SIDE>.png from texture_dir. UVs span the side cluster as one image,
    aspect preserved, overflow filled by EXTEND.

## level

### `bm_level_to_ground`

```
bm_level_to_ground(name: str, axis: str = "z", value: float = 0.0)
```

Translate so object's min along axis lands at value (e.g. z=0 = ground).

## list

### `bm_list_actions`

List all actions: name, fake_user, frame_range.

### `bm_list_bones`

```
bm_list_bones(armature_name: str)
```

List all bones: name, parent, head_local, tail_local, length, use_connect.

### `bm_list_collections`

List all collections + their objects + children.

### `bm_list_modifiers`

```
bm_list_modifiers(name: str)
```

List object's modifiers.

### `bm_list_workspaces`

List workspaces + current.

## local

### `bm_local_to_world`

```
bm_local_to_world(name: str, point: list)
```

Convert object-local point to world.

## loop

### `bm_loop_cut`

```
bm_loop_cut(name: str, edge_index: int, cuts: int = 1)
```

Add loop cut(s) running through an edge.

## make

### `bm_make_lod_set`

```
bm_make_lod_set(name: str, ratios: list = None, filepath_prefix: str = None)
```

Generate LOD chain via duplicate + decimate. Default ratios [1.0, 0.5, 0.25, 0.1]. Optionally exports each as FBX.

### `bm_make_orthogonal_corner`

```
bm_make_orthogonal_corner(name: str, vert_index: int)
```

Snap all edges touching a vert to nearest cardinal axis — produces perfect 90° corners.

## mark

### `bm_mark_seam`

```
bm_mark_seam(name: str, edge_indices: list, clear: bool = False)
```

Mark/clear UV seams on edges.

### `bm_mark_sharp`

```
bm_mark_sharp(name: str, edge_indices: list, clear: bool = False)
```

Mark/clear sharp edges (for edge split / auto-smooth).

## measure

### `bm_measure_edge_length`

```
bm_measure_edge_length(name: str, edge_index: int, space: str = "world")
```

Measure edge length.

## merge

### `bm_merge_verts`

```
bm_merge_verts(name: str, vert_indices: list, mode: str = "CENTER")
```

Merge verts. mode: CENTER|FIRST|LAST|COLLAPSE.

## mesh

### `bm_mesh_separate`

```
bm_mesh_separate(name: str, mode: str = "LOOSE")
```

Separate mesh. mode: LOOSE|SELECTED|MATERIAL. Returns new object names.

### `bm_mesh_thickness_stats`

```
bm_mesh_thickness_stats(name: str, samples: int = 100)
```

Measure wall thickness via raycasts. Returns min/max/avg — catches parts too thin.

## minimize

### `bm_minimize_poles`

```
bm_minimize_poles(name: str, max_iterations: int = 3)
```

Iteratively dissolve high-poles (fan triangulation cleanup).

## mirror

### `bm_mirror_bones`

```
bm_mirror_bones(armature_name: str, src_suffix: str = ".l", dst_suffix: str = ".r")
```

Mirror .l bones to .r (or vice-versa) via armature.symmetrize.

### `bm_mirror_object`

```
bm_mirror_object(name: str, axis: str = "x")
```

Mirror object across axis plane (negates scale on axis).

### `bm_mirror_verts`

```
bm_mirror_verts(name: str, axis: str, vert_filter: dict = None, plane_pos: float = 0.0)
```

Mirror vertex subset across plane (axis='x'|'y'|'z') at plane_pos.

### `bm_mirror_weights`

```
bm_mirror_weights(mesh_name: str, axis: str = "X")
```

Mirror vertex group weights across axis.

## misc

### `bm_boolean`

```
bm_boolean(name: str, target: str, operation: str = "DIFFERENCE", solver: str = "EXACT", apply: bool = True)
```

Boolean op between meshes. operation: DIFFERENCE|UNION|INTERSECT. solver: EXACT|FAST.

### `bm_decimate`

```
bm_decimate(name: str, ratio: float = 0.5)
```

Reduce poly count. Beware: can introduce bad triangulation.

### `bm_distance`

```
bm_distance(p1: list, p2: list)
```

Distance + delta between two world points.

### `bm_duplicate`

```
bm_duplicate(name: str, new_name: str = None, link: bool = False)
```

Duplicate object. link=True for linked (instance) copy.

### `bm_hide`

```
bm_hide(name: str, hide_viewport: bool = True, hide_render: bool = False)
```

Hide/unhide object.

### `bm_lerp`

```
bm_lerp(p1: list, p2: list, t: float)
```

Linear interpolation between two points.

### `bm_list`

```
bm_list(types: list = None)
```

Compact list of objects: name, type, world dims only. ~10x smaller than bm_dump_objects.

### `bm_ping`

Instant health check. Returns scene name + frame.

### `bm_quadrify`

```
bm_quadrify(name: str, face_threshold_deg: float = 40, shape_threshold_deg: float = 40)
```

Convert tris to quads.

### `bm_remesh`

```
bm_remesh(name: str, mode: str = "VOXEL", voxel_size: float = 0.05, octree_depth: int = 5, apply: bool = True)
```

Auto-remesh. mode: VOXEL (most reliable)|QUAD|SHARP|SMOOTH|BLOCKS.

### `bm_rename`

```
bm_rename(old: str, new: str)
```

Rename object.

### `bm_rotate`

```
bm_rotate(name: str, axis: str = "z", angle_deg: float = 0, pivot = "ORIGIN")
```

Rotate object around axis by angle_deg. pivot: ORIGIN|MEDIAN|CENTROID|[x,y,z].

### `bm_scale`

```
bm_scale(name: str, factor)
```

Scale object. factor = float (uniform) or [x,y,z].

### `bm_select`

```
bm_select(names: list, deselect_others: bool = True, active: str = None)
```

Select objects by name. Optionally set active.

### `bm_subdivide`

```
bm_subdivide(name: str, cuts: int = 1)
```

Subdivide entire mesh.

### `bm_symmetrize`

```
bm_symmetrize(name: str, direction: str = "POSITIVE_X", threshold: float = 0.0001)
```

Symmetrize mesh. direction: POSITIVE_X|NEGATIVE_X|POSITIVE_Y|NEGATIVE_Y|POSITIVE_Z|NEGATIVE_Z (or +X/-X shorthand).

### `bm_translate`

```
bm_translate(name: str, delta: list)
```

Translate object by delta=[x,y,z].

### `bm_triangulate`

```
bm_triangulate(name: str)
```

Convert quads/ngons to triangles.

## normal

### `bm_normal_from_3pts`

```
bm_normal_from_3pts(p1: list, p2: list, p3: list)
```

Compute plane normal from 3 points.

## normalize

### `bm_normalize_vertex_groups`

```
bm_normalize_vertex_groups(mesh_name: str, lock_active: bool = False)
```

Normalize all vertex group weights to sum to 1 per vert.

## object

### `bm_object_to_cursor`

```
bm_object_to_cursor(name: str)
```

Move object so its origin lands at cursor.

## offset

### `bm_offset_curve`

```
bm_offset_curve(name: str, distance: float = 0.05, axis: str = "z", new_name: str = None)
```

Create parallel curve offset along axis.

## optimize

### `bm_optimize_for_polycount`

```
bm_optimize_for_polycount(name: str, target_faces: int, preserve_uv: bool = True, prefer_quads: bool = True)
```

Smart polycount reduction. Tries QuadriFlow first, falls back to Decimate.

## paint

### `bm_paint_weight_to_bone`

```
bm_paint_weight_to_bone(mesh_name: str, group_name: str, vert_indices: list, weight: float = 1.0, mode: str = "REPLACE")
```

Paint weight to vertex group. mode: REPLACE|ADD|SUBTRACT|MULTIPLY.

## parent

### `bm_parent_to_bone`

```
bm_parent_to_bone(child_name: str, armature_name: str, bone_name: str, mode: str = "BONE_RELATIVE")
```

Bone-parent child mesh to armature bone. mode: BONE_RELATIVE (preserves world) | BONE.

## pca

### `bm_pca_align`

```
bm_pca_align(name: str, target_axis = "y", vert_filter: dict = None)
```

PCA-align principal axis of vertex subset to target world axis. target_axis: 'x'|'y'|'z' or [vec].
    USE vert_filter to scope to ONE arm/object — never run on multi-loose-part mesh without filter.

## perfect

### `bm_perfect_box`

```
bm_perfect_box(name: str, mins: list, maxs: list, location: list = None)
```

Create perfect axis-aligned box from exact mins/maxs (object-local). 8 verts, 6 faces, no fp noise.

## planar

### `bm_planar_faces`

```
bm_planar_faces(name: str, threshold_deg: float = 2)
```

Flatten near-coplanar faces.

## pole

### `bm_pole_count`

```
bm_pole_count(name: str)
```

Histogram of vert edge-degrees + warnings. Good topology = mostly 4-pole verts.

## pose

### `bm_pose_bone_xform`

```
bm_pose_bone_xform(armature_name: str, bone_name: str, location: list = None, rotation_quaternion: list = None, rotation_euler: list = None, scale = None)
```

Set pose-bone TRS WITHOUT keyframing. Useful for rest-pose tweaks.

## proportional

### `bm_proportional_translate`

```
bm_proportional_translate(name: str, seed_vert_index: int, delta: list, falloff: str = "SMOOTH", radius: float = 1.0)
```

Translate seed vert + propagate with falloff. falloff: SMOOTH|SPHERE|ROOT|SHARP|LINEAR|CONSTANT.

## punch

### `bm_punch_pattern`

```
bm_punch_pattern(target_name: str, count: int = 5, spacing: float = 0.05, slot_size: list = None, start_location: list = None, axis: str = "x", operation: str = "DIFFERENCE")
```

Punch repeated holes/slots through target (e.g. cooling slot pattern on MP40 receiver).

## push

### `bm_push_to_nla`

```
bm_push_to_nla(armature_name: str, action_name: str = None, strip_name: str = None)
```

Push armature's active (or named) action onto a new NLA strip.

## quadriflow

### `bm_quadriflow_remesh`

```
bm_quadriflow_remesh(name: str, target_faces: int = 5000, use_paint_symmetry: bool = False, use_preserve_sharp: bool = True, use_preserve_boundary: bool = True, smooth_normals: bool = True)
```

QuadriFlow (built-in Blender) — best automatic quad remesher.

## quick

### `bm_quick_fps_pose`

```
bm_quick_fps_pose(armature_name: str, pose: str = "AIM")
```

Apply preset FPS pose. pose: AIM|IDLE|RELOAD_PEAK|FIRE_RECOIL.

## read

### `bm_read_console`

```
bm_read_console(lines: int = 50, filter: str = None, stream: str = None, since: str = None, clear: bool = False, max_line: int = 200, max_chars: int = 6000, dedupe: bool = True, mode: str = "compact", include_ts: bool = False)
```

Token-friendly console reader (Blender stdout/stderr ring buffer).

## recalc

### `bm_recalc_normals`

```
bm_recalc_normals(name: str, inside: bool = False)
```

Recalculate normals consistently. inside=True flips outward.

## reload

### `bm_reload_addon`

```
bm_reload_addon(addon_module: str = "blender_mcp_addon")
```

Hot-reload an addon (disable + re-enable). After editing source files,
    call this instead of toggling in Preferences manually. For blender_mcp_addon
    itself, client must reconnect ~1s after this returns (socket restarts).

## remove

### `bm_remove_doubles`

```
bm_remove_doubles(name: str, distance: float = 0.0001)
```

Merge vertices within distance.

### `bm_remove_from_collection`

```
bm_remove_from_collection(object_names: list, collection_name: str)
```

Remove objects from a collection.

### `bm_remove_loose_geometry`

```
bm_remove_loose_geometry(name: str)
```

Delete unconnected verts/edges/faces.

### `bm_remove_modifier`

```
bm_remove_modifier(name: str, modifier_name: str)
```

Remove modifier without applying.

### `bm_remove_zero_weights`

```
bm_remove_zero_weights(mesh_name: str)
```

Remove all zero-weight entries from every group.

## render

### `bm_render_image`

```
bm_render_image(filepath: str, frame: int = None, resolution: list = None)
```

Render single frame to file. resolution=[W,H] optional.

## resize

### `bm_resize_texture`

```
bm_resize_texture(image_name: str, width: int, height: int, save_path: str = None)
```

Resize image in Blender. Optionally save to disk.

## rotate

### `bm_rotate_verts`

```
bm_rotate_verts(name: str, axis: list, angle_deg: float, vert_filter: dict = None, pivot = "CENTROID")
```

Rotate vertex subset around axis. axis=[x,y,z]. pivot: CENTROID|ORIGIN|[x,y,z].
    vert_filter: {'all':true} | {'x_lt':0} | {'x_gt':0} | {'vgroup':'name'} | {'indices':[..]}.

## round

### `bm_round_vert_positions`

```
bm_round_vert_positions(name: str, decimals: int = 3, vert_filter: dict = None)
```

Round vert coords to N decimals — kills floating-point noise.

## save

### `bm_save_blend`

```
bm_save_blend(filepath: str)
```

Save .blend file to filepath.

## score

### `bm_score_mesh_quality`

```
bm_score_mesh_quality(name: str)
```

Comprehensive mesh quality score 0-100 + warnings + symmetry.

## screenshot

### `bm_screenshot_views`

```
bm_screenshot_views(filepath_prefix: str, views: list = None, max_size: int = 800)
```

Take multiple viewport screenshots. views default ['TOP','FRONT','RIGHT']. Returns list of saved paths.

## select

### `bm_select_all`

```
bm_select_all(type: str = None)
```

Select all objects (or all of a type).

### `bm_select_by_material`

```
bm_select_by_material(name: str, material_name: str)
```

Select all faces with given material assigned.

### `bm_select_edge_loop`

```
bm_select_edge_loop(name: str, edge_index: int)
```

Select edge loop from seed edge (Alt+click equivalent).

### `bm_select_edge_ring`

```
bm_select_edge_ring(name: str, edge_index: int)
```

Select edge ring (Ctrl+Alt+click equivalent).

### `bm_select_high_poles`

```
bm_select_high_poles(name: str, min_edges: int = 6)
```

Select verts with too many edges (fan-pole problems).

### `bm_select_inside_bbox`

```
bm_select_inside_bbox(name: str, bbox_min: list, bbox_max: list, space: str = "world")
```

Select verts inside axis-aligned bbox.

### `bm_select_linked`

```
bm_select_linked(name: str, vert_index: int = None)
```

Select all verts connected to seed vert (or current selection).

### `bm_select_ngons`

```
bm_select_ngons(name: str)
```

Select all faces with 5+ verts.

### `bm_select_non_manifold`

```
bm_select_non_manifold(name: str)
```

Select non-manifold edges (holes, T-junctions).

### `bm_select_pattern`

```
bm_select_pattern(pattern: str, deselect_others: bool = True, type: str = None)
```

Select objects matching name pattern.

### `bm_select_stretched_tris`

```
bm_select_stretched_tris(name: str, ratio: float = 3.0)
```

Select sliver triangles (longest/shortest edge ratio above threshold).

### `bm_select_tris`

```
bm_select_tris(name: str)
```

Select all triangle faces.

## separate

### `bm_separate_by_bbox`

```
bm_separate_by_bbox(name: str, bbox_min: list, bbox_max: list, new_name: str = None, space: str = "world")
```

Separate verts inside axis-aligned bbox into new object (e.g. door from car by spatial selection).

### `bm_separate_by_material`

```
bm_separate_by_material(name: str)
```

Separate mesh into one object per material slot.

### `bm_separate_by_normal`

```
bm_separate_by_normal(name: str, axis: str, threshold: float = 0.7, new_name: str = None)
```

Separate faces with normal aligned to axis. axis: 'x','y','z','-x','-y','-z'.

### `bm_separate_by_vgroup`

```
bm_separate_by_vgroup(name: str, vgroup_name: str, new_name: str = None)
```

Separate verts in a vertex group into a new object (e.g. mag from gun).

## set

### `bm_set_active`

```
bm_set_active(name: str)
```

Set active object.

### `bm_set_active_vgroup`

```
bm_set_active_vgroup(mesh_name: str, group_name: str)
```

Set active vertex group on mesh — controls which weights show in WEIGHT_PAINT viewport.

### `bm_set_area_type`

```
bm_set_area_type(area_index: int, type: str)
```

Change area type. type: VIEW_3D|IMAGE_EDITOR|OUTLINER|PROPERTIES|TEXT_EDITOR|NODE_EDITOR|FILE_BROWSER|DOPESHEET_EDITOR|GRAPH_EDITOR|NLA_EDITOR|TIMELINE.

### `bm_set_armature_mode`

```
bm_set_armature_mode(name: str, mode: str = "POSE")
```

Toggle armature pose_position: REST (bind pose) or POSE (anim driven).

### `bm_set_bone_display`

```
bm_set_bone_display(armature_name: str, bone_name: str, shape: str = "OCTAHEDRAL")
```

Set armature display type. shape: OCTAHEDRAL|STICK|BBONE|ENVELOPE|WIRE.

### `bm_set_bone_roll`

```
bm_set_bone_roll(armature_name: str, bone_name: str, angle_deg: float)
```

Set bone roll angle (rotation around bone's Y axis).

### `bm_set_camera`

```
bm_set_camera(name: str = "Camera", location: list = None, target: list = None, lens: float = 35, track_to: bool = True)
```

Position camera. Creates a Camera if missing. If target=[x,y,z] given, adds TRACK_TO constraint to aim at it.

### `bm_set_cursor`

```
bm_set_cursor(location: list = [0, 0, 0])
```

Set 3D cursor location.

### `bm_set_curve_bevel`

```
bm_set_curve_bevel(name: str, depth: float = 0.05, resolution: int = 4, bevel_object: str = None)
```

Add bevel to curve (thickness). bevel_object: name of cross-section curve.

### `bm_set_edge_bevel_weight`

```
bm_set_edge_bevel_weight(name: str, edge_indices: list, weight: float = 1.0)
```

Set bevel weight on edges (for Bevel modifier with Weight limit).

### `bm_set_edge_crease`

```
bm_set_edge_crease(name: str, edge_indices: list, weight: float = 1.0)
```

Set SubSurf crease weight on edges (0=smooth, 1=sharp).

### `bm_set_edge_position`

```
bm_set_edge_position(name: str, edge_index: int, head_pos: list = None, tail_pos: list = None, space: str = "world")
```

Set exact positions of edge's two vertices.

### `bm_set_frame`

```
bm_set_frame(frame: int, start: int = None, end: int = None, fps: int = None)
```

Set scene frame + optional frame range / fps.

### `bm_set_gravity`

```
bm_set_gravity(gravity: list = None, use_gravity: bool = True)
```

Set scene gravity vector.

### `bm_set_keyframe_interp`

```
bm_set_keyframe_interp(action_name: str, mode: str = "LINEAR")
```

Set interpolation mode for ALL keyframes in action. mode: LINEAR|BEZIER|CONSTANT|BACK|BOUNCE|ELASTIC.

### `bm_set_mode`

```
bm_set_mode(name: str, mode: str = "OBJECT")
```

Set object mode. Options: OBJECT|EDIT|POSE|SCULPT|WEIGHT_PAINT|VERTEX_PAINT|TEXTURE_PAINT.

### `bm_set_origin`

```
bm_set_origin(name: str, type: str = "ORIGIN_GEOMETRY", point: list = None)
```

Set object origin. type: ORIGIN_GEOMETRY | ORIGIN_CURSOR | ORIGIN_CENTER_OF_MASS.
    For ORIGIN_CURSOR, point=[x,y,z] sets cursor before.

### `bm_set_origin_to_face`

```
bm_set_origin_to_face(name: str, face_index: int)
```

Set object origin to face's center (for assembly pivot).

### `bm_set_origin_to_vert`

```
bm_set_origin_to_vert(name: str, vert_index: int)
```

Set object origin to vertex position.

### `bm_set_parent`

```
bm_set_parent(child_name: str, parent_name: str, type: str = "OBJECT", bone: str = "", keep_transform: bool = True)
```

Parent child to parent. type: OBJECT|BONE|BONE_RELATIVE.

### `bm_set_pose_from_dict`

```
bm_set_pose_from_dict(armature_name: str, pose_dict: dict)
```

Set multiple bone poses WITHOUT keyframing. Same dict shape as bm_keyframe_pose_dict.

### `bm_set_render`

```
bm_set_render(engine: str = None, samples: int = None, resolution: list = None, percentage: int = None, view_transform: str = None)
```

Configure render settings. engine: BLENDER_EEVEE_NEXT|CYCLES. view_transform: Standard|Filmic|AgX.

### `bm_set_shading_smooth`

```
bm_set_shading_smooth(name: str, smooth: bool = True, auto_smooth_angle: float = None)
```

Shade smooth or flat. auto_smooth_angle in degrees (optional).

### `bm_set_transform`

```
bm_set_transform(name: str, location: list = None, rotation_euler: list = None, rotation_quaternion: list = None, scale = None)
```

Set object transform. Any None field = unchanged. scale can be float (uniform) or [x,y,z].

### `bm_set_vert_bevel_weight`

```
bm_set_vert_bevel_weight(name: str, vert_indices: list, weight: float = 1.0)
```

Set bevel weight on vertices.

### `bm_set_vertex`

```
bm_set_vertex(name: str, index: int, position: list, space: str = "world")
```

Set vertex position by index.

### `bm_set_view`

```
bm_set_view(type: str = "PERSP", view_all: bool = True)
```

Switch viewport. type: TOP|BOTTOM|FRONT|BACK|LEFT|RIGHT|CAMERA|PERSP.

### `bm_set_workspace`

```
bm_set_workspace(name: str)
```

Switch Blender workspace (Layout/Modeling/Sculpting/UV Editing/Animation/...).

## setup

### `bm_setup_arm_ik`

```
bm_setup_arm_ik(armature_name: str, shoulder_bone: str, elbow_bone: str, hand_bone: str, hand_target_name: str = None, pole_target_name: str = None, pole_distance: float = 0.3)
```

One-call arm IK: auto-create hand target + elbow pole + IK constraint.

### `bm_setup_car_template`

```
bm_setup_car_template(name: str = "Car", front_image: str = None, side_image: str = None, top_image: str = None, length: float = 4.7, width: float = 2.0, height: float = 1.45)
```

One-call car modeling setup: blueprint refs + half-cube + Mirror X + SubSurf level 2. Default = Tesla Model 3 dims.

### `bm_setup_ik`

```
bm_setup_ik(armature_name: str, end_bone: str, target_empty: str = None, pole_target: str = None, chain_count: int = 2, pole_angle: float = -90, weight_position: float = 1.0, weight_rotation: float = 0.0)
```

Add IK constraint to end_bone. target_empty/pole_target are object names.

### `bm_setup_leg_ik`

```
bm_setup_leg_ik(armature_name: str, hip_bone: str, knee_bone: str, foot_bone: str, foot_target_name: str = None, pole_target_name: str = None, pole_distance: float = 0.3)
```

One-call leg IK: auto-create foot target + knee pole + IK constraint.

## shrinkwrap

### `bm_shrinkwrap_to`

```
bm_shrinkwrap_to(name: str, target_name: str, wrap_method: str = "NEAREST_SURFACEPOINT", offset: float = 0.0, apply: bool = False)
```

Project mesh onto target via Shrinkwrap. Great for retopo on high-poly references.

## slerp

### `bm_slerp_quat`

```
bm_slerp_quat(q1: list, q2: list, t: float)
```

Spherical lerp between two quaternions (smooth rotation blend).

## smart

### `bm_smart_bevel`

```
bm_smart_bevel(name: str, edge_indices: list, width: float = 0.005, segments: int = 2, crease_for_subsurf: bool = True)
```

Bevel + auto-crease for SubSurf-friendly hard surface (HardOps-style).

## smooth

### `bm_smooth_verts`

```
bm_smooth_verts(name: str, vert_filter: dict = None, factor: float = 0.5, iterations: int = 1)
```

Laplacian-smooth filtered verts. vert_filter same as rotate_verts.

### `bm_smooth_weights`

```
bm_smooth_weights(mesh_name: str, group_name: str = None, iterations: int = 3, factor: float = 0.5)
```

Smooth vertex group weights via neighbor averaging.

## snap

### `bm_snap_to_grid`

```
bm_snap_to_grid(name: str, grid_size: float = 0.1, snap_translation: bool = True, snap_rotation: bool = False)
```

Snap object loc to nearest grid_size step. snap_rotation also rounds rotation to 90°.

## split

### `bm_split_area`

```
bm_split_area(direction: str = "VERTICAL", factor: float = 0.5)
```

Split active 3D viewport. direction: VERTICAL|HORIZONTAL.

## text

### `bm_text_3d`

```
bm_text_3d(text: str, name: str = None, location: list = None, size: float = 0.1, extrude: float = 0.02, align_x: str = "CENTER", align_y: str = "CENTER")
```

Create 3D text object. extrude = depth (thickness).

## transfer

### `bm_transfer_weights`

```
bm_transfer_weights(src_mesh_name: str, dst_mesh_name: str)
```

Transfer all vertex weights between meshes (proximity-based).

## translate

### `bm_translate_verts`

```
bm_translate_verts(name: str, delta: list, vert_filter: dict = None)
```

Translate vertex subset by delta=[x,y,z].

## uv

### `bm_uv_unwrap`

```
bm_uv_unwrap(name: str, method: str = "SMART", angle: float = 66, island_margin: float = 0.02)
```

UV unwrap. method: SMART|UNWRAP|CUBE|SPHERE|CYLINDER|PROJECT_FROM_VIEW.

## view

### `bm_view_camera`

Switch viewport to active camera view.

## warn

### `bm_warn_topology`

```
bm_warn_topology(name: str)
```

COMPREHENSIVE topology audit. Returns warnings + topology_score 0-100. Call after any mesh op to catch junk.

## weight

### `bm_weight_by_axis_split`

```
bm_weight_by_axis_split(mesh_name: str, axis: str, boundary: float, blend_width: float, group_neg: str, group_pos: str, clear_others: bool = True, space: str = "local")
```

Split mesh weights between two bones along an axis with smooth linear blend.

### `bm_weight_by_plane_split`

```
bm_weight_by_plane_split(mesh_name: str, plane_point: list, plane_normal: list, blend_width: float, group_neg: str, group_pos: str, clear_others: bool = True, space: str = "local")
```

Split weights by signed distance to an arbitrary plane. For diagonal-cut
    joints (e.g. Roblox-style 45° elbow). plane_point: [x,y,z] point on plane
    (e.g. elbow position). plane_normal: [nx,ny,nz] (auto-normalized). blend_width:
    half-width of transition. group_neg/pos: vgroup names for neg/pos sides.

### `bm_weight_falloff_from_point`

```
bm_weight_falloff_from_point(mesh_name: str, group_name: str, center_point: list, radius: float, falloff: str = "SMOOTH")
```

Radial falloff weight assignment.

### `bm_weight_gradient`

```
bm_weight_gradient(mesh_name: str, group_name: str, vert1_index: int, vert2_index: int, weight1: float = 1.0, weight2: float = 0.0)
```

Linear gradient between two verts.

## world

### `bm_world_to_local`

```
bm_world_to_local(name: str, point: list)
```

Convert world point to object-local.

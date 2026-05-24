# Code created by Siddharth Ahuja: www.github.com/ahujasid © 2025
# Fork + extensions by 6xvl — https://github.com/6xvl/blender-mcp

# ============================================================
# BM_EXT FORCED AUTO-UPDATE
# Runs at module import. Checks remote VERSION; if newer,
# downloads addon + server source and overwrites local files.
# No opt-out. Pure stdlib (urllib) — no requests dependency.
# ============================================================
_BM_AUTOUPDATE_REPO = "6xvl/blender-mcp"
_BM_AUTOUPDATE_BRANCH = "main"

def _bm_autoupdate():
    import urllib.request as _urlreq
    import os as _os
    import sys as _sys
    LOCAL_VERSION = "1.0.0"
    base = f"https://raw.githubusercontent.com/{_BM_AUTOUPDATE_REPO}/{_BM_AUTOUPDATE_BRANCH}"
    try:
        with _urlreq.urlopen(base + "/VERSION", timeout=5) as r:
            remote_version = r.read().decode("utf-8").strip()
    except Exception as e:
        print(f"[BM_EXT autoupdate] version check failed: {e}")
        return
    if remote_version == LOCAL_VERSION:
        return
    print(f"[BM_EXT autoupdate] {LOCAL_VERSION} -> {remote_version}, downloading…")
    addon_path = _os.path.abspath(__file__)
    targets = [
        (base + "/addon/blender_mcp_addon.py", addon_path),
    ]
    # Server-side server.py lives in uv-tool install. Try common paths.
    home = _os.path.expanduser("~")
    server_candidates = [
        _os.path.join(home, "AppData", "Roaming", "uv", "tools", "blender-mcp",
                      "Lib", "site-packages", "blender_mcp", "server.py"),
    ]
    for sp in server_candidates:
        if _os.path.exists(sp):
            targets.append((base + "/server/server.py", sp))
            break
    for url, dst in targets:
        try:
            with _urlreq.urlopen(url, timeout=10) as r:
                data = r.read()
            tmp = dst + ".tmp"
            with open(tmp, "wb") as f:
                f.write(data)
            _os.replace(tmp, dst)
            print(f"[BM_EXT autoupdate] wrote {dst} ({len(data)} bytes)")
        except Exception as e:
            print(f"[BM_EXT autoupdate] FAILED {url}: {e}")
            return
    print(f"[BM_EXT autoupdate] updated to {remote_version}. Restart Blender to load new code.")

try:
    _bm_autoupdate()
except Exception as _e:
    print(f"[BM_EXT autoupdate] outer error: {_e}")

import re
import bpy
import mathutils
import json
import threading
import socket
import time
import requests
import tempfile
import traceback
import os
import shutil
import zipfile
from bpy.props import IntProperty, BoolProperty
import io
from datetime import datetime
import hashlib, hmac, base64
import os.path as osp
from contextlib import redirect_stdout, suppress
import sys
from collections import deque

# === BM_EXT console capture ===
_BM_LOG = deque(maxlen=4000)
_BM_LOG_INSTALLED = False

class _BmTeeStream:
    def __init__(self, orig, tag):
        self.orig = orig
        self.tag = tag
        self._buf = ""
    def write(self, s):
        try:
            self.orig.write(s)
        except Exception:
            pass
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            _BM_LOG.append({"t": datetime.now().isoformat(timespec="seconds"), "stream": self.tag, "line": line})
    def flush(self):
        try:
            self.orig.flush()
        except Exception:
            pass
    def isatty(self):
        return False

def _bm_install_log_tee():
    global _BM_LOG_INSTALLED
    if _BM_LOG_INSTALLED:
        return
    sys.stdout = _BmTeeStream(sys.stdout, "OUT")
    sys.stderr = _BmTeeStream(sys.stderr, "ERR")
    _BM_LOG_INSTALLED = True

_bm_install_log_tee()

bl_info = {
    "name": "Blender MCP",
    "author": "BlenderMCP",
    "version": (1, 2),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > BlenderMCP",
    "description": "Connect Blender to Claude via MCP",
    "category": "Interface",
}

RODIN_FREE_TRIAL_KEY = "k9TcfFoEhNd9cCPP2guHAHHHkctZHIRhZDywZ1euGUXwihbYLpOjQhofby80NJez"

# Add User-Agent as required by Poly Haven API
REQ_HEADERS = requests.utils.default_headers()
REQ_HEADERS.update({"User-Agent": "blender-mcp"})

class BlenderMCPServer:
    def __init__(self, host='localhost', port=9876):
        self.host = host
        self.port = port
        self.running = False
        self.socket = None
        self.server_thread = None

    def start(self):
        if self.running:
            print("Server is already running")
            return

        self.running = True

        try:
            # Create socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.listen(1)

            # Start server thread
            self.server_thread = threading.Thread(target=self._server_loop)
            self.server_thread.daemon = True
            self.server_thread.start()

            print(f"BlenderMCP server started on {self.host}:{self.port}")
        except Exception as e:
            print(f"Failed to start server: {str(e)}")
            self.stop()

    def stop(self):
        self.running = False

        # Close socket
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None

        # Wait for thread to finish
        if self.server_thread:
            try:
                if self.server_thread.is_alive():
                    self.server_thread.join(timeout=1.0)
            except:
                pass
            self.server_thread = None

        print("BlenderMCP server stopped")

    def _server_loop(self):
        """Main server loop in a separate thread"""
        print("Server thread started")
        self.socket.settimeout(1.0)  # Timeout to allow for stopping

        while self.running:
            try:
                # Accept new connection
                try:
                    client, address = self.socket.accept()
                    print(f"Connected to client: {address}")

                    # Handle client in a separate thread
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client,)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                except socket.timeout:
                    # Just check running condition
                    continue
                except Exception as e:
                    print(f"Error accepting connection: {str(e)}")
                    time.sleep(0.5)
            except Exception as e:
                print(f"Error in server loop: {str(e)}")
                if not self.running:
                    break
                time.sleep(0.5)

        print("Server thread stopped")

    def _handle_client(self, client):
        """Handle connected client"""
        print("Client handler started")
        client.settimeout(None)  # No timeout
        buffer = b''

        try:
            while self.running:
                # Receive data
                try:
                    data = client.recv(8192)
                    if not data:
                        print("Client disconnected")
                        break

                    buffer += data
                    try:
                        # Try to parse command
                        command = json.loads(buffer.decode('utf-8'))
                        buffer = b''

                        # Execute command in Blender's main thread
                        def execute_wrapper():
                            try:
                                response = self.execute_command(command)
                                response_json = json.dumps(response)
                                try:
                                    client.sendall(response_json.encode('utf-8'))
                                except:
                                    print("Failed to send response - client disconnected")
                            except Exception as e:
                                print(f"Error executing command: {str(e)}")
                                traceback.print_exc()
                                try:
                                    error_response = {
                                        "status": "error",
                                        "message": str(e)
                                    }
                                    client.sendall(json.dumps(error_response).encode('utf-8'))
                                except:
                                    pass
                            return None

                        # Schedule execution in main thread
                        bpy.app.timers.register(execute_wrapper, first_interval=0.0)
                    except json.JSONDecodeError:
                        # Incomplete data, wait for more
                        pass
                except Exception as e:
                    print(f"Error receiving data: {str(e)}")
                    break
        except Exception as e:
            print(f"Error in client handler: {str(e)}")
        finally:
            try:
                client.close()
            except:
                pass
            print("Client handler stopped")

    def execute_command(self, command):
        """Execute a command in the main Blender thread"""
        try:
            return self._execute_command_internal(command)

        except Exception as e:
            print(f"Error executing command: {str(e)}")
            traceback.print_exc()
            return {"status": "error", "message": str(e)}

    def _execute_command_internal(self, command):
        """Internal command execution with proper context"""
        cmd_type = command.get("type")
        params = command.get("params", {})

        # Add a handler for checking PolyHaven status
        if cmd_type == "get_polyhaven_status":
            return {"status": "success", "result": self.get_polyhaven_status()}

        # Base handlers that are always available
        handlers = {
            "get_scene_info": self.get_scene_info,
            "get_object_info": self.get_object_info,
            "get_viewport_screenshot": self.get_viewport_screenshot,
            "execute_code": self.execute_code,
            "get_telemetry_consent": self.get_telemetry_consent,
            "get_polyhaven_status": self.get_polyhaven_status,
            "get_hyper3d_status": self.get_hyper3d_status,
            "get_sketchfab_status": self.get_sketchfab_status,
            "get_hunyuan3d_status": self.get_hunyuan3d_status,
            # === BM_EXT: fast specific tools ===
            "bm_read_console": self.bm_read_console,
            "bm_force_mode_set": self.bm_force_mode_set,
            "bm_inspect_modifier": self.bm_inspect_modifier,
            "bm_inspect_animation": self.bm_inspect_animation,
            "bm_get_evaluated_vertex": self.bm_get_evaluated_vertex,
            "bm_count_vgroup_weights": self.bm_count_vgroup_weights,
            "bm_reload_addon": self.bm_reload_addon,
            "bm_dump_objects": self.bm_dump_objects,
            "bm_set_transform": self.bm_set_transform,
            "bm_apply_transforms": self.bm_apply_transforms,
            "bm_set_origin": self.bm_set_origin,
            "bm_delete_objects": self.bm_delete_objects,
            "bm_add_armature": self.bm_add_armature,
            "bm_parent_to_bone": self.bm_parent_to_bone,
            "bm_keyframe_bone": self.bm_keyframe_bone,
            "bm_set_armature_mode": self.bm_set_armature_mode,
            "bm_set_frame": self.bm_set_frame,
            "bm_save_blend": self.bm_save_blend,
            "bm_export_fbx": self.bm_export_fbx,
            "bm_set_camera": self.bm_set_camera,
            "bm_view_camera": self.bm_view_camera,
            # token savers
            "bm_list": self.bm_list,
            "bm_get_transform": self.bm_get_transform,
            "bm_get_bbox": self.bm_get_bbox,
            "bm_ping": self.bm_ping,
            # view
            "bm_set_view": self.bm_set_view,
            # selection / hierarchy
            "bm_select": self.bm_select,
            "bm_set_active": self.bm_set_active,
            "bm_set_parent": self.bm_set_parent,
            "bm_clear_parent": self.bm_clear_parent,
            "bm_duplicate": self.bm_duplicate,
            "bm_rename": self.bm_rename,
            "bm_hide": self.bm_hide,
            # mesh ops
            "bm_rotate_verts": self.bm_rotate_verts,
            "bm_translate_verts": self.bm_translate_verts,
            "bm_mirror_verts": self.bm_mirror_verts,
            "bm_pca_align": self.bm_pca_align,
            "bm_mesh_separate": self.bm_mesh_separate,
            "bm_join_objects": self.bm_join_objects,
            # utility
            "bm_create_empty": self.bm_create_empty,
            "bm_set_cursor": self.bm_set_cursor,
            "bm_clear_pose": self.bm_clear_pose,
            "bm_pose_bone_xform": self.bm_pose_bone_xform,
            "bm_append_from_blend": self.bm_append_from_blend,
            "bm_add_constraint": self.bm_add_constraint,
            "bm_clear_constraints": self.bm_clear_constraints,
            # face identification + coloring
            "bm_identify_faces": self.bm_identify_faces,
            "bm_color_faces": self.bm_color_faces,
            "bm_label_faces_by_side": self.bm_label_faces_by_side,
            "bm_color_faces_by_side": self.bm_color_faces_by_side,
            # Actions / animation
            "bm_create_action": self.bm_create_action,
            "bm_assign_action": self.bm_assign_action,
            "bm_delete_action": self.bm_delete_action,
            "bm_list_actions": self.bm_list_actions,
            "bm_clear_action_keys": self.bm_clear_action_keys,
            "bm_copy_action": self.bm_copy_action,
            "bm_bake_pose_keyframes": self.bm_bake_pose_keyframes,
            "bm_keyframe_pose_dict": self.bm_keyframe_pose_dict,
            "bm_set_pose_from_dict": self.bm_set_pose_from_dict,
            "bm_set_keyframe_interp": self.bm_set_keyframe_interp,
            # Bone tools
            "bm_list_bones": self.bm_list_bones,
            "bm_get_bone_world": self.bm_get_bone_world,
            "bm_edit_bone": self.bm_edit_bone,
            "bm_add_bone_constraint": self.bm_add_bone_constraint,
            "bm_clear_bone_constraints": self.bm_clear_bone_constraints,
            # Viewmodel high-level
            "bm_build_viewmodel_rig": self.bm_build_viewmodel_rig,
            "bm_quick_fps_pose": self.bm_quick_fps_pose,
            # Mode
            "bm_set_mode": self.bm_set_mode,
            # Render
            "bm_render_image": self.bm_render_image,
            "bm_set_render": self.bm_set_render,
            # Screenshot
            "bm_screenshot_views": self.bm_screenshot_views,
            # UV
            "bm_uv_unwrap": self.bm_uv_unwrap,
            # Material
            "bm_create_material": self.bm_create_material,
            "bm_assign_material": self.bm_assign_material,
            # Modeling
            "bm_add_primitive": self.bm_add_primitive,
            "bm_subdivide": self.bm_subdivide,
            "bm_extrude_along_normal": self.bm_extrude_along_normal,
            "bm_recalc_normals": self.bm_recalc_normals,
            "bm_remove_doubles": self.bm_remove_doubles,
            "bm_set_shading_smooth": self.bm_set_shading_smooth,
            # Modifier
            "bm_add_modifier": self.bm_add_modifier,
            "bm_apply_modifier": self.bm_apply_modifier,
            "bm_list_modifiers": self.bm_list_modifiers,
            "bm_remove_modifier": self.bm_remove_modifier,
            # Bevel + smoothing + edge tools
            "bm_bevel_edges": self.bm_bevel_edges,
            "bm_smooth_verts": self.bm_smooth_verts,
            "bm_edge_split": self.bm_edge_split,
            "bm_mark_seam": self.bm_mark_seam,
            "bm_mark_sharp": self.bm_mark_sharp,
            "bm_auto_smooth": self.bm_auto_smooth,
            # Calculation / ruler tools
            "bm_distance": self.bm_distance,
            "bm_angle_vectors": self.bm_angle_vectors,
            "bm_world_to_local": self.bm_world_to_local,
            "bm_local_to_world": self.bm_local_to_world,
            "bm_get_vertex": self.bm_get_vertex,
            "bm_set_vertex": self.bm_set_vertex,
            "bm_find_closest_vertex": self.bm_find_closest_vertex,
            "bm_measure_edge_length": self.bm_measure_edge_length,
            # Format conversion + separation
            "bm_export_format": self.bm_export_format,
            "bm_import_format": self.bm_import_format,
            "bm_convert_format": self.bm_convert_format,
            "bm_separate_by_vgroup": self.bm_separate_by_vgroup,
            "bm_separate_by_bbox": self.bm_separate_by_bbox,
            "bm_separate_by_normal": self.bm_separate_by_normal,
            "bm_separate_by_material": self.bm_separate_by_material,
            # Leveling / alignment
            "bm_level_to_ground": self.bm_level_to_ground,
            "bm_center_to_origin": self.bm_center_to_origin,
            "bm_align_objects": self.bm_align_objects,
            "bm_distribute_objects": self.bm_distribute_objects,
            "bm_snap_to_grid": self.bm_snap_to_grid,
            "bm_align_normal_to_axis": self.bm_align_normal_to_axis,
            # Search / find
            "bm_find_objects": self.bm_find_objects,
            "bm_find_by_property": self.bm_find_by_property,
            "bm_select_pattern": self.bm_select_pattern,
            "bm_select_all": self.bm_select_all,
            # Object-level transforms (shortcuts)
            "bm_translate": self.bm_translate,
            "bm_rotate": self.bm_rotate,
            "bm_scale": self.bm_scale,
            "bm_mirror_object": self.bm_mirror_object,
            "bm_flatten_verts": self.bm_flatten_verts,
            # Cursor
            "bm_cursor_to_selected": self.bm_cursor_to_selected,
            "bm_cursor_to_origin": self.bm_cursor_to_origin,
            "bm_cursor_to_object": self.bm_cursor_to_object,
            "bm_object_to_cursor": self.bm_object_to_cursor,
            # Collections
            "bm_create_collection": self.bm_create_collection,
            "bm_add_to_collection": self.bm_add_to_collection,
            "bm_remove_from_collection": self.bm_remove_from_collection,
            "bm_list_collections": self.bm_list_collections,
            # Mesh ops
            "bm_triangulate": self.bm_triangulate,
            "bm_fill_face": self.bm_fill_face,
            "bm_loop_cut": self.bm_loop_cut,
            "bm_select_linked": self.bm_select_linked,
            # Window / layout
            "bm_set_workspace": self.bm_set_workspace,
            "bm_list_workspaces": self.bm_list_workspaces,
            "bm_split_area": self.bm_split_area,
            "bm_set_area_type": self.bm_set_area_type,
            # Precision mesh
            "bm_set_edge_position": self.bm_set_edge_position,
            "bm_align_edge_to_axis": self.bm_align_edge_to_axis,
            "bm_perfect_box": self.bm_perfect_box,
            "bm_round_vert_positions": self.bm_round_vert_positions,
            "bm_make_orthogonal_corner": self.bm_make_orthogonal_corner,
            # Curves
            "bm_create_curve": self.bm_create_curve,
            "bm_add_curve_primitive": self.bm_add_curve_primitive,
            "bm_curve_to_mesh": self.bm_curve_to_mesh,
            "bm_set_curve_bevel": self.bm_set_curve_bevel,
            # Topology
            "bm_bridge_edge_loops": self.bm_bridge_edge_loops,
            "bm_grid_fill": self.bm_grid_fill,
            "bm_quadrify": self.bm_quadrify,
            "bm_check_topology": self.bm_check_topology,
            "bm_select_ngons": self.bm_select_ngons,
            "bm_select_tris": self.bm_select_tris,
            "bm_select_non_manifold": self.bm_select_non_manifold,
            "bm_dissolve_limited": self.bm_dissolve_limited,
            "bm_clean_topology": self.bm_clean_topology,
            "bm_decimate": self.bm_decimate,
            "bm_add_subsurf": self.bm_add_subsurf,
            "bm_remove_loose_geometry": self.bm_remove_loose_geometry,
            # Topology QA — prevent fan-triangulation junk
            "bm_pole_count": self.bm_pole_count,
            "bm_select_high_poles": self.bm_select_high_poles,
            "bm_select_stretched_tris": self.bm_select_stretched_tris,
            "bm_warn_topology": self.bm_warn_topology,
            # Reference / blueprint setup
            "bm_add_reference_image": self.bm_add_reference_image,
            "bm_select_edge_loop": self.bm_select_edge_loop,
            "bm_select_edge_ring": self.bm_select_edge_ring,
            "bm_inset_faces": self.bm_inset_faces,
            "bm_shrinkwrap_to": self.bm_shrinkwrap_to,
            "bm_remesh": self.bm_remesh,
            # Car modeling additions
            "bm_boolean": self.bm_boolean,
            "bm_bisect_plane": self.bm_bisect_plane,
            "bm_symmetrize": self.bm_symmetrize,
            "bm_set_edge_crease": self.bm_set_edge_crease,
            "bm_set_edge_bevel_weight": self.bm_set_edge_bevel_weight,
            "bm_set_vert_bevel_weight": self.bm_set_vert_bevel_weight,
            "bm_proportional_translate": self.bm_proportional_translate,
            "bm_merge_verts": self.bm_merge_verts,
            "bm_array_modifier": self.bm_array_modifier,
            "bm_curve_modifier": self.bm_curve_modifier,
            "bm_edge_slide": self.bm_edge_slide,
            "bm_select_inside_bbox": self.bm_select_inside_bbox,
            "bm_select_by_material": self.bm_select_by_material,
            "bm_make_lod_set": self.bm_make_lod_set,
            "bm_setup_car_template": self.bm_setup_car_template,
            # Gun modeling additions
            "bm_text_3d": self.bm_text_3d,
            "bm_emboss_text": self.bm_emboss_text,
            "bm_set_origin_to_face": self.bm_set_origin_to_face,
            "bm_set_origin_to_vert": self.bm_set_origin_to_vert,
            "bm_align_face_to_face": self.bm_align_face_to_face,
            "bm_punch_pattern": self.bm_punch_pattern,
            "bm_add_skin_modifier": self.bm_add_skin_modifier,
            "bm_add_wireframe_modifier": self.bm_add_wireframe_modifier,
            "bm_add_solidify_modifier": self.bm_add_solidify_modifier,
            "bm_array_objects_along_edge": self.bm_array_objects_along_edge,
            "bm_mesh_thickness_stats": self.bm_mesh_thickness_stats,
            "bm_center_of_mass": self.bm_center_of_mass,
            # Math helpers
            "bm_lerp": self.bm_lerp,
            "bm_slerp_quat": self.bm_slerp_quat,
            "bm_normal_from_3pts": self.bm_normal_from_3pts,
            "bm_centroid_of_points": self.bm_centroid_of_points,
            "bm_circle_from_3pts": self.bm_circle_from_3pts,
            "bm_dist_point_to_line": self.bm_dist_point_to_line,
            "bm_dist_point_to_plane": self.bm_dist_point_to_plane,
            "bm_intersect_line_plane": self.bm_intersect_line_plane,
            # Curves
            "bm_circle_arc": self.bm_circle_arc,
            "bm_bezier_from_4pts": self.bm_bezier_from_4pts,
            "bm_offset_curve": self.bm_offset_curve,
            # Workflow
            "bm_apply_all_modifiers": self.bm_apply_all_modifiers,
            "bm_smart_bevel": self.bm_smart_bevel,
            "bm_check_symmetry": self.bm_check_symmetry,
            # Character animation — IK + rigging
            "bm_setup_ik": self.bm_setup_ik,
            "bm_setup_leg_ik": self.bm_setup_leg_ik,
            "bm_setup_arm_ik": self.bm_setup_arm_ik,
            "bm_create_control_bone": self.bm_create_control_bone,
            "bm_add_armature_modifier": self.bm_add_armature_modifier,
            "bm_auto_weights": self.bm_auto_weights,
            "bm_assign_vertex_group": self.bm_assign_vertex_group,
            "bm_normalize_vertex_groups": self.bm_normalize_vertex_groups,
            "bm_set_bone_display": self.bm_set_bone_display,
            "bm_set_bone_roll": self.bm_set_bone_roll,
            "bm_mirror_bones": self.bm_mirror_bones,
            "bm_add_bone_chain": self.bm_add_bone_chain,
            "bm_push_to_nla": self.bm_push_to_nla,
            "bm_add_shape_key": self.bm_add_shape_key,
            "bm_blend_actions": self.bm_blend_actions,
            # Smart weight paint
            "bm_paint_weight_to_bone": self.bm_paint_weight_to_bone,
            "bm_smooth_weights": self.bm_smooth_weights,
            "bm_copy_weights": self.bm_copy_weights,
            "bm_set_active_vgroup": self.bm_set_active_vgroup,
            "bm_weight_by_axis_split": self.bm_weight_by_axis_split,
            "bm_weight_by_plane_split": self.bm_weight_by_plane_split,
            "bm_transfer_weights": self.bm_transfer_weights,
            "bm_clean_weights": self.bm_clean_weights,
            "bm_mirror_weights": self.bm_mirror_weights,
            "bm_get_weights_at_vert": self.bm_get_weights_at_vert,
            "bm_weight_gradient": self.bm_weight_gradient,
            "bm_weight_falloff_from_point": self.bm_weight_falloff_from_point,
            "bm_remove_zero_weights": self.bm_remove_zero_weights,
            "bm_isolate_bone_weights": self.bm_isolate_bone_weights,
            "bm_export_weights": self.bm_export_weights,
            "bm_import_weights": self.bm_import_weights,
            # Optimizers
            "bm_quadriflow_remesh": self.bm_quadriflow_remesh,
            "bm_decimate_planar": self.bm_decimate_planar,
            "bm_decimate_unsubdivide": self.bm_decimate_unsubdivide,
            "bm_optimize_for_polycount": self.bm_optimize_for_polycount,
            "bm_equalize_edges": self.bm_equalize_edges,
            "bm_planar_faces": self.bm_planar_faces,
            "bm_minimize_poles": self.bm_minimize_poles,
            "bm_score_mesh_quality": self.bm_score_mesh_quality,
            "bm_compare_meshes": self.bm_compare_meshes,
            # Physics
            "bm_add_cloth": self.bm_add_cloth,
            "bm_add_fluid": self.bm_add_fluid,
            "bm_add_softbody": self.bm_add_softbody,
            "bm_add_rigidbody": self.bm_add_rigidbody,
            "bm_add_collision": self.bm_add_collision,
            "bm_bake_physics": self.bm_bake_physics,
            "bm_add_particle_system": self.bm_add_particle_system,
            "bm_set_gravity": self.bm_set_gravity,
            "bm_add_force_field": self.bm_add_force_field,
            # Generic property animation (watch/microwave/door/light)
            "bm_keyframe_property": self.bm_keyframe_property,
            "bm_add_driver": self.bm_add_driver,
            "bm_cyclic_action": self.bm_cyclic_action,
            "bm_keyframe_material_emission": self.bm_keyframe_material_emission,
            "bm_keyframe_material_color": self.bm_keyframe_material_color,
            "bm_animate_visibility": self.bm_animate_visibility,
            "bm_resize_texture": self.bm_resize_texture,
        }

        # Add Polyhaven handlers only if enabled
        if bpy.context.scene.blendermcp_use_polyhaven:
            polyhaven_handlers = {
                "get_polyhaven_categories": self.get_polyhaven_categories,
                "search_polyhaven_assets": self.search_polyhaven_assets,
                "download_polyhaven_asset": self.download_polyhaven_asset,
                "set_texture": self.set_texture,
            }
            handlers.update(polyhaven_handlers)

        # Add Hyper3d handlers only if enabled
        if bpy.context.scene.blendermcp_use_hyper3d:
            polyhaven_handlers = {
                "create_rodin_job": self.create_rodin_job,
                "poll_rodin_job_status": self.poll_rodin_job_status,
                "import_generated_asset": self.import_generated_asset,
            }
            handlers.update(polyhaven_handlers)

        # Add Sketchfab handlers only if enabled
        if bpy.context.scene.blendermcp_use_sketchfab:
            sketchfab_handlers = {
                "search_sketchfab_models": self.search_sketchfab_models,
                "get_sketchfab_model_preview": self.get_sketchfab_model_preview,
                "download_sketchfab_model": self.download_sketchfab_model,
            }
            handlers.update(sketchfab_handlers)
        
        # Add Hunyuan3d handlers only if enabled
        if bpy.context.scene.blendermcp_use_hunyuan3d:
            hunyuan_handlers = {
                "create_hunyuan_job": self.create_hunyuan_job,
                "poll_hunyuan_job_status": self.poll_hunyuan_job_status,
                "import_generated_asset_hunyuan": self.import_generated_asset_hunyuan
            }
            handlers.update(hunyuan_handlers)

        handler = handlers.get(cmd_type)
        if handler:
            try:
                print(f"Executing handler for {cmd_type}")
                result = handler(**params)
                print(f"Handler execution complete")
                return {"status": "success", "result": result}
            except Exception as e:
                print(f"Error in handler: {str(e)}")
                traceback.print_exc()
                return {"status": "error", "message": str(e)}
        else:
            return {"status": "error", "message": f"Unknown command type: {cmd_type}"}



    # ====================================================================
    # BM_EXT: fast specific tools (direct bpy calls, skip code compilation)
    # ====================================================================

    def _bm_world_bbox(self, obj):
        if obj.type != 'MESH':
            return None
        bb = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
        mins = [min(v[i] for v in bb) for i in range(3)]
        maxs = [max(v[i] for v in bb) for i in range(3)]
        return [mins, maxs]

    def _bm_local_bbox(self, obj):
        if obj.type != 'MESH':
            return None
        bb = [mathutils.Vector(c) for c in obj.bound_box]
        mins = [min(v[i] for v in bb) for i in range(3)]
        maxs = [max(v[i] for v in bb) for i in range(3)]
        return [mins, maxs]

    def bm_dump_objects(self, types=None):
        import math as _math
        result = []
        for o in bpy.data.objects:
            if types and o.type not in types:
                continue
            entry = {
                "name": o.name,
                "type": o.type,
                "location": list(o.location),
                "rotation_euler_deg": [round(_math.degrees(x), 3) for x in o.rotation_euler],
                "rotation_quaternion": list(o.rotation_quaternion),
                "scale": list(o.scale),
                "parent": o.parent.name if o.parent else None,
                "parent_type": o.parent_type,
                "parent_bone": o.parent_bone if o.parent_bone else None,
                "hide_viewport": o.hide_viewport,
                "constraints": [c.type for c in o.constraints],
            }
            if o.type == 'MESH':
                entry["local_bbox"] = self._bm_local_bbox(o)
                entry["world_bbox"] = self._bm_world_bbox(o)
                entry["vertex_count"] = len(o.data.vertices)
                entry["vertex_groups"] = [vg.name for vg in o.vertex_groups]
                entry["modifiers"] = [{"type": m.type, "name": m.name} for m in o.modifiers]
            elif o.type == 'ARMATURE':
                entry["bones"] = [b.name for b in o.data.bones]
                entry["pose_position"] = o.data.pose_position
            result.append(entry)
        return {"objects": result, "count": len(result)}

    def bm_set_transform(self, name, location=None, rotation_euler=None, rotation_quaternion=None, scale=None):
        o = bpy.data.objects.get(name)
        if not o:
            raise ValueError(f"Object not found: {name}")
        if location is not None:
            o.location = mathutils.Vector(location)
        if rotation_quaternion is not None:
            o.rotation_mode = 'QUATERNION'
            o.rotation_quaternion = rotation_quaternion
        elif rotation_euler is not None:
            o.rotation_mode = 'XYZ'
            o.rotation_euler = rotation_euler
        if scale is not None:
            if isinstance(scale, (int, float)):
                o.scale = (scale, scale, scale)
            else:
                o.scale = mathutils.Vector(scale)
        bpy.context.view_layer.update()
        return {"name": name, "location": list(o.location), "rotation_euler": list(o.rotation_euler), "scale": list(o.scale)}

    def bm_apply_transforms(self, name, location=False, rotation=True, scale=True):
        o = bpy.data.objects.get(name)
        if not o:
            raise ValueError(f"Object not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.transform_apply(location=bool(location), rotation=bool(rotation), scale=bool(scale))
        return {"name": name, "applied": {"location": bool(location), "rotation": bool(rotation), "scale": bool(scale)}}

    def bm_set_origin(self, name, type='ORIGIN_GEOMETRY', point=None):
        o = bpy.data.objects.get(name)
        if not o:
            raise ValueError(f"Object not found: {name}")
        if type == 'ORIGIN_CURSOR' and point is not None:
            bpy.context.scene.cursor.location = mathutils.Vector(point)
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.origin_set(type=type, center='MEDIAN')
        if type == 'ORIGIN_CURSOR':
            bpy.context.scene.cursor.location = (0, 0, 0)
        return {"name": name, "location": list(o.location)}

    def bm_delete_objects(self, names):
        deleted = []
        for n in names:
            o = bpy.data.objects.get(n)
            if o:
                bpy.data.objects.remove(o, do_unlink=True)
                deleted.append(n)
        return {"deleted": deleted, "count": len(deleted)}

    def bm_add_armature(self, name, bones):
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
        if name in bpy.data.armatures:
            bpy.data.armatures.remove(bpy.data.armatures[name])
        arm_data = bpy.data.armatures.new(name)
        arm_obj = bpy.data.objects.new(name, arm_data)
        bpy.context.collection.objects.link(arm_obj)
        bpy.context.view_layer.objects.active = arm_obj
        bpy.ops.object.mode_set(mode='EDIT')
        ebs = arm_data.edit_bones
        for spec in bones:
            b = ebs.new(spec["name"])
            b.head = mathutils.Vector(spec["head"])
            b.tail = mathutils.Vector(spec["tail"])
            b.use_connect = bool(spec.get("connect", False))
        for spec in bones:
            if spec.get("parent"):
                ebs[spec["name"]].parent = ebs[spec["parent"]]
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.context.view_layer.update()
        return {"armature": name, "bone_count": len(bones)}

    def bm_parent_to_bone(self, child_name, armature_name, bone_name, mode='BONE_RELATIVE'):
        child = bpy.data.objects.get(child_name)
        arm = bpy.data.objects.get(armature_name)
        if not child or not arm:
            raise ValueError(f"Missing object: child={child_name} arm={armature_name}")
        if bone_name not in arm.data.bones:
            raise ValueError(f"Bone not in armature: {bone_name}")
        bpy.ops.object.select_all(action='DESELECT')
        child.select_set(True)
        arm.select_set(True)
        bpy.context.view_layer.objects.active = arm
        arm.data.bones.active = arm.data.bones[bone_name]
        bpy.ops.object.parent_set(type=mode)
        arm.select_set(False)
        return {"child": child_name, "armature": armature_name, "bone": bone_name, "mode": mode}

    def bm_keyframe_bone(self, armature_name, bone_name, frame, location=None, rotation_quaternion=None, scale=None):
        arm = bpy.data.objects.get(armature_name)
        if not arm:
            raise ValueError(f"Armature not found: {armature_name}")
        if arm.animation_data is None:
            arm.animation_data_create()
        if arm.animation_data.action is None:
            arm.animation_data.action = bpy.data.actions.new(f"{armature_name}_Action")
            arm.animation_data.action.use_fake_user = True
        pb = arm.pose.bones.get(bone_name)
        if pb is None:
            raise ValueError(f"Pose bone not found: {bone_name}")
        pb.rotation_mode = 'QUATERNION'
        if location is not None:
            pb.location = mathutils.Vector(location)
            pb.keyframe_insert("location", frame=int(frame))
        if rotation_quaternion is not None:
            pb.rotation_quaternion = rotation_quaternion
            pb.keyframe_insert("rotation_quaternion", frame=int(frame))
        if scale is not None:
            pb.scale = mathutils.Vector(scale) if not isinstance(scale, (int, float)) else (scale, scale, scale)
            pb.keyframe_insert("scale", frame=int(frame))
        return {"armature": armature_name, "bone": bone_name, "frame": frame}

    def bm_set_armature_mode(self, name, mode='POSE'):
        arm = bpy.data.objects.get(name)
        if not arm or arm.type != 'ARMATURE':
            raise ValueError(f"Armature not found: {name}")
        if mode not in ('REST', 'POSE'):
            raise ValueError("mode must be REST or POSE")
        arm.data.pose_position = mode
        bpy.context.view_layer.update()
        return {"armature": name, "mode": mode}

    def bm_set_frame(self, frame, start=None, end=None, fps=None):
        sc = bpy.context.scene
        if fps is not None:
            sc.render.fps = int(fps)
        if start is not None:
            sc.frame_start = int(start)
        if end is not None:
            sc.frame_end = int(end)
        sc.frame_set(int(frame))
        return {"frame": sc.frame_current, "start": sc.frame_start, "end": sc.frame_end, "fps": sc.render.fps}

    def bm_save_blend(self, filepath):
        bpy.ops.wm.save_as_mainfile(filepath=filepath)
        return {"filepath": filepath, "saved": True}

    def bm_export_fbx(self, filepath, selection_only=False, object_names=None, axis_up='Y', axis_forward='-Z', bake_anim=True, apply_scale=True, mesh_smooth='OFF'):
        if object_names:
            bpy.ops.object.select_all(action='DESELECT')
            for n in object_names:
                o = bpy.data.objects.get(n)
                if o:
                    o.select_set(True)
            selection_only = True
        bpy.ops.export_scene.fbx(
            filepath=filepath,
            use_selection=bool(selection_only),
            object_types={'ARMATURE','MESH','EMPTY'},
            add_leaf_bones=False,
            bake_anim=bool(bake_anim),
            bake_anim_use_all_actions=False,
            bake_anim_use_nla_strips=False,
            bake_anim_force_startend_keying=True,
            bake_anim_simplify_factor=0.0,
            apply_unit_scale=bool(apply_scale),
            bake_space_transform=True,
            axis_forward=axis_forward,
            axis_up=axis_up,
            path_mode='COPY',
            embed_textures=False,
            mesh_smooth_type=mesh_smooth,
        )
        import os as _os
        return {"filepath": filepath, "size": _os.path.getsize(filepath) if _os.path.exists(filepath) else 0}

    def bm_set_camera(self, name='Camera', location=None, target=None, lens=35, track_to=True):
        cam = bpy.data.objects.get(name)
        if cam is None or cam.type != 'CAMERA':
            cam_data = bpy.data.cameras.new(name)
            cam = bpy.data.objects.new(name, cam_data)
            bpy.context.collection.objects.link(cam)
        if location is not None:
            cam.location = mathutils.Vector(location)
        cam.data.lens = float(lens)
        if target is not None and track_to:
            target_name = f"{name}_Target"
            t = bpy.data.objects.get(target_name)
            if t is None:
                t = bpy.data.objects.new(target_name, None)
                bpy.context.collection.objects.link(t)
            t.location = mathutils.Vector(target)
            for c in list(cam.constraints):
                cam.constraints.remove(c)
            con = cam.constraints.new('TRACK_TO')
            con.target = t
            con.track_axis = 'TRACK_NEGATIVE_Z'
            con.up_axis = 'UP_Y'
        bpy.context.scene.camera = cam
        bpy.context.view_layer.update()
        return {"camera": name, "location": list(cam.location), "lens": cam.data.lens}

    def bm_view_camera(self):
        # Switch viewport into camera view via region_3d (more reliable than ops)
        switched = False
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                space = area.spaces.active
                if space and space.region_3d:
                    space.region_3d.view_perspective = 'CAMERA'
                    switched = True
                    break
        return {"camera": bpy.context.scene.camera.name if bpy.context.scene.camera else None, "switched": switched}

    # ====================================================================
    # BM_EXT v2: token savers + mesh ops + utility
    # ====================================================================

    @staticmethod
    def _r(x, d=3):
        if isinstance(x, (list, tuple)):
            return [round(float(v), d) for v in x]
        return round(float(x), d)

    def _filter_verts(self, mesh_obj, vf):
        """Apply vertex filter dict to mesh; return list of MeshVertex.
        vf options: {'all': True}, {'x_lt': N}, {'x_gt': N}, {'y_lt': N}, ...,
        {'vgroup': 'name'}, {'indices': [list]}."""
        if not vf or vf.get("all"):
            return list(mesh_obj.data.vertices)
        if "indices" in vf:
            idx = set(vf["indices"])
            return [v for v in mesh_obj.data.vertices if v.index in idx]
        if "vgroup" in vf:
            vg = mesh_obj.vertex_groups.get(vf["vgroup"])
            if not vg:
                return []
            gi = vg.index
            out = []
            for v in mesh_obj.data.vertices:
                for g in v.groups:
                    if g.group == gi:
                        out.append(v); break
            return out
        out = list(mesh_obj.data.vertices)
        for axis, idx in (("x",0),("y",1),("z",2)):
            for op, fn in ((f"{axis}_lt", lambda c, t: c < t), (f"{axis}_gt", lambda c, t: c > t),
                           (f"{axis}_le", lambda c, t: c <= t), (f"{axis}_ge", lambda c, t: c >= t)):
                if op in vf:
                    t = vf[op]
                    out = [v for v in out if fn(v.co[idx], t)]
        return out

    def bm_list(self, types=None):
        """Compact object list — only name, type, world bbox dims. Skips bbox arrays + vgroups."""
        out = []
        for o in bpy.data.objects:
            if types and o.type not in types:
                continue
            entry = {"name": o.name, "type": o.type}
            if o.type == 'MESH':
                bb = self._bm_world_bbox(o)
                if bb:
                    entry["dims"] = self._r([bb[1][i]-bb[0][i] for i in range(3)])
            out.append(entry)
        return {"objects": out, "count": len(out)}

    def bm_get_transform(self, name):
        o = bpy.data.objects.get(name)
        if not o:
            raise ValueError(f"Object not found: {name}")
        import math as _m
        return {
            "name": name,
            "loc": self._r(list(o.location)),
            "rot_deg": self._r([_m.degrees(x) for x in o.rotation_euler]),
            "scale": self._r(list(o.scale)),
            "parent": o.parent.name if o.parent else None,
        }

    def bm_get_bbox(self, name, space='world'):
        o = bpy.data.objects.get(name)
        if not o:
            raise ValueError(f"Object not found: {name}")
        bb = self._bm_world_bbox(o) if space == 'world' else self._bm_local_bbox(o)
        if bb is None:
            return {"name": name, "bbox": None}
        return {"name": name, "mins": self._r(bb[0]), "maxs": self._r(bb[1]), "dims": self._r([bb[1][i]-bb[0][i] for i in range(3)])}

    # ====================================================================
    # BM_EXT v4: tools replacing prior execute_blender_code usage
    # ====================================================================

    def _bm_find_view3d(self):
        """Locate a VIEW_3D area for context overrides. Returns area or None."""
        for w in bpy.context.window_manager.windows:
            for area in w.screen.areas:
                if area.type == 'VIEW_3D':
                    return area
        return None

    def bm_force_mode_set(self, name, mode):
        """Robust object-mode change with VIEW_3D context override.
        Replaces calls that needed temp_override(area=VIEW_3D) before mode_set.
        mode: OBJECT|EDIT|POSE|WEIGHT_PAINT|SCULPT|VERTEX_PAINT|TEXTURE_PAINT."""
        o = bpy.data.objects.get(name)
        if not o:
            raise ValueError(f"Object not found: {name}")
        v3d = self._bm_find_view3d()
        if v3d is None:
            raise RuntimeError("No VIEW_3D area found in any window")
        with bpy.context.temp_override(area=v3d):
            if bpy.context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            for ob in bpy.context.view_layer.objects:
                ob.select_set(False)
            o.select_set(True)
            bpy.context.view_layer.objects.active = o
            if mode != 'OBJECT':
                bpy.ops.object.mode_set(mode=mode)
        return {"name": name, "mode": bpy.context.mode}

    def bm_inspect_modifier(self, name, modifier_name=None):
        """Full modifier props dump. modifier_name=None → all modifiers."""
        o = bpy.data.objects.get(name)
        if not o:
            raise ValueError(f"Object not found: {name}")
        out = []
        mods = [m for m in o.modifiers if (modifier_name is None or m.name == modifier_name)]
        for m in mods:
            info = {"name": m.name, "type": m.type, "show_viewport": m.show_viewport,
                    "show_render": m.show_render}
            for attr in ("object", "vertex_group", "use_vertex_groups", "use_bone_envelopes",
                         "levels", "render_levels", "use_clamp_overlap", "width",
                         "segments", "thickness", "offset", "count", "fit_type",
                         "operation", "ratio", "factor", "limit_method", "angle"):
                if hasattr(m, attr):
                    v = getattr(m, attr)
                    info[attr] = (v.name if hasattr(v, "name") else v) if v is not None else None
            out.append(info)
        return {"name": name, "modifiers": out}

    def bm_inspect_animation(self, armature_name=None, object_name=None):
        """Animation/action introspection. Returns rotation_mode of pose bones,
        current action name, slots, layers, fcurve count per bone."""
        result = {}
        if armature_name:
            arm = bpy.data.objects.get(armature_name)
            if not arm or arm.type != 'ARMATURE':
                raise ValueError(f"Armature not found: {armature_name}")
            bones = []
            for pb in arm.pose.bones:
                bones.append({"name": pb.name, "rotation_mode": pb.rotation_mode,
                              "rotation_quaternion": [round(x,4) for x in pb.rotation_quaternion],
                              "rotation_euler": [round(x,4) for x in pb.rotation_euler],
                              "location": [round(x,4) for x in pb.location]})
            result["armature"] = armature_name
            result["bones"] = bones
            ad = arm.animation_data
            if ad and ad.action:
                a = ad.action
                act_info = {"name": a.name, "frame_range": list(a.frame_range)}
                try:
                    act_info["layers"] = len(a.layers)
                    act_info["slots"] = [s.name_display for s in a.slots]
                except Exception:
                    pass
                try:
                    act_info["fcurve_count"] = len(a.fcurves)
                except Exception:
                    pass
                result["action"] = act_info
        if object_name:
            o = bpy.data.objects.get(object_name)
            if not o:
                raise ValueError(f"Object not found: {object_name}")
            ad = o.animation_data
            if ad and ad.action:
                a = ad.action
                result.setdefault("objects", []).append({"name": object_name, "action": a.name})
        return result

    def bm_get_evaluated_vertex(self, name, index, space='world'):
        """Get vertex position AFTER modifiers + pose deform are applied (depsgraph
        evaluated). Use to verify Armature modifier actually deforms the mesh.
        space: 'world' or 'local'."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH':
            raise ValueError(f"Mesh not found: {name}")
        deps = bpy.context.evaluated_depsgraph_get()
        ev = o.evaluated_get(deps)
        if not (0 <= index < len(ev.data.vertices)):
            raise ValueError(f"Vertex index out of range: {index}")
        co = ev.data.vertices[index].co
        if space == 'world':
            co = ev.matrix_world @ co
        return {"name": name, "index": index, "space": space,
                "position": [round(x,4) for x in co]}

    def bm_count_vgroup_weights(self, mesh_name, threshold=0.5):
        """Count verts per vgroup. Useful for debugging weight distribution.
        threshold: weight ≥ threshold counts as 'majority'."""
        m = bpy.data.objects.get(mesh_name)
        if not m or m.type != 'MESH':
            raise ValueError(f"Mesh not found: {mesh_name}")
        groups = {vg.name: {"full": 0, "partial": 0, "total_weight": 0.0} for vg in m.vertex_groups}
        zero_verts = 0
        for v in m.data.vertices:
            had_any = False
            for g in v.groups:
                name = m.vertex_groups[g.group].name
                groups[name]["total_weight"] += g.weight
                if g.weight >= threshold:
                    groups[name]["full"] += 1
                else:
                    groups[name]["partial"] += 1
                if g.weight > 0:
                    had_any = True
            if not had_any:
                zero_verts += 1
        for k in groups:
            groups[k]["total_weight"] = round(groups[k]["total_weight"], 3)
        return {"mesh": mesh_name, "vert_count": len(m.data.vertices),
                "zero_weight_verts": zero_verts, "groups": groups}

    def bm_reload_addon(self, addon_module="blender_mcp_addon"):
        """Hot-reload an addon (disable + re-enable). Useful after editing source.
        For the MCP addon itself, this restarts the socket — client must reconnect."""
        import addon_utils, importlib, sys
        def _do_reload():
            try:
                addon_utils.disable(addon_module)
            except Exception:
                pass
            if addon_module in sys.modules:
                try:
                    importlib.reload(sys.modules[addon_module])
                except Exception:
                    pass
            try:
                addon_utils.enable(addon_module, default_set=True, persistent=True)
            except Exception:
                pass
            return None  # one-shot timer
        # Defer so we can return a response before our own server thread dies.
        bpy.app.timers.register(_do_reload, first_interval=0.5)
        return {"addon": addon_module, "scheduled": True, "delay_s": 0.5,
                "note": "If reloading blender_mcp_addon, client must reconnect after ~1s."}

    def bm_ping(self):
        return {"ok": True, "scene": bpy.context.scene.name, "frame": bpy.context.scene.frame_current}

    def bm_read_console(self, lines=50, filter=None, stream=None, since=None,
                        clear=False, max_line=200, max_chars=6000,
                        dedupe=True, mode="compact", include_ts=False):
        """Token-friendly console reader.

        Args:
            lines: tail size (default 50)
            filter: substring grep
            stream: 'OUT' or 'ERR' to limit
            since: ISO timestamp; only newer entries
            clear: drop ring buffer after read
            max_line: truncate each line to N chars (default 200)
            max_chars: total payload char cap (default 6000); trims oldest first
            dedupe: collapse consecutive duplicate lines to "<line> (xN)" (default True)
            mode: 'compact' (string lines) | 'entries' (full objects) | 'summary'
                  (counts only, last 5 errors)
            include_ts: include timestamps in compact lines (default False)
        """
        snap = list(_BM_LOG)
        if stream:
            snap = [e for e in snap if e["stream"] == stream]
        if since:
            snap = [e for e in snap if e["t"] > since]
        if filter:
            snap = [e for e in snap if filter in e["line"]]
        total_match = len(snap)
        tail = snap[-int(lines):] if lines and lines > 0 else snap

        def _trunc(s):
            if max_line and len(s) > max_line:
                return s[:max_line] + "…(+%d)" % (len(s) - max_line)
            return s

        if mode == "summary":
            err = [e for e in snap if e["stream"] == "ERR"]
            out = [e for e in snap if e["stream"] == "OUT"]
            last_err = [_trunc(e["line"]) for e in err[-5:]]
            result = {
                "total_buffer": len(_BM_LOG),
                "matched": total_match,
                "err_count": len(err),
                "out_count": len(out),
                "last_err": last_err,
            }
        else:
            if dedupe:
                deduped = []
                for e in tail:
                    line = _trunc(e["line"])
                    key = (e["stream"], line)
                    if deduped and deduped[-1][0] == key:
                        deduped[-1][1] += 1
                    else:
                        deduped.append([key, 1, e["t"]])
                items = []
                for (strm, line), n, ts in deduped:
                    suffix = " (x%d)" % n if n > 1 else ""
                    if mode == "entries":
                        items.append({"stream": strm, "line": line + suffix,
                                      "count": n, "t": ts})
                    else:
                        tag = "E" if strm == "ERR" else "O"
                        prefix = (ts + " ") if include_ts else ""
                        items.append("%s%s|%s%s" % (prefix, tag, line, suffix))
            else:
                items = []
                for e in tail:
                    line = _trunc(e["line"])
                    if mode == "entries":
                        items.append({"stream": e["stream"], "line": line, "t": e["t"]})
                    else:
                        tag = "E" if e["stream"] == "ERR" else "O"
                        prefix = (e["t"] + " ") if include_ts else ""
                        items.append("%s%s|%s" % (prefix, tag, line))

            if max_chars and max_chars > 0:
                trimmed = []
                used = 0
                for it in reversed(items):
                    chunk = it if isinstance(it, str) else (it.get("line", ""))
                    cost = len(chunk) + 2
                    if used + cost > max_chars:
                        trimmed.append("…(+%d earlier omitted, raise max_chars)" % (len(items) - len(trimmed)))
                        break
                    trimmed.append(it)
                    used += cost
                items = list(reversed(trimmed))

            result = {
                "total_buffer": len(_BM_LOG),
                "matched": total_match,
                "returned": len(items),
                "lines": items,
            }

        if clear:
            _BM_LOG.clear()
        return result

    def bm_set_view(self, type='PERSP', view_all=True):
        """type: TOP|BOTTOM|FRONT|BACK|LEFT|RIGHT|CAMERA|PERSP"""
        switched = False
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                space = area.spaces.active
                if type == 'CAMERA':
                    space.region_3d.view_perspective = 'CAMERA'
                    switched = True
                else:
                    if space.region_3d.view_perspective == 'CAMERA':
                        space.region_3d.view_perspective = 'PERSP'
                    for region in area.regions:
                        if region.type == 'WINDOW':
                            with bpy.context.temp_override(area=area, region=region):
                                if type != 'PERSP':
                                    bpy.ops.view3d.view_axis(type=type)
                                if view_all:
                                    bpy.ops.view3d.view_all()
                            switched = True
                            break
                break
        return {"view": type, "switched": switched}

    def bm_select(self, names, deselect_others=True, active=None):
        if deselect_others:
            bpy.ops.object.select_all(action='DESELECT')
        for n in names:
            o = bpy.data.objects.get(n)
            if o:
                o.select_set(True)
        if active:
            a = bpy.data.objects.get(active)
            if a:
                bpy.context.view_layer.objects.active = a
        return {"selected": list(names), "active": active}

    def bm_set_active(self, name):
        o = bpy.data.objects.get(name)
        if not o:
            raise ValueError(f"Object not found: {name}")
        bpy.context.view_layer.objects.active = o
        return {"active": name}

    def bm_set_parent(self, child_name, parent_name, type='OBJECT', bone='', keep_transform=True):
        """type: OBJECT|BONE|BONE_RELATIVE"""
        child = bpy.data.objects.get(child_name)
        parent = bpy.data.objects.get(parent_name)
        if not child or not parent:
            raise ValueError("Missing object")
        if type in ('BONE','BONE_RELATIVE') and bone:
            if bone not in parent.data.bones:
                raise ValueError(f"Bone not in armature: {bone}")
            bpy.ops.object.select_all(action='DESELECT')
            child.select_set(True); parent.select_set(True)
            bpy.context.view_layer.objects.active = parent
            parent.data.bones.active = parent.data.bones[bone]
            bpy.ops.object.parent_set(type=type)
            parent.select_set(False)
        else:
            bpy.ops.object.select_all(action='DESELECT')
            child.select_set(True); parent.select_set(True)
            bpy.context.view_layer.objects.active = parent
            bpy.ops.object.parent_set(type='OBJECT', keep_transform=keep_transform)
            parent.select_set(False)
        return {"child": child_name, "parent": parent_name, "type": type, "bone": bone or None}

    def bm_clear_parent(self, name, keep_transform=True):
        o = bpy.data.objects.get(name)
        if not o:
            raise ValueError(f"Object not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM' if keep_transform else 'CLEAR')
        return {"name": name}

    def bm_duplicate(self, name, new_name=None, link=False):
        o = bpy.data.objects.get(name)
        if not o:
            raise ValueError(f"Object not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.duplicate(linked=bool(link))
        new = bpy.context.view_layer.objects.active
        if new_name:
            new.name = new_name
        return {"source": name, "new": new.name}

    def bm_rename(self, old, new):
        o = bpy.data.objects.get(old)
        if not o:
            raise ValueError(f"Object not found: {old}")
        o.name = new
        return {"old": old, "new": o.name}

    def bm_hide(self, name, hide_viewport=True, hide_render=False):
        o = bpy.data.objects.get(name)
        if not o:
            raise ValueError(f"Object not found: {name}")
        o.hide_viewport = bool(hide_viewport)
        o.hide_render = bool(hide_render)
        return {"name": name, "hide_viewport": o.hide_viewport, "hide_render": o.hide_render}

    def bm_rotate_verts(self, name, axis, angle_deg, vert_filter=None, pivot='CENTROID'):
        """Rotate filtered verts around axis by angle_deg. pivot: CENTROID|ORIGIN|[x,y,z]."""
        import math as _m
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH':
            raise ValueError(f"Mesh not found: {name}")
        verts = self._filter_verts(o, vert_filter or {"all": True})
        if not verts:
            return {"name": name, "rotated": 0}
        if pivot == 'ORIGIN':
            pv = mathutils.Vector((0,0,0))
        elif pivot == 'CENTROID':
            pv = mathutils.Vector((sum(v.co.x for v in verts)/len(verts),
                                   sum(v.co.y for v in verts)/len(verts),
                                   sum(v.co.z for v in verts)/len(verts)))
        else:
            pv = mathutils.Vector(pivot)
        axis_v = mathutils.Vector(axis).normalized()
        R = mathutils.Matrix.Rotation(_m.radians(angle_deg), 3, axis_v)
        for v in verts:
            v.co = R @ (v.co - pv) + pv
        o.data.update()
        return {"name": name, "rotated": len(verts), "pivot": self._r(list(pv))}

    def bm_translate_verts(self, name, delta, vert_filter=None):
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH':
            raise ValueError(f"Mesh not found: {name}")
        verts = self._filter_verts(o, vert_filter or {"all": True})
        d = mathutils.Vector(delta)
        for v in verts:
            v.co += d
        o.data.update()
        return {"name": name, "translated": len(verts), "delta": list(delta)}

    def bm_mirror_verts(self, name, axis, vert_filter=None, plane_pos=0.0):
        """axis: 'x'|'y'|'z'. Mirrors selected verts across plane axis=plane_pos."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH':
            raise ValueError(f"Mesh not found: {name}")
        verts = self._filter_verts(o, vert_filter or {"all": True})
        ai = {'x':0,'y':1,'z':2}[axis.lower()]
        for v in verts:
            v.co[ai] = 2*plane_pos - v.co[ai]
        o.data.update()
        return {"name": name, "mirrored": len(verts), "axis": axis}

    def bm_pca_align(self, name, target_axis='y', vert_filter=None):
        """PCA-align principal axis of selected verts to target world axis. target_axis: 'x'|'y'|'z' or [vec]."""
        import math as _m
        try:
            import numpy as _np
        except ImportError:
            raise RuntimeError("numpy required for bm_pca_align")
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH':
            raise ValueError(f"Mesh not found: {name}")
        verts = self._filter_verts(o, vert_filter or {"all": True})
        if len(verts) < 3:
            return {"name": name, "rotated": 0, "reason": "too few verts"}
        if isinstance(target_axis, str):
            ta = {'x':mathutils.Vector((1,0,0)),'y':mathutils.Vector((0,1,0)),'z':mathutils.Vector((0,0,1))}[target_axis.lower()]
        else:
            ta = mathutils.Vector(target_axis).normalized()
        pts = _np.array([[v.co.x,v.co.y,v.co.z] for v in verts])
        centroid = pts.mean(axis=0)
        _, _, Vt = _np.linalg.svd(pts - centroid, full_matrices=False)
        principal = mathutils.Vector(Vt[0].tolist())
        if principal.dot(ta) < 0:
            principal = -principal
        ax = principal.cross(ta)
        ang = _m.acos(max(-1, min(1, principal.dot(ta))))
        if ax.length < 1e-9:
            return {"name": name, "rotated": len(verts), "tilt_deg": 0}
        R = mathutils.Matrix.Rotation(ang, 3, ax.normalized())
        c = mathutils.Vector(centroid.tolist())
        for v in verts:
            v.co = R @ (v.co - c) + c
        o.data.update()
        return {"name": name, "rotated": len(verts), "tilt_deg": round(_m.degrees(ang), 3)}

    def bm_mesh_separate(self, name, mode='LOOSE'):
        """mode: LOOSE|SELECTED|MATERIAL. Returns names of new objects."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH':
            raise ValueError(f"Mesh not found: {name}")
        before = {x.name for x in bpy.data.objects}
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        if mode == 'SELECTED':
            pass  # caller pre-selected verts via execute
        else:
            bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.separate(type=mode)
        bpy.ops.object.mode_set(mode='OBJECT')
        new = [x.name for x in bpy.data.objects if x.name not in before]
        return {"source": name, "new_objects": new, "count": len(new)}

    def bm_join_objects(self, names, into):
        """Join meshes 'names' into 'into' mesh. 'into' must be one of the names."""
        if into not in names:
            raise ValueError("'into' must be in 'names'")
        bpy.ops.object.select_all(action='DESELECT')
        for n in names:
            o = bpy.data.objects.get(n)
            if o:
                o.select_set(True)
        active = bpy.data.objects.get(into)
        if not active:
            raise ValueError(f"'into' object not found: {into}")
        bpy.context.view_layer.objects.active = active
        bpy.ops.object.join()
        return {"joined": names, "result": into}

    def bm_create_empty(self, name, location=(0,0,0), display_type='PLAIN_AXES', size=0.1, parent=None, parent_bone=None):
        """display_type: PLAIN_AXES|ARROWS|SPHERE|CUBE|CIRCLE|CONE"""
        e = bpy.data.objects.get(name)
        if e is None:
            e = bpy.data.objects.new(name, None)
            bpy.context.collection.objects.link(e)
        e.empty_display_type = display_type
        e.empty_display_size = float(size)
        e.location = mathutils.Vector(location)
        if parent:
            p = bpy.data.objects.get(parent)
            if p:
                e.parent = p
                if parent_bone:
                    e.parent_type = 'BONE'
                    e.parent_bone = parent_bone
        return {"name": name, "location": list(e.location)}

    def bm_set_cursor(self, location=(0,0,0)):
        bpy.context.scene.cursor.location = mathutils.Vector(location)
        return {"cursor": list(bpy.context.scene.cursor.location)}

    def bm_clear_pose(self, name):
        arm = bpy.data.objects.get(name)
        if not arm or arm.type != 'ARMATURE':
            raise ValueError(f"Armature not found: {name}")
        for pb in arm.pose.bones:
            pb.location = (0,0,0)
            pb.rotation_quaternion = (1,0,0,0)
            pb.rotation_euler = (0,0,0)
            pb.scale = (1,1,1)
        return {"armature": name}

    def bm_pose_bone_xform(self, armature_name, bone_name, location=None, rotation_quaternion=None, rotation_euler=None, scale=None):
        """Set pose-bone transform WITHOUT keyframing."""
        arm = bpy.data.objects.get(armature_name)
        if not arm or arm.type != 'ARMATURE':
            raise ValueError(f"Armature not found: {armature_name}")
        pb = arm.pose.bones.get(bone_name)
        if not pb:
            raise ValueError(f"Pose bone not found: {bone_name}")
        if location is not None:
            pb.location = mathutils.Vector(location)
        if rotation_quaternion is not None:
            pb.rotation_mode = 'QUATERNION'
            pb.rotation_quaternion = rotation_quaternion
        elif rotation_euler is not None:
            pb.rotation_mode = 'XYZ'
            pb.rotation_euler = rotation_euler
        if scale is not None:
            pb.scale = mathutils.Vector(scale) if not isinstance(scale,(int,float)) else (scale,scale,scale)
        return {"armature": armature_name, "bone": bone_name}

    def bm_append_from_blend(self, filepath, object_names=None, action_names=None):
        """Append objects + actions from a .blend file."""
        linked_obj = []; linked_act = []
        with bpy.data.libraries.load(filepath, link=False) as (df, dt):
            if object_names:
                dt.objects = [n for n in df.objects if n in object_names]
            if action_names:
                dt.actions = [n for n in df.actions if n in action_names]
        for o in dt.objects:
            if o is not None:
                bpy.context.collection.objects.link(o)
                linked_obj.append(o.name)
        for a in dt.actions:
            if a is not None:
                linked_act.append(a.name)
        return {"appended_objects": linked_obj, "appended_actions": linked_act}

    def bm_add_constraint(self, name, type, target=None, track_axis='TRACK_NEGATIVE_Z', up_axis='UP_Y', subtarget=None, influence=1.0):
        """type: TRACK_TO|COPY_LOCATION|COPY_ROTATION|CHILD_OF|LIMIT_LOCATION|IK"""
        o = bpy.data.objects.get(name)
        if not o:
            raise ValueError(f"Object not found: {name}")
        con = o.constraints.new(type)
        if target:
            t = bpy.data.objects.get(target)
            if t:
                con.target = t
                if subtarget and hasattr(con, 'subtarget'):
                    con.subtarget = subtarget
        if type == 'TRACK_TO':
            con.track_axis = track_axis
            con.up_axis = up_axis
        if hasattr(con, 'influence'):
            con.influence = float(influence)
        return {"name": name, "constraint": con.name, "type": type}

    def bm_clear_constraints(self, name):
        o = bpy.data.objects.get(name)
        if not o:
            raise ValueError(f"Object not found: {name}")
        n = len(o.constraints)
        for c in list(o.constraints):
            o.constraints.remove(c)
        return {"name": name, "removed": n}

    # ====================================================================
    # Face identification + coloring
    # ====================================================================

    def bm_identify_faces(self, name, threshold=0.7, use_world=True, assign_all=False):
        """Classify each polygon by dominant normal direction.
        Returns {TOP, BOTTOM, FRONT, BACK, LEFT, RIGHT, UNKNOWN: [face_indices]}.
        Convention: +X=RIGHT, -X=LEFT, +Y=BACK, -Y=FRONT, +Z=TOP, -Z=BOTTOM.
        threshold: dot-product cutoff for axis alignment (0.7 ~= 45°).
        use_world: rotate normals to world space using object matrix.
        assign_all: when True, faces below threshold still get assigned to their
            best-matching side (no UNKNOWN bucket) — useful for beveled/rounded
            corners that should share the texture of the nearest cardinal side."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH':
            raise ValueError(f"Mesh not found: {name}")
        sides = {"TOP": [], "BOTTOM": [], "FRONT": [], "BACK": [], "LEFT": [], "RIGHT": [], "UNKNOWN": []}
        axes = {
            "RIGHT":  mathutils.Vector(( 1, 0, 0)),
            "LEFT":   mathutils.Vector((-1, 0, 0)),
            "BACK":   mathutils.Vector(( 0, 1, 0)),
            "FRONT":  mathutils.Vector(( 0,-1, 0)),
            "TOP":    mathutils.Vector(( 0, 0, 1)),
            "BOTTOM": mathutils.Vector(( 0, 0,-1)),
        }
        # World rotation matrix for normals
        if use_world:
            R = o.matrix_world.to_3x3()
        for poly in o.data.polygons:
            n = R @ poly.normal if use_world else poly.normal
            n = n.normalized()
            best_side = None; best_dot = -2.0
            for side, axis in axes.items():
                d = n.dot(axis)
                if d > best_dot:
                    best_dot = d; best_side = side
            if not assign_all and best_dot < threshold:
                sides["UNKNOWN"].append(poly.index)
            else:
                sides[best_side].append(poly.index)
        return {"name": name, "sides": sides, "counts": {k: len(v) for k, v in sides.items()}}

    def bm_color_faces(self, name, face_indices, color, material_name=None):
        """Assign a solid-color material to specific face indices.
        color: [r, g, b, a] in 0-1 range. material_name optional (auto-generated if None)."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH':
            raise ValueError(f"Mesh not found: {name}")
        # Create or reuse material
        if material_name is None:
            material_name = f"BM_{name}_{color[0]:.2f}_{color[1]:.2f}_{color[2]:.2f}"
        mat = bpy.data.materials.get(material_name)
        if mat is None:
            mat = bpy.data.materials.new(material_name)
            mat.use_nodes = True
            mat.diffuse_color = (color[0], color[1], color[2], color[3] if len(color) > 3 else 1.0)
            # Set BSDF base color
            if mat.node_tree:
                for node in mat.node_tree.nodes:
                    if node.type == 'BSDF_PRINCIPLED':
                        node.inputs['Base Color'].default_value = (color[0], color[1], color[2], color[3] if len(color) > 3 else 1.0)
                        break
        # Ensure material is on the object
        slot_idx = -1
        for i, slot in enumerate(o.material_slots):
            if slot.material == mat:
                slot_idx = i; break
        if slot_idx == -1:
            o.data.materials.append(mat)
            slot_idx = len(o.data.materials) - 1
        # Assign to faces
        for fi in face_indices:
            if 0 <= fi < len(o.data.polygons):
                o.data.polygons[fi].material_index = slot_idx
        o.data.update()
        return {"name": name, "material": material_name, "colored_faces": len(face_indices), "slot": slot_idx}

    def bm_label_faces_by_side(self, name, texture_dir, threshold=0.7, sides=None,
                               use_world=False, mirror_lr=False, mirror_fb=False,
                               mirror_tb=False, assign_all=True):
        """Apply per-side image-texture materials. Reads <SIDE>.png from texture_dir
        for each of TOP/BOTTOM/FRONT/BACK/LEFT/RIGHT (or the subset in `sides`).
        UVs are projected per side so the texture spans the side cluster as one
        image, aspect preserved (overflow on long axis filled by EXTEND mode).

        use_world: classify face normals in WORLD space (True) or OBJECT-LOCAL
            (False, default) — local respects mesh rotation/tilt.
        mirror_lr / mirror_fb / mirror_tb: swap which texture goes on opposing
            sides — e.g. mirror_lr=True puts LEFT.png on the +axis face and
            RIGHT.png on the -axis face. Use on mirrored arms (right-side arm of
            a body) so each arm's outer face gets its own letter."""
        import os
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH':
            raise ValueError(f"Mesh not found: {name}")
        mesh = o.data
        if not mesh.uv_layers:
            mesh.uv_layers.new(name='UVMap')
        if not mesh.uv_layers.active:
            mesh.uv_layers.active = mesh.uv_layers[0]
        uv_data = mesh.uv_layers.active.data
        ident = self.bm_identify_faces(name, threshold=threshold, use_world=use_world, assign_all=assign_all)["sides"]
        # Apply mirror swaps on the classification map
        if mirror_lr:
            ident['LEFT'], ident['RIGHT'] = ident.get('RIGHT', []), ident.get('LEFT', [])
        if mirror_fb:
            ident['FRONT'], ident['BACK'] = ident.get('BACK', []), ident.get('FRONT', [])
        if mirror_tb:
            ident['TOP'], ident['BOTTOM'] = ident.get('BOTTOM', []), ident.get('TOP', [])
        target_sides = [s.upper() for s in (sides or ['TOP','BOTTOM','FRONT','BACK','LEFT','RIGHT'])]
        # Side → (u_axis, v_axis, flip_u_if_negative_normal). Convention:
        # +X=RIGHT, -X=LEFT, +Y=BACK, -Y=FRONT, +Z=TOP, -Z=BOTTOM.
        # Choose UV axes so reading from outside is right-side up + not mirrored.
        side_axes = {
            'TOP':    (0, 1, False, True),   # +Z viewed from above: u=X, v=Y (no flip u, flip v so +Y up reads correctly)
            'BOTTOM': (0, 1, False, False),  # -Z viewed from below: mirror handled by orientation
            'FRONT':  (0, 2, True,  False),  # -Y viewed from front: u=X (flipped so RIGHT reads left), v=Z
            'BACK':   (0, 2, False, False),  # +Y viewed from back: u=X, v=Z
            'LEFT':   (1, 2, False, False),  # -X viewed from left: u=Y, v=Z
            'RIGHT':  (1, 2, True,  False),  # +X viewed from right: u=-Y, v=Z
        }
        world = o.matrix_world
        def get_pos(vi):
            return (world @ mesh.vertices[vi].co) if use_world else mesh.vertices[vi].co
        results = {}
        for side in target_sides:
            path = os.path.join(texture_dir, f"{side}.png")
            if not os.path.exists(path):
                results[side] = {"skipped": "missing texture", "path": path}
                continue
            faces = ident.get(side, [])
            if not faces:
                results[side] = {"skipped": "no faces classified", "count": 0}
                continue
            ax_u, ax_v, flip_u, flip_v = side_axes[side]
            # Compute 2D bbox over all loop verts in this side
            u_min = v_min =  1e30
            u_max = v_max = -1e30
            for fi in faces:
                poly = mesh.polygons[fi]
                for li in range(poly.loop_total):
                    vi = mesh.loops[poly.loop_start + li].vertex_index
                    wp = get_pos(vi)
                    u_min = min(u_min, wp[ax_u]); u_max = max(u_max, wp[ax_u])
                    v_min = min(v_min, wp[ax_v]); v_max = max(v_max, wp[ax_v])
            u_span = max(u_max - u_min, 1e-9)
            v_span = max(v_max - v_min, 1e-9)
            mat_name = f"BM_{name}_{side}_LBL"
            mat = bpy.data.materials.get(mat_name)
            if mat is None:
                mat = bpy.data.materials.new(mat_name)
                mat.use_nodes = True
                nt = mat.node_tree
                bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
                tex = nt.nodes.new('ShaderNodeTexImage')
                img = bpy.data.images.load(path, check_existing=True)
                tex.image = img
                tex.extension = 'EXTEND'  # outside 0-1 = edge pixel (bg color)
                if bsdf:
                    nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
            else:
                for n in mat.node_tree.nodes:
                    if n.type == 'TEX_IMAGE':
                        n.extension = 'EXTEND'
            slot = -1
            for i, s in enumerate(o.material_slots):
                if s.material == mat:
                    slot = i; break
            if slot == -1:
                mesh.materials.append(mat)
                slot = len(mesh.materials) - 1
            # Aspect-preserve: image stays 1:1, centered on face. Long axis overflows
            # UV [0,1] → EXTEND extension paints bg color across the overflow.
            short_span = min(u_span, v_span)
            scale_u = u_span / short_span  # >=1
            scale_v = v_span / short_span  # >=1
            off_u = (1.0 - scale_u) * 0.5  # negative when long
            off_v = (1.0 - scale_v) * 0.5
            for fi in faces:
                poly = mesh.polygons[fi]
                poly.material_index = slot
                for li in range(poly.loop_total):
                    vi = mesh.loops[poly.loop_start + li].vertex_index
                    wp = get_pos(vi)
                    nu = (wp[ax_u] - u_min) / u_span  # 0..1 within side
                    nv = (wp[ax_v] - v_min) / v_span
                    u = nu * scale_u + off_u  # spans -((scale-1)/2)..(1+(scale-1)/2)
                    v = nv * scale_v + off_v
                    if flip_u: u = 1.0 - u
                    if flip_v: v = 1.0 - v
                    uv_data[poly.loop_start + li].uv = (u, v)
            results[side] = {"material": mat_name, "faces": len(faces), "slot": slot,
                             "bbox": [round(u_min,3), round(v_min,3), round(u_max,3), round(v_max,3)]}
        mesh.update()
        return {"name": name, "applied": results, "counts": {k: len(v) for k, v in ident.items()}}

    def bm_color_faces_by_side(self, name, color_map, threshold=0.7):
        """Identify faces by side + color in one call.
        color_map: {'TOP': [r,g,b,a], 'FRONT': [..], ...} — only listed sides are colored."""
        sides = self.bm_identify_faces(name, threshold=threshold)["sides"]
        results = {}
        for side, color in color_map.items():
            side_u = side.upper()
            faces = sides.get(side_u, [])
            if faces:
                r = self.bm_color_faces(name, faces, color, material_name=f"BM_{name}_{side_u}")
                results[side_u] = r
        return {"name": name, "applied": results, "counts": {k: len(v) for k, v in sides.items()}}

    # ====================================================================
    # BM_EXT v3: actions, bones, viewmodel, render, UV, material, modeling, modifiers, calc
    # ====================================================================

    # ---- Actions / animation ----

    def bm_create_action(self, name, fake_user=True):
        if name in bpy.data.actions:
            return {"name": name, "existed": True}
        a = bpy.data.actions.new(name)
        a.use_fake_user = bool(fake_user)
        return {"name": name, "existed": False}

    def bm_assign_action(self, armature_name, action_name):
        arm = bpy.data.objects.get(armature_name)
        if not arm:
            raise ValueError(f"Armature not found: {armature_name}")
        act = bpy.data.actions.get(action_name)
        if not act:
            raise ValueError(f"Action not found: {action_name}")
        if arm.animation_data is None:
            arm.animation_data_create()
        arm.animation_data.action = act
        return {"armature": armature_name, "action": action_name}

    def bm_delete_action(self, name):
        a = bpy.data.actions.get(name)
        if not a:
            return {"name": name, "existed": False}
        a.use_fake_user = False
        bpy.data.actions.remove(a)
        return {"name": name, "existed": True}

    def bm_list_actions(self):
        out = []
        for a in bpy.data.actions:
            try:
                fr = a.frame_range
                fr_list = [round(fr[0], 3), round(fr[1], 3)]
            except Exception:
                fr_list = None
            out.append({"name": a.name, "fake_user": a.use_fake_user, "frame_range": fr_list})
        return {"actions": out, "count": len(out)}

    def bm_clear_action_keys(self, action_name, frame_start=None, frame_end=None):
        """Remove all keyframes from action, optionally only within frame range."""
        a = bpy.data.actions.get(action_name)
        if not a:
            raise ValueError(f"Action not found: {action_name}")
        removed = 0
        # Modern API: layers/strips/channelbags. Legacy: fcurves.
        try:
            for layer in a.layers:
                for strip in layer.strips:
                    for slot in a.slots:
                        cb = strip.channelbag(slot)
                        if cb is None:
                            continue
                        for fc in list(cb.fcurves):
                            if frame_start is None and frame_end is None:
                                cb.fcurves.remove(fc); removed += 1
                            else:
                                pts = [kp for kp in list(fc.keyframe_points)
                                       if (frame_start is None or kp.co.x >= frame_start)
                                       and (frame_end is None or kp.co.x <= frame_end)]
                                for kp in pts:
                                    fc.keyframe_points.remove(kp); removed += 1
        except AttributeError:
            for fc in list(a.fcurves):
                if frame_start is None and frame_end is None:
                    a.fcurves.remove(fc); removed += 1
                else:
                    pts = [kp for kp in list(fc.keyframe_points)
                           if (frame_start is None or kp.co.x >= frame_start)
                           and (frame_end is None or kp.co.x <= frame_end)]
                    for kp in pts:
                        fc.keyframe_points.remove(kp); removed += 1
        return {"action": action_name, "removed": removed}

    def bm_copy_action(self, src, dst):
        s = bpy.data.actions.get(src)
        if not s:
            raise ValueError(f"Source action not found: {src}")
        new = s.copy()
        new.name = dst
        new.use_fake_user = True
        return {"src": src, "dst": new.name}

    def bm_bake_pose_keyframes(self, armature_name, frame, bone_names=None):
        """Snapshot current pose into keyframes at `frame`. bone_names: list of bone names or None (all bones)."""
        arm = bpy.data.objects.get(armature_name)
        if not arm or arm.type != 'ARMATURE':
            raise ValueError(f"Armature not found: {armature_name}")
        if arm.animation_data is None or arm.animation_data.action is None:
            raise ValueError(f"Armature has no active action")
        bones = bone_names if bone_names else [pb.name for pb in arm.pose.bones]
        n = 0
        for bn in bones:
            pb = arm.pose.bones.get(bn)
            if not pb:
                continue
            pb.rotation_mode = 'QUATERNION'
            pb.keyframe_insert("location", frame=int(frame))
            pb.keyframe_insert("rotation_quaternion", frame=int(frame))
            pb.keyframe_insert("scale", frame=int(frame))
            n += 1
        return {"armature": armature_name, "frame": frame, "bones_keyed": n}

    def bm_keyframe_pose_dict(self, armature_name, pose_dict, frame):
        """Keyframe multiple bones at once.
        pose_dict: {bone_name: {location?, rotation_quaternion?, rotation_euler?, scale?}, ...}"""
        arm = bpy.data.objects.get(armature_name)
        if not arm or arm.type != 'ARMATURE':
            raise ValueError(f"Armature not found: {armature_name}")
        if arm.animation_data is None:
            arm.animation_data_create()
        if arm.animation_data.action is None:
            arm.animation_data.action = bpy.data.actions.new(f"{armature_name}_Action")
            arm.animation_data.action.use_fake_user = True
        n = 0
        for bn, spec in pose_dict.items():
            pb = arm.pose.bones.get(bn)
            if not pb:
                continue
            pb.rotation_mode = 'QUATERNION'
            if 'location' in spec and spec['location'] is not None:
                pb.location = mathutils.Vector(spec['location'])
                pb.keyframe_insert("location", frame=int(frame))
            if 'rotation_quaternion' in spec and spec['rotation_quaternion'] is not None:
                pb.rotation_quaternion = spec['rotation_quaternion']
                pb.keyframe_insert("rotation_quaternion", frame=int(frame))
            elif 'rotation_euler' in spec and spec['rotation_euler'] is not None:
                pb.rotation_mode = 'XYZ'
                pb.rotation_euler = spec['rotation_euler']
                pb.keyframe_insert("rotation_euler", frame=int(frame))
            if 'scale' in spec and spec['scale'] is not None:
                pb.scale = mathutils.Vector(spec['scale']) if not isinstance(spec['scale'], (int,float)) else (spec['scale'],)*3
                pb.keyframe_insert("scale", frame=int(frame))
            n += 1
        return {"armature": armature_name, "frame": frame, "bones_keyed": n}

    def bm_set_pose_from_dict(self, armature_name, pose_dict):
        """Set multiple bone poses WITHOUT keyframing. Same dict shape as bm_keyframe_pose_dict."""
        arm = bpy.data.objects.get(armature_name)
        if not arm or arm.type != 'ARMATURE':
            raise ValueError(f"Armature not found: {armature_name}")
        n = 0
        for bn, spec in pose_dict.items():
            pb = arm.pose.bones.get(bn)
            if not pb:
                continue
            if 'location' in spec and spec['location'] is not None:
                pb.location = mathutils.Vector(spec['location'])
            if 'rotation_quaternion' in spec and spec['rotation_quaternion'] is not None:
                pb.rotation_mode = 'QUATERNION'
                pb.rotation_quaternion = spec['rotation_quaternion']
            elif 'rotation_euler' in spec and spec['rotation_euler'] is not None:
                pb.rotation_mode = 'XYZ'
                pb.rotation_euler = spec['rotation_euler']
            if 'scale' in spec and spec['scale'] is not None:
                pb.scale = mathutils.Vector(spec['scale']) if not isinstance(spec['scale'], (int,float)) else (spec['scale'],)*3
            n += 1
        return {"armature": armature_name, "bones_set": n}

    def bm_set_keyframe_interp(self, action_name, mode='LINEAR'):
        """Set interpolation mode for ALL keyframes in action. mode: LINEAR|BEZIER|CONSTANT|BACK|BOUNCE|ELASTIC."""
        a = bpy.data.actions.get(action_name)
        if not a:
            raise ValueError(f"Action not found: {action_name}")
        n = 0
        try:
            for layer in a.layers:
                for strip in layer.strips:
                    for slot in a.slots:
                        cb = strip.channelbag(slot)
                        if cb is None:
                            continue
                        for fc in cb.fcurves:
                            for kp in fc.keyframe_points:
                                kp.interpolation = mode; n += 1
        except AttributeError:
            for fc in a.fcurves:
                for kp in fc.keyframe_points:
                    kp.interpolation = mode; n += 1
        return {"action": action_name, "mode": mode, "keys_set": n}

    # ---- Bone tools ----

    def bm_list_bones(self, armature_name):
        arm = bpy.data.objects.get(armature_name)
        if not arm or arm.type != 'ARMATURE':
            raise ValueError(f"Armature not found: {armature_name}")
        out = []
        for b in arm.data.bones:
            out.append({
                "name": b.name,
                "parent": b.parent.name if b.parent else None,
                "head_local": self._r(list(b.head_local)),
                "tail_local": self._r(list(b.tail_local)),
                "length": round(b.length, 4),
                "use_connect": b.use_connect,
            })
        return {"armature": armature_name, "bones": out, "count": len(out)}

    def bm_get_bone_world(self, armature_name, bone_name):
        arm = bpy.data.objects.get(armature_name)
        if not arm or arm.type != 'ARMATURE':
            raise ValueError(f"Armature not found: {armature_name}")
        pb = arm.pose.bones.get(bone_name)
        if not pb:
            raise ValueError(f"Bone not found: {bone_name}")
        h = arm.matrix_world @ pb.head
        t = arm.matrix_world @ pb.tail
        return {"bone": bone_name, "head_world": self._r(list(h)), "tail_world": self._r(list(t)), "length": round((t-h).length, 4)}

    def bm_edit_bone(self, armature_name, bone_name, head=None, tail=None, parent=None, connect=None):
        """Edit existing bone in EDIT mode. Any param None = unchanged."""
        arm = bpy.data.objects.get(armature_name)
        if not arm or arm.type != 'ARMATURE':
            raise ValueError(f"Armature not found: {armature_name}")
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.mode_set(mode='EDIT')
        eb = arm.data.edit_bones.get(bone_name)
        if not eb:
            bpy.ops.object.mode_set(mode='OBJECT')
            raise ValueError(f"Edit bone not found: {bone_name}")
        if head is not None: eb.head = mathutils.Vector(head)
        if tail is not None: eb.tail = mathutils.Vector(tail)
        if parent is not None:
            eb.parent = arm.data.edit_bones.get(parent) if parent else None
        if connect is not None:
            eb.use_connect = bool(connect)
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"armature": armature_name, "bone": bone_name}

    def bm_add_bone_constraint(self, armature_name, bone_name, type, target=None, subtarget=None, **kwargs):
        """type: IK|TRACK_TO|COPY_LOCATION|COPY_ROTATION|COPY_TRANSFORMS|LIMIT_ROTATION|DAMPED_TRACK"""
        arm = bpy.data.objects.get(armature_name)
        if not arm or arm.type != 'ARMATURE':
            raise ValueError(f"Armature not found: {armature_name}")
        pb = arm.pose.bones.get(bone_name)
        if not pb:
            raise ValueError(f"Bone not found: {bone_name}")
        con = pb.constraints.new(type)
        if target:
            t = bpy.data.objects.get(target)
            if t:
                con.target = t
                if subtarget and hasattr(con, 'subtarget'):
                    con.subtarget = subtarget
        for k, v in kwargs.items():
            if hasattr(con, k):
                setattr(con, k, v)
        return {"armature": armature_name, "bone": bone_name, "constraint": con.name, "type": type}

    def bm_clear_bone_constraints(self, armature_name, bone_name):
        arm = bpy.data.objects.get(armature_name)
        if not arm:
            raise ValueError(f"Armature not found: {armature_name}")
        pb = arm.pose.bones.get(bone_name)
        if not pb:
            raise ValueError(f"Bone not found: {bone_name}")
        n = len(pb.constraints)
        for c in list(pb.constraints):
            pb.constraints.remove(c)
        return {"armature": armature_name, "bone": bone_name, "removed": n}

    # ---- Viewmodel high-level ----

    def bm_build_viewmodel_rig(self, r_arm_mesh=None, l_arm_mesh=None, gun_body=None, gun_mag=None,
                               r_wrist=(0.10,-0.30,1.20), l_wrist=(0.05,-0.80,1.20),
                               r_shoulder=None, l_shoulder=None,
                               rig_name="ViewModel_Rig"):
        """Auto-build FPS viewmodel rig with simple bone chain + bone-parents meshes."""
        # Default shoulders behind wrists
        ARM_LEN = 0.56
        if r_shoulder is None:
            d = mathutils.Vector((0.3, 1.0, 0.3)).normalized()
            r_shoulder = mathutils.Vector(r_wrist) + ARM_LEN * d
        if l_shoulder is None:
            d = mathutils.Vector((-0.3, 1.0, 0.3)).normalized()
            l_shoulder = mathutils.Vector(l_wrist) + ARM_LEN * d

        bones = [
            {"name": "Root",     "head": [0,0,0], "tail": [0,0,0.1]},
            {"name": "R_Arm",    "head": list(r_shoulder), "tail": list(r_wrist), "parent": "Root"},
            {"name": "L_Arm",    "head": list(l_shoulder), "tail": list(l_wrist), "parent": "Root"},
            {"name": "Gun_Body", "head": list(r_wrist),    "tail": [r_wrist[0], r_wrist[1]-0.3, r_wrist[2]], "parent": "R_Arm"},
        ]
        if gun_mag:
            bones.append({"name": "Gun_Mag", "head": [r_wrist[0]-0.025, r_wrist[1]-0.375, r_wrist[2]-0.13],
                          "tail": [r_wrist[0]-0.025, r_wrist[1]-0.375, r_wrist[2]-0.23], "parent": "Gun_Body"})
        self.bm_add_armature(rig_name, bones)
        # Bone-parent meshes
        attached = []
        if r_arm_mesh and bpy.data.objects.get(r_arm_mesh):
            self.bm_parent_to_bone(r_arm_mesh, rig_name, "R_Arm", "BONE_RELATIVE"); attached.append((r_arm_mesh,"R_Arm"))
        if l_arm_mesh and bpy.data.objects.get(l_arm_mesh):
            self.bm_parent_to_bone(l_arm_mesh, rig_name, "L_Arm", "BONE_RELATIVE"); attached.append((l_arm_mesh,"L_Arm"))
        if gun_body and bpy.data.objects.get(gun_body):
            self.bm_parent_to_bone(gun_body, rig_name, "Gun_Body", "BONE_RELATIVE"); attached.append((gun_body,"Gun_Body"))
        if gun_mag and bpy.data.objects.get(gun_mag):
            self.bm_parent_to_bone(gun_mag, rig_name, "Gun_Mag", "BONE_RELATIVE"); attached.append((gun_mag,"Gun_Mag"))
        return {"rig": rig_name, "bones": [b["name"] for b in bones], "attached": attached}

    def bm_quick_fps_pose(self, armature_name, pose='AIM'):
        """Apply preset FPS pose. pose: AIM|IDLE|RELOAD_PEAK|FIRE_RECOIL."""
        import math as _m
        presets = {
            'AIM': {},   # rest pose
            'IDLE': {
                'R_Arm': {'rotation_euler': [_m.radians(2),0,0]},
                'L_Arm': {'rotation_euler': [_m.radians(-2),0,0]},
            },
            'RELOAD_PEAK': {
                'R_Arm': {'rotation_euler': [_m.radians(20),0,0]},
                'L_Arm': {'rotation_euler': [_m.radians(-50),0,_m.radians(20)]},
                'Gun_Body': {'rotation_euler': [_m.radians(60), 0, _m.radians(20)]},
            },
            'FIRE_RECOIL': {
                'R_Arm': {'rotation_euler': [_m.radians(-8),0,0]},
                'Gun_Body': {'rotation_euler': [_m.radians(-12),0,0]},
            },
        }
        if pose not in presets:
            raise ValueError(f"Unknown pose: {pose}. Options: {list(presets)}")
        return self.bm_set_pose_from_dict(armature_name, presets[pose])

    # ---- Mode ----

    def bm_set_mode(self, name, mode='OBJECT'):
        """Mode: OBJECT|EDIT|POSE|SCULPT|WEIGHT_PAINT|VERTEX_PAINT|TEXTURE_PAINT."""
        o = bpy.data.objects.get(name)
        if not o:
            raise ValueError(f"Object not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode=mode)
        return {"name": name, "mode": mode}

    # ---- Render ----

    def bm_render_image(self, filepath, frame=None, resolution=None):
        sc = bpy.context.scene
        if frame is not None:
            sc.frame_set(int(frame))
        if resolution is not None:
            sc.render.resolution_x = int(resolution[0])
            sc.render.resolution_y = int(resolution[1])
        sc.render.filepath = filepath
        bpy.ops.render.render(write_still=True)
        import os as _os
        return {"filepath": filepath, "exists": _os.path.exists(filepath), "size": _os.path.getsize(filepath) if _os.path.exists(filepath) else 0}

    def bm_set_render(self, engine=None, samples=None, resolution=None, percentage=None, view_transform=None):
        sc = bpy.context.scene
        if engine: sc.render.engine = engine  # 'BLENDER_EEVEE_NEXT' (4.x), 'CYCLES', etc.
        if samples is not None:
            if sc.render.engine.startswith('BLENDER_EEVEE') and hasattr(sc, 'eevee'):
                sc.eevee.taa_render_samples = int(samples)
            elif sc.render.engine == 'CYCLES':
                sc.cycles.samples = int(samples)
        if resolution:
            sc.render.resolution_x = int(resolution[0])
            sc.render.resolution_y = int(resolution[1])
        if percentage is not None:
            sc.render.resolution_percentage = int(percentage)
        if view_transform:
            sc.view_settings.view_transform = view_transform
        return {"engine": sc.render.engine, "resolution": [sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage]}

    # ---- Multi-view screenshot ----

    def bm_screenshot_views(self, filepath_prefix, views=None, max_size=800):
        """Take multiple viewport screenshots and save. Returns list of paths.
        views: list of TOP/FRONT/LEFT/RIGHT/BACK/BOTTOM/CAMERA."""
        if not views:
            views = ['TOP', 'FRONT', 'RIGHT']
        paths = []
        for v in views:
            self.bm_set_view(v, view_all=(v != 'CAMERA'))
            fp = f"{filepath_prefix}_{v}.png"
            self.get_viewport_screenshot(max_size=max_size, filepath=fp, format='png')
            paths.append(fp)
        return {"paths": paths}

    # ---- UV ----

    def bm_uv_unwrap(self, name, method='SMART', angle=66, island_margin=0.02):
        """method: SMART|UNWRAP|CUBE|SPHERE|CYLINDER|PROJECT_FROM_VIEW."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH':
            raise ValueError(f"Mesh not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        try:
            if method == 'SMART':
                bpy.ops.uv.smart_project(angle_limit=angle, island_margin=island_margin)
            elif method == 'UNWRAP':
                bpy.ops.uv.unwrap(method='ANGLE_BASED', margin=island_margin)
            elif method == 'CUBE':
                bpy.ops.uv.cube_project()
            elif method == 'SPHERE':
                bpy.ops.uv.sphere_project()
            elif method == 'CYLINDER':
                bpy.ops.uv.cylinder_project()
            else:
                bpy.ops.uv.unwrap()
        finally:
            bpy.ops.object.mode_set(mode='OBJECT')
        return {"name": name, "method": method}

    # ---- Materials ----

    def bm_create_material(self, name, base_color=(0.8,0.8,0.8,1), metallic=0.0, roughness=0.5, emission=(0,0,0,0), emission_strength=0.0):
        mat = bpy.data.materials.get(name)
        if mat is None:
            mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        mat.diffuse_color = (base_color[0], base_color[1], base_color[2], base_color[3] if len(base_color) > 3 else 1.0)
        if mat.node_tree:
            for node in mat.node_tree.nodes:
                if node.type == 'BSDF_PRINCIPLED':
                    node.inputs['Base Color'].default_value = (base_color[0], base_color[1], base_color[2], base_color[3] if len(base_color) > 3 else 1.0)
                    if 'Metallic' in node.inputs:
                        node.inputs['Metallic'].default_value = float(metallic)
                    if 'Roughness' in node.inputs:
                        node.inputs['Roughness'].default_value = float(roughness)
                    if 'Emission Color' in node.inputs:
                        node.inputs['Emission Color'].default_value = (emission[0], emission[1], emission[2], emission[3] if len(emission) > 3 else 1.0)
                    if 'Emission Strength' in node.inputs:
                        node.inputs['Emission Strength'].default_value = float(emission_strength)
                    break
        return {"material": name}

    def bm_assign_material(self, name, material_name, face_indices=None):
        """If face_indices None, assign to entire object. Else assign to specific faces (creates slot if needed)."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH':
            raise ValueError(f"Mesh not found: {name}")
        mat = bpy.data.materials.get(material_name)
        if not mat:
            raise ValueError(f"Material not found: {material_name}")
        if face_indices is None:
            if not o.data.materials:
                o.data.materials.append(mat)
            else:
                o.data.materials[0] = mat
            return {"name": name, "material": material_name, "mode": "whole"}
        slot_idx = -1
        for i, slot in enumerate(o.material_slots):
            if slot.material == mat:
                slot_idx = i; break
        if slot_idx == -1:
            o.data.materials.append(mat)
            slot_idx = len(o.data.materials) - 1
        for fi in face_indices:
            if 0 <= fi < len(o.data.polygons):
                o.data.polygons[fi].material_index = slot_idx
        o.data.update()
        return {"name": name, "material": material_name, "mode": "faces", "count": len(face_indices)}

    # ---- Modeling ----

    def bm_add_primitive(self, type, name=None, location=(0,0,0), size=1.0, segments=32, rings=16):
        """type: CUBE|UV_SPHERE|ICO_SPHERE|CYLINDER|CONE|TORUS|PLANE|CIRCLE|MONKEY."""
        t = type.upper()
        opmap = {
            'CUBE': lambda: bpy.ops.mesh.primitive_cube_add(size=size, location=location),
            'UV_SPHERE': lambda: bpy.ops.mesh.primitive_uv_sphere_add(radius=size/2, segments=segments, ring_count=rings, location=location),
            'ICO_SPHERE': lambda: bpy.ops.mesh.primitive_ico_sphere_add(radius=size/2, location=location),
            'CYLINDER': lambda: bpy.ops.mesh.primitive_cylinder_add(radius=size/2, depth=size, vertices=segments, location=location),
            'CONE': lambda: bpy.ops.mesh.primitive_cone_add(radius1=size/2, depth=size, vertices=segments, location=location),
            'TORUS': lambda: bpy.ops.mesh.primitive_torus_add(major_radius=size/2, minor_radius=size/8, location=location),
            'PLANE': lambda: bpy.ops.mesh.primitive_plane_add(size=size, location=location),
            'CIRCLE': lambda: bpy.ops.mesh.primitive_circle_add(radius=size/2, vertices=segments, location=location),
            'MONKEY': lambda: bpy.ops.mesh.primitive_monkey_add(size=size, location=location),
        }
        if t not in opmap:
            raise ValueError(f"Unknown primitive: {type}. Options: {list(opmap)}")
        opmap[t]()
        new_obj = bpy.context.view_layer.objects.active
        if name:
            new_obj.name = name
        return {"name": new_obj.name, "type": t, "location": list(new_obj.location)}

    def bm_subdivide(self, name, cuts=1):
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH':
            raise ValueError(f"Mesh not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.subdivide(number_cuts=int(cuts))
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"name": name, "cuts": cuts, "verts": len(o.data.vertices)}

    def bm_extrude_along_normal(self, name, face_indices, distance):
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH':
            raise ValueError(f"Mesh not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.mode_set(mode='OBJECT')
        face_set = set(face_indices)
        for p in o.data.polygons:
            p.select = p.index in face_set
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.extrude_faces_move(MESH_OT_extrude_faces_indiv={}, TRANSFORM_OT_shrink_fatten={"value": float(distance)})
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"name": name, "extruded": len(face_indices), "distance": distance}

    def bm_recalc_normals(self, name, inside=False):
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH':
            raise ValueError(f"Mesh not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.normals_make_consistent(inside=bool(inside))
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"name": name, "inside": inside}

    def bm_remove_doubles(self, name, distance=0.0001):
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH':
            raise ValueError(f"Mesh not found: {name}")
        before = len(o.data.vertices)
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.remove_doubles(threshold=float(distance))
        bpy.ops.object.mode_set(mode='OBJECT')
        after = len(o.data.vertices)
        return {"name": name, "before": before, "after": after, "merged": before - after}

    def bm_set_shading_smooth(self, name, smooth=True, auto_smooth_angle=None):
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH':
            raise ValueError(f"Mesh not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        if smooth:
            bpy.ops.object.shade_smooth()
        else:
            bpy.ops.object.shade_flat()
        if auto_smooth_angle is not None and hasattr(o.data, 'use_auto_smooth'):
            o.data.use_auto_smooth = True
            import math as _m
            o.data.auto_smooth_angle = _m.radians(float(auto_smooth_angle))
        return {"name": name, "smooth": smooth, "auto_smooth_angle_deg": auto_smooth_angle}

    # ---- Modifiers ----

    def bm_add_modifier(self, name, mod_type, mod_name=None, properties=None):
        """mod_type: SUBSURF|MIRROR|ARMATURE|SOLIDIFY|BEVEL|SMOOTH|DECIMATE|BOOLEAN|ARRAY|LATTICE|SHRINKWRAP|SUBDIVIDE_LEVEL ..."""
        o = bpy.data.objects.get(name)
        if not o:
            raise ValueError(f"Object not found: {name}")
        mod_name = mod_name or mod_type
        m = o.modifiers.new(mod_name, mod_type)
        if properties:
            for k, v in properties.items():
                if hasattr(m, k):
                    if k == 'object' and isinstance(v, str):
                        ref = bpy.data.objects.get(v)
                        if ref: setattr(m, k, ref)
                    else:
                        setattr(m, k, v)
        return {"name": name, "modifier": m.name, "type": mod_type}

    def bm_apply_modifier(self, name, modifier_name):
        o = bpy.data.objects.get(name)
        if not o:
            raise ValueError(f"Object not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.modifier_apply(modifier=modifier_name)
        return {"name": name, "applied": modifier_name}

    def bm_list_modifiers(self, name):
        o = bpy.data.objects.get(name)
        if not o:
            raise ValueError(f"Object not found: {name}")
        out = []
        for m in o.modifiers:
            entry = {"name": m.name, "type": m.type}
            for attr in ('thickness', 'levels', 'render_levels', 'angle_limit', 'iterations', 'factor', 'ratio'):
                if hasattr(m, attr):
                    entry[attr] = getattr(m, attr)
            out.append(entry)
        return {"name": name, "modifiers": out}

    def bm_remove_modifier(self, name, modifier_name):
        o = bpy.data.objects.get(name)
        if not o:
            raise ValueError(f"Object not found: {name}")
        m = o.modifiers.get(modifier_name)
        if not m:
            return {"name": name, "removed": False}
        o.modifiers.remove(m)
        return {"name": name, "removed": True}

    # ---- Bevel + smoothing + edge tools ----

    def bm_bevel_edges(self, name, offset=0.02, segments=2, profile=0.5, edge_indices=None):
        """Bevel edges. edge_indices=None means all edges; else specific edges."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH':
            raise ValueError(f"Mesh not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='EDGE')
        if edge_indices:
            bpy.ops.mesh.select_all(action='DESELECT')
            bpy.ops.object.mode_set(mode='OBJECT')
            edge_set = set(edge_indices)
            for e in o.data.edges:
                e.select = e.index in edge_set
            bpy.ops.object.mode_set(mode='EDIT')
        else:
            bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.bevel(offset=float(offset), segments=int(segments), profile=float(profile))
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"name": name, "offset": offset, "segments": segments}

    def bm_smooth_verts(self, name, vert_filter=None, factor=0.5, iterations=1):
        """Laplacian-smooth selected verts. Stays in OBJECT mode."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH':
            raise ValueError(f"Mesh not found: {name}")
        target_verts = self._filter_verts(o, vert_filter or {"all": True})
        target_set = set(v.index for v in target_verts)
        # Build adjacency
        adj = {i: [] for i in target_set}
        for e in o.data.edges:
            a, b = e.vertices[0], e.vertices[1]
            if a in target_set: adj[a].append(b)
            if b in target_set: adj[b].append(a)
        # Iterate
        for _ in range(int(iterations)):
            new_pos = {}
            for vi in target_set:
                if not adj[vi]:
                    continue
                avg = mathutils.Vector((0,0,0))
                for nb in adj[vi]:
                    avg += o.data.vertices[nb].co
                avg /= len(adj[vi])
                new_pos[vi] = o.data.vertices[vi].co.lerp(avg, float(factor))
            for vi, p in new_pos.items():
                o.data.vertices[vi].co = p
        o.data.update()
        return {"name": name, "smoothed": len(target_verts), "iterations": iterations, "factor": factor}

    def bm_edge_split(self, name, angle_deg=30, edge_indices=None):
        """Split edges by angle threshold or by explicit indices."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH':
            raise ValueError(f"Mesh not found: {name}")
        if edge_indices:
            bpy.ops.object.select_all(action='DESELECT')
            o.select_set(True); bpy.context.view_layer.objects.active = o
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_mode(type='EDGE')
            bpy.ops.mesh.select_all(action='DESELECT')
            bpy.ops.object.mode_set(mode='OBJECT')
            edge_set = set(edge_indices)
            for e in o.data.edges:
                e.select = e.index in edge_set
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.edge_split()
            bpy.ops.object.mode_set(mode='OBJECT')
        else:
            import math as _m
            m = o.modifiers.new("EdgeSplit_tmp", 'EDGE_SPLIT')
            m.split_angle = _m.radians(float(angle_deg))
            bpy.context.view_layer.objects.active = o
            bpy.ops.object.modifier_apply(modifier=m.name)
        return {"name": name}

    def bm_mark_seam(self, name, edge_indices, clear=False):
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH':
            raise ValueError(f"Mesh not found: {name}")
        es = set(edge_indices)
        for e in o.data.edges:
            if e.index in es:
                e.use_seam = not bool(clear)
        return {"name": name, "marked": len(edge_indices), "clear": clear}

    def bm_mark_sharp(self, name, edge_indices, clear=False):
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH':
            raise ValueError(f"Mesh not found: {name}")
        es = set(edge_indices)
        for e in o.data.edges:
            if e.index in es:
                e.use_edge_sharp = not bool(clear)
        return {"name": name, "marked": len(edge_indices), "clear": clear}

    def bm_auto_smooth(self, name, angle_deg=30, enabled=True):
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH':
            raise ValueError(f"Mesh not found: {name}")
        if hasattr(o.data, 'use_auto_smooth'):
            o.data.use_auto_smooth = bool(enabled)
            import math as _m
            o.data.auto_smooth_angle = _m.radians(float(angle_deg))
        return {"name": name, "enabled": enabled, "angle_deg": angle_deg}

    # ---- Calculation / ruler tools ----

    def bm_distance(self, p1, p2):
        v1 = mathutils.Vector(p1); v2 = mathutils.Vector(p2)
        return {"distance": round((v2 - v1).length, 6), "delta": self._r(list(v2 - v1), 6)}

    def bm_angle_vectors(self, v1, v2):
        import math as _m
        a = mathutils.Vector(v1).normalized()
        b = mathutils.Vector(v2).normalized()
        dot = max(-1.0, min(1.0, a.dot(b)))
        return {"angle_deg": round(_m.degrees(_m.acos(dot)), 4), "dot": round(dot, 6)}

    def bm_world_to_local(self, name, point):
        o = bpy.data.objects.get(name)
        if not o:
            raise ValueError(f"Object not found: {name}")
        local = o.matrix_world.inverted() @ mathutils.Vector(point)
        return {"local": self._r(list(local), 6)}

    def bm_local_to_world(self, name, point):
        o = bpy.data.objects.get(name)
        if not o:
            raise ValueError(f"Object not found: {name}")
        world = o.matrix_world @ mathutils.Vector(point)
        return {"world": self._r(list(world), 6)}

    def bm_get_vertex(self, name, index, space='world'):
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH':
            raise ValueError(f"Mesh not found: {name}")
        if index < 0 or index >= len(o.data.vertices):
            raise ValueError(f"Index out of range: {index}")
        co = o.data.vertices[index].co
        if space == 'world':
            co = o.matrix_world @ co
        return {"name": name, "index": index, "position": self._r(list(co), 6), "space": space}

    def bm_set_vertex(self, name, index, position, space='world'):
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH':
            raise ValueError(f"Mesh not found: {name}")
        if index < 0 or index >= len(o.data.vertices):
            raise ValueError(f"Index out of range: {index}")
        p = mathutils.Vector(position)
        if space == 'world':
            p = o.matrix_world.inverted() @ p
        o.data.vertices[index].co = p
        o.data.update()
        return {"name": name, "index": index, "position": list(p), "space": "local"}

    def bm_find_closest_vertex(self, name, point):
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH':
            raise ValueError(f"Mesh not found: {name}")
        target = mathutils.Vector(point)
        best_idx = -1; best_dist = float('inf')
        mw = o.matrix_world
        for v in o.data.vertices:
            d = (mw @ v.co - target).length
            if d < best_dist:
                best_dist = d; best_idx = v.index
        return {"name": name, "index": best_idx, "distance": round(best_dist, 6), "position": self._r(list(mw @ o.data.vertices[best_idx].co), 6)}

    def bm_measure_edge_length(self, name, edge_index, space='world'):
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH':
            raise ValueError(f"Mesh not found: {name}")
        e = o.data.edges[edge_index]
        a = o.data.vertices[e.vertices[0]].co
        b = o.data.vertices[e.vertices[1]].co
        if space == 'world':
            a = o.matrix_world @ a
            b = o.matrix_world @ b
        return {"name": name, "edge": edge_index, "length": round((b - a).length, 6), "space": space}

    # ---- Format conversion ----

    def bm_export_format(self, filepath, format=None, selection_only=False, object_names=None, axis_up='Y', axis_forward='-Z', **kwargs):
        """Universal exporter. format inferred from extension if None. Supports: fbx, obj, gltf, glb, dae, stl, ply, x3d, usd, abc."""
        import os as _os
        if not format:
            ext = _os.path.splitext(filepath)[1].lower().lstrip('.')
            format = ext
        format = format.lower()
        if object_names:
            bpy.ops.object.select_all(action='DESELECT')
            for n in object_names:
                o = bpy.data.objects.get(n)
                if o: o.select_set(True)
            selection_only = True
        # Dispatch
        if format == 'fbx':
            bpy.ops.export_scene.fbx(filepath=filepath, use_selection=bool(selection_only),
                axis_up=axis_up, axis_forward=axis_forward, add_leaf_bones=False, bake_anim=True,
                bake_anim_use_all_actions=False, bake_anim_use_nla_strips=False,
                bake_space_transform=True, apply_unit_scale=True, path_mode='COPY', embed_textures=False)
        elif format == 'obj':
            bpy.ops.wm.obj_export(filepath=filepath, export_selected_objects=bool(selection_only),
                forward_axis=axis_forward, up_axis=axis_up)
        elif format in ('gltf', 'glb'):
            bpy.ops.export_scene.gltf(filepath=filepath, use_selection=bool(selection_only),
                export_format='GLB' if format == 'glb' else 'GLTF_SEPARATE')
        elif format == 'dae':
            bpy.ops.wm.collada_export(filepath=filepath, selected=bool(selection_only))
        elif format == 'stl':
            bpy.ops.wm.stl_export(filepath=filepath, export_selected_objects=bool(selection_only))
        elif format == 'ply':
            bpy.ops.wm.ply_export(filepath=filepath, export_selected_objects=bool(selection_only))
        elif format == 'x3d':
            bpy.ops.export_scene.x3d(filepath=filepath, use_selection=bool(selection_only))
        elif format in ('usd', 'usdc', 'usda'):
            bpy.ops.wm.usd_export(filepath=filepath, selected_objects_only=bool(selection_only))
        elif format == 'abc':
            bpy.ops.wm.alembic_export(filepath=filepath, selected=bool(selection_only))
        else:
            raise ValueError(f"Unsupported format: {format}")
        return {"filepath": filepath, "format": format, "exists": _os.path.exists(filepath),
                "size": _os.path.getsize(filepath) if _os.path.exists(filepath) else 0}

    def bm_import_format(self, filepath, format=None):
        """Universal importer. format inferred from extension if None."""
        import os as _os
        if not format:
            format = _os.path.splitext(filepath)[1].lower().lstrip('.')
        before = {o.name for o in bpy.data.objects}
        f = format.lower()
        if f == 'fbx':       bpy.ops.import_scene.fbx(filepath=filepath)
        elif f == 'obj':     bpy.ops.wm.obj_import(filepath=filepath)
        elif f in ('gltf','glb'): bpy.ops.import_scene.gltf(filepath=filepath)
        elif f == 'dae':     bpy.ops.wm.collada_import(filepath=filepath)
        elif f == 'stl':     bpy.ops.wm.stl_import(filepath=filepath)
        elif f == 'ply':     bpy.ops.wm.ply_import(filepath=filepath)
        elif f == 'x3d':     bpy.ops.import_scene.x3d(filepath=filepath)
        elif f in ('usd','usdc','usda'): bpy.ops.wm.usd_import(filepath=filepath)
        elif f == 'abc':     bpy.ops.wm.alembic_import(filepath=filepath)
        else:
            raise ValueError(f"Unsupported format: {format}")
        new_objs = [o.name for o in bpy.data.objects if o.name not in before]
        return {"filepath": filepath, "format": f, "imported": new_objs}

    def bm_convert_format(self, src_filepath, dst_filepath, src_format=None, dst_format=None):
        """Convert one file to another format in one call."""
        before = {o.name for o in bpy.data.objects}
        self.bm_import_format(src_filepath, src_format)
        new_objs = [o.name for o in bpy.data.objects if o.name not in before]
        bpy.ops.object.select_all(action='DESELECT')
        for n in new_objs:
            o = bpy.data.objects.get(n)
            if o: o.select_set(True)
        result = self.bm_export_format(dst_filepath, dst_format, selection_only=True)
        # Cleanup imported objects (optional - keep them in scene for now)
        return {"src": src_filepath, "dst": dst_filepath, "imported": new_objs, "result": result}

    # ---- Separation tools ----

    def bm_separate_by_vgroup(self, name, vgroup_name, new_name=None):
        """Separate verts in a vertex group into a new object."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH':
            raise ValueError(f"Mesh not found: {name}")
        vg = o.vertex_groups.get(vgroup_name)
        if not vg:
            raise ValueError(f"Vertex group not found: {vgroup_name}")
        before = {x.name for x in bpy.data.objects}
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        o.vertex_groups.active_index = vg.index
        bpy.ops.object.vertex_group_select()
        bpy.ops.mesh.separate(type='SELECTED')
        bpy.ops.object.mode_set(mode='OBJECT')
        new = [x.name for x in bpy.data.objects if x.name not in before]
        if new and new_name:
            bpy.data.objects[new[0]].name = new_name
            new = [new_name]
        return {"source": name, "vgroup": vgroup_name, "new_objects": new}

    def bm_separate_by_bbox(self, name, bbox_min, bbox_max, new_name=None, space='world'):
        """Separate verts inside an axis-aligned bbox into a new object."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH':
            raise ValueError(f"Mesh not found: {name}")
        mins = mathutils.Vector(bbox_min); maxs = mathutils.Vector(bbox_max)
        before = {x.name for x in bpy.data.objects}
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.mode_set(mode='OBJECT')
        mw = o.matrix_world
        for v in o.data.vertices:
            co = mw @ v.co if space == 'world' else v.co
            v.select = (mins.x <= co.x <= maxs.x and mins.y <= co.y <= maxs.y and mins.z <= co.z <= maxs.z)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.separate(type='SELECTED')
        bpy.ops.object.mode_set(mode='OBJECT')
        new = [x.name for x in bpy.data.objects if x.name not in before]
        if new and new_name:
            bpy.data.objects[new[0]].name = new_name
            new = [new_name]
        return {"source": name, "new_objects": new}

    def bm_separate_by_normal(self, name, axis, threshold=0.7, new_name=None):
        """Separate faces whose normal aligns with axis. axis: 'x','y','z','-x','-y','-z'."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH':
            raise ValueError(f"Mesh not found: {name}")
        sign = -1 if axis.startswith('-') else 1
        a = axis.lstrip('-').lower()
        ax_v = mathutils.Vector({'x':(sign,0,0),'y':(0,sign,0),'z':(0,0,sign)}[a])
        R = o.matrix_world.to_3x3()
        before = {x.name for x in bpy.data.objects}
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.mode_set(mode='OBJECT')
        for p in o.data.polygons:
            n = (R @ p.normal).normalized()
            p.select = n.dot(ax_v) >= float(threshold)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='FACE')
        bpy.ops.mesh.separate(type='SELECTED')
        bpy.ops.object.mode_set(mode='OBJECT')
        new = [x.name for x in bpy.data.objects if x.name not in before]
        if new and new_name:
            bpy.data.objects[new[0]].name = new_name
            new = [new_name]
        return {"source": name, "axis": axis, "new_objects": new}

    def bm_separate_by_material(self, name):
        """Separate mesh into one object per material slot."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH':
            raise ValueError(f"Mesh not found: {name}")
        before = {x.name for x in bpy.data.objects}
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.separate(type='MATERIAL')
        bpy.ops.object.mode_set(mode='OBJECT')
        new = [x.name for x in bpy.data.objects if x.name not in before]
        return {"source": name, "new_objects": new}

    # ---- Leveling / alignment ----

    def bm_level_to_ground(self, name, axis='z', value=0.0):
        """Translate object so its min along `axis` lands at `value`. axis: x|y|z."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH':
            raise ValueError(f"Mesh not found: {name}")
        ai = {'x':0,'y':1,'z':2}[axis.lower()]
        bb = [o.matrix_world @ mathutils.Vector(c) for c in o.bound_box]
        cur_min = min(v[ai] for v in bb)
        delta = float(value) - cur_min
        loc = list(o.location); loc[ai] += delta
        o.location = mathutils.Vector(loc)
        return {"name": name, "axis": axis, "delta": delta, "new_location": list(o.location)}

    def bm_center_to_origin(self, name, axes='xyz'):
        """Translate object so its bbox center on selected axes lands at origin. axes: substring of 'xyz'."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH':
            raise ValueError(f"Mesh not found: {name}")
        bb = [o.matrix_world @ mathutils.Vector(c) for c in o.bound_box]
        mins = [min(v[i] for v in bb) for i in range(3)]
        maxs = [max(v[i] for v in bb) for i in range(3)]
        deltas = [0,0,0]
        for ax in axes.lower():
            i = {'x':0,'y':1,'z':2}[ax]
            center = (mins[i] + maxs[i]) / 2
            deltas[i] = -center
        loc = list(o.location)
        for i in range(3):
            loc[i] += deltas[i]
        o.location = mathutils.Vector(loc)
        return {"name": name, "axes": axes, "deltas": deltas, "new_location": list(o.location)}

    def bm_align_objects(self, names, axis='z', target='MIN', value=None):
        """Align bboxes of multiple objects along axis. target: MIN|MAX|CENTER.
        If value None, uses the first object's value as reference."""
        ai = {'x':0,'y':1,'z':2}[axis.lower()]
        objs = [bpy.data.objects.get(n) for n in names if bpy.data.objects.get(n)]
        if not objs:
            return {"aligned": 0}
        def get_ref(o):
            bb = [o.matrix_world @ mathutils.Vector(c) for c in o.bound_box]
            vals = [v[ai] for v in bb]
            if target == 'MIN': return min(vals)
            if target == 'MAX': return max(vals)
            return (min(vals)+max(vals))/2
        ref = float(value) if value is not None else get_ref(objs[0])
        for o in objs:
            cur = get_ref(o)
            delta = ref - cur
            loc = list(o.location); loc[ai] += delta
            o.location = mathutils.Vector(loc)
        return {"aligned": len(objs), "axis": axis, "target": target, "value": ref}

    def bm_distribute_objects(self, names, axis='x', spacing=None, anchor='CENTER'):
        """Distribute objects evenly along axis. If spacing=None, uses range/(n-1)."""
        ai = {'x':0,'y':1,'z':2}[axis.lower()]
        objs = [bpy.data.objects.get(n) for n in names if bpy.data.objects.get(n)]
        if len(objs) < 2:
            return {"distributed": 0}
        def get_pos(o):
            bb = [o.matrix_world @ mathutils.Vector(c) for c in o.bound_box]
            vals = [v[ai] for v in bb]
            if anchor == 'MIN': return min(vals)
            if anchor == 'MAX': return max(vals)
            return (min(vals)+max(vals))/2
        positions = [(get_pos(o), o) for o in objs]
        positions.sort(key=lambda p: p[0])
        first = positions[0][0]; last = positions[-1][0]
        n = len(positions)
        if spacing is None:
            spacing = (last - first) / (n - 1)
        for i, (_, o) in enumerate(positions):
            target = first + i * spacing
            cur = get_pos(o)
            delta = target - cur
            loc = list(o.location); loc[ai] += delta
            o.location = mathutils.Vector(loc)
        return {"distributed": n, "axis": axis, "spacing": round(float(spacing), 6)}

    def bm_snap_to_grid(self, name, grid_size=0.1, snap_translation=True, snap_rotation=False):
        """Snap object location to nearest grid point. Optionally also snap rotation to 90° steps."""
        o = bpy.data.objects.get(name)
        if not o:
            raise ValueError(f"Object not found: {name}")
        if snap_translation:
            g = float(grid_size)
            o.location = mathutils.Vector(tuple(round(v / g) * g for v in o.location))
        if snap_rotation:
            import math as _m
            step = _m.pi / 2
            o.rotation_euler = (round(o.rotation_euler.x / step) * step,
                                round(o.rotation_euler.y / step) * step,
                                round(o.rotation_euler.z / step) * step)
        return {"name": name, "location": self._r(list(o.location), 6)}

    def bm_align_normal_to_axis(self, name, face_index, target_axis='z'):
        """Rotate entire object so face's normal aligns with world axis."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH':
            raise ValueError(f"Mesh not found: {name}")
        if face_index < 0 or face_index >= len(o.data.polygons):
            raise ValueError(f"Face index out of range: {face_index}")
        normal = (o.matrix_world.to_3x3() @ o.data.polygons[face_index].normal).normalized()
        ta = {'x':mathutils.Vector((1,0,0)),'y':mathutils.Vector((0,1,0)),'z':mathutils.Vector((0,0,1)),
              '-x':mathutils.Vector((-1,0,0)),'-y':mathutils.Vector((0,-1,0)),'-z':mathutils.Vector((0,0,-1))}[target_axis.lower()]
        axis = normal.cross(ta)
        import math as _m
        dot = max(-1.0, min(1.0, normal.dot(ta)))
        ang = _m.acos(dot)
        if axis.length < 1e-9:
            return {"name": name, "angle_deg": 0}
        R = mathutils.Matrix.Rotation(ang, 4, axis.normalized())
        o.matrix_world = R @ o.matrix_world
        return {"name": name, "angle_deg": round(_m.degrees(ang), 4), "axis": target_axis}

    # ---- Search / find ----

    def bm_find_objects(self, pattern, type=None):
        """Find objects by name fnmatch pattern (e.g. 'Gun_*', '*Arm*')."""
        import fnmatch
        out = []
        for o in bpy.data.objects:
            if type and o.type != type:
                continue
            if fnmatch.fnmatch(o.name, pattern):
                out.append({"name": o.name, "type": o.type})
        return {"matched": out, "count": len(out)}

    def bm_find_by_property(self, type=None, has_material=None, has_vgroup=None, has_modifier=None, has_parent=None):
        """Filter objects by properties."""
        out = []
        for o in bpy.data.objects:
            if type and o.type != type:
                continue
            if has_material is not None:
                names = [s.material.name for s in o.material_slots if s.material]
                if has_material and has_material not in names: continue
                if has_material == "" and names: continue
            if has_vgroup is not None and o.type == 'MESH':
                if has_vgroup not in {vg.name for vg in o.vertex_groups}: continue
            if has_modifier is not None:
                types = {m.type for m in o.modifiers}
                if has_modifier not in types: continue
            if has_parent is not None:
                if has_parent and not o.parent: continue
                if has_parent == False and o.parent: continue
            out.append({"name": o.name, "type": o.type})
        return {"matched": out, "count": len(out)}

    def bm_select_pattern(self, pattern, deselect_others=True, type=None):
        """Select all objects matching name pattern."""
        import fnmatch
        if deselect_others:
            bpy.ops.object.select_all(action='DESELECT')
        selected = []
        for o in bpy.data.objects:
            if type and o.type != type: continue
            if fnmatch.fnmatch(o.name, pattern):
                o.select_set(True); selected.append(o.name)
        return {"selected": selected}

    def bm_select_all(self, type=None):
        """Select all (or all of type)."""
        if type:
            bpy.ops.object.select_all(action='DESELECT')
            selected = []
            for o in bpy.data.objects:
                if o.type == type:
                    o.select_set(True); selected.append(o.name)
            return {"selected": selected}
        bpy.ops.object.select_all(action='SELECT')
        return {"selected_all": True}

    # ---- Object-level transform shortcuts ----

    def bm_translate(self, name, delta):
        o = bpy.data.objects.get(name)
        if not o: raise ValueError(f"Not found: {name}")
        o.location = mathutils.Vector(o.location) + mathutils.Vector(delta)
        return {"name": name, "new_location": list(o.location)}

    def bm_rotate(self, name, axis='z', angle_deg=0, pivot='ORIGIN'):
        """Rotate object around axis. pivot: ORIGIN|MEDIAN|CENTROID|[x,y,z]."""
        import math as _m
        o = bpy.data.objects.get(name)
        if not o: raise ValueError(f"Not found: {name}")
        if isinstance(axis, str):
            ax = {'x':(1,0,0),'y':(0,1,0),'z':(0,0,1)}[axis.lower()]
        else:
            ax = tuple(axis)
        R = mathutils.Matrix.Rotation(_m.radians(float(angle_deg)), 4, mathutils.Vector(ax).normalized())
        if pivot == 'ORIGIN':
            o.matrix_world = R @ o.matrix_world
        else:
            if pivot in ('MEDIAN', 'CENTROID') and o.type == 'MESH':
                bb = [o.matrix_world @ mathutils.Vector(c) for c in o.bound_box]
                pv = sum(bb, mathutils.Vector()) / 8
            else:
                pv = mathutils.Vector(pivot)
            T1 = mathutils.Matrix.Translation(-pv)
            T2 = mathutils.Matrix.Translation(pv)
            o.matrix_world = T2 @ R @ T1 @ o.matrix_world
        return {"name": name, "axis": axis, "angle_deg": angle_deg}

    def bm_scale(self, name, factor):
        o = bpy.data.objects.get(name)
        if not o: raise ValueError(f"Not found: {name}")
        if isinstance(factor, (int, float)):
            o.scale = (float(factor),) * 3
        else:
            o.scale = mathutils.Vector(factor)
        return {"name": name, "scale": list(o.scale)}

    def bm_mirror_object(self, name, axis='x'):
        """Mirror object across world axis plane (negates scale on axis)."""
        o = bpy.data.objects.get(name)
        if not o: raise ValueError(f"Not found: {name}")
        ai = {'x':0,'y':1,'z':2}[axis.lower()]
        sc = list(o.scale); sc[ai] *= -1
        o.scale = mathutils.Vector(sc)
        return {"name": name, "axis": axis, "scale": list(o.scale)}

    def bm_flatten_verts(self, name, axis='z', value=0.0, vert_filter=None):
        """Set verts in filter to all have axis coord = value (flatten to plane)."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        verts = self._filter_verts(o, vert_filter or {"all": True})
        ai = {'x':0,'y':1,'z':2}[axis.lower()]
        for v in verts:
            v.co[ai] = float(value)
        o.data.update()
        return {"name": name, "flattened": len(verts), "axis": axis, "value": value}

    # ---- Cursor ----

    def bm_cursor_to_selected(self):
        """Move 3D cursor to selection center."""
        sel = [o for o in bpy.context.selected_objects]
        if not sel:
            return {"cursor": list(bpy.context.scene.cursor.location), "warning": "no selection"}
        avg = sum((o.matrix_world.translation for o in sel), mathutils.Vector()) / len(sel)
        bpy.context.scene.cursor.location = avg
        return {"cursor": list(avg)}

    def bm_cursor_to_origin(self):
        bpy.context.scene.cursor.location = (0,0,0)
        return {"cursor": [0,0,0]}

    def bm_cursor_to_object(self, name):
        o = bpy.data.objects.get(name)
        if not o: raise ValueError(f"Not found: {name}")
        bpy.context.scene.cursor.location = o.matrix_world.translation
        return {"cursor": list(bpy.context.scene.cursor.location)}

    def bm_object_to_cursor(self, name):
        o = bpy.data.objects.get(name)
        if not o: raise ValueError(f"Not found: {name}")
        o.location = mathutils.Vector(bpy.context.scene.cursor.location)
        return {"name": name, "new_location": list(o.location)}

    # ---- Collections ----

    def bm_create_collection(self, name, parent_collection=None):
        col = bpy.data.collections.get(name)
        if col is None:
            col = bpy.data.collections.new(name)
            parent = bpy.data.collections.get(parent_collection) if parent_collection else bpy.context.scene.collection
            parent.children.link(col)
        return {"collection": name}

    def bm_add_to_collection(self, object_names, collection_name):
        col = bpy.data.collections.get(collection_name)
        if not col: raise ValueError(f"Collection not found: {collection_name}")
        n = 0
        for nm in object_names:
            o = bpy.data.objects.get(nm)
            if o and o.name not in col.objects:
                col.objects.link(o); n += 1
        return {"collection": collection_name, "added": n}

    def bm_remove_from_collection(self, object_names, collection_name):
        col = bpy.data.collections.get(collection_name)
        if not col: raise ValueError(f"Collection not found: {collection_name}")
        n = 0
        for nm in object_names:
            o = bpy.data.objects.get(nm)
            if o and o.name in col.objects:
                col.objects.unlink(o); n += 1
        return {"collection": collection_name, "removed": n}

    def bm_list_collections(self):
        out = []
        for c in bpy.data.collections:
            out.append({"name": c.name, "objects": [o.name for o in c.objects], "children": [c2.name for c2 in c.children]})
        return {"collections": out}

    # ---- Mesh ops ----

    def bm_triangulate(self, name):
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.quads_convert_to_tris(quad_method='BEAUTY')
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"name": name, "polygons": len(o.data.polygons)}

    def bm_fill_face(self, name, vert_indices):
        """Fill polygon from given verts (must form a closed loop)."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.mesh.select_mode(type='VERT')
        bpy.ops.object.mode_set(mode='OBJECT')
        for vi in vert_indices:
            if 0 <= vi < len(o.data.vertices):
                o.data.vertices[vi].select = True
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.edge_face_add()
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"name": name}

    def bm_loop_cut(self, name, edge_index, cuts=1):
        """Add loop cut(s) running through an edge. Note: relies on operator availability."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.mode_set(mode='OBJECT')
        if 0 <= edge_index < len(o.data.edges):
            o.data.edges[edge_index].select = True
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.loop_multi_select(ring=False)
        bpy.ops.mesh.subdivide(number_cuts=int(cuts))
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"name": name, "cuts": cuts}

    def bm_select_linked(self, name, vert_index=None):
        """In EDIT mode, select all verts connected to the given seed vert (or current selection)."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        if vert_index is not None:
            bpy.ops.mesh.select_all(action='DESELECT')
            bpy.ops.object.mode_set(mode='OBJECT')
            if 0 <= vert_index < len(o.data.vertices):
                o.data.vertices[vert_index].select = True
            bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_linked()
        bpy.ops.object.mode_set(mode='OBJECT')
        selected = sum(1 for v in o.data.vertices if v.select)
        return {"name": name, "selected_verts": selected}

    # ---- Window / layout ----

    def bm_set_workspace(self, name):
        """Switch to Blender workspace by name (Layout/Modeling/Sculpting/UV Editing/Animation/...)."""
        ws = bpy.data.workspaces.get(name)
        if not ws:
            raise ValueError(f"Workspace not found: {name}. Available: {[w.name for w in bpy.data.workspaces]}")
        bpy.context.window.workspace = ws
        return {"workspace": name}

    def bm_list_workspaces(self):
        return {"workspaces": [w.name for w in bpy.data.workspaces], "current": bpy.context.window.workspace.name}

    def bm_split_area(self, direction='VERTICAL', factor=0.5):
        """Split active 3D viewport area. direction: VERTICAL|HORIZONTAL."""
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                with bpy.context.temp_override(area=area):
                    bpy.ops.screen.area_split(direction=direction, factor=float(factor))
                return {"area": area.type, "direction": direction}
        return {"warning": "no 3D viewport found"}

    # ---- Precision mesh ----

    def bm_set_edge_position(self, name, edge_index, head_pos=None, tail_pos=None, space='world'):
        """Set exact positions of an edge's two vertices."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        e = o.data.edges[edge_index]
        mw_inv = o.matrix_world.inverted()
        if head_pos is not None:
            p = mathutils.Vector(head_pos)
            if space == 'world': p = mw_inv @ p
            o.data.vertices[e.vertices[0]].co = p
        if tail_pos is not None:
            p = mathutils.Vector(tail_pos)
            if space == 'world': p = mw_inv @ p
            o.data.vertices[e.vertices[1]].co = p
        o.data.update()
        return {"name": name, "edge": edge_index}

    def bm_align_edge_to_axis(self, name, edge_index, axis='x', fix='HEAD'):
        """Move tail vert so edge is exactly along axis. fix: HEAD (move tail) | TAIL (move head) | CENTER (both)."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        e = o.data.edges[edge_index]
        a, b = o.data.vertices[e.vertices[0]], o.data.vertices[e.vertices[1]]
        ai = {'x':0,'y':1,'z':2}[axis.lower()]
        length = (b.co - a.co).length
        direction = mathutils.Vector((0,0,0)); direction[ai] = 1.0
        if fix == 'HEAD':
            b.co = a.co + direction * length
        elif fix == 'TAIL':
            a.co = b.co - direction * length
        else:  # CENTER
            mid = (a.co + b.co) / 2
            a.co = mid - direction * (length/2)
            b.co = mid + direction * (length/2)
        o.data.update()
        return {"name": name, "edge": edge_index, "axis": axis, "fix": fix}

    def bm_perfect_box(self, name, mins, maxs, location=None):
        """Create perfect axis-aligned box mesh with exact corner coords mins/maxs (object-local)."""
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
        mins_v = mathutils.Vector(mins); maxs_v = mathutils.Vector(maxs)
        verts = [
            (mins_v.x, mins_v.y, mins_v.z), (maxs_v.x, mins_v.y, mins_v.z),
            (maxs_v.x, maxs_v.y, mins_v.z), (mins_v.x, maxs_v.y, mins_v.z),
            (mins_v.x, mins_v.y, maxs_v.z), (maxs_v.x, mins_v.y, maxs_v.z),
            (maxs_v.x, maxs_v.y, maxs_v.z), (mins_v.x, maxs_v.y, maxs_v.z),
        ]
        faces = [(0,1,2,3),(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)]
        me = bpy.data.meshes.new(name + "_Mesh")
        me.from_pydata(verts, [], faces)
        me.update()
        obj = bpy.data.objects.new(name, me)
        if location:
            obj.location = mathutils.Vector(location)
        bpy.context.collection.objects.link(obj)
        return {"name": name, "verts": len(verts), "faces": len(faces), "mins": list(mins), "maxs": list(maxs)}

    def bm_round_vert_positions(self, name, decimals=3, vert_filter=None):
        """Round vert coords to N decimals — kills sub-millimeter noise."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        verts = self._filter_verts(o, vert_filter or {"all": True})
        for v in verts:
            v.co = mathutils.Vector((round(v.co.x, int(decimals)), round(v.co.y, int(decimals)), round(v.co.z, int(decimals))))
        o.data.update()
        return {"name": name, "rounded": len(verts), "decimals": decimals}

    def bm_make_orthogonal_corner(self, name, vert_index):
        """At a vertex shared by multiple edges, snap connected edges to nearest cardinal axis."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        v = o.data.vertices[vert_index]
        # Find connected edges
        adj_edges = [e for e in o.data.edges if vert_index in e.vertices]
        adjusted = 0
        for e in adj_edges:
            other = e.vertices[0] if e.vertices[1] == vert_index else e.vertices[1]
            ov = o.data.vertices[other]
            d = ov.co - v.co
            # Snap to nearest axis
            absd = [abs(d.x), abs(d.y), abs(d.z)]
            ai = absd.index(max(absd))
            length = absd[ai]
            sign = 1 if d[ai] >= 0 else -1
            new_d = mathutils.Vector((0,0,0))
            new_d[ai] = sign * length
            ov.co = v.co + new_d
            adjusted += 1
        o.data.update()
        return {"name": name, "vert": vert_index, "edges_snapped": adjusted}

    # ---- Curves ----

    def bm_create_curve(self, name, points, type='BEZIER', cyclic=False, resolution=12):
        """Create curve from control points.
        type: BEZIER|NURBS|POLY. points = [[x,y,z], ...]. cyclic: closed loop."""
        cu = bpy.data.curves.new(name + "_Curve", 'CURVE')
        cu.dimensions = '3D'
        cu.resolution_u = int(resolution)
        spline = cu.splines.new(type)
        if type == 'BEZIER':
            spline.bezier_points.add(len(points) - 1)
            for i, p in enumerate(points):
                bp = spline.bezier_points[i]
                bp.co = mathutils.Vector(p)
                bp.handle_left_type = 'AUTO'
                bp.handle_right_type = 'AUTO'
        else:
            spline.points.add(len(points) - 1)
            for i, p in enumerate(points):
                spline.points[i].co = (p[0], p[1], p[2], 1.0)
        spline.use_cyclic_u = bool(cyclic)
        obj = bpy.data.objects.new(name, cu)
        bpy.context.collection.objects.link(obj)
        return {"name": name, "type": type, "points": len(points), "cyclic": cyclic}

    def bm_add_curve_primitive(self, type, name=None, location=(0,0,0), radius=1.0):
        """type: BEZIER_CIRCLE|BEZIER_CURVE|NURBS_CIRCLE|NURBS_PATH."""
        t = type.upper()
        opmap = {
            'BEZIER_CIRCLE': lambda: bpy.ops.curve.primitive_bezier_circle_add(radius=radius, location=location),
            'BEZIER_CURVE':  lambda: bpy.ops.curve.primitive_bezier_curve_add(radius=radius, location=location),
            'NURBS_CIRCLE':  lambda: bpy.ops.curve.primitive_nurbs_circle_add(radius=radius, location=location),
            'NURBS_PATH':    lambda: bpy.ops.curve.primitive_nurbs_path_add(radius=radius, location=location),
        }
        if t not in opmap:
            raise ValueError(f"Unknown curve type: {type}. Options: {list(opmap)}")
        opmap[t]()
        new = bpy.context.view_layer.objects.active
        if name:
            new.name = name
        return {"name": new.name, "type": t}

    def bm_curve_to_mesh(self, name):
        """Convert curve to mesh."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'CURVE': raise ValueError(f"Curve not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.convert(target='MESH')
        return {"name": name, "now_type": o.type}

    def bm_set_curve_bevel(self, name, depth=0.05, resolution=4, bevel_object=None):
        """Add bevel to curve (gives it thickness). bevel_object: name of another curve for cross-section."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'CURVE': raise ValueError(f"Curve not found: {name}")
        cu = o.data
        if bevel_object:
            bo = bpy.data.objects.get(bevel_object)
            if bo and bo.type == 'CURVE':
                cu.bevel_mode = 'OBJECT'
                cu.bevel_object = bo
        else:
            cu.bevel_depth = float(depth)
            cu.bevel_resolution = int(resolution)
        return {"name": name, "depth": depth, "resolution": resolution}

    # ---- Topology ----

    def bm_bridge_edge_loops(self, name, edge_indices=None):
        """Bridge selected edge loops. edge_indices: list of edge indices forming two loops, or None to use current selection."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        if edge_indices is not None:
            bpy.ops.mesh.select_mode(type='EDGE')
            bpy.ops.mesh.select_all(action='DESELECT')
            bpy.ops.object.mode_set(mode='OBJECT')
            es = set(edge_indices)
            for e in o.data.edges:
                e.select = e.index in es
            bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.bridge_edge_loops()
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"name": name}

    def bm_grid_fill(self, name, edge_indices=None, span=2):
        """Grid-fill a closed edge loop. edge_indices: edges forming closed loop."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        if edge_indices is not None:
            bpy.ops.mesh.select_mode(type='EDGE')
            bpy.ops.mesh.select_all(action='DESELECT')
            bpy.ops.object.mode_set(mode='OBJECT')
            es = set(edge_indices)
            for e in o.data.edges:
                e.select = e.index in es
            bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.fill_grid(span=int(span))
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"name": name, "span": span}

    def bm_quadrify(self, name, face_threshold_deg=40, shape_threshold_deg=40):
        """Convert tris to quads."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        import math as _m
        bpy.ops.mesh.tris_convert_to_quads(face_threshold=_m.radians(face_threshold_deg),
                                            shape_threshold=_m.radians(shape_threshold_deg))
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"name": name, "polygons": len(o.data.polygons)}

    def bm_check_topology(self, name):
        """Report topology stats: tris, quads, ngons, non-manifold edges, isolated verts."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        tris=0; quads=0; ngons=0
        for p in o.data.polygons:
            n = len(p.vertices)
            if n == 3: tris += 1
            elif n == 4: quads += 1
            else: ngons += 1
        # Non-manifold edges via bmesh
        import bmesh
        bm = bmesh.new(); bm.from_mesh(o.data)
        non_manifold = sum(1 for e in bm.edges if not e.is_manifold)
        boundary = sum(1 for e in bm.edges if e.is_boundary)
        loose_verts = sum(1 for v in bm.verts if not v.link_edges)
        loose_edges = sum(1 for e in bm.edges if not e.link_faces)
        bm.free()
        return {"name": name, "verts": len(o.data.vertices), "edges": len(o.data.edges),
                "tris": tris, "quads": quads, "ngons": ngons,
                "non_manifold_edges": non_manifold, "boundary_edges": boundary,
                "loose_verts": loose_verts, "loose_edges": loose_edges}

    def bm_select_ngons(self, name):
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_face_by_sides(number=4, type='GREATER')
        bpy.ops.object.mode_set(mode='OBJECT')
        n = sum(1 for p in o.data.polygons if p.select)
        return {"name": name, "ngons_selected": n}

    def bm_select_tris(self, name):
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_face_by_sides(number=3, type='EQUAL')
        bpy.ops.object.mode_set(mode='OBJECT')
        n = sum(1 for p in o.data.polygons if p.select)
        return {"name": name, "tris_selected": n}

    def bm_select_non_manifold(self, name):
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='EDGE')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.mesh.select_non_manifold()
        bpy.ops.object.mode_set(mode='OBJECT')
        n = sum(1 for e in o.data.edges if e.select)
        return {"name": name, "non_manifold_edges": n}

    def bm_dissolve_limited(self, name, angle_deg=5):
        """Limited Dissolve — removes extra edges/verts that don't affect shape (cleans topology)."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        before = (len(o.data.vertices), len(o.data.edges), len(o.data.polygons))
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        import math as _m
        bpy.ops.mesh.dissolve_limited(angle_limit=_m.radians(float(angle_deg)))
        bpy.ops.object.mode_set(mode='OBJECT')
        after = (len(o.data.vertices), len(o.data.edges), len(o.data.polygons))
        return {"name": name, "before": before, "after": after}

    def bm_clean_topology(self, name, merge_distance=0.0001, quadrify=True, recalc_normals=True, remove_loose=True):
        """One-shot topology cleanup: merge doubles + recalc normals + tris→quads + remove loose geom."""
        steps = []
        if merge_distance > 0:
            r = self.bm_remove_doubles(name, merge_distance); steps.append({"merged": r["merged"]})
        if recalc_normals:
            self.bm_recalc_normals(name, False); steps.append({"normals": "recalculated"})
        if quadrify:
            r = self.bm_quadrify(name); steps.append({"polys_after_quadrify": r["polygons"]})
        if remove_loose:
            r = self.bm_remove_loose_geometry(name); steps.append(r)
        return {"name": name, "steps": steps}

    def bm_decimate(self, name, ratio=0.5):
        """Reduce poly count via Decimate modifier (applied immediately)."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        before = len(o.data.polygons)
        m = o.modifiers.new("Decimate_tmp", 'DECIMATE')
        m.decimate_type = 'COLLAPSE'
        m.ratio = float(ratio)
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.modifier_apply(modifier=m.name)
        return {"name": name, "before": before, "after": len(o.data.polygons), "ratio": ratio}

    def bm_add_subsurf(self, name, levels=2, render_levels=None):
        """Add Subdivision Surface modifier (smoothing)."""
        o = bpy.data.objects.get(name)
        if not o: raise ValueError(f"Not found: {name}")
        m = o.modifiers.new("Subsurf", 'SUBSURF')
        m.levels = int(levels)
        m.render_levels = int(render_levels) if render_levels is not None else int(levels)
        return {"name": name, "levels": levels}

    def bm_remove_loose_geometry(self, name):
        """Delete unconnected verts + edges + faces."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        before = (len(o.data.vertices), len(o.data.edges), len(o.data.polygons))
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.mesh.select_loose()
        bpy.ops.mesh.delete(type='VERT')
        bpy.ops.object.mode_set(mode='OBJECT')
        after = (len(o.data.vertices), len(o.data.edges), len(o.data.polygons))
        return {"name": name, "before": before, "after": after}

    # ---- Topology QA ----

    def bm_pole_count(self, name):
        """Count verts by edge-degree. Quad-clean topology should be MOSTLY 4-edge poles.
        Avoid: 6+ edge poles (fan triangulation), or many 3-edge poles outside edge corners.
        Returns: {degree: count} histogram + warnings."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        from collections import Counter
        # Count edges per vert
        deg = Counter()
        edge_count = [0] * len(o.data.vertices)
        for e in o.data.edges:
            edge_count[e.vertices[0]] += 1
            edge_count[e.vertices[1]] += 1
        for c in edge_count:
            deg[c] += 1
        deg_d = dict(sorted(deg.items()))
        warnings = []
        if sum(v for k, v in deg.items() if k >= 6) > 0:
            warnings.append(f"FAN POLES: {sum(v for k, v in deg.items() if k >= 6)} verts with 6+ edges. Probably triangle fans — clean with bm_dissolve_limited or remesh.")
        n4 = deg.get(4, 0); ntotal = sum(deg.values())
        quad_pct = 100 * n4 / max(ntotal, 1)
        if quad_pct < 60 and ntotal > 20:
            warnings.append(f"Only {quad_pct:.1f}% of verts are 4-pole (quad topology indicator). Aim for 80%+.")
        return {"name": name, "degrees": deg_d, "quad_pole_pct": round(quad_pct, 1), "warnings": warnings}

    def bm_select_high_poles(self, name, min_edges=6):
        """Select verts with >= min_edges connections (fan-poles, bad topology)."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        edge_count = [0] * len(o.data.vertices)
        for e in o.data.edges:
            edge_count[e.vertices[0]] += 1
            edge_count[e.vertices[1]] += 1
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='VERT')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.mode_set(mode='OBJECT')
        selected = 0
        for v in o.data.vertices:
            if edge_count[v.index] >= int(min_edges):
                v.select = True; selected += 1
        return {"name": name, "selected": selected, "min_edges": min_edges}

    def bm_select_stretched_tris(self, name, ratio=3.0):
        """Select triangles whose longest edge is `ratio`× shorter edge (stretched / sliver tris)."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='FACE')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.mode_set(mode='OBJECT')
        selected = 0
        for p in o.data.polygons:
            if len(p.vertices) != 3: continue
            v = [o.data.vertices[i].co for i in p.vertices]
            edges = [(v[0]-v[1]).length, (v[1]-v[2]).length, (v[2]-v[0]).length]
            if min(edges) > 0 and max(edges) / min(edges) >= float(ratio):
                p.select = True; selected += 1
        return {"name": name, "stretched_tris_selected": selected, "ratio": ratio}

    def bm_warn_topology(self, name):
        """Comprehensive topology quality report. Lists ALL issues with severity."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        warnings = []
        # Stats
        tris=0; quads=0; ngons=0
        for p in o.data.polygons:
            n = len(p.vertices)
            if n == 3: tris += 1
            elif n == 4: quads += 1
            else: ngons += 1
        total = tris + quads + ngons
        # Quad ratio
        if total > 0:
            qpct = 100 * quads / total
            if qpct < 70:
                warnings.append({"severity": "HIGH" if qpct < 50 else "MED", "issue": f"Low quad ratio: {qpct:.0f}% (target 80%+)"})
        if tris > total * 0.2 and total > 10:
            warnings.append({"severity": "MED", "issue": f"Many triangles: {tris}/{total}"})
        if ngons > 0:
            warnings.append({"severity": "MED", "issue": f"{ngons} n-gons (5+ sided faces) — split into quads"})
        # Pole check
        edge_count = [0] * len(o.data.vertices)
        for e in o.data.edges:
            edge_count[e.vertices[0]] += 1
            edge_count[e.vertices[1]] += 1
        fan_poles = sum(1 for c in edge_count if c >= 6)
        if fan_poles > 0:
            warnings.append({"severity": "HIGH", "issue": f"{fan_poles} fan-poles (6+ edges per vert) — classic decimate junk"})
        # Non-manifold
        import bmesh
        bm = bmesh.new(); bm.from_mesh(o.data)
        nm = sum(1 for e in bm.edges if not e.is_manifold)
        loose_v = sum(1 for v in bm.verts if not v.link_edges)
        bm.free()
        if nm > 0:
            warnings.append({"severity": "HIGH", "issue": f"{nm} non-manifold edges — model has holes/T-junctions"})
        if loose_v > 0:
            warnings.append({"severity": "LOW", "issue": f"{loose_v} loose verts — run bm_remove_loose_geometry"})
        # Stretched tri check
        stretched = 0
        for p in o.data.polygons:
            if len(p.vertices) != 3: continue
            v = [o.data.vertices[i].co for i in p.vertices]
            edges = [(v[0]-v[1]).length, (v[1]-v[2]).length, (v[2]-v[0]).length]
            if min(edges) > 0 and max(edges) / min(edges) >= 3.0:
                stretched += 1
        if stretched > 0:
            warnings.append({"severity": "MED", "issue": f"{stretched} stretched/sliver triangles"})
        score = 100
        for w in warnings:
            score -= {"HIGH": 25, "MED": 10, "LOW": 3}[w["severity"]]
        score = max(0, score)
        return {"name": name, "stats": {"verts": len(o.data.vertices), "edges": len(o.data.edges), "tris": tris, "quads": quads, "ngons": ngons}, "warnings": warnings, "topology_score": score}

    # ---- Reference / blueprint setup ----

    def bm_add_reference_image(self, filepath, axis='FRONT', location=(0,0,0), size=1.0, opacity=0.5):
        """Add background reference image (image empty) for blueprint modeling.
        axis: FRONT|BACK|LEFT|RIGHT|TOP|BOTTOM — determines orientation."""
        import os as _os
        if not _os.path.exists(filepath):
            raise ValueError(f"Image not found: {filepath}")
        bpy.ops.object.empty_add(type='IMAGE', location=location)
        e = bpy.context.view_layer.objects.active
        e.data = bpy.data.images.load(filepath)
        e.empty_display_size = float(size)
        e.color = (1, 1, 1, float(opacity))
        # Orient
        import math as _m
        rot = {
            'FRONT':  (_m.radians(90), 0, 0),
            'BACK':   (_m.radians(90), 0, _m.radians(180)),
            'LEFT':   (_m.radians(90), 0, _m.radians(-90)),
            'RIGHT':  (_m.radians(90), 0, _m.radians(90)),
            'TOP':    (0, 0, 0),
            'BOTTOM': (_m.radians(180), 0, 0),
        }
        e.rotation_euler = rot.get(axis.upper(), (0,0,0))
        e.name = f"Ref_{axis}_{_os.path.basename(filepath)}"
        return {"name": e.name, "axis": axis, "filepath": filepath}

    def bm_select_edge_loop(self, name, edge_index):
        """Alt+click equivalent — select edge loop from seed edge."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='EDGE')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.mode_set(mode='OBJECT')
        if 0 <= edge_index < len(o.data.edges):
            o.data.edges[edge_index].select = True
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.loop_multi_select(ring=False)
        bpy.ops.object.mode_set(mode='OBJECT')
        n = sum(1 for e in o.data.edges if e.select)
        return {"name": name, "loop_edges": n}

    def bm_select_edge_ring(self, name, edge_index):
        """Ctrl+Alt+click equivalent — select edge ring."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='EDGE')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.mode_set(mode='OBJECT')
        if 0 <= edge_index < len(o.data.edges):
            o.data.edges[edge_index].select = True
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.loop_multi_select(ring=True)
        bpy.ops.object.mode_set(mode='OBJECT')
        n = sum(1 for e in o.data.edges if e.select)
        return {"name": name, "ring_edges": n}

    def bm_inset_faces(self, name, face_indices, thickness=0.02, depth=0.0, individual=False):
        """Inset faces (used to add edge loops around features without ruining topology)."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='FACE')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.mode_set(mode='OBJECT')
        fs = set(face_indices)
        for p in o.data.polygons:
            p.select = p.index in fs
        bpy.ops.object.mode_set(mode='EDIT')
        if individual:
            bpy.ops.mesh.inset(thickness=float(thickness), depth=float(depth), use_individual=True)
        else:
            bpy.ops.mesh.inset(thickness=float(thickness), depth=float(depth))
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"name": name, "inset_faces": len(face_indices), "thickness": thickness}

    def bm_shrinkwrap_to(self, name, target_name, wrap_method='NEAREST_SURFACEPOINT', offset=0.0, apply=False):
        """Add Shrinkwrap modifier to project mesh onto target (great for retopo)."""
        o = bpy.data.objects.get(name)
        t = bpy.data.objects.get(target_name)
        if not o or not t: raise ValueError("Object or target not found")
        m = o.modifiers.new("Shrinkwrap", 'SHRINKWRAP')
        m.target = t
        m.wrap_method = wrap_method
        m.offset = float(offset)
        if apply:
            bpy.context.view_layer.objects.active = o
            bpy.ops.object.modifier_apply(modifier=m.name)
        return {"name": name, "target": target_name, "method": wrap_method, "applied": apply}

    def bm_remesh(self, name, mode='VOXEL', voxel_size=0.05, octree_depth=5, apply=True):
        """Remesh (auto-retopology). mode: VOXEL|QUAD|SHARP|SMOOTH|BLOCKS."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        before = len(o.data.polygons)
        m = o.modifiers.new("Remesh", 'REMESH')
        m.mode = mode
        if mode == 'VOXEL':
            m.voxel_size = float(voxel_size)
        else:
            m.octree_depth = int(octree_depth)
        if apply:
            bpy.context.view_layer.objects.active = o
            bpy.ops.object.modifier_apply(modifier=m.name)
        return {"name": name, "mode": mode, "before_polys": before, "after_polys": len(o.data.polygons)}

    # ---- Car modeling ----

    def bm_boolean(self, name, target, operation='DIFFERENCE', solver='EXACT', apply=True):
        """Boolean op. operation: DIFFERENCE|UNION|INTERSECT. solver: EXACT|FAST."""
        o = bpy.data.objects.get(name)
        t = bpy.data.objects.get(target)
        if not o or not t: raise ValueError("Object or target not found")
        m = o.modifiers.new("Boolean_tmp", 'BOOLEAN')
        m.operation = operation
        m.solver = solver
        m.object = t
        if apply:
            bpy.context.view_layer.objects.active = o
            bpy.ops.object.modifier_apply(modifier=m.name)
        return {"name": name, "target": target, "operation": operation, "applied": apply}

    def bm_bisect_plane(self, name, plane_point, plane_normal, fill=True, clear_inner=False, clear_outer=False):
        """Bisect mesh with infinite plane. clear_inner=True removes side that normal points AWAY from, clear_outer the opposite."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.bisect(plane_co=plane_point, plane_no=plane_normal, use_fill=bool(fill),
                            clear_inner=bool(clear_inner), clear_outer=bool(clear_outer))
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"name": name, "plane_point": plane_point, "plane_normal": plane_normal}

    def bm_symmetrize(self, name, direction='POSITIVE_X', threshold=0.0001):
        """Symmetrize mesh. direction: POSITIVE_X|NEGATIVE_X|POSITIVE_Y|NEGATIVE_Y|POSITIVE_Z|NEGATIVE_Z.
        Direction = which half to KEEP and mirror to the other side."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        # Map to operator's direction enum
        dir_map = {'+X':'POSITIVE_X','-X':'NEGATIVE_X','+Y':'POSITIVE_Y','-Y':'NEGATIVE_Y','+Z':'POSITIVE_Z','-Z':'NEGATIVE_Z'}
        d = dir_map.get(direction, direction)
        bpy.ops.mesh.symmetrize(direction=d, threshold=float(threshold))
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"name": name, "direction": d}

    def bm_set_edge_crease(self, name, edge_indices, weight=1.0):
        """Set Subsurf crease weight on edges (0=smooth, 1=sharp). For panel seams."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        # Use bmesh for crease access
        import bmesh
        bm = bmesh.new(); bm.from_mesh(o.data)
        bm.edges.ensure_lookup_table()
        cl = bm.edges.layers.float.get("crease_edge") or bm.edges.layers.float.new("crease_edge")
        es = set(edge_indices)
        n = 0
        for e in bm.edges:
            if e.index in es:
                e[cl] = float(weight); n += 1
        bm.to_mesh(o.data); bm.free()
        o.data.update()
        return {"name": name, "edges_creased": n, "weight": weight}

    def bm_set_edge_bevel_weight(self, name, edge_indices, weight=1.0):
        """Set bevel weight on edges (for Bevel modifier with 'Weight' limit method)."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        import bmesh
        bm = bmesh.new(); bm.from_mesh(o.data)
        bm.edges.ensure_lookup_table()
        bl = bm.edges.layers.float.get("bevel_weight_edge") or bm.edges.layers.float.new("bevel_weight_edge")
        es = set(edge_indices); n = 0
        for e in bm.edges:
            if e.index in es:
                e[bl] = float(weight); n += 1
        bm.to_mesh(o.data); bm.free()
        o.data.update()
        return {"name": name, "edges_weighted": n, "weight": weight}

    def bm_set_vert_bevel_weight(self, name, vert_indices, weight=1.0):
        """Vert bevel weight (for vertex bevel)."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        import bmesh
        bm = bmesh.new(); bm.from_mesh(o.data)
        bm.verts.ensure_lookup_table()
        bl = bm.verts.layers.float.get("bevel_weight_vert") or bm.verts.layers.float.new("bevel_weight_vert")
        vs = set(vert_indices); n = 0
        for v in bm.verts:
            if v.index in vs:
                v[bl] = float(weight); n += 1
        bm.to_mesh(o.data); bm.free()
        return {"name": name, "verts_weighted": n}

    def bm_proportional_translate(self, name, seed_vert_index, delta, falloff='SMOOTH', radius=1.0):
        """Translate seed vert + propagate to neighbors with falloff. radius in object-local units.
        falloff: SMOOTH|SPHERE|ROOT|SHARP|LINEAR|CONSTANT|RANDOM."""
        import math as _m
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        if seed_vert_index < 0 or seed_vert_index >= len(o.data.vertices):
            raise ValueError(f"Index out of range: {seed_vert_index}")
        seed = o.data.vertices[seed_vert_index].co.copy()
        d = mathutils.Vector(delta)
        r = float(radius)
        def w(dist):
            if dist >= r: return 0.0
            x = dist / r
            if falloff == 'CONSTANT': return 1.0
            if falloff == 'LINEAR':   return 1.0 - x
            if falloff == 'SPHERE':   return (1.0 - x*x) ** 0.5
            if falloff == 'ROOT':     return 1.0 - x**0.5
            if falloff == 'SHARP':    return (1.0 - x) ** 2
            if falloff == 'SMOOTH':   return 3*(1-x)**2 - 2*(1-x)**3
            return 1.0
        affected = 0
        for v in o.data.vertices:
            dist = (v.co - seed).length
            weight = w(dist)
            if weight > 0:
                v.co += d * weight
                affected += 1
        o.data.update()
        return {"name": name, "affected": affected, "seed": seed_vert_index, "radius": radius, "falloff": falloff}

    def bm_merge_verts(self, name, vert_indices, mode='CENTER'):
        """Merge verts. mode: CENTER|FIRST|LAST|COLLAPSE."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.mode_set(mode='OBJECT')
        vs = set(vert_indices)
        for v in o.data.vertices:
            v.select = v.index in vs
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.merge(type=mode)
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"name": name, "mode": mode}

    def bm_array_modifier(self, name, count=3, axis='x', offset=1.0, fit_type='FIXED_COUNT', curve=None):
        """Array modifier. fit_type: FIXED_COUNT|FIT_LENGTH|FIT_CURVE."""
        o = bpy.data.objects.get(name)
        if not o: raise ValueError(f"Not found: {name}")
        m = o.modifiers.new("Array", 'ARRAY')
        m.count = int(count)
        m.fit_type = fit_type
        m.use_relative_offset = True
        ai = {'x':0,'y':1,'z':2}[axis.lower()]
        rel = [0,0,0]; rel[ai] = float(offset)
        m.relative_offset_displace = rel
        if fit_type == 'FIT_CURVE' and curve:
            cu = bpy.data.objects.get(curve)
            if cu: m.curve = cu
        return {"name": name, "count": count, "axis": axis}

    def bm_curve_modifier(self, name, curve_name, axis='POS_X'):
        """Add Curve modifier — deforms mesh along curve. axis: POS_X|NEG_X|POS_Y|NEG_Y|POS_Z|NEG_Z."""
        o = bpy.data.objects.get(name)
        cu = bpy.data.objects.get(curve_name)
        if not o or not cu: raise ValueError("Mesh or curve not found")
        m = o.modifiers.new("Curve", 'CURVE')
        m.object = cu
        m.deform_axis = axis
        return {"name": name, "curve": curve_name, "axis": axis}

    def bm_edge_slide(self, name, edge_indices, factor=0.5):
        """Slide edge loop along adjacent edges. factor -1..1 (0 = no move)."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='EDGE')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.mode_set(mode='OBJECT')
        es = set(edge_indices)
        for e in o.data.edges:
            e.select = e.index in es
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.transform.edge_slide(value=float(factor))
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"name": name, "factor": factor}

    def bm_select_inside_bbox(self, name, bbox_min, bbox_max, space='world'):
        """Select verts inside an axis-aligned bbox."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.mode_set(mode='OBJECT')
        mins = mathutils.Vector(bbox_min); maxs = mathutils.Vector(bbox_max)
        mw = o.matrix_world
        for v in o.data.vertices:
            co = mw @ v.co if space == 'world' else v.co
            v.select = (mins.x <= co.x <= maxs.x and mins.y <= co.y <= maxs.y and mins.z <= co.z <= maxs.z)
        sel = sum(1 for v in o.data.vertices if v.select)
        return {"name": name, "selected": sel}

    def bm_select_by_material(self, name, material_name):
        """Select all faces with given material."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        slot_idx = -1
        for i, s in enumerate(o.material_slots):
            if s.material and s.material.name == material_name:
                slot_idx = i; break
        if slot_idx == -1:
            return {"name": name, "selected": 0, "warning": f"material not on object: {material_name}"}
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.mode_set(mode='OBJECT')
        n = 0
        for p in o.data.polygons:
            if p.material_index == slot_idx:
                p.select = True; n += 1
        return {"name": name, "selected": n, "material": material_name}

    def bm_make_lod_set(self, name, ratios=None, filepath_prefix=None):
        """Generate LOD chain: duplicate mesh, decimate to each ratio. Optionally export each."""
        if ratios is None: ratios = [1.0, 0.5, 0.25, 0.1]
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        lods = []
        for i, r in enumerate(ratios):
            self.bm_duplicate(name, new_name=f"{name}_LOD{i}")
            new = bpy.data.objects[f"{name}_LOD{i}"]
            if r < 1.0:
                self.bm_decimate(new.name, ratio=float(r))
            lods.append({"name": new.name, "ratio": r, "polys": len(new.data.polygons)})
            if filepath_prefix:
                self.bm_export_format(f"{filepath_prefix}_LOD{i}.fbx", "fbx", selection_only=True, object_names=[new.name])
        return {"source": name, "lods": lods}

    def bm_setup_car_template(self, name="Car", front_image=None, side_image=None, top_image=None,
                              length=4.7, width=2.0, height=1.45):
        """One-call car modeling workspace: ref images + half-cube base + Mirror + SubSurf."""
        results = {"refs": [], "base_mesh": None}
        # Reference images
        if front_image:
            results["refs"].append(self.bm_add_reference_image(front_image, axis='FRONT', size=width))
        if side_image:
            results["refs"].append(self.bm_add_reference_image(side_image, axis='RIGHT', size=length, location=(width/2+0.01, 0, height/2)))
        if top_image:
            results["refs"].append(self.bm_add_reference_image(top_image, axis='TOP', size=length, location=(0, 0, -0.01)))
        # Half-cube base on +X side (the half we model, mirror does the other half)
        self.bm_perfect_box(name, mins=[0, -length/2, 0], maxs=[width/2, length/2, height])
        # Mirror modifier on X axis (clip prevents verts from crossing center plane)
        m = bpy.data.objects[name].modifiers.new("Mirror", 'MIRROR')
        m.use_axis[0] = True
        m.use_clip = True
        # SubSurf level 2
        self.bm_add_subsurf(name, levels=2)
        results["base_mesh"] = name
        return results

    # ---- Gun modeling ----

    def bm_text_3d(self, text, name=None, location=(0,0,0), size=0.1, extrude=0.02, align_x='CENTER', align_y='CENTER'):
        """Create 3D text object."""
        cu = bpy.data.curves.new(name or "Text", 'FONT')
        cu.body = text
        cu.size = float(size)
        cu.extrude = float(extrude)
        cu.align_x = align_x
        cu.align_y = align_y
        obj = bpy.data.objects.new(name or "Text", cu)
        obj.location = mathutils.Vector(location)
        bpy.context.collection.objects.link(obj)
        return {"name": obj.name, "text": text}

    def bm_emboss_text(self, target_name, text, location, size=0.05, depth=0.01, axis='z', operation='DIFFERENCE'):
        """Emboss/engrave text into target mesh via Boolean. axis: which world axis text points along."""
        tmp = self.bm_text_3d(text, name=f"__emboss_{text[:8]}", location=location, size=size, extrude=depth*3)
        text_obj = bpy.data.objects[tmp["name"]]
        # Convert to mesh
        bpy.ops.object.select_all(action='DESELECT')
        text_obj.select_set(True); bpy.context.view_layer.objects.active = text_obj
        bpy.ops.object.convert(target='MESH')
        # Apply boolean
        self.bm_boolean(target_name, text_obj.name, operation=operation, apply=True)
        # Cleanup
        bpy.data.objects.remove(text_obj, do_unlink=True)
        return {"target": target_name, "text": text, "operation": operation}

    def bm_set_origin_to_face(self, name, face_index):
        """Set object origin to face's center."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        center_local = o.data.polygons[face_index].center
        center_world = o.matrix_world @ center_local
        bpy.context.scene.cursor.location = center_world
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.origin_set(type='ORIGIN_CURSOR', center='MEDIAN')
        bpy.context.scene.cursor.location = (0,0,0)
        return {"name": name, "face": face_index, "origin": list(o.location)}

    def bm_set_origin_to_vert(self, name, vert_index):
        """Set object origin to vertex world position."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        v_world = o.matrix_world @ o.data.vertices[vert_index].co
        bpy.context.scene.cursor.location = v_world
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.origin_set(type='ORIGIN_CURSOR', center='MEDIAN')
        bpy.context.scene.cursor.location = (0,0,0)
        return {"name": name, "vert": vert_index, "origin": list(o.location)}

    def bm_align_face_to_face(self, src_name, src_face, dst_name, dst_face, flip=False):
        """Align src object's face to dst object's face. Moves+rotates src so its face center sits on dst's face with normals opposite (touching)."""
        src = bpy.data.objects.get(src_name); dst = bpy.data.objects.get(dst_name)
        if not src or not dst: raise ValueError("Object not found")
        sf = src.data.polygons[src_face]; df = dst.data.polygons[dst_face]
        sn = (src.matrix_world.to_3x3() @ sf.normal).normalized()
        dn = (dst.matrix_world.to_3x3() @ df.normal).normalized()
        sc = src.matrix_world @ sf.center
        dc = dst.matrix_world @ df.center
        # Target normal = -dn (faces touch)
        target_normal = -dn if not flip else dn
        # Rotation to align sn → target_normal
        import math as _m
        axis = sn.cross(target_normal)
        dot = max(-1.0, min(1.0, sn.dot(target_normal)))
        angle = _m.acos(dot)
        if axis.length > 1e-9:
            R = mathutils.Matrix.Rotation(angle, 4, axis.normalized())
            # Rotate around src face center
            T1 = mathutils.Matrix.Translation(-sc)
            T2 = mathutils.Matrix.Translation(sc)
            src.matrix_world = T2 @ R @ T1 @ src.matrix_world
            # After rotation, recompute sc
            sc = src.matrix_world @ src.data.polygons[src_face].center
        # Translate so sc matches dc
        delta = dc - sc
        src.location = src.location + delta
        return {"src": src_name, "dst": dst_name, "delta": list(delta), "angle_deg": round(_m.degrees(angle), 3)}

    def bm_punch_pattern(self, target_name, count=5, spacing=0.05, slot_size=(0.02,0.005,0.02),
                         start_location=(0,0,0), axis='x', operation='DIFFERENCE'):
        """Punch repeated holes/slots through target. Creates cutter array + boolean diff."""
        cutter_name = f"__punch_{target_name}"
        sx, sy, sz = slot_size
        # Create base cutter cube
        self.bm_perfect_box(cutter_name, mins=[-sx/2,-sy/2,-sz/2], maxs=[sx/2,sy/2,sz/2], location=start_location)
        # Array modifier
        m = bpy.data.objects[cutter_name].modifiers.new("Array", 'ARRAY')
        m.count = int(count); m.use_relative_offset = False; m.use_constant_offset = True
        ai = {'x':0,'y':1,'z':2}[axis.lower()]
        co = [0,0,0]; co[ai] = float(spacing)
        m.constant_offset_displace = co
        # Apply array
        bpy.context.view_layer.objects.active = bpy.data.objects[cutter_name]
        bpy.ops.object.modifier_apply(modifier=m.name)
        # Boolean
        self.bm_boolean(target_name, cutter_name, operation=operation, apply=True)
        # Cleanup cutter
        bpy.data.objects.remove(bpy.data.objects[cutter_name], do_unlink=True)
        return {"target": target_name, "count": count, "spacing": spacing}

    def bm_add_skin_modifier(self, name, root_vert_index=0, default_size=0.05):
        """Skin modifier — turns edge graph into cylinders. Set root vert and default radius."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        m = o.modifiers.new("Skin", 'SKIN')
        # Set default size for all skin verts
        sv = o.data.skin_vertices.get('Skin') or o.data.skin_vertices['']  # ensure layer
        for v in o.data.skin_vertices[0].data if o.data.skin_vertices else []:
            v.radius = (float(default_size), float(default_size))
        if 0 <= root_vert_index < len(o.data.skin_vertices[0].data if o.data.skin_vertices else []):
            o.data.skin_vertices[0].data[root_vert_index].use_root = True
        return {"name": name, "root": root_vert_index, "size": default_size}

    def bm_add_wireframe_modifier(self, name, thickness=0.01, offset=0.0):
        """Wireframe modifier — turns mesh into 3D wire."""
        o = bpy.data.objects.get(name)
        if not o: raise ValueError(f"Not found: {name}")
        m = o.modifiers.new("Wireframe", 'WIREFRAME')
        m.thickness = float(thickness)
        m.offset = float(offset)
        return {"name": name, "thickness": thickness}

    def bm_add_solidify_modifier(self, name, thickness=0.01, offset=-1.0):
        """Solidify modifier — adds thickness. offset: -1 inside, 0 centered, 1 outside."""
        o = bpy.data.objects.get(name)
        if not o: raise ValueError(f"Not found: {name}")
        m = o.modifiers.new("Solidify", 'SOLIDIFY')
        m.thickness = float(thickness)
        m.offset = float(offset)
        return {"name": name, "thickness": thickness, "offset": offset}

    def bm_array_objects_along_edge(self, template_name, target_name, edge_indices, count_per_edge=5):
        """Place instances of template at evenly-spaced points along edges of target. For rivets/screws."""
        tmpl = bpy.data.objects.get(template_name)
        tgt = bpy.data.objects.get(target_name)
        if not tmpl or not tgt: raise ValueError("Object not found")
        instances = []
        for ei in edge_indices:
            e = tgt.data.edges[ei]
            a = tgt.matrix_world @ tgt.data.vertices[e.vertices[0]].co
            b = tgt.matrix_world @ tgt.data.vertices[e.vertices[1]].co
            for i in range(int(count_per_edge)):
                t = (i + 0.5) / count_per_edge
                pos = a.lerp(b, t)
                self.bm_duplicate(template_name)
                new = bpy.context.view_layer.objects.active
                new.location = pos
                instances.append(new.name)
        return {"template": template_name, "instances": len(instances)}

    def bm_mesh_thickness_stats(self, name, samples=100):
        """Sample wall thickness via raycasts. Returns min/max/avg in object-local units."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        # For each sample face, raycast inward along negative normal, find hit distance
        import bmesh
        bm = bmesh.new(); bm.from_mesh(o.data)
        bm.normal_update()
        bm.faces.ensure_lookup_table()
        thicknesses = []
        step = max(1, len(bm.faces) // samples)
        for i in range(0, len(bm.faces), step):
            f = bm.faces[i]
            ray_origin = f.calc_center_median() - f.normal * 0.0001
            ray_dir = -f.normal
            hit, loc, _, _ = o.ray_cast(ray_origin, ray_dir)
            if hit:
                thicknesses.append((loc - ray_origin).length)
        bm.free()
        if not thicknesses:
            return {"name": name, "samples": 0, "warning": "no hits"}
        return {"name": name, "samples": len(thicknesses),
                "min": round(min(thicknesses), 5), "max": round(max(thicknesses), 5),
                "avg": round(sum(thicknesses)/len(thicknesses), 5)}

    def bm_center_of_mass(self, name):
        """Geometric centroid of all vertices (world space)."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        if not o.data.vertices:
            return {"name": name, "center": [0,0,0]}
        mw = o.matrix_world
        c = mathutils.Vector((0,0,0))
        for v in o.data.vertices:
            c += mw @ v.co
        c /= len(o.data.vertices)
        return {"name": name, "center": self._r(list(c), 6), "vert_count": len(o.data.vertices)}

    # ---- Math helpers ----

    def bm_lerp(self, p1, p2, t):
        a = mathutils.Vector(p1); b = mathutils.Vector(p2)
        return {"result": list(a.lerp(b, float(t)))}

    def bm_slerp_quat(self, q1, q2, t):
        a = mathutils.Quaternion(q1); b = mathutils.Quaternion(q2)
        r = a.slerp(b, float(t))
        return {"result": list(r)}

    def bm_normal_from_3pts(self, p1, p2, p3):
        a = mathutils.Vector(p1); b = mathutils.Vector(p2); c = mathutils.Vector(p3)
        n = (b - a).cross(c - a).normalized()
        return {"normal": list(n)}

    def bm_centroid_of_points(self, points):
        if not points: return {"centroid": [0,0,0]}
        c = mathutils.Vector((0,0,0))
        for p in points: c += mathutils.Vector(p)
        c /= len(points)
        return {"centroid": list(c), "count": len(points)}

    def bm_circle_from_3pts(self, p1, p2, p3):
        """Center + radius of circle through 3 points (must be coplanar)."""
        a = mathutils.Vector(p1); b = mathutils.Vector(p2); c = mathutils.Vector(p3)
        # Use cross-product method
        ac = c - a; ab = b - a
        n = ab.cross(ac)
        ab_perp = n.cross(ab)
        ac_perp = n.cross(ac)
        ab_mid = (a + b) / 2
        ac_mid = (a + c) / 2
        # Solve: ab_mid + s*ab_perp = ac_mid + t*ac_perp
        # Cross product trick
        denom = ab_perp.cross(ac_perp)
        if denom.length < 1e-9:
            return {"error": "points collinear"}
        t = (ab_mid - ac_mid).cross(ab_perp).dot(denom) / denom.length_squared
        center = ac_mid + t * ac_perp
        radius = (center - a).length
        return {"center": self._r(list(center), 6), "radius": round(radius, 6)}

    def bm_dist_point_to_line(self, point, line_p1, line_p2):
        p = mathutils.Vector(point); a = mathutils.Vector(line_p1); b = mathutils.Vector(line_p2)
        ab = b - a; ap = p - a
        if ab.length_squared < 1e-12:
            return {"distance": ap.length, "closest": list(a)}
        t = ap.dot(ab) / ab.length_squared
        closest = a + ab * max(0.0, min(1.0, t))
        return {"distance": round((p - closest).length, 6), "closest": list(closest), "t": round(t, 6)}

    def bm_dist_point_to_plane(self, point, plane_point, plane_normal):
        p = mathutils.Vector(point); pp = mathutils.Vector(plane_point); pn = mathutils.Vector(plane_normal).normalized()
        d = (p - pp).dot(pn)
        return {"distance": round(d, 6), "signed_distance": round(d, 6)}

    def bm_intersect_line_plane(self, line_p1, line_p2, plane_point, plane_normal):
        l1 = mathutils.Vector(line_p1); l2 = mathutils.Vector(line_p2)
        pp = mathutils.Vector(plane_point); pn = mathutils.Vector(plane_normal).normalized()
        result = mathutils.geometry.intersect_line_plane(l1, l2, pp, pn)
        if result is None:
            return {"error": "no intersection (line parallel to plane)"}
        return {"point": list(result)}

    # ---- Curves ----

    def bm_circle_arc(self, p1, p2, p3, segments=16, name="Arc"):
        """Create curve arc passing through 3 points."""
        c = self.bm_circle_from_3pts(p1, p2, p3)
        if "error" in c: return c
        center = mathutils.Vector(c["center"]); radius = c["radius"]
        a = mathutils.Vector(p1); b = mathutils.Vector(p3)
        # Build poly curve approximating arc
        normal = (mathutils.Vector(p2) - center).cross(a - center)
        if normal.length < 1e-9:
            normal = (a - center).cross(b - center)
        normal.normalize()
        v_start = (a - center).normalized()
        v_end = (b - center).normalized()
        import math as _m
        ang_total = _m.acos(max(-1, min(1, v_start.dot(v_end))))
        points = []
        for i in range(int(segments)+1):
            t = i / segments
            ang = ang_total * t
            R = mathutils.Matrix.Rotation(ang, 3, normal)
            pt = center + (R @ v_start) * radius
            points.append(list(pt))
        return self.bm_create_curve(name, points, type='POLY')

    def bm_bezier_from_4pts(self, p0, p1, p2, p3, segments=16, name="Bezier"):
        """Cubic Bezier curve through control points p0..p3."""
        points = []
        for i in range(int(segments)+1):
            t = i / segments
            u = 1 - t
            pt = (mathutils.Vector(p0) * (u**3)
                  + mathutils.Vector(p1) * (3 * u**2 * t)
                  + mathutils.Vector(p2) * (3 * u * t**2)
                  + mathutils.Vector(p3) * (t**3))
            points.append(list(pt))
        return self.bm_create_curve(name, points, type='POLY')

    def bm_offset_curve(self, name, distance=0.05, axis='z', new_name=None):
        """Create parallel curve offset along axis (sweeps original)."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'CURVE': raise ValueError(f"Curve not found: {name}")
        new_name = new_name or f"{name}_offset"
        # Duplicate curve + offset every control point
        ai = {'x':0,'y':1,'z':2}[axis.lower()]
        new = o.copy(); new.data = o.data.copy(); new.name = new_name
        bpy.context.collection.objects.link(new)
        for spline in new.data.splines:
            if spline.type == 'BEZIER':
                for bp in spline.bezier_points:
                    co = list(bp.co); co[ai] += float(distance); bp.co = co
            else:
                for pt in spline.points:
                    co = list(pt.co); co[ai] += float(distance); pt.co = co
        return {"new": new_name, "axis": axis, "distance": distance}

    # ---- Workflow ----

    def bm_apply_all_modifiers(self, name):
        """Apply all modifiers on object in stack order."""
        o = bpy.data.objects.get(name)
        if not o: raise ValueError(f"Not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        applied = []
        for m in list(o.modifiers):
            try:
                bpy.ops.object.modifier_apply(modifier=m.name)
                applied.append(m.name)
            except Exception as e:
                applied.append(f"{m.name} FAILED: {e}")
        return {"name": name, "applied": applied}

    def bm_smart_bevel(self, name, edge_indices, width=0.005, segments=2, crease_for_subsurf=True):
        """Bevel + auto-mark edge crease for SubSurf-friendly hard surface. Standard hard-ops workflow."""
        # Mark edge crease first
        if crease_for_subsurf:
            self.bm_set_edge_crease(name, edge_indices, weight=1.0)
        # Bevel
        return self.bm_bevel_edges(name, offset=width, segments=segments, edge_indices=edge_indices)

    def bm_check_symmetry(self, name, axis='x', tolerance=0.001):
        """Check if mesh is symmetric across axis plane. Returns matched/unmatched vert counts."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        ai = {'x':0,'y':1,'z':2}[axis.lower()]
        # Build kd tree on mirrored verts
        from mathutils import kdtree
        kd = kdtree.KDTree(len(o.data.vertices))
        for v in o.data.vertices:
            kd.insert(v.co, v.index)
        kd.balance()
        matched = 0; unmatched = 0
        for v in o.data.vertices:
            mirror = mathutils.Vector(v.co)
            mirror[ai] = -mirror[ai]
            co, idx, dist = kd.find(mirror)
            if dist < float(tolerance):
                matched += 1
            else:
                unmatched += 1
        sym_pct = round(100 * matched / max(len(o.data.vertices), 1), 2)
        return {"name": name, "axis": axis, "matched": matched, "unmatched": unmatched, "symmetry_pct": sym_pct}

    # ---- Character animation / IK / rigging ----

    def bm_setup_ik(self, armature_name, end_bone, target_empty=None, pole_target=None, chain_count=2, pole_angle=-90, weight_position=1.0, weight_rotation=0.0):
        """Add IK constraint to end_bone. target_empty + pole_target are object NAMES (empties typically)."""
        arm = bpy.data.objects.get(armature_name)
        if not arm or arm.type != 'ARMATURE':
            raise ValueError(f"Armature not found: {armature_name}")
        pb = arm.pose.bones.get(end_bone)
        if not pb:
            raise ValueError(f"Bone not found: {end_bone}")
        # Remove existing IK on this bone
        for c in list(pb.constraints):
            if c.type == 'IK':
                pb.constraints.remove(c)
        ik = pb.constraints.new('IK')
        ik.chain_count = int(chain_count)
        if target_empty:
            t = bpy.data.objects.get(target_empty)
            if t: ik.target = t
        if pole_target:
            p = bpy.data.objects.get(pole_target)
            if p:
                ik.pole_target = p
                import math as _m
                ik.pole_angle = _m.radians(float(pole_angle))
        ik.use_location = True
        ik.weight = float(weight_position)
        ik.use_rotation = bool(weight_rotation > 0)
        ik.orient_weight = float(weight_rotation)
        return {"armature": armature_name, "end_bone": end_bone, "chain_count": chain_count}

    def bm_setup_leg_ik(self, armature_name, hip_bone, knee_bone, foot_bone,
                       foot_target_name=None, pole_target_name=None, pole_distance=0.3):
        """High-level: set up leg IK with auto-created foot target + knee pole target empties."""
        arm = bpy.data.objects.get(armature_name)
        if not arm: raise ValueError(f"Armature not found: {armature_name}")
        ft_name = foot_target_name or f"{foot_bone}_IK_target"
        pt_name = pole_target_name or f"{knee_bone}_IK_pole"
        foot_pb = arm.pose.bones.get(foot_bone); knee_pb = arm.pose.bones.get(knee_bone)
        if not foot_pb or not knee_pb: raise ValueError("Foot or knee bone not found")
        # Foot target at foot tail
        foot_world = arm.matrix_world @ foot_pb.tail
        self.bm_create_empty(ft_name, list(foot_world), display_type='CUBE', size=0.05)
        # Knee pole forward of knee
        knee_world = arm.matrix_world @ knee_pb.head
        # Forward direction = -Y in most rigs (toward camera/forward)
        import mathutils as mu
        knee_pole_world = knee_world + mu.Vector((0, -pole_distance, 0))
        self.bm_create_empty(pt_name, list(knee_pole_world), display_type='SPHERE', size=0.04)
        # Setup IK
        self.bm_setup_ik(armature_name, foot_bone, target_empty=ft_name, pole_target=pt_name, chain_count=2, pole_angle=-90)
        return {"foot_target": ft_name, "pole_target": pt_name, "hip": hip_bone, "knee": knee_bone, "foot": foot_bone}

    def bm_setup_arm_ik(self, armature_name, shoulder_bone, elbow_bone, hand_bone,
                       hand_target_name=None, pole_target_name=None, pole_distance=0.3):
        """High-level: arm IK with auto hand target + elbow pole target."""
        arm = bpy.data.objects.get(armature_name)
        if not arm: raise ValueError(f"Armature not found: {armature_name}")
        ht_name = hand_target_name or f"{hand_bone}_IK_target"
        pt_name = pole_target_name or f"{elbow_bone}_IK_pole"
        hand_pb = arm.pose.bones.get(hand_bone); elbow_pb = arm.pose.bones.get(elbow_bone)
        if not hand_pb or not elbow_pb: raise ValueError("Hand or elbow bone not found")
        hand_world = arm.matrix_world @ hand_pb.tail
        self.bm_create_empty(ht_name, list(hand_world), display_type='CUBE', size=0.05)
        elbow_world = arm.matrix_world @ elbow_pb.head
        import mathutils as mu
        elbow_pole_world = elbow_world + mu.Vector((0, pole_distance, 0))  # behind (+Y) typically
        self.bm_create_empty(pt_name, list(elbow_pole_world), display_type='SPHERE', size=0.04)
        self.bm_setup_ik(armature_name, hand_bone, target_empty=ht_name, pole_target=pt_name, chain_count=2, pole_angle=90)
        return {"hand_target": ht_name, "pole_target": pt_name, "shoulder": shoulder_bone, "elbow": elbow_bone, "hand": hand_bone}

    def bm_create_control_bone(self, armature_name, name, head, tail, parent=None, custom_shape_obj=None):
        """Add control bone (non-deforming, often parent-less, used as IK target)."""
        arm = bpy.data.objects.get(armature_name)
        if not arm: raise ValueError(f"Armature not found: {armature_name}")
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.mode_set(mode='EDIT')
        eb = arm.data.edit_bones.new(name)
        eb.head = mathutils.Vector(head); eb.tail = mathutils.Vector(tail)
        eb.use_deform = False
        if parent:
            eb.parent = arm.data.edit_bones.get(parent)
        bpy.ops.object.mode_set(mode='OBJECT')
        if custom_shape_obj:
            pb = arm.pose.bones[name]
            pb.custom_shape = bpy.data.objects.get(custom_shape_obj)
        return {"armature": armature_name, "control_bone": name}

    def bm_add_armature_modifier(self, mesh_name, armature_name, vgroups=True, envelopes=False):
        """Bind mesh to armature via Armature modifier."""
        m = bpy.data.objects.get(mesh_name)
        arm = bpy.data.objects.get(armature_name)
        if not m or not arm: raise ValueError("Mesh or armature not found")
        # Remove existing Armature modifiers
        for mod in list(m.modifiers):
            if mod.type == 'ARMATURE':
                m.modifiers.remove(mod)
        mod = m.modifiers.new("Armature", 'ARMATURE')
        mod.object = arm
        mod.use_vertex_groups = bool(vgroups)
        mod.use_bone_envelopes = bool(envelopes)
        # Parent mesh to armature for transform tracking
        m.parent = arm
        return {"mesh": mesh_name, "armature": armature_name}

    def bm_auto_weights(self, mesh_name, armature_name):
        """Bind mesh to armature with automatic weights (heat-map from bones)."""
        m = bpy.data.objects.get(mesh_name)
        arm = bpy.data.objects.get(armature_name)
        if not m or not arm: raise ValueError("Mesh or armature not found")
        bpy.ops.object.select_all(action='DESELECT')
        m.select_set(True); arm.select_set(True)
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.parent_set(type='ARMATURE_AUTO')
        return {"mesh": mesh_name, "armature": armature_name, "method": "automatic_weights"}

    def bm_assign_vertex_group(self, mesh_name, group_name, vert_indices, weight=1.0):
        """Add verts to vertex group with weight. Creates group if missing."""
        m = bpy.data.objects.get(mesh_name)
        if not m or m.type != 'MESH': raise ValueError(f"Mesh not found: {mesh_name}")
        vg = m.vertex_groups.get(group_name)
        if not vg:
            vg = m.vertex_groups.new(name=group_name)
        vg.add(list(vert_indices), float(weight), 'REPLACE')
        return {"mesh": mesh_name, "group": group_name, "verts": len(vert_indices), "weight": weight}

    def bm_normalize_vertex_groups(self, mesh_name, lock_active=False):
        """Normalize all vertex group weights to sum to 1 per vert."""
        m = bpy.data.objects.get(mesh_name)
        if not m or m.type != 'MESH': raise ValueError(f"Mesh not found: {mesh_name}")
        bpy.ops.object.select_all(action='DESELECT')
        m.select_set(True); bpy.context.view_layer.objects.active = m
        bpy.ops.object.vertex_group_normalize_all(lock_active=bool(lock_active))
        return {"mesh": mesh_name}

    def bm_set_bone_display(self, armature_name, bone_name, shape='OCTAHEDRAL'):
        """shape: OCTAHEDRAL|STICK|BBONE|ENVELOPE|WIRE."""
        arm = bpy.data.objects.get(armature_name)
        if not arm or arm.type != 'ARMATURE': raise ValueError(f"Armature not found: {armature_name}")
        # Display type applies to whole armature data, not per bone
        arm.data.display_type = shape
        return {"armature": armature_name, "display": shape}

    def bm_set_bone_roll(self, armature_name, bone_name, angle_deg):
        arm = bpy.data.objects.get(armature_name)
        if not arm: raise ValueError(f"Armature not found: {armature_name}")
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.mode_set(mode='EDIT')
        eb = arm.data.edit_bones.get(bone_name)
        if not eb:
            bpy.ops.object.mode_set(mode='OBJECT')
            raise ValueError(f"Bone not found: {bone_name}")
        import math as _m
        eb.roll = _m.radians(float(angle_deg))
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"armature": armature_name, "bone": bone_name, "roll_deg": angle_deg}

    def bm_mirror_bones(self, armature_name, src_suffix='.l', dst_suffix='.r'):
        """Mirror .l bones to .r side via X-axis symmetry."""
        arm = bpy.data.objects.get(armature_name)
        if not arm or arm.type != 'ARMATURE': raise ValueError(f"Armature not found: {armature_name}")
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.mode_set(mode='EDIT')
        # Select all .l bones
        for eb in arm.data.edit_bones:
            eb.select = eb.name.endswith(src_suffix)
        bpy.ops.armature.symmetrize(direction='POSITIVE_X' if src_suffix.endswith('.l') else 'NEGATIVE_X')
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"armature": armature_name, "mirror": f"{src_suffix} -> {dst_suffix}"}

    def bm_add_bone_chain(self, armature_name, names, head_positions, tail_positions=None, parent_chain=True, parent_first_to=None, connect=True):
        """Add a chain of bones to existing armature. tail_positions auto = next head if None."""
        arm = bpy.data.objects.get(armature_name)
        if not arm or arm.type != 'ARMATURE': raise ValueError(f"Armature not found: {armature_name}")
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.mode_set(mode='EDIT')
        if tail_positions is None:
            tail_positions = head_positions[1:] + [head_positions[-1]]  # last bone tail = +0.1 of head
            # Make last bone have non-zero tail
            last_head = mathutils.Vector(head_positions[-1])
            tail_positions[-1] = list(last_head + mathutils.Vector((0,0,0.1)))
        prev = None
        for i, (n, h, t) in enumerate(zip(names, head_positions, tail_positions)):
            eb = arm.data.edit_bones.new(n)
            eb.head = mathutils.Vector(h)
            eb.tail = mathutils.Vector(t)
            if parent_chain and prev is not None:
                eb.parent = prev
                eb.use_connect = bool(connect)
            elif i == 0 and parent_first_to:
                eb.parent = arm.data.edit_bones.get(parent_first_to)
            prev = eb
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"armature": armature_name, "added": names}

    def bm_push_to_nla(self, armature_name, action_name=None, strip_name=None):
        """Push armature's active (or named) action onto a new NLA strip."""
        arm = bpy.data.objects.get(armature_name)
        if not arm: raise ValueError(f"Armature not found: {armature_name}")
        if arm.animation_data is None:
            return {"warning": "no animation_data"}
        if action_name:
            arm.animation_data.action = bpy.data.actions.get(action_name)
        act = arm.animation_data.action
        if not act:
            return {"warning": "no active action to push"}
        track = arm.animation_data.nla_tracks.new()
        try:
            fr_start = int(act.frame_range[0])
        except Exception:
            fr_start = 0
        strip = track.strips.new(strip_name or act.name, fr_start, act)
        arm.animation_data.action = None
        return {"armature": armature_name, "action": act.name, "track": track.name, "strip": strip.name}

    def bm_add_shape_key(self, mesh_name, name, from_mix=False):
        """Add shape key to mesh. First call creates 'Basis' too."""
        m = bpy.data.objects.get(mesh_name)
        if not m or m.type != 'MESH': raise ValueError(f"Mesh not found: {mesh_name}")
        if m.data.shape_keys is None:
            m.shape_key_add(name="Basis", from_mix=False)
        sk = m.shape_key_add(name=name, from_mix=bool(from_mix))
        return {"mesh": mesh_name, "shape_key": sk.name}

    def bm_blend_actions(self, target_armature, action1, action2, weight=0.5, blend_mode='REPLACE'):
        """Blend two actions via NLA strips. weight: 0=action1, 1=action2."""
        arm = bpy.data.objects.get(target_armature)
        if not arm: raise ValueError(f"Armature not found: {target_armature}")
        a1 = bpy.data.actions.get(action1); a2 = bpy.data.actions.get(action2)
        if not a1 or not a2: raise ValueError("Action not found")
        if arm.animation_data is None: arm.animation_data_create()
        # Layer 1 = base (action1)
        t1 = arm.animation_data.nla_tracks.new()
        try:
            f1 = int(a1.frame_range[0])
        except Exception:
            f1 = 0
        s1 = t1.strips.new(a1.name, f1, a1)
        s1.blend_type = blend_mode
        s1.influence = 1.0 - float(weight)
        # Layer 2 = blend (action2)
        t2 = arm.animation_data.nla_tracks.new()
        try:
            f2 = int(a2.frame_range[0])
        except Exception:
            f2 = 0
        s2 = t2.strips.new(a2.name, f2, a2)
        s2.blend_type = blend_mode
        s2.influence = float(weight)
        return {"armature": target_armature, "blend": [action1, action2], "weight": weight}

    # ---- Smart weight paint ----

    def bm_paint_weight_to_bone(self, mesh_name, group_name, vert_indices, weight=1.0, mode='REPLACE'):
        """Paint weight to vertex group. mode: REPLACE|ADD|SUBTRACT|MULTIPLY."""
        m = bpy.data.objects.get(mesh_name)
        if not m or m.type != 'MESH': raise ValueError(f"Mesh not found: {mesh_name}")
        vg = m.vertex_groups.get(group_name)
        if not vg:
            vg = m.vertex_groups.new(name=group_name)
        vg.add(list(vert_indices), float(weight), mode)
        return {"mesh": mesh_name, "group": group_name, "weight": weight, "mode": mode}

    def bm_smooth_weights(self, mesh_name, group_name=None, iterations=3, factor=0.5):
        """Smooth vertex group weights with neighbor averaging."""
        m = bpy.data.objects.get(mesh_name)
        if not m or m.type != 'MESH': raise ValueError(f"Mesh not found: {mesh_name}")
        if not m.vertex_groups: raise ValueError(f"Mesh has no vertex groups: {mesh_name}")
        prev_active = bpy.context.view_layer.objects.active
        prev_mode = bpy.context.mode if bpy.context.mode else 'OBJECT'
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        m.select_set(True); bpy.context.view_layer.objects.active = m
        if group_name:
            vg = m.vertex_groups.get(group_name)
            if vg: m.vertex_groups.active_index = vg.index
        bpy.ops.object.mode_set(mode='WEIGHT_PAINT')
        try:
            bpy.ops.object.vertex_group_smooth(group_select_mode='ACTIVE' if group_name else 'ALL', factor=float(factor), repeat=int(iterations))
        finally:
            bpy.ops.object.mode_set(mode='OBJECT')
            if prev_active and prev_active.name in bpy.data.objects:
                bpy.context.view_layer.objects.active = prev_active
        return {"mesh": mesh_name, "group": group_name, "iterations": iterations, "factor": factor}

    def bm_set_active_vgroup(self, mesh_name, group_name):
        """Set active vertex group on mesh (for weight paint preview)."""
        m = bpy.data.objects.get(mesh_name)
        if not m or m.type != 'MESH': raise ValueError(f"Mesh not found: {mesh_name}")
        vg = m.vertex_groups.get(group_name)
        if not vg: raise ValueError(f"Vertex group not found: {group_name} (available: {[g.name for g in m.vertex_groups]})")
        m.vertex_groups.active_index = vg.index
        return {"mesh": mesh_name, "active_vgroup": group_name, "index": vg.index}

    def bm_weight_by_axis_split(self, mesh_name, axis, boundary, blend_width,
                                 group_neg, group_pos, clear_others=True, space='local'):
        """Split mesh weights between two bones along an axis with smooth blend.

        Args:
            mesh_name: target mesh
            axis: 'x' | 'y' | 'z'
            boundary: position along axis where split happens (e.g. 0.0 for center)
            blend_width: half-width of smooth transition zone (linear ramp)
            group_neg: vgroup name for the < boundary side (gets weight=1 below)
            group_pos: vgroup name for the > boundary side (gets weight=1 above)
            clear_others: if True, wipe all other vgroups first
            space: 'local' (mesh coord) or 'world' (vert.co transformed)
        Verts within `boundary ± blend_width` get blended weight between the two
        groups; outside that band → 1.0 to the appropriate side."""
        ax_i = {'x': 0, 'y': 1, 'z': 2}[axis.lower()]
        m = bpy.data.objects.get(mesh_name)
        if not m or m.type != 'MESH':
            raise ValueError(f"Mesh not found: {mesh_name}")
        if clear_others:
            for vg in list(m.vertex_groups):
                m.vertex_groups.remove(vg)
        vg_n = m.vertex_groups.get(group_neg) or m.vertex_groups.new(name=group_neg)
        vg_p = m.vertex_groups.get(group_pos) or m.vertex_groups.new(name=group_pos)
        world = m.matrix_world if space == 'world' else None
        bw = max(float(blend_width), 1e-6)
        n_neg = n_pos = n_blend = 0
        for v in m.data.vertices:
            co = (world @ v.co) if world else v.co
            d = co[ax_i] - boundary
            if d >= bw:
                vg_p.add([v.index], 1.0, 'REPLACE')
                n_pos += 1
            elif d <= -bw:
                vg_n.add([v.index], 1.0, 'REPLACE')
                n_neg += 1
            else:
                t = (d + bw) / (2.0 * bw)  # 0 at -bw, 1 at +bw
                vg_p.add([v.index], t, 'REPLACE')
                vg_n.add([v.index], 1.0 - t, 'REPLACE')
                n_blend += 1
        return {"mesh": mesh_name, "axis": axis, "boundary": boundary,
                "blend_width": blend_width, "group_neg": group_neg,
                "group_pos": group_pos, "counts": {"neg": n_neg, "pos": n_pos, "blend": n_blend}}

    def bm_weight_by_plane_split(self, mesh_name, plane_point, plane_normal, blend_width,
                                  group_neg, group_pos, clear_others=True, space='local'):
        """Split weights by signed distance to an arbitrary plane.
        Generalizes bm_weight_by_axis_split — use for diagonal cuts (e.g. 45° elbow).

        Args:
            mesh_name: target mesh
            plane_point: [x,y,z] point on the plane (e.g. elbow joint position)
            plane_normal: [nx,ny,nz] plane normal (need not be unit; will be normalized)
            blend_width: half-width of smooth transition zone along the normal
            group_neg: vgroup for negative side of plane (signed dist < 0)
            group_pos: vgroup for positive side of plane (signed dist > 0)
            clear_others: wipe other vgroups first
            space: 'local' (default) or 'world'
        Example 45° elbow cut at origin, normal pointing into bicep+up:
            plane_point=[0,0,0], plane_normal=[0,1,1]"""
        import math as _math
        m = bpy.data.objects.get(mesh_name)
        if not m or m.type != 'MESH':
            raise ValueError(f"Mesh not found: {mesh_name}")
        if clear_others:
            for vg in list(m.vertex_groups):
                m.vertex_groups.remove(vg)
        vg_n = m.vertex_groups.get(group_neg) or m.vertex_groups.new(name=group_neg)
        vg_p = m.vertex_groups.get(group_pos) or m.vertex_groups.new(name=group_pos)
        nx, ny, nz = plane_normal
        nlen = _math.sqrt(nx*nx + ny*ny + nz*nz) or 1.0
        nx, ny, nz = nx/nlen, ny/nlen, nz/nlen
        px, py, pz = plane_point
        world = m.matrix_world if space == 'world' else None
        bw = float(blend_width)
        sharp = bw <= 0.0
        n_neg = n_pos = n_blend = 0
        for v in m.data.vertices:
            co = (world @ v.co) if world else v.co
            d = (co[0]-px)*nx + (co[1]-py)*ny + (co[2]-pz)*nz
            if sharp:
                if d >= 0:
                    vg_p.add([v.index], 1.0, 'REPLACE'); n_pos += 1
                else:
                    vg_n.add([v.index], 1.0, 'REPLACE'); n_neg += 1
            elif d >= bw:
                vg_p.add([v.index], 1.0, 'REPLACE'); n_pos += 1
            elif d <= -bw:
                vg_n.add([v.index], 1.0, 'REPLACE'); n_neg += 1
            else:
                t = (d + bw) / (2.0 * bw)
                vg_p.add([v.index], t, 'REPLACE')
                vg_n.add([v.index], 1.0 - t, 'REPLACE')
                n_blend += 1
        return {"mesh": mesh_name, "plane_point": list(plane_point),
                "plane_normal": [round(nx,4), round(ny,4), round(nz,4)],
                "blend_width": blend_width, "sharp": sharp,
                "group_neg": group_neg, "group_pos": group_pos,
                "counts": {"neg": n_neg, "pos": n_pos, "blend": n_blend}}

    def bm_copy_weights(self, mesh_name, src_group, dst_group):
        """Copy weight values from src_group to dst_group."""
        m = bpy.data.objects.get(mesh_name)
        if not m or m.type != 'MESH': raise ValueError(f"Mesh not found: {mesh_name}")
        src = m.vertex_groups.get(src_group)
        if not src: raise ValueError(f"Source vgroup not found: {src_group}")
        dst = m.vertex_groups.get(dst_group)
        if not dst:
            dst = m.vertex_groups.new(name=dst_group)
        n = 0
        for v in m.data.vertices:
            try:
                w = src.weight(v.index)
                dst.add([v.index], w, 'REPLACE')
                n += 1
            except RuntimeError:
                pass
        return {"mesh": mesh_name, "src": src_group, "dst": dst_group, "copied": n}

    def bm_transfer_weights(self, src_mesh_name, dst_mesh_name):
        """Transfer all vertex weights from src to dst mesh (proximity-based)."""
        src = bpy.data.objects.get(src_mesh_name); dst = bpy.data.objects.get(dst_mesh_name)
        if not src or not dst: raise ValueError("Mesh not found")
        bpy.ops.object.select_all(action='DESELECT')
        src.select_set(True); dst.select_set(True)
        bpy.context.view_layer.objects.active = dst
        bpy.ops.object.data_transfer(use_reverse_transfer=False, data_type='VGROUP_WEIGHTS', use_create=True, vert_mapping='POLYINTERP_NEAREST', layers_select_src='ALL', layers_select_dst='NAME')
        return {"src": src_mesh_name, "dst": dst_mesh_name}

    def bm_clean_weights(self, mesh_name, threshold=0.01):
        """Remove weights below threshold from all groups."""
        m = bpy.data.objects.get(mesh_name)
        if not m or m.type != 'MESH': raise ValueError(f"Mesh not found: {mesh_name}")
        bpy.ops.object.select_all(action='DESELECT')
        m.select_set(True); bpy.context.view_layer.objects.active = m
        bpy.ops.object.vertex_group_clean(group_select_mode='ALL', limit=float(threshold))
        return {"mesh": mesh_name, "threshold": threshold}

    def bm_mirror_weights(self, mesh_name, axis='X'):
        """Mirror vertex group weights across axis (uses Blender's vertex_group_mirror)."""
        m = bpy.data.objects.get(mesh_name)
        if not m or m.type != 'MESH': raise ValueError(f"Mesh not found: {mesh_name}")
        bpy.ops.object.select_all(action='DESELECT')
        m.select_set(True); bpy.context.view_layer.objects.active = m
        bpy.ops.object.vertex_group_mirror(mirror_weights=True, flip_group_names=True, all_groups=True)
        return {"mesh": mesh_name, "axis": axis}

    def bm_get_weights_at_vert(self, mesh_name, vert_index):
        """Debug: list all vertex groups + weights for a single vert."""
        m = bpy.data.objects.get(mesh_name)
        if not m or m.type != 'MESH': raise ValueError(f"Mesh not found: {mesh_name}")
        v = m.data.vertices[vert_index]
        groups = []
        for g in v.groups:
            groups.append({"group": m.vertex_groups[g.group].name, "weight": round(g.weight, 4)})
        return {"mesh": mesh_name, "vert": vert_index, "weights": groups}

    def bm_weight_gradient(self, mesh_name, group_name, vert1_index, vert2_index, weight1=1.0, weight2=0.0):
        """Linear gradient between two verts (weight = lerp based on distance projected onto v1-v2 line)."""
        m = bpy.data.objects.get(mesh_name)
        if not m or m.type != 'MESH': raise ValueError(f"Mesh not found: {mesh_name}")
        v1 = m.data.vertices[vert1_index].co; v2 = m.data.vertices[vert2_index].co
        line = v2 - v1; length_sq = line.length_squared
        vg = m.vertex_groups.get(group_name) or m.vertex_groups.new(name=group_name)
        n = 0
        for v in m.data.vertices:
            if length_sq < 1e-12:
                t = 0.0
            else:
                t = max(0.0, min(1.0, (v.co - v1).dot(line) / length_sq))
            w = weight1 + (weight2 - weight1) * t
            vg.add([v.index], float(w), 'REPLACE'); n += 1
        return {"mesh": mesh_name, "group": group_name, "verts": n}

    def bm_weight_falloff_from_point(self, mesh_name, group_name, center_point, radius, falloff='SMOOTH'):
        """Radial falloff weight assignment (good for organic blends)."""
        m = bpy.data.objects.get(mesh_name)
        if not m or m.type != 'MESH': raise ValueError(f"Mesh not found: {mesh_name}")
        c = mathutils.Vector(center_point); r = float(radius)
        vg = m.vertex_groups.get(group_name) or m.vertex_groups.new(name=group_name)
        def w(dist):
            if dist >= r: return 0.0
            x = dist / r
            if falloff == 'CONSTANT': return 1.0
            if falloff == 'LINEAR':   return 1.0 - x
            if falloff == 'SPHERE':   return (1.0 - x*x) ** 0.5
            if falloff == 'SHARP':    return (1.0 - x) ** 2
            return 3*(1-x)**2 - 2*(1-x)**3  # SMOOTH
        mw = m.matrix_world
        n = 0
        for v in m.data.vertices:
            dist = (mw @ v.co - c).length
            weight = w(dist)
            if weight > 0:
                vg.add([v.index], float(weight), 'REPLACE'); n += 1
        return {"mesh": mesh_name, "group": group_name, "affected": n, "radius": radius}

    def bm_remove_zero_weights(self, mesh_name):
        """Remove all zero-weight entries from every group."""
        m = bpy.data.objects.get(mesh_name)
        if not m or m.type != 'MESH': raise ValueError(f"Mesh not found: {mesh_name}")
        bpy.ops.object.select_all(action='DESELECT')
        m.select_set(True); bpy.context.view_layer.objects.active = m
        bpy.ops.object.vertex_group_clean(group_select_mode='ALL', limit=0.0)
        return {"mesh": mesh_name}

    def bm_isolate_bone_weights(self, mesh_name, group_name):
        """Visually isolate one bone's weights for debugging."""
        m = bpy.data.objects.get(mesh_name)
        if not m or m.type != 'MESH': raise ValueError(f"Mesh not found: {mesh_name}")
        vg = m.vertex_groups.get(group_name)
        if not vg: raise ValueError(f"Group not found: {group_name}")
        m.vertex_groups.active_index = vg.index
        return {"mesh": mesh_name, "isolated": group_name}

    def bm_export_weights(self, mesh_name, filepath):
        """Export all vertex group weights to JSON."""
        m = bpy.data.objects.get(mesh_name)
        if not m or m.type != 'MESH': raise ValueError(f"Mesh not found: {mesh_name}")
        data = {"mesh": mesh_name, "groups": {}}
        for vg in m.vertex_groups:
            entries = []
            for v in m.data.vertices:
                try:
                    w = vg.weight(v.index)
                    if w > 0: entries.append([v.index, round(w, 5)])
                except RuntimeError:
                    pass
            data["groups"][vg.name] = entries
        with open(filepath, "w") as f:
            json.dump(data, f)
        return {"filepath": filepath, "groups": len(data["groups"])}

    def bm_import_weights(self, mesh_name, filepath):
        """Restore weights from JSON dumped by bm_export_weights."""
        m = bpy.data.objects.get(mesh_name)
        if not m or m.type != 'MESH': raise ValueError(f"Mesh not found: {mesh_name}")
        with open(filepath, "r") as f:
            data = json.load(f)
        for gname, entries in data.get("groups", {}).items():
            vg = m.vertex_groups.get(gname) or m.vertex_groups.new(name=gname)
            for idx, w in entries:
                vg.add([int(idx)], float(w), 'REPLACE')
        return {"mesh": mesh_name, "imported_groups": len(data.get("groups", {}))}

    # ---- Optimizers / remeshers ----

    def bm_quadriflow_remesh(self, name, target_faces=5000, use_paint_symmetry=False, use_preserve_sharp=True, use_preserve_boundary=True, smooth_normals=True):
        """QuadriFlow (built-in Blender) — best automatic quad remesher. Field-aligned."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        before = len(o.data.polygons)
        bpy.ops.object.quadriflow_remesh(target_faces=int(target_faces),
                                          use_paint_symmetry=bool(use_paint_symmetry),
                                          use_preserve_sharp=bool(use_preserve_sharp),
                                          use_preserve_boundary=bool(use_preserve_boundary),
                                          smooth_normals=bool(smooth_normals))
        return {"name": name, "target_faces": target_faces, "before": before, "after": len(o.data.polygons)}

    def bm_decimate_planar(self, name, angle_limit_deg=5):
        """Planar decimation — collapses only flat regions. Preserves curvature."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        before = len(o.data.polygons)
        m = o.modifiers.new("Decimate_planar", 'DECIMATE')
        m.decimate_type = 'DISSOLVE'
        import math as _m
        m.angle_limit = _m.radians(float(angle_limit_deg))
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.modifier_apply(modifier=m.name)
        return {"name": name, "before": before, "after": len(o.data.polygons), "angle": angle_limit_deg}

    def bm_decimate_unsubdivide(self, name, iterations=2):
        """Unsubdivide — reverses subdivision. Great for restoring base mesh."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        before = len(o.data.polygons)
        m = o.modifiers.new("Decimate_unsub", 'DECIMATE')
        m.decimate_type = 'UNSUBDIV'
        m.iterations = int(iterations)
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.modifier_apply(modifier=m.name)
        return {"name": name, "before": before, "after": len(o.data.polygons), "iterations": iterations}

    def bm_optimize_for_polycount(self, name, target_faces, preserve_uv=True, prefer_quads=True):
        """Smart polycount reduction — tries QuadriFlow first (quads), falls back to Decimate."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        before = len(o.data.polygons)
        if prefer_quads:
            try:
                return self.bm_quadriflow_remesh(name, target_faces=int(target_faces))
            except Exception as e:
                pass  # fall through to decimate
        ratio = float(target_faces) / max(before, 1)
        return self.bm_decimate(name, ratio=min(1.0, ratio))

    def bm_equalize_edges(self, name, iterations=3, factor=0.5):
        """Relax verts to make edge lengths more uniform (improves topology evenness)."""
        return self.bm_smooth_verts(name, vert_filter={"all": True}, factor=float(factor), iterations=int(iterations))

    def bm_planar_faces(self, name, threshold_deg=2):
        """Flatten near-coplanar faces (cleans up subtle bumps after boolean ops)."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        import math as _m
        bpy.ops.mesh.face_make_planar(factor=1.0, repeat=1)
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"name": name, "threshold": threshold_deg}

    def bm_minimize_poles(self, name, max_iterations=3):
        """Iteratively dissolve high-poles. Useful for fan-triangulation cleanup."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        results = []
        for i in range(int(max_iterations)):
            r = self.bm_dissolve_limited(name, angle_deg=2)
            results.append(r["after"])
            if i > 0 and results[-1] == results[-2]:
                break
        return {"name": name, "iterations": results}

    def bm_score_mesh_quality(self, name):
        """Comprehensive mesh quality score 0-100. Combines warn_topology + edge variance + pole count."""
        warn = self.bm_warn_topology(name)
        sym = None
        try:
            sym = self.bm_check_symmetry(name, axis='x')
        except Exception:
            pass
        return {"name": name, "score": warn["topology_score"], "stats": warn["stats"], "warnings": warn["warnings"], "symmetry": sym}

    def bm_compare_meshes(self, name1, name2):
        """Compare 2 meshes — vert/edge/poly diff, dim diff, quality score diff."""
        o1 = bpy.data.objects.get(name1); o2 = bpy.data.objects.get(name2)
        if not o1 or not o2: raise ValueError("Mesh not found")
        bb1 = self._bm_world_bbox(o1); bb2 = self._bm_world_bbox(o2)
        dims1 = [bb1[1][i]-bb1[0][i] for i in range(3)] if bb1 else None
        dims2 = [bb2[1][i]-bb2[0][i] for i in range(3)] if bb2 else None
        s1 = self.bm_warn_topology(name1); s2 = self.bm_warn_topology(name2)
        return {
            "name1": name1, "name2": name2,
            "verts_diff": len(o2.data.vertices) - len(o1.data.vertices),
            "polys_diff": len(o2.data.polygons) - len(o1.data.polygons),
            "dims": [self._r(dims1) if dims1 else None, self._r(dims2) if dims2 else None],
            "score_diff": s2["topology_score"] - s1["topology_score"],
        }

    # ---- Physics ----

    def bm_add_cloth(self, name, mass=0.3, tension_stiffness=15, compression_stiffness=15, shear_stiffness=5, bending_stiffness=0.5, quality=5):
        """Add Cloth physics to mesh."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        bpy.context.view_layer.objects.active = o
        if not o.modifiers.get('Cloth'):
            bpy.ops.object.modifier_add(type='CLOTH')
        s = o.modifiers['Cloth'].settings
        s.mass = float(mass)
        s.tension_stiffness = float(tension_stiffness)
        s.compression_stiffness = float(compression_stiffness)
        s.shear_stiffness = float(shear_stiffness)
        s.bending_stiffness = float(bending_stiffness)
        s.quality = int(quality)
        return {"name": name, "physics": "CLOTH"}

    def bm_add_fluid(self, name, type='DOMAIN', domain_type='GAS', resolution=64):
        """type: DOMAIN|FLOW|EFFECTOR. domain_type: GAS|LIQUID."""
        o = bpy.data.objects.get(name)
        if not o: raise ValueError(f"Not found: {name}")
        bpy.context.view_layer.objects.active = o
        if not o.modifiers.get('Fluid'):
            bpy.ops.object.modifier_add(type='FLUID')
        f = o.modifiers['Fluid']
        f.fluid_type = type
        if type == 'DOMAIN':
            f.domain_settings.domain_type = domain_type
            f.domain_settings.resolution_max = int(resolution)
        return {"name": name, "fluid_type": type, "domain_type": domain_type if type=='DOMAIN' else None}

    def bm_add_softbody(self, name, mass=1.0, friction=0.5, goal_default=0.7):
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        bpy.context.view_layer.objects.active = o
        if not o.modifiers.get('Softbody'):
            bpy.ops.object.modifier_add(type='SOFT_BODY')
        s = o.soft_body
        if s:
            s.mass = float(mass); s.friction = float(friction); s.goal_default = float(goal_default)
        return {"name": name, "physics": "SOFTBODY"}

    def bm_add_rigidbody(self, name, type='ACTIVE', mass=1.0, collision_shape='CONVEX_HULL', friction=0.5, restitution=0.0):
        """type: ACTIVE (dynamic) | PASSIVE (static). shape: BOX|SPHERE|CAPSULE|CONVEX_HULL|MESH."""
        o = bpy.data.objects.get(name)
        if not o: raise ValueError(f"Not found: {name}")
        bpy.context.view_layer.objects.active = o
        bpy.ops.rigidbody.object_add()
        rb = o.rigid_body
        rb.type = type
        rb.mass = float(mass)
        rb.collision_shape = collision_shape
        rb.friction = float(friction)
        rb.restitution = float(restitution)
        return {"name": name, "rb_type": type, "mass": mass}

    def bm_add_collision(self, name, damping=0.1, friction=0.5):
        o = bpy.data.objects.get(name)
        if not o: raise ValueError(f"Not found: {name}")
        bpy.context.view_layer.objects.active = o
        if not o.modifiers.get('Collision'):
            bpy.ops.object.modifier_add(type='COLLISION')
        if o.collision:
            o.collision.damping = float(damping)
            o.collision.cloth_friction = float(friction)
        return {"name": name, "physics": "COLLISION"}

    def bm_bake_physics(self, start_frame=1, end_frame=250):
        """Bake all physics simulations in scene from start to end."""
        sc = bpy.context.scene
        sc.frame_start = int(start_frame); sc.frame_end = int(end_frame)
        bpy.ops.ptcache.bake_all(bake=True)
        return {"start": start_frame, "end": end_frame, "baked": True}

    def bm_add_particle_system(self, name, type='EMITTER', count=1000, frame_start=1, frame_end=200, lifetime=50):
        """type: EMITTER|HAIR."""
        o = bpy.data.objects.get(name)
        if not o or o.type != 'MESH': raise ValueError(f"Mesh not found: {name}")
        bpy.context.view_layer.objects.active = o
        ps = o.modifiers.new("Particles", 'PARTICLE_SYSTEM')
        s = o.particle_systems[-1].settings
        s.type = type
        s.count = int(count)
        if type == 'EMITTER':
            s.frame_start = int(frame_start)
            s.frame_end = int(frame_end)
            s.lifetime = int(lifetime)
        return {"name": name, "particle_type": type, "count": count}

    def bm_set_gravity(self, gravity=(0,0,-9.81), use_gravity=True):
        sc = bpy.context.scene
        sc.gravity = mathutils.Vector(gravity)
        sc.use_gravity = bool(use_gravity)
        return {"gravity": list(sc.gravity), "use_gravity": sc.use_gravity}

    def bm_add_force_field(self, name='ForceField', type='WIND', location=(0,0,0), strength=1.0):
        """type: WIND|VORTEX|TURBULENCE|MAGNETIC|HARMONIC|CURVE_GUIDE|TEXTURE|GUIDE."""
        bpy.ops.object.empty_add(type='SPHERE', location=location)
        e = bpy.context.view_layer.objects.active
        e.name = name
        bpy.ops.object.forcefield_toggle()
        e.field.type = type
        e.field.strength = float(strength)
        return {"name": name, "field_type": type, "strength": strength}

    # ---- Generic property animation ----

    def bm_keyframe_property(self, object_name, data_path, frame, value, index=-1):
        """Insert keyframe on ANY property via data_path. Examples:
        - 'location', value=[x,y,z]
        - 'rotation_euler', value=[x,y,z]
        - 'hide_render', value=True"""
        o = bpy.data.objects.get(object_name)
        if not o: raise ValueError(f"Object not found: {object_name}")
        target = o
        parts = data_path.split('.')
        for p in parts[:-1]:
            target = getattr(target, p)
        final_attr = parts[-1]
        if isinstance(value, (list, tuple)):
            setattr(target, final_attr, value)
        else:
            setattr(target, final_attr, value)
        if hasattr(target, 'keyframe_insert'):
            target.keyframe_insert(data_path=final_attr, frame=int(frame), index=int(index))
        else:
            o.keyframe_insert(data_path=data_path, frame=int(frame), index=int(index))
        return {"object": object_name, "path": data_path, "frame": frame}

    def bm_add_driver(self, target_object, target_data_path, source_object, source_data_path, expression="var"):
        """Add driver: target driven by source. data_path like 'rotation_euler[2]' for Z rotation."""
        t = bpy.data.objects.get(target_object); s = bpy.data.objects.get(source_object)
        if not t or not s: raise ValueError("Object not found")
        path = target_data_path; idx = -1
        import re
        m = re.match(r'^(.+)\[(\d+)\]$', target_data_path)
        if m:
            path = m.group(1); idx = int(m.group(2))
        d = t.driver_add(path, idx) if idx >= 0 else t.driver_add(path)
        drv = d.driver if hasattr(d, 'driver') else d[0].driver
        drv.type = 'SCRIPTED'
        drv.expression = expression
        v = drv.variables.new()
        v.name = 'var'
        v.targets[0].id = s
        v.targets[0].data_path = source_data_path
        return {"target": target_object, "source": source_object, "expression": expression}

    def bm_cyclic_action(self, action_name, mode='REPEAT', before='NONE'):
        """Make action loop via Cycles f-modifier. mode: REPEAT|REPEAT_OFFSET|MIRROR."""
        a = bpy.data.actions.get(action_name)
        if not a: raise ValueError(f"Action not found: {action_name}")
        n = 0
        try:
            for layer in a.layers:
                for strip in layer.strips:
                    for slot in a.slots:
                        cb = strip.channelbag(slot)
                        if cb is None: continue
                        for fc in cb.fcurves:
                            mod = fc.modifiers.new('CYCLES')
                            mod.mode_before = before
                            mod.mode_after = mode
                            n += 1
        except AttributeError:
            for fc in a.fcurves:
                mod = fc.modifiers.new('CYCLES')
                mod.mode_before = before
                mod.mode_after = mode
                n += 1
        return {"action": action_name, "fcurves_cycled": n, "mode": mode}

    def bm_keyframe_material_emission(self, material_name, strength, frame):
        """Keyframe Principled BSDF emission strength."""
        mat = bpy.data.materials.get(material_name)
        if not mat or not mat.node_tree: raise ValueError(f"Material/nodes not found: {material_name}")
        for node in mat.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED' and 'Emission Strength' in node.inputs:
                node.inputs['Emission Strength'].default_value = float(strength)
                node.inputs['Emission Strength'].keyframe_insert(data_path='default_value', frame=int(frame))
                return {"material": material_name, "strength": strength, "frame": frame}
        return {"warning": "no Principled BSDF found"}

    def bm_keyframe_material_color(self, material_name, color, frame):
        """Keyframe Principled BSDF base color. color: [r,g,b,a]."""
        mat = bpy.data.materials.get(material_name)
        if not mat or not mat.node_tree: raise ValueError(f"Material/nodes not found: {material_name}")
        for node in mat.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                node.inputs['Base Color'].default_value = (color[0], color[1], color[2], color[3] if len(color) > 3 else 1.0)
                node.inputs['Base Color'].keyframe_insert(data_path='default_value', frame=int(frame))
                return {"material": material_name, "color": color, "frame": frame}
        return {"warning": "no Principled BSDF found"}

    def bm_animate_visibility(self, object_name, frame, visible=True):
        """Keyframe object visibility (viewport + render) at frame."""
        o = bpy.data.objects.get(object_name)
        if not o: raise ValueError(f"Object not found: {object_name}")
        o.hide_viewport = not bool(visible)
        o.hide_render = not bool(visible)
        o.keyframe_insert(data_path='hide_viewport', frame=int(frame))
        o.keyframe_insert(data_path='hide_render', frame=int(frame))
        return {"object": object_name, "frame": frame, "visible": visible}

    # ---- Texture resize ----

    def bm_resize_texture(self, image_name, width, height, save_path=None):
        """Resize an image in Blender. If save_path given, also save to disk."""
        img = bpy.data.images.get(image_name)
        if not img: raise ValueError(f"Image not found: {image_name}")
        img.scale(int(width), int(height))
        if save_path:
            img.save_render(save_path)
        return {"image": image_name, "new_size": [width, height], "saved": save_path}

    def bm_set_area_type(self, area_index, type):
        """Change area type. type: VIEW_3D|IMAGE_EDITOR|OUTLINER|PROPERTIES|TEXT_EDITOR|NODE_EDITOR|FILE_BROWSER|DOPESHEET_EDITOR|GRAPH_EDITOR|NLA_EDITOR|TIMELINE."""
        areas = list(bpy.context.screen.areas)
        if area_index < 0 or area_index >= len(areas):
            raise ValueError(f"area_index out of range: 0..{len(areas)-1}")
        areas[area_index].type = type
        return {"area_index": area_index, "type": type}

    # ====================================================================
    # End BM_EXT v3
    # ====================================================================

    # ====================================================================
    # End BM_EXT v2
    # ====================================================================

    # ====================================================================
    # End BM_EXT
    # ====================================================================

    def get_scene_info(self):
        """Get information about the current Blender scene"""
        try:
            print("Getting scene info...")
            # Simplify the scene info to reduce data size
            scene_info = {
                "name": bpy.context.scene.name,
                "object_count": len(bpy.context.scene.objects),
                "objects": [],
                "materials_count": len(bpy.data.materials),
            }

            # Collect minimal object information (limit to first 10 objects)
            for i, obj in enumerate(bpy.context.scene.objects):
                if i >= 10:  # Reduced from 20 to 10
                    break

                obj_info = {
                    "name": obj.name,
                    "type": obj.type,
                    # Only include basic location data
                    "location": [round(float(obj.location.x), 2),
                                round(float(obj.location.y), 2),
                                round(float(obj.location.z), 2)],
                }
                scene_info["objects"].append(obj_info)

            print(f"Scene info collected: {len(scene_info['objects'])} objects")
            return scene_info
        except Exception as e:
            print(f"Error in get_scene_info: {str(e)}")
            traceback.print_exc()
            return {"error": str(e)}

    @staticmethod
    def _get_aabb(obj):
        """ Returns the world-space axis-aligned bounding box (AABB) of an object. """
        if obj.type != 'MESH':
            raise TypeError("Object must be a mesh")

        # Get the bounding box corners in local space
        local_bbox_corners = [mathutils.Vector(corner) for corner in obj.bound_box]

        # Convert to world coordinates
        world_bbox_corners = [obj.matrix_world @ corner for corner in local_bbox_corners]

        # Compute axis-aligned min/max coordinates
        min_corner = mathutils.Vector(map(min, zip(*world_bbox_corners)))
        max_corner = mathutils.Vector(map(max, zip(*world_bbox_corners)))

        return [
            [*min_corner], [*max_corner]
        ]



    def get_object_info(self, name):
        """Get detailed information about a specific object"""
        obj = bpy.data.objects.get(name)
        if not obj:
            raise ValueError(f"Object not found: {name}")

        # Basic object info
        obj_info = {
            "name": obj.name,
            "type": obj.type,
            "location": [obj.location.x, obj.location.y, obj.location.z],
            "rotation": [obj.rotation_euler.x, obj.rotation_euler.y, obj.rotation_euler.z],
            "scale": [obj.scale.x, obj.scale.y, obj.scale.z],
            "visible": obj.visible_get(),
            "materials": [],
        }

        if obj.type == "MESH":
            bounding_box = self._get_aabb(obj)
            obj_info["world_bounding_box"] = bounding_box

        # Add material slots
        for slot in obj.material_slots:
            if slot.material:
                obj_info["materials"].append(slot.material.name)

        # Add mesh data if applicable
        if obj.type == 'MESH' and obj.data:
            mesh = obj.data
            obj_info["mesh"] = {
                "vertices": len(mesh.vertices),
                "edges": len(mesh.edges),
                "polygons": len(mesh.polygons),
            }

        return obj_info

    def get_viewport_screenshot(self, max_size=800, filepath=None, format="png"):
        """
        Capture a screenshot of the current 3D viewport and save it to the specified path.

        Parameters:
        - max_size: Maximum size in pixels for the largest dimension of the image
        - filepath: Path where to save the screenshot file
        - format: Image format (png, jpg, etc.)

        Returns success/error status
        """
        try:
            if not filepath:
                return {"error": "No filepath provided"}

            # Find the active 3D viewport
            area = None
            for a in bpy.context.screen.areas:
                if a.type == 'VIEW_3D':
                    area = a
                    break

            if not area:
                return {"error": "No 3D viewport found"}

            # Take screenshot with proper context override
            with bpy.context.temp_override(area=area):
                bpy.ops.screen.screenshot_area(filepath=filepath)

            # Load and resize if needed
            img = bpy.data.images.load(filepath)
            width, height = img.size

            if max(width, height) > max_size:
                scale = max_size / max(width, height)
                new_width = int(width * scale)
                new_height = int(height * scale)
                img.scale(new_width, new_height)

                # Set format and save
                img.file_format = format.upper()
                img.save()
                width, height = new_width, new_height

            # Cleanup Blender image data
            bpy.data.images.remove(img)

            return {
                "success": True,
                "width": width,
                "height": height,
                "filepath": filepath
            }

        except Exception as e:
            return {"error": str(e)}

    def execute_code(self, code):
        """Execute arbitrary Blender Python code"""
        # This is powerful but potentially dangerous - use with caution
        try:
            # Create a local namespace for execution
            namespace = {"bpy": bpy}

            # Capture stdout during execution, and return it as result
            capture_buffer = io.StringIO()
            with redirect_stdout(capture_buffer):
                exec(code, namespace)

            captured_output = capture_buffer.getvalue()
            return {"executed": True, "result": captured_output}
        except Exception as e:
            raise Exception(f"Code execution error: {str(e)}")



    def get_polyhaven_categories(self, asset_type):
        """Get categories for a specific asset type from Polyhaven"""
        try:
            if asset_type not in ["hdris", "textures", "models", "all"]:
                return {"error": f"Invalid asset type: {asset_type}. Must be one of: hdris, textures, models, all"}

            response = requests.get(f"https://api.polyhaven.com/categories/{asset_type}", headers=REQ_HEADERS)
            if response.status_code == 200:
                return {"categories": response.json()}
            else:
                return {"error": f"API request failed with status code {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}

    def search_polyhaven_assets(self, asset_type=None, categories=None):
        """Search for assets from Polyhaven with optional filtering"""
        try:
            url = "https://api.polyhaven.com/assets"
            params = {}

            if asset_type and asset_type != "all":
                if asset_type not in ["hdris", "textures", "models"]:
                    return {"error": f"Invalid asset type: {asset_type}. Must be one of: hdris, textures, models, all"}
                params["type"] = asset_type

            if categories:
                params["categories"] = categories

            response = requests.get(url, params=params, headers=REQ_HEADERS)
            if response.status_code == 200:
                # Limit the response size to avoid overwhelming Blender
                assets = response.json()
                # Return only the first 20 assets to keep response size manageable
                limited_assets = {}
                for i, (key, value) in enumerate(assets.items()):
                    if i >= 20:  # Limit to 20 assets
                        break
                    limited_assets[key] = value

                return {"assets": limited_assets, "total_count": len(assets), "returned_count": len(limited_assets)}
            else:
                return {"error": f"API request failed with status code {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}

    def download_polyhaven_asset(self, asset_id, asset_type, resolution="1k", file_format=None):
        try:
            # First get the files information
            files_response = requests.get(f"https://api.polyhaven.com/files/{asset_id}", headers=REQ_HEADERS)
            if files_response.status_code != 200:
                return {"error": f"Failed to get asset files: {files_response.status_code}"}

            files_data = files_response.json()

            # Handle different asset types
            if asset_type == "hdris":
                # For HDRIs, download the .hdr or .exr file
                if not file_format:
                    file_format = "hdr"  # Default format for HDRIs

                if "hdri" in files_data and resolution in files_data["hdri"] and file_format in files_data["hdri"][resolution]:
                    file_info = files_data["hdri"][resolution][file_format]
                    file_url = file_info["url"]

                    # For HDRIs, we need to save to a temporary file first
                    # since Blender can't properly load HDR data directly from memory
                    with tempfile.NamedTemporaryFile(suffix=f".{file_format}", delete=False) as tmp_file:
                        # Download the file
                        response = requests.get(file_url, headers=REQ_HEADERS)
                        if response.status_code != 200:
                            return {"error": f"Failed to download HDRI: {response.status_code}"}

                        tmp_file.write(response.content)
                        tmp_path = tmp_file.name

                    try:
                        # Create a new world if none exists
                        if not bpy.data.worlds:
                            bpy.data.worlds.new("World")

                        world = bpy.data.worlds[0]
                        world.use_nodes = True
                        node_tree = world.node_tree

                        # Clear existing nodes
                        for node in node_tree.nodes:
                            node_tree.nodes.remove(node)

                        # Create nodes
                        tex_coord = node_tree.nodes.new(type='ShaderNodeTexCoord')
                        tex_coord.location = (-800, 0)

                        mapping = node_tree.nodes.new(type='ShaderNodeMapping')
                        mapping.location = (-600, 0)

                        # Load the image from the temporary file
                        env_tex = node_tree.nodes.new(type='ShaderNodeTexEnvironment')
                        env_tex.location = (-400, 0)
                        env_tex.image = bpy.data.images.load(tmp_path)

                        # Use a color space that exists in all Blender versions
                        if file_format.lower() == 'exr':
                            # Try to use Linear color space for EXR files
                            try:
                                env_tex.image.colorspace_settings.name = 'Linear'
                            except:
                                # Fallback to Non-Color if Linear isn't available
                                env_tex.image.colorspace_settings.name = 'Non-Color'
                        else:  # hdr
                            # For HDR files, try these options in order
                            for color_space in ['Linear', 'Linear Rec.709', 'Non-Color']:
                                try:
                                    env_tex.image.colorspace_settings.name = color_space
                                    break  # Stop if we successfully set a color space
                                except:
                                    continue

                        background = node_tree.nodes.new(type='ShaderNodeBackground')
                        background.location = (-200, 0)

                        output = node_tree.nodes.new(type='ShaderNodeOutputWorld')
                        output.location = (0, 0)

                        # Connect nodes
                        node_tree.links.new(tex_coord.outputs['Generated'], mapping.inputs['Vector'])
                        node_tree.links.new(mapping.outputs['Vector'], env_tex.inputs['Vector'])
                        node_tree.links.new(env_tex.outputs['Color'], background.inputs['Color'])
                        node_tree.links.new(background.outputs['Background'], output.inputs['Surface'])

                        # Set as active world
                        bpy.context.scene.world = world

                        # Clean up temporary file
                        try:
                            tempfile._cleanup()  # This will clean up all temporary files
                        except:
                            pass

                        return {
                            "success": True,
                            "message": f"HDRI {asset_id} imported successfully",
                            "image_name": env_tex.image.name
                        }
                    except Exception as e:
                        return {"error": f"Failed to set up HDRI in Blender: {str(e)}"}
                else:
                    return {"error": f"Requested resolution or format not available for this HDRI"}

            elif asset_type == "textures":
                if not file_format:
                    file_format = "jpg"  # Default format for textures

                downloaded_maps = {}

                try:
                    for map_type in files_data:
                        if map_type not in ["blend", "gltf"]:  # Skip non-texture files
                            if resolution in files_data[map_type] and file_format in files_data[map_type][resolution]:
                                file_info = files_data[map_type][resolution][file_format]
                                file_url = file_info["url"]

                                # Use NamedTemporaryFile like we do for HDRIs
                                with tempfile.NamedTemporaryFile(suffix=f".{file_format}", delete=False) as tmp_file:
                                    # Download the file
                                    response = requests.get(file_url, headers=REQ_HEADERS)
                                    if response.status_code == 200:
                                        tmp_file.write(response.content)
                                        tmp_path = tmp_file.name

                                        # Load image from temporary file
                                        image = bpy.data.images.load(tmp_path)
                                        image.name = f"{asset_id}_{map_type}.{file_format}"

                                        # Pack the image into .blend file
                                        image.pack()

                                        # Set color space based on map type
                                        if map_type in ['color', 'diffuse', 'albedo']:
                                            try:
                                                image.colorspace_settings.name = 'sRGB'
                                            except:
                                                pass
                                        else:
                                            try:
                                                image.colorspace_settings.name = 'Non-Color'
                                            except:
                                                pass

                                        downloaded_maps[map_type] = image

                                        # Clean up temporary file
                                        try:
                                            os.unlink(tmp_path)
                                        except:
                                            pass

                    if not downloaded_maps:
                        return {"error": f"No texture maps found for the requested resolution and format"}

                    # Create a new material with the downloaded textures
                    mat = bpy.data.materials.new(name=asset_id)
                    mat.use_nodes = True
                    nodes = mat.node_tree.nodes
                    links = mat.node_tree.links

                    # Clear default nodes
                    for node in nodes:
                        nodes.remove(node)

                    # Create output node
                    output = nodes.new(type='ShaderNodeOutputMaterial')
                    output.location = (300, 0)

                    # Create principled BSDF node
                    principled = nodes.new(type='ShaderNodeBsdfPrincipled')
                    principled.location = (0, 0)
                    links.new(principled.outputs[0], output.inputs[0])

                    # Add texture nodes based on available maps
                    tex_coord = nodes.new(type='ShaderNodeTexCoord')
                    tex_coord.location = (-800, 0)

                    mapping = nodes.new(type='ShaderNodeMapping')
                    mapping.location = (-600, 0)
                    mapping.vector_type = 'TEXTURE'  # Changed from default 'POINT' to 'TEXTURE'
                    links.new(tex_coord.outputs['UV'], mapping.inputs['Vector'])

                    # Position offset for texture nodes
                    x_pos = -400
                    y_pos = 300

                    # Connect different texture maps
                    for map_type, image in downloaded_maps.items():
                        tex_node = nodes.new(type='ShaderNodeTexImage')
                        tex_node.location = (x_pos, y_pos)
                        tex_node.image = image

                        # Set color space based on map type
                        if map_type.lower() in ['color', 'diffuse', 'albedo']:
                            try:
                                tex_node.image.colorspace_settings.name = 'sRGB'
                            except:
                                pass  # Use default if sRGB not available
                        else:
                            try:
                                tex_node.image.colorspace_settings.name = 'Non-Color'
                            except:
                                pass  # Use default if Non-Color not available

                        links.new(mapping.outputs['Vector'], tex_node.inputs['Vector'])

                        # Connect to appropriate input on Principled BSDF
                        if map_type.lower() in ['color', 'diffuse', 'albedo']:
                            links.new(tex_node.outputs['Color'], principled.inputs['Base Color'])
                        elif map_type.lower() in ['roughness', 'rough']:
                            links.new(tex_node.outputs['Color'], principled.inputs['Roughness'])
                        elif map_type.lower() in ['metallic', 'metalness', 'metal']:
                            links.new(tex_node.outputs['Color'], principled.inputs['Metallic'])
                        elif map_type.lower() in ['normal', 'nor']:
                            # Add normal map node
                            normal_map = nodes.new(type='ShaderNodeNormalMap')
                            normal_map.location = (x_pos + 200, y_pos)
                            links.new(tex_node.outputs['Color'], normal_map.inputs['Color'])
                            links.new(normal_map.outputs['Normal'], principled.inputs['Normal'])
                        elif map_type in ['displacement', 'disp', 'height']:
                            # Add displacement node
                            disp_node = nodes.new(type='ShaderNodeDisplacement')
                            disp_node.location = (x_pos + 200, y_pos - 200)
                            links.new(tex_node.outputs['Color'], disp_node.inputs['Height'])
                            links.new(disp_node.outputs['Displacement'], output.inputs['Displacement'])

                        y_pos -= 250

                    return {
                        "success": True,
                        "message": f"Texture {asset_id} imported as material",
                        "material": mat.name,
                        "maps": list(downloaded_maps.keys())
                    }

                except Exception as e:
                    return {"error": f"Failed to process textures: {str(e)}"}

            elif asset_type == "models":
                # For models, prefer glTF format if available
                if not file_format:
                    file_format = "gltf"  # Default format for models

                if file_format in files_data and resolution in files_data[file_format]:
                    file_info = files_data[file_format][resolution][file_format]
                    file_url = file_info["url"]

                    # Create a temporary directory to store the model and its dependencies
                    temp_dir = tempfile.mkdtemp()
                    main_file_path = ""

                    try:
                        # Download the main model file
                        main_file_name = file_url.split("/")[-1]
                        main_file_path = os.path.join(temp_dir, main_file_name)

                        response = requests.get(file_url, headers=REQ_HEADERS)
                        if response.status_code != 200:
                            return {"error": f"Failed to download model: {response.status_code}"}

                        with open(main_file_path, "wb") as f:
                            f.write(response.content)

                        # Check for included files and download them
                        if "include" in file_info and file_info["include"]:
                            for include_path, include_info in file_info["include"].items():
                                # Get the URL for the included file - this is the fix
                                include_url = include_info["url"]

                                # Create the directory structure for the included file
                                include_file_path = os.path.join(temp_dir, include_path)
                                os.makedirs(os.path.dirname(include_file_path), exist_ok=True)

                                # Download the included file
                                include_response = requests.get(include_url, headers=REQ_HEADERS)
                                if include_response.status_code == 200:
                                    with open(include_file_path, "wb") as f:
                                        f.write(include_response.content)
                                else:
                                    print(f"Failed to download included file: {include_path}")

                        # Import the model into Blender
                        if file_format == "gltf" or file_format == "glb":
                            bpy.ops.import_scene.gltf(filepath=main_file_path)
                        elif file_format == "fbx":
                            bpy.ops.import_scene.fbx(filepath=main_file_path)
                        elif file_format == "obj":
                            bpy.ops.import_scene.obj(filepath=main_file_path)
                        elif file_format == "blend":
                            # For blend files, we need to append or link
                            with bpy.data.libraries.load(main_file_path, link=False) as (data_from, data_to):
                                data_to.objects = data_from.objects

                            # Link the objects to the scene
                            for obj in data_to.objects:
                                if obj is not None:
                                    bpy.context.collection.objects.link(obj)
                        else:
                            return {"error": f"Unsupported model format: {file_format}"}

                        # Get the names of imported objects
                        imported_objects = [obj.name for obj in bpy.context.selected_objects]

                        return {
                            "success": True,
                            "message": f"Model {asset_id} imported successfully",
                            "imported_objects": imported_objects
                        }
                    except Exception as e:
                        return {"error": f"Failed to import model: {str(e)}"}
                    finally:
                        # Clean up temporary directory
                        with suppress(Exception):
                            shutil.rmtree(temp_dir)
                else:
                    return {"error": f"Requested format or resolution not available for this model"}

            else:
                return {"error": f"Unsupported asset type: {asset_type}"}

        except Exception as e:
            return {"error": f"Failed to download asset: {str(e)}"}

    def set_texture(self, object_name, texture_id):
        """Apply a previously downloaded Polyhaven texture to an object by creating a new material"""
        try:
            # Get the object
            obj = bpy.data.objects.get(object_name)
            if not obj:
                return {"error": f"Object not found: {object_name}"}

            # Make sure object can accept materials
            if not hasattr(obj, 'data') or not hasattr(obj.data, 'materials'):
                return {"error": f"Object {object_name} cannot accept materials"}

            # Find all images related to this texture and ensure they're properly loaded
            texture_images = {}
            for img in bpy.data.images:
                if img.name.startswith(texture_id + "_"):
                    # Extract the map type from the image name
                    map_type = img.name.split('_')[-1].split('.')[0]

                    # Force a reload of the image
                    img.reload()

                    # Ensure proper color space
                    if map_type.lower() in ['color', 'diffuse', 'albedo']:
                        try:
                            img.colorspace_settings.name = 'sRGB'
                        except:
                            pass
                    else:
                        try:
                            img.colorspace_settings.name = 'Non-Color'
                        except:
                            pass

                    # Ensure the image is packed
                    if not img.packed_file:
                        img.pack()

                    texture_images[map_type] = img
                    print(f"Loaded texture map: {map_type} - {img.name}")

                    # Debug info
                    print(f"Image size: {img.size[0]}x{img.size[1]}")
                    print(f"Color space: {img.colorspace_settings.name}")
                    print(f"File format: {img.file_format}")
                    print(f"Is packed: {bool(img.packed_file)}")

            if not texture_images:
                return {"error": f"No texture images found for: {texture_id}. Please download the texture first."}

            # Create a new material
            new_mat_name = f"{texture_id}_material_{object_name}"

            # Remove any existing material with this name to avoid conflicts
            existing_mat = bpy.data.materials.get(new_mat_name)
            if existing_mat:
                bpy.data.materials.remove(existing_mat)

            new_mat = bpy.data.materials.new(name=new_mat_name)
            new_mat.use_nodes = True

            # Set up the material nodes
            nodes = new_mat.node_tree.nodes
            links = new_mat.node_tree.links

            # Clear default nodes
            nodes.clear()

            # Create output node
            output = nodes.new(type='ShaderNodeOutputMaterial')
            output.location = (600, 0)

            # Create principled BSDF node
            principled = nodes.new(type='ShaderNodeBsdfPrincipled')
            principled.location = (300, 0)
            links.new(principled.outputs[0], output.inputs[0])

            # Add texture nodes based on available maps
            tex_coord = nodes.new(type='ShaderNodeTexCoord')
            tex_coord.location = (-800, 0)

            mapping = nodes.new(type='ShaderNodeMapping')
            mapping.location = (-600, 0)
            mapping.vector_type = 'TEXTURE'  # Changed from default 'POINT' to 'TEXTURE'
            links.new(tex_coord.outputs['UV'], mapping.inputs['Vector'])

            # Position offset for texture nodes
            x_pos = -400
            y_pos = 300

            # Connect different texture maps
            for map_type, image in texture_images.items():
                tex_node = nodes.new(type='ShaderNodeTexImage')
                tex_node.location = (x_pos, y_pos)
                tex_node.image = image

                # Set color space based on map type
                if map_type.lower() in ['color', 'diffuse', 'albedo']:
                    try:
                        tex_node.image.colorspace_settings.name = 'sRGB'
                    except:
                        pass  # Use default if sRGB not available
                else:
                    try:
                        tex_node.image.colorspace_settings.name = 'Non-Color'
                    except:
                        pass  # Use default if Non-Color not available

                links.new(mapping.outputs['Vector'], tex_node.inputs['Vector'])

                # Connect to appropriate input on Principled BSDF
                if map_type.lower() in ['color', 'diffuse', 'albedo']:
                    links.new(tex_node.outputs['Color'], principled.inputs['Base Color'])
                elif map_type.lower() in ['roughness', 'rough']:
                    links.new(tex_node.outputs['Color'], principled.inputs['Roughness'])
                elif map_type.lower() in ['metallic', 'metalness', 'metal']:
                    links.new(tex_node.outputs['Color'], principled.inputs['Metallic'])
                elif map_type.lower() in ['normal', 'nor', 'dx', 'gl']:
                    # Add normal map node
                    normal_map = nodes.new(type='ShaderNodeNormalMap')
                    normal_map.location = (x_pos + 200, y_pos)
                    links.new(tex_node.outputs['Color'], normal_map.inputs['Color'])
                    links.new(normal_map.outputs['Normal'], principled.inputs['Normal'])
                elif map_type.lower() in ['displacement', 'disp', 'height']:
                    # Add displacement node
                    disp_node = nodes.new(type='ShaderNodeDisplacement')
                    disp_node.location = (x_pos + 200, y_pos - 200)
                    disp_node.inputs['Scale'].default_value = 0.1  # Reduce displacement strength
                    links.new(tex_node.outputs['Color'], disp_node.inputs['Height'])
                    links.new(disp_node.outputs['Displacement'], output.inputs['Displacement'])

                y_pos -= 250

            # Second pass: Connect nodes with proper handling for special cases
            texture_nodes = {}

            # First find all texture nodes and store them by map type
            for node in nodes:
                if node.type == 'TEX_IMAGE' and node.image:
                    for map_type, image in texture_images.items():
                        if node.image == image:
                            texture_nodes[map_type] = node
                            break

            # Now connect everything using the nodes instead of images
            # Handle base color (diffuse)
            for map_name in ['color', 'diffuse', 'albedo']:
                if map_name in texture_nodes:
                    links.new(texture_nodes[map_name].outputs['Color'], principled.inputs['Base Color'])
                    print(f"Connected {map_name} to Base Color")
                    break

            # Handle roughness
            for map_name in ['roughness', 'rough']:
                if map_name in texture_nodes:
                    links.new(texture_nodes[map_name].outputs['Color'], principled.inputs['Roughness'])
                    print(f"Connected {map_name} to Roughness")
                    break

            # Handle metallic
            for map_name in ['metallic', 'metalness', 'metal']:
                if map_name in texture_nodes:
                    links.new(texture_nodes[map_name].outputs['Color'], principled.inputs['Metallic'])
                    print(f"Connected {map_name} to Metallic")
                    break

            # Handle normal maps
            for map_name in ['gl', 'dx', 'nor']:
                if map_name in texture_nodes:
                    normal_map_node = nodes.new(type='ShaderNodeNormalMap')
                    normal_map_node.location = (100, 100)
                    links.new(texture_nodes[map_name].outputs['Color'], normal_map_node.inputs['Color'])
                    links.new(normal_map_node.outputs['Normal'], principled.inputs['Normal'])
                    print(f"Connected {map_name} to Normal")
                    break

            # Handle displacement
            for map_name in ['displacement', 'disp', 'height']:
                if map_name in texture_nodes:
                    disp_node = nodes.new(type='ShaderNodeDisplacement')
                    disp_node.location = (300, -200)
                    disp_node.inputs['Scale'].default_value = 0.1  # Reduce displacement strength
                    links.new(texture_nodes[map_name].outputs['Color'], disp_node.inputs['Height'])
                    links.new(disp_node.outputs['Displacement'], output.inputs['Displacement'])
                    print(f"Connected {map_name} to Displacement")
                    break

            # Handle ARM texture (Ambient Occlusion, Roughness, Metallic)
            if 'arm' in texture_nodes:
                separate_rgb = nodes.new(type='ShaderNodeSeparateRGB')
                separate_rgb.location = (-200, -100)
                links.new(texture_nodes['arm'].outputs['Color'], separate_rgb.inputs['Image'])

                # Connect Roughness (G) if no dedicated roughness map
                if not any(map_name in texture_nodes for map_name in ['roughness', 'rough']):
                    links.new(separate_rgb.outputs['G'], principled.inputs['Roughness'])
                    print("Connected ARM.G to Roughness")

                # Connect Metallic (B) if no dedicated metallic map
                if not any(map_name in texture_nodes for map_name in ['metallic', 'metalness', 'metal']):
                    links.new(separate_rgb.outputs['B'], principled.inputs['Metallic'])
                    print("Connected ARM.B to Metallic")

                # For AO (R channel), multiply with base color if we have one
                base_color_node = None
                for map_name in ['color', 'diffuse', 'albedo']:
                    if map_name in texture_nodes:
                        base_color_node = texture_nodes[map_name]
                        break

                if base_color_node:
                    mix_node = nodes.new(type='ShaderNodeMixRGB')
                    mix_node.location = (100, 200)
                    mix_node.blend_type = 'MULTIPLY'
                    mix_node.inputs['Fac'].default_value = 0.8  # 80% influence

                    # Disconnect direct connection to base color
                    for link in base_color_node.outputs['Color'].links:
                        if link.to_socket == principled.inputs['Base Color']:
                            links.remove(link)

                    # Connect through the mix node
                    links.new(base_color_node.outputs['Color'], mix_node.inputs[1])
                    links.new(separate_rgb.outputs['R'], mix_node.inputs[2])
                    links.new(mix_node.outputs['Color'], principled.inputs['Base Color'])
                    print("Connected ARM.R to AO mix with Base Color")

            # Handle AO (Ambient Occlusion) if separate
            if 'ao' in texture_nodes:
                base_color_node = None
                for map_name in ['color', 'diffuse', 'albedo']:
                    if map_name in texture_nodes:
                        base_color_node = texture_nodes[map_name]
                        break

                if base_color_node:
                    mix_node = nodes.new(type='ShaderNodeMixRGB')
                    mix_node.location = (100, 200)
                    mix_node.blend_type = 'MULTIPLY'
                    mix_node.inputs['Fac'].default_value = 0.8  # 80% influence

                    # Disconnect direct connection to base color
                    for link in base_color_node.outputs['Color'].links:
                        if link.to_socket == principled.inputs['Base Color']:
                            links.remove(link)

                    # Connect through the mix node
                    links.new(base_color_node.outputs['Color'], mix_node.inputs[1])
                    links.new(texture_nodes['ao'].outputs['Color'], mix_node.inputs[2])
                    links.new(mix_node.outputs['Color'], principled.inputs['Base Color'])
                    print("Connected AO to mix with Base Color")

            # CRITICAL: Make sure to clear all existing materials from the object
            while len(obj.data.materials) > 0:
                obj.data.materials.pop(index=0)

            # Assign the new material to the object
            obj.data.materials.append(new_mat)

            # CRITICAL: Make the object active and select it
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)

            # CRITICAL: Force Blender to update the material
            bpy.context.view_layer.update()

            # Get the list of texture maps
            texture_maps = list(texture_images.keys())

            # Get info about texture nodes for debugging
            material_info = {
                "name": new_mat.name,
                "has_nodes": new_mat.use_nodes,
                "node_count": len(new_mat.node_tree.nodes),
                "texture_nodes": []
            }

            for node in new_mat.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image:
                    connections = []
                    for output in node.outputs:
                        for link in output.links:
                            connections.append(f"{output.name} → {link.to_node.name}.{link.to_socket.name}")

                    material_info["texture_nodes"].append({
                        "name": node.name,
                        "image": node.image.name,
                        "colorspace": node.image.colorspace_settings.name,
                        "connections": connections
                    })

            return {
                "success": True,
                "message": f"Created new material and applied texture {texture_id} to {object_name}",
                "material": new_mat.name,
                "maps": texture_maps,
                "material_info": material_info
            }

        except Exception as e:
            print(f"Error in set_texture: {str(e)}")
            traceback.print_exc()
            return {"error": f"Failed to apply texture: {str(e)}"}

    def get_telemetry_consent(self):
        """Get the current telemetry consent status"""
        try:
            # Get addon preferences - use the module name
            addon_prefs = bpy.context.preferences.addons.get(__name__)
            if addon_prefs:
                consent = addon_prefs.preferences.telemetry_consent
            else:
                # Fallback to default if preferences not available
                consent = True
        except (AttributeError, KeyError):
            # Fallback to default if preferences not available
            consent = True
        return {"consent": consent}

    def get_polyhaven_status(self):
        """Get the current status of PolyHaven integration"""
        enabled = bpy.context.scene.blendermcp_use_polyhaven
        if enabled:
            return {"enabled": True, "message": "PolyHaven integration is enabled and ready to use."}
        else:
            return {
                "enabled": False,
                "message": """PolyHaven integration is currently disabled. To enable it:
                            1. In the 3D Viewport, find the BlenderMCP panel in the sidebar (press N if hidden)
                            2. Check the 'Use assets from Poly Haven' checkbox
                            3. Restart the connection to Claude"""
        }

    #region Hyper3D
    def get_hyper3d_status(self):
        """Get the current status of Hyper3D Rodin integration"""
        enabled = bpy.context.scene.blendermcp_use_hyper3d
        if enabled:
            if not bpy.context.scene.blendermcp_hyper3d_api_key:
                return {
                    "enabled": False,
                    "message": """Hyper3D Rodin integration is currently enabled, but API key is not given. To enable it:
                                1. In the 3D Viewport, find the BlenderMCP panel in the sidebar (press N if hidden)
                                2. Keep the 'Use Hyper3D Rodin 3D model generation' checkbox checked
                                3. Choose the right plaform and fill in the API Key
                                4. Restart the connection to Claude"""
                }
            mode = bpy.context.scene.blendermcp_hyper3d_mode
            message = f"Hyper3D Rodin integration is enabled and ready to use. Mode: {mode}. " + \
                f"Key type: {'private' if bpy.context.scene.blendermcp_hyper3d_api_key != RODIN_FREE_TRIAL_KEY else 'free_trial'}"
            return {
                "enabled": True,
                "message": message
            }
        else:
            return {
                "enabled": False,
                "message": """Hyper3D Rodin integration is currently disabled. To enable it:
                            1. In the 3D Viewport, find the BlenderMCP panel in the sidebar (press N if hidden)
                            2. Check the 'Use Hyper3D Rodin 3D model generation' checkbox
                            3. Restart the connection to Claude"""
            }

    def create_rodin_job(self, *args, **kwargs):
        match bpy.context.scene.blendermcp_hyper3d_mode:
            case "MAIN_SITE":
                return self.create_rodin_job_main_site(*args, **kwargs)
            case "FAL_AI":
                return self.create_rodin_job_fal_ai(*args, **kwargs)
            case _:
                return f"Error: Unknown Hyper3D Rodin mode!"

    def create_rodin_job_main_site(
            self,
            text_prompt: str=None,
            images: list[tuple[str, str]]=None,
            bbox_condition=None
        ):
        try:
            if images is None:
                images = []
            """Call Rodin API, get the job uuid and subscription key"""
            files = [
                *[("images", (f"{i:04d}{img_suffix}", img)) for i, (img_suffix, img) in enumerate(images)],
                ("tier", (None, "Sketch")),
                ("mesh_mode", (None, "Raw")),
            ]
            if text_prompt:
                files.append(("prompt", (None, text_prompt)))
            if bbox_condition:
                files.append(("bbox_condition", (None, json.dumps(bbox_condition))))
            response = requests.post(
                "https://hyperhuman.deemos.com/api/v2/rodin",
                headers={
                    "Authorization": f"Bearer {bpy.context.scene.blendermcp_hyper3d_api_key}",
                },
                files=files
            )
            data = response.json()
            return data
        except Exception as e:
            return {"error": str(e)}

    def create_rodin_job_fal_ai(
            self,
            text_prompt: str=None,
            images: list[tuple[str, str]]=None,
            bbox_condition=None
        ):
        try:
            req_data = {
                "tier": "Sketch",
            }
            if images:
                req_data["input_image_urls"] = images
            if text_prompt:
                req_data["prompt"] = text_prompt
            if bbox_condition:
                req_data["bbox_condition"] = bbox_condition
            response = requests.post(
                "https://queue.fal.run/fal-ai/hyper3d/rodin",
                headers={
                    "Authorization": f"Key {bpy.context.scene.blendermcp_hyper3d_api_key}",
                    "Content-Type": "application/json",
                },
                json=req_data
            )
            data = response.json()
            return data
        except Exception as e:
            return {"error": str(e)}

    def poll_rodin_job_status(self, *args, **kwargs):
        match bpy.context.scene.blendermcp_hyper3d_mode:
            case "MAIN_SITE":
                return self.poll_rodin_job_status_main_site(*args, **kwargs)
            case "FAL_AI":
                return self.poll_rodin_job_status_fal_ai(*args, **kwargs)
            case _:
                return f"Error: Unknown Hyper3D Rodin mode!"

    def poll_rodin_job_status_main_site(self, subscription_key: str):
        """Call the job status API to get the job status"""
        response = requests.post(
            "https://hyperhuman.deemos.com/api/v2/status",
            headers={
                "Authorization": f"Bearer {bpy.context.scene.blendermcp_hyper3d_api_key}",
            },
            json={
                "subscription_key": subscription_key,
            },
        )
        data = response.json()
        return {
            "status_list": [i["status"] for i in data["jobs"]]
        }

    def poll_rodin_job_status_fal_ai(self, request_id: str):
        """Call the job status API to get the job status"""
        response = requests.get(
            f"https://queue.fal.run/fal-ai/hyper3d/requests/{request_id}/status",
            headers={
                "Authorization": f"KEY {bpy.context.scene.blendermcp_hyper3d_api_key}",
            },
        )
        data = response.json()
        return data

    @staticmethod
    def _clean_imported_glb(filepath, mesh_name=None):
        # Get the set of existing objects before import
        existing_objects = set(bpy.data.objects)

        # Import the GLB file
        bpy.ops.import_scene.gltf(filepath=filepath)

        # Ensure the context is updated
        bpy.context.view_layer.update()

        # Get all imported objects
        imported_objects = list(set(bpy.data.objects) - existing_objects)
        # imported_objects = [obj for obj in bpy.context.view_layer.objects if obj.select_get()]

        if not imported_objects:
            print("Error: No objects were imported.")
            return

        # Identify the mesh object
        mesh_obj = None

        if len(imported_objects) == 1 and imported_objects[0].type == 'MESH':
            mesh_obj = imported_objects[0]
            print("Single mesh imported, no cleanup needed.")
        else:
            if len(imported_objects) == 2:
                empty_objs = [i for i in imported_objects if i.type == "EMPTY"]
                if len(empty_objs) != 1:
                    print("Error: Expected an empty node with one mesh child or a single mesh object.")
                    return
                parent_obj = empty_objs.pop()
                if len(parent_obj.children) == 1:
                    potential_mesh = parent_obj.children[0]
                    if potential_mesh.type == 'MESH':
                        print("GLB structure confirmed: Empty node with one mesh child.")

                        # Unparent the mesh from the empty node
                        potential_mesh.parent = None

                        # Remove the empty node
                        bpy.data.objects.remove(parent_obj)
                        print("Removed empty node, keeping only the mesh.")

                        mesh_obj = potential_mesh
                    else:
                        print("Error: Child is not a mesh object.")
                        return
                else:
                    print("Error: Expected an empty node with one mesh child or a single mesh object.")
                    return
            else:
                print("Error: Expected an empty node with one mesh child or a single mesh object.")
                return

        # Rename the mesh if needed
        try:
            if mesh_obj and mesh_obj.name is not None and mesh_name:
                mesh_obj.name = mesh_name
                if mesh_obj.data.name is not None:
                    mesh_obj.data.name = mesh_name
                print(f"Mesh renamed to: {mesh_name}")
        except Exception as e:
            print("Having issue with renaming, give up renaming.")

        return mesh_obj

    def import_generated_asset(self, *args, **kwargs):
        match bpy.context.scene.blendermcp_hyper3d_mode:
            case "MAIN_SITE":
                return self.import_generated_asset_main_site(*args, **kwargs)
            case "FAL_AI":
                return self.import_generated_asset_fal_ai(*args, **kwargs)
            case _:
                return f"Error: Unknown Hyper3D Rodin mode!"

    def import_generated_asset_main_site(self, task_uuid: str, name: str):
        """Fetch the generated asset, import into blender"""
        response = requests.post(
            "https://hyperhuman.deemos.com/api/v2/download",
            headers={
                "Authorization": f"Bearer {bpy.context.scene.blendermcp_hyper3d_api_key}",
            },
            json={
                'task_uuid': task_uuid
            }
        )
        data_ = response.json()
        temp_file = None
        for i in data_["list"]:
            if i["name"].endswith(".glb"):
                temp_file = tempfile.NamedTemporaryFile(
                    delete=False,
                    prefix=task_uuid,
                    suffix=".glb",
                )

                try:
                    # Download the content
                    response = requests.get(i["url"], stream=True)
                    response.raise_for_status()  # Raise an exception for HTTP errors

                    # Write the content to the temporary file
                    for chunk in response.iter_content(chunk_size=8192):
                        temp_file.write(chunk)

                    # Close the file
                    temp_file.close()

                except Exception as e:
                    # Clean up the file if there's an error
                    temp_file.close()
                    os.unlink(temp_file.name)
                    return {"succeed": False, "error": str(e)}

                break
        else:
            return {"succeed": False, "error": "Generation failed. Please first make sure that all jobs of the task are done and then try again later."}

        try:
            obj = self._clean_imported_glb(
                filepath=temp_file.name,
                mesh_name=name
            )
            result = {
                "name": obj.name,
                "type": obj.type,
                "location": [obj.location.x, obj.location.y, obj.location.z],
                "rotation": [obj.rotation_euler.x, obj.rotation_euler.y, obj.rotation_euler.z],
                "scale": [obj.scale.x, obj.scale.y, obj.scale.z],
            }

            if obj.type == "MESH":
                bounding_box = self._get_aabb(obj)
                result["world_bounding_box"] = bounding_box

            return {
                "succeed": True, **result
            }
        except Exception as e:
            return {"succeed": False, "error": str(e)}

    def import_generated_asset_fal_ai(self, request_id: str, name: str):
        """Fetch the generated asset, import into blender"""
        response = requests.get(
            f"https://queue.fal.run/fal-ai/hyper3d/requests/{request_id}",
            headers={
                "Authorization": f"Key {bpy.context.scene.blendermcp_hyper3d_api_key}",
            }
        )
        data_ = response.json()
        temp_file = None

        temp_file = tempfile.NamedTemporaryFile(
            delete=False,
            prefix=request_id,
            suffix=".glb",
        )

        try:
            # Download the content
            response = requests.get(data_["model_mesh"]["url"], stream=True)
            response.raise_for_status()  # Raise an exception for HTTP errors

            # Write the content to the temporary file
            for chunk in response.iter_content(chunk_size=8192):
                temp_file.write(chunk)

            # Close the file
            temp_file.close()

        except Exception as e:
            # Clean up the file if there's an error
            temp_file.close()
            os.unlink(temp_file.name)
            return {"succeed": False, "error": str(e)}

        try:
            obj = self._clean_imported_glb(
                filepath=temp_file.name,
                mesh_name=name
            )
            result = {
                "name": obj.name,
                "type": obj.type,
                "location": [obj.location.x, obj.location.y, obj.location.z],
                "rotation": [obj.rotation_euler.x, obj.rotation_euler.y, obj.rotation_euler.z],
                "scale": [obj.scale.x, obj.scale.y, obj.scale.z],
            }

            if obj.type == "MESH":
                bounding_box = self._get_aabb(obj)
                result["world_bounding_box"] = bounding_box

            return {
                "succeed": True, **result
            }
        except Exception as e:
            return {"succeed": False, "error": str(e)}
    #endregion
 
    #region Sketchfab API
    def get_sketchfab_status(self):
        """Get the current status of Sketchfab integration"""
        enabled = bpy.context.scene.blendermcp_use_sketchfab
        api_key = bpy.context.scene.blendermcp_sketchfab_api_key

        # Test the API key if present
        if api_key:
            try:
                headers = {
                    "Authorization": f"Token {api_key}"
                }

                response = requests.get(
                    "https://api.sketchfab.com/v3/me",
                    headers=headers,
                    timeout=30  # Add timeout of 30 seconds
                )

                if response.status_code == 200:
                    user_data = response.json()
                    username = user_data.get("username", "Unknown user")
                    return {
                        "enabled": True,
                        "message": f"Sketchfab integration is enabled and ready to use. Logged in as: {username}"
                    }
                else:
                    return {
                        "enabled": False,
                        "message": f"Sketchfab API key seems invalid. Status code: {response.status_code}"
                    }
            except requests.exceptions.Timeout:
                return {
                    "enabled": False,
                    "message": "Timeout connecting to Sketchfab API. Check your internet connection."
                }
            except Exception as e:
                return {
                    "enabled": False,
                    "message": f"Error testing Sketchfab API key: {str(e)}"
                }

        if enabled and api_key:
            return {"enabled": True, "message": "Sketchfab integration is enabled and ready to use."}
        elif enabled and not api_key:
            return {
                "enabled": False,
                "message": """Sketchfab integration is currently enabled, but API key is not given. To enable it:
                            1. In the 3D Viewport, find the BlenderMCP panel in the sidebar (press N if hidden)
                            2. Keep the 'Use Sketchfab' checkbox checked
                            3. Enter your Sketchfab API Key
                            4. Restart the connection to Claude"""
            }
        else:
            return {
                "enabled": False,
                "message": """Sketchfab integration is currently disabled. To enable it:
                            1. In the 3D Viewport, find the BlenderMCP panel in the sidebar (press N if hidden)
                            2. Check the 'Use assets from Sketchfab' checkbox
                            3. Enter your Sketchfab API Key
                            4. Restart the connection to Claude"""
            }

    def search_sketchfab_models(self, query, categories=None, count=20, downloadable=True):
        """Search for models on Sketchfab based on query and optional filters"""
        try:
            api_key = bpy.context.scene.blendermcp_sketchfab_api_key
            if not api_key:
                return {"error": "Sketchfab API key is not configured"}

            # Build search parameters with exact fields from Sketchfab API docs
            params = {
                "type": "models",
                "q": query,
                "count": count,
                "downloadable": downloadable,
                "archives_flavours": False
            }

            if categories:
                params["categories"] = categories

            # Make API request to Sketchfab search endpoint
            # The proper format according to Sketchfab API docs for API key auth
            headers = {
                "Authorization": f"Token {api_key}"
            }


            # Use the search endpoint as specified in the API documentation
            response = requests.get(
                "https://api.sketchfab.com/v3/search",
                headers=headers,
                params=params,
                timeout=30  # Add timeout of 30 seconds
            )

            if response.status_code == 401:
                return {"error": "Authentication failed (401). Check your API key."}

            if response.status_code != 200:
                return {"error": f"API request failed with status code {response.status_code}"}

            response_data = response.json()

            # Safety check on the response structure
            if response_data is None:
                return {"error": "Received empty response from Sketchfab API"}

            # Handle 'results' potentially missing from response
            results = response_data.get("results", [])
            if not isinstance(results, list):
                return {"error": f"Unexpected response format from Sketchfab API: {response_data}"}

            return response_data

        except requests.exceptions.Timeout:
            return {"error": "Request timed out. Check your internet connection."}
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON response from Sketchfab API: {str(e)}"}
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"error": str(e)}

    def get_sketchfab_model_preview(self, uid):
        """Get thumbnail preview image of a Sketchfab model by its UID"""
        try:
            import base64
            
            api_key = bpy.context.scene.blendermcp_sketchfab_api_key
            if not api_key:
                return {"error": "Sketchfab API key is not configured"}

            headers = {"Authorization": f"Token {api_key}"}
            
            # Get model info which includes thumbnails
            response = requests.get(
                f"https://api.sketchfab.com/v3/models/{uid}",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 401:
                return {"error": "Authentication failed (401). Check your API key."}
            
            if response.status_code == 404:
                return {"error": f"Model not found: {uid}"}
            
            if response.status_code != 200:
                return {"error": f"Failed to get model info: {response.status_code}"}
            
            data = response.json()
            thumbnails = data.get("thumbnails", {}).get("images", [])
            
            if not thumbnails:
                return {"error": "No thumbnail available for this model"}
            
            # Find a suitable thumbnail (prefer medium size ~640px)
            selected_thumbnail = None
            for thumb in thumbnails:
                width = thumb.get("width", 0)
                if 400 <= width <= 800:
                    selected_thumbnail = thumb
                    break
            
            # Fallback to the first available thumbnail
            if not selected_thumbnail:
                selected_thumbnail = thumbnails[0]
            
            thumbnail_url = selected_thumbnail.get("url")
            if not thumbnail_url:
                return {"error": "Thumbnail URL not found"}
            
            # Download the thumbnail image
            img_response = requests.get(thumbnail_url, timeout=30)
            if img_response.status_code != 200:
                return {"error": f"Failed to download thumbnail: {img_response.status_code}"}
            
            # Encode image as base64
            image_data = base64.b64encode(img_response.content).decode('ascii')
            
            # Determine format from content type or URL
            content_type = img_response.headers.get("Content-Type", "")
            if "png" in content_type or thumbnail_url.endswith(".png"):
                img_format = "png"
            else:
                img_format = "jpeg"
            
            # Get additional model info for context
            model_name = data.get("name", "Unknown")
            author = data.get("user", {}).get("username", "Unknown")
            
            return {
                "success": True,
                "image_data": image_data,
                "format": img_format,
                "model_name": model_name,
                "author": author,
                "uid": uid,
                "thumbnail_width": selected_thumbnail.get("width"),
                "thumbnail_height": selected_thumbnail.get("height")
            }
            
        except requests.exceptions.Timeout:
            return {"error": "Request timed out. Check your internet connection."}
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"error": f"Failed to get model preview: {str(e)}"}

    def download_sketchfab_model(self, uid, normalize_size=False, target_size=1.0):
        """Download a model from Sketchfab by its UID
        
        Parameters:
        - uid: The unique identifier of the Sketchfab model
        - normalize_size: If True, scale the model so its largest dimension equals target_size
        - target_size: The target size in Blender units (meters) for the largest dimension
        """
        try:
            api_key = bpy.context.scene.blendermcp_sketchfab_api_key
            if not api_key:
                return {"error": "Sketchfab API key is not configured"}

            # Use proper authorization header for API key auth
            headers = {
                "Authorization": f"Token {api_key}"
            }

            # Request download URL using the exact endpoint from the documentation
            download_endpoint = f"https://api.sketchfab.com/v3/models/{uid}/download"

            response = requests.get(
                download_endpoint,
                headers=headers,
                timeout=30  # Add timeout of 30 seconds
            )

            if response.status_code == 401:
                return {"error": "Authentication failed (401). Check your API key."}

            if response.status_code != 200:
                return {"error": f"Download request failed with status code {response.status_code}"}

            data = response.json()

            # Safety check for None data
            if data is None:
                return {"error": "Received empty response from Sketchfab API for download request"}

            # Extract download URL with safety checks
            gltf_data = data.get("gltf")
            if not gltf_data:
                return {"error": "No gltf download URL available for this model. Response: " + str(data)}

            download_url = gltf_data.get("url")
            if not download_url:
                return {"error": "No download URL available for this model. Make sure the model is downloadable and you have access."}

            # Download the model (already has timeout)
            model_response = requests.get(download_url, timeout=60)  # 60 second timeout

            if model_response.status_code != 200:
                return {"error": f"Model download failed with status code {model_response.status_code}"}

            # Save to temporary file
            temp_dir = tempfile.mkdtemp()
            zip_file_path = os.path.join(temp_dir, f"{uid}.zip")

            with open(zip_file_path, "wb") as f:
                f.write(model_response.content)

            # Extract the zip file with enhanced security
            with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
                # More secure zip slip prevention
                for file_info in zip_ref.infolist():
                    # Get the path of the file
                    file_path = file_info.filename

                    # Convert directory separators to the current OS style
                    # This handles both / and \ in zip entries
                    target_path = os.path.join(temp_dir, os.path.normpath(file_path))

                    # Get absolute paths for comparison
                    abs_temp_dir = os.path.abspath(temp_dir)
                    abs_target_path = os.path.abspath(target_path)

                    # Ensure the normalized path doesn't escape the target directory
                    if not abs_target_path.startswith(abs_temp_dir):
                        with suppress(Exception):
                            shutil.rmtree(temp_dir)
                        return {"error": "Security issue: Zip contains files with path traversal attempt"}

                    # Additional explicit check for directory traversal
                    if ".." in file_path:
                        with suppress(Exception):
                            shutil.rmtree(temp_dir)
                        return {"error": "Security issue: Zip contains files with directory traversal sequence"}

                # If all files passed security checks, extract them
                zip_ref.extractall(temp_dir)

            # Find the main glTF file
            gltf_files = [f for f in os.listdir(temp_dir) if f.endswith('.gltf') or f.endswith('.glb')]

            if not gltf_files:
                with suppress(Exception):
                    shutil.rmtree(temp_dir)
                return {"error": "No glTF file found in the downloaded model"}

            main_file = os.path.join(temp_dir, gltf_files[0])

            # Import the model
            bpy.ops.import_scene.gltf(filepath=main_file)

            # Get the imported objects
            imported_objects = list(bpy.context.selected_objects)
            imported_object_names = [obj.name for obj in imported_objects]

            # Clean up temporary files
            with suppress(Exception):
                shutil.rmtree(temp_dir)

            # Find root objects (objects without parents in the imported set)
            root_objects = [obj for obj in imported_objects if obj.parent is None]

            # Helper function to recursively get all mesh children
            def get_all_mesh_children(obj):
                """Recursively collect all mesh objects in the hierarchy"""
                meshes = []
                if obj.type == 'MESH':
                    meshes.append(obj)
                for child in obj.children:
                    meshes.extend(get_all_mesh_children(child))
                return meshes

            # Collect ALL meshes from the entire hierarchy (starting from roots)
            all_meshes = []
            for obj in root_objects:
                all_meshes.extend(get_all_mesh_children(obj))
            
            if all_meshes:
                # Calculate combined world bounding box for all meshes
                all_min = mathutils.Vector((float('inf'), float('inf'), float('inf')))
                all_max = mathutils.Vector((float('-inf'), float('-inf'), float('-inf')))
                
                for mesh_obj in all_meshes:
                    # Get world-space bounding box corners
                    for corner in mesh_obj.bound_box:
                        world_corner = mesh_obj.matrix_world @ mathutils.Vector(corner)
                        all_min.x = min(all_min.x, world_corner.x)
                        all_min.y = min(all_min.y, world_corner.y)
                        all_min.z = min(all_min.z, world_corner.z)
                        all_max.x = max(all_max.x, world_corner.x)
                        all_max.y = max(all_max.y, world_corner.y)
                        all_max.z = max(all_max.z, world_corner.z)
                
                # Calculate dimensions
                dimensions = [
                    all_max.x - all_min.x,
                    all_max.y - all_min.y,
                    all_max.z - all_min.z
                ]
                max_dimension = max(dimensions)
                
                # Apply normalization if requested
                scale_applied = 1.0
                if normalize_size and max_dimension > 0:
                    scale_factor = target_size / max_dimension
                    scale_applied = scale_factor
                    
                    # ✅ Only apply scale to ROOT objects (not children!)
                    # Child objects inherit parent's scale through matrix_world
                    for root in root_objects:
                        root.scale = (
                            root.scale.x * scale_factor,
                            root.scale.y * scale_factor,
                            root.scale.z * scale_factor
                        )
                    
                    # Update the scene to recalculate matrix_world for all objects
                    bpy.context.view_layer.update()
                    
                    # Recalculate bounding box after scaling
                    all_min = mathutils.Vector((float('inf'), float('inf'), float('inf')))
                    all_max = mathutils.Vector((float('-inf'), float('-inf'), float('-inf')))
                    
                    for mesh_obj in all_meshes:
                        for corner in mesh_obj.bound_box:
                            world_corner = mesh_obj.matrix_world @ mathutils.Vector(corner)
                            all_min.x = min(all_min.x, world_corner.x)
                            all_min.y = min(all_min.y, world_corner.y)
                            all_min.z = min(all_min.z, world_corner.z)
                            all_max.x = max(all_max.x, world_corner.x)
                            all_max.y = max(all_max.y, world_corner.y)
                            all_max.z = max(all_max.z, world_corner.z)
                    
                    dimensions = [
                        all_max.x - all_min.x,
                        all_max.y - all_min.y,
                        all_max.z - all_min.z
                    ]
                
                world_bounding_box = [[all_min.x, all_min.y, all_min.z], [all_max.x, all_max.y, all_max.z]]
            else:
                world_bounding_box = None
                dimensions = None
                scale_applied = 1.0

            result = {
                "success": True,
                "message": "Model imported successfully",
                "imported_objects": imported_object_names
            }
            
            if world_bounding_box:
                result["world_bounding_box"] = world_bounding_box
            if dimensions:
                result["dimensions"] = [round(d, 4) for d in dimensions]
            if normalize_size:
                result["scale_applied"] = round(scale_applied, 6)
                result["normalized"] = True
            
            return result

        except requests.exceptions.Timeout:
            return {"error": "Request timed out. Check your internet connection and try again with a simpler model."}
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON response from Sketchfab API: {str(e)}"}
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"error": f"Failed to download model: {str(e)}"}
    #endregion

    #region Hunyuan3D
    def get_hunyuan3d_status(self):
        """Get the current status of Hunyuan3D integration"""
        enabled = bpy.context.scene.blendermcp_use_hunyuan3d
        hunyuan3d_mode = bpy.context.scene.blendermcp_hunyuan3d_mode
        if enabled:
            match hunyuan3d_mode:
                case "OFFICIAL_API":
                    if not bpy.context.scene.blendermcp_hunyuan3d_secret_id or not bpy.context.scene.blendermcp_hunyuan3d_secret_key:
                        return {
                            "enabled": False, 
                            "mode": hunyuan3d_mode, 
                            "message": """Hunyuan3D integration is currently enabled, but SecretId or SecretKey is not given. To enable it:
                                1. In the 3D Viewport, find the BlenderMCP panel in the sidebar (press N if hidden)
                                2. Keep the 'Use Tencent Hunyuan 3D model generation' checkbox checked
                                3. Choose the right platform and fill in the SecretId and SecretKey
                                4. Restart the connection to Claude"""
                        }
                case "LOCAL_API":
                    if not bpy.context.scene.blendermcp_hunyuan3d_api_url:
                        return {
                            "enabled": False, 
                            "mode": hunyuan3d_mode, 
                            "message": """Hunyuan3D integration is currently enabled, but API URL  is not given. To enable it:
                                1. In the 3D Viewport, find the BlenderMCP panel in the sidebar (press N if hidden)
                                2. Keep the 'Use Tencent Hunyuan 3D model generation' checkbox checked
                                3. Choose the right platform and fill in the API URL
                                4. Restart the connection to Claude"""
                        }
                case _:
                    return {
                        "enabled": False, 
                        "message": "Hunyuan3D integration is enabled and mode is not supported."
                    }
            return {
                "enabled": True, 
                "mode": hunyuan3d_mode,
                "message": "Hunyuan3D integration is enabled and ready to use."
            }
        return {
            "enabled": False, 
            "message": """Hunyuan3D integration is currently disabled. To enable it:
                        1. In the 3D Viewport, find the BlenderMCP panel in the sidebar (press N if hidden)
                        2. Check the 'Use Tencent Hunyuan 3D model generation' checkbox
                        3. Restart the connection to Claude"""
        }
    
    @staticmethod
    def get_tencent_cloud_sign_headers(
        method: str,
        path: str,
        headParams: dict,
        data: dict,
        service: str,
        region: str,
        secret_id: str,
        secret_key: str,
        host: str = None
    ):
        """Generate the signature header required for Tencent Cloud API requests headers"""
        # Generate timestamp
        timestamp = int(time.time())
        date = datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d")
        
        # If host is not provided, it is generated based on service and region.
        if not host:
            host = f"{service}.tencentcloudapi.com"
        
        endpoint = f"https://{host}"
        
        # Constructing the request body
        payload_str = json.dumps(data)
        
        # ************* Step 1: Concatenate the canonical request string *************
        canonical_uri = path
        canonical_querystring = ""
        ct = "application/json; charset=utf-8"
        canonical_headers = f"content-type:{ct}\nhost:{host}\nx-tc-action:{headParams.get('Action', '').lower()}\n"
        signed_headers = "content-type;host;x-tc-action"
        hashed_request_payload = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
        
        canonical_request = (method + "\n" +
                            canonical_uri + "\n" +
                            canonical_querystring + "\n" +
                            canonical_headers + "\n" +
                            signed_headers + "\n" +
                            hashed_request_payload)

        # ************* Step 2: Construct the reception signature string *************
        credential_scope = f"{date}/{service}/tc3_request"
        hashed_canonical_request = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
        string_to_sign = ("TC3-HMAC-SHA256" + "\n" +
                        str(timestamp) + "\n" +
                        credential_scope + "\n" +
                        hashed_canonical_request)

        # ************* Step 3: Calculate the signature *************
        def sign(key, msg):
            return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

        secret_date = sign(("TC3" + secret_key).encode("utf-8"), date)
        secret_service = sign(secret_date, service)
        secret_signing = sign(secret_service, "tc3_request")
        signature = hmac.new(
            secret_signing, 
            string_to_sign.encode("utf-8"), 
            hashlib.sha256
        ).hexdigest()

        # ************* Step 4: Connect Authorization *************
        authorization = ("TC3-HMAC-SHA256" + " " +
                        "Credential=" + secret_id + "/" + credential_scope + ", " +
                        "SignedHeaders=" + signed_headers + ", " +
                        "Signature=" + signature)

        # Constructing request headers
        headers = {
            "Authorization": authorization,
            "Content-Type": "application/json; charset=utf-8",
            "Host": host,
            "X-TC-Action": headParams.get("Action", ""),
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Version": headParams.get("Version", ""),
            "X-TC-Region": region
        }

        return headers, endpoint

    def create_hunyuan_job(self, *args, **kwargs):
        match bpy.context.scene.blendermcp_hunyuan3d_mode:
            case "OFFICIAL_API":
                return self.create_hunyuan_job_main_site(*args, **kwargs)
            case "LOCAL_API":
                return self.create_hunyuan_job_local_site(*args, **kwargs)
            case _:
                return f"Error: Unknown Hunyuan3D mode!"

    def create_hunyuan_job_main_site(
        self,
        text_prompt: str = None,
        image: str = None
    ):
        try:
            secret_id = bpy.context.scene.blendermcp_hunyuan3d_secret_id
            secret_key = bpy.context.scene.blendermcp_hunyuan3d_secret_key

            if not secret_id or not secret_key:
                return {"error": "SecretId or SecretKey is not given"}

            # Parameter verification
            if not text_prompt and not image:
                return {"error": "Prompt or Image is required"}
            if text_prompt and image:
                return {"error": "Prompt and Image cannot be provided simultaneously"}
            # Fixed parameter configuration
            service = "hunyuan"
            action = "SubmitHunyuanTo3DJob"
            version = "2023-09-01"
            region = "ap-guangzhou"

            headParams={
                "Action": action,
                "Version": version,
                "Region": region,
            }

            # Constructing request parameters
            data = {
                "Num": 1  # The current API limit is only 1
            }

            # Handling text prompts
            if text_prompt:
                if len(text_prompt) > 200:
                    return {"error": "Prompt exceeds 200 characters limit"}
                data["Prompt"] = text_prompt

            # Handling image
            if image:
                if re.match(r'^https?://', image, re.IGNORECASE) is not None:
                    data["ImageUrl"] = image
                else:
                    try:
                        # Convert to Base64 format
                        with open(image, "rb") as f:
                            image_base64 = base64.b64encode(f.read()).decode("ascii")
                        data["ImageBase64"] = image_base64
                    except Exception as e:
                        return {"error": f"Image encoding failed: {str(e)}"}
            
            # Get signed headers
            headers, endpoint = self.get_tencent_cloud_sign_headers("POST", "/", headParams, data, service, region, secret_id, secret_key)

            response = requests.post(
                endpoint,
                headers = headers,
                data = json.dumps(data)
            )

            if response.status_code == 200:
                return response.json()
            return {
                "error": f"API request failed with status {response.status_code}: {response}"
            }
        except Exception as e:
            return {"error": str(e)}

    def create_hunyuan_job_local_site(
        self,
        text_prompt: str = None,
        image: str = None):
        try:
            base_url = bpy.context.scene.blendermcp_hunyuan3d_api_url.rstrip('/')
            octree_resolution = bpy.context.scene.blendermcp_hunyuan3d_octree_resolution
            num_inference_steps = bpy.context.scene.blendermcp_hunyuan3d_num_inference_steps
            guidance_scale = bpy.context.scene.blendermcp_hunyuan3d_guidance_scale
            texture = bpy.context.scene.blendermcp_hunyuan3d_texture

            if not base_url:
                return {"error": "API URL is not given"}
            # Parameter verification
            if not text_prompt and not image:
                return {"error": "Prompt or Image is required"}

            # Constructing request parameters
            data = {
                "octree_resolution": octree_resolution,
                "num_inference_steps": num_inference_steps,
                "guidance_scale": guidance_scale,
                "texture": texture,
            }

            # Handling text prompts
            if text_prompt:
                data["text"] = text_prompt

            # Handling image
            if image:
                if re.match(r'^https?://', image, re.IGNORECASE) is not None:
                    try:
                        resImg = requests.get(image)
                        resImg.raise_for_status()
                        image_base64 = base64.b64encode(resImg.content).decode("ascii")
                        data["image"] = image_base64
                    except Exception as e:
                        return {"error": f"Failed to download or encode image: {str(e)}"} 
                else:
                    try:
                        # Convert to Base64 format
                        with open(image, "rb") as f:
                            image_base64 = base64.b64encode(f.read()).decode("ascii")
                        data["image"] = image_base64
                    except Exception as e:
                        return {"error": f"Image encoding failed: {str(e)}"}

            response = requests.post(
                f"{base_url}/generate",
                json = data,
            )

            if response.status_code != 200:
                return {
                    "error": f"Generation failed: {response.text}"
                }
        
            # Decode base64 and save to temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".glb") as temp_file:
                temp_file.write(response.content)
                temp_file_name = temp_file.name

            # Import the GLB file in the main thread
            def import_handler():
                bpy.ops.import_scene.gltf(filepath=temp_file_name)
                os.unlink(temp_file.name)
                return None
            
            bpy.app.timers.register(import_handler)

            return {
                "status": "DONE",
                "message": "Generation and Import glb succeeded"
            }
        except Exception as e:
            print(f"An error occurred: {e}")
            return {"error": str(e)}
        
    
    def poll_hunyuan_job_status(self, *args, **kwargs):
        return self.poll_hunyuan_job_status_ai(*args, **kwargs)
    
    def poll_hunyuan_job_status_ai(self, job_id: str):
        """Call the job status API to get the job status"""
        print(job_id)
        try:
            secret_id = bpy.context.scene.blendermcp_hunyuan3d_secret_id
            secret_key = bpy.context.scene.blendermcp_hunyuan3d_secret_key

            if not secret_id or not secret_key:
                return {"error": "SecretId or SecretKey is not given"}
            if not job_id:
                return {"error": "JobId is required"}
            
            service = "hunyuan"
            action = "QueryHunyuanTo3DJob"
            version = "2023-09-01"
            region = "ap-guangzhou"

            headParams={
                "Action": action,
                "Version": version,
                "Region": region,
            }

            clean_job_id = job_id.removeprefix("job_")
            data = {
                "JobId": clean_job_id
            }

            headers, endpoint = self.get_tencent_cloud_sign_headers("POST", "/", headParams, data, service, region, secret_id, secret_key)

            response = requests.post(
                endpoint,
                headers=headers,
                data=json.dumps(data)
            )

            if response.status_code == 200:
                return response.json()
            return {
                "error": f"API request failed with status {response.status_code}: {response}"
            }
        except Exception as e:
            return {"error": str(e)}

    def import_generated_asset_hunyuan(self, *args, **kwargs):
        return self.import_generated_asset_hunyuan_ai(*args, **kwargs)
            
    def import_generated_asset_hunyuan_ai(self, name: str , zip_file_url: str):
        if not zip_file_url:
            return {"error": "Zip file not found"}
        
        # Validate URL
        if not re.match(r'^https?://', zip_file_url, re.IGNORECASE):
            return {"error": "Invalid URL format. Must start with http:// or https://"}
        
        # Create a temporary directory
        temp_dir = tempfile.mkdtemp(prefix="tencent_obj_")
        zip_file_path = osp.join(temp_dir, "model.zip")
        obj_file_path = osp.join(temp_dir, "model.obj")
        mtl_file_path = osp.join(temp_dir, "model.mtl")

        try:
            # Download ZIP file
            zip_response = requests.get(zip_file_url, stream=True)
            zip_response.raise_for_status()
            with open(zip_file_path, "wb") as f:
                for chunk in zip_response.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Unzip the ZIP
            with zipfile.ZipFile(zip_file_path, "r") as zip_ref:
                zip_ref.extractall(temp_dir)

            # Find the .obj file (there may be multiple, assuming the main file is model.obj)
            for file in os.listdir(temp_dir):
                if file.endswith(".obj"):
                    obj_file_path = osp.join(temp_dir, file)

            if not osp.exists(obj_file_path):
                return {"succeed": False, "error": "OBJ file not found after extraction"}

            # Import obj file
            if bpy.app.version>=(4, 0, 0):
                bpy.ops.wm.obj_import(filepath=obj_file_path)
            else:
                bpy.ops.import_scene.obj(filepath=obj_file_path)

            imported_objs = [obj for obj in bpy.context.selected_objects if obj.type == 'MESH']
            if not imported_objs:
                return {"succeed": False, "error": "No mesh objects imported"}

            obj = imported_objs[0]
            if name:
                obj.name = name

            result = {
                "name": obj.name,
                "type": obj.type,
                "location": [obj.location.x, obj.location.y, obj.location.z],
                "rotation": [obj.rotation_euler.x, obj.rotation_euler.y, obj.rotation_euler.z],
                "scale": [obj.scale.x, obj.scale.y, obj.scale.z],
            }

            if obj.type == "MESH":
                bounding_box = self._get_aabb(obj)
                result["world_bounding_box"] = bounding_box

            return {"succeed": True, **result}
        except Exception as e:
            return {"succeed": False, "error": str(e)}
        finally:
            #  Clean up temporary zip and obj, save texture and mtl
            try:
                if os.path.exists(zip_file_path):
                    os.remove(zip_file_path) 
                if os.path.exists(obj_file_path):
                    os.remove(obj_file_path)
            except Exception as e:
                print(f"Failed to clean up temporary directory {temp_dir}: {e}")
    #endregion

# Blender Addon Preferences
class BLENDERMCP_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__
    
    telemetry_consent: BoolProperty(
        name="Allow Telemetry",
        description="Allow collection of prompts, code snippets, and screenshots to help improve Blender MCP",
        default=True
    )

    def draw(self, context):
        layout = self.layout
        
        # Telemetry section
        layout.label(text="Telemetry & Privacy:", icon='PREFERENCES')
        
        box = layout.box()
        row = box.row()
        row.prop(self, "telemetry_consent", text="Allow Telemetry")
        
        # Info text
        box.separator()
        if self.telemetry_consent:
            box.label(text="With consent: We collect anonymized prompts, code, and screenshots.", icon='INFO')
        else:
            box.label(text="Without consent: We only collect minimal anonymous usage data", icon='INFO')
            box.label(text="(tool names, success/failure, duration - no prompts or code).", icon='BLANK1')
        box.separator()
        box.label(text="All data is fully anonymized. You can change this anytime.", icon='CHECKMARK')
        
        # Terms and Conditions link
        box.separator()
        row = box.row()
        row.operator("blendermcp.open_terms", text="View Terms and Conditions", icon='TEXT')

# Blender UI Panel
class BLENDERMCP_PT_Panel(bpy.types.Panel):
    bl_label = "Blender MCP"
    bl_idname = "BLENDERMCP_PT_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'BlenderMCP'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.prop(scene, "blendermcp_port")
        layout.prop(scene, "blendermcp_use_polyhaven", text="Use assets from Poly Haven")

        layout.prop(scene, "blendermcp_use_hyper3d", text="Use Hyper3D Rodin 3D model generation")
        if scene.blendermcp_use_hyper3d:
            layout.prop(scene, "blendermcp_hyper3d_mode", text="Rodin Mode")
            layout.prop(scene, "blendermcp_hyper3d_api_key", text="API Key")
            layout.operator("blendermcp.set_hyper3d_free_trial_api_key", text="Set Free Trial API Key")

        layout.prop(scene, "blendermcp_use_sketchfab", text="Use assets from Sketchfab")
        if scene.blendermcp_use_sketchfab:
            layout.prop(scene, "blendermcp_sketchfab_api_key", text="API Key")

        layout.prop(scene, "blendermcp_use_hunyuan3d", text="Use Tencent Hunyuan 3D model generation")
        if scene.blendermcp_use_hunyuan3d:
            layout.prop(scene, "blendermcp_hunyuan3d_mode", text="Hunyuan3D Mode")
            if scene.blendermcp_hunyuan3d_mode == 'OFFICIAL_API':
                layout.prop(scene, "blendermcp_hunyuan3d_secret_id", text="SecretId")
                layout.prop(scene, "blendermcp_hunyuan3d_secret_key", text="SecretKey")
            if scene.blendermcp_hunyuan3d_mode == 'LOCAL_API':
                layout.prop(scene, "blendermcp_hunyuan3d_api_url", text="API URL")
                layout.prop(scene, "blendermcp_hunyuan3d_octree_resolution", text="Octree Resolution")
                layout.prop(scene, "blendermcp_hunyuan3d_num_inference_steps", text="Number of Inference Steps")
                layout.prop(scene, "blendermcp_hunyuan3d_guidance_scale", text="Guidance Scale")
                layout.prop(scene, "blendermcp_hunyuan3d_texture", text="Generate Texture")
        
        if not scene.blendermcp_server_running:
            layout.operator("blendermcp.start_server", text="Connect to MCP server")
        else:
            layout.operator("blendermcp.stop_server", text="Disconnect from MCP server")
            layout.label(text=f"Running on port {scene.blendermcp_port}")

# Operator to set Hyper3D API Key
class BLENDERMCP_OT_SetFreeTrialHyper3DAPIKey(bpy.types.Operator):
    bl_idname = "blendermcp.set_hyper3d_free_trial_api_key"
    bl_label = "Set Free Trial API Key"

    def execute(self, context):
        context.scene.blendermcp_hyper3d_api_key = RODIN_FREE_TRIAL_KEY
        context.scene.blendermcp_hyper3d_mode = 'MAIN_SITE'
        self.report({'INFO'}, "API Key set successfully!")
        return {'FINISHED'}

# Operator to start the server
class BLENDERMCP_OT_StartServer(bpy.types.Operator):
    bl_idname = "blendermcp.start_server"
    bl_label = "Connect to Claude"
    bl_description = "Start the BlenderMCP server to connect with Claude"

    def execute(self, context):
        scene = context.scene

        # Create a new server instance
        if not hasattr(bpy.types, "blendermcp_server") or not bpy.types.blendermcp_server:
            bpy.types.blendermcp_server = BlenderMCPServer(port=scene.blendermcp_port)

        # Start the server
        bpy.types.blendermcp_server.start()
        scene.blendermcp_server_running = True

        return {'FINISHED'}

# Operator to stop the server
class BLENDERMCP_OT_StopServer(bpy.types.Operator):
    bl_idname = "blendermcp.stop_server"
    bl_label = "Stop the connection to Claude"
    bl_description = "Stop the connection to Claude"

    def execute(self, context):
        scene = context.scene

        # Stop the server if it exists
        if hasattr(bpy.types, "blendermcp_server") and bpy.types.blendermcp_server:
            bpy.types.blendermcp_server.stop()
            del bpy.types.blendermcp_server

        scene.blendermcp_server_running = False

        return {'FINISHED'}

# Operator to open Terms and Conditions
class BLENDERMCP_OT_OpenTerms(bpy.types.Operator):
    bl_idname = "blendermcp.open_terms"
    bl_label = "View Terms and Conditions"
    bl_description = "Open the Terms and Conditions document"

    def execute(self, context):
        # Open the Terms and Conditions on GitHub
        terms_url = "https://github.com/ahujasid/blender-mcp/blob/main/TERMS_AND_CONDITIONS.md"
        try:
            import webbrowser
            webbrowser.open(terms_url)
            self.report({'INFO'}, "Terms and Conditions opened in browser")
        except Exception as e:
            self.report({'ERROR'}, f"Could not open Terms and Conditions: {str(e)}")
        
        return {'FINISHED'}

# Registration functions
def register():
    bpy.types.Scene.blendermcp_port = IntProperty(
        name="Port",
        description="Port for the BlenderMCP server",
        default=9876,
        min=1024,
        max=65535
    )

    bpy.types.Scene.blendermcp_server_running = bpy.props.BoolProperty(
        name="Server Running",
        default=False
    )

    bpy.types.Scene.blendermcp_use_polyhaven = bpy.props.BoolProperty(
        name="Use Poly Haven",
        description="Enable Poly Haven asset integration",
        default=False
    )

    bpy.types.Scene.blendermcp_use_hyper3d = bpy.props.BoolProperty(
        name="Use Hyper3D Rodin",
        description="Enable Hyper3D Rodin generatino integration",
        default=False
    )

    bpy.types.Scene.blendermcp_hyper3d_mode = bpy.props.EnumProperty(
        name="Rodin Mode",
        description="Choose the platform used to call Rodin APIs",
        items=[
            ("MAIN_SITE", "hyper3d.ai", "hyper3d.ai"),
            ("FAL_AI", "fal.ai", "fal.ai"),
        ],
        default="MAIN_SITE"
    )

    bpy.types.Scene.blendermcp_hyper3d_api_key = bpy.props.StringProperty(
        name="Hyper3D API Key",
        subtype="PASSWORD",
        description="API Key provided by Hyper3D",
        default=""
    )

    bpy.types.Scene.blendermcp_use_hunyuan3d = bpy.props.BoolProperty(
        name="Use Hunyuan 3D",
        description="Enable Hunyuan asset integration",
        default=False
    )

    bpy.types.Scene.blendermcp_hunyuan3d_mode = bpy.props.EnumProperty(
        name="Hunyuan3D Mode",
        description="Choose a local or official APIs",
        items=[
            ("LOCAL_API", "local api", "local api"),
            ("OFFICIAL_API", "official api", "official api"),
        ],
        default="LOCAL_API"
    )

    bpy.types.Scene.blendermcp_hunyuan3d_secret_id = bpy.props.StringProperty(
        name="Hunyuan 3D SecretId",
        description="SecretId provided by Hunyuan 3D",
        default=""
    )

    bpy.types.Scene.blendermcp_hunyuan3d_secret_key = bpy.props.StringProperty(
        name="Hunyuan 3D SecretKey",
        subtype="PASSWORD",
        description="SecretKey provided by Hunyuan 3D",
        default=""
    )

    bpy.types.Scene.blendermcp_hunyuan3d_api_url = bpy.props.StringProperty(
        name="API URL",
        description="URL of the Hunyuan 3D API service",
        default="http://localhost:8081"
    )

    bpy.types.Scene.blendermcp_hunyuan3d_octree_resolution = bpy.props.IntProperty(
        name="Octree Resolution",
        description="Octree resolution for the 3D generation",
        default=256,
        min=128,
        max=512,
    )

    bpy.types.Scene.blendermcp_hunyuan3d_num_inference_steps = bpy.props.IntProperty(
        name="Number of Inference Steps",
        description="Number of inference steps for the 3D generation",
        default=20,
        min=20,
        max=50,
    )

    bpy.types.Scene.blendermcp_hunyuan3d_guidance_scale = bpy.props.FloatProperty(
        name="Guidance Scale",
        description="Guidance scale for the 3D generation",
        default=5.5,
        min=1.0,
        max=10.0,
    )

    bpy.types.Scene.blendermcp_hunyuan3d_texture = bpy.props.BoolProperty(
        name="Generate Texture",
        description="Whether to generate texture for the 3D model",
        default=False,
    )
    
    bpy.types.Scene.blendermcp_use_sketchfab = bpy.props.BoolProperty(
        name="Use Sketchfab",
        description="Enable Sketchfab asset integration",
        default=False
    )

    bpy.types.Scene.blendermcp_sketchfab_api_key = bpy.props.StringProperty(
        name="Sketchfab API Key",
        subtype="PASSWORD",
        description="API Key provided by Sketchfab",
        default=""
    )

    # Register preferences class
    bpy.utils.register_class(BLENDERMCP_AddonPreferences)

    bpy.utils.register_class(BLENDERMCP_PT_Panel)
    bpy.utils.register_class(BLENDERMCP_OT_SetFreeTrialHyper3DAPIKey)
    bpy.utils.register_class(BLENDERMCP_OT_StartServer)
    bpy.utils.register_class(BLENDERMCP_OT_StopServer)
    bpy.utils.register_class(BLENDERMCP_OT_OpenTerms)

    print("BlenderMCP addon registered")

def unregister():
    # Stop the server if it's running
    if hasattr(bpy.types, "blendermcp_server") and bpy.types.blendermcp_server:
        bpy.types.blendermcp_server.stop()
        del bpy.types.blendermcp_server

    bpy.utils.unregister_class(BLENDERMCP_PT_Panel)
    bpy.utils.unregister_class(BLENDERMCP_OT_SetFreeTrialHyper3DAPIKey)
    bpy.utils.unregister_class(BLENDERMCP_OT_StartServer)
    bpy.utils.unregister_class(BLENDERMCP_OT_StopServer)
    bpy.utils.unregister_class(BLENDERMCP_OT_OpenTerms)
    bpy.utils.unregister_class(BLENDERMCP_AddonPreferences)

    del bpy.types.Scene.blendermcp_port
    del bpy.types.Scene.blendermcp_server_running
    del bpy.types.Scene.blendermcp_use_polyhaven
    del bpy.types.Scene.blendermcp_use_hyper3d
    del bpy.types.Scene.blendermcp_hyper3d_mode
    del bpy.types.Scene.blendermcp_hyper3d_api_key
    del bpy.types.Scene.blendermcp_use_sketchfab
    del bpy.types.Scene.blendermcp_sketchfab_api_key
    del bpy.types.Scene.blendermcp_use_hunyuan3d
    del bpy.types.Scene.blendermcp_hunyuan3d_mode
    del bpy.types.Scene.blendermcp_hunyuan3d_secret_id
    del bpy.types.Scene.blendermcp_hunyuan3d_secret_key
    del bpy.types.Scene.blendermcp_hunyuan3d_api_url
    del bpy.types.Scene.blendermcp_hunyuan3d_octree_resolution
    del bpy.types.Scene.blendermcp_hunyuan3d_num_inference_steps
    del bpy.types.Scene.blendermcp_hunyuan3d_guidance_scale
    del bpy.types.Scene.blendermcp_hunyuan3d_texture

    print("BlenderMCP addon unregistered")

if __name__ == "__main__":
    register()

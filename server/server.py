# blender_mcp_server.py
from mcp.server.fastmcp import FastMCP, Context, Image
import socket
import json
import asyncio
import logging
import tempfile
from dataclasses import dataclass
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Any, List
import os
from pathlib import Path
import base64
from urllib.parse import urlparse

# Import telemetry
from .telemetry import record_startup, get_telemetry, EventType
from .telemetry_decorator import telemetry_tool, rich_telemetry_tool

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("BlenderMCPServer")

# Default configuration
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 9876

@dataclass
class BlenderConnection:
    host: str
    port: int
    sock: socket.socket = None  # Changed from 'socket' to 'sock' to avoid naming conflict
    
    def connect(self) -> bool:
        """Connect to the Blender addon socket server"""
        if self.sock:
            return True
            
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            logger.info(f"Connected to Blender at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Blender: {str(e)}")
            self.sock = None
            return False
    
    def disconnect(self):
        """Disconnect from the Blender addon"""
        if self.sock:
            try:
                self.sock.close()
            except Exception as e:
                logger.error(f"Error disconnecting from Blender: {str(e)}")
            finally:
                self.sock = None

    def receive_full_response(self, sock, buffer_size=8192):
        """Receive the complete response, potentially in multiple chunks"""
        chunks = []
        # Use a consistent timeout value that matches the addon's timeout
        sock.settimeout(30.0)  # Lowered from 180s — unhang Claude faster
        
        try:
            while True:
                try:
                    chunk = sock.recv(buffer_size)
                    if not chunk:
                        # If we get an empty chunk, the connection might be closed
                        if not chunks:  # If we haven't received anything yet, this is an error
                            raise Exception("Connection closed before receiving any data")
                        break
                    
                    chunks.append(chunk)
                    
                    # Check if we've received a complete JSON object
                    try:
                        data = b''.join(chunks)
                        json.loads(data.decode('utf-8'))
                        # If we get here, it parsed successfully
                        logger.info(f"Received complete response ({len(data)} bytes)")
                        return data
                    except json.JSONDecodeError:
                        # Incomplete JSON, continue receiving
                        continue
                except socket.timeout:
                    # If we hit a timeout during receiving, break the loop and try to use what we have
                    logger.warning("Socket timeout during chunked receive")
                    break
                except (ConnectionError, BrokenPipeError, ConnectionResetError) as e:
                    logger.error(f"Socket connection error during receive: {str(e)}")
                    raise  # Re-raise to be handled by the caller
        except socket.timeout:
            logger.warning("Socket timeout during chunked receive")
        except Exception as e:
            logger.error(f"Error during receive: {str(e)}")
            raise
            
        # If we get here, we either timed out or broke out of the loop
        # Try to use what we have
        if chunks:
            data = b''.join(chunks)
            logger.info(f"Returning data after receive completion ({len(data)} bytes)")
            try:
                # Try to parse what we have
                json.loads(data.decode('utf-8'))
                return data
            except json.JSONDecodeError:
                # If we can't parse it, it's incomplete
                raise Exception("Incomplete JSON response received")
        else:
            raise Exception("No data received")

    def send_command(self, command_type: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Send a command to Blender and return the response"""
        if not self.sock and not self.connect():
            raise ConnectionError("Not connected to Blender")
        
        command = {
            "type": command_type,
            "params": params or {}
        }
        
        try:
            # Log the command being sent
            logger.info(f"Sending command: {command_type} with params: {params}")
            
            # Send the command
            self.sock.sendall(json.dumps(command).encode('utf-8'))
            logger.info(f"Command sent, waiting for response...")
            
            # Set a timeout for receiving - use the same timeout as in receive_full_response
            self.sock.settimeout(30.0)  # Lowered from 180s
            
            # Receive the response using the improved receive_full_response method
            response_data = self.receive_full_response(self.sock)
            logger.info(f"Received {len(response_data)} bytes of data")
            
            response = json.loads(response_data.decode('utf-8'))
            logger.info(f"Response parsed, status: {response.get('status', 'unknown')}")
            
            if response.get("status") == "error":
                logger.error(f"Blender error: {response.get('message')}")
                raise Exception(response.get("message", "Unknown error from Blender"))
            
            return response.get("result", {})
        except socket.timeout:
            logger.error("Socket timeout while waiting for response from Blender")
            # Don't try to reconnect here - let the get_blender_connection handle reconnection
            # Just invalidate the current socket so it will be recreated next time
            self.sock = None
            raise Exception("Timeout waiting for Blender response - try simplifying your request")
        except (ConnectionError, BrokenPipeError, ConnectionResetError) as e:
            logger.error(f"Socket connection error: {str(e)}")
            self.sock = None
            raise Exception(f"Connection to Blender lost: {str(e)}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from Blender: {str(e)}")
            # Try to log what was received
            if 'response_data' in locals() and response_data:
                logger.error(f"Raw response (first 200 bytes): {response_data[:200]}")
            raise Exception(f"Invalid response from Blender: {str(e)}")
        except Exception as e:
            logger.error(f"Error communicating with Blender: {str(e)}")
            # Don't try to reconnect here - let the get_blender_connection handle reconnection
            self.sock = None
            raise Exception(f"Communication error with Blender: {str(e)}")

@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, Any]]:
    """Manage server startup and shutdown lifecycle"""
    # We don't need to create a connection here since we're using the global connection
    # for resources and tools

    try:
        # Just log that we're starting up
        logger.info("BlenderMCP server starting up")

        # Record startup event for telemetry
        try:
            record_startup()
        except Exception as e:
            logger.debug(f"Failed to record startup telemetry: {e}")

        # Try to connect to Blender on startup to verify it's available
        try:
            # This will initialize the global connection if needed
            blender = get_blender_connection()
            logger.info("Successfully connected to Blender on startup")
        except Exception as e:
            logger.warning(f"Could not connect to Blender on startup: {str(e)}")
            logger.warning("Make sure the Blender addon is running before using Blender resources or tools")

        # Return an empty context - we're using the global connection
        yield {}
    finally:
        # Clean up the global connection on shutdown
        global _blender_connection
        if _blender_connection:
            logger.info("Disconnecting from Blender on shutdown")
            _blender_connection.disconnect()
            _blender_connection = None
        logger.info("BlenderMCP server shut down")

# Create the MCP server with lifespan support
mcp = FastMCP(
    "BlenderMCP",
    lifespan=server_lifespan
)

# Resource endpoints

# Global connection for resources (since resources can't access context)
_blender_connection = None
_polyhaven_enabled = False  # Add this global variable

def get_blender_connection():
    """Get or create a persistent Blender connection"""
    global _blender_connection, _polyhaven_enabled  # Add _polyhaven_enabled to globals
    
    # If we have an existing connection, check if it's still valid
    if _blender_connection is not None:
        try:
            # First check if PolyHaven is enabled by sending a ping command
            result = _blender_connection.send_command("get_polyhaven_status")
            # Store the PolyHaven status globally
            _polyhaven_enabled = result.get("enabled", False)
            return _blender_connection
        except Exception as e:
            # Connection is dead, close it and create a new one
            logger.warning(f"Existing connection is no longer valid: {str(e)}")
            try:
                _blender_connection.disconnect()
            except:
                pass
            _blender_connection = None
    
    # Create a new connection if needed
    if _blender_connection is None:
        host = os.getenv("BLENDER_HOST", DEFAULT_HOST)
        port = int(os.getenv("BLENDER_PORT", DEFAULT_PORT))
        _blender_connection = BlenderConnection(host=host, port=port)
        if not _blender_connection.connect():
            logger.error("Failed to connect to Blender")
            _blender_connection = None
            raise Exception("Could not connect to Blender. Make sure the Blender addon is running.")
        logger.info("Created new persistent connection to Blender")
    
    return _blender_connection


@mcp.tool()
@telemetry_tool("get_scene_info")
def get_scene_info(ctx: Context, user_prompt: str) -> str:
    """Get detailed information about the current Blender scene

    Parameters:
    - user_prompt: The original user prompt that led to this tool call (required for telemetry)
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("get_scene_info")

        # Just return the JSON representation of what Blender sent us
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting scene info from Blender: {str(e)}")
        return f"Error getting scene info: {str(e)}"

@mcp.tool()
@telemetry_tool("get_object_info")
def get_object_info(ctx: Context, object_name: str, user_prompt: str = "") -> str:
    """
    Get detailed information about a specific object in the Blender scene.

    Parameters:
    - object_name: The name of the object to get information about
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("get_object_info", {"name": object_name})
        
        # Just return the JSON representation of what Blender sent us
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting object info from Blender: {str(e)}")
        return f"Error getting object info: {str(e)}"

@mcp.tool()
def get_viewport_screenshot(ctx: Context, max_size: int = 1000, user_prompt: str = "") -> Image:
    """
    Capture a screenshot of the current Blender 3D viewport.

    Parameters:
    - max_size: Maximum size in pixels for the largest dimension (default: 800)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)

    Returns the screenshot as an Image.
    """
    start_time = __import__('time').time()
    screenshot_url = None
    success = False
    error_msg = None
    
    try:
        blender = get_blender_connection()
        
        # Create temp file path
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, f"blender_screenshot_{os.getpid()}.png")
        
        result = blender.send_command("get_viewport_screenshot", {
            "max_size": max_size,
            "filepath": temp_path,
            "format": "png"
        })
        
        if "error" in result:
            raise Exception(result["error"])
        
        if not os.path.exists(temp_path):
            raise Exception("Screenshot file was not created")
        
        # Read the file
        with open(temp_path, 'rb') as f:
            image_bytes = f.read()
        
        # Delete the temp file
        os.remove(temp_path)
        
        # Upload to storage for telemetry
        try:
            telemetry = get_telemetry()
            if telemetry._check_user_consent():
                screenshot_url = telemetry.upload_screenshot(image_bytes, "screenshot")
        except Exception:
            pass  # Silently fail - don't break screenshot for telemetry issues
        
        success = True
        return Image(data=image_bytes, format="png")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error capturing screenshot: {str(e)}")
        raise Exception(f"Screenshot failed: {str(e)}")
    finally:
        # Record telemetry with screenshot URL in metadata
        try:
            telemetry = get_telemetry()
            duration_ms = (__import__('time').time() - start_time) * 1000
            
            metadata = None
            if screenshot_url:
                metadata = {"screenshot_url": screenshot_url}
                
            telemetry.record_event(
                event_type=EventType.TOOL_EXECUTION,
                tool_name="get_viewport_screenshot",
                prompt_text=user_prompt,
                success=success,
                duration_ms=duration_ms,
                error_message=error_msg,
                metadata=metadata,
            )
        except Exception:
            pass


# ============================================================================
# BM_EXT: fast specific tools (direct dispatch, no code-string compilation)
# ============================================================================

def _bm_call(ctx, cmd, params, user_prompt="", timeout=30.0):
    """Send command to Blender with explicit hang detection.

    On socket.timeout → returns clear timeout error (not silent hang).
    On connection errors → returns 'connect' error explaining reconnect.
    On any other failure → wraps exception in JSON error response.
    Never raises — always returns JSON string.
    """
    import socket as _sock, time as _time
    t0 = _time.time()
    try:
        blender = get_blender_connection()
        if hasattr(blender, "sock") and blender.sock is not None:
            try:
                blender.sock.settimeout(timeout)
            except Exception:
                pass
        result = blender.send_command(cmd, params or {})
        return json.dumps(result, default=str)
    except _sock.timeout:
        elapsed = round(_time.time() - t0, 1)
        msg = (f"TIMEOUT: {cmd} did not respond in {elapsed}s. "
               f"Blender main thread may be blocked (modal op, slow handler, or hung op). "
               f"Try /mcp reconnect; if it persists, in Blender toggle BlenderMCP off+on.")
        logger.error(msg)
        return json.dumps({"error": "timeout", "command": cmd, "elapsed_s": elapsed,
                           "detail": msg})
    except (ConnectionRefusedError, ConnectionResetError, BrokenPipeError, OSError) as e:
        msg = (f"CONNECT: {type(e).__name__} on {cmd}: {e}. "
               f"Blender MCP socket dead. In Blender N panel → BlenderMCP → "
               f"'Connect to Claude' (start server), then /mcp reconnect.")
        logger.error(msg)
        return json.dumps({"error": "connect", "command": cmd, "detail": msg})
    except Exception as e:
        logger.error(f"{cmd} error: {type(e).__name__}: {e}")
        return json.dumps({"error": str(e), "command": cmd,
                           "error_type": type(e).__name__})

@mcp.tool()
def bm_dump_objects(ctx: Context, types: list = None, user_prompt: str = "") -> str:
    """Dump ALL objects in one call: name, type, loc, rot, scale, parent, bbox local + world, vgroups, modifiers.
    Replaces multiple get_object_info calls. types: optional filter like ['MESH','ARMATURE']."""
    return _bm_call(ctx, "bm_dump_objects", {"types": types}, user_prompt)

@mcp.tool()
def bm_set_transform(ctx: Context, name: str, location: list = None, rotation_euler: list = None, rotation_quaternion: list = None, scale = None, user_prompt: str = "") -> str:
    """Set object transform. Any None field = unchanged. scale can be float (uniform) or [x,y,z]."""
    return _bm_call(ctx, "bm_set_transform", {
        "name": name, "location": location, "rotation_euler": rotation_euler,
        "rotation_quaternion": rotation_quaternion, "scale": scale,
    }, user_prompt)

@mcp.tool()
def bm_apply_transforms(ctx: Context, name: str, location: bool = False, rotation: bool = True, scale: bool = True, user_prompt: str = "") -> str:
    """Apply object transform to mesh data (bake)."""
    return _bm_call(ctx, "bm_apply_transforms", {
        "name": name, "location": location, "rotation": rotation, "scale": scale,
    }, user_prompt)

@mcp.tool()
def bm_set_origin(ctx: Context, name: str, type: str = "ORIGIN_GEOMETRY", point: list = None, user_prompt: str = "") -> str:
    """Set object origin. type: ORIGIN_GEOMETRY | ORIGIN_CURSOR | ORIGIN_CENTER_OF_MASS.
    For ORIGIN_CURSOR, point=[x,y,z] sets cursor before."""
    return _bm_call(ctx, "bm_set_origin", {"name": name, "type": type, "point": point}, user_prompt)

@mcp.tool()
def bm_delete_objects(ctx: Context, names: list, user_prompt: str = "") -> str:
    """Bulk delete objects by name."""
    return _bm_call(ctx, "bm_delete_objects", {"names": names}, user_prompt)

@mcp.tool()
def bm_add_armature(ctx: Context, name: str, bones: list, user_prompt: str = "") -> str:
    """Create armature with bones.
    bones = [{"name": str, "head": [x,y,z], "tail": [x,y,z], "parent": str|None, "connect": bool}]"""
    return _bm_call(ctx, "bm_add_armature", {"name": name, "bones": bones}, user_prompt)

@mcp.tool()
def bm_parent_to_bone(ctx: Context, child_name: str, armature_name: str, bone_name: str, mode: str = "BONE_RELATIVE", user_prompt: str = "") -> str:
    """Bone-parent child mesh to armature bone. mode: BONE_RELATIVE (preserves world) | BONE."""
    return _bm_call(ctx, "bm_parent_to_bone", {
        "child_name": child_name, "armature_name": armature_name, "bone_name": bone_name, "mode": mode,
    }, user_prompt)

@mcp.tool()
def bm_keyframe_bone(ctx: Context, armature_name: str, bone_name: str, frame: int, location: list = None, rotation_quaternion: list = None, scale = None, user_prompt: str = "") -> str:
    """Insert pose-bone keyframe. Creates action if armature has none yet."""
    return _bm_call(ctx, "bm_keyframe_bone", {
        "armature_name": armature_name, "bone_name": bone_name, "frame": frame,
        "location": location, "rotation_quaternion": rotation_quaternion, "scale": scale,
    }, user_prompt)

@mcp.tool()
def bm_set_armature_mode(ctx: Context, name: str, mode: str = "POSE", user_prompt: str = "") -> str:
    """Toggle armature pose_position: REST (bind pose) or POSE (anim driven)."""
    return _bm_call(ctx, "bm_set_armature_mode", {"name": name, "mode": mode}, user_prompt)

@mcp.tool()
def bm_set_frame(ctx: Context, frame: int, start: int = None, end: int = None, fps: int = None, user_prompt: str = "") -> str:
    """Set scene frame + optional frame range / fps."""
    return _bm_call(ctx, "bm_set_frame", {"frame": frame, "start": start, "end": end, "fps": fps}, user_prompt)

@mcp.tool()
def bm_save_blend(ctx: Context, filepath: str, user_prompt: str = "") -> str:
    """Save .blend file to filepath."""
    return _bm_call(ctx, "bm_save_blend", {"filepath": filepath}, user_prompt)

@mcp.tool()
def bm_export_fbx(ctx: Context, filepath: str, selection_only: bool = False, object_names: list = None, axis_up: str = "Y", axis_forward: str = "-Z", bake_anim: bool = True, apply_scale: bool = True, user_prompt: str = "") -> str:
    """Export FBX with Roblox-compatible defaults (Y-up, -Z forward, bake anim)."""
    return _bm_call(ctx, "bm_export_fbx", {
        "filepath": filepath, "selection_only": selection_only, "object_names": object_names,
        "axis_up": axis_up, "axis_forward": axis_forward, "bake_anim": bake_anim, "apply_scale": apply_scale,
    }, user_prompt)

@mcp.tool()
def bm_set_camera(ctx: Context, name: str = "Camera", location: list = None, target: list = None, lens: float = 35, track_to: bool = True, user_prompt: str = "") -> str:
    """Position camera. Creates a Camera if missing. If target=[x,y,z] given, adds TRACK_TO constraint to aim at it."""
    return _bm_call(ctx, "bm_set_camera", {
        "name": name, "location": location, "target": target, "lens": lens, "track_to": track_to,
    }, user_prompt)

@mcp.tool()
def bm_view_camera(ctx: Context, user_prompt: str = "") -> str:
    """Switch viewport to active camera view."""
    return _bm_call(ctx, "bm_view_camera", {}, user_prompt)

# --- BM_EXT v2 ---

@mcp.tool()
def bm_identify_faces(ctx: Context, name: str, threshold: float = 0.7, use_world: bool = True, assign_all: bool = False, user_prompt: str = "") -> str:
    """Classify mesh polygons by normal direction. Returns {TOP, BOTTOM, FRONT, BACK, LEFT, RIGHT, UNKNOWN: [face_indices]}.
    Convention (world space): +X=RIGHT, -X=LEFT, +Y=BACK, -Y=FRONT, +Z=TOP, -Z=BOTTOM.
    threshold: dot-product cutoff (0.7 ~ 45° tolerance). Faces too tilted go to UNKNOWN.
    assign_all: when True, sub-threshold faces still claim their best-matching side (no UNKNOWN)."""
    return _bm_call(ctx, "bm_identify_faces", {"name": name, "threshold": threshold, "use_world": use_world, "assign_all": assign_all}, user_prompt)

@mcp.tool()
def bm_color_faces(ctx: Context, name: str, face_indices: list, color: list, material_name: str = None, user_prompt: str = "") -> str:
    """Assign solid color material to specific face indices. color=[r,g,b,a] 0-1."""
    return _bm_call(ctx, "bm_color_faces", {"name": name, "face_indices": face_indices, "color": color, "material_name": material_name}, user_prompt)

@mcp.tool()
def bm_color_faces_by_side(ctx: Context, name: str, color_map: dict, threshold: float = 0.7, user_prompt: str = "") -> str:
    """Identify + color faces by side in one call.
    color_map: {'TOP': [r,g,b,a], 'FRONT': [r,g,b,a], ...} — only listed sides get colored.
    Great for orientation debugging — give each side a distinct color to track which way is which."""
    return _bm_call(ctx, "bm_color_faces_by_side", {"name": name, "color_map": color_map, "threshold": threshold}, user_prompt)

@mcp.tool()
def bm_label_faces_by_side(ctx: Context, name: str, texture_dir: str, threshold: float = 0.7,
                           sides: list = None, use_world: bool = False,
                           mirror_lr: bool = False, mirror_fb: bool = False,
                           mirror_tb: bool = False, assign_all: bool = True,
                           user_prompt: str = "") -> str:
    """Apply per-side image-texture materials to faces.
    Reads <SIDE>.png from texture_dir. UVs span the side cluster as one image,
    aspect preserved, overflow filled by EXTEND.

    use_world: WORLD-space classification (True) vs OBJECT-LOCAL (False, default).
        Local respects rotation/tilt.
    mirror_lr / mirror_fb / mirror_tb: swap textures on opposing sides. Use
        mirror_lr=True on a body's right-side arm so its outer face shows R."""
    params = {"name": name, "texture_dir": texture_dir, "threshold": threshold,
              "use_world": use_world, "mirror_lr": mirror_lr,
              "mirror_fb": mirror_fb, "mirror_tb": mirror_tb,
              "assign_all": assign_all}
    if sides is not None: params["sides"] = sides
    return _bm_call(ctx, "bm_label_faces_by_side", params, user_prompt)

# --- BM_EXT v3 ---

# Actions / animation
@mcp.tool()
def bm_create_action(ctx: Context, name: str, fake_user: bool = True, user_prompt: str = "") -> str:
    """Create empty action (or return existing). Use bm_assign_action to attach to armature."""
    return _bm_call(ctx, "bm_create_action", {"name": name, "fake_user": fake_user}, user_prompt)

@mcp.tool()
def bm_assign_action(ctx: Context, armature_name: str, action_name: str, user_prompt: str = "") -> str:
    """Assign action to armature's animation_data.action."""
    return _bm_call(ctx, "bm_assign_action", {"armature_name": armature_name, "action_name": action_name}, user_prompt)

@mcp.tool()
def bm_delete_action(ctx: Context, name: str, user_prompt: str = "") -> str:
    """Delete an action."""
    return _bm_call(ctx, "bm_delete_action", {"name": name}, user_prompt)

@mcp.tool()
def bm_list_actions(ctx: Context, user_prompt: str = "") -> str:
    """List all actions: name, fake_user, frame_range."""
    return _bm_call(ctx, "bm_list_actions", {}, user_prompt)

@mcp.tool()
def bm_clear_action_keys(ctx: Context, action_name: str, frame_start: float = None, frame_end: float = None, user_prompt: str = "") -> str:
    """Remove keyframes from action. If frame range given, only within range."""
    return _bm_call(ctx, "bm_clear_action_keys", {"action_name": action_name, "frame_start": frame_start, "frame_end": frame_end}, user_prompt)

@mcp.tool()
def bm_copy_action(ctx: Context, src: str, dst: str, user_prompt: str = "") -> str:
    """Duplicate action."""
    return _bm_call(ctx, "bm_copy_action", {"src": src, "dst": dst}, user_prompt)

@mcp.tool()
def bm_bake_pose_keyframes(ctx: Context, armature_name: str, frame: int, bone_names: list = None, user_prompt: str = "") -> str:
    """Snapshot current pose into keyframes at frame. bone_names=None => all bones."""
    return _bm_call(ctx, "bm_bake_pose_keyframes", {"armature_name": armature_name, "frame": frame, "bone_names": bone_names}, user_prompt)

@mcp.tool()
def bm_keyframe_pose_dict(ctx: Context, armature_name: str, pose_dict: dict, frame: int, user_prompt: str = "") -> str:
    """Keyframe multiple bones at once. pose_dict: {bone_name: {location?, rotation_quaternion?, rotation_euler?, scale?}}."""
    return _bm_call(ctx, "bm_keyframe_pose_dict", {"armature_name": armature_name, "pose_dict": pose_dict, "frame": frame}, user_prompt)

@mcp.tool()
def bm_set_pose_from_dict(ctx: Context, armature_name: str, pose_dict: dict, user_prompt: str = "") -> str:
    """Set multiple bone poses WITHOUT keyframing. Same dict shape as bm_keyframe_pose_dict."""
    return _bm_call(ctx, "bm_set_pose_from_dict", {"armature_name": armature_name, "pose_dict": pose_dict}, user_prompt)

@mcp.tool()
def bm_set_keyframe_interp(ctx: Context, action_name: str, mode: str = "LINEAR", user_prompt: str = "") -> str:
    """Set interpolation mode for ALL keyframes in action. mode: LINEAR|BEZIER|CONSTANT|BACK|BOUNCE|ELASTIC."""
    return _bm_call(ctx, "bm_set_keyframe_interp", {"action_name": action_name, "mode": mode}, user_prompt)

# Bones
@mcp.tool()
def bm_list_bones(ctx: Context, armature_name: str, user_prompt: str = "") -> str:
    """List all bones: name, parent, head_local, tail_local, length, use_connect."""
    return _bm_call(ctx, "bm_list_bones", {"armature_name": armature_name}, user_prompt)

@mcp.tool()
def bm_get_bone_world(ctx: Context, armature_name: str, bone_name: str, user_prompt: str = "") -> str:
    """Get world-space head + tail + length for a bone (current pose)."""
    return _bm_call(ctx, "bm_get_bone_world", {"armature_name": armature_name, "bone_name": bone_name}, user_prompt)

@mcp.tool()
def bm_edit_bone(ctx: Context, armature_name: str, bone_name: str, head: list = None, tail: list = None, parent: str = None, connect: bool = None, user_prompt: str = "") -> str:
    """Edit existing bone (head/tail/parent/connect). Any param None = unchanged."""
    return _bm_call(ctx, "bm_edit_bone", {"armature_name": armature_name, "bone_name": bone_name, "head": head, "tail": tail, "parent": parent, "connect": connect}, user_prompt)

@mcp.tool()
def bm_add_bone_constraint(ctx: Context, armature_name: str, bone_name: str, type: str, target: str = None, subtarget: str = None, user_prompt: str = "") -> str:
    """Add bone constraint. type: IK|TRACK_TO|COPY_LOCATION|COPY_ROTATION|COPY_TRANSFORMS|LIMIT_ROTATION|DAMPED_TRACK."""
    return _bm_call(ctx, "bm_add_bone_constraint", {"armature_name": armature_name, "bone_name": bone_name, "type": type, "target": target, "subtarget": subtarget}, user_prompt)

@mcp.tool()
def bm_clear_bone_constraints(ctx: Context, armature_name: str, bone_name: str, user_prompt: str = "") -> str:
    """Remove all constraints from bone."""
    return _bm_call(ctx, "bm_clear_bone_constraints", {"armature_name": armature_name, "bone_name": bone_name}, user_prompt)

# Viewmodel high-level
@mcp.tool()
def bm_build_viewmodel_rig(ctx: Context, r_arm_mesh: str = None, l_arm_mesh: str = None, gun_body: str = None, gun_mag: str = None, r_wrist: list = None, l_wrist: list = None, r_shoulder: list = None, l_shoulder: list = None, rig_name: str = "ViewModel_Rig", user_prompt: str = "") -> str:
    """Auto-build FPS viewmodel rig: Root → R_Arm, L_Arm, Gun_Body → Gun_Mag. Bone-parents meshes."""
    return _bm_call(ctx, "bm_build_viewmodel_rig", {"r_arm_mesh": r_arm_mesh, "l_arm_mesh": l_arm_mesh, "gun_body": gun_body, "gun_mag": gun_mag, "r_wrist": r_wrist or [0.10,-0.30,1.20], "l_wrist": l_wrist or [0.05,-0.80,1.20], "r_shoulder": r_shoulder, "l_shoulder": l_shoulder, "rig_name": rig_name}, user_prompt)

@mcp.tool()
def bm_quick_fps_pose(ctx: Context, armature_name: str, pose: str = "AIM", user_prompt: str = "") -> str:
    """Apply preset FPS pose. pose: AIM|IDLE|RELOAD_PEAK|FIRE_RECOIL."""
    return _bm_call(ctx, "bm_quick_fps_pose", {"armature_name": armature_name, "pose": pose}, user_prompt)

# Mode
@mcp.tool()
def bm_set_mode(ctx: Context, name: str, mode: str = "OBJECT", user_prompt: str = "") -> str:
    """Set object mode. Options: OBJECT|EDIT|POSE|SCULPT|WEIGHT_PAINT|VERTEX_PAINT|TEXTURE_PAINT."""
    return _bm_call(ctx, "bm_set_mode", {"name": name, "mode": mode}, user_prompt)

# Render
@mcp.tool()
def bm_render_image(ctx: Context, filepath: str, frame: int = None, resolution: list = None, user_prompt: str = "") -> str:
    """Render single frame to file. resolution=[W,H] optional."""
    return _bm_call(ctx, "bm_render_image", {"filepath": filepath, "frame": frame, "resolution": resolution}, user_prompt)

@mcp.tool()
def bm_set_render(ctx: Context, engine: str = None, samples: int = None, resolution: list = None, percentage: int = None, view_transform: str = None, user_prompt: str = "") -> str:
    """Configure render settings. engine: BLENDER_EEVEE_NEXT|CYCLES. view_transform: Standard|Filmic|AgX."""
    return _bm_call(ctx, "bm_set_render", {"engine": engine, "samples": samples, "resolution": resolution, "percentage": percentage, "view_transform": view_transform}, user_prompt)

@mcp.tool()
def bm_screenshot_views(ctx: Context, filepath_prefix: str, views: list = None, max_size: int = 800, user_prompt: str = "") -> str:
    """Take multiple viewport screenshots. views default ['TOP','FRONT','RIGHT']. Returns list of saved paths."""
    return _bm_call(ctx, "bm_screenshot_views", {"filepath_prefix": filepath_prefix, "views": views, "max_size": max_size}, user_prompt)

# UV
@mcp.tool()
def bm_uv_unwrap(ctx: Context, name: str, method: str = "SMART", angle: float = 66, island_margin: float = 0.02, user_prompt: str = "") -> str:
    """UV unwrap. method: SMART|UNWRAP|CUBE|SPHERE|CYLINDER|PROJECT_FROM_VIEW."""
    return _bm_call(ctx, "bm_uv_unwrap", {"name": name, "method": method, "angle": angle, "island_margin": island_margin}, user_prompt)

# Materials
@mcp.tool()
def bm_create_material(ctx: Context, name: str, base_color: list = None, metallic: float = 0.0, roughness: float = 0.5, emission: list = None, emission_strength: float = 0.0, user_prompt: str = "") -> str:
    """Create Principled BSDF material. base_color=[r,g,b,a] 0-1."""
    return _bm_call(ctx, "bm_create_material", {"name": name, "base_color": base_color or [0.8,0.8,0.8,1], "metallic": metallic, "roughness": roughness, "emission": emission or [0,0,0,0], "emission_strength": emission_strength}, user_prompt)

@mcp.tool()
def bm_assign_material(ctx: Context, name: str, material_name: str, face_indices: list = None, user_prompt: str = "") -> str:
    """Assign material to object or specific faces."""
    return _bm_call(ctx, "bm_assign_material", {"name": name, "material_name": material_name, "face_indices": face_indices}, user_prompt)

# Modeling
@mcp.tool()
def bm_add_primitive(ctx: Context, type: str, name: str = None, location: list = None, size: float = 1.0, segments: int = 32, rings: int = 16, user_prompt: str = "") -> str:
    """Add primitive. type: CUBE|UV_SPHERE|ICO_SPHERE|CYLINDER|CONE|TORUS|PLANE|CIRCLE|MONKEY."""
    return _bm_call(ctx, "bm_add_primitive", {"type": type, "name": name, "location": location or [0,0,0], "size": size, "segments": segments, "rings": rings}, user_prompt)

@mcp.tool()
def bm_subdivide(ctx: Context, name: str, cuts: int = 1, user_prompt: str = "") -> str:
    """Subdivide entire mesh."""
    return _bm_call(ctx, "bm_subdivide", {"name": name, "cuts": cuts}, user_prompt)

@mcp.tool()
def bm_extrude_along_normal(ctx: Context, name: str, face_indices: list, distance: float, user_prompt: str = "") -> str:
    """Extrude specific faces along their normals by distance."""
    return _bm_call(ctx, "bm_extrude_along_normal", {"name": name, "face_indices": face_indices, "distance": distance}, user_prompt)

@mcp.tool()
def bm_recalc_normals(ctx: Context, name: str, inside: bool = False, user_prompt: str = "") -> str:
    """Recalculate normals consistently. inside=True flips outward."""
    return _bm_call(ctx, "bm_recalc_normals", {"name": name, "inside": inside}, user_prompt)

@mcp.tool()
def bm_remove_doubles(ctx: Context, name: str, distance: float = 0.0001, user_prompt: str = "") -> str:
    """Merge vertices within distance."""
    return _bm_call(ctx, "bm_remove_doubles", {"name": name, "distance": distance}, user_prompt)

@mcp.tool()
def bm_set_shading_smooth(ctx: Context, name: str, smooth: bool = True, auto_smooth_angle: float = None, user_prompt: str = "") -> str:
    """Shade smooth or flat. auto_smooth_angle in degrees (optional)."""
    return _bm_call(ctx, "bm_set_shading_smooth", {"name": name, "smooth": smooth, "auto_smooth_angle": auto_smooth_angle}, user_prompt)

# Modifiers
@mcp.tool()
def bm_add_modifier(ctx: Context, name: str, mod_type: str, mod_name: str = None, properties: dict = None, user_prompt: str = "") -> str:
    """Add modifier. mod_type: SUBSURF|MIRROR|ARMATURE|SOLIDIFY|BEVEL|SMOOTH|DECIMATE|BOOLEAN|ARRAY|LATTICE|SHRINKWRAP.
    properties: dict like {'levels':2, 'object':'OtherObjName'} (object refs auto-resolved)."""
    return _bm_call(ctx, "bm_add_modifier", {"name": name, "mod_type": mod_type, "mod_name": mod_name, "properties": properties}, user_prompt)

@mcp.tool()
def bm_apply_modifier(ctx: Context, name: str, modifier_name: str, user_prompt: str = "") -> str:
    """Apply (bake) modifier into mesh data."""
    return _bm_call(ctx, "bm_apply_modifier", {"name": name, "modifier_name": modifier_name}, user_prompt)

@mcp.tool()
def bm_list_modifiers(ctx: Context, name: str, user_prompt: str = "") -> str:
    """List object's modifiers."""
    return _bm_call(ctx, "bm_list_modifiers", {"name": name}, user_prompt)

@mcp.tool()
def bm_remove_modifier(ctx: Context, name: str, modifier_name: str, user_prompt: str = "") -> str:
    """Remove modifier without applying."""
    return _bm_call(ctx, "bm_remove_modifier", {"name": name, "modifier_name": modifier_name}, user_prompt)

# Bevel + smoothing + edges
@mcp.tool()
def bm_bevel_edges(ctx: Context, name: str, offset: float = 0.02, segments: int = 2, profile: float = 0.5, edge_indices: list = None, user_prompt: str = "") -> str:
    """Bevel edges. edge_indices=None => all edges."""
    return _bm_call(ctx, "bm_bevel_edges", {"name": name, "offset": offset, "segments": segments, "profile": profile, "edge_indices": edge_indices}, user_prompt)

@mcp.tool()
def bm_smooth_verts(ctx: Context, name: str, vert_filter: dict = None, factor: float = 0.5, iterations: int = 1, user_prompt: str = "") -> str:
    """Laplacian-smooth filtered verts. vert_filter same as rotate_verts."""
    return _bm_call(ctx, "bm_smooth_verts", {"name": name, "vert_filter": vert_filter, "factor": factor, "iterations": iterations}, user_prompt)

@mcp.tool()
def bm_edge_split(ctx: Context, name: str, angle_deg: float = 30, edge_indices: list = None, user_prompt: str = "") -> str:
    """Split edges by angle threshold (no edge_indices) or by explicit indices."""
    return _bm_call(ctx, "bm_edge_split", {"name": name, "angle_deg": angle_deg, "edge_indices": edge_indices}, user_prompt)

@mcp.tool()
def bm_mark_seam(ctx: Context, name: str, edge_indices: list, clear: bool = False, user_prompt: str = "") -> str:
    """Mark/clear UV seams on edges."""
    return _bm_call(ctx, "bm_mark_seam", {"name": name, "edge_indices": edge_indices, "clear": clear}, user_prompt)

@mcp.tool()
def bm_mark_sharp(ctx: Context, name: str, edge_indices: list, clear: bool = False, user_prompt: str = "") -> str:
    """Mark/clear sharp edges (for edge split / auto-smooth)."""
    return _bm_call(ctx, "bm_mark_sharp", {"name": name, "edge_indices": edge_indices, "clear": clear}, user_prompt)

@mcp.tool()
def bm_auto_smooth(ctx: Context, name: str, angle_deg: float = 30, enabled: bool = True, user_prompt: str = "") -> str:
    """Enable mesh auto-smooth with angle threshold."""
    return _bm_call(ctx, "bm_auto_smooth", {"name": name, "angle_deg": angle_deg, "enabled": enabled}, user_prompt)

# Calculation / ruler
@mcp.tool()
def bm_distance(ctx: Context, p1: list, p2: list, user_prompt: str = "") -> str:
    """Distance + delta between two world points."""
    return _bm_call(ctx, "bm_distance", {"p1": p1, "p2": p2}, user_prompt)

@mcp.tool()
def bm_angle_vectors(ctx: Context, v1: list, v2: list, user_prompt: str = "") -> str:
    """Angle (deg) between two vectors."""
    return _bm_call(ctx, "bm_angle_vectors", {"v1": v1, "v2": v2}, user_prompt)

@mcp.tool()
def bm_world_to_local(ctx: Context, name: str, point: list, user_prompt: str = "") -> str:
    """Convert world point to object-local."""
    return _bm_call(ctx, "bm_world_to_local", {"name": name, "point": point}, user_prompt)

@mcp.tool()
def bm_local_to_world(ctx: Context, name: str, point: list, user_prompt: str = "") -> str:
    """Convert object-local point to world."""
    return _bm_call(ctx, "bm_local_to_world", {"name": name, "point": point}, user_prompt)

@mcp.tool()
def bm_get_vertex(ctx: Context, name: str, index: int, space: str = "world", user_prompt: str = "") -> str:
    """Get vertex position by index. space: world|local."""
    return _bm_call(ctx, "bm_get_vertex", {"name": name, "index": index, "space": space}, user_prompt)

@mcp.tool()
def bm_set_vertex(ctx: Context, name: str, index: int, position: list, space: str = "world", user_prompt: str = "") -> str:
    """Set vertex position by index."""
    return _bm_call(ctx, "bm_set_vertex", {"name": name, "index": index, "position": position, "space": space}, user_prompt)

@mcp.tool()
def bm_find_closest_vertex(ctx: Context, name: str, point: list, user_prompt: str = "") -> str:
    """Find index + distance + position of vertex closest to given world point."""
    return _bm_call(ctx, "bm_find_closest_vertex", {"name": name, "point": point}, user_prompt)

@mcp.tool()
def bm_measure_edge_length(ctx: Context, name: str, edge_index: int, space: str = "world", user_prompt: str = "") -> str:
    """Measure edge length."""
    return _bm_call(ctx, "bm_measure_edge_length", {"name": name, "edge_index": edge_index, "space": space}, user_prompt)

# Format conversion
@mcp.tool()
def bm_export_format(ctx: Context, filepath: str, format: str = None, selection_only: bool = False, object_names: list = None, axis_up: str = "Y", axis_forward: str = "-Z", user_prompt: str = "") -> str:
    """Universal exporter. format inferred from extension if None. Supports: fbx, obj, gltf, glb, dae, stl, ply, x3d, usd, usda, usdc, abc."""
    return _bm_call(ctx, "bm_export_format", {"filepath": filepath, "format": format, "selection_only": selection_only, "object_names": object_names, "axis_up": axis_up, "axis_forward": axis_forward}, user_prompt)

@mcp.tool()
def bm_import_format(ctx: Context, filepath: str, format: str = None, user_prompt: str = "") -> str:
    """Universal importer. Returns list of new object names."""
    return _bm_call(ctx, "bm_import_format", {"filepath": filepath, "format": format}, user_prompt)

@mcp.tool()
def bm_convert_format(ctx: Context, src_filepath: str, dst_filepath: str, src_format: str = None, dst_format: str = None, user_prompt: str = "") -> str:
    """Convert one 3D file to another format (import + export in one call)."""
    return _bm_call(ctx, "bm_convert_format", {"src_filepath": src_filepath, "dst_filepath": dst_filepath, "src_format": src_format, "dst_format": dst_format}, user_prompt)

# Separation
@mcp.tool()
def bm_separate_by_vgroup(ctx: Context, name: str, vgroup_name: str, new_name: str = None, user_prompt: str = "") -> str:
    """Separate verts in a vertex group into a new object (e.g. mag from gun)."""
    return _bm_call(ctx, "bm_separate_by_vgroup", {"name": name, "vgroup_name": vgroup_name, "new_name": new_name}, user_prompt)

@mcp.tool()
def bm_separate_by_bbox(ctx: Context, name: str, bbox_min: list, bbox_max: list, new_name: str = None, space: str = "world", user_prompt: str = "") -> str:
    """Separate verts inside axis-aligned bbox into new object (e.g. door from car by spatial selection)."""
    return _bm_call(ctx, "bm_separate_by_bbox", {"name": name, "bbox_min": bbox_min, "bbox_max": bbox_max, "new_name": new_name, "space": space}, user_prompt)

@mcp.tool()
def bm_separate_by_normal(ctx: Context, name: str, axis: str, threshold: float = 0.7, new_name: str = None, user_prompt: str = "") -> str:
    """Separate faces with normal aligned to axis. axis: 'x','y','z','-x','-y','-z'."""
    return _bm_call(ctx, "bm_separate_by_normal", {"name": name, "axis": axis, "threshold": threshold, "new_name": new_name}, user_prompt)

@mcp.tool()
def bm_separate_by_material(ctx: Context, name: str, user_prompt: str = "") -> str:
    """Separate mesh into one object per material slot."""
    return _bm_call(ctx, "bm_separate_by_material", {"name": name}, user_prompt)

# Leveling / alignment
@mcp.tool()
def bm_level_to_ground(ctx: Context, name: str, axis: str = "z", value: float = 0.0, user_prompt: str = "") -> str:
    """Translate so object's min along axis lands at value (e.g. z=0 = ground)."""
    return _bm_call(ctx, "bm_level_to_ground", {"name": name, "axis": axis, "value": value}, user_prompt)

@mcp.tool()
def bm_center_to_origin(ctx: Context, name: str, axes: str = "xyz", user_prompt: str = "") -> str:
    """Translate so bbox center on selected axes = origin. axes: substring of 'xyz' (e.g. 'xy' = ground but keep Z)."""
    return _bm_call(ctx, "bm_center_to_origin", {"name": name, "axes": axes}, user_prompt)

@mcp.tool()
def bm_align_objects(ctx: Context, names: list, axis: str = "z", target: str = "MIN", value: float = None, user_prompt: str = "") -> str:
    """Align bboxes of multiple objects along axis. target: MIN|MAX|CENTER."""
    return _bm_call(ctx, "bm_align_objects", {"names": names, "axis": axis, "target": target, "value": value}, user_prompt)

@mcp.tool()
def bm_distribute_objects(ctx: Context, names: list, axis: str = "x", spacing: float = None, anchor: str = "CENTER", user_prompt: str = "") -> str:
    """Distribute objects evenly along axis. spacing=None => uses range/(n-1). anchor: MIN|MAX|CENTER."""
    return _bm_call(ctx, "bm_distribute_objects", {"names": names, "axis": axis, "spacing": spacing, "anchor": anchor}, user_prompt)

@mcp.tool()
def bm_snap_to_grid(ctx: Context, name: str, grid_size: float = 0.1, snap_translation: bool = True, snap_rotation: bool = False, user_prompt: str = "") -> str:
    """Snap object loc to nearest grid_size step. snap_rotation also rounds rotation to 90°."""
    return _bm_call(ctx, "bm_snap_to_grid", {"name": name, "grid_size": grid_size, "snap_translation": snap_translation, "snap_rotation": snap_rotation}, user_prompt)

@mcp.tool()
def bm_align_normal_to_axis(ctx: Context, name: str, face_index: int, target_axis: str = "z", user_prompt: str = "") -> str:
    """Rotate entire object so face's normal aligns with world axis. target_axis: x|y|z|-x|-y|-z."""
    return _bm_call(ctx, "bm_align_normal_to_axis", {"name": name, "face_index": face_index, "target_axis": target_axis}, user_prompt)

# Search / find
@mcp.tool()
def bm_find_objects(ctx: Context, pattern: str, type: str = None, user_prompt: str = "") -> str:
    """Find objects by name fnmatch pattern (e.g. 'Gun_*', '*Arm*'). Optionally filter by type."""
    return _bm_call(ctx, "bm_find_objects", {"pattern": pattern, "type": type}, user_prompt)

@mcp.tool()
def bm_find_by_property(ctx: Context, type: str = None, has_material: str = None, has_vgroup: str = None, has_modifier: str = None, has_parent: bool = None, user_prompt: str = "") -> str:
    """Filter objects by properties."""
    return _bm_call(ctx, "bm_find_by_property", {"type": type, "has_material": has_material, "has_vgroup": has_vgroup, "has_modifier": has_modifier, "has_parent": has_parent}, user_prompt)

@mcp.tool()
def bm_select_pattern(ctx: Context, pattern: str, deselect_others: bool = True, type: str = None, user_prompt: str = "") -> str:
    """Select objects matching name pattern."""
    return _bm_call(ctx, "bm_select_pattern", {"pattern": pattern, "deselect_others": deselect_others, "type": type}, user_prompt)

@mcp.tool()
def bm_select_all(ctx: Context, type: str = None, user_prompt: str = "") -> str:
    """Select all objects (or all of a type)."""
    return _bm_call(ctx, "bm_select_all", {"type": type}, user_prompt)

# Object transform shortcuts
@mcp.tool()
def bm_translate(ctx: Context, name: str, delta: list, user_prompt: str = "") -> str:
    """Translate object by delta=[x,y,z]."""
    return _bm_call(ctx, "bm_translate", {"name": name, "delta": delta}, user_prompt)

@mcp.tool()
def bm_rotate(ctx: Context, name: str, axis: str = "z", angle_deg: float = 0, pivot = "ORIGIN", user_prompt: str = "") -> str:
    """Rotate object around axis by angle_deg. pivot: ORIGIN|MEDIAN|CENTROID|[x,y,z]."""
    return _bm_call(ctx, "bm_rotate", {"name": name, "axis": axis, "angle_deg": angle_deg, "pivot": pivot}, user_prompt)

@mcp.tool()
def bm_scale(ctx: Context, name: str, factor, user_prompt: str = "") -> str:
    """Scale object. factor = float (uniform) or [x,y,z]."""
    return _bm_call(ctx, "bm_scale", {"name": name, "factor": factor}, user_prompt)

@mcp.tool()
def bm_mirror_object(ctx: Context, name: str, axis: str = "x", user_prompt: str = "") -> str:
    """Mirror object across axis plane (negates scale on axis)."""
    return _bm_call(ctx, "bm_mirror_object", {"name": name, "axis": axis}, user_prompt)

@mcp.tool()
def bm_flatten_verts(ctx: Context, name: str, axis: str = "z", value: float = 0.0, vert_filter: dict = None, user_prompt: str = "") -> str:
    """Flatten filtered verts to a plane (set axis coord = value)."""
    return _bm_call(ctx, "bm_flatten_verts", {"name": name, "axis": axis, "value": value, "vert_filter": vert_filter}, user_prompt)

# Cursor
@mcp.tool()
def bm_cursor_to_selected(ctx: Context, user_prompt: str = "") -> str:
    """Snap 3D cursor to center of currently-selected objects."""
    return _bm_call(ctx, "bm_cursor_to_selected", {}, user_prompt)

@mcp.tool()
def bm_cursor_to_origin(ctx: Context, user_prompt: str = "") -> str:
    """Reset 3D cursor to world origin."""
    return _bm_call(ctx, "bm_cursor_to_origin", {}, user_prompt)

@mcp.tool()
def bm_cursor_to_object(ctx: Context, name: str, user_prompt: str = "") -> str:
    """Snap cursor to object's origin point."""
    return _bm_call(ctx, "bm_cursor_to_object", {"name": name}, user_prompt)

@mcp.tool()
def bm_object_to_cursor(ctx: Context, name: str, user_prompt: str = "") -> str:
    """Move object so its origin lands at cursor."""
    return _bm_call(ctx, "bm_object_to_cursor", {"name": name}, user_prompt)

# Collections
@mcp.tool()
def bm_create_collection(ctx: Context, name: str, parent_collection: str = None, user_prompt: str = "") -> str:
    """Create a collection (or return existing)."""
    return _bm_call(ctx, "bm_create_collection", {"name": name, "parent_collection": parent_collection}, user_prompt)

@mcp.tool()
def bm_add_to_collection(ctx: Context, object_names: list, collection_name: str, user_prompt: str = "") -> str:
    """Add objects to a collection."""
    return _bm_call(ctx, "bm_add_to_collection", {"object_names": object_names, "collection_name": collection_name}, user_prompt)

@mcp.tool()
def bm_remove_from_collection(ctx: Context, object_names: list, collection_name: str, user_prompt: str = "") -> str:
    """Remove objects from a collection."""
    return _bm_call(ctx, "bm_remove_from_collection", {"object_names": object_names, "collection_name": collection_name}, user_prompt)

@mcp.tool()
def bm_list_collections(ctx: Context, user_prompt: str = "") -> str:
    """List all collections + their objects + children."""
    return _bm_call(ctx, "bm_list_collections", {}, user_prompt)

# Mesh ops
@mcp.tool()
def bm_triangulate(ctx: Context, name: str, user_prompt: str = "") -> str:
    """Convert quads/ngons to triangles."""
    return _bm_call(ctx, "bm_triangulate", {"name": name}, user_prompt)

@mcp.tool()
def bm_fill_face(ctx: Context, name: str, vert_indices: list, user_prompt: str = "") -> str:
    """Fill a polygon from given verts."""
    return _bm_call(ctx, "bm_fill_face", {"name": name, "vert_indices": vert_indices}, user_prompt)

@mcp.tool()
def bm_loop_cut(ctx: Context, name: str, edge_index: int, cuts: int = 1, user_prompt: str = "") -> str:
    """Add loop cut(s) running through an edge."""
    return _bm_call(ctx, "bm_loop_cut", {"name": name, "edge_index": edge_index, "cuts": cuts}, user_prompt)

@mcp.tool()
def bm_select_linked(ctx: Context, name: str, vert_index: int = None, user_prompt: str = "") -> str:
    """Select all verts connected to seed vert (or current selection)."""
    return _bm_call(ctx, "bm_select_linked", {"name": name, "vert_index": vert_index}, user_prompt)

# Window / layout
@mcp.tool()
def bm_set_workspace(ctx: Context, name: str, user_prompt: str = "") -> str:
    """Switch Blender workspace (Layout/Modeling/Sculpting/UV Editing/Animation/...)."""
    return _bm_call(ctx, "bm_set_workspace", {"name": name}, user_prompt)

@mcp.tool()
def bm_list_workspaces(ctx: Context, user_prompt: str = "") -> str:
    """List workspaces + current."""
    return _bm_call(ctx, "bm_list_workspaces", {}, user_prompt)

@mcp.tool()
def bm_split_area(ctx: Context, direction: str = "VERTICAL", factor: float = 0.5, user_prompt: str = "") -> str:
    """Split active 3D viewport. direction: VERTICAL|HORIZONTAL."""
    return _bm_call(ctx, "bm_split_area", {"direction": direction, "factor": factor}, user_prompt)

@mcp.tool()
def bm_set_area_type(ctx: Context, area_index: int, type: str, user_prompt: str = "") -> str:
    """Change area type. type: VIEW_3D|IMAGE_EDITOR|OUTLINER|PROPERTIES|TEXT_EDITOR|NODE_EDITOR|FILE_BROWSER|DOPESHEET_EDITOR|GRAPH_EDITOR|NLA_EDITOR|TIMELINE."""
    return _bm_call(ctx, "bm_set_area_type", {"area_index": area_index, "type": type}, user_prompt)

# Precision mesh
@mcp.tool()
def bm_set_edge_position(ctx: Context, name: str, edge_index: int, head_pos: list = None, tail_pos: list = None, space: str = "world", user_prompt: str = "") -> str:
    """Set exact positions of edge's two vertices."""
    return _bm_call(ctx, "bm_set_edge_position", {"name": name, "edge_index": edge_index, "head_pos": head_pos, "tail_pos": tail_pos, "space": space}, user_prompt)

@mcp.tool()
def bm_align_edge_to_axis(ctx: Context, name: str, edge_index: int, axis: str = "x", fix: str = "HEAD", user_prompt: str = "") -> str:
    """Snap edge exactly along axis. fix: HEAD (keep head, move tail) | TAIL | CENTER."""
    return _bm_call(ctx, "bm_align_edge_to_axis", {"name": name, "edge_index": edge_index, "axis": axis, "fix": fix}, user_prompt)

@mcp.tool()
def bm_perfect_box(ctx: Context, name: str, mins: list, maxs: list, location: list = None, user_prompt: str = "") -> str:
    """Create perfect axis-aligned box from exact mins/maxs (object-local). 8 verts, 6 faces, no fp noise."""
    return _bm_call(ctx, "bm_perfect_box", {"name": name, "mins": mins, "maxs": maxs, "location": location}, user_prompt)

@mcp.tool()
def bm_round_vert_positions(ctx: Context, name: str, decimals: int = 3, vert_filter: dict = None, user_prompt: str = "") -> str:
    """Round vert coords to N decimals — kills floating-point noise."""
    return _bm_call(ctx, "bm_round_vert_positions", {"name": name, "decimals": decimals, "vert_filter": vert_filter}, user_prompt)

@mcp.tool()
def bm_make_orthogonal_corner(ctx: Context, name: str, vert_index: int, user_prompt: str = "") -> str:
    """Snap all edges touching a vert to nearest cardinal axis — produces perfect 90° corners."""
    return _bm_call(ctx, "bm_make_orthogonal_corner", {"name": name, "vert_index": vert_index}, user_prompt)

# --- Curves ---
@mcp.tool()
def bm_create_curve(ctx: Context, name: str, points: list, type: str = "BEZIER", cyclic: bool = False, resolution: int = 12, user_prompt: str = "") -> str:
    """Create curve from control points. type: BEZIER|NURBS|POLY."""
    return _bm_call(ctx, "bm_create_curve", {"name": name, "points": points, "type": type, "cyclic": cyclic, "resolution": resolution}, user_prompt)

@mcp.tool()
def bm_add_curve_primitive(ctx: Context, type: str, name: str = None, location: list = None, radius: float = 1.0, user_prompt: str = "") -> str:
    """Add curve primitive. type: BEZIER_CIRCLE|BEZIER_CURVE|NURBS_CIRCLE|NURBS_PATH."""
    return _bm_call(ctx, "bm_add_curve_primitive", {"type": type, "name": name, "location": location or [0,0,0], "radius": radius}, user_prompt)

@mcp.tool()
def bm_curve_to_mesh(ctx: Context, name: str, user_prompt: str = "") -> str:
    """Convert curve object to mesh."""
    return _bm_call(ctx, "bm_curve_to_mesh", {"name": name}, user_prompt)

@mcp.tool()
def bm_set_curve_bevel(ctx: Context, name: str, depth: float = 0.05, resolution: int = 4, bevel_object: str = None, user_prompt: str = "") -> str:
    """Add bevel to curve (thickness). bevel_object: name of cross-section curve."""
    return _bm_call(ctx, "bm_set_curve_bevel", {"name": name, "depth": depth, "resolution": resolution, "bevel_object": bevel_object}, user_prompt)

# --- Topology ---
@mcp.tool()
def bm_bridge_edge_loops(ctx: Context, name: str, edge_indices: list = None, user_prompt: str = "") -> str:
    """Bridge two edge loops. edge_indices: list forming two loops, or None for current selection."""
    return _bm_call(ctx, "bm_bridge_edge_loops", {"name": name, "edge_indices": edge_indices}, user_prompt)

@mcp.tool()
def bm_grid_fill(ctx: Context, name: str, edge_indices: list = None, span: int = 2, user_prompt: str = "") -> str:
    """Grid-fill closed edge loop."""
    return _bm_call(ctx, "bm_grid_fill", {"name": name, "edge_indices": edge_indices, "span": span}, user_prompt)

@mcp.tool()
def bm_quadrify(ctx: Context, name: str, face_threshold_deg: float = 40, shape_threshold_deg: float = 40, user_prompt: str = "") -> str:
    """Convert tris to quads."""
    return _bm_call(ctx, "bm_quadrify", {"name": name, "face_threshold_deg": face_threshold_deg, "shape_threshold_deg": shape_threshold_deg}, user_prompt)

@mcp.tool()
def bm_check_topology(ctx: Context, name: str, user_prompt: str = "") -> str:
    """Report tris/quads/ngons/non-manifold/loose stats."""
    return _bm_call(ctx, "bm_check_topology", {"name": name}, user_prompt)

@mcp.tool()
def bm_select_ngons(ctx: Context, name: str, user_prompt: str = "") -> str:
    """Select all faces with 5+ verts."""
    return _bm_call(ctx, "bm_select_ngons", {"name": name}, user_prompt)

@mcp.tool()
def bm_select_tris(ctx: Context, name: str, user_prompt: str = "") -> str:
    """Select all triangle faces."""
    return _bm_call(ctx, "bm_select_tris", {"name": name}, user_prompt)

@mcp.tool()
def bm_select_non_manifold(ctx: Context, name: str, user_prompt: str = "") -> str:
    """Select non-manifold edges (holes, T-junctions)."""
    return _bm_call(ctx, "bm_select_non_manifold", {"name": name}, user_prompt)

@mcp.tool()
def bm_dissolve_limited(ctx: Context, name: str, angle_deg: float = 5, user_prompt: str = "") -> str:
    """Limited Dissolve — removes unnecessary geometry below angle threshold. Best topology cleanup tool."""
    return _bm_call(ctx, "bm_dissolve_limited", {"name": name, "angle_deg": angle_deg}, user_prompt)

@mcp.tool()
def bm_clean_topology(ctx: Context, name: str, merge_distance: float = 0.0001, quadrify: bool = True, recalc_normals: bool = True, remove_loose: bool = True, user_prompt: str = "") -> str:
    """One-shot cleanup: merge doubles + recalc normals + tris→quads + remove loose."""
    return _bm_call(ctx, "bm_clean_topology", {"name": name, "merge_distance": merge_distance, "quadrify": quadrify, "recalc_normals": recalc_normals, "remove_loose": remove_loose}, user_prompt)

@mcp.tool()
def bm_decimate(ctx: Context, name: str, ratio: float = 0.5, user_prompt: str = "") -> str:
    """Reduce poly count. Beware: can introduce bad triangulation."""
    return _bm_call(ctx, "bm_decimate", {"name": name, "ratio": ratio}, user_prompt)

@mcp.tool()
def bm_add_subsurf(ctx: Context, name: str, levels: int = 2, render_levels: int = None, user_prompt: str = "") -> str:
    """Add Subdivision Surface modifier."""
    return _bm_call(ctx, "bm_add_subsurf", {"name": name, "levels": levels, "render_levels": render_levels}, user_prompt)

@mcp.tool()
def bm_remove_loose_geometry(ctx: Context, name: str, user_prompt: str = "") -> str:
    """Delete unconnected verts/edges/faces."""
    return _bm_call(ctx, "bm_remove_loose_geometry", {"name": name}, user_prompt)

# --- Topology QA ---
@mcp.tool()
def bm_pole_count(ctx: Context, name: str, user_prompt: str = "") -> str:
    """Histogram of vert edge-degrees + warnings. Good topology = mostly 4-pole verts."""
    return _bm_call(ctx, "bm_pole_count", {"name": name}, user_prompt)

@mcp.tool()
def bm_select_high_poles(ctx: Context, name: str, min_edges: int = 6, user_prompt: str = "") -> str:
    """Select verts with too many edges (fan-pole problems)."""
    return _bm_call(ctx, "bm_select_high_poles", {"name": name, "min_edges": min_edges}, user_prompt)

@mcp.tool()
def bm_select_stretched_tris(ctx: Context, name: str, ratio: float = 3.0, user_prompt: str = "") -> str:
    """Select sliver triangles (longest/shortest edge ratio above threshold)."""
    return _bm_call(ctx, "bm_select_stretched_tris", {"name": name, "ratio": ratio}, user_prompt)

@mcp.tool()
def bm_warn_topology(ctx: Context, name: str, user_prompt: str = "") -> str:
    """COMPREHENSIVE topology audit. Returns warnings + topology_score 0-100. Call after any mesh op to catch junk."""
    return _bm_call(ctx, "bm_warn_topology", {"name": name}, user_prompt)

# --- Reference / blueprint ---
@mcp.tool()
def bm_add_reference_image(ctx: Context, filepath: str, axis: str = "FRONT", location: list = None, size: float = 1.0, opacity: float = 0.5, user_prompt: str = "") -> str:
    """Add background reference image for blueprint modeling. axis: FRONT|BACK|LEFT|RIGHT|TOP|BOTTOM."""
    return _bm_call(ctx, "bm_add_reference_image", {"filepath": filepath, "axis": axis, "location": location or [0,0,0], "size": size, "opacity": opacity}, user_prompt)

@mcp.tool()
def bm_select_edge_loop(ctx: Context, name: str, edge_index: int, user_prompt: str = "") -> str:
    """Select edge loop from seed edge (Alt+click equivalent)."""
    return _bm_call(ctx, "bm_select_edge_loop", {"name": name, "edge_index": edge_index}, user_prompt)

@mcp.tool()
def bm_select_edge_ring(ctx: Context, name: str, edge_index: int, user_prompt: str = "") -> str:
    """Select edge ring (Ctrl+Alt+click equivalent)."""
    return _bm_call(ctx, "bm_select_edge_ring", {"name": name, "edge_index": edge_index}, user_prompt)

@mcp.tool()
def bm_inset_faces(ctx: Context, name: str, face_indices: list, thickness: float = 0.02, depth: float = 0.0, individual: bool = False, user_prompt: str = "") -> str:
    """Inset faces. Critical for adding edge loops around features without breaking topology."""
    return _bm_call(ctx, "bm_inset_faces", {"name": name, "face_indices": face_indices, "thickness": thickness, "depth": depth, "individual": individual}, user_prompt)

@mcp.tool()
def bm_shrinkwrap_to(ctx: Context, name: str, target_name: str, wrap_method: str = "NEAREST_SURFACEPOINT", offset: float = 0.0, apply: bool = False, user_prompt: str = "") -> str:
    """Project mesh onto target via Shrinkwrap. Great for retopo on high-poly references."""
    return _bm_call(ctx, "bm_shrinkwrap_to", {"name": name, "target_name": target_name, "wrap_method": wrap_method, "offset": offset, "apply": apply}, user_prompt)

@mcp.tool()
def bm_remesh(ctx: Context, name: str, mode: str = "VOXEL", voxel_size: float = 0.05, octree_depth: int = 5, apply: bool = True, user_prompt: str = "") -> str:
    """Auto-remesh. mode: VOXEL (most reliable)|QUAD|SHARP|SMOOTH|BLOCKS."""
    return _bm_call(ctx, "bm_remesh", {"name": name, "mode": mode, "voxel_size": voxel_size, "octree_depth": octree_depth, "apply": apply}, user_prompt)

# Car modeling
@mcp.tool()
def bm_boolean(ctx: Context, name: str, target: str, operation: str = "DIFFERENCE", solver: str = "EXACT", apply: bool = True, user_prompt: str = "") -> str:
    """Boolean op between meshes. operation: DIFFERENCE|UNION|INTERSECT. solver: EXACT|FAST."""
    return _bm_call(ctx, "bm_boolean", {"name": name, "target": target, "operation": operation, "solver": solver, "apply": apply}, user_prompt)

@mcp.tool()
def bm_bisect_plane(ctx: Context, name: str, plane_point: list, plane_normal: list, fill: bool = True, clear_inner: bool = False, clear_outer: bool = False, user_prompt: str = "") -> str:
    """Bisect mesh with plane. clear_inner removes side opposite normal."""
    return _bm_call(ctx, "bm_bisect_plane", {"name": name, "plane_point": plane_point, "plane_normal": plane_normal, "fill": fill, "clear_inner": clear_inner, "clear_outer": clear_outer}, user_prompt)

@mcp.tool()
def bm_symmetrize(ctx: Context, name: str, direction: str = "POSITIVE_X", threshold: float = 0.0001, user_prompt: str = "") -> str:
    """Symmetrize mesh. direction: POSITIVE_X|NEGATIVE_X|POSITIVE_Y|NEGATIVE_Y|POSITIVE_Z|NEGATIVE_Z (or +X/-X shorthand)."""
    return _bm_call(ctx, "bm_symmetrize", {"name": name, "direction": direction, "threshold": threshold}, user_prompt)

@mcp.tool()
def bm_set_edge_crease(ctx: Context, name: str, edge_indices: list, weight: float = 1.0, user_prompt: str = "") -> str:
    """Set SubSurf crease weight on edges (0=smooth, 1=sharp)."""
    return _bm_call(ctx, "bm_set_edge_crease", {"name": name, "edge_indices": edge_indices, "weight": weight}, user_prompt)

@mcp.tool()
def bm_set_edge_bevel_weight(ctx: Context, name: str, edge_indices: list, weight: float = 1.0, user_prompt: str = "") -> str:
    """Set bevel weight on edges (for Bevel modifier with Weight limit)."""
    return _bm_call(ctx, "bm_set_edge_bevel_weight", {"name": name, "edge_indices": edge_indices, "weight": weight}, user_prompt)

@mcp.tool()
def bm_set_vert_bevel_weight(ctx: Context, name: str, vert_indices: list, weight: float = 1.0, user_prompt: str = "") -> str:
    """Set bevel weight on vertices."""
    return _bm_call(ctx, "bm_set_vert_bevel_weight", {"name": name, "vert_indices": vert_indices, "weight": weight}, user_prompt)

@mcp.tool()
def bm_proportional_translate(ctx: Context, name: str, seed_vert_index: int, delta: list, falloff: str = "SMOOTH", radius: float = 1.0, user_prompt: str = "") -> str:
    """Translate seed vert + propagate with falloff. falloff: SMOOTH|SPHERE|ROOT|SHARP|LINEAR|CONSTANT."""
    return _bm_call(ctx, "bm_proportional_translate", {"name": name, "seed_vert_index": seed_vert_index, "delta": delta, "falloff": falloff, "radius": radius}, user_prompt)

@mcp.tool()
def bm_merge_verts(ctx: Context, name: str, vert_indices: list, mode: str = "CENTER", user_prompt: str = "") -> str:
    """Merge verts. mode: CENTER|FIRST|LAST|COLLAPSE."""
    return _bm_call(ctx, "bm_merge_verts", {"name": name, "vert_indices": vert_indices, "mode": mode}, user_prompt)

@mcp.tool()
def bm_array_modifier(ctx: Context, name: str, count: int = 3, axis: str = "x", offset: float = 1.0, fit_type: str = "FIXED_COUNT", curve: str = None, user_prompt: str = "") -> str:
    """Array modifier (non-destructive)."""
    return _bm_call(ctx, "bm_array_modifier", {"name": name, "count": count, "axis": axis, "offset": offset, "fit_type": fit_type, "curve": curve}, user_prompt)

@mcp.tool()
def bm_curve_modifier(ctx: Context, name: str, curve_name: str, axis: str = "POS_X", user_prompt: str = "") -> str:
    """Deform mesh along curve via Curve modifier. axis: POS_X|NEG_X|POS_Y|NEG_Y|POS_Z|NEG_Z."""
    return _bm_call(ctx, "bm_curve_modifier", {"name": name, "curve_name": curve_name, "axis": axis}, user_prompt)

@mcp.tool()
def bm_edge_slide(ctx: Context, name: str, edge_indices: list, factor: float = 0.5, user_prompt: str = "") -> str:
    """Slide edge loop along adjacent edges. factor: -1..1."""
    return _bm_call(ctx, "bm_edge_slide", {"name": name, "edge_indices": edge_indices, "factor": factor}, user_prompt)

@mcp.tool()
def bm_select_inside_bbox(ctx: Context, name: str, bbox_min: list, bbox_max: list, space: str = "world", user_prompt: str = "") -> str:
    """Select verts inside axis-aligned bbox."""
    return _bm_call(ctx, "bm_select_inside_bbox", {"name": name, "bbox_min": bbox_min, "bbox_max": bbox_max, "space": space}, user_prompt)

@mcp.tool()
def bm_select_by_material(ctx: Context, name: str, material_name: str, user_prompt: str = "") -> str:
    """Select all faces with given material assigned."""
    return _bm_call(ctx, "bm_select_by_material", {"name": name, "material_name": material_name}, user_prompt)

@mcp.tool()
def bm_make_lod_set(ctx: Context, name: str, ratios: list = None, filepath_prefix: str = None, user_prompt: str = "") -> str:
    """Generate LOD chain via duplicate + decimate. Default ratios [1.0, 0.5, 0.25, 0.1]. Optionally exports each as FBX."""
    return _bm_call(ctx, "bm_make_lod_set", {"name": name, "ratios": ratios or [1.0, 0.5, 0.25, 0.1], "filepath_prefix": filepath_prefix}, user_prompt)

@mcp.tool()
def bm_setup_car_template(ctx: Context, name: str = "Car", front_image: str = None, side_image: str = None, top_image: str = None, length: float = 4.7, width: float = 2.0, height: float = 1.45, user_prompt: str = "") -> str:
    """One-call car modeling setup: blueprint refs + half-cube + Mirror X + SubSurf level 2. Default = Tesla Model 3 dims."""
    return _bm_call(ctx, "bm_setup_car_template", {"name": name, "front_image": front_image, "side_image": side_image, "top_image": top_image, "length": length, "width": width, "height": height}, user_prompt)

# Gun modeling
@mcp.tool()
def bm_text_3d(ctx: Context, text: str, name: str = None, location: list = None, size: float = 0.1, extrude: float = 0.02, align_x: str = "CENTER", align_y: str = "CENTER", user_prompt: str = "") -> str:
    """Create 3D text object. extrude = depth (thickness)."""
    return _bm_call(ctx, "bm_text_3d", {"text": text, "name": name, "location": location or [0,0,0], "size": size, "extrude": extrude, "align_x": align_x, "align_y": align_y}, user_prompt)

@mcp.tool()
def bm_emboss_text(ctx: Context, target_name: str, text: str, location: list, size: float = 0.05, depth: float = 0.01, axis: str = "z", operation: str = "DIFFERENCE", user_prompt: str = "") -> str:
    """Emboss/engrave text into target via Boolean. operation: DIFFERENCE (engrave) | UNION (emboss)."""
    return _bm_call(ctx, "bm_emboss_text", {"target_name": target_name, "text": text, "location": location, "size": size, "depth": depth, "axis": axis, "operation": operation}, user_prompt)

@mcp.tool()
def bm_set_origin_to_face(ctx: Context, name: str, face_index: int, user_prompt: str = "") -> str:
    """Set object origin to face's center (for assembly pivot)."""
    return _bm_call(ctx, "bm_set_origin_to_face", {"name": name, "face_index": face_index}, user_prompt)

@mcp.tool()
def bm_set_origin_to_vert(ctx: Context, name: str, vert_index: int, user_prompt: str = "") -> str:
    """Set object origin to vertex position."""
    return _bm_call(ctx, "bm_set_origin_to_vert", {"name": name, "vert_index": vert_index}, user_prompt)

@mcp.tool()
def bm_align_face_to_face(ctx: Context, src_name: str, src_face: int, dst_name: str, dst_face: int, flip: bool = False, user_prompt: str = "") -> str:
    """Move + rotate src so its face touches dst's face (normals opposite). Critical for assembling gun parts."""
    return _bm_call(ctx, "bm_align_face_to_face", {"src_name": src_name, "src_face": src_face, "dst_name": dst_name, "dst_face": dst_face, "flip": flip}, user_prompt)

@mcp.tool()
def bm_punch_pattern(ctx: Context, target_name: str, count: int = 5, spacing: float = 0.05, slot_size: list = None, start_location: list = None, axis: str = "x", operation: str = "DIFFERENCE", user_prompt: str = "") -> str:
    """Punch repeated holes/slots through target (e.g. cooling slot pattern on MP40 receiver)."""
    return _bm_call(ctx, "bm_punch_pattern", {"target_name": target_name, "count": count, "spacing": spacing, "slot_size": slot_size or [0.02,0.005,0.02], "start_location": start_location or [0,0,0], "axis": axis, "operation": operation}, user_prompt)

@mcp.tool()
def bm_add_skin_modifier(ctx: Context, name: str, root_vert_index: int = 0, default_size: float = 0.05, user_prompt: str = "") -> str:
    """Skin modifier — turns edge graph into cylinders. Set root vert + default radius."""
    return _bm_call(ctx, "bm_add_skin_modifier", {"name": name, "root_vert_index": root_vert_index, "default_size": default_size}, user_prompt)

@mcp.tool()
def bm_add_wireframe_modifier(ctx: Context, name: str, thickness: float = 0.01, offset: float = 0.0, user_prompt: str = "") -> str:
    """Wireframe modifier — converts mesh to 3D wire."""
    return _bm_call(ctx, "bm_add_wireframe_modifier", {"name": name, "thickness": thickness, "offset": offset}, user_prompt)

@mcp.tool()
def bm_add_solidify_modifier(ctx: Context, name: str, thickness: float = 0.01, offset: float = -1.0, user_prompt: str = "") -> str:
    """Solidify modifier — gives sheet thickness. offset: -1=inside, 0=center, 1=outside."""
    return _bm_call(ctx, "bm_add_solidify_modifier", {"name": name, "thickness": thickness, "offset": offset}, user_prompt)

@mcp.tool()
def bm_array_objects_along_edge(ctx: Context, template_name: str, target_name: str, edge_indices: list, count_per_edge: int = 5, user_prompt: str = "") -> str:
    """Place instances of template along edges of target — rivets, screws, body trim."""
    return _bm_call(ctx, "bm_array_objects_along_edge", {"template_name": template_name, "target_name": target_name, "edge_indices": edge_indices, "count_per_edge": count_per_edge}, user_prompt)

@mcp.tool()
def bm_mesh_thickness_stats(ctx: Context, name: str, samples: int = 100, user_prompt: str = "") -> str:
    """Measure wall thickness via raycasts. Returns min/max/avg — catches parts too thin."""
    return _bm_call(ctx, "bm_mesh_thickness_stats", {"name": name, "samples": samples}, user_prompt)

@mcp.tool()
def bm_center_of_mass(ctx: Context, name: str, user_prompt: str = "") -> str:
    """Geometric centroid of all verts (world space). For balance checks."""
    return _bm_call(ctx, "bm_center_of_mass", {"name": name}, user_prompt)

# Math helpers
@mcp.tool()
def bm_lerp(ctx: Context, p1: list, p2: list, t: float, user_prompt: str = "") -> str:
    """Linear interpolation between two points."""
    return _bm_call(ctx, "bm_lerp", {"p1": p1, "p2": p2, "t": t}, user_prompt)

@mcp.tool()
def bm_slerp_quat(ctx: Context, q1: list, q2: list, t: float, user_prompt: str = "") -> str:
    """Spherical lerp between two quaternions (smooth rotation blend)."""
    return _bm_call(ctx, "bm_slerp_quat", {"q1": q1, "q2": q2, "t": t}, user_prompt)

@mcp.tool()
def bm_normal_from_3pts(ctx: Context, p1: list, p2: list, p3: list, user_prompt: str = "") -> str:
    """Compute plane normal from 3 points."""
    return _bm_call(ctx, "bm_normal_from_3pts", {"p1": p1, "p2": p2, "p3": p3}, user_prompt)

@mcp.tool()
def bm_centroid_of_points(ctx: Context, points: list, user_prompt: str = "") -> str:
    """Centroid of a list of points."""
    return _bm_call(ctx, "bm_centroid_of_points", {"points": points}, user_prompt)

@mcp.tool()
def bm_circle_from_3pts(ctx: Context, p1: list, p2: list, p3: list, user_prompt: str = "") -> str:
    """Center + radius of circle through 3 coplanar points."""
    return _bm_call(ctx, "bm_circle_from_3pts", {"p1": p1, "p2": p2, "p3": p3}, user_prompt)

@mcp.tool()
def bm_dist_point_to_line(ctx: Context, point: list, line_p1: list, line_p2: list, user_prompt: str = "") -> str:
    """Distance from point to line segment + closest point."""
    return _bm_call(ctx, "bm_dist_point_to_line", {"point": point, "line_p1": line_p1, "line_p2": line_p2}, user_prompt)

@mcp.tool()
def bm_dist_point_to_plane(ctx: Context, point: list, plane_point: list, plane_normal: list, user_prompt: str = "") -> str:
    """Signed distance from point to infinite plane."""
    return _bm_call(ctx, "bm_dist_point_to_plane", {"point": point, "plane_point": plane_point, "plane_normal": plane_normal}, user_prompt)

@mcp.tool()
def bm_intersect_line_plane(ctx: Context, line_p1: list, line_p2: list, plane_point: list, plane_normal: list, user_prompt: str = "") -> str:
    """Intersection point of line and plane."""
    return _bm_call(ctx, "bm_intersect_line_plane", {"line_p1": line_p1, "line_p2": line_p2, "plane_point": plane_point, "plane_normal": plane_normal}, user_prompt)

# Curves
@mcp.tool()
def bm_circle_arc(ctx: Context, p1: list, p2: list, p3: list, segments: int = 16, name: str = "Arc", user_prompt: str = "") -> str:
    """Create curve arc passing through 3 points (p2 is the mid-point hint)."""
    return _bm_call(ctx, "bm_circle_arc", {"p1": p1, "p2": p2, "p3": p3, "segments": segments, "name": name}, user_prompt)

@mcp.tool()
def bm_bezier_from_4pts(ctx: Context, p0: list, p1: list, p2: list, p3: list, segments: int = 16, name: str = "Bezier", user_prompt: str = "") -> str:
    """Create cubic Bezier curve from 4 control points."""
    return _bm_call(ctx, "bm_bezier_from_4pts", {"p0": p0, "p1": p1, "p2": p2, "p3": p3, "segments": segments, "name": name}, user_prompt)

@mcp.tool()
def bm_offset_curve(ctx: Context, name: str, distance: float = 0.05, axis: str = "z", new_name: str = None, user_prompt: str = "") -> str:
    """Create parallel curve offset along axis."""
    return _bm_call(ctx, "bm_offset_curve", {"name": name, "distance": distance, "axis": axis, "new_name": new_name}, user_prompt)

# Workflow
@mcp.tool()
def bm_apply_all_modifiers(ctx: Context, name: str, user_prompt: str = "") -> str:
    """Apply all modifiers in stack order."""
    return _bm_call(ctx, "bm_apply_all_modifiers", {"name": name}, user_prompt)

@mcp.tool()
def bm_smart_bevel(ctx: Context, name: str, edge_indices: list, width: float = 0.005, segments: int = 2, crease_for_subsurf: bool = True, user_prompt: str = "") -> str:
    """Bevel + auto-crease for SubSurf-friendly hard surface (HardOps-style)."""
    return _bm_call(ctx, "bm_smart_bevel", {"name": name, "edge_indices": edge_indices, "width": width, "segments": segments, "crease_for_subsurf": crease_for_subsurf}, user_prompt)

@mcp.tool()
def bm_check_symmetry(ctx: Context, name: str, axis: str = "x", tolerance: float = 0.001, user_prompt: str = "") -> str:
    """Verify mesh is symmetric across axis. Returns matched/unmatched + symmetry %."""
    return _bm_call(ctx, "bm_check_symmetry", {"name": name, "axis": axis, "tolerance": tolerance}, user_prompt)

# Character animation / IK / rigging
@mcp.tool()
def bm_setup_ik(ctx: Context, armature_name: str, end_bone: str, target_empty: str = None, pole_target: str = None, chain_count: int = 2, pole_angle: float = -90, weight_position: float = 1.0, weight_rotation: float = 0.0, user_prompt: str = "") -> str:
    """Add IK constraint to end_bone. target_empty/pole_target are object names."""
    return _bm_call(ctx, "bm_setup_ik", {"armature_name": armature_name, "end_bone": end_bone, "target_empty": target_empty, "pole_target": pole_target, "chain_count": chain_count, "pole_angle": pole_angle, "weight_position": weight_position, "weight_rotation": weight_rotation}, user_prompt)

@mcp.tool()
def bm_setup_leg_ik(ctx: Context, armature_name: str, hip_bone: str, knee_bone: str, foot_bone: str, foot_target_name: str = None, pole_target_name: str = None, pole_distance: float = 0.3, user_prompt: str = "") -> str:
    """One-call leg IK: auto-create foot target + knee pole + IK constraint."""
    return _bm_call(ctx, "bm_setup_leg_ik", {"armature_name": armature_name, "hip_bone": hip_bone, "knee_bone": knee_bone, "foot_bone": foot_bone, "foot_target_name": foot_target_name, "pole_target_name": pole_target_name, "pole_distance": pole_distance}, user_prompt)

@mcp.tool()
def bm_setup_arm_ik(ctx: Context, armature_name: str, shoulder_bone: str, elbow_bone: str, hand_bone: str, hand_target_name: str = None, pole_target_name: str = None, pole_distance: float = 0.3, user_prompt: str = "") -> str:
    """One-call arm IK: auto-create hand target + elbow pole + IK constraint."""
    return _bm_call(ctx, "bm_setup_arm_ik", {"armature_name": armature_name, "shoulder_bone": shoulder_bone, "elbow_bone": elbow_bone, "hand_bone": hand_bone, "hand_target_name": hand_target_name, "pole_target_name": pole_target_name, "pole_distance": pole_distance}, user_prompt)

@mcp.tool()
def bm_create_control_bone(ctx: Context, armature_name: str, name: str, head: list, tail: list, parent: str = None, custom_shape_obj: str = None, user_prompt: str = "") -> str:
    """Add non-deforming control bone (used as IK target etc.). custom_shape_obj: name of object to use as bone shape."""
    return _bm_call(ctx, "bm_create_control_bone", {"armature_name": armature_name, "name": name, "head": head, "tail": tail, "parent": parent, "custom_shape_obj": custom_shape_obj}, user_prompt)

@mcp.tool()
def bm_add_armature_modifier(ctx: Context, mesh_name: str, armature_name: str, vgroups: bool = True, envelopes: bool = False, user_prompt: str = "") -> str:
    """Bind mesh to armature via Armature modifier + parenting."""
    return _bm_call(ctx, "bm_add_armature_modifier", {"mesh_name": mesh_name, "armature_name": armature_name, "vgroups": vgroups, "envelopes": envelopes}, user_prompt)

@mcp.tool()
def bm_auto_weights(ctx: Context, mesh_name: str, armature_name: str, user_prompt: str = "") -> str:
    """Bind mesh to armature with AUTOMATIC heat-map weights (no manual weight painting needed)."""
    return _bm_call(ctx, "bm_auto_weights", {"mesh_name": mesh_name, "armature_name": armature_name}, user_prompt)

@mcp.tool()
def bm_assign_vertex_group(ctx: Context, mesh_name: str, group_name: str, vert_indices: list, weight: float = 1.0, user_prompt: str = "") -> str:
    """Add verts to vertex group with weight. Creates group if missing."""
    return _bm_call(ctx, "bm_assign_vertex_group", {"mesh_name": mesh_name, "group_name": group_name, "vert_indices": vert_indices, "weight": weight}, user_prompt)

@mcp.tool()
def bm_normalize_vertex_groups(ctx: Context, mesh_name: str, lock_active: bool = False, user_prompt: str = "") -> str:
    """Normalize all vertex group weights to sum to 1 per vert."""
    return _bm_call(ctx, "bm_normalize_vertex_groups", {"mesh_name": mesh_name, "lock_active": lock_active}, user_prompt)

@mcp.tool()
def bm_set_bone_display(ctx: Context, armature_name: str, bone_name: str, shape: str = "OCTAHEDRAL", user_prompt: str = "") -> str:
    """Set armature display type. shape: OCTAHEDRAL|STICK|BBONE|ENVELOPE|WIRE."""
    return _bm_call(ctx, "bm_set_bone_display", {"armature_name": armature_name, "bone_name": bone_name, "shape": shape}, user_prompt)

@mcp.tool()
def bm_set_bone_roll(ctx: Context, armature_name: str, bone_name: str, angle_deg: float, user_prompt: str = "") -> str:
    """Set bone roll angle (rotation around bone's Y axis)."""
    return _bm_call(ctx, "bm_set_bone_roll", {"armature_name": armature_name, "bone_name": bone_name, "angle_deg": angle_deg}, user_prompt)

@mcp.tool()
def bm_mirror_bones(ctx: Context, armature_name: str, src_suffix: str = ".l", dst_suffix: str = ".r", user_prompt: str = "") -> str:
    """Mirror .l bones to .r (or vice-versa) via armature.symmetrize."""
    return _bm_call(ctx, "bm_mirror_bones", {"armature_name": armature_name, "src_suffix": src_suffix, "dst_suffix": dst_suffix}, user_prompt)

@mcp.tool()
def bm_add_bone_chain(ctx: Context, armature_name: str, names: list, head_positions: list, tail_positions: list = None, parent_chain: bool = True, parent_first_to: str = None, connect: bool = True, user_prompt: str = "") -> str:
    """Add chain of bones. tail auto-derived from next head if None. parent_chain: each bone parents to previous."""
    return _bm_call(ctx, "bm_add_bone_chain", {"armature_name": armature_name, "names": names, "head_positions": head_positions, "tail_positions": tail_positions, "parent_chain": parent_chain, "parent_first_to": parent_first_to, "connect": connect}, user_prompt)

@mcp.tool()
def bm_push_to_nla(ctx: Context, armature_name: str, action_name: str = None, strip_name: str = None, user_prompt: str = "") -> str:
    """Push armature's active (or named) action onto a new NLA strip."""
    return _bm_call(ctx, "bm_push_to_nla", {"armature_name": armature_name, "action_name": action_name, "strip_name": strip_name}, user_prompt)

@mcp.tool()
def bm_add_shape_key(ctx: Context, mesh_name: str, name: str, from_mix: bool = False, user_prompt: str = "") -> str:
    """Add shape key to mesh (auto-creates Basis on first call)."""
    return _bm_call(ctx, "bm_add_shape_key", {"mesh_name": mesh_name, "name": name, "from_mix": from_mix}, user_prompt)

@mcp.tool()
def bm_blend_actions(ctx: Context, target_armature: str, action1: str, action2: str, weight: float = 0.5, blend_mode: str = "REPLACE", user_prompt: str = "") -> str:
    """Blend two actions via NLA strips. weight: 0=action1, 1=action2."""
    return _bm_call(ctx, "bm_blend_actions", {"target_armature": target_armature, "action1": action1, "action2": action2, "weight": weight, "blend_mode": blend_mode}, user_prompt)

# Smart weight paint
@mcp.tool()
def bm_paint_weight_to_bone(ctx: Context, mesh_name: str, group_name: str, vert_indices: list, weight: float = 1.0, mode: str = "REPLACE", user_prompt: str = "") -> str:
    """Paint weight to vertex group. mode: REPLACE|ADD|SUBTRACT|MULTIPLY."""
    return _bm_call(ctx, "bm_paint_weight_to_bone", {"mesh_name": mesh_name, "group_name": group_name, "vert_indices": vert_indices, "weight": weight, "mode": mode}, user_prompt)

@mcp.tool()
def bm_smooth_weights(ctx: Context, mesh_name: str, group_name: str = None, iterations: int = 3, factor: float = 0.5, user_prompt: str = "") -> str:
    """Smooth vertex group weights via neighbor averaging."""
    return _bm_call(ctx, "bm_smooth_weights", {"mesh_name": mesh_name, "group_name": group_name, "iterations": iterations, "factor": factor}, user_prompt)

@mcp.tool()
def bm_copy_weights(ctx: Context, mesh_name: str, src_group: str, dst_group: str, user_prompt: str = "") -> str:
    """Copy weights from src vgroup to dst vgroup."""
    return _bm_call(ctx, "bm_copy_weights", {"mesh_name": mesh_name, "src_group": src_group, "dst_group": dst_group}, user_prompt)

@mcp.tool()
def bm_set_active_vgroup(ctx: Context, mesh_name: str, group_name: str, user_prompt: str = "") -> str:
    """Set active vertex group on mesh — controls which weights show in WEIGHT_PAINT viewport."""
    return _bm_call(ctx, "bm_set_active_vgroup", {"mesh_name": mesh_name, "group_name": group_name}, user_prompt)

@mcp.tool()
def bm_weight_by_plane_split(ctx: Context, mesh_name: str, plane_point: list,
                             plane_normal: list, blend_width: float,
                             group_neg: str, group_pos: str,
                             clear_others: bool = True, space: str = "local",
                             user_prompt: str = "") -> str:
    """Split weights by signed distance to an arbitrary plane. For diagonal-cut
    joints (e.g. Roblox-style 45° elbow). plane_point: [x,y,z] point on plane
    (e.g. elbow position). plane_normal: [nx,ny,nz] (auto-normalized). blend_width:
    half-width of transition. group_neg/pos: vgroup names for neg/pos sides.

    Example 45° elbow cut at origin, normal pointing into bicep+up:
        plane_point=[0,0,0], plane_normal=[0,1,1], group_neg='Forearm', group_pos='Bicep'"""
    return _bm_call(ctx, "bm_weight_by_plane_split",
                    {"mesh_name": mesh_name, "plane_point": plane_point,
                     "plane_normal": plane_normal, "blend_width": blend_width,
                     "group_neg": group_neg, "group_pos": group_pos,
                     "clear_others": clear_others, "space": space}, user_prompt)

@mcp.tool()
def bm_weight_by_axis_split(ctx: Context, mesh_name: str, axis: str, boundary: float,
                            blend_width: float, group_neg: str, group_pos: str,
                            clear_others: bool = True, space: str = "local",
                            user_prompt: str = "") -> str:
    """Split mesh weights between two bones along an axis with smooth linear blend.

    axis: 'x'|'y'|'z'. boundary: position along axis (e.g. 0.0). blend_width: half-width
    of transition band. group_neg: vgroup for < boundary side. group_pos: vgroup for >
    boundary side. clear_others: wipe other vgroups first. space: 'local' or 'world'."""
    return _bm_call(ctx, "bm_weight_by_axis_split",
                    {"mesh_name": mesh_name, "axis": axis, "boundary": boundary,
                     "blend_width": blend_width, "group_neg": group_neg, "group_pos": group_pos,
                     "clear_others": clear_others, "space": space}, user_prompt)

@mcp.tool()
def bm_transfer_weights(ctx: Context, src_mesh_name: str, dst_mesh_name: str, user_prompt: str = "") -> str:
    """Transfer all vertex weights between meshes (proximity-based)."""
    return _bm_call(ctx, "bm_transfer_weights", {"src_mesh_name": src_mesh_name, "dst_mesh_name": dst_mesh_name}, user_prompt)

@mcp.tool()
def bm_clean_weights(ctx: Context, mesh_name: str, threshold: float = 0.01, user_prompt: str = "") -> str:
    """Remove weights below threshold from all groups."""
    return _bm_call(ctx, "bm_clean_weights", {"mesh_name": mesh_name, "threshold": threshold}, user_prompt)

@mcp.tool()
def bm_mirror_weights(ctx: Context, mesh_name: str, axis: str = "X", user_prompt: str = "") -> str:
    """Mirror vertex group weights across axis."""
    return _bm_call(ctx, "bm_mirror_weights", {"mesh_name": mesh_name, "axis": axis}, user_prompt)

@mcp.tool()
def bm_get_weights_at_vert(ctx: Context, mesh_name: str, vert_index: int, user_prompt: str = "") -> str:
    """Debug: list all vertex groups + weights for a single vert."""
    return _bm_call(ctx, "bm_get_weights_at_vert", {"mesh_name": mesh_name, "vert_index": vert_index}, user_prompt)

@mcp.tool()
def bm_weight_gradient(ctx: Context, mesh_name: str, group_name: str, vert1_index: int, vert2_index: int, weight1: float = 1.0, weight2: float = 0.0, user_prompt: str = "") -> str:
    """Linear gradient between two verts."""
    return _bm_call(ctx, "bm_weight_gradient", {"mesh_name": mesh_name, "group_name": group_name, "vert1_index": vert1_index, "vert2_index": vert2_index, "weight1": weight1, "weight2": weight2}, user_prompt)

@mcp.tool()
def bm_weight_falloff_from_point(ctx: Context, mesh_name: str, group_name: str, center_point: list, radius: float, falloff: str = "SMOOTH", user_prompt: str = "") -> str:
    """Radial falloff weight assignment."""
    return _bm_call(ctx, "bm_weight_falloff_from_point", {"mesh_name": mesh_name, "group_name": group_name, "center_point": center_point, "radius": radius, "falloff": falloff}, user_prompt)

@mcp.tool()
def bm_remove_zero_weights(ctx: Context, mesh_name: str, user_prompt: str = "") -> str:
    """Remove all zero-weight entries from every group."""
    return _bm_call(ctx, "bm_remove_zero_weights", {"mesh_name": mesh_name}, user_prompt)

@mcp.tool()
def bm_isolate_bone_weights(ctx: Context, mesh_name: str, group_name: str, user_prompt: str = "") -> str:
    """Visually isolate one bone's weights."""
    return _bm_call(ctx, "bm_isolate_bone_weights", {"mesh_name": mesh_name, "group_name": group_name}, user_prompt)

@mcp.tool()
def bm_export_weights(ctx: Context, mesh_name: str, filepath: str, user_prompt: str = "") -> str:
    """Export vertex group weights to JSON."""
    return _bm_call(ctx, "bm_export_weights", {"mesh_name": mesh_name, "filepath": filepath}, user_prompt)

@mcp.tool()
def bm_import_weights(ctx: Context, mesh_name: str, filepath: str, user_prompt: str = "") -> str:
    """Restore weights from JSON."""
    return _bm_call(ctx, "bm_import_weights", {"mesh_name": mesh_name, "filepath": filepath}, user_prompt)

# Optimizers / remeshers
@mcp.tool()
def bm_quadriflow_remesh(ctx: Context, name: str, target_faces: int = 5000, use_paint_symmetry: bool = False, use_preserve_sharp: bool = True, use_preserve_boundary: bool = True, smooth_normals: bool = True, user_prompt: str = "") -> str:
    """QuadriFlow (built-in Blender) — best automatic quad remesher."""
    return _bm_call(ctx, "bm_quadriflow_remesh", {"name": name, "target_faces": target_faces, "use_paint_symmetry": use_paint_symmetry, "use_preserve_sharp": use_preserve_sharp, "use_preserve_boundary": use_preserve_boundary, "smooth_normals": smooth_normals}, user_prompt)

@mcp.tool()
def bm_decimate_planar(ctx: Context, name: str, angle_limit_deg: float = 5, user_prompt: str = "") -> str:
    """Planar decimation — preserves curvature, collapses flat regions."""
    return _bm_call(ctx, "bm_decimate_planar", {"name": name, "angle_limit_deg": angle_limit_deg}, user_prompt)

@mcp.tool()
def bm_decimate_unsubdivide(ctx: Context, name: str, iterations: int = 2, user_prompt: str = "") -> str:
    """Reverse subdivision."""
    return _bm_call(ctx, "bm_decimate_unsubdivide", {"name": name, "iterations": iterations}, user_prompt)

@mcp.tool()
def bm_optimize_for_polycount(ctx: Context, name: str, target_faces: int, preserve_uv: bool = True, prefer_quads: bool = True, user_prompt: str = "") -> str:
    """Smart polycount reduction. Tries QuadriFlow first, falls back to Decimate."""
    return _bm_call(ctx, "bm_optimize_for_polycount", {"name": name, "target_faces": target_faces, "preserve_uv": preserve_uv, "prefer_quads": prefer_quads}, user_prompt)

@mcp.tool()
def bm_equalize_edges(ctx: Context, name: str, iterations: int = 3, factor: float = 0.5, user_prompt: str = "") -> str:
    """Relax verts to make edge lengths more uniform."""
    return _bm_call(ctx, "bm_equalize_edges", {"name": name, "iterations": iterations, "factor": factor}, user_prompt)

@mcp.tool()
def bm_planar_faces(ctx: Context, name: str, threshold_deg: float = 2, user_prompt: str = "") -> str:
    """Flatten near-coplanar faces."""
    return _bm_call(ctx, "bm_planar_faces", {"name": name, "threshold_deg": threshold_deg}, user_prompt)

@mcp.tool()
def bm_minimize_poles(ctx: Context, name: str, max_iterations: int = 3, user_prompt: str = "") -> str:
    """Iteratively dissolve high-poles (fan triangulation cleanup)."""
    return _bm_call(ctx, "bm_minimize_poles", {"name": name, "max_iterations": max_iterations}, user_prompt)

@mcp.tool()
def bm_score_mesh_quality(ctx: Context, name: str, user_prompt: str = "") -> str:
    """Comprehensive mesh quality score 0-100 + warnings + symmetry."""
    return _bm_call(ctx, "bm_score_mesh_quality", {"name": name}, user_prompt)

@mcp.tool()
def bm_compare_meshes(ctx: Context, name1: str, name2: str, user_prompt: str = "") -> str:
    """Compare 2 meshes: vert/poly diff, dim diff, quality score diff."""
    return _bm_call(ctx, "bm_compare_meshes", {"name1": name1, "name2": name2}, user_prompt)

# Physics
@mcp.tool()
def bm_add_cloth(ctx: Context, name: str, mass: float = 0.3, tension_stiffness: float = 15, compression_stiffness: float = 15, shear_stiffness: float = 5, bending_stiffness: float = 0.5, quality: int = 5, user_prompt: str = "") -> str:
    """Add Cloth physics to mesh."""
    return _bm_call(ctx, "bm_add_cloth", {"name": name, "mass": mass, "tension_stiffness": tension_stiffness, "compression_stiffness": compression_stiffness, "shear_stiffness": shear_stiffness, "bending_stiffness": bending_stiffness, "quality": quality}, user_prompt)

@mcp.tool()
def bm_add_fluid(ctx: Context, name: str, type: str = "DOMAIN", domain_type: str = "GAS", resolution: int = 64, user_prompt: str = "") -> str:
    """type: DOMAIN|FLOW|EFFECTOR. domain_type: GAS|LIQUID."""
    return _bm_call(ctx, "bm_add_fluid", {"name": name, "type": type, "domain_type": domain_type, "resolution": resolution}, user_prompt)

@mcp.tool()
def bm_add_softbody(ctx: Context, name: str, mass: float = 1.0, friction: float = 0.5, goal_default: float = 0.7, user_prompt: str = "") -> str:
    """Add Soft Body physics."""
    return _bm_call(ctx, "bm_add_softbody", {"name": name, "mass": mass, "friction": friction, "goal_default": goal_default}, user_prompt)

@mcp.tool()
def bm_add_rigidbody(ctx: Context, name: str, type: str = "ACTIVE", mass: float = 1.0, collision_shape: str = "CONVEX_HULL", friction: float = 0.5, restitution: float = 0.0, user_prompt: str = "") -> str:
    """type: ACTIVE|PASSIVE. shape: BOX|SPHERE|CAPSULE|CONVEX_HULL|MESH."""
    return _bm_call(ctx, "bm_add_rigidbody", {"name": name, "type": type, "mass": mass, "collision_shape": collision_shape, "friction": friction, "restitution": restitution}, user_prompt)

@mcp.tool()
def bm_add_collision(ctx: Context, name: str, damping: float = 0.1, friction: float = 0.5, user_prompt: str = "") -> str:
    """Add collision for cloth/fluid/softbody to bounce off."""
    return _bm_call(ctx, "bm_add_collision", {"name": name, "damping": damping, "friction": friction}, user_prompt)

@mcp.tool()
def bm_bake_physics(ctx: Context, start_frame: int = 1, end_frame: int = 250, user_prompt: str = "") -> str:
    """Bake all physics simulations in scene."""
    return _bm_call(ctx, "bm_bake_physics", {"start_frame": start_frame, "end_frame": end_frame}, user_prompt)

@mcp.tool()
def bm_add_particle_system(ctx: Context, name: str, type: str = "EMITTER", count: int = 1000, frame_start: int = 1, frame_end: int = 200, lifetime: int = 50, user_prompt: str = "") -> str:
    """type: EMITTER|HAIR."""
    return _bm_call(ctx, "bm_add_particle_system", {"name": name, "type": type, "count": count, "frame_start": frame_start, "frame_end": frame_end, "lifetime": lifetime}, user_prompt)

@mcp.tool()
def bm_set_gravity(ctx: Context, gravity: list = None, use_gravity: bool = True, user_prompt: str = "") -> str:
    """Set scene gravity vector."""
    return _bm_call(ctx, "bm_set_gravity", {"gravity": gravity or [0,0,-9.81], "use_gravity": use_gravity}, user_prompt)

@mcp.tool()
def bm_add_force_field(ctx: Context, name: str = "ForceField", type: str = "WIND", location: list = None, strength: float = 1.0, user_prompt: str = "") -> str:
    """type: WIND|VORTEX|TURBULENCE|MAGNETIC|HARMONIC|CURVE_GUIDE|GUIDE."""
    return _bm_call(ctx, "bm_add_force_field", {"name": name, "type": type, "location": location or [0,0,0], "strength": strength}, user_prompt)

# Generic property animation
@mcp.tool()
def bm_keyframe_property(ctx: Context, object_name: str, data_path: str, frame: int, value, index: int = -1, user_prompt: str = "") -> str:
    """Insert keyframe on ANY property. data_path examples: 'location', 'hide_render', 'rotation_euler'."""
    return _bm_call(ctx, "bm_keyframe_property", {"object_name": object_name, "data_path": data_path, "frame": frame, "value": value, "index": index}, user_prompt)

@mcp.tool()
def bm_add_driver(ctx: Context, target_object: str, target_data_path: str, source_object: str, source_data_path: str, expression: str = "var", user_prompt: str = "") -> str:
    """Add driver: target_obj.target_data_path driven by source_obj.source_data_path with Python expression (var = source value)."""
    return _bm_call(ctx, "bm_add_driver", {"target_object": target_object, "target_data_path": target_data_path, "source_object": source_object, "source_data_path": source_data_path, "expression": expression}, user_prompt)

@mcp.tool()
def bm_cyclic_action(ctx: Context, action_name: str, mode: str = "REPEAT", before: str = "NONE", user_prompt: str = "") -> str:
    """Loop action forever via Cycles f-modifier. mode: REPEAT|REPEAT_OFFSET|MIRROR."""
    return _bm_call(ctx, "bm_cyclic_action", {"action_name": action_name, "mode": mode, "before": before}, user_prompt)

@mcp.tool()
def bm_keyframe_material_emission(ctx: Context, material_name: str, strength: float, frame: int, user_prompt: str = "") -> str:
    """Keyframe Principled BSDF emission strength (for light on/off animations)."""
    return _bm_call(ctx, "bm_keyframe_material_emission", {"material_name": material_name, "strength": strength, "frame": frame}, user_prompt)

@mcp.tool()
def bm_keyframe_material_color(ctx: Context, material_name: str, color: list, frame: int, user_prompt: str = "") -> str:
    """Keyframe Principled BSDF base color. color: [r,g,b,a] 0-1."""
    return _bm_call(ctx, "bm_keyframe_material_color", {"material_name": material_name, "color": color, "frame": frame}, user_prompt)

@mcp.tool()
def bm_animate_visibility(ctx: Context, object_name: str, frame: int, visible: bool = True, user_prompt: str = "") -> str:
    """Keyframe object visibility (viewport + render)."""
    return _bm_call(ctx, "bm_animate_visibility", {"object_name": object_name, "frame": frame, "visible": visible}, user_prompt)

# Texture
@mcp.tool()
def bm_resize_texture(ctx: Context, image_name: str, width: int, height: int, save_path: str = None, user_prompt: str = "") -> str:
    """Resize image in Blender. Optionally save to disk."""
    return _bm_call(ctx, "bm_resize_texture", {"image_name": image_name, "width": width, "height": height, "save_path": save_path}, user_prompt)



@mcp.tool()
def bm_list(ctx: Context, types: list = None, user_prompt: str = "") -> str:
    """Compact list of objects: name, type, world dims only. ~10x smaller than bm_dump_objects."""
    return _bm_call(ctx, "bm_list", {"types": types}, user_prompt)

@mcp.tool()
def bm_get_transform(ctx: Context, name: str, user_prompt: str = "") -> str:
    """Single object TRS (loc/rot_deg/scale/parent) — compact."""
    return _bm_call(ctx, "bm_get_transform", {"name": name}, user_prompt)

@mcp.tool()
def bm_get_bbox(ctx: Context, name: str, space: str = "world", user_prompt: str = "") -> str:
    """Single object bbox + dims. space: world|local."""
    return _bm_call(ctx, "bm_get_bbox", {"name": name, "space": space}, user_prompt)

@mcp.tool()
def bm_ping(ctx: Context, user_prompt: str = "") -> str:
    """Instant health check. Returns scene name + frame."""
    return _bm_call(ctx, "bm_ping", {}, user_prompt, timeout=5.0)

@mcp.tool()
def bm_force_mode_set(ctx: Context, name: str, mode: str, user_prompt: str = "") -> str:
    """Robust object-mode change with VIEW_3D area override built-in.
    Replaces brittle bm_set_mode that fails with 'context is incorrect'.
    mode: OBJECT|EDIT|POSE|WEIGHT_PAINT|SCULPT|VERTEX_PAINT|TEXTURE_PAINT."""
    return _bm_call(ctx, "bm_force_mode_set", {"name": name, "mode": mode}, user_prompt)

@mcp.tool()
def bm_inspect_modifier(ctx: Context, name: str, modifier_name: str = None, user_prompt: str = "") -> str:
    """Detailed modifier dump — use_vertex_groups, use_bone_envelopes, object ref,
    levels, segments, etc. Set modifier_name=None for all modifiers on the object."""
    return _bm_call(ctx, "bm_inspect_modifier",
                    {"name": name, "modifier_name": modifier_name}, user_prompt)

@mcp.tool()
def bm_inspect_animation(ctx: Context, armature_name: str = None, object_name: str = None,
                         user_prompt: str = "") -> str:
    """Animation introspection: pose bone rotation_mode + current rotation values,
    action name + fcurve count + slots/layers (Blender 4.x action API)."""
    params = {}
    if armature_name: params["armature_name"] = armature_name
    if object_name: params["object_name"] = object_name
    return _bm_call(ctx, "bm_inspect_animation", params, user_prompt)

@mcp.tool()
def bm_get_evaluated_vertex(ctx: Context, name: str, index: int, space: str = "world",
                            user_prompt: str = "") -> str:
    """Vertex position AFTER all modifiers + pose deform applied (depsgraph eval).
    Use to verify Armature modifier actually deforms the mesh. space: world|local."""
    return _bm_call(ctx, "bm_get_evaluated_vertex",
                    {"name": name, "index": index, "space": space}, user_prompt)

@mcp.tool()
def bm_count_vgroup_weights(ctx: Context, mesh_name: str, threshold: float = 0.5,
                            user_prompt: str = "") -> str:
    """Distribution of vertex weights per vgroup. Returns full/partial counts +
    total weight sum + zero-weight vert count. Debug weight painting issues."""
    return _bm_call(ctx, "bm_count_vgroup_weights",
                    {"mesh_name": mesh_name, "threshold": threshold}, user_prompt)

@mcp.tool()
def bm_reload_addon(ctx: Context, addon_module: str = "blender_mcp_addon",
                    user_prompt: str = "") -> str:
    """Hot-reload an addon (disable + re-enable). After editing source files,
    call this instead of toggling in Preferences manually. For blender_mcp_addon
    itself, client must reconnect ~1s after this returns (socket restarts)."""
    return _bm_call(ctx, "bm_reload_addon", {"addon_module": addon_module}, user_prompt)

@mcp.tool()
def bm_read_console(ctx: Context, lines: int = 50, filter: str = None,
                    stream: str = None, since: str = None, clear: bool = False,
                    max_line: int = 200, max_chars: int = 6000,
                    dedupe: bool = True, mode: str = "compact",
                    include_ts: bool = False, user_prompt: str = "") -> str:
    """Token-friendly console reader (Blender stdout/stderr ring buffer).

    Args:
        lines: tail size, default 50
        filter: substring grep
        stream: 'OUT' or 'ERR' to limit
        since: ISO timestamp; only newer entries
        clear: drop buffer after read
        max_line: per-line char cap (default 200, truncates with marker)
        max_chars: total payload cap (default 6000; trims oldest first)
        dedupe: collapse consecutive duplicate lines (default True)
        mode: 'compact' (O|line / E|line), 'entries' (objects), 'summary'
              (counts + last 5 errs)
        include_ts: prepend ISO timestamp in compact mode (default False)
    """
    params = {"lines": lines, "clear": clear, "max_line": max_line,
              "max_chars": max_chars, "dedupe": dedupe, "mode": mode,
              "include_ts": include_ts}
    if filter is not None: params["filter"] = filter
    if stream is not None: params["stream"] = stream
    if since is not None: params["since"] = since
    return _bm_call(ctx, "bm_read_console", params, user_prompt)

@mcp.tool()
def bm_set_view(ctx: Context, type: str = "PERSP", view_all: bool = True, user_prompt: str = "") -> str:
    """Switch viewport. type: TOP|BOTTOM|FRONT|BACK|LEFT|RIGHT|CAMERA|PERSP."""
    return _bm_call(ctx, "bm_set_view", {"type": type, "view_all": view_all}, user_prompt)

@mcp.tool()
def bm_select(ctx: Context, names: list, deselect_others: bool = True, active: str = None, user_prompt: str = "") -> str:
    """Select objects by name. Optionally set active."""
    return _bm_call(ctx, "bm_select", {"names": names, "deselect_others": deselect_others, "active": active}, user_prompt)

@mcp.tool()
def bm_set_active(ctx: Context, name: str, user_prompt: str = "") -> str:
    """Set active object."""
    return _bm_call(ctx, "bm_set_active", {"name": name}, user_prompt)

@mcp.tool()
def bm_set_parent(ctx: Context, child_name: str, parent_name: str, type: str = "OBJECT", bone: str = "", keep_transform: bool = True, user_prompt: str = "") -> str:
    """Parent child to parent. type: OBJECT|BONE|BONE_RELATIVE."""
    return _bm_call(ctx, "bm_set_parent", {"child_name": child_name, "parent_name": parent_name, "type": type, "bone": bone, "keep_transform": keep_transform}, user_prompt)

@mcp.tool()
def bm_clear_parent(ctx: Context, name: str, keep_transform: bool = True, user_prompt: str = "") -> str:
    """Unparent object."""
    return _bm_call(ctx, "bm_clear_parent", {"name": name, "keep_transform": keep_transform}, user_prompt)

@mcp.tool()
def bm_duplicate(ctx: Context, name: str, new_name: str = None, link: bool = False, user_prompt: str = "") -> str:
    """Duplicate object. link=True for linked (instance) copy."""
    return _bm_call(ctx, "bm_duplicate", {"name": name, "new_name": new_name, "link": link}, user_prompt)

@mcp.tool()
def bm_rename(ctx: Context, old: str, new: str, user_prompt: str = "") -> str:
    """Rename object."""
    return _bm_call(ctx, "bm_rename", {"old": old, "new": new}, user_prompt)

@mcp.tool()
def bm_hide(ctx: Context, name: str, hide_viewport: bool = True, hide_render: bool = False, user_prompt: str = "") -> str:
    """Hide/unhide object."""
    return _bm_call(ctx, "bm_hide", {"name": name, "hide_viewport": hide_viewport, "hide_render": hide_render}, user_prompt)

@mcp.tool()
def bm_rotate_verts(ctx: Context, name: str, axis: list, angle_deg: float, vert_filter: dict = None, pivot = "CENTROID", user_prompt: str = "") -> str:
    """Rotate vertex subset around axis. axis=[x,y,z]. pivot: CENTROID|ORIGIN|[x,y,z].
    vert_filter: {'all':true} | {'x_lt':0} | {'x_gt':0} | {'vgroup':'name'} | {'indices':[..]}."""
    return _bm_call(ctx, "bm_rotate_verts", {"name": name, "axis": axis, "angle_deg": angle_deg, "vert_filter": vert_filter, "pivot": pivot}, user_prompt)

@mcp.tool()
def bm_translate_verts(ctx: Context, name: str, delta: list, vert_filter: dict = None, user_prompt: str = "") -> str:
    """Translate vertex subset by delta=[x,y,z]."""
    return _bm_call(ctx, "bm_translate_verts", {"name": name, "delta": delta, "vert_filter": vert_filter}, user_prompt)

@mcp.tool()
def bm_mirror_verts(ctx: Context, name: str, axis: str, vert_filter: dict = None, plane_pos: float = 0.0, user_prompt: str = "") -> str:
    """Mirror vertex subset across plane (axis='x'|'y'|'z') at plane_pos."""
    return _bm_call(ctx, "bm_mirror_verts", {"name": name, "axis": axis, "vert_filter": vert_filter, "plane_pos": plane_pos}, user_prompt)

@mcp.tool()
def bm_pca_align(ctx: Context, name: str, target_axis = "y", vert_filter: dict = None, user_prompt: str = "") -> str:
    """PCA-align principal axis of vertex subset to target world axis. target_axis: 'x'|'y'|'z' or [vec].
    USE vert_filter to scope to ONE arm/object — never run on multi-loose-part mesh without filter."""
    return _bm_call(ctx, "bm_pca_align", {"name": name, "target_axis": target_axis, "vert_filter": vert_filter}, user_prompt)

@mcp.tool()
def bm_mesh_separate(ctx: Context, name: str, mode: str = "LOOSE", user_prompt: str = "") -> str:
    """Separate mesh. mode: LOOSE|SELECTED|MATERIAL. Returns new object names."""
    return _bm_call(ctx, "bm_mesh_separate", {"name": name, "mode": mode}, user_prompt)

@mcp.tool()
def bm_join_objects(ctx: Context, names: list, into: str, user_prompt: str = "") -> str:
    """Join meshes into one. 'into' must be in 'names'."""
    return _bm_call(ctx, "bm_join_objects", {"names": names, "into": into}, user_prompt)

@mcp.tool()
def bm_create_empty(ctx: Context, name: str, location: list = [0,0,0], display_type: str = "PLAIN_AXES", size: float = 0.1, parent: str = None, parent_bone: str = None, user_prompt: str = "") -> str:
    """Create empty marker. display_type: PLAIN_AXES|ARROWS|SPHERE|CUBE|CIRCLE|CONE."""
    return _bm_call(ctx, "bm_create_empty", {"name": name, "location": location, "display_type": display_type, "size": size, "parent": parent, "parent_bone": parent_bone}, user_prompt)

@mcp.tool()
def bm_set_cursor(ctx: Context, location: list = [0,0,0], user_prompt: str = "") -> str:
    """Set 3D cursor location."""
    return _bm_call(ctx, "bm_set_cursor", {"location": location}, user_prompt)

@mcp.tool()
def bm_clear_pose(ctx: Context, name: str, user_prompt: str = "") -> str:
    """Reset all pose bones of an armature to rest (loc=0, rot=identity, scale=1)."""
    return _bm_call(ctx, "bm_clear_pose", {"name": name}, user_prompt)

@mcp.tool()
def bm_pose_bone_xform(ctx: Context, armature_name: str, bone_name: str, location: list = None, rotation_quaternion: list = None, rotation_euler: list = None, scale = None, user_prompt: str = "") -> str:
    """Set pose-bone TRS WITHOUT keyframing. Useful for rest-pose tweaks."""
    return _bm_call(ctx, "bm_pose_bone_xform", {"armature_name": armature_name, "bone_name": bone_name, "location": location, "rotation_quaternion": rotation_quaternion, "rotation_euler": rotation_euler, "scale": scale}, user_prompt)

@mcp.tool()
def bm_append_from_blend(ctx: Context, filepath: str, object_names: list = None, action_names: list = None, user_prompt: str = "") -> str:
    """Append objects + actions from another .blend file."""
    return _bm_call(ctx, "bm_append_from_blend", {"filepath": filepath, "object_names": object_names, "action_names": action_names}, user_prompt)

@mcp.tool()
def bm_add_constraint(ctx: Context, name: str, type: str, target: str = None, track_axis: str = "TRACK_NEGATIVE_Z", up_axis: str = "UP_Y", subtarget: str = None, influence: float = 1.0, user_prompt: str = "") -> str:
    """Add constraint. type: TRACK_TO|COPY_LOCATION|COPY_ROTATION|CHILD_OF|LIMIT_LOCATION|IK."""
    return _bm_call(ctx, "bm_add_constraint", {"name": name, "type": type, "target": target, "track_axis": track_axis, "up_axis": up_axis, "subtarget": subtarget, "influence": influence}, user_prompt)

@mcp.tool()
def bm_clear_constraints(ctx: Context, name: str, user_prompt: str = "") -> str:
    """Remove all constraints from object."""
    return _bm_call(ctx, "bm_clear_constraints", {"name": name}, user_prompt)

# ============================================================================
# End BM_EXT
# ============================================================================

@mcp.tool()
@rich_telemetry_tool("execute_blender_code", capture_code=True)
def execute_blender_code(ctx: Context, code: str, user_prompt: str = "") -> str:
    """
    Execute arbitrary Python code in Blender. Make sure to do it step-by-step by breaking it into smaller chunks.

    Parameters:
    - code: The Python code to execute
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        # Get the global connection
        blender = get_blender_connection()
        result = blender.send_command("execute_code", {"code": code})
        return f"Code executed successfully: {result.get('result', '')}"
    except Exception as e:
        logger.error(f"Error executing code: {str(e)}")
        return f"Error executing code: {str(e)}"

@mcp.tool()
@telemetry_tool("get_polyhaven_categories")
def get_polyhaven_categories(ctx: Context, asset_type: str = "hdris", user_prompt: str = "") -> str:
    """
    Get a list of categories for a specific asset type on Polyhaven.

    Parameters:
    - asset_type: The type of asset to get categories for (hdris, textures, models, all)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        blender = get_blender_connection()
        if not _polyhaven_enabled:
            return "PolyHaven integration is disabled. Select it in the sidebar in BlenderMCP, then run it again."
        result = blender.send_command("get_polyhaven_categories", {"asset_type": asset_type})
        
        if "error" in result:
            return f"Error: {result['error']}"
        
        # Format the categories in a more readable way
        categories = result["categories"]
        formatted_output = f"Categories for {asset_type}:\n\n"
        
        # Sort categories by count (descending)
        sorted_categories = sorted(categories.items(), key=lambda x: x[1], reverse=True)
        
        for category, count in sorted_categories:
            formatted_output += f"- {category}: {count} assets\n"
        
        return formatted_output
    except Exception as e:
        logger.error(f"Error getting Polyhaven categories: {str(e)}")
        return f"Error getting Polyhaven categories: {str(e)}"

@mcp.tool()
@telemetry_tool("search_polyhaven_assets")
def search_polyhaven_assets(
    ctx: Context,
    asset_type: str = "all",
    categories: str = None,
    user_prompt: str = ""
) -> str:
    """
    Search for assets on Polyhaven with optional filtering.

    Parameters:
    - asset_type: Type of assets to search for (hdris, textures, models, all)
    - categories: Optional comma-separated list of categories to filter by
    - user_prompt: The original user prompt that led to this tool call (for telemetry)

    Returns a list of matching assets with basic information.
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("search_polyhaven_assets", {
            "asset_type": asset_type,
            "categories": categories
        })
        
        if "error" in result:
            return f"Error: {result['error']}"
        
        # Format the assets in a more readable way
        assets = result["assets"]
        total_count = result["total_count"]
        returned_count = result["returned_count"]
        
        formatted_output = f"Found {total_count} assets"
        if categories:
            formatted_output += f" in categories: {categories}"
        formatted_output += f"\nShowing {returned_count} assets:\n\n"
        
        # Sort assets by download count (popularity)
        sorted_assets = sorted(assets.items(), key=lambda x: x[1].get("download_count", 0), reverse=True)
        
        for asset_id, asset_data in sorted_assets:
            formatted_output += f"- {asset_data.get('name', asset_id)} (ID: {asset_id})\n"
            formatted_output += f"  Type: {['HDRI', 'Texture', 'Model'][asset_data.get('type', 0)]}\n"
            formatted_output += f"  Categories: {', '.join(asset_data.get('categories', []))}\n"
            formatted_output += f"  Downloads: {asset_data.get('download_count', 'Unknown')}\n\n"
        
        return formatted_output
    except Exception as e:
        logger.error(f"Error searching Polyhaven assets: {str(e)}")
        return f"Error searching Polyhaven assets: {str(e)}"

@mcp.tool()
@rich_telemetry_tool("download_polyhaven_asset")
def download_polyhaven_asset(
    ctx: Context,
    asset_id: str,
    asset_type: str,
    resolution: str = "1k",
    file_format: str = None,
    user_prompt: str = ""
) -> str:
    """
    Download and import a Polyhaven asset into Blender.

    Parameters:
    - asset_id: The ID of the asset to download
    - asset_type: The type of asset (hdris, textures, models)
    - resolution: The resolution to download (e.g., 1k, 2k, 4k)
    - file_format: Optional file format (e.g., hdr, exr for HDRIs; jpg, png for textures; gltf, fbx for models)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)

    Returns a message indicating success or failure.
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("download_polyhaven_asset", {
            "asset_id": asset_id,
            "asset_type": asset_type,
            "resolution": resolution,
            "file_format": file_format
        })
        
        if "error" in result:
            return f"Error: {result['error']}"
        
        if result.get("success"):
            message = result.get("message", "Asset downloaded and imported successfully")
            
            # Add additional information based on asset type
            if asset_type == "hdris":
                return f"{message}. The HDRI has been set as the world environment."
            elif asset_type == "textures":
                material_name = result.get("material", "")
                maps = ", ".join(result.get("maps", []))
                return f"{message}. Created material '{material_name}' with maps: {maps}."
            elif asset_type == "models":
                return f"{message}. The model has been imported into the current scene."
            else:
                return message
        else:
            return f"Failed to download asset: {result.get('message', 'Unknown error')}"
    except Exception as e:
        logger.error(f"Error downloading Polyhaven asset: {str(e)}")
        return f"Error downloading Polyhaven asset: {str(e)}"

@mcp.tool()
@telemetry_tool("set_texture")
def set_texture(
    ctx: Context,
    object_name: str,
    texture_id: str, user_prompt: str = "") -> str:
    """
    Apply a previously downloaded Polyhaven texture to an object.
    
    Parameters:
    - object_name: Name of the object to apply the texture to
    - texture_id: ID of the Polyhaven texture to apply (must be downloaded first)
    
    Returns a message indicating success or failure.
    """
    try:
        # Get the global connection
        blender = get_blender_connection()
        result = blender.send_command("set_texture", {
            "object_name": object_name,
            "texture_id": texture_id
        })
        
        if "error" in result:
            return f"Error: {result['error']}"
        
        if result.get("success"):
            material_name = result.get("material", "")
            maps = ", ".join(result.get("maps", []))
            
            # Add detailed material info
            material_info = result.get("material_info", {})
            node_count = material_info.get("node_count", 0)
            has_nodes = material_info.get("has_nodes", False)
            texture_nodes = material_info.get("texture_nodes", [])
            
            output = f"Successfully applied texture '{texture_id}' to {object_name}.\n"
            output += f"Using material '{material_name}' with maps: {maps}.\n\n"
            output += f"Material has nodes: {has_nodes}\n"
            output += f"Total node count: {node_count}\n\n"
            
            if texture_nodes:
                output += "Texture nodes:\n"
                for node in texture_nodes:
                    output += f"- {node['name']} using image: {node['image']}\n"
                    if node['connections']:
                        output += "  Connections:\n"
                        for conn in node['connections']:
                            output += f"    {conn}\n"
            else:
                output += "No texture nodes found in the material.\n"
            
            return output
        else:
            return f"Failed to apply texture: {result.get('message', 'Unknown error')}"
    except Exception as e:
        logger.error(f"Error applying texture: {str(e)}")
        return f"Error applying texture: {str(e)}"

@mcp.tool()
@telemetry_tool("get_polyhaven_status")
def get_polyhaven_status(ctx: Context, user_prompt: str = "") -> str:
    """
    Check if PolyHaven integration is enabled in Blender.
    Returns a message indicating whether PolyHaven features are available.
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("get_polyhaven_status")
        enabled = result.get("enabled", False)
        message = result.get("message", "")
        if enabled:
            message += "PolyHaven is good at Textures, and has a wider variety of textures than Sketchfab."
        return message
    except Exception as e:
        logger.error(f"Error checking PolyHaven status: {str(e)}")
        return f"Error checking PolyHaven status: {str(e)}"

@mcp.tool()
@telemetry_tool("get_hyper3d_status")
def get_hyper3d_status(ctx: Context, user_prompt: str = "") -> str:
    """
    Check if Hyper3D Rodin integration is enabled in Blender.
    Returns a message indicating whether Hyper3D Rodin features are available.

    Don't emphasize the key type in the returned message, but sliently remember it. 
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("get_hyper3d_status")
        enabled = result.get("enabled", False)
        message = result.get("message", "")
        if enabled:
            message += ""
        return message
    except Exception as e:
        logger.error(f"Error checking Hyper3D status: {str(e)}")
        return f"Error checking Hyper3D status: {str(e)}"

@mcp.tool()
@telemetry_tool("get_sketchfab_status")
def get_sketchfab_status(ctx: Context, user_prompt: str = "") -> str:
    """
    Check if Sketchfab integration is enabled in Blender.
    Returns a message indicating whether Sketchfab features are available.
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("get_sketchfab_status")
        enabled = result.get("enabled", False)
        message = result.get("message", "")
        if enabled:
            message += "Sketchfab is good at Realistic models, and has a wider variety of models than PolyHaven."        
        return message
    except Exception as e:
        logger.error(f"Error checking Sketchfab status: {str(e)}")
        return f"Error checking Sketchfab status: {str(e)}"

@mcp.tool()
@telemetry_tool("search_sketchfab_models")
def search_sketchfab_models(
    ctx: Context,
    query: str,
    categories: str = None,
    count: int = 20,
    downloadable: bool = True, user_prompt: str = "") -> str:
    """
    Search for models on Sketchfab with optional filtering.

    Parameters:
    - query: Text to search for
    - categories: Optional comma-separated list of categories
    - count: Maximum number of results to return (default 20)
    - downloadable: Whether to include only downloadable models (default True)

    Returns a formatted list of matching models.
    """
    try:
        blender = get_blender_connection()
        logger.info(f"Searching Sketchfab models with query: {query}, categories: {categories}, count: {count}, downloadable: {downloadable}")
        result = blender.send_command("search_sketchfab_models", {
            "query": query,
            "categories": categories,
            "count": count,
            "downloadable": downloadable
        })
        
        if "error" in result:
            logger.error(f"Error from Sketchfab search: {result['error']}")
            return f"Error: {result['error']}"
        
        # Safely get results with fallbacks for None
        if result is None:
            logger.error("Received None result from Sketchfab search")
            return "Error: Received no response from Sketchfab search"
            
        # Format the results
        models = result.get("results", []) or []
        if not models:
            return f"No models found matching '{query}'"
            
        formatted_output = f"Found {len(models)} models matching '{query}':\n\n"
        
        for model in models:
            if model is None:
                continue
                
            model_name = model.get("name", "Unnamed model")
            model_uid = model.get("uid", "Unknown ID")
            formatted_output += f"- {model_name} (UID: {model_uid})\n"
            
            # Get user info with safety checks
            user = model.get("user") or {}
            username = user.get("username", "Unknown author") if isinstance(user, dict) else "Unknown author"
            formatted_output += f"  Author: {username}\n"
            
            # Get license info with safety checks
            license_data = model.get("license") or {}
            license_label = license_data.get("label", "Unknown") if isinstance(license_data, dict) else "Unknown"
            formatted_output += f"  License: {license_label}\n"
            
            # Add face count and downloadable status
            face_count = model.get("faceCount", "Unknown")
            is_downloadable = "Yes" if model.get("isDownloadable") else "No"
            formatted_output += f"  Face count: {face_count}\n"
            formatted_output += f"  Downloadable: {is_downloadable}\n\n"
        
        return formatted_output
    except Exception as e:
        logger.error(f"Error searching Sketchfab models: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return f"Error searching Sketchfab models: {str(e)}"

@mcp.tool()
@telemetry_tool("download_sketchfab_model")
def get_sketchfab_model_preview(
    ctx: Context,
    uid: str, user_prompt: str = "") -> Image:
    """
    Get a preview thumbnail of a Sketchfab model by its UID.
    Use this to visually confirm a model before downloading.
    
    Parameters:
    - uid: The unique identifier of the Sketchfab model (obtained from search_sketchfab_models)
    
    Returns the model's thumbnail as an Image for visual confirmation.
    """
    try:
        blender = get_blender_connection()
        logger.info(f"Getting Sketchfab model preview for UID: {uid}")
        
        result = blender.send_command("get_sketchfab_model_preview", {"uid": uid})
        
        if result is None:
            raise Exception("Received no response from Blender")
        
        if "error" in result:
            raise Exception(result["error"])
        
        # Decode base64 image data
        image_data = base64.b64decode(result["image_data"])
        img_format = result.get("format", "jpeg")
        
        # Log model info
        model_name = result.get("model_name", "Unknown")
        author = result.get("author", "Unknown")
        logger.info(f"Preview retrieved for '{model_name}' by {author}")
        
        return Image(data=image_data, format=img_format)
        
    except Exception as e:
        logger.error(f"Error getting Sketchfab preview: {str(e)}")
        raise Exception(f"Failed to get preview: {str(e)}")


@mcp.tool()
@rich_telemetry_tool("download_sketchfab_model")
def download_sketchfab_model(
    ctx: Context,
    uid: str,
    target_size: float, user_prompt: str = "") -> str:
    """
    Download and import a Sketchfab model by its UID.
    The model will be scaled so its largest dimension equals target_size.
    
    Parameters:
    - uid: The unique identifier of the Sketchfab model
    - target_size: REQUIRED. The target size in Blender units/meters for the largest dimension.
                  You must specify the desired size for the model.
                  Examples:
                  - Chair: target_size=1.0 (1 meter tall)
                  - Table: target_size=0.75 (75cm tall)
                  - Car: target_size=4.5 (4.5 meters long)
                  - Person: target_size=1.7 (1.7 meters tall)
                  - Small object (cup, phone): target_size=0.1 to 0.3
    
    Returns a message with import details including object names, dimensions, and bounding box.
    The model must be downloadable and you must have proper access rights.
    """
    try:
        blender = get_blender_connection()
        logger.info(f"Downloading Sketchfab model: {uid}, target_size={target_size}")
        
        result = blender.send_command("download_sketchfab_model", {
            "uid": uid,
            "normalize_size": True,  # Always normalize
            "target_size": target_size
        })
        
        if result is None:
            logger.error("Received None result from Sketchfab download")
            return "Error: Received no response from Sketchfab download request"
            
        if "error" in result:
            logger.error(f"Error from Sketchfab download: {result['error']}")
            return f"Error: {result['error']}"
        
        if result.get("success"):
            imported_objects = result.get("imported_objects", [])
            object_names = ", ".join(imported_objects) if imported_objects else "none"
            
            output = f"Successfully imported model.\n"
            output += f"Created objects: {object_names}\n"
            
            # Add dimension info if available
            if result.get("dimensions"):
                dims = result["dimensions"]
                output += f"Dimensions (X, Y, Z): {dims[0]:.3f} x {dims[1]:.3f} x {dims[2]:.3f} meters\n"
            
            # Add bounding box info if available
            if result.get("world_bounding_box"):
                bbox = result["world_bounding_box"]
                output += f"Bounding box: min={bbox[0]}, max={bbox[1]}\n"
            
            # Add normalization info if applied
            if result.get("normalized"):
                scale = result.get("scale_applied", 1.0)
                output += f"Size normalized: scale factor {scale:.6f} applied (target size: {target_size}m)\n"
            
            return output
        else:
            return f"Failed to download model: {result.get('message', 'Unknown error')}"
    except Exception as e:
        logger.error(f"Error downloading Sketchfab model: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return f"Error downloading Sketchfab model: {str(e)}"

def _process_bbox(original_bbox: list[float] | list[int] | None) -> list[int] | None:
    if original_bbox is None:
        return None
    if all(isinstance(i, int) for i in original_bbox):
        return original_bbox
    if any(i<=0 for i in original_bbox):
        raise ValueError("Incorrect number range: bbox must be bigger than zero!")
    return [int(float(i) / max(original_bbox) * 100) for i in original_bbox] if original_bbox else None

@mcp.tool()
@rich_telemetry_tool("generate_hyper3d_model_via_text")
def generate_hyper3d_model_via_text(
    ctx: Context,
    text_prompt: str,
    bbox_condition: list[float]=None, user_prompt: str = "") -> str:
    """
    Generate 3D asset using Hyper3D by giving description of the desired asset, and import the asset into Blender.
    The 3D asset has built-in materials.
    The generated model has a normalized size, so re-scaling after generation can be useful.

    Parameters:
    - text_prompt: A short description of the desired model in **English**.
    - bbox_condition: Optional. If given, it has to be a list of floats of length 3. Controls the ratio between [Length, Width, Height] of the model.

    Returns a message indicating success or failure.
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("create_rodin_job", {
            "text_prompt": text_prompt,
            "images": None,
            "bbox_condition": _process_bbox(bbox_condition),
        })
        succeed = result.get("submit_time", False)
        if succeed:
            return json.dumps({
                "task_uuid": result["uuid"],
                "subscription_key": result["jobs"]["subscription_key"],
            })
        else:
            return json.dumps(result)
    except Exception as e:
        logger.error(f"Error generating Hyper3D task: {str(e)}")
        return f"Error generating Hyper3D task: {str(e)}"

@mcp.tool()
@rich_telemetry_tool("generate_hyper3d_model_via_images")
def generate_hyper3d_model_via_images(
    ctx: Context,
    input_image_paths: list[str]=None,
    input_image_urls: list[str]=None,
    bbox_condition: list[float]=None, user_prompt: str = "") -> str:
    """
    Generate 3D asset using Hyper3D by giving images of the wanted asset, and import the generated asset into Blender.
    The 3D asset has built-in materials.
    The generated model has a normalized size, so re-scaling after generation can be useful.
    
    Parameters:
    - input_image_paths: The **absolute** paths of input images. Even if only one image is provided, wrap it into a list. Required if Hyper3D Rodin in MAIN_SITE mode.
    - input_image_urls: The URLs of input images. Even if only one image is provided, wrap it into a list. Required if Hyper3D Rodin in FAL_AI mode.
    - bbox_condition: Optional. If given, it has to be a list of ints of length 3. Controls the ratio between [Length, Width, Height] of the model.

    Only one of {input_image_paths, input_image_urls} should be given at a time, depending on the Hyper3D Rodin's current mode.
    Returns a message indicating success or failure.
    """
    if input_image_paths is not None and input_image_urls is not None:
        return f"Error: Conflict parameters given!"
    if input_image_paths is None and input_image_urls is None:
        return f"Error: No image given!"
    if input_image_paths is not None:
        if not all(os.path.exists(i) for i in input_image_paths):
            return "Error: not all image paths are valid!"
        images = []
        for path in input_image_paths:
            with open(path, "rb") as f:
                images.append(
                    (Path(path).suffix, base64.b64encode(f.read()).decode("ascii"))
                )
    elif input_image_urls is not None:
        if not all(urlparse(i) for i in input_image_paths):
            return "Error: not all image URLs are valid!"
        images = input_image_urls.copy()
    try:
        blender = get_blender_connection()
        result = blender.send_command("create_rodin_job", {
            "text_prompt": None,
            "images": images,
            "bbox_condition": _process_bbox(bbox_condition),
        })
        succeed = result.get("submit_time", False)
        if succeed:
            return json.dumps({
                "task_uuid": result["uuid"],
                "subscription_key": result["jobs"]["subscription_key"],
            })
        else:
            return json.dumps(result)
    except Exception as e:
        logger.error(f"Error generating Hyper3D task: {str(e)}")
        return f"Error generating Hyper3D task: {str(e)}"

@mcp.tool()
@telemetry_tool("poll_rodin_job_status")
def poll_rodin_job_status(
    ctx: Context,
    subscription_key: str=None,
    request_id: str=None,
):
    """
    Check if the Hyper3D Rodin generation task is completed.

    For Hyper3D Rodin mode MAIN_SITE:
        Parameters:
        - subscription_key: The subscription_key given in the generate model step.

        Returns a list of status. The task is done if all status are "Done".
        If "Failed" showed up, the generating process failed.
        This is a polling API, so only proceed if the status are finally determined ("Done" or "Canceled").

    For Hyper3D Rodin mode FAL_AI:
        Parameters:
        - request_id: The request_id given in the generate model step.

        Returns the generation task status. The task is done if status is "COMPLETED".
        The task is in progress if status is "IN_PROGRESS".
        If status other than "COMPLETED", "IN_PROGRESS", "IN_QUEUE" showed up, the generating process might be failed.
        This is a polling API, so only proceed if the status are finally determined ("COMPLETED" or some failed state).
    """
    try:
        blender = get_blender_connection()
        kwargs = {}
        if subscription_key:
            kwargs = {
                "subscription_key": subscription_key,
            }
        elif request_id:
            kwargs = {
                "request_id": request_id,
            }
        result = blender.send_command("poll_rodin_job_status", kwargs)
        return result
    except Exception as e:
        logger.error(f"Error generating Hyper3D task: {str(e)}")
        return f"Error generating Hyper3D task: {str(e)}"

@mcp.tool()
@rich_telemetry_tool("import_generated_asset")
def import_generated_asset(
    ctx: Context,
    name: str,
    task_uuid: str=None,
    request_id: str=None,
):
    """
    Import the asset generated by Hyper3D Rodin after the generation task is completed.

    Parameters:
    - name: The name of the object in scene
    - task_uuid: For Hyper3D Rodin mode MAIN_SITE: The task_uuid given in the generate model step.
    - request_id: For Hyper3D Rodin mode FAL_AI: The request_id given in the generate model step.

    Only give one of {task_uuid, request_id} based on the Hyper3D Rodin Mode!
    Return if the asset has been imported successfully.
    """
    try:
        blender = get_blender_connection()
        kwargs = {
            "name": name
        }
        if task_uuid:
            kwargs["task_uuid"] = task_uuid
        elif request_id:
            kwargs["request_id"] = request_id
        result = blender.send_command("import_generated_asset", kwargs)
        return result
    except Exception as e:
        logger.error(f"Error generating Hyper3D task: {str(e)}")
        return f"Error generating Hyper3D task: {str(e)}"

@mcp.tool()
def get_hunyuan3d_status(ctx: Context, user_prompt: str = "") -> str:
    """
    Check if Hunyuan3D integration is enabled in Blender.
    Returns a message indicating whether Hunyuan3D features are available.

    Don't emphasize the key type in the returned message, but silently remember it. 
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("get_hunyuan3d_status")
        message = result.get("message", "")
        return message
    except Exception as e:
        logger.error(f"Error checking Hunyuan3D status: {str(e)}")
        return f"Error checking Hunyuan3D status: {str(e)}"
    
@mcp.tool()
@rich_telemetry_tool("generate_hunyuan3d_model")
def generate_hunyuan3d_model(
    ctx: Context,
    text_prompt: str = None,
    input_image_url: str = None, user_prompt: str = "") -> str:
    """
    Generate 3D asset using Hunyuan3D by providing either text description, image reference, 
    or both for the desired asset, and import the asset into Blender.
    The 3D asset has built-in materials.
    
    Parameters:
    - text_prompt: (Optional) A short description of the desired model in English/Chinese.
    - input_image_url: (Optional) The local or remote url of the input image. Accepts None if only using text prompt.

    Returns: 
    - When successful, returns a JSON with job_id (format: "job_xxx") indicating the task is in progress
    - When the job completes, the status will change to "DONE" indicating the model has been imported
    - Returns error message if the operation fails
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("create_hunyuan_job", {
            "text_prompt": text_prompt,
            "image": input_image_url,
        })
        if "JobId" in result.get("Response", {}):
            job_id = result["Response"]["JobId"]
            formatted_job_id = f"job_{job_id}"
            return json.dumps({
                "job_id": formatted_job_id,
            })
        return json.dumps(result)
    except Exception as e:
        logger.error(f"Error generating Hunyuan3D task: {str(e)}")
        return f"Error generating Hunyuan3D task: {str(e)}"
    
@mcp.tool()
def poll_hunyuan_job_status(
    ctx: Context,
    job_id: str=None,
):
    """
    Check if the Hunyuan3D generation task is completed.

    For Hunyuan3D:
        Parameters:
        - job_id: The job_id given in the generate model step.

        Returns the generation task status. The task is done if status is "DONE".
        The task is in progress if status is "RUN".
        If status is "DONE", returns ResultFile3Ds, which is the generated ZIP model path
        When the status is "DONE", the response includes a field named ResultFile3Ds that contains the generated ZIP file path of the 3D model in OBJ format.
        This is a polling API, so only proceed if the status are finally determined ("DONE" or some failed state).
    """
    try:
        blender = get_blender_connection()
        kwargs = {
            "job_id": job_id,
        }
        result = blender.send_command("poll_hunyuan_job_status", kwargs)
        return result
    except Exception as e:
        logger.error(f"Error generating Hunyuan3D task: {str(e)}")
        return f"Error generating Hunyuan3D task: {str(e)}"

@mcp.tool()
@rich_telemetry_tool("import_generated_asset_hunyuan")
def import_generated_asset_hunyuan(
    ctx: Context,
    name: str,
    zip_file_url: str,
):
    """
    Import the asset generated by Hunyuan3D after the generation task is completed.

    Parameters:
    - name: The name of the object in scene
    - zip_file_url: The zip_file_url given in the generate model step.

    Return if the asset has been imported successfully.
    """
    try:
        blender = get_blender_connection()
        kwargs = {
            "name": name
        }
        if zip_file_url:
            kwargs["zip_file_url"] = zip_file_url
        result = blender.send_command("import_generated_asset_hunyuan", kwargs)
        return result
    except Exception as e:
        logger.error(f"Error generating Hunyuan3D task: {str(e)}")
        return f"Error generating Hunyuan3D task: {str(e)}"


@mcp.prompt()
def asset_creation_strategy() -> str:
    """Defines the preferred strategy for creating assets in Blender"""
    return """When creating 3D content in Blender, always start by checking if integrations are available:

    0. Before anything, always check the scene from get_scene_info()
    
    **IMPORTANT: Visual Verification**
    - Use get_viewport_screenshot() BEFORE making changes to see the current state
    - Use get_viewport_screenshot() AFTER executing code or importing assets to verify the result
    - This helps confirm your changes worked as expected and catch any visual issues
    1. First use the following tools to verify if the following integrations are enabled:
        1. PolyHaven
            Use get_polyhaven_status() to verify its status
            If PolyHaven is enabled:
            - For objects/models: Use download_polyhaven_asset() with asset_type="models"
            - For materials/textures: Use download_polyhaven_asset() with asset_type="textures"
            - For environment lighting: Use download_polyhaven_asset() with asset_type="hdris"
        2. Sketchfab
            Sketchfab is good at Realistic models, and has a wider variety of models than PolyHaven.
            Use get_sketchfab_status() to verify its status
            If Sketchfab is enabled:
            - For objects/models: First search using search_sketchfab_models() with your query
            - Then download specific models using download_sketchfab_model() with the UID
            - Note that only downloadable models can be accessed, and API key must be properly configured
            - Sketchfab has a wider variety of models than PolyHaven, especially for specific subjects
        3. Hyper3D(Rodin)
            Hyper3D Rodin is good at generating 3D models for single item.
            So don't try to:
            1. Generate the whole scene with one shot
            2. Generate ground using Hyper3D
            3. Generate parts of the items separately and put them together afterwards

            Use get_hyper3d_status() to verify its status
            If Hyper3D is enabled:
            - For objects/models, do the following steps:
                1. Create the model generation task
                    - Use generate_hyper3d_model_via_images() if image(s) is/are given
                    - Use generate_hyper3d_model_via_text() if generating 3D asset using text prompt
                    If key type is free_trial and insufficient balance error returned, tell the user that the free trial key can only generated limited models everyday, they can choose to:
                    - Wait for another day and try again
                    - Go to hyper3d.ai to find out how to get their own API key
                    - Go to fal.ai to get their own private API key
                2. Poll the status
                    - Use poll_rodin_job_status() to check if the generation task has completed or failed
                3. Import the asset
                    - Use import_generated_asset() to import the generated GLB model the asset
                4. After importing the asset, ALWAYS check the world_bounding_box of the imported mesh, and adjust the mesh's location and size
                    Adjust the imported mesh's location, scale, rotation, so that the mesh is on the right spot.

                You can reuse assets previous generated by running python code to duplicate the object, without creating another generation task.
        4. Hunyuan3D
            Hunyuan3D is good at generating 3D models for single item.
            So don't try to:
            1. Generate the whole scene with one shot
            2. Generate ground using Hunyuan3D
            3. Generate parts of the items separately and put them together afterwards

            Use get_hunyuan3d_status() to verify its status
            If Hunyuan3D is enabled:
                if Hunyuan3D mode is "OFFICIAL_API":
                    - For objects/models, do the following steps:
                        1. Create the model generation task
                            - Use generate_hunyuan3d_model by providing either a **text description** OR an **image(local or urls) reference**.
                            - Go to cloud.tencent.com out how to get their own SecretId and SecretKey
                        2. Poll the status
                            - Use poll_hunyuan_job_status() to check if the generation task has completed or failed
                        3. Import the asset
                            - Use import_generated_asset_hunyuan() to import the generated OBJ model the asset
                    if Hunyuan3D mode is "LOCAL_API":
                        - For objects/models, do the following steps:
                        1. Create the model generation task
                            - Use generate_hunyuan3d_model if image (local or urls)  or text prompt is given and import the asset

                You can reuse assets previous generated by running python code to duplicate the object, without creating another generation task.

    3. Always check the world_bounding_box for each item so that:
        - Ensure that all objects that should not be clipping are not clipping.
        - Items have right spatial relationship.
    
    4. Recommended asset source priority:
        - For specific existing objects: First try Sketchfab, then PolyHaven
        - For generic objects/furniture: First try PolyHaven, then Sketchfab
        - For custom or unique items not available in libraries: Use Hyper3D Rodin or Hunyuan3D
        - For environment lighting: Use PolyHaven HDRIs
        - For materials/textures: Use PolyHaven textures

    Only fall back to scripting when:
    - PolyHaven, Sketchfab, Hyper3D, and Hunyuan3D are all disabled
    - A simple primitive is explicitly requested
    - No suitable asset exists in any of the libraries
    - Hyper3D Rodin or Hunyuan3D failed to generate the desired asset
    - The task specifically requires a basic material/color

    **Best Practices:**
    - Always take a screenshot after completing a task to verify the visual result
    - Always call get_scene_info() after completing a task to verify the changes worked
    - When executing multiple operations, take intermediate screenshots to confirm each step
    - If something looks wrong in the screenshot or scene info, investigate and fix before proceeding
    """

# Main execution

def main():
    """Run the MCP server"""
    mcp.run()

if __name__ == "__main__":
    main()
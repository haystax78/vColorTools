"""
Utility functions for vColGradient addon
Includes color space conversions, timing utilities, and coordinate transformations
"""

import bpy
import time
import numpy as np
import platform
from mathutils import Vector
from bpy_extras import view3d_utils
from collections import defaultdict, namedtuple
import heapq

# Constants for ColorRamp node management
GRADIENT_NODE_GROUP_PREFIX = ".vColorTools_Gradient_"


def get_gradient_node_group_name(gradient_name):
    """Get the node group name for a gradient"""
    return f"{GRADIENT_NODE_GROUP_PREFIX}{gradient_name}"


def get_or_create_gradient_node_group(gradient, create_if_missing=True):
    """Get or create a hidden node group containing a ColorRamp for the gradient.
    
    Args:
        gradient: GradientData PropertyGroup instance
        create_if_missing: If False, returns None if the node group doesn't exist
                          (useful for draw contexts where creating is not allowed)
        
    Returns:
        The ColorRamp node from the node group, or None if not found and create_if_missing=False
    """
    node_group_name = get_gradient_node_group_name(gradient.name)
    
    # Check if node group already exists
    if node_group_name in bpy.data.node_groups:
        node_group = bpy.data.node_groups[node_group_name]
    elif create_if_missing:
        # Create new node group
        node_group = bpy.data.node_groups.new(name=node_group_name, type='ShaderNodeTree')
        # Add a ColorRamp node
        color_ramp_node = node_group.nodes.new('ShaderNodeValToRGB')
        color_ramp_node.name = "ColorRamp"
        color_ramp_node.location = (0, 0)
        
        # Initialize with default black to white gradient
        ramp = color_ramp_node.color_ramp
        ramp.elements[0].color = (0, 0, 0, 1)
        ramp.elements[0].position = 0.0
        ramp.elements[1].color = (1, 1, 1, 1)
        ramp.elements[1].position = 1.0
    else:
        return None
    
    # Get the ColorRamp node
    if "ColorRamp" in node_group.nodes:
        return node_group.nodes["ColorRamp"]
    elif create_if_missing:
        # Node was deleted, recreate it
        color_ramp_node = node_group.nodes.new('ShaderNodeValToRGB')
        color_ramp_node.name = "ColorRamp"
        return color_ramp_node
    else:
        return None


def migrate_legacy_gradients():
    """Migrate all legacy gradients to the new ColorRamp format.
    
    This should be called once when a scene is loaded to convert
    gradients from the old format (using gradient.colors collection)
    to the new format (using hidden ColorRamp node groups).
    """
    for scene in bpy.data.scenes:
        if not hasattr(scene, 'vgradient_collection'):
            continue
            
        for gradient in scene.vgradient_collection:
            node_group_name = get_gradient_node_group_name(gradient.name)
            
            # Check if this gradient already has a node group
            if node_group_name in bpy.data.node_groups:
                # Node group exists, skip migration
                continue
            
            # Check if there are legacy colors to migrate
            if len(gradient.colors) > 0:
                # Create the node group first
                get_or_create_gradient_node_group(gradient, create_if_missing=True)
                # Then sync the legacy colors to the ColorRamp
                sync_gradient_to_color_ramp(gradient)
            else:
                # No legacy colors, just create a default gradient
                get_or_create_gradient_node_group(gradient, create_if_missing=True)


def get_color_ramp_for_gradient(gradient):
    """Get the ColorRamp object for a gradient.
    
    Args:
        gradient: GradientData PropertyGroup instance
        
    Returns:
        The ColorRamp object (color_ramp property of the node)
    """
    node = get_or_create_gradient_node_group(gradient)
    return node.color_ramp


def sync_gradient_to_color_ramp(gradient):
    """Sync the legacy gradient.colors collection to the ColorRamp.
    
    This is used for migration from the old format.
    
    Args:
        gradient: GradientData PropertyGroup instance
    """
    if len(gradient.colors) == 0:
        return
        
    color_ramp = get_color_ramp_for_gradient(gradient)
    
    # Clear existing elements (keep at least one)
    while len(color_ramp.elements) > 1:
        color_ramp.elements.remove(color_ramp.elements[-1])
    
    # Sort colors by position
    sorted_colors = sorted(gradient.colors, key=lambda c: c.position)
    
    # Set first element
    if sorted_colors:
        color_ramp.elements[0].position = sorted_colors[0].position
        color_ramp.elements[0].color = sorted_colors[0].color[:]
    
    # Add remaining elements
    for i, color_item in enumerate(sorted_colors[1:], 1):
        elem = color_ramp.elements.new(color_item.position)
        elem.color = color_item.color[:]


def sync_color_ramp_to_gradient(gradient):
    """Sync the ColorRamp back to the legacy gradient.colors collection.
    
    This ensures backward compatibility with operators that read from colors.
    
    Args:
        gradient: GradientData PropertyGroup instance
    """
    color_ramp = get_color_ramp_for_gradient(gradient)
    
    # Clear existing colors
    gradient.colors.clear()
    
    # Copy from ColorRamp
    for elem in color_ramp.elements:
        color_item = gradient.colors.add()
        color_item.position = elem.position
        color_item.color = elem.color[:]


def cleanup_gradient_node_groups():
    """Remove orphaned gradient node groups that don't have matching gradients."""
    # Get all gradient names from scenes
    gradient_names = set()
    for scene in bpy.data.scenes:
        if hasattr(scene, 'vgradient_collection'):
            for gradient in scene.vgradient_collection:
                gradient_names.add(get_gradient_node_group_name(gradient.name))
    
    # Find and remove orphaned node groups
    to_remove = []
    for ng in bpy.data.node_groups:
        if ng.name.startswith(GRADIENT_NODE_GROUP_PREFIX):
            if ng.name not in gradient_names:
                to_remove.append(ng)
    
    for ng in to_remove:
        bpy.data.node_groups.remove(ng)


def rename_gradient_node_group(old_name, new_name):
    """Rename a gradient's node group when the gradient is renamed.
    
    Args:
        old_name: Previous gradient name
        new_name: New gradient name
    """
    old_ng_name = get_gradient_node_group_name(old_name)
    new_ng_name = get_gradient_node_group_name(new_name)
    
    if old_ng_name in bpy.data.node_groups:
        bpy.data.node_groups[old_ng_name].name = new_ng_name


def get_gradient_colors_from_ramp(gradient):
    """Get a list of (position, color) tuples from the gradient's ColorRamp.
    
    Args:
        gradient: GradientData PropertyGroup instance
        
    Returns:
        List of (position, (r, g, b, a)) tuples sorted by position
    """
    color_ramp = get_color_ramp_for_gradient(gradient)
    colors = []
    for elem in color_ramp.elements:
        colors.append((elem.position, tuple(elem.color)))
    return sorted(colors, key=lambda x: x[0])


def get_gradient_first_color(gradient):
    """Get the first (position 0) color from the gradient's ColorRamp.
    
    Args:
        gradient: GradientData PropertyGroup instance
        
    Returns:
        Tuple (r, g, b, a) of the first color, or (0, 0, 0, 1) if empty
    """
    colors = get_gradient_colors_from_ramp(gradient)
    if colors:
        return colors[0][1]
    return (0.0, 0.0, 0.0, 1.0)


def get_gradient_last_color(gradient):
    """Get the last (position 1) color from the gradient's ColorRamp.
    
    Args:
        gradient: GradientData PropertyGroup instance
        
    Returns:
        Tuple (r, g, b, a) of the last color, or (1, 1, 1, 1) if empty
    """
    colors = get_gradient_colors_from_ramp(gradient)
    if colors:
        return colors[-1][1]
    return (1.0, 1.0, 1.0, 1.0)


def get_gradient_color_count(gradient):
    """Get the number of color stops in the gradient's ColorRamp.
    
    Args:
        gradient: GradientData PropertyGroup instance
        
    Returns:
        Number of color stops
    """
    color_ramp = get_color_ramp_for_gradient(gradient)
    return len(color_ramp.elements)

def get_unified_paint_settings(context):
    """Return UnifiedPaintSettings for current Blender version.
    
    Blender 5.0 moved unified_paint_settings under mode-specific Paint
    structs (e.g. tool_settings.sculpt.unified_paint_settings).
    Prior versions exposed it directly on tool_settings.
    
    This helper tries the new locations first, then falls back.
    Returns None if not available.
    """
    ts = getattr(context, 'tool_settings', None)
    if not ts:
        return None

    # Blender 5.0+ locations (mode-specific Paint structs)
    for paint_attr in ('sculpt', 'vertex_paint', 'image_paint',
                       'weight_paint', 'grease_pencil_paint'):
        paint = getattr(ts, paint_attr, None)
        if paint and hasattr(paint, 'unified_paint_settings'):
            ups = getattr(paint, 'unified_paint_settings', None)
            if ups is not None:
                return ups

    # Pre-5.0 fallback
    return getattr(ts, 'unified_paint_settings', None)

def print_timing(start_time, label):
    """Print timing information for performance analysis"""
    elapsed = (time.time() - start_time) * 1000
    print(f"{label}: {elapsed:.2f}ms")
    return time.time()

def get_ui_scale(context=None):
    """Get UI scale factor based on platform and display settings
    
    This helps standardize the appearance of UI elements across different platforms
    and display resolutions by providing a scale factor that can be used to adjust
    sizes of UI elements like lines, circles, etc.
    
    Args:
        context: Optional Blender context. If not provided, uses bpy.context
        
    Returns:
        float: Scale factor to multiply UI element sizes by
    """
    if context is None:
        context = bpy.context
    
    # Get system information
    system = platform.system()
    
    # Get Blender's UI scale factor
    ui_scale = context.preferences.view.ui_scale
    
    # Base scale factor
    scale = 1.0
    
    # Platform-specific adjustments
    if system == "Darwin":  # macOS
        # macOS needs much larger UI elements due to high-DPI displays
        scale = 1.5
    elif system == "Windows":
        # Windows scaling is generally good as-is
        scale = 1.0
    elif system == "Linux":
        # Linux might need slight adjustment
        scale = 1.2
    
    # Apply Blender's UI scale
    scale *= ui_scale
    
    # Get screen DPI information if available
    try:
        # This is a rough approximation as Blender doesn't expose screen DPI directly
        area = context.area
        if area and area.type == 'VIEW_3D':
            region = area.regions[4]  # Usually the main region
            # Use region dimensions as a rough proxy for DPI scaling
            # This helps with multi-monitor setups with different DPIs
            region_scale = min(region.width / 1000, region.height / 1000)
            # Limit the influence of this factor
            region_scale = max(0.8, min(1.5, region_scale))
            scale *= region_scale
    except:
        # If we can't get region info, just use the base scale
        pass
    
    return scale

def world_to_screen_batch(world_coords, region, region_3d):
    """Convert world coordinates to screen coordinates in batch using NumPy"""
    # Get view and projection matrices
    view_matrix = np.array(region_3d.view_matrix)
    proj_matrix = np.array(region_3d.window_matrix)
    
    # Convert world coordinates to NumPy array
    coords = np.array(world_coords)
    
    # Add homogeneous coordinate (w=1)
    coords_4d = np.column_stack([coords, np.ones(len(coords))])
    
    # Apply view matrix
    view_coords = coords_4d @ view_matrix.T
    
    # Apply projection matrix
    clip_coords = view_coords @ proj_matrix.T
    
    # Perform perspective division
    clip_coords = clip_coords / clip_coords[:, 3:]
    
    # Convert to screen coordinates
    screen_coords = np.empty((len(coords), 2), dtype=np.float32)
    screen_coords[:, 0] = (clip_coords[:, 0] + 1.0) * region.width * 0.5
    screen_coords[:, 1] = (clip_coords[:, 1] + 1.0) * region.height * 0.5
    
    return screen_coords

def transform_verts_to_world_batch(verts, matrix_world):
    """Transform vertex positions from local to world space in batch using NumPy
    
    Args:
        verts: NumPy array of vertex positions (shape: [n, 3])
        matrix_world: 4x4 world matrix of the object
        
    Returns:
        NumPy array of vertex positions in world space (shape: [n, 3])
    """
    # Convert matrix to NumPy array
    matrix = np.array(matrix_world)
    
    # Extract rotation matrix (3x3) and translation vector
    rotation = matrix[:3, :3]
    translation = matrix[:3, 3]
    
    # Apply rotation and translation to all vertices at once
    world_verts = np.dot(verts, rotation.T) + translation
    
    return world_verts

def get_active_gradient(context):
    """Get the active gradient from the context"""
    if len(context.scene.vgradient_collection) > 0:
        return context.scene.vgradient_collection[context.scene.vgradient_active_index]
    return None

def ensure_vertex_color_attribute(obj):
    """Ensure the object has a vertex color attribute and return it
    In Edit mode, uses BYTE_COLOR attributes with CORNER domain
    In Object mode, uses FLOAT_COLOR attributes with POINT domain
    Always tries to reuse existing attributes rather than creating new ones
    """
    if obj.type != 'MESH':
        return None
    
    # Debug: Print existing attributes before we do anything
    print(f"\n[DEBUG] ensure_vertex_color_attribute for {obj.name}")
    print(f"[DEBUG] Object mode: {obj.mode}")
    print(f"[DEBUG] Existing attributes:")
    for attr in obj.data.attributes:
        print(f"  - {attr.name} (domain: {attr.domain}, type: {attr.data_type})")
    
    # In Edit mode, we need to use BYTE_COLOR attributes with BMesh
    if obj.mode == 'EDIT':
        import bmesh
        # Get the BMesh
        bm = bmesh.from_edit_mesh(obj.data)
        
        # Debug: Print existing BMesh color layers
        print(f"[DEBUG] Existing BMesh color layers:")
        for layer_name in bm.loops.layers.color.keys():
            print(f"  - {layer_name}")
        
        # First check if we have any existing BYTE_COLOR attributes
        byte_color_attrs = [attr for attr in obj.data.attributes 
                           if attr.domain == 'CORNER' and attr.data_type == 'BYTE_COLOR']
        
        if byte_color_attrs:
            # Use the first BYTE_COLOR attribute
            print(f"[DEBUG] Using existing BYTE_COLOR attribute: {byte_color_attrs[0].name}")
            obj.data.attributes.active_color = byte_color_attrs[0]
            return byte_color_attrs[0]
        
        # If we have BMesh color layers but no BYTE_COLOR attributes, something is wrong
        # This shouldn't happen, but let's handle it just in case
        if bm.loops.layers.color and not byte_color_attrs:
            print(f"[DEBUG] Warning: BMesh color layers exist but no BYTE_COLOR attributes found")
        
        # If no BYTE_COLOR attributes exist, we need to create one via BMesh
        # First, remove any existing FLOAT_COLOR attributes to avoid duplicates
        attrs_to_remove = []
        for attr in obj.data.attributes:
            if attr.domain == 'CORNER' and attr.data_type == 'FLOAT_COLOR':
                attrs_to_remove.append(attr)
        
        # Remove the attributes (can't do it in the loop above)
        for attr in attrs_to_remove:
            print(f"[DEBUG] Removing FLOAT_COLOR attribute: {attr.name}")
            obj.data.attributes.remove(attr)
        
        # Create a new BMesh color layer, which will create a BYTE_COLOR attribute
        print(f"[DEBUG] Creating new BMesh color layer: ColorFC")
        color_layer = bm.loops.layers.color.new("ColorFC")
        
        # Find the corresponding BYTE_COLOR attribute that was created
        byte_color_attr = None
        for attr in obj.data.attributes:
            if attr.domain == 'CORNER' and attr.data_type == 'BYTE_COLOR':
                byte_color_attr = attr
                print(f"[DEBUG] Found new BYTE_COLOR attribute: {attr.name}")
                break
        
        # Set it as the active color attribute
        if byte_color_attr:
            obj.data.attributes.active_color = byte_color_attr
            print(f"[DEBUG] Set active color attribute to: {byte_color_attr.name}")
            return byte_color_attr
        else:
            print(f"[DEBUG] Error: Failed to create BYTE_COLOR attribute")
            return None
    
    # For Object mode, use FLOAT_COLOR attributes with POINT domain
    domain = 'POINT'
    
    # First check for active color attribute with the correct domain
    active_color = obj.data.attributes.active_color
    if active_color and active_color.domain == domain and active_color.data_type == 'FLOAT_COLOR':
        print(f"[DEBUG] Using active color attribute: {active_color.name}")
        return active_color
    
    # Get all color attributes of the appropriate domain
    color_attributes = [attr for attr in obj.data.attributes 
                       if attr.domain == domain and attr.data_type == 'FLOAT_COLOR']
    
    # If we have any color attributes with the correct domain, use the first one
    if color_attributes:
        print(f"[DEBUG] Using existing color attribute: {color_attributes[0].name}")
        obj.data.attributes.active_color = color_attributes[0]
        return color_attributes[0]
    
    # Check for BYTE_COLOR attributes that we can convert to FLOAT_COLOR
    byte_color_attrs = [attr for attr in obj.data.attributes 
                       if attr.data_type == 'BYTE_COLOR']
    
    if byte_color_attrs:
        # Convert the first BYTE_COLOR attribute to FLOAT_COLOR with POINT domain
        source_attr = byte_color_attrs[0]
        source_name = source_attr.name
        source_domain = source_attr.domain
        print(f"[DEBUG] Converting BYTE_COLOR attribute '{source_name}' to FLOAT_COLOR")
        
        # Read existing color data from source attribute
        num_elements = len(source_attr.data)
        source_colors = []
        for i in range(num_elements):
            source_colors.append(tuple(source_attr.data[i].color))
        
        num_verts = len(obj.data.vertices)
        
        # Pre-compute vertex colors if converting from CORNER domain
        vertex_color_data = []
        if source_domain == 'CORNER':
            # Build vertex to loop mapping
            vertex_colors = {}
            vertex_counts = {}
            for poly in obj.data.polygons:
                for loop_idx in poly.loop_indices:
                    vert_idx = obj.data.loops[loop_idx].vertex_index
                    color = source_colors[loop_idx]
                    if vert_idx not in vertex_colors:
                        vertex_colors[vert_idx] = [0.0, 0.0, 0.0, 0.0]
                        vertex_counts[vert_idx] = 0
                    vertex_colors[vert_idx][0] += color[0]
                    vertex_colors[vert_idx][1] += color[1]
                    vertex_colors[vert_idx][2] += color[2]
                    vertex_colors[vert_idx][3] += color[3]
                    vertex_counts[vert_idx] += 1
            
            # Average colors
            for vert_idx in range(num_verts):
                if vert_idx in vertex_colors and vertex_counts[vert_idx] > 0:
                    count = vertex_counts[vert_idx]
                    vertex_color_data.append((
                        vertex_colors[vert_idx][0] / count,
                        vertex_colors[vert_idx][1] / count,
                        vertex_colors[vert_idx][2] / count,
                        vertex_colors[vert_idx][3] / count
                    ))
                else:
                    vertex_color_data.append((1.0, 1.0, 1.0, 1.0))
        else:
            # Direct copy for POINT domain
            for i in range(num_verts):
                if i < num_elements:
                    vertex_color_data.append(source_colors[i])
                else:
                    vertex_color_data.append((1.0, 1.0, 1.0, 1.0))
        
        # Remove the old BYTE_COLOR attribute first (so we can reuse the name)
        obj.data.attributes.remove(source_attr)
        
        # Create new FLOAT_COLOR attribute with the original name
        new_attr = obj.data.attributes.new(name=source_name, type='FLOAT_COLOR', domain=domain)
        
        # Apply the pre-computed colors
        for vert_idx in range(num_verts):
            new_attr.data[vert_idx].color = vertex_color_data[vert_idx]
        
        obj.data.attributes.active_color = new_attr
        print(f"[DEBUG] Converted to FLOAT_COLOR attribute: {new_attr.name}")
        return new_attr
    
    # If no color attributes exist, create a new one named "Color"
    print(f"[DEBUG] Creating new color attribute named 'Color'")
    color_attribute = obj.data.attributes.new(name="Color", type='FLOAT_COLOR', domain=domain)
    obj.data.attributes.active_color = color_attribute
    return color_attribute

def update_color_attribute(obj, attribute, values, selected_verts=None):
    """Update a color attribute with the given values, handling Edit mode correctly
    
    Args:
        obj: The mesh object
        attribute: The color attribute to update
        values: Numpy array of color values (in linear RGB space)
        selected_verts: Optional array of selected vertex indices (for Edit mode)
    
    Returns:
        True if successful, False if there was an error
    """
    import numpy as np
    import bmesh
    
    # Debug: Print attribute info at the start
    print(f"\n[DEBUG] update_color_attribute for {obj.name}")
    print(f"[DEBUG] Attribute: {attribute.name} (domain: {attribute.domain}, type: {attribute.data_type})")
    print(f"[DEBUG] Object mode: {obj.mode}")
    
    # Debug: Print all attributes
    print(f"[DEBUG] All attributes at start:")
    for attr in obj.data.attributes:
        print(f"  - {attr.name} (domain: {attr.domain}, type: {attr.data_type})")
    
    # Handle Edit mode differently
    if obj.mode == 'EDIT':
        # Get the BMesh
        bm = bmesh.from_edit_mesh(obj.data)
        
        # Debug: Print BMesh color layers
        print(f"[DEBUG] BMesh color layers at start:")
        for layer_name in bm.loops.layers.color.keys():
            print(f"  - {layer_name}")
        
        # Check if we already have any BMesh color layers
        if bm.loops.layers.color:
            # Use the existing BMesh color layer instead of creating a new one
            color_layer_name = bm.loops.layers.color.keys()[0]
            color_layer = bm.loops.layers.color[color_layer_name]
            print(f"[DEBUG] Using existing BMesh color layer: {color_layer_name}")
            
            # Get the corresponding attribute (it might have a different name)
            byte_color_attr = None
            for attr in obj.data.attributes:
                if attr.domain == 'CORNER' and attr.data_type == 'BYTE_COLOR':
                    byte_color_attr = attr
                    print(f"[DEBUG] Found corresponding BYTE_COLOR attribute: {attr.name}")
                    break
        else:
            # We need to create a new BMesh color layer
            # First, remove any existing FLOAT_COLOR attributes to avoid duplicates
            attrs_to_remove = []
            for attr in obj.data.attributes:
                if attr.domain == 'CORNER' and attr.data_type == 'FLOAT_COLOR':
                    attrs_to_remove.append(attr)
            
            # Remove the attributes (can't do it in the loop above)
            for attr in attrs_to_remove:
                print(f"[DEBUG] Removing attribute: {attr.name}")
                obj.data.attributes.remove(attr)
            
            # Now create a new BMesh color layer
            print(f"[DEBUG] Creating new BMesh color layer: Color")
            color_layer = bm.loops.layers.color.new("Color")
            
            # Find the corresponding BYTE_COLOR attribute that was created
            byte_color_attr = None
            for attr in obj.data.attributes:
                if attr.domain == 'CORNER' and attr.data_type == 'BYTE_COLOR':
                    byte_color_attr = attr
                    print(f"[DEBUG] Found new BYTE_COLOR attribute: {attr.name}")
                    break
            
            # Set it as the active color attribute
            if byte_color_attr:
                obj.data.attributes.active_color = byte_color_attr
                print(f"[DEBUG] Set active color attribute to: {byte_color_attr.name}")
        
        # Reshape values to 4-component colors if needed
        if len(values.shape) == 1:
            values = values.reshape(-1, 4)
        
        # Following Method 1 exactly: Use face.select to determine selected faces
        # This gives clean, sharp edges at selection boundaries
        
        # Get selected faces
        selected_faces = [f for f in bm.faces if f.select]
        print(f"\nUpdate Color Attribute Debug:")
        print(f"Mode: {obj.mode}")
        print(f"Selected faces: {len(selected_faces)}")
        print(f"Values shape: {values.shape}")
        print(f"Color layer: {color_layer.name if hasattr(color_layer, 'name') else color_layer}")
        
        if selected_faces:
            # We have selected faces, only update those
            print(f"Updating {len(selected_faces)} selected faces")
            sample_count = min(3, len(values))
            print(f"Sample colors (first {sample_count}):", values[:sample_count])
            
            for face in selected_faces:
                for loop in face.loops:
                    vert_idx = loop.vert.index
                    if vert_idx < len(values):
                        # Convert from linear RGB to sRGB before writing to BMesh color layer
                        linear_color = values[vert_idx]
                        srgb_color = tuple(linear_to_srgb(c) for c in linear_color[:3]) + (linear_color[3],)
                        loop[color_layer] = srgb_color
        else:
            # No selection or not in face select mode, update all loops
            for face in bm.faces:
                for loop in face.loops:
                    vert_idx = loop.vert.index
                    if vert_idx < len(values):
                        # Convert from linear RGB to sRGB before writing to BMesh color layer
                        linear_color = values[vert_idx]
                        srgb_color = tuple(linear_to_srgb(c) for c in linear_color[:3]) + (linear_color[3],)
                        loop[color_layer] = srgb_color
        
        # Update the mesh
        bmesh.update_edit_mesh(obj.data)
        
        # Debug: Print attributes after update
        print(f"[DEBUG] All attributes after update:")
        for attr in obj.data.attributes:
            print(f"  - {attr.name} (domain: {attr.domain}, type: {attr.data_type})")
        
        # Debug: Print BMesh color layers after update
        print(f"[DEBUG] BMesh color layers after update:")
        for layer_name in bm.loops.layers.color.keys():
            print(f"  - {layer_name}")
            
        return True
    else:
        # In Object or Sculpt mode, use the normal approach
        try:
            # Check if the object has modifiers that might affect vertex count
            has_modifiers = len(obj.modifiers) > 0
            print(f"[DEBUG] Object has modifiers: {has_modifiers}")
            
            # Get the expected length of the attribute data
            expected_length = 0
            if attribute.domain == 'POINT':
                expected_length = len(obj.data.vertices) * 4  # RGBA = 4 components
            elif attribute.domain == 'CORNER':
                expected_length = len(obj.data.loops) * 4  # RGBA = 4 components
            elif attribute.domain == 'FACE':
                expected_length = len(obj.data.polygons) * 4  # RGBA = 4 components
            
            print(f"[DEBUG] Expected attribute length: {expected_length}")
            print(f"[DEBUG] Values array length: {len(values.reshape(-1))}")
            
            # Ensure our values array matches the expected length
            flat_values = values.reshape(-1)
            if len(flat_values) != expected_length:
                print(f"[DEBUG] Length mismatch - resizing array")
                # If lengths don't match, we need to resize our array
                # This can happen with mirror modifiers where the evaluated mesh has more vertices
                # than the original mesh
                
                # Create a new array of the correct size
                if expected_length > 0:
                    # If our array is too large, truncate it
                    if len(flat_values) > expected_length:
                        flat_values = flat_values[:expected_length]
                    # If our array is too small, pad it with the last value
                    else:
                        # Get the last complete color (4 components)
                        last_color = flat_values[-4:] if len(flat_values) >= 4 else np.array([1.0, 1.0, 1.0, 1.0])
                        # Calculate how many elements we need to add
                        padding_length = expected_length - len(flat_values)
                        # Create padding array by repeating the last color
                        padding = np.tile(last_color, padding_length // 4 + 1)[:padding_length]
                        # Concatenate the original array with the padding
                        flat_values = np.concatenate([flat_values, padding])
            
            # Now update the attribute data
            attribute.data.foreach_set("color", flat_values)
            obj.data.update()
            
            # Debug: Print attributes after update
            print(f"[DEBUG] All attributes after update:")
            for attr in obj.data.attributes:
                print(f"  - {attr.name} (domain: {attr.domain}, type: {attr.data_type})")
                
            return True
        except Exception as e:
            print(f"[DEBUG] Error updating color attribute: {e}")
            print(f"[DEBUG] Error type: {type(e).__name__}")
            # Try a more cautious approach for objects with modifiers
            try:
                print(f"[DEBUG] Trying alternative update method")
                # Update colors one by one instead of using foreach_set
                if attribute.domain == 'POINT':
                    for i, v in enumerate(obj.data.vertices):
                        if i < len(values):
                            attribute.data[i].color = values[i]
                elif attribute.domain == 'CORNER':
                    for i, l in enumerate(obj.data.loops):
                        if i < len(values):
                            attribute.data[i].color = values[i]
                elif attribute.domain == 'FACE':
                    for i, p in enumerate(obj.data.polygons):
                        if i < len(values):
                            attribute.data[i].color = values[i]
                obj.data.update()
                return True
            except Exception as e2:
                print(f"[DEBUG] Alternative method also failed: {e2}")
                return False

def get_selected_vertices(obj):
    """Get indices of selected vertices in Edit mode
    Returns a numpy array of selected vertex indices, or None if not in Edit mode
    or if no vertices are selected"""
    if obj.mode != 'EDIT':
        return None
        
    import bmesh
    import bpy
    # Get the bmesh from the object
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    
    # Debug selection modes
    select_mode = bpy.context.tool_settings.mesh_select_mode
    print(f"Selection mode: {select_mode} (Vertex, Edge, Face)")
    
    # Check if we're in face select mode and have selected faces
    face_select_mode = select_mode[2]  # True if in face select mode
    selected_faces = [f for f in bm.faces if f.select]
    print(f"Face select mode: {face_select_mode}, Selected faces: {len(selected_faces)}")
    
    # If in face select mode with selected faces, get all vertices of those faces
    if face_select_mode and selected_faces:
        print("Using face selection to determine selected vertices")
        selected_indices = set()
        for face in selected_faces:
            for vert in face.verts:
                selected_indices.add(vert.index)
        selected_indices = list(selected_indices)
    else:
        # Check if any vertices are directly selected
        has_selection = any(v.select for v in bm.verts)
        
        # If no explicit selection, return None (indicating all vertices should be affected)
        if not has_selection:
            print("No vertex selection found, returning None")
            return None
            
        # Get indices of selected vertices
        selected_indices = [v.index for v in bm.verts if v.select]
    
    print(f"Selected vertices: {len(selected_indices)}")
    
    # Convert to numpy array for efficiency
    import numpy as np
    return np.array(selected_indices, dtype=np.int32)

def apply_mask_mode(context, event):
    """Determine if we should apply the gradient as a sculpt mask instead of vertex colors.
    Returns a tuple of (use_mask_mode, gradient) where:
    - use_mask_mode: True if Alt is held and we're in sculpt mode
    - gradient: The gradient to use (either user-selected or black-to-white)"""
    # Check if we're in sculpt mode first
    in_sculpt_mode = context.mode == 'SCULPT'
    
    # Alt key is ignored in Edit mode
    in_edit_mode = context.mode == 'EDIT_MESH'
    
    # Check if Alt is held - handle different event types
    alt_held = False
    if event and not in_edit_mode:
        if hasattr(event, 'alt'):
            alt_held = event.alt
        elif hasattr(event, 'alt_pressed'):  # For custom event objects
            alt_held = event.alt_pressed
    
    # Print debug info
    print(f"Alt held: {alt_held}, Sculpt mode: {in_sculpt_mode}, Edit mode: {in_edit_mode}")
    
    # Determine if we should use mask mode - never in Edit mode
    use_mask_mode = alt_held and in_sculpt_mode
    
    if use_mask_mode:
        # Create a temporary black to white gradient
        gradient = type('GradientData', (), {'colors': [], 'use_screen_space': False})()
        gradient.colors = [
            type('ColorItem', (), {'color': (0.0, 0.0, 0.0, 1.0)})(),
            type('ColorItem', (), {'color': (1.0, 1.0, 1.0, 1.0)})()
        ]
        
        # Get the screen space setting from the active gradient if available
        active_gradient = get_active_gradient(context)
        if active_gradient and hasattr(active_gradient, 'use_screen_space'):
            gradient.use_screen_space = active_gradient.use_screen_space
        
        return True, gradient
    else:
        # Use the active gradient normally
        return False, get_active_gradient(context)

def gamma_correct(c):
    """Apply gamma correction to a color value"""
    return pow(c, 1/2.2)

def srgb_to_linear(c):
    """Convert from sRGB to linear RGB"""
    if c <= 0.04045:
        return c / 12.92
    else:
        return pow((c + 0.055) / 1.055, 2.4)

def linear_to_srgb(c):
    """Convert from linear RGB to sRGB"""
    if c <= 0.0031308:
        return c * 12.92
    else:
        return 1.055 * pow(c, 1/2.4) - 0.055

def convert_color_srgb_to_linear(color):
    """Convert a color from sRGB to linear RGB"""
    return tuple(srgb_to_linear(c) for c in color)

def convert_color_linear_to_srgb(color):
    """Convert a color from linear RGB to sRGB"""
    return tuple(linear_to_srgb(c) for c in color)

def get_vertex_colors_from_bmesh(obj, num_verts):
    """Get vertex colors from a BMesh in Edit mode, handling color space conversion
    
    Args:
        obj: The mesh object in Edit mode
        num_verts: Number of vertices in the mesh
        
    Returns:
        Numpy array of vertex colors in linear RGB space
    """
    import bmesh
    import numpy as np
    
    # Initialize with white (linear RGB)
    colors = np.ones((num_verts, 4), dtype=np.float32)
    
    # Get the BMesh
    bm = bmesh.from_edit_mesh(obj.data)
    
    # Debug output
    print(f"\n[DEBUG] get_vertex_colors_from_bmesh for {obj.name}")
    print(f"[DEBUG] Number of vertices: {num_verts}")
    print(f"[DEBUG] BMesh has {len(bm.verts)} vertices")
    print(f"[DEBUG] BMesh has {len(bm.faces)} faces")
    print(f"[DEBUG] Color layers: {[layer.name for layer in bm.loops.layers.color]}")
    
    # Check if we have a color layer
    if bm.loops.layers.color:
        color_layer = bm.loops.layers.color[0]  # Use the first color layer
        print(f"[DEBUG] Using color layer: {color_layer.name}")
        
        # For each vertex, average the colors from its loops
        vert_colors = {}
        for face in bm.faces:
            for loop in face.loops:
                vert_idx = loop.vert.index
                if vert_idx not in vert_colors:
                    vert_colors[vert_idx] = []
                # Get color from BMesh (in sRGB space)
                srgb_color = np.array(loop[color_layer])
                # Convert to linear RGB
                linear_color = np.array([srgb_to_linear(c) for c in srgb_color])
                vert_colors[vert_idx].append(linear_color)
        
        print(f"[DEBUG] Collected colors for {len(vert_colors)} vertices")
        
        # Average the colors for each vertex
        for vert_idx, linear_colors in vert_colors.items():
            if linear_colors:  # Make sure we have colors for this vertex
                # Check if the index is valid
                if 0 <= vert_idx < num_verts:
                    colors[vert_idx] = np.mean(linear_colors, axis=0)
                else:
                    print(f"[WARNING] Vertex index {vert_idx} is out of bounds (max: {num_verts-1})")
    else:
        print(f"[DEBUG] No color layers found in BMesh")
    
    return colors

def linear_srgb_to_oklab_vectorized(rgb):
    """Vectorized conversion from linear sRGB to Oklab
    rgb: Nx3 array of linear RGB values"""
    # Convert to cone responses (matrix multiplication)
    lms = np.dot(rgb, np.array([
        [0.4122214708, 0.5363325363, 0.0514459929],
        [0.2119034982, 0.6806995451, 0.1073969566],
        [0.0883024619, 0.2817188376, 0.6299787005]
    ]).T)
    
    # Non-linearity using cube root
    lms_ = np.cbrt(lms)
    
    # Convert to Lab coordinates (matrix multiplication)
    return np.dot(lms_, np.array([
        [0.2104542553, 0.7936177850, -0.0040720468],
        [1.9779984951, -2.4285922050, 0.4505937099],
        [0.0259040371, 0.7827717662, -0.8086757660]
    ]).T)

def oklab_to_linear_srgb_vectorized(lab):
    """Vectorized conversion from Oklab to linear sRGB
    lab: Nx3 array of Oklab values"""
    # Convert to LMS coordinates (matrix multiplication)
    lms_ = np.dot(lab, np.array([
        [1.0, 0.3963377774, 0.2158037573],
        [1.0, -0.1055613458, -0.0638541728],
        [1.0, -0.0894841775, -1.2914855480]
    ]).T)
    
    # Non-linearity using cube
    lms = lms_ * lms_ * lms_
    
    # Convert to RGB (matrix multiplication)
    return np.dot(lms, np.array([
        [4.0767416621, -3.3077115913, 0.2309699292],
        [-1.2684380046, 2.6097574011, -0.3413193965],
        [-0.0041960863, -0.7034186147, 1.7076147010]
    ]).T)

def interpolate_gradient_color(gradient, factor):
    """Interpolate color from gradient based on factor (0-1) using ColorRamp data"""
    if not gradient:
        return (1, 1, 1, 1)
    
    # Get colors from ColorRamp (already sorted by position)
    color_stops = get_gradient_colors_from_ramp(gradient)
    
    if len(color_stops) < 2:
        if len(color_stops) == 1:
            return color_stops[0][1]
        return (1, 1, 1, 1)
    
    # Handle edge cases
    if factor <= color_stops[0][0]:
        return color_stops[0][1]
    if factor >= color_stops[-1][0]:
        return color_stops[-1][1]
    
    # Find the two color stops to interpolate between
    for i in range(len(color_stops) - 1):
        pos1 = color_stops[i][0]
        pos2 = color_stops[i+1][0]
        
        if pos1 <= factor < pos2:
            color1 = color_stops[i][1]
            color2 = color_stops[i+1][1]
            
            # Calculate local factor within segment
            segment_size = pos2 - pos1
            if segment_size > 0:
                local_factor = (factor - pos1) / segment_size
            else:
                local_factor = 0.0
            
            # Interpolate color and alpha
            r = color1[0] * (1 - local_factor) + color2[0] * local_factor
            g = color1[1] * (1 - local_factor) + color2[1] * local_factor
            b = color1[2] * (1 - local_factor) + color2[2] * local_factor
            a = color1[3] * (1 - local_factor) + color2[3] * local_factor
            
            return (r, g, b, a)
    
    # Fallback (should never reach here)
    return color_stops[-1][1]

def interpolate_gradient_colors_batch(gradient, factors):
    """Interpolate colors for multiple factors at once using ColorRamp data"""
    import numpy as np
    import time
    
    # Get colors from the ColorRamp
    color_stops = get_gradient_colors_from_ramp(gradient)
    num_colors = len(color_stops)
    
    if num_colors == 0:
        return None
    if num_colors == 1:
        color = np.array(color_stops[0][1], dtype=np.float32)
        return np.tile(color, (len(factors), 1))
    
    # color_stops is already sorted by position: list of (position, (r,g,b,a))
    positions = np.array([stop[0] for stop in color_stops], dtype=np.float32)
    colors = np.array([stop[1] for stop in color_stops], dtype=np.float32)
    # print_timing(sort_start, "Sort color stops and create arrays")
    
    # Initialize result array
    result = np.zeros((len(factors), 4), dtype=np.float32)
    
    # Handle factors below first position
    below_mask = factors < positions[0]
    if np.any(below_mask):
        result[below_mask] = colors[0]
    
    # Handle factors above last position
    above_mask = factors >= positions[-1]
    if np.any(above_mask):
        result[above_mask] = colors[-1]
    
    # Handle factors within the gradient range
    # middle_start = time.time()
    middle_mask = ~(below_mask | above_mask)
    middle_factors = factors[middle_mask]
    
    if len(middle_factors) > 0:
        # For each factor, find which segment it falls into
        indices = np.zeros(len(middle_factors), dtype=np.int32)
        local_factors = np.zeros(len(middle_factors), dtype=np.float32)
        # print_timing(middle_start, "Setup middle factors")
        
        # segment_start = time.time()
        # Vectorized approach to find segments
        # For each factor, find the index of the last position that is <= factor
        # This is much faster than the nested loop approach
        
        # Create a 2D array where each row contains all positions
        # and each column represents a factor
        positions_2d = positions[:, np.newaxis]
        factors_2d = middle_factors[np.newaxis, :]
        
        # Create a mask where positions <= factors
        mask = positions_2d <= factors_2d
        
        # For each column (factor), find the last True value (last position <= factor)
        # This gives us the index of the segment start for each factor
        indices = np.sum(mask, axis=0) - 1
        
        # Ensure indices are within valid range (0 to len(positions)-2)
        indices = np.clip(indices, 0, len(positions) - 2)
        
        # Calculate local factors within each segment
        segment_starts = positions[indices]
        segment_ends = positions[indices + 1]
        segment_sizes = segment_ends - segment_starts
        
        # Handle potential division by zero
        valid_segments = segment_sizes > 0
        local_factors = np.zeros_like(middle_factors)
        
        if np.any(valid_segments):
            # Only calculate for valid segments
            local_factors[valid_segments] = (middle_factors[valid_segments] - segment_starts[valid_segments]) / segment_sizes[valid_segments]
        # print_timing(segment_start, "Find segments for middle factors")
        
        # Get the colors to interpolate between
        # interp_color_start = time.time()
        colors1 = colors[indices]
        colors2 = colors[indices + 1]
    
        if gradient.use_oklab:
            # Extract RGB components
            rgb1 = colors1[:, :3]
            rgb2 = colors2[:, :3]
            
            # Convert to Oklab space (vectorized)
            lab1 = linear_srgb_to_oklab_vectorized(rgb1)
            lab2 = linear_srgb_to_oklab_vectorized(rgb2)
            
            # Interpolate in Oklab space
            local_factors = local_factors[:, np.newaxis]
            lab_result = lab1 * (1 - local_factors) + lab2 * local_factors
            
            # Convert back to sRGB (vectorized)
            rgb_result = oklab_to_linear_srgb_vectorized(lab_result)
            
            # Add alpha interpolation
            alphas = colors1[:, 3] * (1 - local_factors.flatten()) + colors2[:, 3] * local_factors.flatten()
            
            # No need for debug prints in production code
            
            middle_result = np.column_stack((rgb_result, alphas))
        else:
            # Standard RGB interpolation
            local_factors = local_factors[:, np.newaxis]
            middle_result = colors1 * (1 - local_factors) + colors2 * local_factors
            
            # No need for debug prints in production code
        
        # Assign interpolated colors to the result array
        result[middle_mask] = middle_result
        # print_timing(interp_color_start, "Color space conversion and interpolation")
    
    # print_timing(interp_start, "Total interpolate_gradient_colors_batch time")
    return result

# ---- Symmetry Functions ----

def get_symmetry_data(obj, context):
    """Get symmetry data from object's mesh mirror settings
    
    Args:
        obj: The mesh object
        context: The current context
        
    Returns:
        Dictionary with symmetry information:
        - use_symmetry: Boolean indicating if symmetry should be used
        - symmetry_axes: List of enabled symmetry axes (X, Y, Z)
        - pivot_point: World space pivot point for symmetry
    """
    # Placeholder implementation that always returns symmetry disabled
    # This ensures the addon works while we develop the new symmetry approach
    result = {
        'use_symmetry': False,
        'symmetry_axes': [],
        'pivot_point': None
    }
    return result


def apply_symmetry_to_factors(verts, factors, symmetry_data):
    """Placeholder for the new optimized symmetry implementation
    
    Args:
        verts: NumPy array of vertex positions (shape: [n, 3])
        factors: NumPy array of gradient factors (shape: [n])
        symmetry_data: Dictionary with symmetry information
        
    Returns:
        NumPy array of updated factors with symmetry applied
    """
    # For now, just return the original factors unchanged
    # This ensures the addon works while we develop the new symmetry approach
    return factors

# ---- Gradient Position Functions ----

def ensure_gradient_positions(gradient):
    """Ensure all color stops in the gradient have position values
    
    This function initializes position values for gradient color stops if they are missing,
    invalid, or if all positions are set to 0. It distributes positions evenly from 0 to 1.
    
    Args:
        gradient: The gradient object with color stops to initialize
    """
    # Initialize positions evenly distributed from 0 to 1
    num_colors = len(gradient.colors)
    if num_colors > 0:
        # Check if positions need to be initialized
        # This handles three cases:
        # 1. Positions don't exist (old gradients)
        # 2. All positions are 0 (incorrectly initialized gradients)
        # 3. Some positions are invalid (negative values)
        needs_initialization = False
        all_zero = True
        
        # First pass: check if we need to initialize positions
        for color_stop in gradient.colors:
            if not hasattr(color_stop, 'position') or color_stop.position < 0.0:
                needs_initialization = True
                break
            if color_stop.position > 0.0:
                all_zero = False
        
        # If all positions are 0, we also need to initialize
        if all_zero and num_colors > 1:
            needs_initialization = True
        
        # If positions need initialization, distribute evenly
        if needs_initialization:
            for i, color_stop in enumerate(gradient.colors):
                # Distribute evenly from 0 to 1
                color_stop.position = i / max(1, num_colors - 1)

# ---- Blend Mode Functions ----

def apply_blend_mode(base_colors, blend_colors, blend_mode, opacity):
    """Apply the selected blend mode to blend two color arrays
    
    Args:
        base_colors: NumPy array of base colors (shape: [n, 4] for RGBA)
        blend_colors: NumPy array of blend colors (shape: [n, 4] for RGBA)
        blend_mode: String indicating the blend mode ('NORMAL', 'MULTIPLY', 'ADD', 'SUBTRACT', 'COLOR')
        opacity: Float opacity value (0.0 to 1.0)
        
    Returns:
        NumPy array of blended colors (shape: [n, 4] for RGBA)
    """
    import numpy as np
    
    # Extract RGB components (first 3 channels) and alpha
    base_rgb = base_colors[:, :3]
    blend_rgb = blend_colors[:, :3]
    
    # Get alpha values from the blend colors
    blend_alpha = blend_colors[:, 3:4]
    
    # Debug: Check if blend_alpha contains values other than 1.0
    has_alpha_variation = np.any(blend_alpha < 0.999)
    if has_alpha_variation:
        print(f"DEBUG: blend_alpha has variation: min={np.min(blend_alpha)}, max={np.max(blend_alpha)}")
    
    # Combine global opacity with per-color alpha values
    # Make sure blend_alpha is properly affecting the result
    effective_opacity = opacity * blend_alpha
    
    # Debug: Check effective_opacity
    if has_alpha_variation:
        print(f"DEBUG: effective_opacity with opacity={opacity}: min={np.min(effective_opacity)}, max={np.max(effective_opacity)}")
    
    # Apply the appropriate blend mode
    if blend_mode == 'NORMAL':
        # Normal blend mode (standard alpha blending with Oklab)
        # Convert to Oklab space for perceptual blending
        base_lab = linear_srgb_to_oklab_vectorized(base_rgb)
        blend_lab = linear_srgb_to_oklab_vectorized(blend_rgb)
        
        # Reshape effective_opacity for proper broadcasting
        # This ensures the alpha values are properly applied to each RGB channel
        effective_opacity_3d = np.tile(effective_opacity, (1, 3))
        
        # Interpolate in Oklab space using per-vertex effective opacity
        result_lab = base_lab * (1 - effective_opacity_3d) + blend_lab * effective_opacity_3d
        
        # Convert back to linear RGB
        result_rgb = oklab_to_linear_srgb_vectorized(result_lab)
    
    elif blend_mode == 'MULTIPLY':
        # Multiply blend mode
        result_rgb = base_rgb * blend_rgb
        
        # Reshape effective_opacity for proper broadcasting
        effective_opacity_3d = np.tile(effective_opacity, (1, 3))
        
        # Apply effective opacity
        result_rgb = base_rgb * (1 - effective_opacity_3d) + result_rgb * effective_opacity_3d
    
    elif blend_mode == 'ADD':
        # Add blend mode (with clamping)
        result_rgb = np.minimum(base_rgb + blend_rgb, 1.0)
        
        # Reshape effective_opacity for proper broadcasting
        effective_opacity_3d = np.tile(effective_opacity, (1, 3))
        
        # Apply effective opacity
        result_rgb = base_rgb * (1 - effective_opacity_3d) + result_rgb * effective_opacity_3d
    
    elif blend_mode == 'SUBTRACT':
        # Subtract blend mode (with clamping)
        result_rgb = np.maximum(base_rgb - blend_rgb, 0.0)
        
        # Reshape effective_opacity for proper broadcasting
        effective_opacity_3d = np.tile(effective_opacity, (1, 3))
        
        # Apply effective opacity
        result_rgb = base_rgb * (1 - effective_opacity_3d) + result_rgb * effective_opacity_3d
    
    elif blend_mode == 'COLOR':
        # Color blend mode (preserve luminosity of base, use hue/saturation of blend)
        # Convert to Oklab space
        base_lab = linear_srgb_to_oklab_vectorized(base_rgb)
        blend_lab = linear_srgb_to_oklab_vectorized(blend_rgb)
        
        # Keep L from base, take a/b from blend
        result_lab = np.column_stack([
            base_lab[:, 0],  # L from base
            blend_lab[:, 1],  # a from blend
            blend_lab[:, 2]   # b from blend
        ])
        
        # Convert back to linear RGB
        result_rgb = oklab_to_linear_srgb_vectorized(result_lab)
        
        # Reshape effective_opacity for proper broadcasting
        effective_opacity_3d = np.tile(effective_opacity, (1, 3))
        
        # Apply effective opacity
        result_rgb = base_rgb * (1 - effective_opacity_3d) + result_rgb * effective_opacity_3d
    
    else:
        # Fallback to normal blend
        # Reshape effective_opacity for proper broadcasting
        effective_opacity_3d = np.tile(effective_opacity, (1, 3))
        
        # Apply effective opacity
        result_rgb = base_rgb * (1 - effective_opacity_3d) + blend_rgb * effective_opacity_3d
    
    # Always set alpha to 1.0 for all vertices
    result_alpha = np.ones_like(base_colors[:, 3:4])
    
    # Combine RGB and alpha
    return np.column_stack((result_rgb, result_alpha))

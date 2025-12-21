"""
UI panels for vColGradient addon
Contains panel classes for the addon UI
"""

import bpy
import importlib
from .. import utils

class VGRADIENT_UL_colors(bpy.types.UIList):
    """UI list for displaying gradient colors"""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            # Create a more compact layout with color swatch and position
            row = layout.row(align=True)
            
            # Color swatch with transparency - keep this as the main interactive element
            # This ensures the color picker works when clicked
            row.prop(item, "color", text="")
            
            # Add position value with a smaller input field
            row.prop(item, "position", text="Pos", slider=True)

class COLOR_ATTRIBUTE_UL_List(bpy.types.UIList):
    bl_idname = "COLOR_ATTRIBUTE_UL_list"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index, flt_flag):
        if item:
            mesh = context.object.data if context.object and context.object.type == 'MESH' else None
            
            # Check if this is the active color attribute
            is_active = False
            if mesh and mesh.attributes.active_color:
                is_active = (item.name == mesh.attributes.active_color.name)
            
            row = layout.row()
            
            # Add active marker as a clickable button
            if is_active:
                op = row.operator("vgradient.color_attribute_set_active_by_click", text="", icon='RADIOBUT_ON', emboss=False)
                op.attribute_index = index
            else:
                op = row.operator("vgradient.color_attribute_set_active_by_click", text="", icon='RADIOBUT_OFF', emboss=False)
                op.attribute_index = index
            
            # Name
            split = row.split(factor=0.5)
            split.label(text=item.name)
            
            # Type and domain info
            info_row = split.row()
            
            # Get domain as string
            domain = "Unknown"
            if item.domain == 'POINT':
                domain = "Vertex"
            elif item.domain == 'EDGE':
                domain = "Edge"
            elif item.domain == 'FACE':
                domain = "Face"
            elif item.domain == 'CORNER':
                domain = "Face Corner"
            
            # Get data type as string
            data_type = "Unknown"
            if item.data_type == 'BYTE_COLOR':
                data_type = "Byte"
            elif item.data_type == 'FLOAT_COLOR':
                data_type = "Color"
            
            info_row.label(text=f"{domain} | {data_type}")
        else:
            layout.label(text="", translate=False, icon='BLANK1')

class VGRADIENT_PT_Panel(bpy.types.Panel):
    bl_label = "vColor Tools"
    bl_idname = "VGRADIENT_PT_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "vColor Tools"
    
    @classmethod
    def poll(cls, context):
        # Show panel in Object, Edit, and Sculpt modes
        return context.mode in {'OBJECT', 'EDIT_MESH', 'SCULPT'}

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        # Check if there are gradients
        has_gradients = len(scene.vgradient_collection) > 0
        
        # Initialize positions for all gradients to ensure they have proper values
        # This fixes gradients with missing or invalid position data immediately
        if has_gradients:
            for i, gradient in enumerate(scene.vgradient_collection):
                # Initialize gradient positions
                utils.ensure_gradient_positions(gradient)
                
                # Positions are now properly initialized, no need for debug output
        
        # Use property split for global settings to align values
        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation decorators
        
        # Global options (always visible at the top, following order of importance)
        col = layout.column(align=True)
        col.label(text="Global Options")
        col.prop(context.scene, "vgradient_blend_mode", text="Blend Mode")
        col.prop(context.scene, "vgradient_global_opacity", text="Opacity", slider=True)
        col.prop(context.scene, "vgradient_use_unified_color")
        
        # Symmetry is now automatically inherited from Blender's sculpt settings
        layout.separator()
        
        # Tool info panel - display in all supported modes with collapsible UI
        box = layout.box()
        row = box.row()
        row.prop(context.scene, "vgradient_show_info_panel", icon="TRIA_DOWN" if context.scene.vgradient_show_info_panel else "TRIA_RIGHT", icon_only=True, emboss=False)
        row.label(text="Help", icon='INFO')
        
        # Only show info content if expanded
        if context.scene.vgradient_show_info_panel:
            info_col = box.column(align=True)
            
            # Common info for all modes
            info_col.label(text="• Ctrl - Angle snapping in Linear tool")
            
            # Mode-specific info
            if context.mode == 'EDIT_MESH':
                info_col.label(text="• In Edit mode:")
                info_col.label(text="• Colors applied to face corner data for crisp edges")
                info_col.label(text="• If nothing is selected, tools affect all vertices")
            elif context.mode == 'OBJECT':
                info_col.label(text="• Select one or more objects to use tools")
            elif context.mode == 'SCULPT':
                info_col.label(text="• X - Toggle gradient direction")
                info_col.label(text="• Alt - Apply gradient as sculpt Mask")
        
        # Gradient tools section - most important section
        box = layout.box()
        row = box.row()
        row.prop(context.scene, "vgradient_show_gradient_tools", icon='TRIA_DOWN' if context.scene.vgradient_show_gradient_tools else 'TRIA_RIGHT', icon_only=True, emboss=False)
        row.label(text="Gradient Tools", icon='COLORSET_13_VEC')
        
        # Only show gradient tools contents if expanded
        gradient_tools_visible = context.scene.vgradient_show_gradient_tools
        
        if gradient_tools_visible:
            # Import the gradient editor state variables
            from ..ui.gradient_editor import _is_running
            
            # Gradient operators in a row with proper alignment and spacing
            # Following the "Mode toggling buttons" guideline for important actions
            row = box.row(align=True)
            row.scale_y = 1.2  # Make buttons slightly larger for better visibility
            # Disable gradient tools when editor is active
            row.enabled = has_gradients and not _is_running
            if _is_running:
                row.label(text="Gradient tools disabled while editor is active")
            else:
                row.operator("vgradient.linear", icon='ARROW_LEFTRIGHT', text="Linear")
                row.operator("vgradient.radial", icon='RADIOBUT_ON', text="Radial")
                row.operator("vgradient.normal", icon='NORMALS_VERTEX', text="Normal")
                row.operator("vgradient.curve", icon='CURVE_PATH', text="Curve")
            
            # Show message if no gradients (with clear visual hierarchy)
            if not has_gradients:
                box.separator()
                subcol = box.column(align=True)
                subcol.scale_y = 1.2
                subcol.label(text="No gradients available", icon='INFO')
                subcol.label(text="Create a gradient to use the tools")
                subcol.separator(factor=0.5)
                subcol.operator("vgradient.add_gradient", icon='ADD', text="Create Gradient")
            # Gradient-specific options (only when gradients exist)
            elif has_gradients:
                gradient = scene.vgradient_collection[scene.vgradient_active_index]
                
                # Create a row for both toggle buttons side by side
                row = box.row(align=True)
                row.use_property_split = False  # Turn off property split for this row
                
                # Create a button that toggles between "Perceptual" and "Standard" color interpolation
                if gradient.use_oklab:
                    color_text = "Perceptual"
                    color_icon = 'COLOR'
                else:
                    color_text = "Standard"
                    color_icon = 'IPO_LINEAR'
                
                # Create a button that toggles between "Screen-Space" and "3D"
                if gradient.use_screen_space:
                    screen_text = "Screen-Space"
                    screen_icon = 'WINDOW'
                else:
                    screen_text = "3D"
                    screen_icon = 'MESH_CUBE'
                
                # Add both toggle buttons side by side
                row.prop(gradient, "use_oklab", text=color_text, icon=color_icon, toggle=True)
                row.prop(gradient, "use_screen_space", text=screen_text, icon=screen_icon, toggle=True)
                
                # Add Gradient Manager directly in the gradient tools panel
                box.separator(factor=1.0)
                
                # Heading for gradients list
                box.label(text="Available Gradients:")
                
                # Gradient selection row with better spacing
                row = box.row()
                # Disable gradient list when editor is active
                row.enabled = not _is_running
                row.template_list("UI_UL_list", "vgradient_list", scene, "vgradient_collection",
                                scene, "vgradient_active_index", rows=2)
                
                # Add/Remove gradient buttons
                col = row.column(align=True)
                # Disable gradient management when editor is active
                col.enabled = not _is_running
                col.operator("vgradient.add_gradient", icon='ADD', text="")
                col.operator("vgradient.remove_gradient", icon='REMOVE', text="")
                
                # Color list section
                gradient = scene.vgradient_collection[scene.vgradient_active_index]
                
                # Visual Gradient Editor section
                box.separator(factor=0.5)
                
                # Gradient Editor heading with visual indicator
                row = box.row()
                row.label(text="Gradient Editor:")
                
                # Import the gradient editor state variables
                from ..ui.gradient_editor import _is_running, _active_gradient
                
                # Start/stop gradient editor buttons
                row = box.row(align=True)
                if not _is_running:
                    row.operator("vgradient.start_gradient_editor", text="Open Gradient Editor", icon='MODIFIER')
                else:
                    # Make the stop button more prominent
                    row.scale_y = 1.2
                    row.alert = True
                    row.operator("vgradient.stop_gradient_editor", text="Stop Editing", icon='CANCEL')
                    
                    # Instructions
                    col = box.column(align=True)
                    col.label(text="• Click gradient to add color stops")
                    col.label(text="• Drag triangles to adjust positions")
                    col.label(text="• Press ENTER/LMB to accept changes")
                    
                # Color list with reordering - use a more compact horizontal layout
                row = box.row()
                # Use a more compact list but keep the standard layout for functionality
                row.template_list("VGRADIENT_UL_colors", "", 
                                gradient, "colors",
                                gradient, "active_color_index",
                                rows=min(3, max(2, len(gradient.colors))))
                
                # Add/Remove/Move buttons with better grouping
                col = row.column(align=True)
                # Disable color stop management when editor is active
                # (except for color editing which should remain available)
                col.enabled = not _is_running
                # Group add/remove operations
                col.operator("vgradient.add_color", icon='ADD', text="")
                col.operator("vgradient.remove_color", icon='REMOVE', text="")
                col.separator(factor=0.5)
                # Group movement operations
                col.operator("vgradient.move_color", icon='TRIA_UP', text="").type = 'UP'
                col.operator("vgradient.move_color", icon='TRIA_DOWN', text="").type = 'DOWN'
                
        
        # Import the gradient editor state variables if not already imported
        try:
            _is_running
        except NameError:
            from ..ui.gradient_editor import _is_running
            
        # Flood Fill Tool - Collapsible panel
        box = layout.box()
        row = box.row()
        row.prop(context.scene, "vgradient_show_flood_fill", icon='TRIA_DOWN' if context.scene.vgradient_show_flood_fill else 'TRIA_RIGHT', icon_only=True, emboss=False)
        row.label(text="Flood Fill Tool", icon='BRUSH_DATA')
        
        # Show disabled status if editor is active
        if _is_running:
            row.label(text="(Disabled while editor is active)", icon='LOCKED')
        
        # Only show flood fill contents if expanded
        if context.scene.vgradient_show_flood_fill:
            ups = utils.get_unified_paint_settings(context)

            # Determine the data source and property name based on the toggle
            if context.scene.vgradient_use_unified_color and ups:
                data_source = ups
                prop_name = "color"
            else:
                data_source = context.scene
                prop_name = "vgradient_flood_fill_color"

            # Color wheel with dynamic scaling
            col = box.column()
            col.scale_y = context.scene.vgradient_wheel_scale
            col.template_color_picker(data_source, prop_name, value_slider=True)

            # Controls row: color swatch, size slider, reset button
            ctrl_col = box.column(align=True)
            row = ctrl_col.row(align=True)
            split = row.split(factor=0.35, align=True)
            split.prop(data_source, prop_name, text="")
            right_split = split.split(factor=0.85, align=True)
            right_split.prop(context.scene, "vgradient_wheel_scale", text="Size", slider=True)
            right_split.operator("vgradient.reset_wheel_scale", text="", icon='LOOP_BACK')

            # Flood Fill Button
            row = ctrl_col.row(align=True)
            row.operator("vgradient.flood_fill", icon='BRUSH_DATA', text="Fill")
            
            # Show message if disabled
            if _is_running:
                box.label(text="Flood fill is disabled while the gradient editor is active", icon='INFO')
        
        # Color Palette - Separate collapsible panel
        box = layout.box()
        row = box.row()
        row.prop(context.scene, "vgradient_show_color_palette", icon='TRIA_DOWN' if context.scene.vgradient_show_color_palette else 'TRIA_RIGHT', icon_only=True, emboss=False)
        row.label(text="Color Palette", icon='COLOR')
        
        # Only show color palette contents if expanded
        if context.scene.vgradient_show_color_palette:
            ts = context.tool_settings
            
            # Get paint settings based on current mode
            paint_settings = None
            if context.mode == 'PAINT_VERTEX':
                paint_settings = ts.vertex_paint
            elif context.mode == 'SCULPT':
                paint_settings = ts.sculpt
            elif context.mode == 'PAINT_TEXTURE':
                paint_settings = ts.image_paint
            else:
                paint_settings = ts.image_paint
            
            if paint_settings:
                # Palette selector using Blender's native template (no auto 'new' button)
                row = box.row(align=True)
                row.template_ID(paint_settings, "palette")
                
                # Show create default vColorTools palette button if no palette exists
                if not paint_settings.palette:
                    row.operator(
                        "vgradient.create_default_palette",
                        text="Create Default Palette",
                        icon='ADD'
                    )
                    # Show hint about existing vColorTools palette
                    if "vColorTools" in bpy.data.palettes:
                        box.label(text="Use the dropdown to select the existing 'vColorTools' palette or click the palette button to create/assign it.", icon='INFO')
                
                if paint_settings.palette:
                    # Native palette grid display
                    col = box.column()
                    col.template_palette(paint_settings, "palette", color=True)
        
        # RGB Curves - Collapsible panel
        box = layout.box()
        row = box.row()
        row.prop(context.scene, "vgradient_show_curves", icon='TRIA_DOWN' if context.scene.vgradient_show_curves else 'TRIA_RIGHT', icon_only=True, emboss=False)
        row.label(text="RGB Curves", icon='FCURVE')
        
        # Only show curves contents if expanded
        if context.scene.vgradient_show_curves:
            # Try to get the curves node
            from ..gradient_operators.curves import get_or_create_curves_node, CURVES_NODE_TREE_NAME
            
            curves_node = None
            if CURVES_NODE_TREE_NAME in bpy.data.node_groups:
                node_tree = bpy.data.node_groups[CURVES_NODE_TREE_NAME]
                for node in node_tree.nodes:
                    if node.type == 'CURVE_RGB':
                        curves_node = node
                        break
            
            if curves_node is None:
                # Curves not initialized yet
                box.label(text="Click to initialize curves editor", icon='INFO')
                box.operator("vgradient.init_curves", text="Initialize Curves")
            else:
                # Import helper to check for stored colors
                from ..gradient_operators.curves import has_stored_colors
                
                # Store/Clear button at top - toggles based on stored state
                row = box.row(align=True)
                if has_stored_colors(context):
                    row.operator("vgradient.clear_stored_colors", text="Clear Base", icon='X')
                else:
                    row.operator("vgradient.store_colors", text="Store Base", icon='FILE_TICK')
                
                # Show the curves editor using the node's mapping
                box.template_curve_mapping(curves_node, "mapping", type='COLOR')
                
                # Contrast and Saturation sliders
                col = box.column(align=True)
                col.prop(context.scene, "vgradient_curves_contrast", slider=True)
                col.prop(context.scene, "vgradient_curves_saturation", slider=True)
                
                # Apply and Reset buttons
                row = box.row(align=True)
                row.scale_y = 1.2
                row.operator("vgradient.apply_curves", text="Apply", icon='CHECKMARK')
                row.operator("vgradient.reset_curves", text="Reset", icon='LOOP_BACK')
                
                # Info text
                col = box.column(align=True)
                col.scale_y = 0.8
                col.label(text="Store base colors for non-destructive editing")
        
        # Color Attribute Manager - Separate collapsible panel
        if context.object and context.object.type == 'MESH':
            box = layout.box()
            row = box.row()
            row.prop(context.scene, "vgradient_show_color_attributes", icon='TRIA_DOWN' if context.scene.vgradient_show_color_attributes else 'TRIA_RIGHT', icon_only=True, emboss=False)
            row.label(text="Color Attribute Manager", icon='GROUP_VCOL')
            
            # Only show color attribute manager contents if expanded
            if context.scene.vgradient_show_color_attributes:
                mesh = context.object.data
                
                # Main row with list and buttons
                row = box.row()
                
                # Color attributes list
                row.template_list("COLOR_ATTRIBUTE_UL_list", "", mesh, "color_attributes", 
                                context.scene, "active_color_attribute_index")
                
                # Add/Remove/Duplicate/Set Active/Convert buttons column
                col = row.column(align=True)
                col.operator("geometry.color_attribute_add", icon='ADD', text="")
                # Use our custom remove operator instead of the built-in one
                col.operator("vgradient.color_attribute_remove", icon='REMOVE', text="")
                # Add the other operations to the same column
                col.operator("vgradient.color_attribute_duplicate", icon='DUPLICATE', text="")
                col.operator("vgradient.color_attribute_set_active", icon='RADIOBUT_ON', text="")
                col.operator("vgradient.color_attribute_convert", icon='SHADERFX', text="")

# Create a custom operator to handle color attribute removal with the correct index
class VGRADIENT_OT_color_attribute_remove(bpy.types.Operator):
    bl_idname = "vgradient.color_attribute_remove"
    bl_label = "Remove Color Attribute"
    bl_description = "Remove the selected color attribute"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.object
        if not obj or obj.type != 'MESH':
            return {'CANCELLED'}
            
        mesh = obj.data
        attr_idx = context.scene.active_color_attribute_index
        
        print(f"[DEBUG] Removing color attribute at index {attr_idx}")
        print(f"[DEBUG] Available attributes: {[attr.name for attr in mesh.color_attributes]}")
        
        if attr_idx >= 0 and attr_idx < len(mesh.color_attributes):
            attr_name = mesh.color_attributes[attr_idx].name
            print(f"[DEBUG] Removing attribute: {attr_name}")
            
            # Find the attribute in the mesh attributes collection
            for i, attr in enumerate(mesh.attributes):
                if attr.name == attr_name:
                    print(f"[DEBUG] Found attribute {attr_name} at index {i} in mesh.attributes")
                    # Remove the attribute directly
                    mesh.attributes.remove(attr)
                    print(f"[DEBUG] After removal: {[attr.name for attr in mesh.color_attributes]}")
                    return {'FINISHED'}
            
            print(f"[DEBUG] Could not find attribute {attr_name} in mesh.attributes")
            return {'CANCELLED'}
        else:
            print(f"[DEBUG] Invalid index: {attr_idx}")
            return {'CANCELLED'}

# Create a custom operator to handle color attribute duplication
class VGRADIENT_OT_color_attribute_duplicate(bpy.types.Operator):
    bl_idname = "vgradient.color_attribute_duplicate"
    bl_label = "Duplicate Color Attribute"
    bl_description = "Duplicate the selected color attribute"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.object
        if not obj or obj.type != 'MESH':
            return {'CANCELLED'}
            
        mesh = obj.data
        attr_idx = context.scene.active_color_attribute_index
        
        print(f"[DEBUG] Duplicating color attribute at index {attr_idx}")
        print(f"[DEBUG] Available attributes: {[attr.name for attr in mesh.color_attributes]}")
        
        if attr_idx >= 0 and attr_idx < len(mesh.color_attributes):
            source_attr = mesh.color_attributes[attr_idx]
            source_name = source_attr.name
            new_name = f"{source_name}.copy"
            print(f"[DEBUG] Duplicating attribute: {source_name} to {new_name}")
            
            # Find the source attribute in the mesh attributes collection
            source_attr_data = None
            for attr in mesh.attributes:
                if attr.name == source_name:
                    source_attr_data = attr
                    break
            
            if source_attr_data:
                # Create a new attribute with the same properties
                new_attr = mesh.attributes.new(name=new_name, type=source_attr_data.data_type, domain=source_attr_data.domain)
                
                # Copy the data from the source attribute to the new attribute
                if obj.mode == 'EDIT':
                    # In Edit mode, we need to use BMesh
                    import bmesh
                    bm = bmesh.from_edit_mesh(mesh)
                    
                    # Find the color layers
                    if source_attr_data.domain == 'CORNER':
                        source_layer = bm.loops.layers.color.get(source_name)
                        new_layer = bm.loops.layers.color.get(new_name)
                        
                        if source_layer and new_layer:
                            # Copy the data
                            for face in bm.faces:
                                for loop in face.loops:
                                    loop[new_layer] = loop[source_layer]
                            
                            # Update the mesh
                            bmesh.update_edit_mesh(mesh)
                    
                else:  # Object mode
                    # Copy the data directly
                    if source_attr_data.data_type == 'FLOAT_COLOR':
                        for i in range(len(source_attr_data.data)):
                            new_attr.data[i].color = source_attr_data.data[i].color
                    elif source_attr_data.data_type == 'BYTE_COLOR':
                        for i in range(len(source_attr_data.data)):
                            new_attr.data[i].color = source_attr_data.data[i].color
                
                print(f"[DEBUG] After duplication: {[attr.name for attr in mesh.color_attributes]}")
                return {'FINISHED'}
            else:
                print(f"[DEBUG] Could not find source attribute {source_name} in mesh.attributes")
                return {'CANCELLED'}
        else:
            print(f"[DEBUG] Invalid index: {attr_idx}")
            return {'CANCELLED'}

# Create a custom operator to handle color attribute conversion
class VGRADIENT_OT_color_attribute_convert(bpy.types.Operator):
    bl_idname = "vgradient.color_attribute_convert"
    bl_label = "Convert Color Attribute"
    bl_description = "Convert the selected color attribute (Object mode only)"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.object
        if not obj or obj.type != 'MESH':
            return {'CANCELLED'}
        
        # Check if we're in edit mode
        if obj.mode == 'EDIT':
            self.report({'ERROR'}, "Color attribute conversion is not available in Edit mode. Switch to Object mode first.")
            return {'CANCELLED'}
            
        mesh = obj.data
        attr_idx = context.scene.active_color_attribute_index
        
        print(f"[DEBUG] Converting color attribute at index {attr_idx}")
        print(f"[DEBUG] Available attributes: {[attr.name for attr in mesh.color_attributes]}")
        
        if attr_idx >= 0 and attr_idx < len(mesh.color_attributes):
            source_attr = mesh.color_attributes[attr_idx]
            source_name = source_attr.name
            print(f"[DEBUG] Converting attribute: {source_name}")
            
            # Find the attribute in the mesh attributes collection to get its index
            attr_mesh_idx = -1
            for i, attr in enumerate(mesh.attributes):
                if attr.name == source_name:
                    attr_mesh_idx = i
                    break
            
            if attr_mesh_idx >= 0:
                print(f"[DEBUG] Found attribute {source_name} at index {attr_mesh_idx} in mesh.attributes")
                
                # Set the active attribute index in the mesh
                mesh.attributes.active_index = attr_mesh_idx
                
                # Get the current attribute for debugging
                attr = mesh.attributes[attr_mesh_idx]
                print(f"[DEBUG] Current attribute: {attr.name}, type: {attr.data_type}, domain: {attr.domain}")
                
                # Use the Blender operator to show the conversion popup
                # This will invoke the standard Blender conversion dialog
                try:
                    # First, ensure this is the active color attribute
                    # Find its index in the color_attributes collection
                    color_attr_idx = -1
                    for i, attr in enumerate(mesh.color_attributes):
                        if attr.name == source_name:
                            color_attr_idx = i
                            break
                    
                    if color_attr_idx >= 0:
                        # Set it as the active color attribute
                        mesh.color_attributes.active_index = color_attr_idx
                        print(f"[DEBUG] Set active color attribute index to {color_attr_idx}")
                        
                        # Now call the Blender operator with 'INVOKE_DEFAULT' to show the popup
                        # This is the key to getting the popup to show
                        bpy.ops.geometry.color_attribute_convert('INVOKE_DEFAULT')
                        print(f"[DEBUG] Called conversion operator with INVOKE_DEFAULT")
                        return {'FINISHED'}
                    else:
                        self.report({'ERROR'}, f"Could not find color attribute {source_name}")
                        return {'CANCELLED'}
                except Exception as e:
                    self.report({'ERROR'}, f"Conversion failed: {str(e)}")
                    print(f"[DEBUG] Conversion error: {str(e)}")
                    return {'CANCELLED'}
            else:
                print(f"[DEBUG] Could not find attribute {source_name} in mesh.attributes")
                self.report({'ERROR'}, f"Could not find attribute {source_name} in mesh attributes")
                return {'CANCELLED'}
        else:
            print(f"[DEBUG] Invalid index: {attr_idx}")
            self.report({'ERROR'}, "Invalid attribute index")
            return {'CANCELLED'}

# Create a custom operator to handle setting active color attribute
class VGRADIENT_OT_color_attribute_set_active(bpy.types.Operator):
    bl_idname = "vgradient.color_attribute_set_active"
    bl_label = "Set Active Color Attribute"
    bl_description = "Set the selected color attribute as active for viewport"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.object
        if not obj or obj.type != 'MESH':
            return {'CANCELLED'}
            
        mesh = obj.data
        attr_idx = context.scene.active_color_attribute_index
        
        print(f"[DEBUG] Setting active color attribute at index {attr_idx}")
        print(f"[DEBUG] Available attributes: {[attr.name for attr in mesh.color_attributes]}")
        
        if attr_idx >= 0 and attr_idx < len(mesh.color_attributes):
            attr_name = mesh.color_attributes[attr_idx].name
            print(f"[DEBUG] Setting active attribute: {attr_name}")
            
            # Set as active color attribute
            mesh.attributes.active_color = mesh.color_attributes[attr_idx]
            
            print(f"[DEBUG] Active color attribute is now: {mesh.attributes.active_color.name if mesh.attributes.active_color else 'None'}")
            return {'FINISHED'}
        else:
            print(f"[DEBUG] Invalid index: {attr_idx}")
            return {'CANCELLED'}

# Create a custom operator to handle setting active color attribute by clicking the radio button
class VGRADIENT_OT_color_attribute_set_active_by_click(bpy.types.Operator):
    bl_idname = "vgradient.color_attribute_set_active_by_click"
    bl_label = "Set Active Color Attribute By Click"
    bl_description = "Set this color attribute as active for viewport"
    bl_options = {'REGISTER', 'UNDO'}
    
    attribute_index: bpy.props.IntProperty()
    
    def execute(self, context):
        obj = context.object
        if not obj or obj.type != 'MESH':
            return {'CANCELLED'}
            
        mesh = obj.data
        
        # Set the selected attribute index
        context.scene.active_color_attribute_index = self.attribute_index
        
        if self.attribute_index >= 0 and self.attribute_index < len(mesh.color_attributes):
            attr_name = mesh.color_attributes[self.attribute_index].name
            
            # Set as active color attribute
            mesh.attributes.active_color = mesh.color_attributes[self.attribute_index]
            return {'FINISHED'}
        else:
            return {'CANCELLED'}

# Note: The Color Attribute Manager panel has been integrated into the main panel

class VGRADIENT_OT_reset_wheel_scale(bpy.types.Operator):
    """Reset color wheel scale to default value"""
    bl_idname = "vgradient.reset_wheel_scale"
    bl_label = "Reset Wheel Scale"
    bl_description = "Reset the color wheel size to default"
    bl_options = {'INTERNAL'}
    
    def execute(self, context):
        context.scene.vgradient_wheel_scale = 1.0
        return {'FINISHED'}


# List of all classes in this module
classes = (
    VGRADIENT_UL_colors,
    COLOR_ATTRIBUTE_UL_List,
    VGRADIENT_OT_color_attribute_remove,
    VGRADIENT_OT_color_attribute_duplicate,
    VGRADIENT_OT_color_attribute_convert,
    VGRADIENT_OT_color_attribute_set_active,
    VGRADIENT_OT_color_attribute_set_active_by_click,
    VGRADIENT_OT_reset_wheel_scale,
    VGRADIENT_PT_Panel,
)


def register():
    """Register all UI classes"""
    # Register properties for the collapsible panels
    bpy.types.Scene.vgradient_show_manager = bpy.props.BoolProperty(
        name="Show Gradient Manager",
        description="Show or hide the gradient manager section",
        default=False
    )
    
    bpy.types.Scene.vgradient_show_color_attributes = bpy.props.BoolProperty(
        name="Show Color Attribute Manager",
        description="Show or hide the color attribute manager section",
        default=False
    )
    
    bpy.types.Scene.active_color_attribute_index = bpy.props.IntProperty()
    
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    """Unregister all UI classes"""
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    # Unregister the properties
    if hasattr(bpy.types.Scene, "vgradient_show_manager"):
        del bpy.types.Scene.vgradient_show_manager
    if hasattr(bpy.types.Scene, "vgradient_show_color_attributes"):
        del bpy.types.Scene.vgradient_show_color_attributes
    if hasattr(bpy.types.Scene, "active_color_attribute_index"):
        del bpy.types.Scene.active_color_attribute_index

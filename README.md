# vColorTools - Vertex Color Tools Addon for Blender

**Version:** 1.2.1  
**Author:** MattGPT  
**Compatibility:** Blender 4.0.0 and newer  

## Overview

vColorTools is a powerful Blender addon for creating and manipulating vertex colors with intuitive gradient tools. It offers advanced color interpolation, multiple gradient types, and works seamlessly in Object, Edit, and Sculpt modes. The addon enables precise control over vertex color data with optimized performance suitable for both artistic and technical workflows.

## What's New in v1.2.1

- Fixed incorrect color application in Blender 5 for Flood Fill
  (unified paint color is linear in 5.0+, no double conversion).
- Non-destructive RGB Curves confirmed to operate in linear RGB.
- Store Base now converts BYTE_COLOR attributes to FLOAT_COLOR instead
  of creating a duplicate empty attribute; preserves data and name.
- Palette panel updated to Blender-native layout using `template_palette`,
  with a dedicated "Create Default Palette" (vColorTools) button and
  legacy palette compatibility.
- Fill tool panel updated with a resizable color wheel and compact
  controls row (swatch, size slider, reset).

## Key Features

### Gradient Types
- **Linear Gradient (Minus Key):** Create gradients between two points
- **Radial Gradient (Zero Key):** Create circular gradients from a center point
- **Normal Gradient:** Apply gradients based on vertex normal alignment
- **Curve Gradient (Shift + Zero Key):** Create gradients along customizable bezier curves
- **Flood Fill (Equals Key):** Fill entire mesh with a single color

### Color Management
- **Multiple Gradient Presets:** Save and load gradient presets for quick reuse
- **Per-Color-Stop Alpha Control:** Adjust opacity independently for each color in a gradient
- **Color Space Options:**
  - Perceptual blending using Oklab color space
  - Standard RGB color interpolation

### RGB Curves Adjustment (New in v1.2.0)
- **Full RGB Curves Editor:** Blender's native curve editor for precise color control
- **Per-Channel Curves:** Adjust Red, Green, Blue, and Combined (master) curves
- **Contrast Control:** Fine-tune contrast with dedicated slider
- **Saturation Control:** Adjust color intensity from grayscale to oversaturated
- **Non-Destructive Workflow:**
  - Store Base: Save current vertex colors as baseline
  - Clear Base: Remove stored baseline
  - Adjustments always apply from stored baseline (no stacking)
  - Reset restores original colors and resets all sliders

### Advanced Features
- **Projection Modes:**
  - Screen-space projection for intuitive 2D workflows
  - 3D space projection for precise technical applications
- **Blend Modes:** Multiple blend modes for combining colors
- **Global Opacity:** Control overall opacity for subtle color adjustments
- **Symmetry Support:** Automatic symmetry following Blender's sculpt symmetry settings
- **Edit Mode Support:** Apply gradients to selected vertices, edges, or faces
- **Color Attribute Management:** Full control over color attributes including:
  - Convert between domain types (vertex, face, face corner)
  - Convert between data types (byte, float)
  - Duplicate color attributes
  - Set active color attributes

## Installation

1. Download the addon zip file
2. In Blender, go to Edit > Preferences > Add-ons
3. Click "Install..." and select the downloaded zip file
4. Enable the addon by checking the box next to "Object: vColorTools"

## Usage Guide

### Interface Location
The addon's panel is located in the 3D View sidebar (press `N` to toggle), under the "vColor Tools" tab.

### Global Options
- **Blend Mode:** Choose how new colors blend with existing colors (Replace, Add, Multiply, etc.)
- **Opacity:** Control the global opacity of gradient operations
- **Help Panel:** Collapsible panel with mode-specific tips and keyboard shortcuts

### Using Gradient Tools

#### Linear Gradient Tool
1. Press the minus key (`-`) to activate
2. Click to set the start point (uses first color in gradient)
3. Move and click again to set the end point (uses last color in gradient)
4. Hold `Ctrl` while dragging for angle snapping
5. Hold `Alt` to apply as sculpt mask in Sculpt mode

#### Radial Gradient Tool
1. Press the zero key (`0`) to activate
2. Click to set the center point (uses first color in gradient)
3. Move to define radius and click again
4. Hold `Alt` to apply as sculpt mask in Sculpt mode

#### Normal Gradient Tool
1. Click the "Normal" button in the panel
2. Click on a surface to sample the normal direction
3. The gradient is applied based on how closely vertex normals align with the sampled normal
4. Hold `Alt` to apply as sculpt mask in Sculpt mode

#### Curve Gradient Tool
1. Press the equal key (`=`) to activate
2. Place three control points to define a bezier curve
3. Adjust control points by click-dragging
4. Click to apply the gradient along the curve path
5. Hold `Alt` to apply as sculpt mask in Sculpt mode

#### Flood Fill Tool
1. Select a color using Blender's color picker
2. Click the "Flood Fill" button to apply the color to the entire mesh or selection

### Managing Gradients
- Create multiple named gradients for different purposes
- Add, remove, and reorder color stops within each gradient
- Toggle between screen-space and 3D projection
- Toggle between perceptual (Oklab) and standard color interpolation

### Color Attribute Management
- Create new color attributes with different domains and data types
- Duplicate existing color attributes
- Convert between different domain types (vertex, face, face corner)
- Convert between different data types (byte, float)
- Delete unused color attributes
- Set the active color attribute for viewport display

### Using RGB Curves
1. Expand the "RGB Curves" panel
2. Click "Initialize Curves" (first time only)
3. Click "Store Base" to save current vertex colors as baseline
4. Adjust curves by adding/moving control points
5. Use Contrast and Saturation sliders for quick adjustments
6. Click "Apply" to apply changes
7. Adjust again and Apply - changes don't stack (uses stored baseline)
8. Click "Reset" to restore original colors and reset all controls
9. Click "Clear Base" to remove stored baseline when finished

## Tips for Best Results

1. **Screen-Space vs. 3D:** Screen-space gradients appear consistent from any viewing angle, while 3D gradients follow the actual model geometry.

2. **Perceptual Color Blending:** Enable Oklab blending for more natural-looking color transitions, especially with vibrant colors.

3. **Edit Mode Selection:** In Edit mode, gradients only affect selected geometry. If nothing is selected, all vertices are affected.

4. **Alpha Control:** Per-color-stop alpha allows for creating complex gradients with varying opacity regions.

5. **Performance Optimization:**
   - Screen-space projection with batch processing is faster for dense meshes
   - Consider using simpler meshes for complex gradient work
   - Symmetry operations can be slower, especially with large meshes

6. **Workflow Integration:**
   - Use gradients to create base colors for texture painting
   - Create smooth gradients for sculpting using the Alt modifier
   - Combine multiple gradient operations with different blend modes for complex effects

7. **Keyboard Shortcuts:**
   - Minus key (`-`): Linear gradient
   - Zero key (`0`): Radial gradient
   - Shift + Zero key (`)`): Curve gradient
   - Equal key (`=`): Flood fill
   - `Ctrl`: Angle snapping in Linear tool
   - `Alt`: Apply as sculpt mask in Sculpt mode

## Compatibility Notes

- Fully compatible with Blender 4.0.0 and newer, including Blender 5.0
- Works in Object, Edit, and Sculpt modes
- Compatible with all Blender color attribute types and domains
- Optimal performance with modern GPUs supporting efficient batch processing

## Troubleshooting

- **Gradient Not Visible:** Ensure your material is set up to display vertex colors (use Attribute node in shader)


## License

This addon is released under the GPL v3 license.


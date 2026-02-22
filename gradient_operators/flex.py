"""
Flex gradient operator for vColorTools addon.
Apply active gradient to Super Tools flex meshes from root to tip.
"""

import json

import bpy
import numpy as np
from mathutils import Vector

from .. import utils


class VGRADIENT_OT_flex_gradient(bpy.types.Operator):
    """Apply active gradient to selected flex meshes root-to-tip."""

    bl_idname = "vgradient.flex_gradient"
    bl_label = "Flex Gradient"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Apply active gradient to selected Super Tools flex meshes"

    @classmethod
    def poll(cls, context):
        area = getattr(context, "area", None)
        if not area or area.type != 'VIEW_3D':
            return False
        return context.mode in {'OBJECT', 'EDIT_MESH', 'SCULPT'}

    def execute(self, context):
        gradient = utils.get_active_gradient(context)
        if not gradient or utils.get_gradient_color_count(gradient) < 1:
            self.report({'WARNING'}, "No active gradient available")
            return {'CANCELLED'}

        objects = self._get_target_objects(context)
        if not objects:
            self.report({'WARNING'}, "No valid mesh objects selected")
            return {'CANCELLED'}

        processed = 0
        skipped = 0

        for obj in objects:
            if "flex_curve_data" not in obj:
                skipped += 1
                continue

            curve_data = self._parse_flex_curve_data(obj)
            if not curve_data:
                skipped += 1
                continue

            segment_count = int(curve_data.get("segments", 0))
            if segment_count < 1:
                skipped += 1
                continue

            curve_points = self._get_curve_points_local(obj, curve_data)
            if len(curve_points) < 2:
                skipped += 1
                continue

            segment_spine = self._build_segment_spine(curve_points, curve_data)
            if len(segment_spine) < 2:
                skipped += 1
                continue

            if not self._apply_gradient_to_object(
                context,
                obj,
                gradient,
                segment_spine,
                segment_count,
            ):
                skipped += 1
                continue

            processed += 1

        if processed == 0:
            self.report(
                {'WARNING'},
                "No compatible flex meshes processed",
            )
            return {'CANCELLED'}

        self.report(
            {'INFO'},
            f"Applied flex gradient to {processed} object(s), skipped {skipped}",
        )
        return {'FINISHED'}

    def _get_target_objects(self, context):
        if context.mode == 'SCULPT':
            if context.active_object and context.active_object.type == 'MESH':
                return [context.active_object]
            return []

        if context.mode == 'EDIT_MESH':
            if context.active_object and context.active_object.type == 'MESH':
                return [context.active_object]
            return []

        return [obj for obj in context.selected_objects if obj.type == 'MESH']

    def _parse_flex_curve_data(self, obj):
        data_json = obj.get("flex_curve_data")
        if not data_json:
            return None

        try:
            data = json.loads(data_json)
        except Exception:
            return None

        if not isinstance(data, dict):
            return None
        return data

    def _get_curve_points_local(self, obj, curve_data):
        points = []
        for point_data in curve_data.get("curve_points", []):
            try:
                points.append(
                    Vector(
                        (
                            float(point_data["x"]),
                            float(point_data["y"]),
                            float(point_data["z"]),
                        )
                    )
                )
            except Exception:
                return []

        if not points:
            return []

        in_object_space = bool(curve_data.get("in_object_space", True))
        if in_object_space:
            return points

        world_to_local = obj.matrix_world.inverted_safe()
        return [world_to_local @ point for point in points]

    def _resample_polyline(self, points, sample_count):
        if len(points) < 2 or sample_count < 2:
            return points

        cumulative_lengths = [0.0]
        total_length = 0.0

        for idx in range(1, len(points)):
            segment_length = (points[idx] - points[idx - 1]).length
            total_length += segment_length
            cumulative_lengths.append(total_length)

        if total_length <= 1e-8:
            return [points[0].copy() for _ in range(sample_count)]

        result = []
        for sample_idx in range(sample_count):
            target = (sample_idx / (sample_count - 1)) * total_length
            seg_idx = 0
            while (
                seg_idx < len(cumulative_lengths) - 1
                and cumulative_lengths[seg_idx + 1] < target
            ):
                seg_idx += 1

            start = points[seg_idx]
            end = points[min(seg_idx + 1, len(points) - 1)]
            seg_start = cumulative_lengths[seg_idx]
            seg_end = cumulative_lengths[min(seg_idx + 1, len(cumulative_lengths) - 1)]
            seg_len = max(seg_end - seg_start, 1e-8)
            t = (target - seg_start) / seg_len
            result.append(start.lerp(end, t))

        return result

    def _build_segment_spine(self, curve_points, curve_data):
        """Build a segment spine that matches Super Tools interpolation."""
        segment_count = int(curve_data.get("segments", 0))
        sample_count = max(2, segment_count + 1)

        try:
            from super_tools.utils import flex_math as flex_math_utils

            use_bspline = bool(curve_data.get("bspline_mode", False))
            tensions = curve_data.get("tensions", None)
            sharp_points = curve_data.get("no_tangent_points", None)

            if use_bspline:
                spine = flex_math_utils.bspline_cubic_open_uniform(
                    curve_points,
                    sample_count,
                )
            else:
                spine = flex_math_utils.interpolate_curve_3d(
                    curve_points,
                    num_points=sample_count,
                    sharp_points=sharp_points,
                    tensions=tensions,
                )

            if len(spine) >= 2:
                return spine
        except Exception:
            # Fallback for environments where Super Tools is unavailable.
            pass

        return self._resample_polyline(curve_points, sample_count)

    def _apply_gradient_to_object(
        self,
        context,
        obj,
        gradient,
        segment_spine,
        segment_count,
    ):
        mesh = obj.data
        num_verts = len(mesh.vertices)
        if num_verts == 0:
            return False

        segment_indices = self._calculate_segment_indices(
            mesh,
            segment_spine,
            segment_count,
        )

        gradient_colors = []
        denom = max(1, segment_count - 1)
        for segment_idx in range(segment_count):
            factor = segment_idx / denom
            gradient_colors.append(utils.interpolate_gradient_color(gradient, factor))

        new_colors = np.zeros((num_verts, 4), dtype=np.float32)
        for vert_idx, seg_idx in enumerate(segment_indices):
            new_colors[vert_idx] = gradient_colors[seg_idx]

        target_attribute = utils.ensure_vertex_color_attribute(obj)
        if not target_attribute:
            return False

        obj.data.attributes.active_color = target_attribute

        selected_verts = None
        if context.mode == 'EDIT_MESH':
            selected_verts = utils.get_selected_vertices(obj)

        opacity = context.scene.vgradient_global_opacity
        blend_mode = context.scene.vgradient_blend_mode

        needs_existing = (
            selected_verts is not None
            or opacity < 0.999
            or blend_mode != 'NORMAL'
        )

        existing_colors = None
        if needs_existing:
            if obj.mode == 'EDIT':
                existing_colors = utils.get_vertex_colors_from_bmesh(obj, num_verts)
            else:
                existing_colors = np.zeros(num_verts * 4, dtype=np.float32)
                target_attribute.data.foreach_get("color", existing_colors)
                existing_colors = existing_colors.reshape(num_verts, 4)

        if blend_mode == 'NORMAL' and opacity >= 0.999:
            blended = new_colors
        else:
            blended = utils.apply_blend_mode(
                existing_colors,
                new_colors,
                blend_mode,
                opacity,
            )

        if selected_verts is not None:
            if existing_colors is None:
                existing_colors = utils.get_vertex_colors_from_bmesh(obj, num_verts)
            mask = np.zeros(num_verts, dtype=bool)
            mask[selected_verts] = True
            final_colors = np.where(mask[:, np.newaxis], blended, existing_colors)
            utils.update_color_attribute(
                obj,
                target_attribute,
                final_colors,
                selected_verts,
            )
        else:
            utils.update_color_attribute(obj, target_attribute, blended, None)

        return True

    def _calculate_segment_indices(self, mesh, spine_points, segment_count):
        spine_lengths = [0.0]
        total_spine_length = 0.0

        for idx in range(1, len(spine_points)):
            seg_len = (spine_points[idx] - spine_points[idx - 1]).length
            total_spine_length += seg_len
            spine_lengths.append(total_spine_length)

        if total_spine_length <= 1e-8:
            return np.zeros(len(mesh.vertices), dtype=np.int32)

        indices = np.zeros(len(mesh.vertices), dtype=np.int32)

        for vert_idx, vert in enumerate(mesh.vertices):
            point = vert.co
            best_dist_sq = float("inf")
            best_s = 0.0

            for seg_idx in range(len(spine_points) - 1):
                a = spine_points[seg_idx]
                b = spine_points[seg_idx + 1]
                ab = b - a
                ab_len_sq = ab.length_squared
                if ab_len_sq <= 1e-12:
                    continue

                t = (point - a).dot(ab) / ab_len_sq
                t = max(0.0, min(1.0, t))
                projected = a + ab * t
                dist_sq = (point - projected).length_squared

                if dist_sq < best_dist_sq:
                    best_dist_sq = dist_sq
                    seg_len = (b - a).length
                    best_s = spine_lengths[seg_idx] + t * seg_len

            normalized = best_s / total_spine_length
            segment_index = int(normalized * segment_count)
            if segment_index >= segment_count:
                segment_index = segment_count - 1
            indices[vert_idx] = segment_index

        return indices

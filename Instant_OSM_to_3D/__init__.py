bl_info = {
    "name": "Instant OSM to 3D Monolith [LITE]",
    "author": "Obsidiam",
    "version": (1, 4, 1),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > GIS Generator Tab",
    "description": "Free Version: Interactive 2D Blueprint, Crop Box Culling, and Fixed Facade Generation",
    "category": "3D View",
}

import bpy
import json
import os
import math
import random
from mathutils import Vector

EARTH_RADIUS = 6378137.0

def lon_lat_to_meters(lon, lat):
    x = EARTH_RADIUS * math.radians(lon)
    y = EARTH_RADIUS * math.log(math.tan(math.pi / 4.0 + math.radians(lat) / 2.0))
    return x, y

def get_or_create_collection(name, parent_col):
    col = bpy.data.collections.get(name)
    if not col:
        col = bpy.data.collections.new(name)
        parent_col.children.link(col)
    return col

def setup_building_materials(obj, win_obj=None):
    wall_mat = bpy.data.materials.get("OSM_Walls") or bpy.data.materials.new(name="OSM_Walls")
    wall_mat.use_nodes = True
    if wall_mat.node_tree.nodes.get("Principled BSDF"):
        bsdf = wall_mat.node_tree.nodes["Principled BSDF"]
        bsdf.inputs['Base Color'].default_value = (0.55, 0.55, 0.55, 1.0)
        bsdf.inputs['Roughness'].default_value = 0.85
    wall_mat.diffuse_color = (0.55, 0.55, 0.55, 1.0)
        
    roof_mat = bpy.data.materials.get("OSM_Roofs") or bpy.data.materials.new(name="OSM_Roofs")
    roof_mat.use_nodes = True
    if roof_mat.node_tree.nodes.get("Principled BSDF"):
        bsdf = roof_mat.node_tree.nodes["Principled BSDF"]
        bsdf.inputs['Base Color'].default_value = (0.25, 0.25, 0.25, 1.0)
        bsdf.inputs['Roughness'].default_value = 0.70
    roof_mat.diffuse_color = (0.25, 0.25, 0.25, 1.0)

    if win_obj:
        win_mat = bpy.data.materials.get("OSM_Windows") or bpy.data.materials.new(name="OSM_Windows")
        win_mat.use_nodes = True
        if win_mat.node_tree.nodes.get("Principled BSDF"):
            bsdf = win_mat.node_tree.nodes["Principled BSDF"]
            bsdf.inputs['Base Color'].default_value = (0.02, 0.25, 0.45, 1.0)
            bsdf.inputs['Roughness'].default_value = 0.02
            bsdf.inputs['Metallic'].default_value = 0.95
        win_mat.diffuse_color = (0.02, 0.25, 0.45, 1.0)
        win_obj.data.materials.clear()
        win_obj.data.materials.append(win_mat)

def setup_road_materials(obj):
    road_mat = bpy.data.materials.get("OSM_Road_Asphalt") or bpy.data.materials.new(name="OSM_Road_Asphalt")
    road_mat.use_nodes = True
    if road_mat.node_tree.nodes.get("Principled BSDF"):
        bsdf = road_mat.node_tree.nodes["Principled BSDF"]
        bsdf.inputs['Base Color'].default_value = (0.06, 0.08, 0.08, 1.0)
        bsdf.inputs['Roughness'].default_value = 0.92
    road_mat.diffuse_color = (0.06, 0.08, 0.08, 1.0)
        
    foot_mat = bpy.data.materials.get("OSM_Footway") or bpy.data.materials.new(name="OSM_Footway")
    foot_mat.use_nodes = True
    if foot_mat.node_tree.nodes.get("Principled BSDF"):
        bsdf = foot_mat.node_tree.nodes["Principled BSDF"]
        bsdf.inputs['Base Color'].default_value = (0.22, 0.22, 0.22, 1.0)
        bsdf.inputs['Roughness'].default_value = 0.80
    foot_mat.diffuse_color = (0.22, 0.22, 0.22, 1.0)

    obj.data.materials.clear()
    obj.data.materials.append(road_mat)
    obj.data.materials.append(foot_mat)

def setup_nature_materials(obj, type_nature="park"):
    if type_nature == "water":
        mat = bpy.data.materials.get("OSM_Water") or bpy.data.materials.new(name="OSM_Water")
        mat.use_nodes = True
        if mat.node_tree.nodes.get("Principled BSDF"):
            bsdf = mat.node_tree.nodes["Principled BSDF"]
            bsdf.inputs['Base Color'].default_value = (0.05, 0.35, 0.65, 1.0)
            bsdf.inputs['Roughness'].default_value = 0.10
            bsdf.inputs['Specular IOR Level'].default_value = 0.7
        mat.diffuse_color = (0.05, 0.35, 0.65, 1.0)
    else:
        mat = bpy.data.materials.get("OSM_Park") or bpy.data.materials.new(name="OSM_Park")
        mat.use_nodes = True
        if mat.node_tree.nodes.get("Principled BSDF"):
            bsdf = mat.node_tree.nodes["Principled BSDF"]
            bsdf.inputs['Base Color'].default_value = (0.15, 0.45, 0.20, 1.0)
            bsdf.inputs['Roughness'].default_value = 0.90
        mat.diffuse_color = (0.15, 0.45, 0.20, 1.0)
        
    obj.data.materials.clear()
    obj.data.materials.append(mat)


class WM_OT_CreateMapBlueprint(bpy.types.Operator):
    bl_label = "Create 2D Map Blueprint"
    bl_idname = "wm.create_map_blueprint"
    bl_description = "Generate 2D wireframe map tracing layout"
    
    def execute(self, context):
        scene = context.scene
        path = bpy.path.abspath(scene.geojson_file_path)
        if not path or not os.path.exists(path):
            self.report({'ERROR'}, "File not found!"); return {'CANCELLED'}
        try:
            with open(path, 'r', encoding='utf-8') as f: data = json.load(f)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to read GeoJSON: {str(e)}"); return {'CANCELLED'}
            
        raw_features, all_lons, all_lats = [], [], []
        for feature in data.get('features', []):
            geometry = feature.get('geometry', {})
            properties = feature.get('properties', {})
            g_type = geometry.get('type')
            
            if g_type == 'Polygon':
                coords_list = geometry.get('coordinates', [])
                if not coords_list or not isinstance(coords_list, list): continue
                coords = coords_list[0]
                if len(coords) < 3: continue
                
                if 'building' in properties:
                    raw_features.append({'type': 'building', 'coords': coords})
                elif 'leisure' in properties or properties.get('landuse') in ['park', 'forest', 'meadow', 'recreation_ground'] or 'natural' in properties and properties['natural'] == 'wood':
                    raw_features.append({'type': 'park', 'coords': coords})
                elif 'water' in properties or 'natural' in properties and properties['natural'] == 'water' or 'waterway' in properties:
                    raw_features.append({'type': 'water', 'coords': coords})
                for lon, lat in coords: all_lons.append(lon); all_lats.append(lat)
                
            elif g_type == 'LineString' and 'highway' in properties:
                coords = geometry.get('coordinates', [])
                if len(coords) < 2: continue
                raw_features.append({'type': 'road', 'coords': coords})
                for lon, lat in coords: all_lons.append(lon); all_lats.append(lat)
                    
        if not raw_features:
            self.report({'ERROR'}, "No valid features found!"); return {'CANCELLED'}
        center_lon, center_lat = sum(all_lons) / len(all_lons), sum(all_lats) / len(all_lats)
        center_x, center_y = lon_lat_to_meters(center_lon, center_lat)
        
        root_collection = context.scene.collection
        blueprint_col = get_or_create_collection("OSM_Blueprint_Draft", root_collection)
        verts, edges, v_offset = [], [], 0
        for feat in raw_features:
            points = []
            for lon, lat in feat['coords']:
                mx, my = lon_lat_to_meters(lon, lat); points.append((mx - center_x, my - center_y, 0.0))
            num_pts = len(points); verts.extend(points)
            if feat['type'] in ['building', 'park', 'water']:
                for i in range(num_pts): edges.append([v_offset + i, v_offset + ((i + 1) % num_pts)])
            else:
                for i in range(num_pts - 1): edges.append([v_offset + i, v_offset + i + 1])
            v_offset += num_pts
            
        b_mesh = bpy.data.meshes.new("Blueprint_WireMesh")
        b_obj = bpy.data.objects.new("OSM_2D_Blueprint", b_mesh)
        b_mesh.from_pydata(verts, edges, []); b_mesh.update(); blueprint_col.objects.link(b_obj)
        if "OSM_Crop_Box" in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects["OSM_Crop_Box"], do_unlink=True)
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 15.0))
        crop_box = context.active_object; crop_box.name = "OSM_Crop_Box"
        crop_box.dimensions = (150.0, 150.0, 30.0); crop_box.display_type = 'WIRE'
        self.report({'INFO'}, "Blueprint map deployed successfully!"); return {'FINISHED'}

class WM_OT_GenerateCropCity(bpy.types.Operator):
    bl_label = "Generate 3D City (Cropped)"
    bl_idname = "wm.generate_crop_city"
    bl_description = "Generate 3D buildings, roads, parks, and water inside the Crop Box"
    
    def execute(self, context):
        scene = context.scene
        crop_box = bpy.data.objects.get("OSM_Crop_Box")
        if not crop_box:
            self.report({'ERROR'}, "OSM_Crop_Box not found! Create blueprint first."); return {'CANCELLED'}
            
        box_loc, box_dim = crop_box.location, crop_box.dimensions
        min_x, max_x = box_loc.x - (box_dim.x / 2.0), box_loc.x + (box_dim.x / 2.0)
        min_y, max_y = box_loc.y - (box_dim.y / 2.0), box_loc.y + (box_dim.y / 2.0)
        
        path = bpy.path.abspath(scene.geojson_file_path)
        try:
            with open(path, 'r', encoding='utf-8') as f: data = json.load(f)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to read file: {e}"); return {'CANCELLED'}
            
        raw_buildings, raw_roads, raw_parks, raw_water, all_lons, all_lats = [], [], [], [], [], []
        for feature in data.get('features', []):
            geometry = feature.get('geometry', {})
            properties = feature.get('properties', {})
            g_type = geometry.get('type')
            
            if g_type == 'Polygon':
                coords_list = geometry.get('coordinates', [])
                if coords_list and isinstance(coords_list, list):
                    coords = coords_list[0]
                    if 'building' in properties:
                        raw_buildings.append({'coords': coords, 'properties': properties})
                    elif 'leisure' in properties or properties.get('landuse') in ['park', 'forest', 'meadow', 'recreation_ground'] or properties.get('natural') == 'wood':
                        raw_parks.append({'coords': coords})
                    elif 'water' in properties or properties.get('natural') == 'water' or 'waterway' in properties:
                        raw_water.append({'coords': coords})
                    for lon, lat in coords: 
                        all_lons.append(lon)
                        all_lats.append(lat)
            elif g_type == 'LineString' and 'highway' in properties:
                coords = geometry.get('coordinates', [])
                if len(coords) >= 2:
                    raw_roads.append({'coords': coords, 'properties': properties})
                    for lon, lat in coords: 
                        all_lons.append(lon)
                        all_lats.append(lat)
                    
        if not any([raw_buildings, raw_roads, raw_parks, raw_water]):
            self.report({'ERROR'}, "No valid features found!"); return {'CANCELLED'}
            
        center_lon, center_lat = sum(all_lons) / len(all_lons), sum(all_lats) / len(all_lats)
        center_x, center_y = lon_lat_to_meters(center_lon, center_lat)
        
        root_collection = context.scene.collection
        main_col = get_or_create_collection("OSM_Final_3D_Generation", root_collection)
        
        wall_vertices, wall_faces, roof_vertices, roof_faces = [], [], [], []
        win_vertices, win_faces, win_vert_offset = [], [], 0
        
        # Финишируем размеры окон жестко в коде для LITE
        win_width, win_height = 0.5, 0.6
        step_x, step_y = 1.2, 1.4
        margin_x, margin_y = 0.6, 0.5
        
        processed_buildings_count = 0

        if raw_buildings:
            for b in raw_buildings:
                local_coords, sum_x, sum_y = [], 0.0, 0.0
                for lon, lat in b['coords']:
                    gx, gy = lon_lat_to_meters(lon, lat)
                    lx, ly = gx - center_x, gy - center_y
                    local_coords.append((lx, ly))
                    sum_x += lx
                    sum_y += ly
                num_points = len(local_coords)
                if num_points < 3: 
                    continue
                if not (min_x <= (sum_x / num_points) <= max_x and min_y <= (sum_y / num_points) <= max_y): 
                    continue
                    
                props = b['properties']
                height = float(random.randint(10, 25))
                if 'height' in props:
                    try: height = float(props['height'])
                    except: pass
                elif 'building:levels' in props:
                    try: height = float(props['building:levels']) * 3.0
                    except: pass
                
                r_v_start = len(roof_vertices)
                for x, y in local_coords: 
                    roof_vertices.append((x, y, 0.0))
                for x, y in local_coords: 
                    roof_vertices.append((x, y, height))
                roof_faces.append(list(range(r_v_start + num_points - 1, r_v_start - 1, -1)))
                roof_faces.append(list(range(r_v_start + num_points, r_v_start + num_points * 2)))
                
                for i in range(num_points):
                    x1, y1 = local_coords[i][0], local_coords[i][1]
                    x2, y2 = local_coords[(i + 1) % num_points][0], local_coords[(i + 1) % num_points][1]
                    w_v_start = len(wall_vertices)
                    wall_vertices.extend([(x1, y1, 0.0), (x2, y2, 0.0), (x2, y2, height), (x1, y1, height)])
                    wall_faces.append([w_v_start, w_v_start + 1, w_v_start + 2, w_v_start + 3])
                    
                    p_left, p_right = Vector((x1, y1, 0.0)), Vector((x2, y2, 0.0))
                    edge_vec = p_right - p_left
                    w_width = edge_vec.length
                    if w_width < (win_width + margin_x * 2) or height < (win_height + margin_y * 2) or w_width > 500.0: 
                        continue
                    w_dir = edge_vec.normalized()
                    normal = w_dir.cross(Vector((0, 0, 1))).normalized()
                    w_center_base = p_left + (edge_vec * 0.5)
                    curr_x = -w_width / 2.0 + margin_x + (win_width / 2.0)
                    end_x = w_width / 2.0 - margin_x - (win_width / 2.0)
                    while curr_x <= end_x:
                        curr_y = margin_y + (win_height / 2.0)
                        while curr_y <= height - margin_y - (win_height / 2.0):
                            w_c = w_center_base + (w_dir * curr_x) + (Vector((0, 0, 1)) * curr_y) + normal * 0.01
                            p0 = w_c - (w_dir * win_width / 2.0) - (Vector((0, 0, 1)) * win_height / 2.0)
                            p1 = w_c + (w_dir * win_width / 2.0) - (Vector((0, 0, 1)) * win_height / 2.0)
                            p2 = w_c + (w_dir * win_width / 2.0) + (Vector((0, 0, 1)) * win_height / 2.0)
                            p3 = w_c - (w_dir * win_width / 2.0) + (Vector((0, 0, 1)) * win_height / 2.0)
                            win_vertices.extend([p0, p1, p2, p3])
                            win_faces.append([win_vert_offset, win_vert_offset + 1, win_vert_offset + 2, win_vert_offset + 3])
                            win_vert_offset += 4
                            curr_y += step_y
                        curr_x += step_x
                processed_buildings_count += 1
                if processed_buildings_count % 60 == 0: 
                    context.view_layer.update()

            if wall_vertices:
                b_mesh = bpy.data.meshes.new("District_Walls")
                b_obj = bpy.data.objects.new("3D_District_Walls", b_mesh)
                b_mesh.from_pydata(wall_vertices, [], wall_faces)
                b_mesh.update()
                main_col.objects.link(b_obj)
                setup_building_materials(b_obj)
                
                context.view_layer.update()
                bpy.ops.object.select_all(action='DESELECT')
                b_obj.select_set(True)
                context.view_layer.objects.active = b_obj
                bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.select_all(action='SELECT')
                bpy.ops.uv.smart_project(angle_limit=66.0, island_margin=0.02)
                bpy.ops.object.mode_set(mode='OBJECT')

                r_mesh = bpy.data.meshes.new("District_Roofs")
                r_obj = bpy.data.objects.new("3D_District_Roofs", r_mesh)
                r_mesh.from_pydata(roof_vertices, [], roof_faces)
                r_mesh.update()
                main_col.objects.link(r_obj)
                r_obj.data.materials.append(bpy.data.materials.get("OSM_Roofs"))
                
                if win_vertices:
                    w_mesh = bpy.data.meshes.new("District_Windows")
                    w_obj = bpy.data.objects.new("Generated_Windows_Monolith", w_mesh)
                    w_mesh.from_pydata(win_vertices, [], win_faces)
                    w_mesh.update()
                    main_col.objects.link(w_obj)
                    setup_building_materials(b_obj, win_obj=w_obj)

        if raw_roads:
            col_roads = get_or_create_collection("OSM_Final_Roads", main_col)
            road_vertices, road_faces, road_mat_indices = [], [], []
            r_v_offset = 0
            for r in raw_roads:
                h_type = r['properties'].get('highway')
                width = 2.0 if h_type in ['footway', 'pedestrian', 'path', 'cycleway'] else 7.0
                mat_idx = 1 if h_type in ['footway', 'pedestrian', 'path', 'cycleway'] else 0
                half_w = width / 2.0
                
                all_points = []
                for lon, lat in r['coords']:
                    mx, my = lon_lat_to_meters(lon, lat)
                    lx, ly = mx - center_x, my - center_y
                    all_points.append(Vector((lx, ly, 0.015)))
                
                points = []
                for pt in all_points:
                    if min_x <= pt.x <= max_x and min_y <= pt.y <= max_y:
                        points.append(pt)
                
                num_pts = len(points)
                if num_pts < 2: 
                    continue
                    
                local_left_right = []
                for i in range(num_pts):
                    if i == 0: 
                        dir_vec = (points[1] - points[0]).normalized()
                    elif i == num_pts - 1: 
                        dir_vec = (points[num_pts-1] - points[num_pts-2]).normalized()
                    else:
                        dir_vec = (points[i+1] - points[i-1]).normalized()
                    
                    perp_vec = Vector((-dir_vec.y, dir_vec.x, 0.0))
                    local_left_right.append((points[i] + perp_vec * half_w, points[i] - perp_vec * half_w))
                
                for left, right in local_left_right:
                    road_vertices.append((left.x, left.y, left.z))
                    road_vertices.append((right.x, right.y, right.z))
                
                for i in range(num_pts - 1):
                    v0, v1 = r_v_offset + (i * 2), r_v_offset + (i * 2 + 1)
                    v2, v3 = r_v_offset + ((i+1) * 2 + 1), r_v_offset + ((i+1) * 2)
                    road_faces.append([v0, v1, v2, v3])
                    road_mat_indices.append(mat_idx)
                r_v_offset += num_pts * 2

            if road_vertices:
                road_mesh = bpy.data.meshes.new("District_Roads")
                road_obj = bpy.data.objects.new("3D_District_Roads", road_mesh)
                road_mesh.from_pydata(road_vertices, [], road_faces)
                road_mesh.update()
                setup_road_materials(road_obj)
                for face_idx, m_idx in enumerate(road_mesh.polygons):
                    if face_idx < len(road_mat_indices):
                        road_mesh.polygons[face_idx].material_index = road_mat_indices[face_idx]
                col_roads.objects.link(road_obj)

        if raw_parks:
            col_nature = get_or_create_collection("OSM_Final_Nature", main_col)
            p_vertices, p_faces, p_v_start = [], [], 0
            for park in raw_parks:
                p_coords, sum_px, sum_py = [], 0.0, 0.0
                for lon, lat in park['coords']:
                    gx, gy = lon_lat_to_meters(lon, lat)
                    lx, ly = gx - center_x, gy - center_y
                    p_coords.append((lx, ly, 0.002))
                    sum_px += lx
                    sum_py += ly
                n_pts = len(p_coords)
                if n_pts < 3:
                    continue
                if not (min_x <= sum_px / n_pts <= max_x and min_y <= sum_py / n_pts <= max_y):
                    continue
                p_vertices.extend(p_coords)
                p_faces.append(list(range(p_v_start, p_v_start + n_pts)))
                p_v_start += n_pts
            if p_vertices:
                p_mesh = bpy.data.meshes.new("District_Parks")
                p_obj = bpy.data.objects.new("3D_District_Parks", p_mesh)
                p_mesh.from_pydata(p_vertices, [], p_faces)
                p_mesh.update()
                col_nature.objects.link(p_obj)
                setup_nature_materials(p_obj, "park")

        if raw_water:
            col_nature = get_or_create_collection("OSM_Final_Nature", main_col)
            w_vertices, w_faces, w_v_start = [], [], 0
            for water in raw_water:
                w_coords, sum_wx, sum_wy = [], 0.0, 0.0
                for lon, lat in water['coords']:
                    gx, gy = lon_lat_to_meters(lon, lat)
                    lx, ly = gx - center_x, gy - center_y
                    w_coords.append((lx, ly, 0.005))
                    sum_wx += lx
                    sum_wy += ly
                n_pts = len(w_coords)
                if n_pts < 3:
                    continue
                if not (min_x <= sum_wx / n_pts <= max_x and min_y <= sum_wy / n_pts <= max_y):
                    continue
                w_vertices.extend(w_coords)
                w_faces.append(list(range(w_v_start, w_v_start + n_pts)))
                w_v_start += n_pts
            if w_vertices:
                w_mesh = bpy.data.meshes.new("District_Water")
                w_obj = bpy.data.objects.new("3D_District_Water", w_mesh)
                w_mesh.from_pydata(w_vertices, [], w_faces)
                w_mesh.update()
                col_nature.objects.link(w_obj)
                setup_nature_materials(w_obj, "water")

        self.report({'INFO'}, "Target district generated successfully with nature elements!")
        return {'FINISHED'}

class WM_OT_ResetCitySettings(bpy.types.Operator):
    bl_label = "Reset Settings"
    bl_idname = "wm.reset_city_settings"
    bl_description = "Reset current generator path"

    def execute(self, context):
        context.scene.geojson_file_path = ""
        self.report({'INFO'}, "Settings reset successfully.")
        return {'FINISHED'}

class GIS_PT_GeneratorPanel(bpy.types.Panel):
    bl_label = "OSM City Monolith Settings [LITE]"
    bl_idname = "GIS_PT_generator_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'GIS Generator Tab'

    def draw(self, context):
        layout, scene = self.layout, context.scene
        box_source = layout.box()
        box_source.label(text="Step 1: Load Map Source", icon='WORLD')
        box_source.prop(scene, "geojson_file_path", text="GeoJSON File")
        box_source.operator("wm.create_map_blueprint", text="Create 2D Map Blueprint", icon='GREASEPENCIL')

        if "OSM_Crop_Box" in bpy.data.objects:
            box_info = layout.box()
            box_info.label(text="Step 2: Setup Crop Box", icon='VIEW3D')
            box_info.label(text="Select 'OSM_Crop_Box'. Press G to move, S to scale.")
            
            layout.separator()
            layout.operator("wm.generate_crop_city", text="Generate 3D City", icon='PLAY')
            layout.separator()
            layout.operator("wm.reset_city_settings", text="Reset Defaults", icon='LOOP_BACK')

def register():
    bpy.utils.register_class(WM_OT_CreateMapBlueprint)
    bpy.utils.register_class(WM_OT_GenerateCropCity)
    bpy.utils.register_class(WM_OT_ResetCitySettings)
    bpy.utils.register_class(GIS_PT_GeneratorPanel)
    bpy.types.Scene.geojson_file_path = bpy.props.StringProperty(name="GeoJSON Path", subtype='FILE_PATH')

def unregister():
    bpy.utils.unregister_class(WM_OT_CreateMapBlueprint)
    bpy.utils.unregister_class(WM_OT_GenerateCropCity)
    bpy.utils.unregister_class(WM_OT_ResetCitySettings)
    bpy.utils.unregister_class(GIS_PT_GeneratorPanel)
    del bpy.types.Scene.geojson_file_path

if __name__ == "__main__":
    register()




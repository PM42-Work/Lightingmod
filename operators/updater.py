import bpy
import os
import urllib.request
import json
import zipfile
import shutil
import tempfile
import sys

class LIGHTINGMOD_OT_update_addon(bpy.types.Operator):
    bl_idname = "lightingmod.update_addon"
    bl_label  = "Check for Updates"
    bl_description = "Checks GitHub for updates and installs if a newer version is available"

    def execute(self, context):
        # 1. Provide your standard GitHub Repo URL here
        repo_url = "https://github.com/PM42-Work/Lightingmod"
        
        # 2. Extract the username and repo automatically
        parts = repo_url.rstrip("/").split("/")
        github_user = parts[-2]
        github_repo = parts[-1]
        
        # 3. Read the preference from AddonPreferences
        addon_name = __package__.split('.')[0]
        prefs = context.preferences.addons[addon_name].preferences
        use_experimental = prefs.use_experimental_updates
        
        # 4. Determine API endpoint based on checkbox
        if use_experimental:
            api_url = f"https://api.github.com/repos/{github_user}/{github_repo}/releases"
        else:
            api_url = f"https://api.github.com/repos/{github_user}/{github_repo}/releases/latest"

        addon_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

        # 5. Get current local version from __init__.py's bl_info
        try:
            local_version = sys.modules[addon_name].bl_info.get('version', (0, 0, 0))
        except Exception:
            local_version = (0, 0, 0)

        try:
            self.report({'INFO'}, "Checking GitHub for updates...")
            req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
            
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
                
            # If experimental, API returns a list. Pick the newest one [0].
            release_data = data[0] if isinstance(data, list) else data
            tag_name = release_data.get('tag_name', 'Unknown')
            
            # 6. Parse GitHub Tag into a version tuple (e.g., "v1.3.0-beta" -> (1, 3, 0))
            clean_tag = tag_name.lstrip('v').split('-')[0]
            try:
                remote_version = tuple(map(int, clean_tag.split('.')))
            except ValueError:
                remote_version = (0, 0, 0)
            
            local_version_str = ".".join(map(str, local_version))
            
            # 7. Compare Versions!
            if remote_version <= local_version:
                def draw_uptodate(self, ctx):
                    self.layout.label(text=f"You are already on the latest version (v{local_version_str}).")
                    if use_experimental and '-' not in tag_name:
                        self.layout.label(text="(No experimental pre-releases found on GitHub).")
                context.window_manager.popup_menu(draw_uptodate, title="Up to Date", icon='INFO')
                self.report({'INFO'}, "Addon is up to date.")
                return {'FINISHED'}

            # 8. Proceed with download if an update is found
            assets = release_data.get('assets', [])
            download_url = None
            for asset in assets:
                if asset.get('name') == 'AdvancedLighting.zip':
                    download_url = asset.get('browser_download_url')
                    break
                    
            if not download_url:
                self.report({'ERROR'}, f"No AdvancedLighting.zip found in release {tag_name}.")
                return {'CANCELLED'}

            self.report({'INFO'}, f"Downloading update {tag_name}...")
            
            with tempfile.TemporaryDirectory() as temp_dir:
                zip_path = os.path.join(temp_dir, "update.zip")
                
                # Download
                req_zip = urllib.request.Request(download_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req_zip) as response_zip, open(zip_path, 'wb') as out_file:
                    shutil.copyfileobj(response_zip, out_file)
                
                # Extract
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
                    
                # The folder inside the zip built by your GitHub action
                inner_folder = os.path.join(temp_dir, "AdvancedLighting")
                
                # Copy and overwrite files (dirs_exist_ok=True preserves dependencies folder)
                shutil.copytree(inner_folder, addon_dir, dirs_exist_ok=True)
                
            def draw_success(self, ctx):
                self.layout.label(text=f"Successfully updated from v{local_version_str} to {tag_name}.")
                self.layout.label(text="Please restart Blender to apply changes.")
            context.window_manager.popup_menu(draw_success, title="Update Complete", icon='INFO')
            
        except urllib.error.HTTPError as e:
            self.report({'ERROR'}, f"GitHub API Error: {e.code}. Check repository link/visibility.")
            return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Update failed: {str(e)}")
            return {'CANCELLED'}

        return {'FINISHED'}

classes = (LIGHTINGMOD_OT_update_addon,)

def register():
    for cls in classes: bpy.utils.register_class(cls)
def unregister():
    for cls in reversed(classes): bpy.utils.unregister_class(cls)
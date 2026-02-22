import bpy
import os
import urllib.request
import json
import zipfile
import shutil
import tempfile

class LIGHTINGMOD_OT_update_addon(bpy.types.Operator):
    bl_idname = "lightingmod.update_addon"
    bl_label  = "Update Addon"
    bl_description = "Downloads and installs the latest release from GitHub"

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

        try:
            self.report({'INFO'}, "Checking GitHub for updates...")
            req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
            
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
                
            # If experimental, API returns a list. Pick the newest one [0].
            release_data = data[0] if isinstance(data, list) else data
            tag_name = release_data.get('tag_name', 'Unknown')
            assets = release_data.get('assets', [])
            
            # Find the ZIP asset
            download_url = None
            for asset in assets:
                if asset.get('name') == 'AdvancedLighting.zip':
                    download_url = asset.get('browser_download_url')
                    break
                    
            if not download_url:
                self.report({'ERROR'}, f"No AdvancedLighting.zip found in release {tag_name}.")
                return {'CANCELLED'}

            self.report({'INFO'}, f"Downloading version {tag_name}...")
            
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
                
            def draw(self, context):
                self.layout.label(text=f"Successfully updated to version {tag_name}.")
                self.layout.label(text="Please restart Blender to apply changes.")
            context.window_manager.popup_menu(draw, title="Update Complete", icon='INFO')
            
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
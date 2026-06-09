import bpy
import os
import urllib.request
import json
import zipfile
import shutil
import tempfile
import sys
import threading

# --- BACKGROUND THREAD WORKER ---
def update_worker(download_url, addon_dir, state):
    try:
        state['status'] = "Connecting to GitHub..."
        req = urllib.request.Request(download_url, headers={'User-Agent': 'Mozilla/5.0'})
        
        with urllib.request.urlopen(req) as response:
            total_size = int(response.getheader('Content-Length', '0'))
            
            with tempfile.TemporaryDirectory() as temp_dir:
                zip_path = os.path.join(temp_dir, "update.zip")
                
                with open(zip_path, 'wb') as out_file:
                    chunk_size = 8192
                    downloaded = 0
                    
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk: 
                            break
                        out_file.write(chunk)
                        downloaded += len(chunk)
                        
                        if total_size > 0:
                            # Cap download phase at 90% so the bar doesn't hang at 100% while extracting
                            state['progress'] = min(0.9, downloaded / total_size)
                            state['status'] = f"Downloading Update... {int((downloaded/total_size)*100)}%"
                
                state['status'] = "Extracting files..."
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
                    
                state['status'] = "Installing..."
                inner_folder = os.path.join(temp_dir, "AdvancedLighting")
                shutil.copytree(inner_folder, addon_dir, dirs_exist_ok=True)
                
        state['progress'] = 1.0
        state['status'] = "Done"
        state['is_done'] = True
        
    except Exception as e:
        state['error'] = str(e)
        state['is_done'] = True


# --- MODAL PROGRESS BAR & INSTALLER ---
class ADVLIGHTING_OT_perform_update(bpy.types.Operator):
    bl_idname = "advlighting.perform_update"
    bl_label = "Update Advanced Lighting"
    
    download_url: bpy.props.StringProperty()
    tag_name: bpy.props.StringProperty()
    local_version_str: bpy.props.StringProperty()
    
    _timer = None
    _state = None

    def invoke(self, context, event):
        # Spawns a native popup dialog asking the user to confirm the update
        return context.window_manager.invoke_props_dialog(self, width=400)
        
    def draw(self, context):
        layout = self.layout
        layout.label(text=f"A new update is available: {self.tag_name}", icon='INFO')
        layout.label(text=f"You are currently on v{self.local_version_str}")
        layout.separator()
        layout.label(text="Click OK to download and install this update.")
        layout.label(text="Blender will remain fully responsive during the download.")

    def execute(self, context):
        addon_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        
        # Create a shared state dictionary for the thread to communicate with Blender
        self._state = {
            'progress': 0.0,
            'status': "Starting download...",
            'is_done': False,
            'error': None
        }
        
        # Start Blender Native Progress Bar & Timer
        self._timer = context.window_manager.event_timer_add(0.1, window=context.window)
        context.window_manager.modal_handler_add(self)
        context.window_manager.progress_begin(0, 100)
        
        # Spawn Background Thread
        t = threading.Thread(target=update_worker, args=(self.download_url, addon_dir, self._state))
        t.daemon = True
        t.start()
        
        return {'RUNNING_MODAL'}
        
    def modal(self, context, event):
        if event.type == 'TIMER':
            # Update the progress bar and header text
            context.window_manager.progress_update(int(self._state['progress'] * 100))
            if context.area:
                context.area.header_text_set(self._state['status'])
            
            # Check if thread is finished
            if self._state['is_done']:
                context.window_manager.progress_end()
                context.window_manager.event_timer_remove(self._timer)
                if context.area:
                    context.area.header_text_set(None) 
                
                if self._state['error']:
                    self.report({'ERROR'}, f"Update Failed: {self._state['error']}")
                else:
                    # Save the tag name to a local variable to prevent 'self' scope clashing
                    updated_tag = self.tag_name 
                    
                    def draw_success(popup, ctx):
                        popup.layout.label(text=f"Successfully updated to {updated_tag}.")
                        popup.layout.label(text="Please restart Blender to apply changes.")
                        
                    context.window_manager.popup_menu(draw_success, title="Update Complete", icon='CHECKMARK')
                    self.report({'INFO'}, "Update complete. Restart Blender.")
                    
                return {'FINISHED'}
                
        return {'PASS_THROUGH'}


# --- THE FAST GITHUB CHECKER ---
class ADVLIGHTING_OT_update_addon(bpy.types.Operator):
    bl_idname = "advlighting.update_addon"
    bl_label  = "Check for Updates"
    bl_description = "Checks GitHub for updates and installs if a newer version is available"

    def execute(self, context):
        repo_url = "https://github.com/PM42-Work/Lightingmod"
        parts = repo_url.rstrip("/").split("/")
        github_user = parts[-2]
        github_repo = parts[-1]
        
        addon_name = __package__.split('.')[0]
        prefs = context.preferences.addons[addon_name].preferences
        use_experimental = prefs.use_experimental_updates
        
        if use_experimental:
            api_url = f"https://api.github.com/repos/{github_user}/{github_repo}/releases"
        else:
            api_url = f"https://api.github.com/repos/{github_user}/{github_repo}/releases/latest"

        try:
            local_version = sys.modules[addon_name].bl_info.get('version', (0, 0, 0))
        except Exception:
            local_version = (0, 0, 0)

        try:
            self.report({'INFO'}, "Checking GitHub for updates...")
            req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
            
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
                
            release_data = data[0] if isinstance(data, list) else data
            tag_name = release_data.get('tag_name', 'Unknown')
            
            clean_tag = tag_name.lstrip('v').split('-')[0]
            try:
                remote_version = tuple(map(int, clean_tag.split('.')))
            except ValueError:
                remote_version = (0, 0, 0)
            
            local_version_str = ".".join(map(str, local_version))
            
            # Compare Versions
            if remote_version <= local_version:
                def draw_uptodate(self, ctx):
                    self.layout.label(text=f"You are already on the latest version (v{local_version_str}).")
                    if use_experimental and '-' not in tag_name:
                        self.layout.label(text="(No experimental pre-releases found on GitHub).")
                context.window_manager.popup_menu(draw_uptodate, title="Up to Date", icon='INFO')
                self.report({'INFO'}, "Addon is up to date.")
                return {'FINISHED'}

            # Get Download URL
            assets = release_data.get('assets', [])
            download_url = None
            for asset in assets:
                if asset.get('name') == 'AdvancedLighting.zip':
                    download_url = asset.get('browser_download_url')
                    break
                    
            if not download_url:
                self.report({'ERROR'}, f"No AdvancedLighting.zip found in release {tag_name}.")
                return {'CANCELLED'}

            # Instantly launch the Modal Download Dialog
            bpy.ops.advlighting.perform_update('INVOKE_DEFAULT', 
                download_url=download_url, 
                tag_name=tag_name, 
                local_version_str=local_version_str
            )
            
        except urllib.error.HTTPError as e:
            self.report({'ERROR'}, f"GitHub API Error: {e.code}. Check repository link/visibility.")
            return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Update failed: {str(e)}")
            return {'CANCELLED'}

        return {'FINISHED'}

classes = (
    ADVLIGHTING_OT_perform_update,
    ADVLIGHTING_OT_update_addon,
)

def register():
    for cls in classes: bpy.utils.register_class(cls)
def unregister():
    for cls in reversed(classes): bpy.utils.unregister_class(cls)
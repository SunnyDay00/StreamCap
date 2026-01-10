import asyncio
import os
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import flet as ft
from dotenv import find_dotenv, load_dotenv

from ...utils.logger import logger
from ..base_page import PageBase as BasePage

dotenv_path = find_dotenv()
load_dotenv(dotenv_path)
VIDEO_API_EXTERNAL_URL = os.getenv("VIDEO_API_EXTERNAL_URL")


class StoragePage(BasePage):
    def __init__(self, app):
        super().__init__(app)
        self.page_name = "storage"
        self.root_path = None
        self.current_path = None
        self.path_display = None
        self.content = None
        self.file_list = None
        self._ = {}
        self.executor = ThreadPoolExecutor(max_workers=4)
        # self.processing_files = set() # Track files currently being processed -> Moved to TranscriptionManager
        self.load_language()
        self.app.language_manager.add_observer(self)
        
        self.app.language_manager.add_observer(self)
        
        self.transcription_manager = self.app.transcription_manager

    async def load(self):
        try:
            self.root_path = self.app.settings.get_video_save_path()
            if self.current_path is None or not os.path.exists(self.current_path):
                self.current_path = self.root_path
            self.setup_ui()
            await self.update_file_list()
        except Exception as e:
            logger.error(f"Error loading StoragePage: {e}")
            self.app.content_area.controls = [ft.Text(f"Error loading page: {e}", color=ft.Colors.RED)]
            self.app.content_area.update()

    def setup_ui(self):
        self.path_display = ft.Text(
            self._["storage_path"] + ": " + self.current_path,
            size=14,
            color=ft.Colors.GREY_600,
            selectable=True,
        )
        
        # Action Bar
        self.action_bar = ft.Row(
            controls=[
                ft.ElevatedButton(self._["identify_all"], icon=ft.icons.ALL_INCLUSIVE, on_click=self.on_identify_all),
                ft.ElevatedButton(self._["identify_remaining"], icon=ft.icons.FILTER_ALT, on_click=self.on_identify_remaining),
                ft.ElevatedButton(self._.get("identify_all_durations", "识别全部时长"), icon=ft.icons.TIMER, on_click=self.on_identify_durations),
                ft.ElevatedButton(self._["batch_export"], icon=ft.icons.SAVE_ALT, on_click=self.on_batch_export),
            ],
            spacing=10,
        )
        
        self.file_list = ft.ListView(expand=True, spacing=2, padding=10)
        self.content = ft.Column(controls=[self.path_display, self.action_bar, self.file_list])
        self.app.content_area.controls = [self.content]
        self.app.content_area.update()

    def load_language(self):
        language = self.app.language_manager.language
        for key in ("storage_page", "base"):
            self._.update(language.get(key, {}))

    async def update_file_list(self):
        # Optimization: Don't update UI if this page is not currently displayed
        if self.app.current_page != self:
            return

        try:
            self.path_display.value = self._["current_path"] + ":" + self.current_path
            self.file_list.controls.clear()

            # Navigation / Tool Bar
            nav_controls = []
            
            # Back Button
            if self.current_path != self.root_path:
                back_button = ft.ElevatedButton(
                    self._["go_back"],
                    icon=ft.icons.ARROW_BACK,
                    on_click=lambda _: self.app.page.run_task(self.navigate_to_parent)
                )
                if self.app.is_mobile:
                    # Mobile simplified view
                    # For mobile, we might just stick to list tile, but for now specific logic:
                     back_item = ft.ListTile(
                        leading=ft.Icon(ft.icons.ARROW_BACK, color=ft.colors.BLUE),
                        title=ft.Text(self._["go_back"]),
                        on_click=lambda _: self.app.page.run_task(self.navigate_to_parent),
                    )
                     nav_controls.append(back_item)
                else:
                    nav_controls.append(back_button)
            
            if not self.app.is_mobile: 
                 # Desktop Navigation Row
                 # Add Spacer
                 nav_controls.append(ft.Container(expand=True))
                 
                 # Refresh Button
                 refresh_btn = ft.TextButton(
                     self._.get("refresh_interface", "Refresh"),
                     icon=ft.icons.REFRESH,
                     on_click=lambda _: self.app.page.run_task(self.update_file_list)
                 )
                 nav_controls.append(refresh_btn)
                 
                 # Wrap in row
                 # Note: If we had mobile item, nav_controls has a ListTile. We shouldn't put ListTile in Row like this.
                 # Splitting logic clean:
                 
                 if nav_controls:
                     # Filter out non-controls if any
                     final_controls = [c for c in nav_controls if isinstance(c, ft.Control)]
                     
                     nav_row = ft.Row(
                         controls=final_controls,
                         alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                     )
                     self.file_list.controls.append(nav_row)
            else:
                 # Mobile: Just append back item if exists
                 for c in nav_controls:
                     self.file_list.controls.append(c)

            exists, is_empty = await self.check_directory()
            if not exists or is_empty:
                self.show_empty_folder_message()
            else:
                await self.create_file_buttons()
            
        except Exception as e:
            logger.error(f"Error updating file list: {e}")
            await self.app.snack_bar.show_snack_bar(self._["file_list_update_error"])
        finally:
            if self.file_list.page:
                try:
                    self.file_list.update()
                except Exception as e:
                    logger.warning(f"Failed to update file list: {e}")

    async def check_directory(self):
        def _check():
            if not os.path.exists(self.current_path):
                return False, True
            try:
                with os.scandir(self.current_path) as it:
                    return True, not any(True for _ in it)
            except Exception:
                return False, True

        return await asyncio.get_event_loop().run_in_executor(self.executor, _check)

    def on_identify_all(self, e):
        self.app.page.run_task(self.batch_identify, True)

    def on_identify_remaining(self, e):
         self.app.page.run_task(self.batch_identify, False)

    def on_batch_export(self, e):
        self.app.page.run_task(self.batch_export)

    def on_identify_durations(self, e):
        self.app.page.run_task(self.batch_identify_durations)


    def _is_supported_media(self, filename: str) -> bool:
        ext = os.path.splitext(filename)[1].lower()
        return ext in ['.mp3', '.wav', '.m4a', '.mp4', '.mov', '.mkv', 
                       '.flv', '.wma', '.aac', '.flac', '.avi', '.ts', '.webm']

    async def batch_identify(self, process_all=False):
        files_to_process = []
        try:
             with os.scandir(self.current_path) as it:
                for entry in it:
                    if entry.is_file():
                        if self._is_supported_media(entry.name):
                            if process_all or not self.transcription_manager.has_text(entry.path):
                                files_to_process.append(entry.path)
        except Exception as e:
            logger.error(f"Error scanning files: {e}")
            return

        if not files_to_process:
             await self.app.snack_bar.show_snack_bar(self._["no_files_to_process"])
             return

        # Mark all as processing
        # for path in files_to_process:
        #     self.processing_files.add(path)
        
        await self.update_file_list()
        
        # Start background processing task
        async def process_batch():
            try:
                # 1. Determine Concurrency Mode
                use_cloud = self.app.config_manager.get_config_value("enable_cloud_stt", False)
                
                # Cloud: Supports parallel processing (Limit to 5 to be safe with bandwidth/connections)
                # Local: Strictly sequential to avoid CPU/GPU contention
                concurrency = 5 if use_cloud else 1
                semaphore = asyncio.Semaphore(concurrency)
                
                if use_cloud:
                     await self.app.snack_bar.show_snack_bar(f"Starting Cloud Batch (Concurrency: {concurrency})")
                else:
                     # Check local models readiness before starting loop if using local
                     from ...core.stt.local_stt import LocalSTTService
                     stt_service = LocalSTTService(self.app.config_manager)
                     is_ready, _ = stt_service.check_models_status()
                     if not is_ready:
                          await self.update_file_list()
                          await self.app.snack_bar.show_snack_bar(self._["go_to_configure_models"], bgcolor=ft.Colors.RED)
                          return

                # 2. Worker Function
                async def worker(file_path):
                    async with semaphore:
                        try:
                            # Use Manager to handle Cloud/Local switch + AI Optimization + Saving
                            await self.transcription_manager.transcribe_file(file_path, self.executor)
                        except Exception as e:
                            logger.error(f"Failed to transcribe {file_path}: {e}")
                        finally:
                            # Update UI incrementally to show completion status
                            if self.app.current_page == self:
                                try:
                                    await self.update_file_list()
                                except Exception:
                                    pass

                # 3. Launch Tasks
                tasks = [asyncio.create_task(worker(fp)) for fp in files_to_process]
                
                # Monitor progress (Optional enhancement: Progress Bar)
                # For now, wait for all
                await asyncio.gather(*tasks)

            except Exception as e:
                 logger.error(f"Batch processing error: {e}")
            finally:
                if self.app.current_page == self:
                    try:
                        await self.update_file_list()
                        await self.app.snack_bar.show_snack_bar(self._["identification_complete"])
                    except Exception:
                        pass

        # Fire and forget
        self.app.page.run_task(process_batch)


    async def batch_export(self):
        export_content = ""
        has_content = False
        try:
            with os.scandir(self.current_path) as it:
                entries = sorted(it, key=lambda e: e.name)
                for entry in entries:
                    # Specific user request: Only read TXT files in current directory
                    if entry.is_file() and entry.name.lower().endswith(".txt"):
                        try:
                            # Avoid reading the export file itself if typically named 'export...'
                            # But here we read everything that is .txt.
                            with open(entry.path, "r", encoding="utf-8") as f:
                                text = f.read()
                                if text.strip():
                                    has_content = True
                                    export_content += f"=== {entry.name} ===\n{text}\n\n"
                        except Exception as e:
                            logger.error(f"Error reading {entry.name}: {e}")
                            
        except Exception as e:
            logger.error(f"Error gathering texts: {e}")
            return

        if not has_content:
            await self.app.snack_bar.show_snack_bar(self._["no_transcriptions_to_export"])
            return

        # Fix: Ensure content is treated as string and file picker is properly awaited/handled
        # Note: FilePicker result event is async, but save_file is non-blocking to UI.
        
        file_picker = ft.FilePicker()
        def on_result(e):
             self.app.page.run_task(self._on_batch_export_result, e, export_content)
        
        file_picker.on_result = on_result
        self.app.page.overlay.append(file_picker)
        self.app.page.update()
        
        # Use directory name as default filename
        dir_name = os.path.basename(self.current_path) or "export"
        default_name = f"{dir_name}.txt"
        file_picker.save_file(allowed_extensions=["txt"], file_name=default_name)

    def did_mount(self):
        super().did_mount()
        self.app.page.pubsub.subscribe(self.on_message)

    def will_unmount(self):
        self.app.page.pubsub.unsubscribe_all(self.on_message)
        super().will_unmount()

    def on_message(self, message):
        if message == "storage_update":
            if self.page:
                 self.app.page.run_task(self.update_file_list)
    async def _on_batch_export_result(self, e: ft.FilePickerResultEvent, content: str):
        if e.path:
            try:
                with open(e.path, "w", encoding="utf-8") as f:
                    f.write(content)
                await self.app.snack_bar.show_snack_bar(self._["batch_export_success"])
            except Exception as ex:
                logger.error(f"Batch export failed: {ex}")
                await self.app.snack_bar.show_snack_bar(f"Export failed: {ex}", bgcolor=ft.Colors.RED)


    async def identify_text(self, file_path):
        # Check history
        if self.transcription_manager.has_text(file_path):
            # Confirmation Dialog
            async def on_yes(e):
                self.app.page.close(confirm_dialog)
                await self._start_identification_task(file_path)
            
            def on_no(e):
                 self.app.page.close(confirm_dialog)
            
            confirm_dialog = ft.AlertDialog(
                title=ft.Text(self._["reidentify_confirm_title"]),
                content=ft.Text(self._["reidentify_confirm_content"]),
                actions=[
                    ft.TextButton(self._["yes"], on_click=on_yes),
                    ft.TextButton(self._["no"], on_click=on_no),
                ],
            )
            self.app.page.open(confirm_dialog)
            self.app.page.update()
            return
        
        await self._start_identification_task(file_path)
    
    async def _start_identification_task(self, file_path):
        # Add to processing MANUALLY to ensure UI shows spinner immediately
        self.transcription_manager.mark_processing(file_path)
        await self.update_file_list()
        
        # Run actual logic
        self.app.page.run_task(self._do_identify_bg, file_path)

    async def _do_identify_bg(self, file_path):
        try:
             await self.transcription_manager.transcribe_file(file_path, self.executor)
        except Exception as e:
            logger.error(f"Identify text failed: {e}")
            if "Models are not ready" in str(e):
                 await self.app.snack_bar.show_snack_bar(self._["go_to_configure_models"], bgcolor=ft.Colors.RED)
            else:
                 await self.app.snack_bar.show_snack_bar(f"{self._['identification_failed']}: {e}", bgcolor=ft.Colors.RED)
        finally:
            # Manually trigger update to remove spinner and show result
            await self.update_file_list()

    def show_transcription_result(self, file_path):
        text = self.transcription_manager.get_text(file_path)
        if not text:
            return

        metadata = self.transcription_manager.get_metadata(file_path)
        is_ai_optimized = metadata.get("ai_optimized", False)

        def copy_to_clipboard(e):
            self.app.page.set_clipboard(text)
            self.app.snack_bar.show_snack_bar(self._["copy_success"])

        title_content = ft.Row([
            ft.Text(self._["identification_result"], size=20, weight=ft.FontWeight.BOLD),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        # Badge Container (Right side of title)
        badge_row = ft.Row(spacing=5, alignment=ft.MainAxisAlignment.END)

        if is_ai_optimized:
            badge_row.controls.append(
                ft.Container(
                    content=ft.Text(self._.get("ai_optimized_label", "AI 优化"), size=10, color=ft.Colors.WHITE),
                    bgcolor=ft.Colors.BLUE,
                    padding=5,
                    border_radius=5
                )
            )

        source = metadata.get("source")
        if source:
             # Localize source
             source_key = f"source_{source}"
             source_label = self._.get(source_key, source.capitalize()) 
             # Manual fallback if key missing for common ones
             if source == "cloud" and source_key not in self._:
                 source_label = "云端"
                 
             source_color = ft.Colors.PURPLE if source == "cloud" else ft.Colors.TEAL
             badge_row.controls.append(
                ft.Container(
                    content=ft.Text(source_label, size=10, color=ft.Colors.WHITE),
                    bgcolor=source_color,
                    padding=5,
                    border_radius=5
                )
             )
        
        # Add badge row to title content
        title_content.controls.append(badge_row)

        result_dialog = ft.AlertDialog(
            title=title_content,
            content=ft.Column(
                [
                    ft.TextField(
                        value=text,
                        multiline=True,
                        min_lines=5,
                        max_lines=15,
                        read_only=True,
                        text_size=14,
                    )
                ],
                width=600,
                scroll=ft.ScrollMode.AUTO,
                tight=True,
            ),
            actions=[
                ft.TextButton(self._["copy_text"], on_click=copy_to_clipboard),
                ft.TextButton(self._["close"], on_click=lambda e: self.app.page.close(result_dialog)),
            ],
        )
        self.app.page.open(result_dialog)
        self.app.page.update()

    def view_history(self, file_path):
        if self.transcription_manager.has_text(file_path):
            self.show_transcription_result(file_path)

    def export_text_file(self, file_path):
        text = self.transcription_manager.get_text(file_path)
        if not text:
             return
        
        file_picker = ft.FilePicker()
        def on_result(e):
            self.app.page.run_task(self._on_export_result, e, text)
            
        file_picker.on_result = on_result
        self.app.page.overlay.append(file_picker)
        self.app.page.update()
        
        default_name = os.path.splitext(os.path.basename(file_path))[0] + ".txt"
        file_picker.save_file(allowed_extensions=["txt"], file_name=default_name)

    async def _on_export_result(self, e, text):
         if e.path:
            try:
                with open(e.path, "w", encoding="utf-8") as f:
                    f.write(text)
                await self.app.snack_bar.show_snack_bar(self._["export_success"])
            except Exception as ex:
                logger.error(f"Export failed: {ex}")

    def _extract_duration(self, filename: str) -> str | None:
        """Extract duration from filename (FORMAT: _HHhMMmSSs)"""
        name, _ = os.path.splitext(filename)
        # Search for pattern at end of string: _00h00m36s
        match = re.search(r"_(\d+h\d+m\d+s)$", name)
        if match:
             return match.group(1)
        return None

    async def create_file_buttons(self):
        def _get_items():
            try:
                _items = []
                if not os.path.exists(self.current_path):
                    return []
                with os.scandir(self.current_path) as it:
                    for entry in it:
                        # Filter out .txt, .meta, and .part files
                        if entry.is_file() and (entry.name.lower().endswith(".txt") or entry.name.lower().endswith(".meta") or entry.name.lower().endswith(".part")):
                            continue
                        _items.append((entry.name, entry.is_dir(), entry.path))
                return sorted(_items, key=lambda x: (-x[1], x[0].lower()))
            except Exception as e:
                logger.error(f"Error listing directory: {e}")
                return []

        items = await asyncio.get_event_loop().run_in_executor(self.executor, _get_items)
        
        controls_list = []
        is_mobile = self.app.is_mobile
        for name, is_dir, full_path in items:
            if is_mobile:
                icon = ft.Icon(ft.icons.FOLDER, color=ft.colors.BLUE) if is_dir else ft.Icon(ft.icons.INSERT_DRIVE_FILE)
                # Mobile view simplification omitted for brevity, keeping existing logic
                item = ft.ListTile(
                    leading=icon,
                    title=ft.Text(name),
                    on_click=lambda e, path=full_path, is_directory=is_dir: self.app.page.run_task(
                        self.navigate_to if is_directory else self.preview_file, 
                        path
                    ),
                )
                controls_list.append(item)
            else:
                if is_dir:
                    btn = ft.ElevatedButton(
                        f"📁 {name}",
                        on_click=lambda e, path=full_path: self.app.page.run_task(self.navigate_to, path),
                        style=ft.ButtonStyle(
                            shape=ft.RoundedRectangleBorder(radius=10),
                            alignment=ft.alignment.center_left,
                        ),
                    )
                    controls_list.append(ft.Row([ft.Container(content=btn, expand=True)]))

                else:
                    ext = os.path.splitext(name)[1].lower()
                    icon_str = "📄"  # Default generic file icon
                    
                    if ext in ['.mp3', '.wav', '.m4a', '.flac', '.aac', '.wma']:
                        icon_str = "🎵"
                    elif ext in ['.mp4', '.mov', '.mkv', '.flv', '.avi', '.ts', '.webm']:
                        icon_str = "🎬"

                    file_btn = ft.ElevatedButton(
                        f"{icon_str} {name}",
                        on_click=lambda e, path=full_path: self.app.page.run_task(self.preview_file, path),
                        style=ft.ButtonStyle(
                            shape=ft.RoundedRectangleBorder(radius=10),
                            alignment=ft.alignment.center_left,
                        ),
                    )
                    
                    row_controls = [ft.Container(content=file_btn, expand=True)]
                    
                    # Add Duration Display for media files
                    if self._is_supported_media(name):
                         duration_str = self._extract_duration(name)
                         
                         unknown_label = self._.get("unknown_duration", "Unknown")
                         
                         if duration_str:
                             # Format: 00h00m36s
                             # Parse and localize
                             match = re.match(r"(\d+)h(\d+)m(\d+)s", duration_str)
                             if match:
                                 h, m, s = map(int, match.groups())
                                 
                                 # Format based on simplified keys or hardcoded if keys missing
                                 # We assume keys "unit_h", "unit_m", "unit_s" exist or fallback
                                 u_h = self._.get("unit_h", "h")
                                 u_m = self._.get("unit_m", "m")
                                 u_s = self._.get("unit_s", "s")
                                 
                                 # Smart formatting: hide 0h if 0
                                 if h > 0:
                                     display_time = f"{h}{u_h}{m}{u_m}{s}{u_s}"
                                 elif m > 0:
                                     display_time = f"{m}{u_m}{s}{u_s}"
                                 else:
                                     display_time = f"{s}{u_s}"
                             else:
                                 display_time = duration_str
                         else:
                             display_time = unknown_label
                         
                         # UI Improvement: Chip/Badge style
                         # UI Improvement: Chip/Badge style
                         duration_badge = ft.Container(
                             content=ft.Row(
                                 [
                                     ft.Icon(ft.icons.ACCESS_TIME, size=14, color=ft.Colors.GREY_600),
                                     ft.Text(display_time, size=12, color=ft.Colors.GREY_700, weight=ft.FontWeight.W_500)
                                 ],
                                 alignment=ft.MainAxisAlignment.CENTER,
                                 spacing=2
                             ),
                             bgcolor=ft.Colors.GREY_100,
                             padding=ft.padding.symmetric(horizontal=8, vertical=4),
                             border_radius=12,
                             width=110,  # Fixed width for duration badge container (content centered)
                             on_click=lambda e, path=full_path: self.app.page.run_task(self.update_file_duration, path),
                             tooltip=self._.get("click_to_update_duration", "点击更新时长"),
                             ink=True,
                         )
                         
                         row_controls.append(
                             ft.Container(
                                 content=duration_badge,
                                 padding=ft.padding.only(right=10),
                             )
                         )
                    
                    # Logic to identify if it's a media file that supports transcription
                    if self._is_supported_media(name):
                         
                         action_buttons = []
                         if self.transcription_manager.is_processing(full_path):
                             # Show processing state
                             # For processing, we can put it in the same action container or separate?
                             # Let's put in action container to keep alignment.
                             action_buttons.append(ft.ProgressRing(width=20, height=20, stroke_width=2))
                             action_buttons.append(ft.Text(self._["identifying"], italic=True, color=ft.Colors.BLUE))
                         else:
                             has_transcription = self.transcription_manager.has_text(full_path)
                             
                             identify_label = self._["reidentify_text"] if has_transcription else self._["identify_text"]
                             identify_btn = ft.ElevatedButton(
                                identify_label,
                                icon=ft.icons.TEXT_SNIPPET,
                                on_click=lambda e, path=full_path: self.app.page.run_task(self.identify_text, path)
                             )
                             
                             if has_transcription:
                                 history_btn = ft.ElevatedButton(
                                     self._["view_text"],
                                     icon=ft.icons.DESCRIPTION,
                                     on_click=lambda e, path=full_path: self.view_history(path)
                                 )
                                 export_btn = ft.IconButton(
                                     icon=ft.icons.SAVE_ALT,
                                     tooltip=self._["export_text"],
                                     on_click=lambda e, path=full_path: self.export_text_file(path)
                                 )
                                 action_buttons.append(history_btn)
                                 action_buttons.append(export_btn)
                             
                             action_buttons.append(identify_btn)
                         
                         # Fixed width container for actions to ensure file button has uniform width
                         actions_container = ft.Container(
                             content=ft.Row(action_buttons, alignment=ft.MainAxisAlignment.END, spacing=5),
                             width=280, 
                             alignment=ft.alignment.center_right
                         )
                         row_controls.append(actions_container)
                         
                    controls_list.append(ft.Row(row_controls))

        self.file_list.controls.extend(controls_list)
    def show_empty_folder_message(self):
        self.file_list.controls.append(
            ft.Card(
                content=ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Icon(ft.icons.FOLDER_OPEN),
                            ft.Text(self._["empty_recording_folder"], size=16, weight=ft.FontWeight.BOLD)
                        ],
                        alignment=ft.MainAxisAlignment.CENTER
                    ),
                    padding=20
                ),
                elevation=2,
                margin=10,
                width=400
            )
        )

    async def navigate_to(self, path):
        self.current_path = path
        self.path_display.value = self._["current_path"] + ":" + self.current_path
        await self.update_file_list()
        self.content.update()

    async def navigate_to_parent(self):
        self.current_path = os.path.dirname(self.current_path)
        self.path_display.value = self._["current_path"] + ":" + self.current_path
        await self.update_file_list()
        self.content.update()

    async def open_external_player(self, file_path):
        """Open file with system default player"""
        try:
            if self.app.page.platform == "windows":
                os.startfile(file_path)
            elif self.app.page.platform == "macos":
                import subprocess
                subprocess.run(["open", file_path])
            else: # linux
                import subprocess
                subprocess.run(["xdg-open", file_path])
            await self.app.snack_bar.show_snack_bar(self._.get("opened_external", "Opened in system player"))
        except Exception as e:
            logger.error(f"Failed to open external player: {e}")
            await self.app.snack_bar.show_snack_bar(f"Failed to open: {e}")

    async def preview_file(self, file_path, room_url=None):
        import urllib.parse
        
        # Check setting: Use System Player
        if self.app.settings.user_config.get("use_system_player", False) and not self.app.page.web:
             await self.open_external_player(file_path)
             return

        from ..components.business.video_player import VideoPlayer

        video_player = VideoPlayer(self.app)

        if self.app.page.web:
            if not VIDEO_API_EXTERNAL_URL:
                logger.error("VIDEO_API_EXTERNAL_URL is not set in .env")
                await self.app.snack_bar.show_snack_bar(self._["video_api_server_not_set"])
                return

            relative_path = os.path.relpath(file_path, self.root_path)
            filename = urllib.parse.quote(os.path.basename(file_path))
            subfolder = urllib.parse.quote(os.path.dirname(relative_path).replace("\\", "/"))
            api_url = f"{VIDEO_API_EXTERNAL_URL}/api/videos?filename={filename}&subfolder={subfolder}"
            await video_player.preview_video(api_url, is_file_path=False, room_url=room_url)
        else:
            await video_player.preview_video(file_path, is_file_path=True, room_url=room_url)

    async def update_file_duration(self, file_path):
        """Calculate duration and rename file with duration suffix"""
        if not os.path.exists(file_path):
            return

        await self.app.snack_bar.show_snack_bar(self._.get("calculating_duration", "正在计算时长..."))
        
        try:
            from ...utils import utils
            # Run duration check in thread
            duration_str = await asyncio.get_event_loop().run_in_executor(
                None, utils.get_media_duration, file_path
            )

            if not duration_str:
                await self.app.snack_bar.show_snack_bar(self._.get("duration_update_failed", "时长更新失败"))
                return

            # Construct new filename
            directory = os.path.dirname(file_path)
            filename = os.path.basename(file_path)
            name_without_ext, ext = os.path.splitext(filename)
            
            # Remove existing duration pattern if present (e.g., _01h20m30s)
            # Pattern: _\d{2}h\d{2}m\d{2}s at the end of name
            name_clean = re.sub(r"_\d{2}h\d{2}m\d{2}s$", "", name_without_ext)
            
            # Format: original_name_HHhMMmSSs.ext
            new_filename = f"{name_clean}_{duration_str}{ext}"
            new_full_path = os.path.join(directory, new_filename)
            
            if new_full_path != file_path:
                if self._rename_with_associated_files(file_path, new_full_path):
                    await self.app.snack_bar.show_snack_bar(self._.get("duration_update_success", "时长更新成功"))
                    await self.update_file_list()
            else:
                 await self.app.snack_bar.show_snack_bar("时长未变化")

        except Exception as e:
            logger.error(f"Error updating duration: {e}")
            await self.app.snack_bar.show_snack_bar(f"{self._.get('duration_update_failed', '时长更新失败')}: {e}")

    async def batch_identify_durations(self):
        """Identify durations for all eligible files in current directory"""
        files_to_process = []
        try:
            with os.scandir(self.current_path) as it:
                for entry in it:
                     if entry.is_file():
                        if self._is_supported_media(entry.name):
                            files_to_process.append(entry.path)
        except Exception as e:
             logger.error(f"Error scanning for durations: {e}")
             return

        if not files_to_process:
             await self.app.snack_bar.show_snack_bar(self._.get("no_files_to_process", "没有文件需要处理"))
             return

        await self.app.snack_bar.show_snack_bar(self._.get("identifying_durations", "正在识别时长..."))
        
        count = 0
        from ...utils import utils
        
        for file_path in files_to_process:
            if not os.path.exists(file_path):
                continue

            try:
                # Synchronous duration check
                duration_str = await asyncio.get_event_loop().run_in_executor(
                    None, utils.get_media_duration, file_path
                )
                
                if duration_str:
                    directory = os.path.dirname(file_path)
                    filename = os.path.basename(file_path)
                    name_without_ext, ext = os.path.splitext(filename)
                    
                    name_clean = re.sub(r"_\d{2}h\d{2}m\d{2}s$", "", name_without_ext)
                    new_filename = f"{name_clean}_{duration_str}{ext}"
                    new_full_path = os.path.join(directory, new_filename)
                    
                    if new_full_path != file_path:
                        if self._rename_with_associated_files(file_path, new_full_path):
                            count += 1
            except Exception as e:
                logger.error(f"Failed to update duration for {file_path}: {e}")
        
        if count > 0:
             await self.update_file_list()
             await self.app.snack_bar.show_snack_bar(f"{self._.get('duration_identification_complete', '时长识别完成')}: Updated {count} files")
        else:
             await self.app.snack_bar.show_snack_bar("没有文件需要更新")

    def _rename_with_associated_files(self, old_path, new_path) -> bool:
        """Rename media file and its associated text/meta files"""
        try:
            # 1. Rename the main file
            if os.path.exists(old_path):
                os.rename(old_path, new_path)
                logger.info(f"Renamed main file: {old_path} -> {new_path}")
            else:
                return False
            
            # 2. Rename associated files
            old_base = os.path.splitext(old_path)[0]
            new_base = os.path.splitext(new_path)[0]
            
            associated_exts = ['.txt', '.meta']
            
            # Rename standard extensions
            for ext in associated_exts:
                old_assoc = old_base + ext
                new_assoc = new_base + ext
                if os.path.exists(old_assoc):
                    os.rename(old_assoc, new_assoc)
                    logger.info(f"Renamed associated: {old_assoc} -> {new_assoc}")
            
            # Rename AI optimized file: filename_AI.txt
            old_ai = f"{old_base}_AI.txt"
            new_ai = f"{new_base}_AI.txt"
            if os.path.exists(old_ai):
                 os.rename(old_ai, new_ai)
                 logger.info(f"Renamed AI text: {old_ai} -> {new_ai}")

            return True
        except Exception as e:
            logger.error(f"Error during rename chain: {e}")
            return False



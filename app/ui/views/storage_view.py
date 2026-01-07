import asyncio
import os
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
        self.processing_files = set() # Track files currently being processed
        self.load_language()
        self.app.language_manager.add_observer(self)
        
        from ...core.stt.transcription_manager import TranscriptionManager
        self.transcription_manager = TranscriptionManager(self.app.config_manager)

    async def load(self):
        try:
            self.root_path = self.app.settings.get_video_save_path()
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

            if self.current_path != self.root_path:
                back_button = ft.ElevatedButton(
                    self._["go_back"],
                    icon=ft.icons.ARROW_BACK,
                    on_click=lambda _: self.app.page.run_task(self.navigate_to_parent)
                )
                if self.app.is_mobile:
                    back_item = ft.ListTile(
                        leading=ft.Icon(ft.icons.ARROW_BACK, color=ft.colors.BLUE),
                        title=ft.Text(self._["go_back"]),
                        on_click=lambda _: self.app.page.run_task(self.navigate_to_parent),
                    )
                    self.file_list.controls.append(back_item)
                else:
                    self.file_list.controls.append(back_button)

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

    async def batch_identify(self, process_all=False):
        files_to_process = []
        try:
             with os.scandir(self.current_path) as it:
                for entry in it:
                    if entry.is_file():
                        ext = os.path.splitext(entry.name)[1].lower()
                        if ext in ['.mp3', '.wav', '.m4a', '.mp4', '.mov', '.mkv', '.flv']:
                            if process_all or not self.transcription_manager.has_text(entry.path):
                                files_to_process.append(entry.path)
        except Exception as e:
            logger.error(f"Error scanning files: {e}")
            return

        if not files_to_process:
             await self.app.snack_bar.show_snack_bar(self._["no_files_to_process"])
             return

        # Mark all as processing
        for path in files_to_process:
            self.processing_files.add(path)
        
        await self.update_file_list()
        
        # Start background processing task
        async def process_batch():
            from ...core.stt.local_stt import LocalSTTService
            stt_service = LocalSTTService(self.app.config_manager)
            
            # Check models first (quick check)
            is_ready, _ = stt_service.check_models_status()
            if not is_ready:
                 self.processing_files.clear()
                 await self.update_file_list()
                 await self.app.snack_bar.show_snack_bar(self._["go_to_configure_models"], bgcolor=ft.Colors.RED)
                 return

            # Process sequentially
            loop = asyncio.get_running_loop()
            
            for file_path in files_to_process:
                try:
                    text_result = await loop.run_in_executor(self.executor, lambda: stt_service.transcribe(file_path))
                    self.transcription_manager.set_text(file_path, text_result)
                except Exception as e:
                    logger.error(f"Failed to transcribe {file_path}: {e}")
                finally:
                    if file_path in self.processing_files:
                        self.processing_files.remove(file_path)
                    
                    # Only update UI if the page is still active/mounted
                    if self.app.current_page == self:
                        try:
                            await self.update_file_list()
                        except Exception as ex:
                            logger.warning(f"UI update failed (ignored): {ex}")

            if self.app.current_page == self:
                await self.app.snack_bar.show_snack_bar(self._["identification_complete"])

        # Fire and forget
        self.app.page.run_task(process_batch)


    async def batch_export(self):
        export_content = ""
        has_content = False
        try:
            with os.scandir(self.current_path) as it:
                entries = sorted(it, key=lambda e: e.name)
                for entry in entries:
                    if entry.is_file():
                        text = self.transcription_manager.get_text(entry.path)
                        if text:
                            has_content = True
                            export_content += f"=== {entry.name} ===\n{text}\n\n"
        except Exception as e:
            logger.error(f"Error gathering texts: {e}")
            return

        if not has_content:
            await self.app.snack_bar.show_snack_bar(self._["no_transcriptions_to_export"])
            return

        file_picker = ft.FilePicker()
        def on_result(e):
             self.app.page.run_task(self._on_batch_export_result, e, export_content)
        
        file_picker.on_result = on_result
        self.app.page.overlay.append(file_picker)
        self.app.page.update()
        file_picker.save_file(allowed_extensions=["txt"], file_name="batch_export.txt")

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
        # Add to processing and update UI to show progress row
        self.processing_files.add(file_path)
        await self.update_file_list()
        
        # Run actual logic
        await self.app.page.run_task(self._do_identify_bg, file_path)

    async def _do_identify_bg(self, file_path):
        from ...core.stt.local_stt import LocalSTTService
        stt_service = LocalSTTService(self.app.config_manager)

        is_ready, status = stt_service.check_models_status()
        if not is_ready:
             self.processing_files.discard(file_path)
             await self.update_file_list()
             await self.app.snack_bar.show_snack_bar(self._["go_to_configure_models"], bgcolor=ft.Colors.RED)
             return

        try:
            loop = asyncio.get_running_loop()
            text_result = await loop.run_in_executor(self.executor, lambda: stt_service.transcribe(file_path))
            
            self.transcription_manager.set_text(file_path, text_result)
            
            # Show result or just finish? 
            # User wants it in background. So no popup.
            # Just remove from processing and update UI (which will show View History and Export buttons)
            
        except Exception as e:
            logger.error(f"Identify text failed: {e}")
            await self.app.snack_bar.show_snack_bar(f"{self._['identification_failed']}: {e}", bgcolor=ft.Colors.RED)
        finally:
            self.processing_files.discard(file_path)
            await self.update_file_list()

    def show_transcription_result(self, text):
        def copy_to_clipboard(e):
            self.app.page.set_clipboard(text)
            self.app.snack_bar.show_snack_bar(self._["copy_success"])

        result_dialog = ft.AlertDialog(
            title=ft.Text(self._["identification_result"]),
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
        text = self.transcription_manager.get_text(file_path)
        if text:
            self.show_transcription_result(text)

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

    async def create_file_buttons(self):
        def _get_items():
            try:
                _items = []
                if not os.path.exists(self.current_path):
                    return []
                with os.scandir(self.current_path) as it:
                    for entry in it:
                        # Filter out .txt files created by transcription
                        if entry.is_file() and entry.name.lower().endswith(".txt"):
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
                    file_btn = ft.ElevatedButton(
                        f"📄 {name}",
                        on_click=lambda e, path=full_path: self.app.page.run_task(self.preview_file, path),
                        style=ft.ButtonStyle(
                            shape=ft.RoundedRectangleBorder(radius=10),
                            alignment=ft.alignment.center_left,
                        ),
                    )
                    
                    row_controls = [ft.Container(content=file_btn, expand=True)]
                    
                    # Logic to identify if it's a media file that supports transcription
                    ext = os.path.splitext(name)[1].lower()
                    if ext in ['.mp3', '.wav', '.m4a', '.mp4', '.mov', '.mkv', '.flv']:
                         
                         if full_path in self.processing_files:
                             # Show processing state
                             row_controls.append(ft.ProgressRing(width=20, height=20, stroke_width=2))
                             row_controls.append(ft.Text(self._["identifying"], italic=True, color=ft.Colors.BLUE))
                         else:
                             has_transcription = self.transcription_manager.has_text(full_path)
                             
                             identify_btn = ft.ElevatedButton(
                                self._["identify_text"],
                                icon=ft.icons.TEXT_SNIPPET,
                                on_click=lambda e, path=full_path: self.app.page.run_task(self.identify_text, path)
                             )
                             
                             if has_transcription:
                                 history_btn = ft.ElevatedButton(
                                     self._["view_history"],
                                     icon=ft.icons.HISTORY,
                                     on_click=lambda e, path=full_path: self.view_history(path)
                                 )
                                 export_btn = ft.IconButton(
                                     icon=ft.icons.SAVE_ALT,
                                     tooltip=self._["export_text"],
                                     on_click=lambda e, path=full_path: self.export_text_file(path)
                                 )
                                 
                                 row_controls.append(history_btn)
                                 row_controls.append(export_btn)
                                 row_controls.append(identify_btn) # Re-identify
                             else:
                                 row_controls.append(identify_btn)
                         
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

    async def preview_file(self, file_path, room_url=None):
        import urllib.parse

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

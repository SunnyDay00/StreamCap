import asyncio
import os

import flet as ft

from ...models.media.audio_format_model import AudioFormat
from ...models.media.video_format_model import VideoFormat
from ...models.media.video_quality_model import VideoQuality
from ...utils.delay import DelayedTaskExecutor
from ...utils.logger import logger
from ..base_page import PageBase
from ..components.dialogs.help_dialog import HelpDialog


class SettingsPage(PageBase):
    def __init__(self, app):
        super().__init__(app)
        self.page_name = "settings"
        self.config_manager = self.app.config_manager

        self.user_config = self.config_manager.load_user_config()
        self.language_option = self.config_manager.load_language_config()
        self.default_config = self.config_manager.load_default_config()
        self.user_config = self.config_manager.load_user_config()
        self.web_auth_config = self.config_manager.load_web_auth_config()
        self.cookies_config = self.config_manager.load_cookies_config()
        self.accounts_config = self.config_manager.load_accounts_config()
        self.about_config = self.config_manager.load_about_config()

        self.language_code = None
        self.default_language = None
        self.focused_control = None
        self.tab_recording = None
        self.tab_push = None
        self.tab_cookies = None
        self.tab_accounts = None
        self.tab_cloud = None
        self.tab_security = None
        self.has_unsaved_changes = {}
        self.delay_handler = DelayedTaskExecutor(self.app, self)
        self.load_language()
        self.init_unsaved_changes()
        self.page.on_keyboard_event = self.on_keyboard

    async def load(self):
        try:
            self.content_area.clean()
            language = self.app.language_manager.language
            self._ = language["settings_page"] | language["video_quality"] | language["base"]
            self.tab_recording = self.create_recording_settings_tab()
            self.tab_push = self.create_push_settings_tab()
            self.tab_cookies = self.create_cookies_settings_tab()
            self.tab_accounts = self.create_accounts_settings_tab()
            self.tab_cloud = self.create_cloud_settings_tab()
            self.page.on_keyboard_event = self.on_keyboard

            tabs = [
                ft.Tab(text=self._["recording_settings"], content=self.tab_recording),
                ft.Tab(text=self._["push_settings"], content=self.tab_push),
                ft.Tab(text=self._["cookies_settings"], content=self.tab_cookies),
                ft.Tab(text=self._["accounts_settings"], content=self.tab_accounts),
                ft.Tab(text=self._["cloud_model_settings"], content=self.tab_cloud),
                ft.Tab(text=self._["dependencies"], content=self.create_dependencies_tab()),
            ]
            
            if self.app.page.web:
                self.tab_security = self.create_security_settings_tab()
                tabs.append(ft.Tab(text=self._["security_settings"], content=self.tab_security))

            settings_tabs = ft.Tabs(
                selected_index=0,
                animation_duration=300,
                tabs=tabs,
                expand=True,
            )

            if self.app.is_mobile:
                scrollable_content = ft.Container(
                    content=settings_tabs,
                    expand=True,
                    width=float("inf"),
                )
            else:
                scrollable_content = ft.Container(
                    content=settings_tabs,
                    expand=True,
                )

            settings_content = ft.Container(
                content=scrollable_content,
                expand=True,
            )

            column_layout = ft.Column(
                [
                    settings_content,
                ],
                spacing=0,
                expand=True,
                width=float("inf") if self.app.is_mobile else None,
            )

            self.content_area.controls.append(column_layout)
            self.app.complete_page.update()
        except Exception as e:
            logger.error(f"Error loading SettingsPage: {e}")
            self.content_area.controls.append(ft.Text(f"Error loading settings: {e}", color=ft.Colors.RED))
            self.app.complete_page.update()

    def init_unsaved_changes(self):
        self.has_unsaved_changes = {
            "user_config": False,
            "cookies_config": False,
            "accounts_config": False,
            "cloud_config": False
        }

    def load_language(self):
        self.default_language, default_language_code = list(self.language_option.items())[0]
        select_language = self.user_config.get("language")
        self.language_code = self.language_option.get(select_language, default_language_code)
        self.app.language_code = self.language_code

    def get_config_value(self, key, default=None):
        return self.user_config.get(key, self.default_config.get(key, default))

    def get_cookies_value(self, key, default=""):
        return self.cookies_config.get(key, default)

    def get_accounts_value(self, key, default=None):
        k1, k2 = key.split("_", maxsplit=1)
        return self.accounts_config.get(k1, {}).get(k2, default)

    async def restore_default_config(self, _):
        """Restore settings to their default values."""

        async def confirm_dlg(_):
            ui_language = self.user_config["language"]
            self.user_config = self.default_config.copy()
            self.user_config["language"] = ui_language
            self.app.language_manager.notify_observers()
            self.page.run_task(self.load)
            await self.config_manager.save_user_config(self.user_config)
            logger.success("Default configuration restored.")
            await self.app.snack_bar.show_snack_bar(self._["success_restore_tip"], bgcolor=ft.Colors.GREEN)
            await close_dialog(None)

        async def close_dialog(_):
            restore_alert_dialog.open = False
            restore_alert_dialog.update()

        restore_alert_dialog = ft.AlertDialog(
            title=ft.Text(self._["confirm"]),
            content=ft.Text(self._["query_restore_config_tip"]),
            actions=[
                ft.TextButton(text=self._["cancel"], on_click=close_dialog),
                ft.TextButton(text=self._["sure"], on_click=confirm_dlg),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            modal=False,
        )

        self.app.dialog_area.content = restore_alert_dialog
        self.app.dialog_area.content.open = True
        self.app.dialog_area.update()

    async def on_change(self, e):
        """Handle changes in any input field and trigger auto-save."""
        key = e.control.data
        if isinstance(e.control, (ft.Switch, ft.Checkbox)):
            self.user_config[key] = e.data.lower() == "true"
        else:
            self.user_config[key] = e.data
            
        if key in ["folder_name_platform", "folder_name_author", "folder_name_time", "folder_name_title"]:
            for recording in self.app.record_manager.recordings:
                recording.recording_dir = None
            self.page.run_task(self.app.record_manager.persist_recordings)
            
        if key == "language":
            self.load_language()
            self.app.language_manager.load()
            self.app.language_manager.notify_observers()
            self.page.run_task(self.load)

        if key == "loop_time_seconds":
            self.app.record_manager.initialize_dynamic_state()
        self.page.run_task(self.delay_handler.start_task_timer, self.save_user_config_after_delay, None)
        self.has_unsaved_changes['user_config'] = True

    def on_cookies_change(self, e):
        """Handle changes in any input field and trigger auto-save."""
        key = e.control.data
        self.cookies_config[key] = e.data
        self.page.run_task(self.delay_handler.start_task_timer, self.save_web_auth_config_after_delay, None)
        self.has_unsaved_changes['cookies_config'] = True

    def on_accounts_change(self, e):
        """Handle changes in any input field and trigger auto-save."""
        key = e.control.data
        k1, k2 = key.split("_", maxsplit=1)
        if k1 not in self.accounts_config:
            self.accounts_config[k1] = {}

        self.accounts_config[k1][k2] = e.data
        self.page.run_task(self.delay_handler.start_task_timer, self.save_accounts_after_delay, None)
        self.has_unsaved_changes['accounts_config'] = True

    async def save_user_config_after_delay(self, delay):
        if delay:
            await asyncio.sleep(delay)
        await self.config_manager.save_user_config(self.user_config)

    async def save_web_auth_config_after_delay(self, delay):
        await asyncio.sleep(delay)
        if self.has_unsaved_changes['cookies_config']:
            await self.config_manager.save_cookies_config(self.cookies_config)

    async def save_accounts_after_delay(self, delay):
        await asyncio.sleep(delay)
        if self.has_unsaved_changes['accounts_config']:
            await self.config_manager.save_accounts_config(self.accounts_config)

    def get_video_save_path(self):
        live_save_path = self.get_config_value("live_save_path")
        if not live_save_path:
            live_save_path = os.path.join(self.app.run_path, 'downloads')
        return live_save_path

    @staticmethod
    def get_supported_record_format() -> list:
        return VideoFormat.get_formats() + AudioFormat.get_formats()

    def create_recording_settings_tab(self):
        """Create UI elements for recording settings."""
        is_mobile = self.app.is_mobile
        
        return ft.Column(
            [
                self.create_setting_group(
                    self._["basic_settings"],
                    self._["program_config"],
                    [
                        self.create_setting_row(
                            self._["restore_defaults"],
                            ft.IconButton(
                                icon=ft.Icons.RESTORE_OUTLINED,
                                icon_size=32,
                                tooltip=self._["restore_defaults"],
                                on_click=self.restore_default_config,
                            ),
                        ),
                        self.create_setting_row(
                            self._["program_language"],
                            ft.Dropdown(
                                options=[
                                    ft.dropdown.Option(key=k, text=self._[k]) for k, v in self.language_option.items()
                                ],
                                value=self.get_config_value("language", self.default_language),
                                width=200,
                                on_change=self.on_change,
                                data="language",
                                tooltip=self._["switch_language"],
                            ),
                        ),
                        self.create_setting_row(
                            self._["filename_includes_title"],
                            ft.Switch(
                                value=self.get_config_value("filename_includes_title"),
                                on_change=self.on_change,
                                data="filename_includes_title",
                            ),
                        ),
                        self.create_setting_row(
                            self._["custom_filename_template"],
                            ft.TextField(
                                value=self.get_config_value("custom_filename_template", "{anchor_name}_{title}_{time}"),
                                width=300,
                                on_change=self.on_change,
                                data="custom_filename_template",
                                hint_text="{anchor_name}_{title}_{time}",
                            ),
                        ),
                        self.pick_folder(
                            self._["live_recording_path"],
                            ft.TextField(
                                value=self.get_video_save_path(),
                                width=300,
                                on_change=self.on_change,
                                data="live_save_path",
                            ),
                        ),
                        self.create_setting_row(
                            self._["remove_emojis"],
                            ft.Switch(
                                value=self.get_config_value("remove_emojis"),
                                on_change=self.on_change,
                                data="remove_emojis",
                            ),
                        ),
                        self.create_folder_setting_row(self._["name_rules"]),
                        self.create_setting_row(
                            self._["remember_window_size"],
                            ft.Switch(
                                value=self.get_config_value("remember_window_size", False),
                                on_change=self.on_change,
                                data="remember_window_size",
                            ),
                        ),
                    ],
                    is_mobile,
                ),
                self.create_setting_group(
                    self._["proxy_settings"],
                    self._["is_proxy_enabled"],
                    [
                        self.create_setting_row(
                            self._["enable_proxy"],
                            ft.Switch(
                                value=self.get_config_value("enable_proxy"),
                                on_change=self.on_change,
                                data="enable_proxy",
                            ),
                        ),
                        self.create_setting_row(
                            self._["proxy_address"],
                            ft.TextField(
                                value=self.get_config_value("proxy_address"),
                                width=300,
                                on_change=self.on_change,
                                data="proxy_address",
                            ),
                        ),
                    ],
                    is_mobile,
                ),
                self.create_setting_group(
                    self._["recording_options"],
                    self._["advanced_config"],
                    [
                        self.create_setting_row(
                            self._["video_record_format"],
                            ft.Dropdown(
                                options=[ft.dropdown.Option(i) for i in self.get_supported_record_format()],
                                value=self.get_config_value("video_format", VideoFormat.TS),
                                width=200,
                                data="video_format",
                                on_change=self.on_change,
                                tooltip=self._["switch_video_format"],
                            ),
                        ),
                        self.create_setting_row(
                            self._["recording_quality"],
                            ft.Dropdown(
                                options=[ft.dropdown.Option(i, text=self._[i]) for i in VideoQuality.get_qualities()],
                                value=self.get_config_value("record_quality", VideoQuality.OD),
                                width=200,
                                data="record_quality",
                                on_change=self.on_change,
                                tooltip=self._["switch_recording_quality"],
                            ),
                        ),
                        self.create_setting_row(
                            self._["loop_time"],
                            ft.TextField(
                                value=self.get_config_value("loop_time_seconds"),
                                width=100,
                                data="loop_time_seconds",
                                on_change=self.on_change,
                            ),
                        ),
                        self.create_setting_row(
                            self._["is_segmented_recording_enabled"],
                            ft.Switch(
                                value=self.get_config_value("segmented_recording_enabled"),
                                data="segmented_recording_enabled",
                                on_change=self.on_change,
                            ),
                        ),
                        self.create_setting_row(
                            self._["force_https"],
                            ft.Switch(
                                value=self.get_config_value("force_https_recording"),
                                data="force_https_recording",
                                on_change=self.on_change,
                            ),
                        ),
                        self.create_setting_row(
                            self._["default_live_source"],
                            ft.Dropdown(
                                options=[ft.dropdown.Option(i) for i in ['HLS', 'FLV']],
                                value=self.get_config_value("default_live_source", 'FLV'),
                                width=200,
                                data="default_live_source",
                                on_change=self.on_change,
                                tooltip=self._["default_live_source_tip"],
                            ),
                        ),
                        self.create_setting_row(
                            self._["flv_use_direct_download"],
                            ft.Switch(
                                value=self.get_config_value("flv_use_direct_download"),
                                data="flv_use_direct_download",
                                on_change=self.on_change,
                                tooltip=self._["flv_use_direct_download_tip"],
                            ),
                        ),
                        self.create_setting_row(
                            self._["space_threshold"],
                            ft.TextField(
                                value=self.get_config_value("recording_space_threshold"),
                                width=100,
                                data="recording_space_threshold",
                                on_change=self.on_change,
                            ),
                        ),
                        self.create_setting_row(
                            self._["segment_time"],
                            ft.TextField(
                                value=self.get_config_value("video_segment_time"),
                                width=100,
                                data="video_segment_time",
                                on_change=self.on_change,
                            ),
                        ),
                        self.create_setting_row(
                            self._["convert_mp4"],
                            ft.Switch(
                                value=self.get_config_value("convert_to_mp4"),
                                data="convert_to_mp4",
                                on_change=self.on_change,
                            ),
                        ),
                        self.create_setting_row(
                            self._["delete_original"],
                            ft.Switch(
                                value=self.get_config_value("delete_original"),
                                data="delete_original",
                                on_change=self.on_change,
                            ),
                        ),
                        self.create_setting_row(
                            self._["generate_timestamps_subtitle"],
                            ft.Switch(
                                value=self.get_config_value("generate_time_subtitle_file"),
                                data="generate_time_subtitle_file",
                                on_change=self.on_change,
                            ),
                        ),
                        self.create_setting_row(
                            self._["custom_script"],
                            ft.Switch(
                                value=self.get_config_value("execute_custom_script"),
                                data="execute_custom_script",
                                on_change=self.on_change,
                            ),
                        ),
                        self.create_setting_row(
                            self._["script_command"],
                            ft.TextField(
                                value=self.get_config_value("custom_script_command"),
                                width=300,
                                data="custom_script_command",
                                on_change=self.on_change,
                            ),
                        ),
                        self.create_setting_row(
                            self._["default_platform_with_proxy"],
                            ft.TextField(
                                value=self.get_config_value("default_platform_with_proxy"),
                                width=300,
                                data="default_platform_with_proxy",
                                on_change=self.on_change,
                            ),
                        ),
                        self.create_setting_row(
                            self._["platform_max_concurrent_requests"],
                            ft.TextField(
                                value=str(self.get_config_value("platform_max_concurrent_requests", 3)),
                                width=100,
                                data="platform_max_concurrent_requests",
                                on_change=self.on_change,
                                hint_text=self._["platform_max_concurrent_requests_tip"]
                            ),
                        ),
                        self.create_setting_row(
                            self._["check_live_on_browser_refresh"],
                            ft.Switch(
                                value=self.get_config_value("check_live_on_browser_refresh", True),
                                data="check_live_on_browser_refresh",
                                on_change=self.on_change,
                                tooltip=self._['check_live_on_browser_refresh_tip']
                            ),
                        ),
                    ],
                    is_mobile,
                ),
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
        )

    def create_cloud_settings_tab(self):
        """Create UI elements for Local Speech Recognition Model settings."""
        is_mobile = self.app.is_mobile
        
        try:
            from ...core.stt.local_stt import LocalSTTService, MODELS
            stt_service = LocalSTTService(self.config_manager)
            
            self.download_progress_bar = ft.ProgressBar(width=400, visible=False)
            self.download_status_text = ft.Text(visible=False)
            self.model_list_container = ft.Column()  # Use a Column for the list
            self.model_list_ref = ft.Ref[ft.Column]()

            def create_model_list():
                try:
                    is_ready, status = stt_service.check_models_status()
                    rows = []
                    for key, model_id in MODELS.items():
                        ready = status.get(key, False)
                        rows.append(
                            ft.Row([
                                ft.Icon(ft.icons.CHECK_CIRCLE if ready else ft.icons.CANCEL, 
                                        color=ft.Colors.GREEN if ready else ft.Colors.RED),
                                ft.Column([
                                     ft.Text(f"{key.upper()} Model: {model_id.split('/')[-1]}", weight=ft.FontWeight.BOLD),
                                     ft.Text(self._.get(f"model_desc_{key}", ""), size=12, color=ft.Colors.GREY)
                                ], spacing=2, expand=True),
                                ft.Text(self._["model_status_ready"] if ready else self._["model_status_missing"], 
                                        color=ft.Colors.GREEN if ready else ft.Colors.RED)
                            ], alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.START)
                        )
                    return rows
                except Exception as e:
                    logger.error(f"Error creating model list: {e}")
                    return [ft.Text(f"Error loading model status: {e}", color=ft.Colors.RED)]

            def update_model_list_ui():
                if self.model_list_ref.current:
                    self.model_list_ref.current.controls = create_model_list()
                    self.model_list_ref.current.update()

            def download_models(e):
                self.download_progress_bar.visible = True
                self.download_status_text.visible = True
                self.download_status_text.value = self._["model_downloading"]
                self.page.update()
                
                def progress_callback(msg):
                    self.download_status_text.value = msg
                    self.page.update()
                
                self.app.page.run_task(_download_task, progress_callback)

            async def _download_task(callback):
                try:
                    loop = asyncio.get_running_loop()
                    success, msg = await loop.run_in_executor(None, stt_service.download_models, callback)
                    self.download_status_text.value = self._["model_download_success"] if success else f"{self._['model_download_failed']}: {msg}"
                except Exception as e:
                     self.download_status_text.value = f"Download error: {e}"
                
                self.download_progress_bar.visible = False
                
                # Safely update UI
                try:
                    update_model_list_ui()
                except Exception as e:
                    logger.error(f"Error updating model list UI: {e}")
                self.page.update()
            
            # Initial Load
            initial_rows = create_model_list()
            
            # 1. Local STT Controls
            # 1. Local STT Controls
            local_stt_controls = [
                        ft.Container(
                            content=ft.Column(controls=initial_rows, ref=self.model_list_ref), 
                            padding=10
                        ),
                        ft.Container(
                             content=ft.Text(self._.get("download_warning_tip", "* Large download warning"), size=12, color=ft.Colors.GREY),
                             padding=ft.padding.only(left=10, bottom=10)
                        ),
                        ft.Row([
                            ft.ElevatedButton(
                                text=self._["check_models"],
                                icon=ft.icons.REFRESH,
                                on_click=lambda e: update_model_list_ui()
                            ),
                            ft.ElevatedButton(
                                text=self._["download_models"],
                                icon=ft.icons.DOWNLOAD,
                                on_click=download_models
                            ),
                        ]),
                        
                        # Vocal Enhancement Toggle
                        ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
                        self.create_setting_row(
                             self._.get("enable_vocal_enhancement", "Enable Vocal Enhancement"),
                             ft.Switch(
                                value=self.get_config_value("enable_vocal_enhancement", False),
                                data="enable_vocal_enhancement",
                                on_change=self.on_change
                             )
                        ),
                        ft.Container(
                            content=ft.Text(self._.get("vocal_enhancement_tip", "Tip..."), size=12, color=ft.Colors.GREY),
                            padding=ft.padding.only(left=0, top=0, bottom=10)
                        ),

                        self.download_status_text,
                        self.download_progress_bar,
                    ]


            # AI Configuration Logic
            from ...core.ai.ai_optimizer import CONF_AI_API_KEY, CONF_AI_BASE_URL, CONF_AI_MODEL, CONF_AI_ENABLED, DEFAULT_AI_BASE_URL, DEFAULT_AI_MODEL

            def on_ai_test_click(e):
                self.app.page.run_task(test_ai_connection)

            async def test_ai_connection():
                from ...core.ai.ai_optimizer import AITextOptimizer
                optimizer = AITextOptimizer(self.config_manager)
                
                api_key = self.get_config_value(CONF_AI_API_KEY)
                base_url = self.get_config_value(CONF_AI_BASE_URL, DEFAULT_AI_BASE_URL)
                model = self.get_config_value(CONF_AI_MODEL, DEFAULT_AI_MODEL)
                
                if not api_key:
                    await self.app.snack_bar.show_snack_bar(self._["please_enter_api_key"], bgcolor=ft.Colors.RED)
                    return

                await self.app.snack_bar.show_snack_bar(self._["test_connection_start"], bgcolor=ft.Colors.BLUE)
                
                success, msg = await optimizer.test_connection(api_key, base_url, model)
                if success:
                    await self.app.snack_bar.show_snack_bar(f"{self._['connection_success']}: {msg}", bgcolor=ft.Colors.GREEN)
                else:
                    await self.app.snack_bar.show_snack_bar(f"{self._['connection_failed']}: {msg}", bgcolor=ft.Colors.RED)

            ai_config_controls = [
                self.create_setting_row(
                    self._["enable_ai_optimization"],
                    ft.Switch(
                        value=self.get_config_value(CONF_AI_ENABLED, False),
                        data=CONF_AI_ENABLED,
                        on_change=self.on_change
                    )
                ),
                self.create_setting_row(
                    f"{self._['ai_api_key']} *",
                    ft.TextField(
                        value=self.get_config_value(CONF_AI_API_KEY),
                        data=CONF_AI_API_KEY,
                        password=True,
                        can_reveal_password=True,
                        width=400,
                        on_change=self.on_change,
                        hint_text="sk-..."
                    )
                ),
                self.create_setting_row(
                    self._["ai_base_url"],
                    ft.TextField(
                        value=self.get_config_value(CONF_AI_BASE_URL, DEFAULT_AI_BASE_URL),
                        data=CONF_AI_BASE_URL,
                        width=400,
                        on_change=self.on_change
                    )
                ),
                self.create_setting_row(
                    self._["ai_model"],
                    ft.Column([
                        ft.TextField(
                            value=self.get_config_value(CONF_AI_MODEL, DEFAULT_AI_MODEL),
                            data=CONF_AI_MODEL,
                            width=400,
                            on_change=self.on_change,
                            hint_text="e.g. gpt-3.5-turbo, qwen-max"
                        ),
                         ft.Text(self._["ai_model_tip"], size=12, color=ft.Colors.GREY)
                    ])
                ),
                ft.ElevatedButton(
                    self._["test_configuration"],
                    icon=ft.icons.SCIENCE,
                    on_click=on_ai_test_click,
                    style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE)
                )
            ]

            # 2. Auto Identify Controls
            # Use a custom row instead of create_setting_row to have control over label size
            auto_identify_controls = [
                ft.Container(
                    content=ft.Row([
                        ft.Text(self._.get("auto_identify_text", "Auto Identify"), size=16, weight=ft.FontWeight.BOLD), # Larger font
                        ft.Switch(
                            value=self.get_config_value("auto_identify_text", False),
                            data="auto_identify_text",
                            on_change=self.on_change
                        )
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    padding=ft.padding.symmetric(vertical=10)
                )
            ]

        except Exception as e:
            logger.error(f"Failed to initialize LocalSTTService or UI: {e}")
            local_stt_controls = [ft.Text(f"Error initializing local STT service: {e}", color=ft.Colors.RED)]
            ai_config_controls = []
            auto_identify_controls = []

        return ft.Column(
            [
                self.create_setting_group(
                    self._["local_stt_settings"],
                    self._["local_stt_tip"],
                    local_stt_controls,
                    is_mobile,
                ),
                self.create_setting_group(
                    self._.get("auto_identify_text", "Auto Identify"),
                    self._.get("auto_identify_tip", "Automatically identify text after recording completes."),
                    auto_identify_controls,
                    is_mobile,
                ),
                self.create_setting_group(
                    self._["ai_config_title"],
                    self._["ai_config_tip"],
                    ai_config_controls,
                    is_mobile,
                ),
            ],
            spacing=20,
            scroll=ft.ScrollMode.AUTO,
        )


    def create_dependencies_tab(self):
        """Create UI elements for Dependencies settings."""
        is_mobile = self.app.is_mobile
        
        self.dep_status_container = ft.Column()
        
        async def check_dependencies(e=None):
            self.dep_status_container.controls.clear()
            
            components = ["FFmpeg", "Node.js"]
            for comp_name in components:
                status = await self.app.install_manager.get_component_status(comp_name)
                if not status:
                    continue
                
                is_installed = status["installed"]
                color = ft.Colors.GREEN if is_installed else ft.Colors.RED
                status_text = self._["installed"] if is_installed else self._["missing"]
                icon = ft.icons.CHECK_CIRCLE if is_installed else ft.icons.CANCEL
                
                path_info = status.get("path", "N/A")
                if status.get("is_local"):
                     path_info += f" ({self._['builtin']})"
                else:
                     path_info += f" ({self._['system']})"
                     
                card_content = ft.Column([
                    ft.Row([
                        ft.Icon(icon, color=color, size=30),
                        ft.Text(status["name"], size=20, weight=ft.FontWeight.BOLD, expand=True),
                        ft.Container(
                            content=ft.Text(status_text, color=ft.Colors.WHITE, size=12),
                            bgcolor=color,
                            padding=5,
                            border_radius=5
                        )
                    ]),
                    ft.Divider(),
                    ft.Row([ft.Text(f"{self._['version']}: ", weight=ft.FontWeight.BOLD), ft.Text(status.get("version", "N/A"))]),
                    ft.Row([ft.Text(f"{self._['path']}: ", weight=ft.FontWeight.BOLD), ft.Text(path_info, size=12, overflow=ft.TextOverflow.ELLIPSIS, expand=True)]),
                ])
                
                action_row = ft.Row([
                    ft.ElevatedButton(
                        text=self._["reinstall"] if is_installed else self._["install_now"],
                        icon=ft.icons.DOWNLOAD,
                        on_click=lambda e, name=comp_name: self.app.page.run_task(install_dependency, name)
                    )
                ], alignment=ft.MainAxisAlignment.END)
                
                card_content.controls.append(ft.Divider())
                card_content.controls.append(action_row)

                self.dep_status_container.controls.append(
                    ft.Card(
                        content=ft.Container(
                            content=card_content,
                            padding=15
                        )
                    )
                )
            self.dep_status_container.update()

        async def install_dependency(name):
            from ...scripts.ffmpeg_install import install_ffmpeg
            from ...scripts.node_install import install_nodejs
            
            install_func = None
            if name == "FFmpeg":
                install_func = install_ffmpeg
            elif name == "Node.js":
                install_func = install_nodejs
                
            if install_func:
                self.app.page.show_snack_bar(ft.SnackBar(content=ft.Text(f"Starting {name} installation...")))
                
                async def progress_callback(progress, status):
                    if progress_dialog.open:
                        pb.value = progress
                        status_txt.value = status
                        progress_dialog.update()

                pb = ft.ProgressBar(width=300)
                status_txt = ft.Text("Initializing...")
                progress_dialog = ft.AlertDialog(
                    title=ft.Text(f"Installing {name}"),
                    content=ft.Column([status_txt, pb], height=100, tight=True),
                    modal=True,
                )
                self.app.page.open(progress_dialog)
                self.app.page.update()
                
                try:
                    res = await install_func(progress_callback)
                    self.app.page.close(progress_dialog)
                    if res:
                        await self.app.snack_bar.show_snack_bar(self._["install_success"], bgcolor=ft.Colors.GREEN)
                        await check_dependencies()
                    else:
                        await self.app.snack_bar.show_snack_bar(self._["install_failed"], bgcolor=ft.Colors.RED)
                except Exception as ex:
                    self.app.page.close(progress_dialog)
                    await self.app.snack_bar.show_snack_bar(f"{self._['install_failed']}: {ex}", bgcolor=ft.Colors.RED)

        self.app.page.run_task(check_dependencies)

        return ft.Column(
            [
                self.create_setting_group(
                    self._["dependency_check"],
                    self._["program_config"],
                    [
                        ft.Container(content=self.dep_status_container),
                    ],
                    is_mobile
                ),
                 ft.Row([
                    ft.ElevatedButton(
                        self._["check_update"],
                        icon=ft.icons.REFRESH,
                        on_click=check_dependencies
                    )
                 ], alignment=ft.MainAxisAlignment.CENTER)
            ],
            scroll=ft.ScrollMode.AUTO,
        )

    def create_push_settings_tab(self):
        """Create UI elements for push configuration."""
        is_mobile = self.app.is_mobile
        
        return ft.Column(
            [
                self.create_setting_group(
                    self._["push_notifications"],
                    self._["stream_start_notification_enabled"],
                    [
                        self.create_setting_row(
                            self._["system_status_bar_notification_enabled"],
                            ft.Switch(
                                value=self.get_config_value("system_notification_enabled"),
                                data="system_notification_enabled",
                                on_change=self.on_change,
                            ),
                        ),
                        self.create_setting_row(
                            self._["open_broadcast_push_enabled"],
                            ft.Switch(
                                value=self.get_config_value("stream_start_notification_enabled"),
                                data="stream_start_notification_enabled",
                                on_change=self.on_change,
                            ),
                        ),
                        self.create_setting_row(
                            self._["close_broadcast_push_enabled"],
                            ft.Switch(
                                value=self.get_config_value("stream_end_notification_enabled"),
                                data="stream_end_notification_enabled",
                                on_change=self.on_change,
                            ),
                        ),
                        self.create_setting_row(
                            self._["only_notify_no_record"],
                            ft.Switch(
                                value=self.get_config_value("only_notify_no_record"),
                                data="only_notify_no_record",
                                on_change=self.on_change,
                            ),
                        ),
                        self.create_setting_row(
                            self._["notify_loop_time"],
                            ft.TextField(
                                value=self.get_config_value("notify_loop_time"),
                                width=300,
                                data="notify_loop_time",
                                on_change=self.on_change,
                            ),
                        ),
                    ],
                    is_mobile,
                ),
                self.create_setting_group(
                    self._["custom_push_settings"],
                    self._["personalized_notification_content_behavior"],
                    [
                        self.create_setting_row(
                            self._["custom_push_title"],
                            ft.TextField(
                                value=self.get_config_value("custom_notification_title"),
                                width=300,
                                data="custom_notification_title",
                                on_change=self.on_change,
                            ),
                        ),
                        self.create_setting_row(
                            self._["custom_open_broadcast_content"],
                            ft.TextField(
                                value=self.get_config_value("custom_stream_start_content"),
                                width=300,
                                data="custom_stream_start_content",
                                on_change=self.on_change,
                            ),
                        ),
                        self.create_setting_row(
                            self._["custom_close_broadcast_content"],
                            ft.TextField(
                                value=self.get_config_value("custom_stream_end_content"),
                                width=300,
                                data="custom_stream_end_content",
                                on_change=self.on_change,
                            ),
                        ),
                    ],
                    is_mobile,
                ),
                self.create_setting_group(
                    self._["push_channels"],
                    self._["select_and_enable_channels"],
                    [self.create_push_channels_layout()],
                    is_mobile,
                ),
                self.create_setting_group(
                    self._["channel_configuration"],
                    self._["configure_enabled_channels"],
                    [
                        self.create_channel_config(
                            self._["dingtalk"],
                            [
                                self.create_setting_row(
                                    self._["dingtalk_webhook_url"],
                                    ft.TextField(
                                        value=self.get_config_value("dingtalk_webhook_url"),
                                        hint_text=self._["dingtalk_webhook_hint"],
                                        width=300,
                                        on_change=self.on_change,
                                        data="dingtalk_webhook_url",
                                    ),
                                ),
                                self.create_setting_row(
                                    self._["dingtalk_at_objects"],
                                    ft.TextField(
                                        value=self.get_config_value("dingtalk_at_objects"),
                                        hint_text=self._["dingtalk_phone_numbers_hint"],
                                        width=300,
                                        on_change=self.on_change,
                                        data="dingtalk_at_objects",
                                    ),
                                ),
                                self.create_setting_row(
                                    self._["dingtalk_at_all"],
                                    ft.Switch(
                                        value=self.get_config_value("dingtalk_at_all"),
                                        on_change=self.on_change,
                                        data="dingtalk_at_all",
                                    ),
                                ),
                            ],
                        ),
                        self.create_channel_config(
                            self._["wechat"],
                            [
                                self.create_setting_row(
                                    self._["wechat_webhook_url"],
                                    ft.TextField(
                                        value=self.get_config_value("wechat_webhook_url"),
                                        width=300,
                                        on_change=self.on_change,
                                        data="wechat_webhook_url",
                                    ),
                                ),
                            ],
                        ),
                        self.create_channel_config(
                            self._["feishu"],
                            [
                                self.create_setting_row(
                                    self._["feishu_webhook_url"],
                                    ft.TextField(
                                        value=self.get_config_value("feishu_webhook_url"),
                                        width=300,
                                        on_change=self.on_change,
                                        data="feishu_webhook_url",
                                    ),
                                ),
                            ],
                        ),
                        self.create_channel_config(
                            self._["serverchan"],
                            [
                                self.create_setting_row(
                                    self._["serverchan_send_key"],
                                    ft.TextField(
                                        value=self.get_config_value("serverchan_sendkey"),
                                        width=300,
                                        on_change=self.on_change,
                                        data="serverchan_sendkey",
                                    ),
                                ),
                                self.create_setting_row(
                                    self._["serverchan_channel"],
                                    ft.TextField(
                                        value=self.get_config_value("serverchan_channel"),
                                        width=300,
                                        keyboard_type=ft.KeyboardType.NUMBER,
                                        on_change=self.on_change,
                                        data="serverchan_channel",
                                    ),
                                ),
                                self.create_setting_row(
                                    self._["serverchan_tags"],
                                    ft.TextField(
                                        value=self.get_config_value("serverchan_tags"),
                                        width=300,
                                        keyboard_type=ft.KeyboardType.NUMBER,
                                        on_change=self.on_change,
                                        data="serverchan_tags",
                                    ),
                                ),
                            ],
                        ),
                        self.create_channel_config(
                            self._["email"],
                            [
                                self.create_setting_row(
                                    self._["smtp_server"],
                                    ft.TextField(
                                        value=self.get_config_value("smtp_server"),
                                        width=300,
                                        on_change=self.on_change,
                                        data="smtp_server",
                                    ),
                                ),
                                self.create_setting_row(
                                    self._["email_username"],
                                    ft.TextField(
                                        value=self.get_config_value("email_username"),
                                        width=300,
                                        on_change=self.on_change,
                                        data="email_username",
                                    ),
                                ),
                                self.create_setting_row(
                                    self._["email_password"],
                                    ft.TextField(
                                        value=self.get_config_value("email_password"),
                                        width=300,
                                        on_change=self.on_change,
                                        data="email_password",
                                    ),
                                ),
                                self.create_setting_row(
                                    self._["sender_email"],
                                    ft.TextField(
                                        value=self.get_config_value("sender_email"),
                                        width=300,
                                        on_change=self.on_change,
                                        data="sender_email",
                                    ),
                                ),
                                self.create_setting_row(
                                    self._["sender_name"],
                                    ft.TextField(
                                        value=self.get_config_value("sender_name"),
                                        width=300,
                                        on_change=self.on_change,
                                        data="sender_name",
                                    ),
                                ),
                                self.create_setting_row(
                                    self._["recipient_email"],
                                    ft.TextField(
                                        value=self.get_config_value("recipient_email"),
                                        width=300,
                                        on_change=self.on_change,
                                        data="recipient_email",
                                    ),
                                ),
                            ],
                        ),
                        self.create_channel_config(
                            "Bark",
                            [
                                self.create_setting_row(
                                    self._["bark_webhook_url"],
                                    ft.TextField(
                                        value=self.get_config_value("bark_webhook_url"),
                                        width=300,
                                        on_change=self.on_change,
                                        data="bark_webhook_url",
                                    ),
                                ),
                                self.create_setting_row(
                                    self._["bark_interrupt_level"],
                                    ft.Dropdown(
                                        options=[ft.dropdown.Option("active"), ft.dropdown.Option("passive")],
                                        value=self.get_config_value("bark_interrupt_level"),
                                        width=200,
                                        on_change=self.on_change,
                                        data="bark_interrupt_level",
                                    ),
                                ),
                                self.create_setting_row(
                                    self._["bark_sound"],
                                    ft.TextField(
                                        width=300,
                                        on_change=self.on_change,
                                        data="bark_sound",
                                        value=self.get_config_value("bark_sound"),
                                    ),
                                ),
                            ],
                        ),
                        self.create_channel_config(
                            "Ntfy",
                            [
                                self.create_setting_row(
                                    self._["ntfy_server_url"],
                                    ft.TextField(
                                        value=self.get_config_value("ntfy_server_url"),
                                        width=300,
                                        on_change=self.on_change,
                                        data="ntfy_server_url",
                                    ),
                                ),
                                self.create_setting_row(
                                    self._["ntfy_tags"],
                                    ft.TextField(
                                        value=self.get_config_value("ntfy_tags"),
                                        width=300,
                                        on_change=self.on_change,
                                        data="ntfy_tags",
                                    ),
                                ),
                                self.create_setting_row(
                                    self._["ntfy_email"],
                                    ft.TextField(
                                        value=self.get_config_value("ntfy_email"),
                                        width=300,
                                        on_change=self.on_change,
                                        data="ntfy_email",
                                    ),
                                ),
                                self.create_setting_row(
                                    self._["ntfy_action_url"],
                                    ft.TextField(
                                        value=self.get_config_value("ntfy_action_url"),
                                        width=300,
                                        on_change=self.on_change,
                                        data="ntfy_action_url",
                                    ),
                                ),
                            ],
                        ),
                        self.create_channel_config(
                            self._["telegram"],
                            [
                                self.create_setting_row(
                                    self._["telegram_api_token"],
                                    ft.TextField(
                                        value=self.get_config_value("telegram_api_token"),
                                        width=300,
                                        on_change=self.on_change,
                                        data="telegram_api_token",
                                    ),
                                ),
                                self.create_setting_row(
                                    self._["telegram_chat_id"],
                                    ft.TextField(
                                        value=self.get_config_value("telegram_chat_id"),
                                        width=300,
                                        on_change=self.on_change,
                                        data="telegram_chat_id",
                                    ),
                                ),
                            ],
                        ),
                    ],
                    is_mobile,
                ),
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
        )

    def create_push_channels_layout(self):
        controls = [
            self.create_channel_switch_container(
                self._["dingtalk"], ft.Icons.BUSINESS_CENTER, "dingtalk_enabled"
            ),
            self.create_channel_switch_container(
                self._["wechat"], ft.Icons.WECHAT, "wechat_enabled"
            ),
            self.create_channel_switch_container(
                self._["feishu"], ft.Icons.BOOK, "feishu_enabled"
            ),
            self.create_channel_switch_container(
                self._["serverchan"], ft.Icons.CLOUD_OUTLINED, "serverchan_enabled"
            ),
            self.create_channel_switch_container(
                self._["email"], ft.Icons.EMAIL, "email_enabled"
            ),
            self.create_channel_switch_container(
                "Bark", ft.Icons.NOTIFICATIONS_ACTIVE, "bark_enabled"
            ),
            self.create_channel_switch_container(
                "Ntfy", ft.Icons.NOTIFICATIONS, "ntfy_enabled"
            ),
            self.create_channel_switch_container(
                self._["telegram"], ft.Icons.SMS, "telegram_enabled"
            ),
        ]

        if self.app.is_mobile:
            return ft.Row(
                controls=controls,
                spacing=5,
                wrap=True,
            )
        if self.app.page.web:
            return ft.Row(
                controls=controls,
                alignment=ft.MainAxisAlignment.START,
                spacing=12,
            )
        else:
            return ft.Container(
                content=ft.GridView(
                    controls=controls,
                    runs_count=3,
                    max_extent=175,
                    spacing=5,
                    run_spacing=2,
                    child_aspect_ratio=2.5,
                ),
                expand=True,
            )

    def create_cookies_settings_tab(self):
        """Create UI elements for push configuration."""
        is_mobile = self.app.is_mobile
        
        platforms = [
            "douyin",
            "tiktok",
            "kuaishou",
            "huya",
            "douyu",
            "yy",
            "bilibili",
            "xhs",
            "bigo",
            "blued",
            "soop",
            "netease",
            "qiandurebo",
            "pandalive",
            "maoerfm",
            "winktv",
            "flextv",
            "look",
            "popkontv",
            "twitcasting",
            "baidu",
            "weibo",
            "kugou",
            "twitch",
            "liveme",
            "huajiao",
            "liuxing",
            "showroom",
            "acfun",
            "changliao",
            "yinbo",
            "inke",
            "zhihu",
            "chzzk",
            "haixiu",
            "vvxq",
            "17live",
            "lang",
            "piaopiao",
            "6room",
            "lehai",
            "catshow",
            "shopee",
            "youtube",
            "taobao",
            "jd",
        ]

        setting_rows = []
        for platform in platforms:
            cookie_field = ft.TextField(
                value=self.get_cookies_value(platform), width=500, data=platform, on_change=self.on_cookies_change
            )
            setting_rows.append(self.create_setting_row(self._[f"{platform}_cookie"], cookie_field))

        return ft.Column(
            [
                self.create_setting_group(
                    self._["cookies_settings"], self._["configure_platform_cookies"], setting_rows, is_mobile
                ),
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
        )

    def create_accounts_settings_tab(self):
        """Create UI elements for platform accounts configuration."""
        is_mobile = self.app.is_mobile
        
        return ft.Column(
            [
                self.create_setting_group(
                    self._["accounts_settings"],
                    self._["configure_platform_accounts"],
                    [
                        self.create_setting_row(
                            self._["sooplive_username"],
                            ft.TextField(
                                value=self.get_accounts_value("sooplive_username"),
                                width=500,
                                data="sooplive_username",
                                on_change=self.on_accounts_change,
                            ),
                        ),
                        self.create_setting_row(
                            self._["sooplive_password"],
                            ft.TextField(
                                value=self.get_accounts_value("sooplive_password"),
                                width=500,
                                data="sooplive_password",
                                on_change=self.on_accounts_change,
                            ),
                        ),
                        self.create_setting_row(
                            self._["flextv_username"],
                            ft.TextField(
                                value=self.get_accounts_value("flextv_username"),
                                width=500,
                                data="flextv_username",
                                on_change=self.on_accounts_change,
                            ),
                        ),
                        self.create_setting_row(
                            self._["flextv_password"],
                            ft.TextField(
                                value=self.get_accounts_value("flextv_password"),
                                width=500,
                                data="flextv_password",
                                on_change=self.on_accounts_change,
                            ),
                        ),
                        self.create_setting_row(
                            self._["popkontv_username"],
                            ft.TextField(
                                value=self.get_accounts_value("popkontv_username"),
                                width=500,
                                data="popkontv_username",
                                on_change=self.on_accounts_change,
                            ),
                        ),
                        self.create_setting_row(
                            self._["popkontv_password"],
                            ft.TextField(
                                value=self.get_accounts_value("popkontv_password"),
                                width=500,
                                data="popkontv_password",
                                on_change=self.on_accounts_change,
                            ),
                        ),
                        self.create_setting_row(
                            self._["twitcasting_account_type"],
                            ft.Dropdown(
                                options=[ft.dropdown.Option("Default"), ft.dropdown.Option("Twitter")],
                                value=self.get_accounts_value("twitcasting_account_type", "Default"),
                                width=500,
                                data="twitcasting_account_type",
                                on_change=self.on_accounts_change,
                                tooltip=self._["switch_account_type"],
                            ),
                        ),
                        self.create_setting_row(
                            self._["twitcasting_username"],
                            ft.TextField(
                                value=self.get_accounts_value("twitcasting_username"),
                                width=500,
                                data="twitcasting_username",
                                on_change=self.on_accounts_change,
                            ),
                        ),
                        self.create_setting_row(
                            self._["twitcasting_password"],
                            ft.TextField(
                                value=self.get_accounts_value("twitcasting_password"),
                                width=500,
                                data="twitcasting_password",
                                on_change=self.on_accounts_change,
                            ),
                        ),
                    ],
                    is_mobile,
                ),
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
        )

    def create_folder_setting_row(self, label):
        checkboxes = [
            ft.Checkbox(
                label=self._["platform"],
                value=self.get_config_value("folder_name_platform"),
                on_change=self.on_change,
                data="folder_name_platform",
            ),
            ft.Checkbox(
                label=self._["author"],
                value=self.get_config_value("folder_name_author"),
                on_change=self.on_change,
                data="folder_name_author",
            ),
            ft.Checkbox(
                label=self._["time"],
                value=self.get_config_value("folder_name_time"),
                on_change=self.on_change,
                data="folder_name_time",
            ),
            ft.Checkbox(
                label=self._["title"],
                value=self.get_config_value("folder_name_title"),
                on_change=self.on_change,
                data="folder_name_title",
            ),
        ]
        
        if self.app.is_mobile:
            checkbox_grid = ft.Column(
                [
                    ft.Row([checkboxes[0], checkboxes[1]], spacing=10),
                    ft.Row([checkboxes[2], checkboxes[3]], spacing=10),
                ],
                spacing=5,
            )
            
            return ft.Column(
                [
                    ft.Text(label, text_align=ft.TextAlign.LEFT, weight=ft.FontWeight.BOLD),
                    ft.Container(
                        content=checkbox_grid,
                        margin=ft.margin.only(top=5, bottom=10),
                    )
                ],
                spacing=5,
                alignment=ft.MainAxisAlignment.START,
                horizontal_alignment=ft.CrossAxisAlignment.START,
                width=float("inf"),
            )
        else:
            return ft.Row(
                [ft.Text(label, width=200, text_align=ft.TextAlign.RIGHT), *checkboxes],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )

    def create_channel_switch_container(self, channel_name, icon, key):
        """Helper method to create a container with a switch and an icon for each channel."""
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(icon, size=24, color=ft.Colors.GREY_700),
                    ft.Text(channel_name, size=14),
                    ft.Switch(value=self.get_config_value(key), label="", width=50, on_change=self.on_change, data=key),
                ],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=5,
            margin=5,
        )

    @staticmethod
    def create_channel_config(channel_name, settings):
        """Helper method to create expandable configurations for each channel."""
        return ft.ExpansionTile(
            initially_expanded=False,
            title=ft.Text(channel_name, size=14, weight=ft.FontWeight.BOLD),
            controls=[ft.Container(content=ft.Column(settings, spacing=5), padding=10)],
            tile_padding=0,
        )

    @staticmethod
    def create_setting_group(title, description, settings, is_mobile=False):
        """Helper method to group settings under a title."""
        padding = 5 if is_mobile else 10
        margin = 5 if is_mobile else 10
        
        card = ft.Card(
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(title, size=16, weight=ft.FontWeight.BOLD),
                        ft.Text(description, theme_style=ft.TextThemeStyle.BODY_MEDIUM, opacity=0.7),
                        *settings,
                    ],
                    spacing=5,
                ),
                padding=padding,
            ),
            elevation=5,
            margin=margin,
        )
        
        if is_mobile:
            return ft.Container(
                content=card,
                width=float("inf"),
                expand=True,
            )
        else:
            return card

    def set_focused_control(self, control):
        """Store the currently focused control."""
        self.focused_control = control

    def create_setting_row(self, label, control):
        """Helper method to create a row for each setting."""
        if hasattr(control, 'on_focus'):
            control.on_focus = lambda e: self.set_focused_control(e.control)
            
        if self.app.is_mobile:
            if isinstance(control, (ft.Switch, ft.Checkbox, ft.IconButton)):
                return ft.Row(
                    [
                        ft.Text(label),
                        ft.Container(expand=True),
                        control
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    width=float("inf"),
                )
            
            if hasattr(control, 'width') and control.width and control.width > 250:
                control.width = 250
                
            if isinstance(control, (ft.TextField, ft.Dropdown)):
                control.width = float("inf")
                control.expand = True
                
            return ft.Column(
                [
                    ft.Text(label, text_align=ft.TextAlign.LEFT),
                    ft.Container(
                        content=control,
                        margin=ft.margin.only(top=5, bottom=10),
                        expand=True,
                        width=float("inf"),
                    )
                ],
                spacing=0,
                alignment=ft.MainAxisAlignment.START,
                horizontal_alignment=ft.CrossAxisAlignment.START,
                width=float("inf"),
            )
        else:
            return ft.Row(
                [ft.Text(label, width=200, text_align=ft.TextAlign.RIGHT), control],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )

    def pick_folder(self, label, control):
        def picked_folder(e: ft.FilePickerResultEvent):
            path = e.path
            if path:
                control.value = path
                control.update()
                e.control.data = control.data
                e.data = path
                self.page.run_task(self.on_change, e)

        async def pick_folder(_):
            if self.app.page.web:
                await self.app.snack_bar.show_snack_bar(self._["unsupported_select_path"])
            folder_picker.get_directory_path()

        folder_picker = ft.FilePicker(on_result=picked_folder)
        self.page.overlay.append(folder_picker)
        self.page.update()

        btn_pick_folder = ft.ElevatedButton(
            text=self._["select"], icon=ft.Icons.FOLDER_OPEN, on_click=pick_folder, tooltip=self._["select_btn_tip"]
        )
        
        if self.app.is_mobile:
            if hasattr(control, 'width'):
                control.width = float("inf")
                control.expand = True
                
            return ft.Column(
                [
                    ft.Text(label, text_align=ft.TextAlign.LEFT),
                    ft.Row(
                        [
                            ft.Container(
                                content=control,
                                expand=True,
                            ),
                            btn_pick_folder
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        expand=True,
                        width=float("inf"),
                    ),
                ],
                spacing=5,
                alignment=ft.MainAxisAlignment.START,
                horizontal_alignment=ft.CrossAxisAlignment.START,
                width=float("inf"),
            )
        else:
            return ft.Row(
                [ft.Text(label, width=200, text_align=ft.TextAlign.RIGHT), control, btn_pick_folder],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )

    async def is_changed(self):
        if self.app.current_page != self:
            return

        show_snack_bar = False
        save_methods = {
            "user_config": (self.config_manager.save_user_config, self.user_config),
            "cookies_config": (self.config_manager.save_cookies_config, self.cookies_config),
            "accounts_config": (self.config_manager.save_accounts_config, self.accounts_config)
        }

        for config_key, should_save in self.has_unsaved_changes.items():
            if should_save and config_key in save_methods:
                save_method, config_value = save_methods[config_key]
                await save_method(config_value)
                self.has_unsaved_changes[config_key] = False
                show_snack_bar = True

        if show_snack_bar:
            await self.app.snack_bar.show_snack_bar(
                self._["success_save_config_tip"], duration=1500, bgcolor=ft.Colors.GREEN
            )

    async def on_keyboard(self, e: ft.KeyboardEvent):
        if e.alt and e.key == "H":
            self.app.dialog_area.content = HelpDialog(self.app)
            self.app.dialog_area.content.open = True
            self.app.dialog_area.update()

        if self.app.current_page == self and e.ctrl and e.key == "S":
            self.page.run_task(self.is_changed)

    def create_security_settings_tab(self):
        is_mobile = self.app.is_mobile
        
        async def change_password(_):
            old_password = old_password_field.value
            new_password = new_password_field.value
            confirm_password = confirm_password_field.value
            
            if not old_password:
                await self.app.snack_bar.show_snack_bar(self._["old_password_required"], bgcolor=ft.Colors.RED)
                return
                
            if not new_password:
                await self.app.snack_bar.show_snack_bar(self._["new_password_required"], bgcolor=ft.Colors.RED)
                return
                
            if new_password != confirm_password:
                await self.app.snack_bar.show_snack_bar(self._["passwords_not_match"], bgcolor=ft.Colors.RED)
                return
                
            _username = self.app.current_username
            if _username:
                success = await self.app.auth_manager.change_password(_username, old_password, new_password)
                
                if success:
                    old_password_field.value = ""
                    new_password_field.value = ""
                    confirm_password_field.value = ""
                    old_password_field.update()
                    new_password_field.update()
                    confirm_password_field.update()
                    
                    await self.app.snack_bar.show_snack_bar(self._["password_changed"], bgcolor=ft.Colors.GREEN)
                else:
                    await self.app.snack_bar.show_snack_bar(self._["old_password_incorrect"], bgcolor=ft.Colors.RED)
            else:
                await self.app.snack_bar.show_snack_bar(self._["not_logged_in"], bgcolor=ft.Colors.RED)
        
        async def toggle_login_required(_):
            login_required = login_required_switch.value
            self.user_config["login_required"] = login_required
            await self.config_manager.save_user_config(self.user_config)
            
            if login_required:
                await self.app.snack_bar.show_snack_bar(self._["login_required_enabled"], bgcolor=ft.Colors.GREEN)
            else:
                await self.app.snack_bar.show_snack_bar(self._["login_required_disabled"], bgcolor=ft.Colors.GREEN)
        
        username = self.app.current_username or "admin"
        
        old_password_field = ft.TextField(
            password=True,
            width=300,
            label=self._["old_password"],
        )
        
        new_password_field = ft.TextField(
            password=True,
            width=300,
            label=self._["new_password"],
        )
        
        confirm_password_field = ft.TextField(
            password=True,
            width=300,
            label=self._["confirm_password"],
        )
        
        change_password_button = ft.ElevatedButton(
            text=self._["change_password"],
            on_click=change_password,
            icon=ft.icons.LOCK_RESET,
        )
        
        login_required_switch = ft.Switch(
            value=self.get_config_value("login_required", False),
            on_change=toggle_login_required,
        )
        
        return ft.Column(
            [
                self.create_setting_group(
                    self._["security_settings"],
                    self._["web_login_configuration"],
                    [
                        self.create_setting_row(
                            self._["login_required"],
                            login_required_switch,
                        ),
                        self.create_setting_row(
                            self._["current_username"],
                            ft.Text(username),
                        ),
                        self.create_setting_row(
                            self._["old_password"],
                            old_password_field,
                        ),
                        self.create_setting_row(
                            self._["new_password"],
                            new_password_field,
                        ),
                        self.create_setting_row(
                            self._["confirm_password"],
                            confirm_password_field,
                        ),
                        self.create_setting_row(
                            "",
                            change_password_button,
                        ),
                    ],
                    is_mobile,
                ),
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
        )

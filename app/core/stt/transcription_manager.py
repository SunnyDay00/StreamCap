import os
from ...utils.logger import logger

class TranscriptionManager:
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.processing_files = set()
        # No longer loading JSON data
    
    def _normalize_path(self, file_path):
        return os.path.normpath(os.path.abspath(file_path))

    def is_processing(self, file_path):
        return self._normalize_path(file_path) in self.processing_files

    def mark_processing(self, file_path):
        """Manually mark a file as processing (useful for immediate UI updates)"""
        self.processing_files.add(self._normalize_path(file_path))

    AI_SUFFIX = "_ai"
    CLOUD_SUFFIX = "_cloud"
    LOCAL_SUFFIX = "_local"

    def _get_txt_path(self, file_path, source=None, ai_optimized=False):
        """
        Get transcription path based on source and optimization.
        source: 'cloud', 'local', or None (legacy/default)
        """
        base, ext = os.path.splitext(file_path)
        
        # Determine source suffix
        s_suffix = ""
        if source == "cloud":
            s_suffix = self.CLOUD_SUFFIX
        elif source == "local":
            s_suffix = self.LOCAL_SUFFIX
            
        # Determine AI suffix
        a_suffix = self.AI_SUFFIX if ai_optimized else ""
        
        return f"{base}{s_suffix}{a_suffix}.txt"

    def _get_existing_transcription_info(self, file_path):
        """
        Scan for existing transcription files and return the best match path and metadata.
        Priority: Cloud+AI > Local+AI > Legacy AI > Cloud > Local > Legacy Raw
        """
        # Define priority list of (source, ai_optimized) tuples
        priorities = [
            ("cloud", True),
            ("local", True),
            (None, True),   # Legacy AI
            ("cloud", False),
            ("local", False),
            (None, False)   # Legacy Raw
        ]
        
        for source, is_ai in priorities:
            path = self._get_txt_path(file_path, source=source, ai_optimized=is_ai)
            if os.path.exists(path):
                return path, {"source": source, "ai_optimized": is_ai}
        
        return None, None

    def get_text(self, file_path):
        """Get transcription text. Prioritizes AI optimized and Cloud versions."""
        path, _ = self._get_existing_transcription_info(file_path)
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                logger.error(f"Failed to read transcription {path}: {e}")
        return None

    def set_text(self, file_path, text, metadata=None):
        """
        Save transcription text with appropriate naming.
        metadata: {'ai_optimized': bool, 'source': 'cloud'/'local'}
        """
        if metadata is None:
            metadata = {}
            
        is_optimized = metadata.get("ai_optimized", False)
        source = metadata.get("source", "local") # Default to local if not specified
        
        txt_path = self._get_txt_path(file_path, source=source, ai_optimized=is_optimized)
        
        try:
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(text)
            
            # Note: We do NOT strictly delete other versions here to avoid data loss,
            # allowing user to switch between Cloud/Local results if they exist.
            # However, logic elsewhere might rely on checking "has_text", which now follows priority.
            
            # Cleanup legacy .meta file if it exists (we don't use it anymore)
            meta_path = os.path.splitext(file_path)[0] + ".meta"
            if os.path.exists(meta_path):
                try:
                    os.remove(meta_path)
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Failed to save transcription to {txt_path}: {e}")

    def get_metadata(self, file_path):
        """Infer metadata from best existing file."""
        _, metadata = self._get_existing_transcription_info(file_path)
        return metadata if metadata else {"ai_optimized": False, "source": "local"}

    def has_text(self, file_path):
        """Check if any transcription file exists."""
        path, _ = self._get_existing_transcription_info(file_path)
        return path is not None

    async def transcribe_file(self, file_path, executor=None):
        """
        Transcribe a file using configured service (Cloud/Local) and AI optimization.
        """
        norm_path = self._normalize_path(file_path)
        self.processing_files.add(norm_path)
        try:
            from ...core.stt.local_stt import LocalSTTService
            from ...core.ai.ai_optimizer import AITextOptimizer
            import asyncio

            # Check Cloud STT setting
            use_cloud = self.config_manager.get_config_value("enable_cloud_stt", False)
            
            loop = asyncio.get_running_loop()
            text_result = ""
            source = "local"

            if use_cloud:
                source = "cloud"
                from ...core.stt.cloud_stt import CloudSTTService
                cloud_service = CloudSTTService(self.config_manager)
                text_result = await cloud_service.transcribe(file_path)
            else:
                source = "local"
                stt_service = LocalSTTService(self.config_manager)
                is_ready, status = stt_service.check_models_status()
                if not is_ready:
                     raise Exception("STT Models are not ready/downloaded")
                
                text_result = await loop.run_in_executor(executor, lambda: stt_service.transcribe(file_path))
            
            # first save raw result
            self.set_text(file_path, text_result, metadata={"ai_optimized": False, "source": source})

            # 2. AI Optimization
            is_optimized = False
            try:
                ai_optimizer = AITextOptimizer(self.config_manager)
                optimized_text = await ai_optimizer.optimize_text(text_result)
                if optimized_text != text_result:
                    text_result = optimized_text
                    is_optimized = True
            except Exception as ai_e:
                logger.error(f"AI Optimization failed: {ai_e}")
                # Keep using raw text result

            if is_optimized:
                 self.set_text(file_path, text_result, metadata={"ai_optimized": True, "source": source})
                 # Cleanup raw version to avoid clutter (User request)
                 raw_path = self._get_txt_path(file_path, source=source, ai_optimized=False)
                 if os.path.exists(raw_path):
                     try:
                         os.remove(raw_path)
                         logger.info(f"Cleaned up raw transcription: {raw_path}")
                     except Exception:
                         pass

            # Cleanup Other Sources to prevent duplicate/conflicting files
            # If we just saved 'cloud', delete 'local'. If 'local', delete 'cloud'.
            other_sources = ['local', 'cloud', None] # None is legacy
            current_source = source
            
            for s in other_sources:
                 if s != current_source:
                     # Remove both AI and Raw for other sources
                     for ai in [True, False]:
                         p = self._get_txt_path(file_path, source=s, ai_optimized=ai)
                         if os.path.exists(p):
                             try:
                                 os.remove(p)
                                 logger.info(f"Cleaned up stale source file: {p}")
                             except Exception:
                                 pass
                 
            return text_result
        finally:
            if norm_path in self.processing_files:
                self.processing_files.discard(norm_path)


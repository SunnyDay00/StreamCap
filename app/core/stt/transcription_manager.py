import os
from ...utils.logger import logger

class TranscriptionManager:
    def __init__(self, config_manager):
        self.config_manager = config_manager
        # No longer loading JSON data

    AI_SUFFIX = "_AI"

    def _get_txt_path(self, file_path, ai_optimized=False):
        """Get the expected path for the transcription text file."""
        suffix = self.AI_SUFFIX if ai_optimized else ""
        return os.path.splitext(file_path)[0] + suffix + ".txt"

    def get_text(self, file_path):
        """Get transcription text. Prioritizes AI optimized version."""
        # Check for AI optimized version first
        ai_path = self._get_txt_path(file_path, ai_optimized=True)
        if os.path.exists(ai_path):
            try:
                with open(ai_path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                logger.error(f"Failed to read AI transcription {ai_path}: {e}")

        # Check for normal version
        txt_path = self._get_txt_path(file_path, ai_optimized=False)
        if os.path.exists(txt_path):
            try:
                with open(txt_path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                logger.error(f"Failed to read transcription {txt_path}: {e}")
        return None



    def set_text(self, file_path, text, metadata=None):
        """
        Save transcription text.
        If metadata['ai_optimized'] is True, save with AI suffix.
        Crucially, if saving Non-AI, remove any existing AI file to prevent serving stale AI content.
        """
        is_optimized = metadata.get("ai_optimized", False) if metadata else False
        txt_path = self._get_txt_path(file_path, ai_optimized=is_optimized)
        
        try:
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(text)
            
            # Clean up logic to maintain consistency
            if not is_optimized:
                # If we are saving a RAW transcription, we must delete any existing AI transcription
                # because get_text prioritizes AI. If we didn't delete it, get_text would return the OLD AI result
                # instead of this NEW RAW result.
                ai_path = self._get_txt_path(file_path, ai_optimized=True)
                if os.path.exists(ai_path):
                    try:
                        os.remove(ai_path)
                        logger.info(f"Removed stale AI transcription: {ai_path}")
                    except Exception as e:
                        logger.error(f"Failed to remove stale AI file {ai_path}: {e}")

            # Note: We don't delete RAW file when saving AI file, as having a backup/base is fine.
            # And get_text prefers AI anyway.

            # Cleanup legacy .meta file if it exists
            meta_path = os.path.splitext(file_path)[0] + ".meta"
            if os.path.exists(meta_path):
                try:
                    os.remove(meta_path)
                except Exception as e:
                    logger.warning(f"Failed to remove legacy meta file: {e}")

        except Exception as e:
            logger.error(f"Failed to save transcription to {txt_path}: {e}")

    def get_metadata(self, file_path):
        """Infer metadata from file existence."""
        ai_path = self._get_txt_path(file_path, ai_optimized=True)
        if os.path.exists(ai_path):
            return {"ai_optimized": True}
        
        # Check legacy meta file just in case or if we want to support transition?
        # For this refactor, we rely on filename.
        return {"ai_optimized": False}

    def has_text(self, file_path):
        """Check if any transcription file exists."""
        ai_path = self._get_txt_path(file_path, ai_optimized=True)
        if os.path.exists(ai_path):
            return True
        
        txt_path = self._get_txt_path(file_path, ai_optimized=False)
        return os.path.exists(txt_path)

    async def transcribe_file(self, file_path, executor=None):
        """
        Transcribe a file using LocalSTTService and optional AI optimization.
        Returns the transcribed text.
        """
        from ...core.stt.local_stt import LocalSTTService
        from ...core.ai.ai_optimizer import AITextOptimizer
        import asyncio

        stt_service = LocalSTTService(self.config_manager)
        is_ready, status = stt_service.check_models_status()
        if not is_ready:
             raise Exception("STT Models are not ready/downloaded")

        loop = asyncio.get_running_loop()
        
        # 1. Local STT
        # Use passed executor or default to None (default loop executor)
        text_result = await loop.run_in_executor(executor, lambda: stt_service.transcribe(file_path))
        
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
            # Proceed with original text if AI fails

        self.set_text(file_path, text_result, metadata={"ai_optimized": is_optimized} if is_optimized else None)
        return text_result


import os
from ...utils.logger import logger

class TranscriptionManager:
    def __init__(self, config_manager):
        self.config_manager = config_manager
        # No longer loading JSON data

    def _get_txt_path(self, file_path):
        """Get the expected path for the transcription text file."""
        return os.path.splitext(file_path)[0] + ".txt"

    def get_text(self, file_path):
        """Get transcription text for a file path by reading the .txt file."""
        txt_path = self._get_txt_path(file_path)
        if os.path.exists(txt_path):
            try:
                with open(txt_path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                logger.error(f"Failed to read transcription file {txt_path}: {e}")
        return None

    def set_text(self, file_path, text):
        """Save transcription text to a .txt file next to the media file."""
        txt_path = self._get_txt_path(file_path)
        try:
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception as e:
            logger.error(f"Failed to save transcription to {txt_path}: {e}")

    def has_text(self, file_path):
        """Check if transcription .txt file exists."""
        txt_path = self._get_txt_path(file_path)
        return os.path.exists(txt_path)


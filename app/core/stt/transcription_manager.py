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



    def _get_meta_path(self, file_path):
        """Get the expected path for the transcription metadata file."""
        return os.path.splitext(file_path)[0] + ".meta"

    def set_text(self, file_path, text, metadata=None):
        """
        Save transcription text to a .txt file next to the media file.
        Optionally save metadata to a .meta json file.
        """
        txt_path = self._get_txt_path(file_path)
        try:
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(text)
            
            # Metadata handling
            meta_path = self._get_meta_path(file_path)
            if metadata:
                import json
                try:
                    with open(meta_path, "w", encoding="utf-8") as f:
                        json.dump(metadata, f, ensure_ascii=False)
                except Exception as e:
                    logger.error(f"Failed to save metadata to {meta_path}: {e}")
            elif os.path.exists(meta_path):
                 # Clear old metadata if set_text is called without metadata (re-identification case)
                 # Or should we keep it? Better to clear or overwrite if None passed implies "new raw transcription".
                 # Assuming set_text is a full overwrite.
                 os.remove(meta_path)
                 
        except Exception as e:
            logger.error(f"Failed to save transcription to {txt_path}: {e}")

    def get_metadata(self, file_path):
        """Get transcription metadata if available."""
        meta_path = self._get_meta_path(file_path)
        if os.path.exists(meta_path):
            try:
                import json
                with open(meta_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to read metadata file {meta_path}: {e}")
        return {}

    def has_text(self, file_path):
        """Check if transcription .txt file exists."""
        txt_path = self._get_txt_path(file_path)
        return os.path.exists(txt_path)


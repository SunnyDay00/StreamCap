import os
from ...utils.logger import logger
import datetime as import_datetime

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

    def _get_txt_path(self, file_path, source=None, ai_optimized=False, model=None):
        """
        Get transcription path based on source, optimization, and model.
        source: 'cloud', 'local', or None (legacy/default)
        model: optional model specific string (e.g. 'fun-asr-nano')
        """
        base, ext = os.path.splitext(file_path)
        
        # Determine source suffix
        s_suffix = ""
        if source == "cloud":
            s_suffix = self.CLOUD_SUFFIX
        elif source == "local":
            s_suffix = self.LOCAL_SUFFIX
        
        # Determine model suffix
        # The user wants "local_FunASR_ai", so model goes after source, before AI
        m_suffix = f"_{model}" if model else ""
            
        # Determine AI suffix
        a_suffix = self.AI_SUFFIX if ai_optimized else ""
        
        return f"{base}{s_suffix}{m_suffix}{a_suffix}.txt"

    def _get_existing_transcription_info(self, file_path):
        """
        Scan for existing transcription files and return the best match path and metadata.
        Priority: 
        1. Cloud AI
        2. Local AI (Any model)
        3. Legacy AI
        4. Cloud Raw
        5. Local Raw (Any model)
        6. Legacy Raw
        """
        
        directory = os.path.dirname(file_path)
        basename = os.path.splitext(os.path.basename(file_path))[0]
        
        if not os.path.exists(directory):
             return None, None

        candidates = []
        
        try:
            with os.scandir(directory) as it:
                for entry in it:
                    if not entry.is_file() or not entry.name.lower().endswith(".txt"):
                        continue
                    
                    name_root = os.path.splitext(entry.name)[0]
                    # Check if file starts with basename
                    # Use a delimiter check to ensure we don't match "videoclip2" against "videoclip"
                    if not name_root.startswith(basename):
                        continue
                        
                    # Calculate suffix remainder
                    suffix = name_root[len(basename):]
                    if suffix and not suffix.startswith("_"):
                         # Basename partial match (e.g. video_vs_videoclip)
                         continue
                    
                    # Analyze suffix
                    meta = {"path": entry.path, "priority": 0}
                    
                    is_ai = self.AI_SUFFIX in suffix
                    meta["ai_optimized"] = is_ai
                    
                    # Determine Source & Model
                    # Expected format: _source[_model][_ai]
                    
                    if self.CLOUD_SUFFIX in suffix:
                        meta["source"] = "cloud"
                        # base priority 30 (AI) or 10 (Raw)
                        p = 30 if is_ai else 10
                        if "paraformer" in suffix.lower(): # e.g. _cloud_paraformer
                             meta["model"] = "Paraformer" # Guess
                        meta["priority"] = p
                    elif self.LOCAL_SUFFIX in suffix:
                        meta["source"] = "local"
                        # base priority 20 (AI) or 5 (Raw)
                        p = 20 if is_ai else 5
                        meta["priority"] = p
                        
                        # Extract model name?
                        # suffix is like "_local_FunASR_ai" or "_local"
                        # remove known parts
                        rem = suffix.replace(self.LOCAL_SUFFIX, "").replace(self.AI_SUFFIX, "")
                        # rem should be "_ModelName" or empty
                        if rem.startswith("_"):
                             meta["model"] = rem[1:] # e.g. "Fun-ASR-Nano"
                             
                    else:
                        # Legacy (no source suffix or just _ai)
                        if is_ai and suffix == self.AI_SUFFIX: 
                            meta["source"] = None
                            meta["priority"] = 15
                        elif suffix == "":
                            meta["source"] = None
                            meta["priority"] = 1
                        else:
                            # Unrelated txt file that happens to start with basename?
                            # e.g. "video_readme.txt". Ignore if it doesn't match our specific patterns?
                            # But we want to be liberal with legacy.
                            # Let's assume generic text files are low priority legacy raw
                            continue
                            
                    candidates.append(meta)
        except Exception as e:
            logger.error(f"Error scanning for transcriptions: {e}")
            return None, None

        if not candidates:
            return None, None
            
        # Sort by priority desc
        candidates.sort(key=lambda x: x["priority"], reverse=True)
        best = candidates[0]
        
        # Return format consistent with caller expectation
        # metadata dict should just contain source, ai_optimized, model
        ret_meta = {k: v for k, v in best.items() if k in ["source", "ai_optimized", "model"]}
        return best["path"], ret_meta

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
        model_name = metadata.get("model")
        
        # New: Pass model name to get path
        txt_path = self._get_txt_path(file_path, source=source, ai_optimized=is_optimized, model=model_name)
        
        try:
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(text)
            
            # --- Cleanup Logic ---
            # We want to remove *other* versions of the same type (Source+AI state)
            # but which might have DIFFERENT model names or NO model name (legacy)
            # e.g. If saving "_local_FunASR_ai.txt", remove "_local_Paraformer_ai.txt" and "_local_ai.txt"
            
            directory = os.path.dirname(file_path)
            basename = os.path.splitext(os.path.basename(file_path))[0]
            
            if os.path.exists(directory):
                with os.scandir(directory) as it:
                    for entry in it:
                        if not entry.is_file() or not entry.name.lower().endswith(".txt"):
                            continue
                        
                        # Don't delete self
                        if os.path.abspath(entry.path) == os.path.abspath(txt_path):
                            continue
                            
                        name_root = os.path.splitext(entry.name)[0]
                        if not name_root.startswith(basename):
                            continue
                        
                        suffix = name_root[len(basename):]
                        
                        # Check strict compatibility for deletion
                        # We delete if:
                        # 1. It matches the same Source (local/cloud)
                        # 2. It matches the same AI state (optimized/raw)
                        # 3. It's legacy (no source) and we are saving a prioritized version?
                        #    No, user only said "ensure correctly deleted" implies replacement functionality.
                        
                        is_entry_ai = self.AI_SUFFIX in suffix
                        if is_entry_ai != is_optimized:
                            continue # Don't delete AI dict/raw dict cross-wise
                            
                        is_entry_cloud = self.CLOUD_SUFFIX in suffix
                        is_entry_local = self.LOCAL_SUFFIX in suffix
                        
                        # If current is local, delete other locals
                        if source == "local" and is_entry_local:
                             try:
                                 os.remove(entry.path)
                                 logger.info(f"Cleaned up old local version: {entry.name}")
                             except: pass
                        # If current is cloud, delete other clouds
                        elif source == "cloud" and is_entry_cloud:
                             try:
                                 os.remove(entry.path)
                                 logger.info(f"Cleaned up old cloud version: {entry.name}")
                             except: pass
                        # If legacy (no source match), maybe delete only if we are creating one?
                        # User specifically mentioned "re-identifying correctly deletes PREVIOUS".
                        # If previously was local_paraformer and now local_funasr, yes delete.
                        # If previously was legacy, also delete?
                        # Let's say if we are saving "local", we delete "local" variants.
                        
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
                text_result, model_name = await cloud_service.transcribe(file_path)
            else:
                source = "local"
                stt_service = LocalSTTService(self.config_manager)
                is_ready, status = stt_service.check_models_status()
                if not is_ready:
                     raise Exception("STT Models are not ready/downloaded")
                
                # Run in executor, now returns tuple (text, model_name)
                text_result, model_name = await loop.run_in_executor(executor, lambda: stt_service.transcribe(file_path))
            
            # first save raw result
            self.set_text(file_path, text_result, metadata={"ai_optimized": False, "source": source, "model": model_name})

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
                 self.set_text(file_path, text_result, metadata={"ai_optimized": True, "source": source, "model": model_name})
                 # Cleanup raw version to avoid clutter (User request)
                 # MUST pass model_name to get the correct filename to delete!
                 raw_path = self._get_txt_path(file_path, source=source, ai_optimized=False, model=model_name)
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


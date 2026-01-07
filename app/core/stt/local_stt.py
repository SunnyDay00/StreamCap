import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading

from ...utils.logger import logger
from ..media.audio_extractor import AudioExtractor

# Using explicit model IDs to ensure download success
MODELS = {
    "vad": "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
    "asr": "iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
    "punc": "iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch"
}

class LocalSTTService:
    _instance = None

    def __new__(cls, config_manager):
        if cls._instance is None:
            cls._instance = super(LocalSTTService, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def __init__(self, config_manager):
        if self.initialized:
            return
        self.config_manager = config_manager
        self.run_path = config_manager.run_path
        self.models_dir = os.path.join(self.run_path, "assets", "models")
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.model_pipeline = None
        self.lock = threading.Lock()
        self.initialized = True

    def check_models_status(self):
        """Check if all models are downloaded."""
        status = {}
        all_ready = True
        
        for key, model_id in MODELS.items():
            model_name = model_id.split("/")[-1]
            model_path = os.path.join(self.models_dir, model_name)
            
            if os.path.exists(model_path) and os.path.isdir(model_path):
                status[key] = True
            else:
                status[key] = False
                all_ready = False
                
        return all_ready, status

    def download_models(self, progress_callback=None):
        """Download all required models."""
        try:
            from modelscope.hub.snapshot_download import snapshot_download
            
            os.makedirs(self.models_dir, exist_ok=True)
            
            for key, model_id in MODELS.items():
                logger.info(f"Downloading model: {model_id}")
                if progress_callback:
                    progress_callback(f"Downloading {key} model...")
                
                model_name = model_id.split("/")[-1]
                local_dir = os.path.join(self.models_dir, model_name)
                
                snapshot_download(model_id, local_dir=local_dir)
                
            if progress_callback:
                progress_callback("All models downloaded.")
            return True, "Success"
        except Exception as e:
            logger.error(f"Model download failed: {e}")
            return False, str(e)

    def load_pipeline(self):
        """Load the FunASR pipeline."""
        if self.model_pipeline:
            return

        is_ready, _ = self.check_models_status()
        if not is_ready:
            raise FileNotFoundError("Models are not fully downloaded.")

        vad_path = os.path.join(self.models_dir, MODELS["vad"].split("/")[-1])
        asr_path = os.path.join(self.models_dir, MODELS["asr"].split("/")[-1])
        punc_path = os.path.join(self.models_dir, MODELS["punc"].split("/")[-1])

        logger.info("Loading Local STT pipeline...")
        from funasr import AutoModel

        self.model_pipeline = AutoModel(
            model=asr_path,
            vad_model=vad_path,
            punc_model=punc_path,
        )
        logger.info("Local STT pipeline loaded.")

    def transcribe(self, file_path: str):
        """Transcribe audio file."""
        # Ensure we only run one transcription at a time to prevent model conflicts and resource exhaustion
        with self.lock:
            if not self.model_pipeline:
                 self.load_pipeline()

            # Extract audio if valid video
            audio_path = file_path
            
            ext = os.path.splitext(file_path)[1].lower()
            if ext not in ['.mp3', '.wav', '.m4a', '.aac', '.flac']:
                 pass 

            try:
               res = self.model_pipeline.generate(input=audio_path, batch_size_s=300, hotword='StreamCap')
               
               if isinstance(res, list) and len(res) > 0:
                   return res[0].get("text", "")
               return str(res)
               
            except Exception as e:
                logger.error(f"Transcription failed: {e}")
                raise e

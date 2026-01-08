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
    "punc": "iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch",
    "enhance": "dengcunqin/speech_mossformer2_separation_temporal_16k"
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
        self.separation_pipeline = None # New pipeline for separation
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

    def process_audio_separation(self, audio_path: str) -> str:
        """Run MossFormer2 to separate vocals."""
        try:
            from modelscope.pipelines import pipeline
            from modelscope.utils.constant import Tasks
            import soundfile as sf
            import numpy as np
            
            if not self.separation_pipeline:
                 model_id = MODELS["enhance"]
                 # Locate model dir if downloaded
                 model_name = model_id.split("/")[-1]
                 model_dir = os.path.join(self.models_dir, model_name)
                 
                 logger.info(f"Loading separation model from {model_dir}...")
                 # Use local path if exists, else ID (which might trigger download if not handled, but we rely on download_models)
                 load_path = model_dir if os.path.exists(model_dir) else model_id
                 
                 self.separation_pipeline = pipeline(
                     task=Tasks.audio_separation,
                     model=load_path
                 )
            
            logger.info(f"Running MossFormer2 separation on {audio_path}...")
            
            # Run inference
            # result usually contains 'output_pcm_list' (list of numpy arrays)
            result = self.separation_pipeline(audio_in=audio_path)
            
            if 'output_pcm_list' in result:
                pcm_list = result['output_pcm_list']
                if len(pcm_list) > 0:
                    # Usually speaker 0 is the target or one of them. 
                    # For separation, we might have multiple. We'll pick index 0 for now.
                    # Or we should check if there's a convention.
                    # Assuming index 0 is the primary source/speech.
                    enhanced_pcm = pcm_list[0]
                    
                    # Ensure it's in the right shape for soundfile (samples, channels)
                    # result might be (1, samples) or (samples,).
                    if len(enhanced_pcm.shape) == 2 and enhanced_pcm.shape[0] < enhanced_pcm.shape[1]:
                         enhanced_pcm = enhanced_pcm.T
                    
                    # Save to temp file
                    base, ext = os.path.splitext(audio_path)
                    output_path = f"{base}_enhanced.wav"
                    
                    # Get sample rate - pipeline usually matches input or 16000? 
                    # MossFormer2 16k model outputs 16k.
                    sf.write(output_path, enhanced_pcm, 16000)
                    
                    logger.info(f"Separation complete. Saved to: {output_path}")
                    return output_path
            
            logger.warning("No audio data found in separation result.")
            return audio_path

        except Exception as e:
            logger.error(f"Vocal separation failed: {e}")
            return audio_path

    def transcribe(self, file_path: str):
        """Transcribe audio file."""
        # Ensure we only run one transcription at a time to prevent model conflicts and resource exhaustion
        with self.lock:
            if not self.model_pipeline:
                 self.load_pipeline()

            # Extract audio if valid video
            audio_path = file_path
            
            # Check for Vocal Enhancement
            enhanced_temp_path = None
            if self.config_manager.get("enable_vocal_enhancement", False):
                 try:
                     enhanced_path = self.process_audio_separation(audio_path)
                     if enhanced_path != audio_path:
                         audio_path = enhanced_path
                         enhanced_temp_path = enhanced_path
                 except Exception as e:
                     logger.error(f"Enhancement step failed, proceeding with original: {e}")

            try:
               logger.info(f"Transcribing: {audio_path}")
               # AutoModel inference
               res = self.model_pipeline.generate(input=audio_path, batch_size_s=300, hotword='StreamCap')
               
               result_text = ""
               if isinstance(res, list) and len(res) > 0:
                   result_text = res[0].get("text", "")
               else:
                   result_text = str(res)
               
               return result_text
               
            except Exception as e:
                logger.error(f"Transcription failed: {e}")
                raise e
            finally:
                # Cleanup temp enhanced file
                if enhanced_temp_path and os.path.exists(enhanced_temp_path):
                    try:
                        os.remove(enhanced_temp_path)
                        logger.info(f"Removed temp enhanced file: {enhanced_temp_path}")
                    except Exception as ex:
                        logger.warning(f"Failed to remove temp file: {ex}")

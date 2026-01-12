import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading

from ...utils.logger import logger
from ..media.audio_extractor import AudioExtractor

# Using explicit model IDs to ensure download success
# Using explicit model IDs to ensure download success
MODELS = {
    "vad": "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
    "punc": "iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch",
    "enhance": "dengcunqin/speech_mossformer2_separation_temporal_16k"
}

ASR_MODELS = {
    "paraformer": "iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
    "fun_asr_nano": "FunAudioLLM/Fun-ASR-Nano-2512"
}

# --- Global Warning Suppression ---
import logging
import warnings
# Silence transformers logging
logging.getLogger("transformers").setLevel(logging.ERROR)
# Silence specific warnings
warnings.filterwarnings("ignore", message=".*The attention mask and the pad token id were not set.*")
warnings.filterwarnings("ignore", message=".*Setting `pad_token_id` to `eos_token_id`.*")
# ----------------------------------

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
        
        # Concurrency Control
        # Default to 1 if not set
        # Default to 1 if not set
        val = config_manager.get_config_value("local_max_concurrent_tasks", 1)
        max_concurrent = int(val) if val is not None else 1
        # Cap at 4 for sanity
        max_concurrent = max(1, min(4, max_concurrent))
        self.semaphore = threading.BoundedSemaphore(value=max_concurrent)
        self.initialized = True

    def _get_all_models(self):
        """Helper to get all models as a single dict for checking/downloading"""
        all_models = MODELS.copy()
        all_models.update(ASR_MODELS)
        return all_models

    def check_models_status(self):
        """Check if all models are downloaded."""
        status = {}
        all_ready = True
        
        for key, model_id in self._get_all_models().items():
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
            
            for key, model_id in self._get_all_models().items():
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
        # We only strictly require the active ASR model and auxiliary models (vad, punc)
        # But check_models_status checks ALL. For simplicity, we might want to relax this later
        # or just assume if user clicks 'download', everything is downloaded.
        
        # Determine which ASR model to use
        asr_model_key = self.config_manager.get_config_value("local_asr_model", "paraformer")
        if asr_model_key not in ASR_MODELS:
            logger.warning(f"Unknown ASR model key '{asr_model_key}', falling back to 'paraformer'")
            asr_model_key = "paraformer"
            
        asr_model_id = ASR_MODELS[asr_model_key]
        asr_model_name = asr_model_id.split("/")[-1]
        asr_path = os.path.join(self.models_dir, asr_model_name)

        vad_path = os.path.join(self.models_dir, MODELS["vad"].split("/")[-1])
        punc_path = os.path.join(self.models_dir, MODELS["punc"].split("/")[-1])
        
        # Verify active models exist
        for p in [asr_path, vad_path, punc_path]:
             if not os.path.exists(p):
                 raise FileNotFoundError(f"Required model path not found: {p}")

        logger.info(f"Loading Local STT pipeline with ASR model: {asr_model_key}...")
        
        # Optimize CPU usage with safety redundancy
        # Reserve cores for System/UI to prevent freeze
        try:
            import torch
            num_cores = os.cpu_count() or 4
            
            # 1. Determine concurrent tasks settings
            # We must read from config again or use the semaphore value if accessible, 
            # but reading config is safer as semaphore is internal
            val = self.config_manager.get_config_value("local_max_concurrent_tasks", 1)
            max_concurrent = int(val) if val is not None else 1
            max_concurrent = max(1, min(4, max_concurrent))

            # 2. Reserve cores (at least 2 for system/UI)
            reserved_cores = 2
            available_cores = max(1, num_cores - reserved_cores)
            
            # 3. Calculate threads per task
            # Total theoretical load = threads_per_task * max_concurrent
            # So: threads_per_task = available / concurrent
            num_threads = max(1, available_cores // max_concurrent)
            
            torch.set_num_threads(num_threads)
            logger.info(f"CPU Optimization: Cores={num_cores}, Reserved={reserved_cores}, Concurrent={max_concurrent} -> Threads/Task={num_threads}")
        except Exception as e:
            logger.warning(f"Failed to set PyTorch threads: {e}")

        from funasr import AutoModel

        # Base arguments
        model_kwargs = {
            "model": asr_path,
            "vad_model": vad_path,
            "punc_model": punc_path,
        }

        # Model specific adjustments
        if asr_model_key == "fun_asr_nano":
            # Fun-ASR-Nano-2512 specific
            model_kwargs["trust_remote_code"] = True
            # Add model directory to sys.path so 'model.py' and dependencies like 'ctc.py' can be imported
            import sys
            if asr_path not in sys.path:
                 sys.path.append(asr_path)
            # model_kwargs["remote_code"] = "./model.py"

        # Disable auto update check to prevent hangs
        model_kwargs["disable_update"] = True
        
        # Device selection
        device_selection = self.config_manager.get_config_value("local_device", "auto")
        if device_selection != "auto":
             model_kwargs["device"] = device_selection
             logger.info(f"Using explicitly configured device: {device_selection}")
        else:
             logger.info("Using automatic device detection (Default)")

        self.model_pipeline = AutoModel(**model_kwargs)
        self.active_asr_model = asr_model_key # Track which model is loaded
        logger.info("Local STT pipeline loaded.")

    def process_audio_separation(self, audio_path: str) -> str:
        """Run MossFormer2 to separate vocals using ONNX."""
        try:
            import onnxruntime as ort
            import numpy as np
            import soundfile as sf
            import librosa
            
            model_id = MODELS["enhance"]
            model_name = model_id.split("/")[-1]
            model_dir = os.path.join(self.models_dir, model_name)
            onnx_model_path = os.path.join(model_dir, "simple_model.onnx")
            
            if not os.path.exists(onnx_model_path):
                 logger.error(f"ONNX model not found at {onnx_model_path}")
                 return audio_path

            if not self.separation_pipeline:
                 logger.info(f"Loading ONNX model from {onnx_model_path}...")
                 self.separation_pipeline = ort.InferenceSession(onnx_model_path)
            
            session = self.separation_pipeline

            logger.info(f"Running MossFormer2 separation (ONNX) on {audio_path}...")
            
            # Load and Resample to 16k using librosa
            # mono=True ensures 1 channel
            audio_data, _ = librosa.load(audio_path, sr=16000, mono=True)
            
            # Input preparation: Model expects (Batch, Time) -> (1, samples)
            input_tensor = audio_data[np.newaxis, :].astype(np.float32)

            input_name = session.get_inputs()[0].name
            
            # Inference
            outputs = session.run(None, {input_name: input_tensor})
            est_source = outputs[0] # Expected shape: (Batch, Time, Sources)
            
            # Extract dominant speaker (Index 0)
            # Note: MossFormer2 separation usually outputs 2 sources. 
            # We assume source 0 is the desired one or we just pick the first one.
            ns = 0
            signal = est_source[0, :, ns]
            
            # Normalize
            max_val = np.abs(signal).max()
            if max_val > 0:
                signal = signal / max_val * 0.9
            
            # Save
            base, ext = os.path.splitext(audio_path)
            output_path = f"{base}_enhanced.wav"
            
            sf.write(output_path, signal, 16000)
            
            logger.info(f"Separation complete. Saved to: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Vocal separation failed: {e}")
            return audio_path

    def transcribe(self, file_path: str):
        """Transcribe audio file."""
        # Ensure we only run one transcription at a time to prevent model conflicts and resource exhaustion
        with self.semaphore:
            if not self.model_pipeline:
                 self.load_pipeline()

            # Extract audio if valid video
            audio_path = file_path
            
            # Check for Vocal Enhancement
            enhanced_temp_path = None
            if self.config_manager.get_config_value("enable_vocal_enhancement", False):
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

               # Base kwargs
               generate_kwargs = {
                   "input": audio_path,
                   "hotword": 'StreamCap'
               }
               
               if getattr(self, "active_asr_model", "") == "fun_asr_nano":
                   generate_kwargs["language"] = "中文"
                   generate_kwargs["batch_size"] = 1
                   # Nano model does not support batch decoding, must use batch_size=1 and no batch_size_s
               else:
                   # Default Paraformer supports dynamic batching
                   generate_kwargs["batch_size_s"] = 300

               res = self.model_pipeline.generate(**generate_kwargs)
               
               result_text = ""
               if isinstance(res, list) and len(res) > 0:
                   result_text = res[0].get("text", "")
               else:
                   result_text = str(res)
               
               return result_text, getattr(self, "active_asr_model", "local")
               
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

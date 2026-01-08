import os
import soundfile as sf
import numpy as np
from modelscope.pipelines import pipeline
from modelscope.utils.constant import Tasks
from app.core.config.config_manager import ConfigManager
from app.core.stt.local_stt import LocalSTTService

# Generate dummy 1s audio
sf.write("test_input.wav", np.random.uniform(-1, 1, 16000), 16000)

print("Defining model ID...")
model_id = "dengcunqin/speech_mossformer2_separation_temporal_16k"

print("Initializing pipeline...")
try:
    sep_pipeline = pipeline(
        task=Tasks.audio_separation,
        model=model_id,
        model_revision='v1.0.0' 
    )
    print("Pipeline initialized.")

    print("Running inference...")
    result = sep_pipeline(audio_in="test_input.wav")
    print(f"Result keys: {result.keys() if isinstance(result, dict) else type(result)}")
    
    if 'output_pcm_list' in result:
        print(f"Output PCM list length: {len(result['output_pcm_list'])}")
    
    print("SUCCESS: Model works.")
except Exception as e:
    print(f"FAILURE: {e}")
    import traceback
    traceback.print_exc()

if os.path.exists("test_input.wav"):
    os.remove("test_input.wav")

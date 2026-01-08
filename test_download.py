from modelscope.hub.snapshot_download import snapshot_download
import sys

def try_download(model_id, revision=None):
    print(f"Attempting download: {model_id} (rev={revision})...")
    try:
        path = snapshot_download(model_id, revision=revision)
        print(f"SUCCESS: {path}")
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        return False

# 1. Try MossFormer2 revisions
if try_download('iic/speech_mossformer2_separation_temporal_16k', revision='v1.0.0'): exit(0)
if try_download('iic/speech_mossformer2_separation_temporal_16k', revision='v1.0.1'): exit(0)
if try_download('iic/speech_mossformer2_separation_temporal_16k', revision='v1.0.2'): exit(0)
if try_download('iic/speech_mossformer2_separation_temporal_16k', revision='master'): exit(0)

# 2. Try MossFormer1 (Fallback)
if try_download('damo/speech_mossformer_separation_temporal_8k'): exit(0)

print("All attempts failed.")

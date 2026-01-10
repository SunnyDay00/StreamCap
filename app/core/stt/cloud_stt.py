import os
import asyncio
import math
import mimetypes
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List

# Try imports, they will be available at runtime via libs/
try:
    import httpx
    from openai import OpenAI
except ImportError:
    pass

from ...utils.logger import logger

class CloudSTTService:
    # Model Constraints
    MODEL_CONSTRAINTS = {
        "qwen3-asr-flash-filetrans": {
            "max_size_mb": 2000,
            "max_duration_sec": 12 * 3600, # 12 hours
            "safe_split_sec": 11.5 * 3600 # 11.5 hours safety margin
        },
        "qwen3-asr-flash": {
            "max_size_mb": 10,
            "max_duration_sec": 5 * 60,   # 5 minutes
            "safe_split_sec": 4.5 * 60    # 4.5 minutes safety margin
        }
    }
    
    # Defaults
    DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    
    def __init__(self, config_manager):
        self.config_manager = config_manager

    def _get_api_key(self):
        return self.config_manager.get_config_value("cloud_stt_api_key", "")

    def _get_base_url(self):
        return self.config_manager.get_config_value("cloud_stt_base_url", self.DEFAULT_BASE_URL)

    def _get_model(self):
        return self.config_manager.get_config_value("cloud_stt_model", "qwen3-asr-flash-filetrans")

    async def transcribe(self, file_path: str) -> str:
        """
        Main entry point for transcription. 
        Handles splitting if necessary, upload, and transcription logic.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Audio file not found: {file_path}")

        api_key = self._get_api_key()
        if not api_key:
            raise ValueError("API Key is missing")

        model = self._get_model()
        final_text = ""

        # 1. Check constraints & Split if needed
        chunks = await self._prepare_audio_chunks(file_path, model)
        logger.info(f"Audio prepared: {len(chunks)} chunks to process for model {model}")

        # 2. Process chunks
        # Sequential processing to keep it simple and orderly, though parallel is possible
        for i, chunk_path in enumerate(chunks):
            try:
                logger.info(f"Processing chunk {i+1}/{len(chunks)}: {chunk_path}")
                chunk_text = await self._process_single_file(chunk_path, api_key, model)
                if chunk_text:
                    if final_text:
                        final_text += " "
                    final_text += chunk_text
            except Exception as e:
                logger.error(f"Failed to process chunk {chunk_path}: {e}")
                # We continue to next chunk even if one fails? Or fail all? 
                # Let's append error marker but continue
                final_text += f" [Error processing chunk {i+1}] "
            finally:
                 # Cleanup temp chunk if it's not the original file
                 if chunk_path != file_path and os.path.exists(chunk_path):
                     try:
                         os.remove(chunk_path)
                     except:
                         pass

        return final_text.strip()
        
    async def _process_single_file(self, file_path: str, api_key: str, model: str) -> str:
        """
        Process a single audio file (chunk or full).
        Follows Aliyun 3-step flow: Policy -> Upload -> Transcribe
        """
        # Step 1: Get Upload Policy
        policy = await self._get_upload_policy(api_key, model)
        
        # Step 2: Upload to OSS
        oss_url = await self._upload_file_to_oss(policy, file_path)
        
        # Step 3: Transcribe using OpenAI-compatible API with oss URL
        text = await self._transcribe_oss_url(api_key, model, oss_url)
        
        return text

    async def _get_upload_policy(self, api_key: str, model: str):
        """Get Aliyun OSS upload policy."""
        url = "https://dashscope.aliyuncs.com/api/v1/uploads"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        params = {
            "action": "getPolicy",
            "model": model
        }
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code != 200:
                raise Exception(f"Get policy failed: {resp.text}")
            return resp.json()['data']

    async def _upload_file_to_oss(self, policy: dict, file_path: str) -> str:
        """Upload file to OSS using the provided policy."""
        file_name = Path(file_path).name
        key = f"{policy['upload_dir']}/{file_name}"
        upload_host = policy['upload_host']
        
        # Prepare form data
        # We need to use run_in_executor for standard requests if httpx multipart is tricky with policy
        # But httpx handles multipart fine.
        
        data = {
            'OSSAccessKeyId': policy['oss_access_key_id'],
            'Signature': policy['signature'],
            'policy': policy['policy'],
            'x-oss-object-acl': policy['x_oss_object_acl'],
            'x-oss-forbid-overwrite': policy['x_oss_forbid_overwrite'],
            'key': key,
            'success_action_status': '200',
        }
        
        # Read file
        # Check file size for memory safety? 2GB max for filetrans is big.
        # Ideally stream upload, but httpx/requests multipart usually reads into memory or requires open file.
        # Given we are in async, we should be careful. 
        # For simplicity and robustness with the Aliyun example, we'll try httpx with open file.
        
        files = {'file': (file_name, open(file_path, 'rb'))}
        
        async with httpx.AsyncClient(timeout=300.0) as client: # Generous timeout for upload
            resp = await client.post(upload_host, data=data, files=files)
            files['file'][1].close() # Close file handle
            
            if resp.status_code != 200:
                raise Exception(f"OSS upload failed: {resp.text}")
        
        # Protocol must be oss://
        return f"oss://{key}"

    async def _transcribe_oss_url(self, api_key: str, model: str, oss_url: str) -> str:
        """Call OpenAI-compatible API with OSS URL."""
        base_url = self._get_base_url()
        
        # We use standard OpenAI client but executed in thread pool since it's sync
        def _call_sync():
            msg_content = {
                "role": "user",
                "content": [
                    {"type": "input_audio", "input_audio": {"data": oss_url}}
                ]
            }
            # Add file transfer header
            extra_headers = {"X-DashScope-OssResourceResolve": "enable"}
            
            client = OpenAI(api_key=api_key, base_url=base_url)
            
            completion = client.chat.completions.create(
                model=model,
                messages=[msg_content],
                extra_headers=extra_headers
            )
            return completion.choices[0].message.content

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _call_sync)

    async def _prepare_audio_chunks(self, file_path: str, model: str) -> List[str]:
        """
        Check audio duration/size and split if necessary using ffmpeg.
        Returns list of temporary file paths (or original path if no split needed).
        """
        constraints = self.MODEL_CONSTRAINTS.get(model, self.MODEL_CONSTRAINTS["qwen3-asr-flash-filetrans"])
        
        # 1. Get info
        duration = await self._get_audio_duration(file_path)
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        
        logger.info(f"File info: {duration}s, {file_size_mb:.2f}MB. Limits: {constraints['max_duration_sec']}s, {constraints['max_size_mb']}MB")
        
        if duration <= constraints['max_duration_sec'] and file_size_mb <= constraints['max_size_mb']:
            return [file_path]
            
        # 2. Split required
        logger.info("Constraints exceeded, starting auto-split...")
        from ...core.media.ffmpeg_builders.base import FFmpegBuilder
        
        # We'll use segment muxer
        safe_time = constraints['safe_split_sec']
        output_pattern = f"{file_path}_part%03d{os.path.splitext(file_path)[1]}"
        
        # Construct splitter command
        # ffmpeg -i input -f segment -segment_time {safe_time} -c copy output_%03d.ext
        cmd = [
            "ffmpeg", "-y", "-i", file_path, 
            "-f", "segment", 
            "-segment_time", str(safe_time),
            "-c", "copy",
            output_pattern
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"Split failed: {stderr.decode()}")
            raise Exception("Audio splitting failed")
            
        # Find generated parts
        import glob
        # Glob pattern needs to handle the %03d part
        # file_path_part000.mp3 etc
        # Use directory listing to be safe
        directory = os.path.dirname(file_path)
        basename_glob = f"{os.path.basename(file_path)}_part*"
        
        parts = glob.glob(os.path.join(directory, basename_glob))
        parts.sort() # Ensure order
        
        return parts

    async def _get_audio_duration(self, file_path: str) -> float:
        """Get audio duration using ffprobe."""
        cmd = [
            "ffprobe", "-v", "error", 
            "-show_entries", "format=duration", 
            "-of", "default=noprint_wrappers=1:nokey=1", 
            file_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        try:
            return float(stdout.decode().strip())
        except:
             return 0.0

    async def test_connection(self):
        """Test API connection using a dummy listing or lightweight call."""
        # Simple policy get test
        try:
            api_key = self._get_api_key()
            if not api_key: return False, "Missing API Key"
            
            # Just try to get policy for the model, simplest auth check
            await self._get_upload_policy(api_key, self._get_model())
            return True, "Aliyun API Connected"
        except Exception as e:
            return False, str(e)

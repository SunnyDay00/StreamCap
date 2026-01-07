import asyncio
import os
import subprocess

from ...utils.logger import logger


class AudioExtractor:
    @staticmethod
    async def extract_audio(video_path: str, output_path: str = None) -> str:
        """
        Extract audio from video file using FFmpeg.
        
        Args:
            video_path: Path to the input video file
            output_path: Path to the output audio file. If None, will default to video filename with .mp3 extension
            
        Returns:
            str: Path to the extracted audio file
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        if output_path is None:
            base, _ = os.path.splitext(video_path)
            output_path = f"{base}_extracted.mp3"

        # FFmpeg command to extract audio: -i input -vn (no video) -acodec libmp3lame (or copy if compatible)
        # Using libmp3lame for broad compatibility, -q:a 2 for good quality
        # Overwrite existing file with -y
        cmd = [
            "ffmpeg",
            "-y",
            "-i", video_path,
            "-vn",
            "-acodec", "libmp3lame",
            "-q:a", "2",
            output_path
        ]

        logger.info(f"Extracting audio from {video_path} to {output_path}")
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"FFmpeg extraction failed: {stderr.decode()}")
                raise Exception(f"FFmpeg extraction failed: {stderr.decode()}")
                
            return output_path
            
        except Exception as e:
            logger.error(f"Error during audio extraction: {e}")
            raise e

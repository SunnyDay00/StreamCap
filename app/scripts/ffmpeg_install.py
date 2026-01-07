import asyncio
import os
import platform
import re
import subprocess
import sys
import zipfile
import shutil
from pathlib import Path

import httpx

from ..utils.logger import logger
from ..utils.utils import get_startup_info

current_platform = platform.system()
execute_dir = os.path.split(os.path.realpath(sys.argv[0]))[0]
ffmpeg_path = os.path.join(execute_dir, "ffmpeg")
startupinfo = get_startup_info()


async def unzip_file(zip_path: str | Path, extract_to: str | Path, delete: bool = True) -> None:
    if not os.path.exists(extract_to):
        os.makedirs(extract_to, exist_ok=True)

    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, _sync_unzip, zip_path, extract_to)
        logger.debug(f"Compressed file decompression completed: {zip_path}")
    except Exception as e:
        logger.error(f"Failed to decompress the compressed file: {e}")
        raise Exception("Failed to decompress the compressed file")

    if delete and os.path.exists(zip_path):
        os.remove(zip_path)


def _sync_unzip(zip_path: str | Path, extract_to: str | Path) -> None:
    if not zipfile.is_zipfile(zip_path):
        os.remove(zip_path)
        logger.error(f"The file is not a valid ZIP file: {zip_path}")
        raise ValueError("The file is not a valid ZIP file")

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(extract_to)


async def get_lanzou_download_link(url: str, password: str | None = None, headers: dict | None = None) -> str | None:
    try:

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url, headers=headers)
            html_str = response.text
            sign = re.search("var \\w+ = '([A-Za-z0-9_\\-+/]{80,})';", html_str).group(1)

            data = {
                "action": "downprocess",
                "p": password,
                "sign": sign,
                "kd": "1",
            }

            response = await client.post(
                "https://wweb.lanzoum.com/ajaxm.php?file=219989236",
                headers=headers,
                data=data
            )
            json_data = response.json()
            download_url = json_data["dom"] + "/file/" + json_data["url"]
            response = await client.get(download_url, headers=headers, follow_redirects=True)
            return str(response.url)
    except Exception as e:
        logger.error(f"Failed to obtain ffmpeg download address. {e}")


async def install_ffmpeg_windows(update_progress):
    try:
        logger.warning("ffmpeg is not installed.")
        logger.debug("Installing the latest version of ffmpeg for Windows...")
        await update_progress(0.1, "Get FFmpeg installation resources")
        headers = {
            'content-type': 'application/x-www-form-urlencoded',
            'accept-language': 'zh-CN,zh;q=0.9',
            'origin': 'https://wweb.lanzoum.com',
            'referer': 'https://wweb.lanzoum.com/iHAc22ly3r3g',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)'
                          ' Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0',
            'x-requested-with': 'XMLHttpRequest',
        }
        ffmpeg_url = await get_lanzou_download_link("https://wweb.lanzoum.com/iHAc22ly3r3g", "eots", headers)
        if ffmpeg_url:
            full_file_name = "ffmpeg_latest_build_20250124.zip"
            version = "v20250124"
            zip_file_path = Path(execute_dir) / full_file_name
            if Path(zip_file_path).exists():
                await update_progress(0.8, "FFmpeg installation file already exists")
                logger.debug("ffmpeg installation file already exists, start install...")
            else:
                await update_progress(0.2, "Start downloading FFmpeg installation package")
                logger.debug(f"FFmpeg Download ({version}): {ffmpeg_url}")
                async with (httpx.AsyncClient(follow_redirects=True) as client,
                            client.stream("GET", ffmpeg_url, headers=headers) as resp):

                    total_size = int(resp.headers.get("Content-Length", 0))
                    if resp.status_code != 200 and total_size != 0:
                        logger.error("FFmpeg package resources cannot be accessed")
                        raise Exception("The resource address cannot be accessed")

                    downloaded = 0
                    with open(zip_file_path, "wb") as f:
                        async for chunk in resp.aiter_bytes():
                            f.write(chunk)
                            downloaded += len(chunk)

                            progress = 0.2 + 0.6 * (downloaded / total_size)
                            await update_progress(
                                round(progress, 2), f"Downloading... {downloaded // 1024}KB/{total_size // 1024}KB"
                            )

            await update_progress(0.8, "Extracting and cleaning installation files")
            await unzip_file(zip_file_path, execute_dir)
            await update_progress(0.9, "Configuring FFmpeg environment variables")
            os.environ["PATH"] = ffmpeg_path + os.pathsep + os.environ.get("PATH")
            result = subprocess.run(["ffmpeg", "-version"], capture_output=True, startupinfo=startupinfo)
            if result.returncode == 0:
                logger.success("FFmpeg installation was successful")
                return True
            else:
                logger.error("ffmpeg installation failed. Please manually install ffmpeg by yourself")
                raise Exception("Please restart the program")
        else:
            logger.error("Please manually install ffmpeg by yourself")
            raise Exception("Failed to obtain the FFmpeg download address")
    except Exception as e:
        raise RuntimeError(f"FFmpeg install failed, {e}") from None


async def install_ffmpeg_mac(update_progress):
    logger.warning("FFmpeg is not installed.")
    logger.debug("Installing the stable version of ffmpeg for macOS...")
    await update_progress(0.1, "Get FFmpeg installation resources")
    await asyncio.sleep(2)
    await update_progress(0.3, "Please be patient and wait...")
    timeout = 300
    try:
        result = subprocess.run(["brew", "install", "ffmpeg"], capture_output=True,
                                startupinfo=startupinfo, timeout=timeout)
        if result.returncode == 0:
            logger.success("FFmpeg installation was successful. Restart for changes to take effect.")
            return True
        else:
            logger.error("FFmpeg installation failed")
            raise Exception("Please manually install FFmpeg by yourself")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install ffmpeg using Homebrew. {e}")
        logger.error("Please install ffmpeg manually or check your Homebrew installation.")
        raise Exception("Please check if Homebrew has been installed") from None
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        raise Exception(e) from None


async def install_ffmpeg_linux(update_progress):
    is_rhs = True
    timeout = 180

    try:
        logger.warning("ffmpeg is not installed.")
        logger.debug("Trying to install the stable version of ffmpeg")
        await update_progress(0.1, "Get FFmpeg installation resources")
        try:
            result = subprocess.run(["yum", "-y", "update"], capture_output=True,
                                    startupinfo=startupinfo, timeout=timeout)
            if result.returncode != 0:
                logger.error("Failed to update package lists using yum.")
                return False

            result = subprocess.run(["yum", "install", "-y", "ffmpeg"], capture_output=True,
                                    startupinfo=startupinfo, timeout=timeout)
            if result.returncode == 0:
                logger.success("ffmpeg installation was successful using yum. Restart for changes to take effect.")
                return True
            logger.error(result.stderr.decode("utf-8").strip())
        except subprocess.TimeoutExpired:
            logger.error("Command execution timed out. Please try to manually install ffmpeg.")
            raise Exception("Command execution timed out after {} seconds".format(timeout))
    except FileNotFoundError:
        logger.error("yum command not found, trying to install using apt...")
        is_rhs = False
    except Exception as e:
        logger.error(f"An error occurred while trying to install ffmpeg using yum: {e}")

    if not is_rhs:
        try:
            logger.debug("Trying to install the stable version of ffmpeg for Linux using apt...")
            try:
                result = subprocess.run(["apt", "update"], capture_output=True,
                                        startupinfo=startupinfo, timeout=timeout)
                if result.returncode != 0:
                    logger.error("Failed to update package lists using apt")
                    return False

                result = subprocess.run(["apt", "install", "-y", "ffmpeg"], capture_output=True,
                                        startupinfo=startupinfo, timeout=timeout)
                if result.returncode == 0:
                    logger.success("ffmpeg installation was successful using apt. Restart for changes to take effect.")
                    return True
                else:
                    logger.error(result.stderr.decode("utf-8").strip())
            except subprocess.TimeoutExpired:
                logger.error("Command execution timed out. Please try to manually install ffmpeg.")
                raise Exception("Command execution timed out after {} seconds".format(timeout))
        except FileNotFoundError:
            logger.error("apt command not found, unable to install ffmpeg. Please manually install ffmpeg by yourself")
        except Exception as e:
            logger.error(f"An error occurred while trying to install ffmpeg using apt: {e}")
    logger.error("Manual installation of ffmpeg is required. Please manually install ffmpeg by yourself.")
    raise Exception("Please manually install FFmpeg by yourself")


async def install_ffmpeg(update_progress) -> bool:
    if current_platform == "Windows":
        return await install_ffmpeg_windows(update_progress)
    elif current_platform == "Linux":
        return await install_ffmpeg_linux(update_progress)
    elif current_platform == "Darwin":
        return await install_ffmpeg_mac(update_progress)
    else:
        logger.warning(
            f"ffmpeg auto installation is not supported on this platform: {current_platform}. Please "
            f"install ffmpeg manually."
        )
    return False



def get_ffmpeg_path() -> str | None:
    """
    Search for ffmpeg executable in the following order:
    1. 'ffmpeg' directory in execute_dir (recursive search for bin/ffmpeg or straight ffmpeg)
    2. 'assets/ffmpeg' directory
    3. System PATH
    """
    search_dirs = [
        os.path.join(execute_dir, "ffmpeg"),
        os.path.join(execute_dir, "assets", "ffmpeg"),
    ]

    # 1. Search in local directories
    exe_name = "ffmpeg.exe" if current_platform == "Windows" else "ffmpeg"
    
    for dir_path in search_dirs:
        if not os.path.exists(dir_path):
            continue
            
        # Walk to find the executable, covering potential 'bin' subfolders from zip extraction
        for root, _, files in os.walk(dir_path):
            if exe_name in files:
                return os.path.join(root, exe_name)

    # 2. Search in PATH (fallback)
    return shutil.which("ffmpeg")


def get_ffmpeg_version_info(path: str) -> str | None:
    """Get version string from ffmpeg executable."""
    try:
        startupinfo = get_startup_info()
        result = subprocess.run([path, "-version"], capture_output=True, startupinfo=startupinfo, text=True)
        if result.returncode == 0:
            # First line usually contains version info, e.g., "ffmpeg version n4.4 ..."
            return result.stdout.splitlines()[0]
    except Exception as e:
        logger.error(f"Failed to get ffmpeg version: {e}")
    return None


async def check_ffmpeg_installed() -> bool:
    try:
        path = get_ffmpeg_path()
        if path:
            # Update env path to ensure other processes can find this local ffmpeg if needed
            # But primarily we should return True
            # Also verify it runs
            if get_ffmpeg_version_info(path):
                # Ensure the directory of the found ffmpeg is in PATH for legacy support
                ffmpeg_dir = os.path.dirname(path)
                if ffmpeg_dir not in os.environ["PATH"]:
                     os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ["PATH"]
                return True
    except Exception as e:
        logger.error(f"Error checking ffmpeg: {e}")
    return False


def update_env_path():
    """
    Deprecated: Path handling is now done dynamically in check_ffmpeg_installed or get_ffmpeg_path callers.
    Kept for compatibility if needed, but implementation updated to allow finding it.
    """
    path = get_ffmpeg_path()
    if path:
         ffmpeg_dir = os.path.dirname(path)
         if ffmpeg_dir not in os.environ["PATH"]:
             os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ["PATH"]


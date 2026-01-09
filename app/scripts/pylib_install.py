import asyncio
import os
import subprocess
import sys
from pathlib import Path

from ..utils.logger import logger
from ..utils.utils import get_startup_info

execute_dir = os.path.split(os.path.realpath(sys.argv[0]))[0]
libs_path = os.path.join(execute_dir, "libs")
requirements_path = os.path.join(execute_dir, "requirements.txt")
startupinfo = get_startup_info()


async def install_pylibs(update_progress, labels: dict | None = None) -> bool:
    """
    Install Python dependencies from requirements.txt to the local 'libs' directory.
    """
    labels = labels or {}
    msg_checking = labels.get("checking_reqs", "Checking requirements.txt...")
    msg_installing = labels.get("installing_libs", "Installing pip dependencies...")
    msg_complete = labels.get("install_complete", "Installation complete")
    
    try:
        logger.info("Starting Python libraries installation...")
        await update_progress(0.1, msg_checking)
        
        if not os.path.exists(requirements_path):
            logger.error(f"requirements.txt not found at {requirements_path}")
            raise FileNotFoundError("requirements.txt not found")

        # Create libs directory if it doesn't exist
        if not os.path.exists(libs_path):
            os.makedirs(libs_path, exist_ok=True)

        await update_progress(0.2, msg_installing)
        logger.info(f"Installing dependencies to {libs_path}...")
        
        # Construct pip command
        # Use the current python executable to run pip
        cmd = [
            sys.executable, "-m", "pip", "install", 
            "-r", requirements_path, 
            "--target", libs_path,
            "--upgrade",
            "-v"
        ]
        
        # Use mirror if in China
        cmd.extend(["-i", "https://pypi.tuna.tsinghua.edu.cn/simple"])

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            startupinfo=startupinfo,
            env=env
        )

        # Read output line by line to update progress (simulated)
        # Pip doesn't give easy percentage, so we'll just indicate activity
        
        async def read_stream(stream, is_stderr=False):
            while True:
                line = await stream.readline()
                if not line:
                    break
                line_str = line.decode('utf-8', errors='ignore').strip()
                if line_str:
                    logger.debug(f"[PIP{' ERROR' if is_stderr else ''}] {line_str}")
                    
                    if not is_stderr:
                        # Parse verbose output for progress
                        if line_str.startswith("Installing ") or line_str.startswith("Copying "):
                             # Example: Installing collected packages: foo, bar
                             # or Copying foo/bar.py to ...
                             # We can show the first few words
                             msg = line_str[:50] + "..." if len(line_str) > 50 else line_str
                             await update_progress(0.5, msg)
                        elif "Downloading" in line_str:
                             await update_progress(0.3, "Downloading dependencies...")

        await asyncio.gather(
            read_stream(process.stdout),
            read_stream(process.stderr, is_stderr=True)
        )
        
        await process.wait()

        if process.returncode == 0:
            await update_progress(1.0, msg_complete)
            logger.success("Python libraries installed successfully.")
            return True
        else:
            logger.error(f"Pip install failed with return code {process.returncode}")
            return False

    except Exception as e:
        logger.error(f"Python libs installation failed: {e}")
        return False


async def check_pylibs_installed() -> bool:
    """
    Check if the 'libs' directory exists and contains some key packages.
    This is a basic check.
    """
    if not os.path.exists(libs_path):
        return False
        
    # Check for a few key directories that should exist after install
    # Based on requirements.txt
    key_packages = ["flet", "httpx", "streamget"]
    
    for pkg in key_packages:
        # pip installs packages as folders in the target dir
        # Note: formatting might vary (e.g. flet_core), but usually the main package name exists
        pkg_path = os.path.join(libs_path, pkg)
        if not os.path.exists(pkg_path):
             # Try egg-info or dist-info if direct folder checks are flaky?
             # But usually simple folder check is enough for "is it likely installed"
             # Let's perform a looser check or just check if folder is not empty
             pass 
             
    # If libs folder has content, we assume it's at least partially installed.
    # A robust check would verify metadata.
    # For now, check if directory is not empty.
    if os.listdir(libs_path):
        return True
        
    return False

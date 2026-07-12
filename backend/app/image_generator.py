import os
import io
import gc
import time
import base64
import threading
from diffusers import AutoPipelineForText2Image

# Threading lock for generation concurrency
_sd_lock = threading.Lock()

class LocalImageGenerator:
    """
    Singleton manager for offline Stable Diffusion image generation.
    Optimized for CPU-based execution using SD-Turbo (1-step generation).
    Includes an automatic idle-unload timer to release RAM when inactive.
    """
    _instance = None
    _pipeline = None
    _unload_timer = None
    _last_active_time = 0.0
    _idle_timeout_seconds = 60.0  # Unload model after 60s of inactivity

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_pipeline(self):
        """
        Loads the Stable Diffusion pipeline into RAM.
        Runs under locks to guarantee singleton instantiation.
        """
        if self._pipeline is not None:
            return self._pipeline

        print("[*] Loading offline Stable Diffusion (SD-Turbo) into RAM...")
        start_time = time.time()
        
        # Load pipeline optimized for CPU (float32)
        # Using local cache by default. Diffusers will download weights on first run
        # and reuse them offline thereafter.
        self._pipeline = AutoPipelineForText2Image.from_pretrained(
            "stabilityai/sd-turbo",
            torch_dtype=None,  # Defaults to float32 on CPU
            safety_checker=None, # Disable checker to save RAM/weights
            low_cpu_mem_usage=True
        )
        
        # Disable progress bar to prevent terminal spam
        self._pipeline.set_progress_bar_config(disable=True)
        
        load_time = time.time() - start_time
        print(f"[+] Stable Diffusion model loaded in {load_time:.2f}s.")
        return self._pipeline

    def generate_image_base64(self, prompt: str) -> str:
        """
        Generates an image from a text prompt and returns the JPEG as a base64 string.
        """
        with _sd_lock:
            self._last_active_time = time.time()
            self._reset_unload_timer()

            # Ensure pipeline is loaded
            pipeline = self._load_pipeline()

            print(f"[*] Generating local image on CPU for prompt: '{prompt}'")
            start_time = time.time()
            
            # SD-Turbo is optimized for exactly 1 inference step and guidance_scale=0.0
            image_result = pipeline(
                prompt=prompt,
                num_inference_steps=1,
                guidance_scale=0.0
            ).images[0]

            gen_time = time.time() - start_time
            print(f"[+] Image generated successfully in {gen_time:.2f}s.")

            # Save PIL image to memory buffer as JPEG
            buffered = io.BytesIO()
            image_result.save(buffered, format="JPEG", quality=85)
            
            # Encode to base64 string
            img_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
            
            # Restart the idle countdown
            self._schedule_unload_timer()
            
            return img_base64

    def _schedule_unload_timer(self):
        """
        Starts a background timer to unload the model if it remains idle.
        """
        self._reset_unload_timer()
        self._unload_timer = threading.Timer(self._idle_timeout_seconds, self._unload_model)
        self._unload_timer.daemon = True
        self._unload_timer.start()

    def _reset_unload_timer(self):
        """
        Cancels any pending unload timers.
        """
        if self._unload_timer is not None:
            self._unload_timer.cancel()
            self._unload_timer = None

    def _unload_model(self):
        """
        Deletes the pipeline reference and runs python garbage collection
        to release the memory (RAM) footprint.
        """
        with _sd_lock:
            # Double check if someone used it in between
            if time.time() - self._last_active_time < self._idle_timeout_seconds:
                return

            if self._pipeline is not None:
                print("[*] Idle timeout reached. Unloading Stable Diffusion from RAM...")
                del self._pipeline
                self._pipeline = None
                
                # Force garbage collection
                gc.collect()
                print("[+] Stable Diffusion unloaded. RAM freed.")

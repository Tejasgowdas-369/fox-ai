import os
import time
import threading
from llama_cpp import Llama
from .config import MODEL_PATH, N_CTX, N_THREADS

class ModelManager:
    """
    Singleton class to manage the GGUF model instance.
    Guarantees the model is loaded exactly once (preventing reload bugs)
    and tracks loading duration.
    """
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._model = None
                cls._instance._load_time_ms = 0.0
                cls._instance._is_loading = False
                cls._instance._load_error = None
                cls._instance._resolved_model_path = MODEL_PATH
        return cls._instance

    def load_model(self):
        """
        Loads the GGUF model file into memory.
        Measures and prints startup time for console debugging.
        """
        with self._lock:
            if self._model is not None:
                return
            
            if self._is_loading:
                return

            self._is_loading = True
            self._load_error = None

            # Auto-detect existing GGUF model file if default is not found
            resolved_path = MODEL_PATH
            if not os.path.exists(resolved_path):
                models_dir = os.path.dirname(resolved_path)
                if os.path.exists(models_dir):
                    gguf_files = [f for f in os.listdir(models_dir) if f.endswith(".gguf")]
                    if gguf_files:
                        resolved_path = os.path.join(models_dir, gguf_files[0])
                        print(f"[*] Default model not found. Auto-detected GGUF model: {resolved_path}")

            if not os.path.exists(resolved_path):
                error_msg = f"No GGUF model files found in '{os.path.dirname(MODEL_PATH)}'. Please run download_model.py or drop a model in the models/ folder."
                self._load_error = error_msg
                self._is_loading = False
                print(f"[!] Error: {error_msg}")
                return

            self._resolved_model_path = resolved_path
            print(f"[*] Loading local LLM model from: {self._resolved_model_path}")
            print(f"[*] Configuration: context_window={N_CTX}, threads={N_THREADS}")
            
            start_time = time.time()
            try:
                # Load Llama model instance
                self._model = Llama(
                    model_path=self._resolved_model_path,
                    n_ctx=N_CTX,
                    n_threads=N_THREADS,
                    verbose=False  # Keeps stdout pollution to a minimum
                )
                self._load_time_ms = (time.time() - start_time) * 1000
                print(f"[+] Model loaded successfully in {self._load_time_ms:.2f}ms!")
            except Exception as e:
                self._load_error = str(e)
                print(f"[!] Critical error loading model: {e}")
            finally:
                self._is_loading = False

    @property
    def model(self) -> Llama:
        return self._model

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def load_time_ms(self) -> float:
        return self._load_time_ms

    @property
    def load_error(self) -> str:
        return self._load_error

    @property
    def model_name(self) -> str:
        return os.path.basename(self._resolved_model_path)

    @property
    def quantization(self) -> str:
        # Deduce quantization from filename for info display
        filename = self.model_name.upper()
        for term in ["Q4_K_M", "Q4_K_S", "Q4_0", "Q4_1", "Q5_K_M", "Q8_0", "Q2_K"]:
            if term in filename:
                return term
        if "Q4" in filename:
            return "Q4"
        return "Unknown"

    def tokenize(self, text: str) -> list:
        """
        Tokenizes text using the model's tokenizer.
        Used for counting prompt tokens.
        """
        if not self.is_loaded:
            return []
        try:
            return self._model.tokenize(text.encode("utf-8"))
        except Exception:
            return []

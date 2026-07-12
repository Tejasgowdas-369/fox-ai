import os
import sys
import urllib.request
from pathlib import Path

# Color codes for premium terminal formatting
GREEN = "\033[92m"
AMBER = "\033[93m"
CYAN = "\033[96m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"

# List of pre-selected lightweight models
MODELS = [
    {
        "name": "Qwen 2.5 1.5B Instruct (Q4_K_M)",
        "filename": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "url": "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "size": "1.13 GB",
        "ram": "2.0 GB",
        "desc": "Super lightweight, fast, excellent multi-lingual and coding support."
    },
    {
        "name": "Llama 3.2 3B Instruct (Q4_K_M)",
        "filename": "Llama-3.2-3B-Instruct-Q4_K_M.gguf",
        "url": "https://huggingface.co/lmstudio-community/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf",
        "size": "2.02 GB",
        "ram": "3.5 GB",
        "desc": "Meta's state-of-the-art small model. Superb general conversation and reasoning."
    },
    {
        "name": "Gemma 2 2B Instruct (Q4_K_M)",
        "filename": "gemma-2-2b-it-Q4_K_M.gguf",
        "url": "https://huggingface.co/lmstudio-community/gemma-2-2b-it-GGUF/resolve/main/gemma-2-2b-it-Q4_K_M.gguf",
        "size": "1.71 GB",
        "ram": "3.0 GB",
        "desc": "Google's optimized conversational model. High knowledge retention and reasoning."
    },
    {
        "name": "Phi 3 Mini 4K Instruct (Q4_K_M)",
        "filename": "Phi-3-mini-4k-instruct-q4.gguf",
        "url": "https://huggingface.co/microsoft/Phi-3-mini-4k-instruct-gguf/resolve/main/Phi-3-mini-4k-instruct-q4.gguf",
        "size": "2.20 GB",
        "ram": "4.0 GB",
        "desc": "Microsoft's highly capable logical-reasoning and math-oriented model."
    },
    {
        "name": "TinyLlama 1.1B Chat (Q4_K_M)",
        "filename": "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf",
        "url": "https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf",
        "size": "660 MB",
        "ram": "1.2 GB",
        "desc": "Ultra-lightweight. Best for older laptops, testing, and very low RAM machines."
    }
]

def show_progress(block_num, block_size, total_size):
    """
    Renders a live progress bar in the console.
    """
    downloaded = block_num * block_size
    percent = min(100, int(downloaded * 100 / total_size))
    
    # Calculate progress bar length
    bar_length = 40
    filled_length = int(bar_length * percent / 100)
    bar = "=" * filled_length + "-" * (bar_length - filled_length)
    
    # Calculate downloaded and total in Megabytes
    dl_mb = downloaded / (1024 * 1024)
    tot_mb = total_size / (1024 * 1024)
    
    sys.stdout.write(f"\r[{CYAN}{bar}{RESET}] {percent}% ({dl_mb:.1f}/{tot_mb:.1f} MB)")
    sys.stdout.flush()

def main():
    print(f"\n{BOLD}{AMBER}🦊 Fox AI — Local LLM Downloader Wizard{RESET}\n")
    print("Select a lightweight GGUF model to download directly onto your machine:")
    print("-" * 75)
    
    for i, model in enumerate(MODELS, 1):
        print(f"{BOLD}{i}. {model['name']}{RESET}")
        print(f"   Size: {CYAN}{model['size']}{RESET} | Recommended RAM: {GREEN}{model['ram']}{RESET}")
        print(f"   Description: {model['desc']}")
        print("-" * 75)
        
    try:
        choice = input(f"Select a model (1-{len(MODELS)}) or 'q' to quit: ").strip().lower()
        if choice == 'q':
            print("\nExiting installer. Goodbye!")
            return
            
        choice_idx = int(choice) - 1
        if choice_idx < 0 or choice_idx >= len(MODELS):
            raise ValueError()
    except (ValueError, IndexError):
        print(f"\n{RED}[!] Invalid choice. Please run the script again and choose a valid number.{RESET}")
        return

    selected_model = MODELS[choice_idx]
    
    # Destination directory setup
    models_dir = Path(__file__).resolve().parent / "models"
    models_dir.mkdir(exist_ok=True)
    dest_path = models_dir / selected_model["filename"]

    print(f"\n[*] Selected: {BOLD}{selected_model['name']}{RESET}")
    print(f"[*] Downloading GGUF to: {CYAN}{dest_path}{RESET}")
    
    if dest_path.exists():
        overwrite = input(f"{AMBER}[?] File already exists. Overwrite? (y/n): {RESET}").strip().lower()
        if overwrite != 'y':
            print("\nDownload cancelled. Using existing file.")
            return

    # Add custom User-Agent to bypass potential cloudflare blockages on Hugging Face resolver
    opener = urllib.request.build_opener()
    opener.addheaders = [('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')]
    urllib.request.install_opener(opener)

    print("\n[*] Starting download (this may take a few minutes depending on your internet)...")
    try:
        urllib.request.urlretrieve(
            selected_model["url"], 
            filename=str(dest_path), 
            reporthook=show_progress
        )
        print(f"\n\n{GREEN}[+] Success! Model downloaded and saved to /models folder.{RESET}")
        print(f"[*] Filename: {selected_model['filename']}")
        print(f"\n{BOLD}Now you can start your server using:{RESET}")
        print(f"{CYAN}python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000{RESET}\n")
    except Exception as e:
        print(f"\n\n{RED}[!] Download failed. Error: {e}{RESET}")
        if dest_path.exists():
            dest_path.unlink() # Delete partial file on error

if __name__ == "__main__":
    # Support color formatting on Windows command prompt
    os.system('color')
    main()

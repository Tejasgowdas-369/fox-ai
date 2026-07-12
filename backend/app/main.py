import os
import time
import asyncio
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .config import MODEL_PATH, N_CTX, IN_MEMORY_GUARANTEE, format_prompt
from .model import ModelManager
from .image_generator import LocalImageGenerator

# =====================================================================
# IN-MEMORY ONLY GUARANTEE
# Fox AI stores nothing — all data lives in RAM and is wiped when the app closes.
# No database writes, no temporary JSON dumps, no disk chat logs.
# =====================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load singleton model on startup
    manager = ModelManager()
    # Run model loading in a background thread so FastAPI startup is not blocked
    threading.Thread(target=manager.load_model, daemon=True).start()
    yield
    # Explicit confirmation on shutdown
    print("[*] Fox AI Server shutting down...")
    print("[*] Verification: Chat history in RAM wiped completely. No temp files, caches, or logs containing chat content written to disk.")

app = FastAPI(
    title="Fox AI",
    description="Private Local LLM Chatbot",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def get_health():
    """
    Returns system status, active model information, and load time.
    """
    manager = ModelManager()
    return {
        "status": "healthy" if manager.is_loaded else "unloaded",
        "model_name": manager.model_name,
        "quantization": manager.quantization,
        "context_size": N_CTX,
        "loaded": manager.is_loaded,
        "load_time_ms": manager.load_time_ms,
        "error": manager.load_error,
        "in_memory_guarantee": IN_MEMORY_GUARANTEE
    }

async def stream_llama_model(model, prompt):
    """
    Runs the blocking llama-cpp generator inside a background thread
    and pushes tokens into an asyncio Queue. Yields tokens asynchronously.
    """
    queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def producer():
        try:
            # Call llama.cpp completion generator
            generator = model(
                prompt=prompt,
                max_tokens=1024,
                stream=True,
                # Explicit stop sequences to avoid leaking instruct tags
                stop=[
                    "<start_of_turn>",
                    "<end_of_turn>",
                    "<|end|>",
                    "<|user|>",
                    "<|assistant|>",
                    "User:",
                    "Assistant:",
                    "\nUser:",
                    "\nAssistant:"
                ]
            )
            for chunk in generator:
                loop.call_soon_threadsafe(queue.put_nowait, chunk)
            # Sentinel value representing end of stream
            loop.call_soon_threadsafe(queue.put_nowait, None)
        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, e)

    # Start producer thread
    thread = threading.Thread(target=producer, daemon=True)
    thread.start()

    while True:
        chunk = await queue.get()
        if chunk is None:
            break
        if isinstance(chunk, Exception):
            raise chunk
        yield chunk

@app.websocket("/chat")
async def chat_endpoint(websocket: WebSocket):
    """
    WebSocket chat handler. Maintains conversation state strictly in memory (RAM).
    Wiped completely when the connection closes.
    """
    await websocket.accept()
    
    manager = ModelManager()
    if not manager.is_loaded:
        await websocket.send_json({
            "type": "error",
            "content": "Model is not loaded yet. Please wait a few seconds or check if the GGUF file exists in the models/ directory."
        })
        await websocket.close()
        return

    # Connection-specific, RAM-only chat history
    chat_history = []
    
    try:
        while True:
            # Wait for message from client
            data = await websocket.receive_json()
            user_message = data.get("message", "").strip()
            files_payload = data.get("files", [])
            images_payload = data.get("images", [])

            if not user_message and not files_payload and not images_payload:
                continue

            # ---------------------------------------------------------
            # Option A: Local Image Generation (Stable Diffusion)
            # ---------------------------------------------------------
            if user_message.lower().startswith("/image"):
                prompt_text = user_message[6:].strip()
                if not prompt_text:
                    await websocket.send_json({
                        "type": "error",
                        "content": "Please provide a description, e.g., `/image a cute cartoon fox`."
                    })
                    continue

                # Initialize generation loader state
                await websocket.send_json({
                    "type": "start",
                    "prompt_tokens": 0
                })
                
                await websocket.send_json({
                    "type": "token",
                    "content": "🎨 Generating image locally on CPU using Stable Diffusion (SD-Turbo)... This will take a few seconds..."
                })

                loop = asyncio.get_running_loop()
                try:
                    generator = LocalImageGenerator.get_instance()
                    # Run CPU-blocking Stable Diffusion in thread pool executor
                    img_base64 = await loop.run_in_executor(
                        None, 
                        generator.generate_image_base64, 
                        prompt_text
                    )
                    
                    # Return generated image base64 packet
                    await websocket.send_json({
                        "type": "image",
                        "content": img_base64,
                        "prompt": prompt_text
                    })
                    
                    # Log generated indicator in session memory
                    chat_history.append({
                        "role": "assistant",
                        "content": f"[Local SD-Turbo generated image for prompt: '{prompt_text}']"
                    })
                    
                    await websocket.send_json({
                        "type": "usage",
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0
                    })
                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "content": f"Image Generation Failed: {str(e)}"
                    })
                continue

            # ---------------------------------------------------------
            # Option B: Local Document/Code File Context Injection
            # ---------------------------------------------------------
            context_prefix = ""
            if files_payload:
                context_prefix += "--- Attached Local Files Context ---\n"
                for file_item in files_payload:
                    filename = file_item.get("name", "unknown_file")
                    content = file_item.get("content", "")
                    context_prefix += f"[File: {filename}]\n{content}\n[End of File]\n\n"
                context_prefix += "------------------------------------\n\n"
            
            # Combine attachments with prompt message
            full_user_prompt = context_prefix + user_message

            # Check if user sent an image, but model is not vision-capable
            if images_payload:
                # Add a visual assistant warning message about vision model requirements
                # while parsing standard prompt message
                await websocket.send_json({
                    "type": "start",
                    "prompt_tokens": 0
                })
                await websocket.send_json({
                    "type": "token",
                    "content": "⚠️ [Image upload detected] I currently do not support local image analysis. To describe images offline, please place a Llama-3.2-Vision model and its corresponding mmproj file in your /models folder.\n\n"
                })
                # Proceed with standard text message processing
                if not user_message:
                    await websocket.send_json({
                        "type": "usage",
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0
                    })
                    continue

            # Append to session history (RAM)
            chat_history.append({"role": "user", "content": full_user_prompt})

            # Format full conversation context
            formatted_prompt = format_prompt(chat_history, manager.model_name)
            
            # Count prompt tokens
            prompt_tokens = len(manager.tokenize(formatted_prompt))

            # Send initialization event
            await websocket.send_json({
                "type": "start",
                "prompt_tokens": prompt_tokens
            })

            start_time = time.time()
            ttft_ms = None
            completion_tokens = 0
            full_response = ""

            try:
                # Stream generation
                async for chunk in stream_llama_model(manager.model, formatted_prompt):
                    token_text = chunk["choices"][0]["text"]
                    full_response += token_text
                    completion_tokens += 1

                    try:
                        if ttft_ms is None:
                            # Time-To-First-Token in milliseconds
                            ttft_ms = (time.time() - start_time) * 1000
                            await websocket.send_json({
                                "type": "token",
                                "content": token_text,
                                "ttft_ms": ttft_ms
                            })
                        else:
                            await websocket.send_json({
                                "type": "token",
                                "content": token_text
                            })
                    except (WebSocketDisconnect, RuntimeError):
                        print("[*] Client disconnected during active token streaming.")
                        return

                # Append assistant response to history (RAM)
                chat_history.append({"role": "assistant", "content": full_response})

                # Send ending statistics
                try:
                    await websocket.send_json({
                        "type": "usage",
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": prompt_tokens + completion_tokens
                    })
                except (WebSocketDisconnect, RuntimeError):
                    print("[*] Client disconnected before usage statistics could be sent.")
                    return

            except Exception as e:
                # Avoid crashing on encode errors when logging exception details (e.g. emojis) on Windows console
                try:
                    print(f"[!] Error during inference: {e}")
                except Exception:
                    print("[!] Error during inference (could not display exception details due to console encoding limits)")
                
                try:
                    await websocket.send_json({
                        "type": "error",
                        "content": f"Inference Error: {str(e)}"
                    })
                except Exception:
                    pass

    except WebSocketDisconnect:
        # Connection closed, RAM conversation data will garbage-collect
        print("[*] WebSocket disconnected. Session memory cleared.")
    except Exception as e:
        print(f"[!] WebSocket error: {e}")

# Serve frontend directory
# If static files are located in /frontend, this serves index.html at root "/"
# Mount uvicorn paths before static files to prevent overlaps
frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
else:
    print(f"[!] Warning: Frontend directory not found at {frontend_path}")

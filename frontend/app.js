/* =====================================================================
   FOX AI - FRONTEND APPLICATION JAVASCRIPT CONTROLLER
   ===================================================================== */

document.addEventListener("DOMContentLoaded", () => {
  // DOM Elements
  const chatForm = document.getElementById("chat-form");
  const userInput = document.getElementById("user-input");
  const sendBtn = document.getElementById("send-btn");
  const clearBtn = document.getElementById("clear-btn");
  
  const attachBtn = document.getElementById("attach-btn");
  const fileInput = document.getElementById("file-attachment-input");
  const previewContainer = document.getElementById("attachment-preview-container");
  
  const chatHistory = document.getElementById("chat-history");
  const welcomeMessage = document.getElementById("welcome-message");
  const thinkingIndicator = document.getElementById("thinking-indicator");
  
  const activeModelName = document.getElementById("active-model-name");
  const connectionStatus = document.getElementById("connection-status");
  const statusDot = connectionStatus.querySelector(".status-dot");
  const statusLabel = connectionStatus.querySelector(".status-label");
  
  const statLatency = document.getElementById("stat-latency");
  const statPromptTokens = document.getElementById("stat-prompt-tokens");
  const statGenTokens = document.getElementById("stat-gen-tokens");
  const statTotalTokens = document.getElementById("stat-total-tokens");
  
  const errorModal = document.getElementById("error-modal");
  const modalTitle = document.getElementById("modal-title");
  const modalContent = document.getElementById("modal-content");

  // Application State
  let ws = null;
  let isGenerating = false;
  let currentAssistantBubble = null;
  let currentAssistantText = "";
  let attachedFiles = [];
  
  // Set host coordinates dynamically
  const HTTP_API_URL = `${window.location.protocol}//${window.location.host}`;
  const WS_API_URL = `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/chat`;

  // Start Health Check Polling
  checkServerHealth();

  /**
   * Safe HTML Escaping & Markdown Parser
   * Renders code blocks (```...```) and inline code (`...`) cleanly.
   */
  function parseContent(text) {
    // Escape HTML to prevent cross-site scripting
    let html = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

    // Convert code blocks: ```code```
    html = html.replace(/```(?:[a-zA-Z0-9]+)?\n([\s\S]*?)```/g, (_, code) => {
      return `<pre><code>${code.trim()}</code></pre>`;
    });

    // Convert inline code: `code`
    html = html.replace(/`([^`\n]+)`/g, '<code>$1</code>');

    return html;
  }

  /**
   * Checks the FastAPI backend health and model loading progress.
   */
  async function checkServerHealth() {
    updateStatusIndicator("loading", "Checking server...");
    
    try {
      const response = await fetch(`${HTTP_API_URL}/api/health`);
      if (!response.ok) throw new Error("Server health endpoint returned error status.");
      
      const healthData = await response.json();
      
      if (healthData.status === "healthy" && healthData.loaded) {
        // Model loaded successfully
        activeModelName.textContent = healthData.model_name;
        updateStatusIndicator("connected", "Online (RAM)");
        hideErrorModal();
        initializeWebSocket();
      } else if (healthData.status === "unloaded" && !healthData.loaded) {
        // Server is up but model is still loading
        updateStatusIndicator("loading", "Loading GGUF model...");
        activeModelName.textContent = healthData.model_name || "Gemma 2 2B";
        
        // Show loading progress notice
        showErrorModal(
          "Initializing Local LLM Model",
          `<p>The FastAPI server is online and currently loading <strong>${healthData.model_name}</strong> into system memory (RAM).</p>
           <p class="tip">This typically takes 5-15 seconds depending on your SSD and RAM speed. Please wait...</p>`
        );
        
        // Poll again shortly
        setTimeout(checkServerHealth, 2000);
      } else {
        // Unknown status or load error
        const errMsg = healthData.error || "Unknown load error";
        showErrorModal(
          "Model Load Failed",
          `<p>Failed to load the model GGUF file: <code>${healthData.model_name}</code></p>
           <p class="tip">Error details: ${errMsg}</p>`
        );
        updateStatusIndicator("disconnected", "Load Error");
      }
    } catch (error) {
      console.error("[!] Health check failed:", error);
      updateStatusIndicator("disconnected", "Offline");
      showErrorModal(
        "Connection Offline",
        `<p>Could not connect to the local Fox AI backend at <code>${HTTP_API_URL}</code>.</p>
         <p class="tip">Please verify that you have started the server command:<br><code>python -m uvicorn backend.app.main:app</code></p>`
      );
      // Retry in 5 seconds
      setTimeout(checkServerHealth, 5000);
    }
  }

  /**
   * Updates the UI status pill
   */
  function updateStatusIndicator(state, text) {
    statusDot.className = "status-dot";
    statusDot.classList.add(state);
    statusLabel.textContent = text;
  }

  /**
   * Modal control functions
   */
  function showErrorModal(title, htmlContent) {
    modalTitle.textContent = title;
    modalContent.innerHTML = htmlContent;
    errorModal.style.display = "flex";
    userInput.disabled = true;
    sendBtn.disabled = true;
  }

  function hideErrorModal() {
    errorModal.style.display = "none";
  }

  /**
   * Initializes the WebSocket Connection
   */
  function initializeWebSocket() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      return; // Already active
    }

    console.log(`[*] Connecting to WebSocket: ${WS_API_URL}`);
    ws = new WebSocket(WS_API_URL);

    ws.onopen = () => {
      console.log("[+] WebSocket connected!");
      updateStatusIndicator("connected", "Online (RAM)");
      userInput.disabled = false;
      sendBtn.disabled = false;
      userInput.focus();
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case "start":
          // Hide thinking state
          thinkingIndicator.style.display = "none";
          
          // Set prompt token count stats
          statPromptTokens.textContent = data.prompt_tokens;
          
          // Create assistant bubble placeholder
          appendMessageBubble("assistant", "");
          break;

        case "token":
          // Accumulate and render token text
          currentAssistantText += data.content;
          currentAssistantBubble.innerHTML = parseContent(currentAssistantText);
          scrollToBottom();

          // Display TTFT latency if sent on the first token
          if (data.ttft_ms !== undefined) {
            statLatency.textContent = `${Math.round(data.ttft_ms)}ms`;
          }
          break;

        case "usage":
          // Render ending generation metrics
          statPromptTokens.textContent = data.prompt_tokens;
          statGenTokens.textContent = data.completion_tokens;
          statTotalTokens.textContent = data.total_tokens;
          
          // Unlock text input form
          setGeneratingState(false);
          break;

        case "image":
          // Hide thinking state
          thinkingIndicator.style.display = "none";
          
          // Create assistant bubble containing the generated image
          const imageRow = document.createElement("div");
          imageRow.className = `chat-row assistant`;

          const imageBubble = document.createElement("div");
          imageBubble.className = "message-bubble";
          
          const imageLabel = document.createElement("p");
          imageLabel.innerHTML = `🎨 Generated image for: <em>"${data.prompt}"</em>`;
          
          const imgEl = document.createElement("img");
          imgEl.src = `data:image/jpeg;base64,${data.content}`;
          imgEl.className = "chat-image-attachment";
          imgEl.alt = data.prompt;
          
          imageBubble.appendChild(imageLabel);
          imageBubble.appendChild(imgEl);
          imageRow.appendChild(imageBubble);
          chatHistory.appendChild(imageRow);
          scrollToBottom();

          // Unlock text input form
          setGeneratingState(false);
          break;

        case "error":
          thinkingIndicator.style.display = "none";
          appendMessageBubble("assistant", `⚠️ Error: ${data.content}`);
          setGeneratingState(false);
          break;
      }
    };

    ws.onclose = (event) => {
      console.log("[!] WebSocket closed:", event.reason);
      updateStatusIndicator("disconnected", "Offline");
      setGeneratingState(false);
      userInput.disabled = true;
      sendBtn.disabled = true;
      
      // Auto-reconnect if not intentionally wiped
      if (event.code !== 1000) {
        setTimeout(checkServerHealth, 3000);
      }
    };

    ws.onerror = (error) => {
      console.error("[!] WebSocket error:", error);
      ws.close();
    };
  }

  /**
   * Appends a message bubble (user or assistant) to the chat viewport.
   */
  function appendMessageBubble(role, text) {
    // Hide welcome message on first activity
    if (welcomeMessage.style.display !== "none") {
      welcomeMessage.style.display = "none";
    }

    const row = document.createElement("div");
    row.className = `chat-row ${role}`;

    const bubble = document.createElement("div");
    bubble.className = "message-bubble";
    bubble.innerHTML = parseContent(text);
    
    row.appendChild(bubble);
    chatHistory.appendChild(row);
    scrollToBottom();

    if (role === "assistant") {
      currentAssistantBubble = bubble;
      currentAssistantText = text;
    }
  }

  /**
   * Appends a message bubble with custom raw HTML (for files visualization).
   */
  function appendMessageBubbleCustom(role, htmlContent) {
    if (welcomeMessage.style.display !== "none") {
      welcomeMessage.style.display = "none";
    }

    const row = document.createElement("div");
    row.className = `chat-row ${role}`;

    const bubble = document.createElement("div");
    bubble.className = "message-bubble";
    bubble.innerHTML = htmlContent;
    
    row.appendChild(bubble);
    chatHistory.appendChild(row);
    scrollToBottom();

    if (role === "assistant") {
      currentAssistantBubble = bubble;
      currentAssistantText = "";
    }
  }

  /**
   * Adjusts UI states based on generation activities.
   */
  function setGeneratingState(generating) {
    isGenerating = generating;
    userInput.disabled = generating;
    sendBtn.disabled = generating;
    
    if (generating) {
      thinkingIndicator.style.display = "flex";
      scrollToBottom();
    } else {
      thinkingIndicator.style.display = "none";
      userInput.focus();
    }
  }

  /**
   * Automatically scrolls chat history viewport to the bottom.
   */
  function scrollToBottom() {
    chatHistory.scrollTop = chatHistory.scrollHeight;
  }

  // Handle Form Submission
  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    if (isGenerating) return;

    const message = userInput.value.trim();
    if (!message && attachedFiles.length === 0) return;

    // Render attachments visualization inside the user's bubble
    let userBubbleHTML = "";
    if (message) {
      userBubbleHTML += `<p>${parseContent(message)}</p>`;
    }
    
    if (attachedFiles.length > 0) {
      userBubbleHTML += `<div style="display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.5rem;">`;
      attachedFiles.forEach(file => {
        const icon = file.type === "image" ? "🖼️" : "📄";
        userBubbleHTML += `
          <div class="attachment-pill type-${file.type}" style="animation: none; margin: 0; background: rgba(255,255,255,0.08);">
            <span>${icon}</span>
            <span>${file.name}</span>
          </div>
        `;
      });
      userBubbleHTML += `</div>`;
    }

    // Append custom user message bubble
    appendMessageBubbleCustom("user", userBubbleHTML);
    
    // Construct JSON payload
    const payload = {
      message: message,
      files: [],
      images: []
    };

    attachedFiles.forEach(file => {
      if (file.type === "image") {
        // Strip header prefix data:image/...;base64,
        const base64Data = file.rawData.split(",")[1] || file.rawData;
        payload.images.push(base64Data);
      } else {
        payload.files.push({
          name: file.name,
          content: file.rawData
        });
      }
    });

    // Reset inputs and state
    userInput.value = "";
    userInput.style.height = "auto";
    attachedFiles = [];
    renderAttachmentPills();

    // Set generating state
    setGeneratingState(true);

    // Send payload to WebSocket
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload));
    } else {
      appendMessageBubble("assistant", "⚠️ Error: WebSocket connection is offline.");
      setGeneratingState(false);
    }
  });

  // Wipe RAM / Reset Conversation
  clearBtn.addEventListener("click", () => {
    if (confirm("Are you sure you want to wipe the active session? This clears the backend RAM conversation log completely.")) {
      // Close existing socket intentionally (clearing backend conversation cache in RAM)
      if (ws) {
        ws.close(1000, "RAM session wipe requested");
      }

      // Reset statistics UI
      statLatency.textContent = "—";
      statPromptTokens.textContent = "0";
      statGenTokens.textContent = "0";
      statTotalTokens.textContent = "0";

      // Reset chat view
      chatHistory.innerHTML = "";
      welcomeMessage.style.display = "flex";
      
      // Re-establish WebSocket connection (starts fresh session context)
      setTimeout(initializeWebSocket, 500);
    }
  });

  // Auto-resize textarea input height
  userInput.addEventListener("input", function() {
    this.style.height = "auto";
    this.style.height = (this.scrollHeight - 4) + "px";
  });

  // Support Enter key submission, Shift+Enter for newline
  userInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      chatForm.dispatchEvent(new Event("submit"));
    }
  });

  /* =====================================================================
     Attachment Handling & File Reader Implementations
     ===================================================================== */

  // Trigger file dialog
  attachBtn.addEventListener("click", () => {
    if (isGenerating) return;
    fileInput.click();
  });

  // Handle files input changes
  fileInput.addEventListener("change", (e) => {
    const files = Array.from(e.target.files);
    
    if (attachedFiles.length + files.length > 5) {
      alert("You can attach a maximum of 5 files.");
      fileInput.value = "";
      return;
    }

    files.forEach(file => {
      // 10MB validation limit
      if (file.size > 10 * 1024 * 1024) {
        alert(`File "${file.name}" exceeds the 10MB size limit.`);
        return;
      }

      const fileType = file.type.startsWith("image/") ? "image" : "file";
      const reader = new FileReader();

      reader.onload = (event) => {
        attachedFiles.push({
          name: file.name,
          size: file.size,
          type: fileType,
          rawData: event.target.result
        });
        renderAttachmentPills();
      };

      // Always read as Data URL (base64) so we can transmit all files (including binary files like PDF) safely
      reader.readAsDataURL(file);
    });

    fileInput.value = ""; // Clear file picker value
  });

  // Render attachment pills in preview panel
  function renderAttachmentPills() {
    if (attachedFiles.length === 0) {
      previewContainer.innerHTML = "";
      previewContainer.style.display = "none";
      return;
    }

    previewContainer.innerHTML = "";
    previewContainer.style.display = "flex";

    attachedFiles.forEach((file, index) => {
      const pill = document.createElement("div");
      pill.className = `attachment-pill type-${file.type}`;
      
      const icon = file.type === "image" ? "🖼️" : "📄";
      const sizeKB = Math.round(file.size / 1024);
      
      pill.innerHTML = `
        <span class="pill-icon">${icon}</span>
        <span class="pill-name" title="${file.name}">${truncateString(file.name, 18)} (${sizeKB}KB)</span>
        <span class="pill-remove" data-index="${index}">✕</span>
      `;
      
      previewContainer.appendChild(pill);
    });

    // Wire up delete controls on attachment pills
    previewContainer.querySelectorAll(".pill-remove").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const index = parseInt(e.target.getAttribute("data-index"));
        attachedFiles.splice(index, 1);
        renderAttachmentPills();
      });
    });
  }

  function truncateString(str, num) {
    if (str.length <= num) return str;
    return str.slice(0, num) + "...";
  }
});

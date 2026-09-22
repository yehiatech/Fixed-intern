document.addEventListener("DOMContentLoaded", () => {
    const chatFab = document.getElementById("chat-fab");
    const chatWindow = document.getElementById("chat-window");
    const closeChatBtn = document.getElementById("close-chat");
    const sendBtn = document.getElementById("send-btn");
    const chatInput = document.getElementById("chat-input");
    const chatMessages = document.getElementById("chat-messages");
    const loadingIndicator = document.getElementById("loading-indicator");

    // Toggle Chat Window
    chatFab.addEventListener("click", () => {
        chatWindow.classList.toggle("hidden");
    });

    closeChatBtn.addEventListener("click", () => {
        chatWindow.classList.add("hidden");
    });

    // Handle Sending Messages
    const sendMessage = async () => {
        const text = chatInput.value.trim();
        if (!text) return;

        // 1. Append User Message
        appendMessage("user", text);
        chatInput.value = "";
        
        // 2. Show Loading
        loadingIndicator.classList.remove("hidden");
        scrollToBottom();

        // 3. Make Real API Call to Backend
        try {
            const response = await fetch("http://localhost:8002/chat", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    organization_id: "00000000-0000-0000-0000-000000000000",
                    query: text
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            // Backend returns { answer: "ai text..." } based on chat.py
            const aiText = data.answer || data.response || data.message || data.text || "No response received";
            
            loadingIndicator.classList.add("hidden");
            appendMessage("ai", aiText);
        } catch (error) {
            console.error("Chat API error:", error);
            loadingIndicator.classList.add("hidden");
            appendMessage("ai", "Sorry, an error occurred while connecting to the server."); 
        }
    };

    // Send on Button Click
    sendBtn.addEventListener("click", sendMessage);

    // Send on Enter Key
    chatInput.addEventListener("keypress", (e) => {
        if (e.key === "Enter") {
            sendMessage();
        }
    });

    // Helper: Append Message to UI
    function appendMessage(sender, text) {
        const messageDiv = document.createElement("div");
        messageDiv.classList.add("message", `${sender}-message`);

        const bubble = document.createElement("div");
        bubble.classList.add("bubble");
        bubble.textContent = text;

        messageDiv.appendChild(bubble);
        chatMessages.appendChild(messageDiv);
        
        scrollToBottom();
    }

    // Helper: Scroll to the latest message
    function scrollToBottom() {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
});

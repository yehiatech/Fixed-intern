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
            // Backend returns { answer: "ai text...", interaction_id: "..." } based on chat.py
            const aiText = data.answer || data.response || data.message || data.text || "No response received";
            const interactionId = data.interaction_id || null;
            
            loadingIndicator.classList.add("hidden");
            appendMessage("ai", aiText, interactionId);
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
    function appendMessage(sender, text, interactionId = null) {
        const messageDiv = document.createElement("div");
        messageDiv.classList.add("message", `${sender}-message`);

        const bubble = document.createElement("div");
        bubble.classList.add("bubble");
        bubble.textContent = text;
        messageDiv.appendChild(bubble);

        // Add feedback buttons for AI messages with an interaction ID
        if (sender === "ai" && interactionId) {
            const feedbackContainer = document.createElement("div");
            feedbackContainer.classList.add("feedback-container");

            const upBtn = document.createElement("button");
            upBtn.classList.add("feedback-btn");
            upBtn.innerHTML = "👍";
            upBtn.onclick = () => sendFeedback(interactionId, "up", upBtn, downBtn);

            const downBtn = document.createElement("button");
            downBtn.classList.add("feedback-btn");
            downBtn.innerHTML = "👎";
            downBtn.onclick = () => sendFeedback(interactionId, "down", downBtn, upBtn);

            feedbackContainer.appendChild(upBtn);
            feedbackContainer.appendChild(downBtn);
            messageDiv.appendChild(feedbackContainer);
        }

        chatMessages.appendChild(messageDiv);
        scrollToBottom();
    }

    async function sendFeedback(interactionId, rating, clickedBtn, otherBtn) {
        if (clickedBtn.classList.contains("selected") || otherBtn.classList.contains("selected")) return; // already submitted

        try {
            const response = await fetch("http://localhost:8002/feedback", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    interaction_id: interactionId,
                    rating: rating
                })
            });

            if (response.ok) {
                clickedBtn.classList.add("selected");
                clickedBtn.style.opacity = "1";
                otherBtn.style.opacity = "0.3";
                clickedBtn.style.cursor = "default";
                otherBtn.style.cursor = "default";
            }
        } catch (error) {
            console.error("Feedback error:", error);
        }
    }

    // Helper: Scroll to the latest message
    function scrollToBottom() {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
});

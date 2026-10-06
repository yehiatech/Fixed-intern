document.addEventListener("DOMContentLoaded", () => {
    // Which organization this widget belongs to. Tickets the chatbot opens are saved under it.
    // Embed with:  index.html?org_id=<organization uuid>   (or set window.CHAT_ORG_ID before this script).
    const NO_ORG = "00000000-0000-0000-0000-000000000000";
    const ORG_ID = new URLSearchParams(window.location.search).get("org_id") || window.CHAT_ORG_ID || NO_ORG;
    if (ORG_ID === NO_ORG) {
        console.warn("Chat widget: no org_id provided - the chatbot cannot save tickets. Use ?org_id=<uuid>.");
    }
    // Conversation memory, so the bot can collect name / phone / issue over several messages.
    const chatHistory = [];

    const chatFab = document.getElementById("chat-fab");
    const chatWindow = document.getElementById("chat-window");
    const closeChatBtn = document.getElementById("close-chat");
    const sendBtn = document.getElementById("send-btn");
    const chatInput = document.getElementById("chat-input");
    const chatMessages = document.getElementById("chat-messages");
    const loadingIndicator = document.getElementById("loading-indicator");
    const loadingEta = document.getElementById("loading-eta");

    // ---- Persona picker: the chat user chooses how the assistant talks.
    // Empty value = the organization's own persona (the previous behaviour).
    const personaSelect = document.getElementById("persona-select");
    const PERSONA_KEY = "chat_persona_" + ORG_ID;
    const PERSONA_LABELS = { "default": "ودود ومحترف", "formal": "رسمي", "concise": "مختصر", "enthusiastic": "حماسي" };
    const getPersonaId = () => (personaSelect && personaSelect.value) || null;

    async function loadPersonas() {
        if (!personaSelect) return;
        try {
            const res = await fetch("http://localhost:8002/chat/personas?organization_id=" + encodeURIComponent(ORG_ID));
            if (!res.ok) return;
            const data = await res.json();
            const list = data.personas || [];
            if (!list.length) return;               // nothing to choose -> keep the selector hidden
            personaSelect.innerHTML = "";
            const def = document.createElement("option");
            def.value = "";
            def.textContent = "الأسلوب الافتراضي";
            personaSelect.appendChild(def);
            list.forEach(p => {
                const opt = document.createElement("option");
                opt.value = p.id;
                opt.textContent = p.is_custom ? (p.name || "مخصص") : (PERSONA_LABELS[p.key] || p.name);
                if (p.description) opt.title = p.description;
                personaSelect.appendChild(opt);
            });
            let saved = null;
            try { saved = localStorage.getItem(PERSONA_KEY); } catch (_) {}
            if (saved && list.some(p => p.id === saved)) personaSelect.value = saved;
            personaSelect.style.display = "";
            personaSelect.addEventListener("change", () => {
                try { localStorage.setItem(PERSONA_KEY, personaSelect.value); } catch (_) {}
            });
        } catch (e) {
            console.warn("Personas unavailable:", e);   // chat keeps working with the default persona
        }
    }
    loadPersonas();

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
        
        // 2. Show Loading. For anything but small talk, ask the backend how
        //    complex the message is and show the expected wait while /chat runs.
        let chatDone = false;
        if (loadingEta) loadingEta.textContent = "";
        loadingIndicator.classList.remove("hidden");
        scrollToBottom();
        fetch("http://localhost:8002/chat/estimate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ organization_id: ORG_ID, query: text, history: [...chatHistory] })
        })
            .then(r => (r.ok ? r.json() : null))
            .then(est => {
                if (est && est.eta_label && !chatDone && loadingEta) loadingEta.textContent = est.eta_label;
            })
            .catch(() => {});   // the estimate is a nice-to-have, never block the chat on it

        // 3. Make Real API Call to Backend
        try {
            const response = await fetch("http://localhost:8002/chat", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    organization_id: ORG_ID,
                    query: text,
                    persona_id: getPersonaId(),
                    history: [...chatHistory]
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            // Backend returns { answer: "ai text...", interaction_id: "..." } based on chat.py
            const aiText = data.answer || data.response || data.message || data.text || "No response received";
            const interactionId = data.interaction_id || null;
            
            chatDone = true;
            loadingIndicator.classList.add("hidden");
            appendMessage("ai", aiText, interactionId);
            chatHistory.push({ role: "user", content: [{ text: text }] });
            chatHistory.push({ role: "assistant", content: [{ text: aiText }] });
        } catch (error) {
            console.error("Chat API error:", error);
            chatDone = true;
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

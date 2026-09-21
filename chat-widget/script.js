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

        // 3. Fake API Call Delay (Mocking the POST /chat endpoint)
        await new Promise(resolve => setTimeout(resolve, 1500));

        // 4. Fake AI Response
        const fakeResponses = [
            "لقد بحثت في قاعدة المعرفة، سياسة الإجازات تسمح بـ 21 يوم سنوياً.",
            "هل يمكنك توضيح سؤالك أكثر؟",
            "بناءً على دليل الموظف، يرجى التواصل مع قسم الموارد البشرية للحصول على النموذج.",
            "تم تسجيل طلبك بنجاح، هل هناك أي شيء آخر يمكنني مساعدتك به؟"
        ];
        const randomResponse = fakeResponses[Math.floor(Math.random() * fakeResponses.length)];
        
        loadingIndicator.classList.add("hidden");
        appendMessage("ai", randomResponse);
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

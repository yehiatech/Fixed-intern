// RAG Chatbot Shared Component
function initChatbot(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    container.innerHTML = `<!-- Chat Header (RTL for Arabic Chatbot) -->
            <div class="bg-[#177a94] p-4 text-white flex items-center justify-between shadow-md z-10" dir="rtl">
                <div class="flex items-center gap-3">
                    <div class="bg-white bg-opacity-20 p-2 rounded-full">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"></path></svg>
                    </div>
                    <div>
                        <h2 class="font-bold leading-tight">المساعد الذكي</h2>
                        <p class="text-[10px] text-blue-100 uppercase tracking-wider">متصل الآن</p>
                    </div>
                </div>
                <span class="flex h-3 w-3 relative">
                    <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                    <span class="relative inline-flex rounded-full h-3 w-3 bg-green-500 border-2 border-white"></span>
                </span>
            </div>
            
            <!-- Chat Messages Area (RTL) -->
            <div id="chatBox" class="flex-1 p-4 overflow-y-auto chat-scroll bg-[#f5f6f8] flex flex-col gap-4" dir="rtl">
                
                <!-- AI Message Initial -->
                <div class="flex flex-col items-start w-full">
                    <span class="text-xs text-gray-500 mb-1 mr-1">المساعد الذكي</span>
                    <div class="bg-white border border-gray-200 px-4 py-2.5 rounded-2xl rounded-tr-sm shadow-sm text-sm text-gray-800 max-w-[85%] leading-relaxed">
                        مرحباً! أنا المساعد الذكي الخاص بك. كيف يمكنني مساعدتك في استفساراتك اليوم؟
                    </div>
                </div>

            </div>

            <!-- Loading Indicator -->
            <div id="loadingIndicator" class="hidden flex gap-1 p-4 justify-center items-center bg-[#f5f6f8]" dir="rtl">
                <div class="w-2 h-2 bg-[#177a94] rounded-full animate-bounce"></div>
                <div class="w-2 h-2 bg-[#177a94] rounded-full animate-bounce" style="animation-delay: 0.2s"></div>
                <div class="w-2 h-2 bg-[#177a94] rounded-full animate-bounce" style="animation-delay: 0.4s"></div>
            </div>

            <!-- Chat Input Area (RTL) -->
            <div class="p-3 bg-white border-t border-gray-200" dir="rtl">
                <form id="chatForm" class="flex gap-2 relative items-center">
                    
                    <!-- File Upload -->
                    <input type="file" id="pdfUploadInput" accept=".pdf" class="hidden">
                    <button type="button" id="uploadBtn" class="text-gray-400 hover:text-[#177a94] transition-colors p-2" title="رفع ملف PDF">
                        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"></path></svg>
                    </button>
                    <button type="button" id="micBtn" class="text-gray-400 hover:text-red-500 transition-colors p-2" title="تحدث">
                        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"></path></svg>
                    </button>

                    <input type="text" id="chatInput" class="flex-1 pr-4 pl-12 py-3 bg-gray-50 border border-gray-300 rounded-full focus:outline-none focus:border-[#177a94] focus:ring-1 focus:ring-[#177a94] text-sm text-right" placeholder="اكتب رسالتك هنا..." required autocomplete="off">
                    <button type="submit" id="sendBtn" class="absolute left-1 top-1 bottom-1 aspect-square bg-[#177a94] text-white rounded-full hover:bg-[#126379] transition-colors flex items-center justify-center">
                        <svg class="w-4 h-4 mr-0.5 transform rotate-180" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"></path></svg>
                    </button>
                </form>
            </div>`;

    const SESSION = (typeof requireSession === 'function') ? requireSession() : null;
    if (!SESSION) {
        container.innerHTML = '<div class="p-4 text-red-500">Session missing. Please log in.</div>';
        return;
    }
    
// --- Real Backend Chatbot Logic ---
            const chatForm = document.getElementById('chatForm');
            const chatInput = document.getElementById('chatInput');
            const chatBox = document.getElementById('chatBox');
            const loadingIndicator = document.getElementById('loadingIndicator');

            // -- File Upload Logic --
            const pdfUploadInput = document.getElementById('pdfUploadInput');
            const uploadBtn = document.getElementById('uploadBtn');

            uploadBtn.addEventListener('click', () => {
                pdfUploadInput.click();
            });

            pdfUploadInput.addEventListener('change', async (e) => {
                const file = e.target.files[0];
                if (!file) return;
                
                if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
                    alert('يرجى اختيار ملف PDF فقط.');
                    return;
                }

                // Show processing message
                appendMessage('user', `📄 جاري رفع الملف: ${file.name}...`);
                loadingIndicator.classList.remove("hidden");
                chatBox.scrollTop = chatBox.scrollHeight;

                const formData = new FormData();
                formData.append("file", file);
                formData.append("organization_id", SESSION.organization_id);

                try {
                    const response = await fetch("http://localhost:8002/upload", {
                        method: "POST",
                        body: formData
                    });

                    if (!response.ok) throw new Error("Upload failed");
                    
                    const data = await response.json();
                    loadingIndicator.classList.add("hidden");
                    const sT = 'تم رفع الملف بنجاح! يمكنك الآن سؤالي عن محتواه.'; appendMessage('ai', '✅ ' + sT); playTTS(sT);
                } catch(error) {
                    console.error("Upload Error:", error);
                    loadingIndicator.classList.add("hidden");
                    const eT = 'عذراً، فشل رفع الملف.'; appendMessage('ai', '❌ ' + eT); playTTS(eT);
                }
                
                pdfUploadInput.value = '';
            });

            
            // --- STT (Speech-To-Text) Logic ---
            const micBtn = document.getElementById('micBtn');
            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            let recognition;
            
            if (SpeechRecognition) {
                recognition = new SpeechRecognition();
                recognition.lang = 'ar-EG'; 
                recognition.continuous = true;
                recognition.interimResults = true;

                let isListening = false;
                let fullTranscript = '';

                
                recognition.onstart = () => {
                    console.log("STT: Microphone started listening");
                    isListening = true;
                    fullTranscript = '';
                    if (micBtn) {
                        micBtn.classList.remove('text-gray-400');
                        micBtn.classList.add('text-red-500', 'animate-pulse');
                    }
                    const sendBtn = document.getElementById('sendBtn');
                    if (sendBtn) {
                        sendBtn.disabled = true;
                        sendBtn.classList.add('opacity-50', 'cursor-not-allowed');
                    }
                    chatInput.placeholder = "جاري الاستماع...";
                };

                recognition.onresult = (event) => {
                    let finalT = '';
                    let interimT = '';
                    
                    for (let i = event.resultIndex; i < event.results.length; ++i) {
                        if (event.results[i].isFinal) {
                            finalT += event.results[i][0].transcript;
                        } else {
                            interimT += event.results[i][0].transcript;
                        }
                    }
                    
                    fullTranscript += finalT;
                    chatInput.value = fullTranscript + interimT;
                };

                recognition.onerror = (event) => {
                    console.error("STT Error:", event.error);
                    isListening = false;
                    chatInput.placeholder = "حدث خطأ: " + event.error;
                    setTimeout(() => { chatInput.placeholder = "اكتب رسالتك هنا..."; }, 3000);
                };

                recognition.onend = () => {
                    console.log("STT: Microphone stopped listening");
                    isListening = false;
                    if (micBtn) {
                        micBtn.classList.add('text-gray-400');
                        micBtn.classList.remove('text-red-500', 'animate-pulse');
                    }
                    
                    if (fullTranscript.trim().length > 0) {
                        chatInput.placeholder = "جاري تنقيح النص الذكي...";
                        
                        // Disable input and send button during cleanup
                        chatInput.disabled = true;
                        const sendBtn = document.getElementById('sendBtn');
                        if (sendBtn) {
                            sendBtn.disabled = true;
                            sendBtn.classList.add('opacity-50', 'cursor-not-allowed');
                        }

                        // Extract context
                        let lastAiMsg = '';
                        if (typeof chatHistory !== 'undefined' && chatHistory.length > 0) {
                            const aiMsgs = chatHistory.filter(m => m.sender === 'ai');
                            if (aiMsgs.length > 0) {
                                lastAiMsg = aiMsgs[aiMsgs.length - 1].text;
                            }
                        }
                        
                        fetch("http://localhost:8002/cleanup-stt", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ text: fullTranscript, context: lastAiMsg })
                        })
                        .then(res => res.json())
                        .then(data => {
                            chatInput.value = data.cleaned_text || fullTranscript;
                            chatInput.placeholder = "اكتب رسالتك هنا...";
                        })
                        .catch(err => {
                            console.error("STT Cleanup failed", err);
                            chatInput.placeholder = "اكتب رسالتك هنا...";
                        })
                        .finally(() => {
                            // Re-enable input and send button
                            chatInput.disabled = false;
                            if (sendBtn) {
                                sendBtn.disabled = false;
                                sendBtn.classList.remove('opacity-50', 'cursor-not-allowed');
                            }
                            chatInput.focus();
                        });
                    } else {
                        chatInput.placeholder = "اكتب رسالتك هنا...";
                        chatInput.disabled = false;
                        const sendBtn = document.getElementById('sendBtn');
                        if (sendBtn) {
                            sendBtn.disabled = false;
                            sendBtn.classList.remove('opacity-50', 'cursor-not-allowed');
                        }
                    }
                };

                if (micBtn) {
                    micBtn.addEventListener('click', (e) => {
                        e.preventDefault();
                        if (isListening) {
                            recognition.stop();
                            return;
                        }
                        try {
                            recognition.start();
                        } catch(err) {}
                    });
                }
            }



            // --- TTS (Text-To-Speech) Logic using AWS Polly Backend ---
            let currentAudio = null;
            let currentSpeakerBtn = null;

            async function playTTS(text, btnElement) {
                // If something is currently playing, stop it
                if (currentAudio) {
                    currentAudio.pause();
                    currentAudio.currentTime = 0;
                    if (currentSpeakerBtn) {
                        currentSpeakerBtn.innerHTML = '🔊';
                    }
                    
                    // If the user clicked the same button that was playing, just stop and return
                    if (currentSpeakerBtn === btnElement) {
                        currentAudio = null;
                        currentSpeakerBtn = null;
                        return;
                    }
                }

                currentSpeakerBtn = btnElement;
                if (currentSpeakerBtn) {
                    currentSpeakerBtn.innerHTML = '⏳'; // Loading state
                }

                try {
                    const response = await fetch("http://localhost:8002/tts", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ text: text })
                    });
                    if (!response.ok) throw new Error("TTS failed");
                    
                    const blob = await response.blob();
                    const audioUrl = URL.createObjectURL(blob);
                    currentAudio = new Audio(audioUrl);
                    
                    currentAudio.onended = () => {
                        if (currentSpeakerBtn === btnElement) {
                            currentSpeakerBtn.innerHTML = '🔊';
                            currentAudio = null;
                            currentSpeakerBtn = null;
                        }
                    };

                    currentAudio.play();
                    
                    if (currentSpeakerBtn === btnElement) {
                        currentSpeakerBtn.innerHTML = '⏹️'; // Stop state
                    }
                } catch (error) {
                    console.error("Error playing TTS:", error);
                    if (currentSpeakerBtn === btnElement) {
                        currentSpeakerBtn.innerHTML = '🔊';
                    }
                }
            }

            function appendMessage(sender, text, interactionId = null) {
                const messageDiv = document.createElement('div');
                // RTL Layout adjustments: User is on the left (items-end), AI is on the right (items-start)
                messageDiv.className = sender === 'user' ? "flex flex-col items-end w-full" : "flex flex-col items-start w-full";
                
                if (sender === 'user') {
                    messageDiv.innerHTML = `
                        <span class="text-xs text-gray-500 mb-1 ml-1">أنت</span>
                        <div class="bg-[#177a94] text-white px-4 py-2.5 rounded-2xl rounded-tl-sm shadow-sm text-sm max-w-[85%] text-right leading-relaxed">
                            ${text}
                        </div>
                    `;
                } else {
                                        let feedbackHtml = '';
                    if (interactionId) {
                        feedbackHtml = `
                            <div class="flex gap-4 opacity-70 hover:opacity-100 transition-opacity">
                                <button type="button" class="feedback-btn hover:text-[#177a94] text-lg transition-transform hover:scale-110" data-id="${interactionId}" data-rating="up">👍</button>
                                <button type="button" class="feedback-btn hover:text-red-500 text-lg transition-transform hover:scale-110" data-id="${interactionId}" data-rating="down">👎</button>
                            </div>
                        `;
                    }
                    
                    messageDiv.innerHTML = `
                        <span class="text-xs text-gray-500 mb-1 mr-1">المساعد الذكي</span>
                        <div class="bg-white border border-gray-200 px-4 py-2.5 rounded-2xl rounded-tr-sm shadow-sm text-sm text-gray-800 text-right max-w-[85%] leading-relaxed">
                            ${text}
                        </div>
                        <div class="flex items-center gap-4 mt-2 mr-1">
                            <button type="button" class="speaker-btn hover:text-[#177a94] text-lg transition-transform hover:scale-110" title="استمع">🔊</button>
                            ${feedbackHtml}
                        </div>
                    `;
                }
                
                chatBox.appendChild(messageDiv);
                chatBox.scrollTop = chatBox.scrollHeight;

                // Bind speaker buttons
                const speakerBtns = messageDiv.querySelectorAll('.speaker-btn');
                speakerBtns.forEach(btn => {
                    btn.addEventListener('click', (e) => {
                        playTTS(text, e.currentTarget);
                    });
                });

                // Bind feedback buttons
                if (interactionId) {
                    const btns = messageDiv.querySelectorAll('.feedback-btn');
                    btns.forEach(btn => {
                        btn.addEventListener('click', async (e) => {
                            if(messageDiv.dataset.voted) return; // Allow only one vote per message
                            messageDiv.dataset.voted = "true";
                            
                            const rating = e.currentTarget.getAttribute('data-rating');
                            
                            // Visual feedback
                            btns.forEach(b => {
                                if (b !== e.currentTarget) b.style.opacity = '0.3';
                                b.style.cursor = 'default';
                            });

                            try {
                                await fetch("http://localhost:8002/feedback", {
                                    method: "POST",
                                    headers: { "Content-Type": "application/json" },
                                    body: JSON.stringify({ interaction_id: interactionId, rating: rating })
                                });
                            } catch(err) {
                                console.error("Feedback error", err);
                            }
                        });
                    });
                }
            }

            let chatHistory = [];

                        chatForm.addEventListener('submit', async (e) => {
                  e.preventDefault();
                  
                  // Block submission if STT is active or cleaning up
                  const sendBtn = document.getElementById('sendBtn');
                  if (sendBtn && sendBtn.disabled) return;

                const text = chatInput.value.trim();
                if(!text) return;

                // Append user message
                appendMessage('user', text);
                chatInput.value = '';
                
                // Show loading dots
                loadingIndicator.classList.remove("hidden");
                chatBox.scrollTop = chatBox.scrollHeight;

                const historyToSend = [...chatHistory];

                // Send request to localhost:8002/chat
                try {
                    const response = await fetch("http://localhost:8002/chat", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            organization_id: SESSION.organization_id,
                            user_id: SESSION.user_id,
                            query: text,
                            history: historyToSend
                        })
                    });

                    if (!response.ok) throw new Error("Server error");
                    const data = await response.json();
                    
                    loadingIndicator.classList.add("hidden");
                    const aiText = data.answer || data.response || data.message || data.text || "تم الاستلام بنجاح.";
                    appendMessage('ai', aiText, data.interaction_id);
                    

                    // Update memory
                    chatHistory.push({ role: 'user', content: [{ text: text }] });
                    chatHistory.push({ role: 'assistant', content: [{ text: aiText }] });

                } catch (error) {
                    console.error("Chat error:", error);
                    loadingIndicator.classList.add("hidden");
                    appendMessage('ai', "عذراً، حدث خطأ أثناء الاتصال بالخادم.");
                }
            });
        
}

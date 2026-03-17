document.addEventListener("DOMContentLoaded", function() {
    const chatBox = document.getElementById("chat-box");
    const chatInput = document.getElementById("chat-input");
    const sendBtn = document.getElementById("send-btn");

    // Legacy direct WS path was removed to prevent split-brain ownership.
    // Unified runtime path is /admin/api/chat/ws via API Gateway-aware clients.
    const socket = null;
    chatBox.innerHTML += "<p><em>Legacy admin_chat.js is disabled. Use the unified chat UI.</em></p>";


    if (!socket) {
        return;
    }

    socket.onopen = function(event) {
        chatBox.innerHTML += "<p><em>Connected to AI...</em></p>";
    };

    socket.onmessage = function(event) {
        // Since the backend streams raw lines, we need to parse the JSON content.
        // The AI service nests the actual content inside a 'delta' key.
        try {
            const data = JSON.parse(event.data);
            if (data && data.delta) { // Check for the 'delta' key
                chatBox.innerHTML += `<span>${data.delta}</span>`;
            } else if (event.data.includes("Error:")) { // Handle plain error messages
                chatBox.innerHTML += `<p style="color: red;">${event.data}</p>`;
            }
        } catch (e) {
            // If it's not valid JSON, it might be a plain text message or an error
            // This also handles the final full response from invoke_chat_stream
            // which is not a delta chunk. We can ignore it for a cleaner UI.
        }

        // Auto-scroll to the bottom
        chatBox.scrollTop = chatBox.scrollHeight;
    };

    socket.onclose = function(event) {
        chatBox.innerHTML += "<p><em>Connection closed.</em></p>";
    };

    socket.onerror = function(error) {
        chatBox.innerHTML += `<p><em>An error occurred: ${error.message}</em></p>`;
    };

    function sendMessage() {
        const message = chatInput.value;
        if (message.trim() !== "") {
            chatBox.innerHTML += `<p><b>You:</b> ${message}</p>`;
            socket.send(message);
            chatInput.value = "";
            chatBox.innerHTML += `<p><b>AI:</b> </p>`; // Prepare a new line for the AI's response
        }
    }

    sendBtn.addEventListener("click", sendMessage);
    chatInput.addEventListener("keypress", function(event) {
        if (event.key === "Enter") {
            sendMessage();
        }
    });
});

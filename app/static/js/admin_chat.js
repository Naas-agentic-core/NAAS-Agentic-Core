document.addEventListener("DOMContentLoaded", function() {
    const chatBox = document.getElementById("chat-box");
    const chatInput = document.getElementById("chat-input");
    const sendBtn = document.getElementById("send-btn");

    if (!chatBox || !chatInput || !sendBtn) {
        return;
    }

    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const token = localStorage.getItem("token");
    const wsUrl = `${protocol}://${window.location.host}/admin/api/chat/ws`;

    // Unified WS path through Gateway-compatible endpoint.
    const socket = token ? new WebSocket(wsUrl, ["jwt", token]) : new WebSocket(wsUrl);

    socket.onopen = function() {
        chatBox.innerHTML += "<p><em>Connected to AI...</em></p>";
    };

    socket.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            const payload = data && typeof data === "object" ? data.payload : null;
            const payloadContent = payload && typeof payload === "object" ? payload.content : "";
            const deltaContent = payloadContent || data.delta || "";

            if (deltaContent) {
                chatBox.innerHTML += `<span>${deltaContent}</span>`;
            } else if (data && data.type === "error") {
                const details = payload && payload.details ? payload.details : "Unexpected error";
                chatBox.innerHTML += `<p style=\"color: red;\">${details}</p>`;
            }
        } catch (_error) {
            if (String(event.data || "").includes("Error:")) {
                chatBox.innerHTML += `<p style=\"color: red;\">${event.data}</p>`;
            }
        }

        chatBox.scrollTop = chatBox.scrollHeight;
    };

    socket.onclose = function() {
        chatBox.innerHTML += "<p><em>Connection closed.</em></p>";
    };

    socket.onerror = function(error) {
        const message = error && error.message ? error.message : "WebSocket error";
        chatBox.innerHTML += `<p><em>An error occurred: ${message}</em></p>`;
    };

    function sendMessage() {
        const message = chatInput.value;
        if (message.trim() !== "" && socket.readyState === WebSocket.OPEN) {
            chatBox.innerHTML += `<p><b>You:</b> ${message}</p>`;
            socket.send(JSON.stringify({ question: message }));
            chatInput.value = "";
            chatBox.innerHTML += "<p><b>AI:</b> </p>";
        }
    }

    sendBtn.addEventListener("click", sendMessage);
    chatInput.addEventListener("keypress", function(event) {
        if (event.key === "Enter") {
            sendMessage();
        }
    });
});

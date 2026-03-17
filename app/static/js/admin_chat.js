document.addEventListener("DOMContentLoaded", function() {
    const chatBox = document.getElementById("chat-box");
    const chatInput = document.getElementById("chat-input");
    const sendBtn = document.getElementById("send-btn");

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
            const deltaContent = data?.payload?.content || data?.delta || "";
            if (deltaContent) {
                chatBox.innerHTML += `<span>${deltaContent}</span>`;
            } else if (data?.type === "error") {
                const details = data?.payload?.details || "Unexpected error";
                chatBox.innerHTML += `<p style=\"color: red;\">${details}</p>`;
            }
        } catch (e) {
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
        chatBox.innerHTML += `<p><em>An error occurred: ${error.message || "WebSocket error"}</em></p>`;
    };

    function sendMessage() {
        const message = chatInput.value;
        if (message.trim() !== "" && socket.readyState === WebSocket.OPEN) {
            chatBox.innerHTML += `<p><b>You:</b> ${message}</p>`;
            socket.send(JSON.stringify({ question: message }));
            chatInput.value = "";
            chatBox.innerHTML += `<p><b>AI:</b> </p>`;
        }
    }

    sendBtn.addEventListener("click", sendMessage);
    chatInput.addEventListener("keypress", function(event) {
        if (event.key === "Enter") {
            sendMessage();
        }
    });
});
